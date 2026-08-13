"""
ChromaDB Vector Service for LawAI
Manages vector storage and retrieval for legal documents
"""
import logging
import os
from typing import Any

import chromadb
from chromadb.config import Settings
from chromadb.errors import NotFoundError

from .embedding_service import get_embedding_service
from .query_expansion import expand_query
from .retrieval.structured_filter import parse_citation

logger = logging.getLogger(__name__)

DEFAULT_CHROMADB_PATH = "./chroma_db"
# An exact citation match is not a distance, but every consumer sorts and
# formats by one. Zero is the value a perfect cosine match would carry, and it
# keeps exact hits at the head of a merged multi-collection ranking.
EXACT_MATCH_DISTANCE = 0.0


class VectorService:
    """Service for managing ChromaDB collections and operations"""

    # Collection names
    BNS_COLLECTION = "bns_sections"
    BNSS_COLLECTION = "bnss_sections"
    BSA_COLLECTION = "bsa_sections"
    SC_JUDGEMENTS_COLLECTION = "sc_judgements"

    def __init__(self, persist_directory: str | None = None):
        """
        Initialize ChromaDB client with persistent storage

        Args:
            persist_directory: Directory for persistent storage. Defaults to
                ``CHROMADB_PATH`` from the environment, else ``./chroma_db``
                (CWD-relative, so this resolves under ``backend/`` in a normal
                dev run and to the mounted volume in a container).
        """
        try:
            self.persist_directory = persist_directory or os.getenv(
                "CHROMADB_PATH", DEFAULT_CHROMADB_PATH
            )
            persist_directory = self.persist_directory

            # Create directory if it doesn't exist
            os.makedirs(persist_directory, exist_ok=True)

            # Initialize ChromaDB client with persistent storage
            self.client = chromadb.PersistentClient(
                path=persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )

            # Get embedding service
            self.embedding_service = get_embedding_service()

            logger.info(f"ChromaDB initialized at {persist_directory}")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            raise

    def _get_or_create_collection(self, collection_name: str) -> chromadb.Collection:
        """
        Get or create a collection

        Args:
            collection_name: Name of the collection

        Returns:
            ChromaDB collection
        """
        try:
            collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            return collection
        except Exception as e:
            logger.error(f"Error getting/creating collection {collection_name}: {e}")
            raise

    def add_documents(
        self,
        collection_name: str,
        documents: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str]
    ) -> None:
        """
        Add documents to a collection

        Args:
            collection_name: Name of the collection
            documents: List of document texts
            metadatas: List of metadata dicts
            ids: List of unique IDs
        """
        try:
            if not documents or not metadatas or not ids:
                raise ValueError("Documents, metadatas, and ids cannot be empty")

            if len(documents) != len(metadatas) != len(ids):
                raise ValueError("Documents, metadatas, and ids must have same length")

            collection = self._get_or_create_collection(collection_name)

            # Generate embeddings
            embeddings = self.embedding_service.embed_texts(documents)

            # Add to collection
            collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids,
                embeddings=embeddings
            )

            logger.info(f"Added {len(documents)} documents to {collection_name}")
        except Exception as e:
            logger.error(f"Error adding documents to {collection_name}: {e}")
            raise

    def _exact_section_hits(
        self, collection: chromadb.Collection, collection_name: str, query: str
    ) -> dict[str, list[Any]]:
        """
        Fetch the section a query cites, by metadata rather than by embedding.

        A section number is nearly invisible to a dense embedder -- "482" and
        "483" land in almost the same place, and a section's text rarely
        repeats its own number -- so a cited section has to be looked up, not
        searched for. Returns empty when the query cites nothing, cites another
        act, or cites a repealed provision whose number cannot be translated
        (see ``services.retrieval.structured_filter``).
        """
        citation = parse_citation(query)
        if citation is None or not citation.resolvable:
            return {}
        if citation.collection is not None and citation.collection != collection_name:
            return {}

        # More than one section where a repealed provision was split across
        # several: IPC 376 is answered by BNS 64 and BNS 65 alike.
        sections = list(citation.sections)
        found = collection.get(
            where=(
                {"section_number": sections[0]}
                if len(sections) == 1
                else {"$or": [{"section_number": s} for s in sections]}
            ),
            include=["documents", "metadatas"],
        )
        if not found.get("ids"):
            logger.debug(
                f"{collection_name}: no section {', '.join(sections)} for cited {query!r}"
            )
            return {}

        logger.info(
            f"{collection_name}: citation {citation.act_name} {citation.section} "
            f"resolved to section {', '.join(sections)} "
            f"({len(found['ids'])} chunks) by exact lookup"
        )
        return {
            "ids": list(found["ids"]),
            "documents": list(found["documents"]),
            "metadatas": list(found["metadatas"]),
            "distances": [EXACT_MATCH_DISTANCE] * len(found["ids"]),
        }

    def search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        expand: bool = True,
        structured: bool = True
    ) -> dict[str, Any]:
        """
        Search for similar documents in a collection

        Args:
            collection_name: Name of the collection
            query: Search query
            top_k: Number of results to return
            expand: Append statutory phrasing for recognised terms of art and
                repealed code names before embedding (see
                ``services.query_expansion``). Only the *embedded* text is
                affected — callers still hold the user's original wording for
                display and for the generation prompt. Pass False to measure
                unexpanded behaviour.
            structured: Resolve a cited section by exact metadata lookup and
                rank it first, ahead of the vector results. Pass False to
                measure retrieval without it.

        Returns:
            Dict with 'documents', 'metadatas', 'distances', 'ids'
        """
        try:
            collection = self._get_or_create_collection(collection_name)

            exact = (
                self._exact_section_hits(collection, collection_name, query)
                if structured
                else {}
            )

            search_text = expand_query(query) if expand else query

            # Generate query embedding
            query_embedding = self.embedding_service.embed_text(search_text)

            # Search
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k
            )

            # Format results
            formatted_results = {
                'documents': results['documents'][0] if results['documents'] else [],
                'metadatas': results['metadatas'][0] if results['metadatas'] else [],
                'distances': results['distances'][0] if results['distances'] else [],
                'ids': results['ids'][0] if results['ids'] else []
            }

            if exact:
                formatted_results = self._merge_exact_hits(
                    exact, formatted_results, top_k
                )

            logger.info(f"Search in {collection_name} returned {len(formatted_results['documents'])} results")
            return formatted_results
        except Exception as e:
            logger.error(f"Error searching {collection_name}: {e}")
            raise

    @staticmethod
    def _merge_exact_hits(
        exact: dict[str, list[Any]], vector: dict[str, list[Any]], top_k: int
    ) -> dict[str, Any]:
        """
        Put the cited section first, then fill the rest from the vector hits.

        The vector results are kept rather than replaced: a citation is usually
        only part of what was asked ("section 35 of BNSS on arrest without
        warrant"), and the neighbouring sections are often what the reader
        actually needs. ``top_k`` still bounds the total, so an exact hit costs
        a vector hit rather than being added on top of one.
        """
        seen = set(exact["ids"])
        merged = {key: list(values) for key, values in exact.items()}
        for index, doc_id in enumerate(vector["ids"]):
            if len(merged["ids"]) >= top_k:
                break
            if doc_id in seen:
                continue
            seen.add(doc_id)
            for key in ("ids", "documents", "metadatas", "distances"):
                merged[key].append(vector[key][index])
        return merged

    def get_collection_stats(self, collection_name: str) -> dict[str, Any]:
        """
        Get statistics for a collection

        Args:
            collection_name: Name of the collection

        Returns:
            Dict with collection statistics
        """
        try:
            collection = self._get_or_create_collection(collection_name)
            count = collection.count()

            return {
                'name': collection_name,
                'count': count,
                'metadata': collection.metadata
            }
        except Exception as e:
            logger.error(f"Error getting stats for {collection_name}: {e}")
            raise

    def delete_collection(self, collection_name: str) -> None:
        """
        Delete a collection.

        Deleting something that is already absent is a no-op, not an error.
        The only caller is ``init_vector_db.py``'s reset path, which wants the
        collection *gone* — and on a fresh database chromadb raises
        ``NotFoundError`` instead. That made a first-run seed abort on the very
        first collection, which is precisely the path a new deployment takes.
        """
        try:
            self.client.delete_collection(collection_name)
            logger.info(f"Deleted collection {collection_name}")
        except NotFoundError:
            logger.info(f"Collection {collection_name} did not exist; nothing to delete")
        except Exception as e:
            logger.error(f"Error deleting collection {collection_name}: {e}")
            raise

    def reset_database(self) -> None:
        """Reset entire database (use with caution!)"""
        try:
            self.client.reset()
            logger.warning("Database reset completed")
        except Exception as e:
            logger.error(f"Error resetting database: {e}")
            raise


# Global instance
_vector_service: VectorService | None = None


def get_vector_service() -> VectorService:
    """Get or create the global vector service instance"""
    global _vector_service
    if _vector_service is None:
        _vector_service = VectorService()
    return _vector_service
