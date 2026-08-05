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

logger = logging.getLogger(__name__)

DEFAULT_CHROMADB_PATH = "./chroma_db"


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

    def search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        expand: bool = True
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

        Returns:
            Dict with 'documents', 'metadatas', 'distances', 'ids'
        """
        try:
            collection = self._get_or_create_collection(collection_name)

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

            logger.info(f"Search in {collection_name} returned {len(formatted_results['documents'])} results")
            return formatted_results
        except Exception as e:
            logger.error(f"Error searching {collection_name}: {e}")
            raise

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
