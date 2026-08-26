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
from .retrieval.lexical import (
    CANDIDATES,
    get_index,
    hybrid_enabled,
    reciprocal_rank_fusion,
)
from .retrieval.reranker import (
    DEFAULT_CANDIDATES,
    as_distance,
    get_reranker,
    rerank_enabled,
)
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
        Add or replace documents in a collection, keyed by id.

        Uses ``upsert`` rather than ``add``, which makes re-seeding idempotent
        in content and not merely in count. ``collection.add`` **silently
        discards** a write whose id already exists -- no exception, no warning,
        and the *previous* text is what stays indexed. That is the wrong
        failure for this corpus: re-running the seed after fixing a parse would
        report success while continuing to serve the old text. The concrete
        case is BNSS 531, which was 129,022 characters until the parser stopped
        it swallowing the First Schedule; under ``add`` the 1,873-character
        correction would never have landed.

        Ids are deterministic (``bns_103``, or ``bns_103__c2`` for a chunked
        section), so an upsert of the same corpus is a no-op and an upsert of a
        corrected one replaces exactly the chunks that changed.

        Args:
            collection_name: Name of the collection
            documents: List of document texts
            metadatas: List of metadata dicts
            ids: List of unique IDs

        Raises:
            ValueError: If any list is empty, or the three lengths differ
        """
        try:
            if not documents or not metadatas or not ids:
                raise ValueError("Documents, metadatas, and ids cannot be empty")

            # Compared against one length. Written as a chained comparison this
            # reads as `(a != b) and (b != c)`, which is False whenever two of
            # the three match -- so one list out of step, the likeliest
            # mismatch, passed straight through. chromadb catches it, so nothing
            # was mis-paired; what was lost was the diagnosis, since its error
            # names `embeddings`, a list the caller never passed.
            if not (len(documents) == len(metadatas) == len(ids)):
                raise ValueError(
                    "Documents, metadatas, and ids must have the same length "
                    f"(got {len(documents)}, {len(metadatas)}, {len(ids)})"
                )

            collection = self._get_or_create_collection(collection_name)

            # Generate embeddings
            embeddings = self.embedding_service.embed_texts(documents)

            collection.upsert(
                documents=documents,
                metadatas=metadatas,
                ids=ids,
                embeddings=embeddings
            )

            logger.info(f"Upserted {len(documents)} documents to {collection_name}")
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
        structured: bool = True,
        rerank: bool | None = None,
        hybrid: bool | None = None,
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
            rerank: Reorder the vector hits with a cross-encoder (see
                ``services.retrieval.reranker``). ``None`` follows the
                ``ENABLE_RERANK`` environment variable. Reranking pulls a
                deeper candidate pool and cuts back to ``top_k`` afterwards, so
                turning it on changes what the caller sees without changing
                what it asked for.
            hybrid: Fuse a BM25 ranking into the candidate pool by reciprocal
                rank fusion (see ``services.retrieval.lexical``). ``None``
                follows the ``ENABLE_HYBRID`` environment variable.

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

            # A reranker can only reorder what it is given, so it is given more
            # than the caller asked for; fusion goes deeper still, because it
            # decides which candidates the reranker ever sees.
            reranking = rerank_enabled() if rerank is None else rerank
            fusing = hybrid_enabled() if hybrid is None else hybrid
            n_results = top_k
            if reranking:
                n_results = max(n_results, DEFAULT_CANDIDATES)
            if fusing:
                n_results = max(n_results, CANDIDATES)

            # Search
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results
            )

            # Format results
            formatted_results = {
                'documents': results['documents'][0] if results['documents'] else [],
                'metadatas': results['metadatas'][0] if results['metadatas'] else [],
                'distances': results['distances'][0] if results['distances'] else [],
                'ids': results['ids'][0] if results['ids'] else []
            }

            if fusing:
                # The expanded text here too. Built on the raw query first, on
                # the reasoning that expansion is a crutch for an embedder that
                # cannot match a word it never sees, while BM25 matches words
                # it does -- so the appended phrase would be a second bag of
                # legal terms competing with the user's own.
                #
                # Measured, that was backwards. BM25 on the raw query scores
                # term_of_art at recall@3 0.250; on the expanded query, 0.938,
                # with recall@20 going 0.870 -> 0.986 overall and *not one
                # query regressing*. The alias table does not append vocabulary,
                # it appends the statute's own phrasing -- "power of High Court
                # to prevent abuse of process" is nearly verbatim BNSS 528 --
                # and matching literal text is the one thing BM25 is better at
                # than anything else here.
                #
                # Three layers now, and every one of them wants the expanded
                # query. The expansion is not a dense-retrieval workaround; it
                # is the bridge from what a lawyer says to what the gazette
                # printed, and every retriever needs to cross it.
                formatted_results = self._fuse_lexical(
                    collection, collection_name, search_text, formatted_results, n_results
                )

            if reranking:
                # The *expanded* text, not the user's wording. Reranking was
                # first built on the raw query, on the reasoning that expansion
                # is a crutch for a bi-encoder that never sees the chunk while a
                # cross-encoder does. Measured, that cost term_of_art 0.250 of
                # recall@3 and 0.306 of MRR -- the class where expansion is
                # load-bearing, because the term of art is absent from the
                # section that governs it. "Anticipatory" appears nowhere in
                # BNSS 482, so a cross-encoder shown "grounds for anticipatory
                # bail" reads a chunk that never says the word and demotes what
                # expansion had just surfaced. Seeing both texts together does
                # not help a model that has not been told they are the same
                # thing; the alias table is what says so.
                formatted_results = self._rerank(
                    search_text, formatted_results, top_k
                )
            elif n_results > top_k:
                # Fusion pulls a deeper pool than the caller asked for, and
                # reranking is what normally cuts it back. With reranking off
                # nothing did, so ``search(top_k=6)`` returned thirty results
                # and every caller's context budget silently grew fivefold.
                formatted_results = {
                    key: values[:top_k] for key, values in formatted_results.items()
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
    def _fuse_lexical(
        collection: Any,
        collection_name: str,
        query: str,
        dense: dict[str, Any],
        n_results: int,
    ) -> dict[str, Any]:
        """
        Fuse a BM25 ranking into the dense candidates by reciprocal rank fusion.

        The two retrievers fail on disjoint sets, which is the only reason this
        is worth its complexity: measured alone over the golden set, BM25 beats
        dense at recall@3 on citation (0.875 vs 0.250), judgement (1.000 vs
        0.833) and plain (1.000 vs 0.960), and is beaten badly on term_of_art
        (0.250 vs 0.875). One matches the query's words, the other matches its
        meaning, and legal questions come in both shapes.

        A chunk BM25 finds that dense missed has no distance of its own, so it
        is given the worst distance in the dense list rather than a fabricated
        one. The number is a floor, not a measurement -- what orders the list
        after this is fusion rank and then the cross-encoder, both of which
        ignore it. It exists so downstream code that reads ``distances`` gets a
        value that cannot overstate the match.
        """
        index = get_index(collection, collection_name)
        if index is None:
            return dense

        # Both rankings are expressed in the same identity so a chunk found by
        # both fuses as one document. Without that it appears twice and RRF
        # counts it as two documents that one retriever liked, rather than one
        # that both did -- which inverts the property fusion is bought for.
        by_key: dict[str, dict[str, Any]] = {}
        dense_ranking: list[str] = []
        for position, chroma_id in enumerate(dense["ids"]):
            key = VectorService._chunk_key(dense["metadatas"][position], chroma_id)
            dense_ranking.append(key)
            by_key.setdefault(key, {
                "id": chroma_id,
                "document": dense["documents"][position],
                "metadata": dense["metadatas"][position],
                "distance": dense["distances"][position],
            })

        # A lexical-only hit has no distance of its own. It is given the worst
        # in the dense list -- a floor, not a measurement. What orders the list
        # from here is fusion rank and then the cross-encoder, both of which
        # ignore it; it exists so downstream code reading ``distances`` cannot
        # be handed a number that overstates the match.
        worst = max(dense["distances"], default=1.0)
        lexical_ranking: list[str] = []
        for position in index.top(query, n_results):
            metadata = index.metadatas[position]
            key = VectorService._chunk_key(metadata)
            lexical_ranking.append(key)
            by_key.setdefault(key, {
                "id": key,
                "document": index.documents[position],
                "metadata": metadata,
                "distance": worst,
            })

        fused = reciprocal_rank_fusion([dense_ranking, lexical_ranking])[:n_results]
        return {
            "ids": [by_key[key]["id"] for key in fused],
            "documents": [by_key[key]["document"] for key in fused],
            "metadatas": [by_key[key]["metadata"] for key in fused],
            "distances": [by_key[key]["distance"] for key in fused],
        }

    @staticmethod
    def _chunk_key(metadata: dict[str, Any], fallback: str | None = None) -> str:
        """
        A stable identity for a chunk, so the two retrievers fuse as one list.

        Fusion has to recognise that dense hit #3 and lexical hit #7 are the
        same chunk, or the document appears twice and RRF counts it as two
        documents one retriever liked rather than one both did. The BM25 index
        is built from ``collection.get``, which returns documents and metadata
        without the ids ``collection.query`` returns, so identity comes from
        the metadata the ingest wrote: the parent document plus which chunk of
        it this is.
        """
        parent = metadata.get("parent_id") or metadata.get("id")
        if not parent:
            return fallback or f"?#{metadata.get('chunk_index', 0)}"
        return f"{parent}#{metadata.get('chunk_index', 0)}"

    @staticmethod
    def _rerank(
        query: str, results: dict[str, Any], top_k: int
    ) -> dict[str, Any]:
        """
        Reorder vector hits by cross-encoder relevance and cut to ``top_k``.

        The bi-encoder's distances are kept under ``vector_distances`` and
        ``distances`` is rewritten from the rerank scores. That is not
        bookkeeping: ``RAGService._format_sources`` turns a distance into the
        relevance score the UI shows, so an ordering from one model beside
        scores from another puts the second source above the first on the page.
        Whichever model decided the order has to be the one that explains it.

        A reranker that cannot load leaves the order alone and the list is
        simply truncated -- the caller still gets ``top_k`` bi-encoder hits,
        which is what it would have got had reranking never been asked for.
        """
        documents = results["documents"]
        if not documents:
            return results

        order = get_reranker().order(query, documents)
        if order is None:
            return {key: values[:top_k] for key, values in results.items()}

        order = order[:top_k]
        scores = get_reranker().score(query, documents) or []
        reranked: dict[str, Any] = {
            key: [results[key][i] for i in order]
            for key in ("ids", "documents", "metadatas")
        }
        reranked["vector_distances"] = [results["distances"][i] for i in order]
        reranked["distances"] = [as_distance(scores[i]) for i in order]
        return reranked

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

    # -- atomic rebuild ----------------------------------------------------
    #
    # ChromaDB has no transactions, so a multi-batch write cannot be rolled
    # back: a seed that dies on batch 7 of 13 leaves a collection that is
    # half the corpus and reports itself perfectly healthy. Nothing downstream
    # can tell a partial index from a small one, and the failure is silent in
    # the direction that matters -- retrieval simply stops finding things.
    #
    # What chromadb does give is a rename, which is a metadata operation. So a
    # rebuild is written into a staging collection under a different name and
    # only becomes visible by renaming it into place. Readers see the previous
    # index until the moment the new one is complete and verified, and a crash
    # at any point before the swap leaves the live collection untouched.
    #
    # The swap itself is two renames, because chromadb refuses to rename onto a
    # name that exists (UNIQUE constraint on collections.name):
    #
    #     live -> retired      (metadata write)
    #     staging -> live      (metadata write)
    #     drop retired         (slow, but live is already correct)
    #
    # The uncovered window is between the two renames rather than spanning a
    # whole collection delete, and `repair_interrupted_rebuild` recovers from
    # a crash inside it.

    STAGING_SUFFIX = "__staging"
    RETIRED_SUFFIX = "__retired"

    def staging_name(self, collection_name: str) -> str:
        return f"{collection_name}{self.STAGING_SUFFIX}"

    def list_collection_names(self) -> list[str]:
        return [c.name for c in self.client.list_collections()]

    def begin_rebuild(self, collection_name: str) -> str:
        """
        Open an empty staging collection for ``collection_name``.

        Any staging collection left by a previous failed run is dropped first:
        it holds an unknown prefix of an unknown corpus, and appending to it
        would produce a mix of two builds that no hash would detect.
        """
        staging = self.staging_name(collection_name)
        self.delete_collection(staging)
        self._get_or_create_collection(staging)
        logger.info(f"staging {staging} opened for rebuild of {collection_name}")
        return staging

    def promote_rebuild(self, collection_name: str, expected_chunks: int) -> None:
        """
        Swap a completed staging collection into place.

        ``expected_chunks`` is checked before anything is swapped, so a staging
        collection that silently lost writes -- the exact failure ``upsert``
        was introduced to prevent -- cannot be promoted over a good index.

        Raises:
            ValueError: If staging is absent or holds the wrong number of rows.
        """
        staging = self.staging_name(collection_name)
        if staging not in self.list_collection_names():
            raise ValueError(f"no staging collection {staging} to promote")

        actual = self._get_or_create_collection(staging).count()
        if actual != expected_chunks:
            raise ValueError(
                f"refusing to promote {staging}: holds {actual} chunks, expected "
                f"{expected_chunks}. The live index has not been touched."
            )

        retired = f"{collection_name}{self.RETIRED_SUFFIX}"
        self.delete_collection(retired)

        names = self.list_collection_names()
        if collection_name in names:
            self.client.get_collection(collection_name).modify(name=retired)
        self.client.get_collection(staging).modify(name=collection_name)
        self.delete_collection(retired)

        logger.info(f"promoted {staging} -> {collection_name} ({actual} chunks)")

    def abandon_rebuild(self, collection_name: str) -> None:
        """Drop a staging collection without promoting it."""
        self.delete_collection(self.staging_name(collection_name))

    def repair_interrupted_rebuild(self, collection_name: str) -> str | None:
        """
        Recover from a crash inside the two-rename swap.

        The only losable state is a process death between renaming the live
        collection to ``__retired`` and renaming staging into its place, which
        leaves no collection under the real name. Both possible worlds are
        recoverable, and neither invents data:

        - a retired collection exists and the live name does not -> the swap
          had not completed, so rename the retired one back. The index is the
          previous good one and the rebuild is simply lost.
        - the live name exists -> the swap completed; any leftover retired or
          staging collection is debris and is dropped.

        Returns a description of what was repaired, or None if nothing was.
        """
        names = self.list_collection_names()
        retired = f"{collection_name}{self.RETIRED_SUFFIX}"
        staging = self.staging_name(collection_name)

        if collection_name not in names and retired in names:
            self.client.get_collection(retired).modify(name=collection_name)
            self.delete_collection(staging)
            message = (
                f"recovered {collection_name} from an interrupted rebuild; the "
                "previous index was restored and the rebuild discarded"
            )
            logger.warning(message)
            return message

        debris = [n for n in (retired, staging) if n in names]
        if collection_name in names and debris:
            for name in debris:
                self.delete_collection(name)
            message = f"cleared debris from a previous rebuild: {', '.join(debris)}"
            logger.info(message)
            return message
        return None


# Global instance
_vector_service: VectorService | None = None


def get_vector_service() -> VectorService:
    """Get or create the global vector service instance"""
    global _vector_service
    if _vector_service is None:
        _vector_service = VectorService()
    return _vector_service
