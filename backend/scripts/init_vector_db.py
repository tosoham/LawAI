#!/usr/bin/env python3
"""
Seed ChromaDB with the ingested Indian legal corpus.

Reads ``data/processed/*.json`` (produced by ``scripts/ingest_legal_acts.py``
and ``scripts/ingest_judgments.py``) and populates the BNS, BNSS, BSA and
Supreme Court judgement collections.

Long documents are split before embedding. The embedding model
(``all-MiniLM-L6-v2``) truncates at roughly 256 word-piece tokens, so a 60,000
character judgement would otherwise be represented by its first paragraph alone
and would never match a query about its actual holding.

Three properties this script is built around
--------------------------------------------

**The swap is atomic.** ChromaDB has no transactions, so a seed that dies on
batch 7 of 13 used to leave a collection holding half the corpus and reporting
itself healthy -- nothing downstream can distinguish a partial index from a
small one, and retrieval just quietly stops finding things. Each collection is
now rebuilt into a *staging* collection and renamed into place only once it is
complete and its row count verified. Readers see the previous index until that
moment, and a crash before it leaves the live index untouched.

**Unchanged work is not redone.** Every chunk carries a content hash, and every
collection carries the hash of all of them. A collection whose hash matches the
manifest is skipped outright, and within a collection that *has* changed, chunks
whose hashes are unchanged have their vectors copied from the live index rather
than recomputed. Re-seeding after a one-section fix costs one embedding, not
3,184.

**The index records what produced it.** Model, dimension and chunk parameters go
into ``index_manifest.json`` beside the store. Querying an index with a different
embedding model than built it is silent and total -- well-formed numbers,
meaningless distances -- so the seed refuses to append across that change and
rebuilds instead.

Usage:
    python scripts/init_vector_db.py                  # seed what has changed
    python scripts/init_vector_db.py --force          # rebuild everything
    python scripts/init_vector_db.py --dry-run        # report the plan only
    python scripts/init_vector_db.py --collection bns_sections
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.data_loader import LegalDataLoader
from services.embedding_service import get_embedding_service
from services.index_manifest import IndexManifest, chunk_hash, content_hash
from services.vector_service import VectorService, get_vector_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Sized for all-MiniLM-L6-v2's ~256 token window, with overlap so a passage
# split across a boundary is still retrievable from either side.
MAX_CHUNK_CHARS = 1200
CHUNK_OVERLAP_CHARS = 150
# Documents are embedded in batches to bound peak memory during seeding.
BATCH_SIZE = 256
# A write can fail for reasons that pass on their own -- a busy sqlite file,
# a transient filesystem hiccup on a mounted volume. Retried with a widening
# gap so a five-minute pass is not lost to a hundred-millisecond problem.
MAX_WRITE_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.5


def split_text(text: str) -> list[str]:
    """Split text into overlapping chunks, preferring paragraph boundaries."""
    text = text.strip()
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]

    # Break on paragraphs first, then sentences, so chunks stay coherent.
    pieces = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    units: list[str] = []
    for piece in pieces:
        if len(piece) <= MAX_CHUNK_CHARS:
            units.append(piece)
            continue
        for sentence in re.split(r"(?<=[.;:])\s+", piece):
            sentence = sentence.strip()
            if not sentence:
                continue
            while len(sentence) > MAX_CHUNK_CHARS:
                units.append(sentence[:MAX_CHUNK_CHARS])
                sentence = sentence[MAX_CHUNK_CHARS - CHUNK_OVERLAP_CHARS:]
            units.append(sentence)

    chunks: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}" if current else unit
        if len(candidate) <= MAX_CHUNK_CHARS:
            current = candidate
            continue
        if current:
            chunks.append(current)
            tail = current[-CHUNK_OVERLAP_CHARS:]
            current = f"{tail}\n\n{unit}" if len(unit) < MAX_CHUNK_CHARS else unit
        else:
            current = unit
    if current:
        chunks.append(current)

    return chunks or [text[:MAX_CHUNK_CHARS]]


def chunk_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Expand records into embeddable chunks.

    Every chunk keeps its parent's metadata plus ``parent_id`` and chunk
    counters, so a retrieved chunk can still be cited as its source section or
    judgement. Ids are deterministic, which is what lets a re-seed replace
    exactly the chunks that changed.
    """
    chunked: list[dict[str, Any]] = []

    for record in records:
        parts = split_text(record["text"])
        for index, part in enumerate(parts):
            metadata = dict(record["metadata"])
            metadata["parent_id"] = record["id"]
            metadata["chunk_index"] = index
            metadata["chunk_count"] = len(parts)
            chunked.append({
                "id": record["id"] if len(parts) == 1 else f"{record['id']}__c{index}",
                "text": part,
                "metadata": metadata,
            })

    return chunked


@dataclass
class SeedPlan:
    """What one collection needs, decided before anything is written."""

    collection_name: str
    label: str
    documents: int
    chunks: list[dict[str, Any]]
    digest: str
    reason: str
    needs_rebuild: bool

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)


@dataclass
class SeedOutcome:
    collection_name: str
    skipped: bool = False
    embedded: int = 0
    reused: int = 0
    seconds: float = 0.0
    reason: str = ""


@dataclass
class _Progress:
    """Throughput reporting for a long pass, so a stall is visible as one."""

    total: int
    started: float = field(default_factory=time.monotonic)

    def log(self, name: str, done: int) -> None:
        elapsed = max(time.monotonic() - self.started, 1e-6)
        rate = done / elapsed
        remaining = (self.total - done) / rate if rate > 0 else 0.0
        logger.info(
            f"  {name}: {done}/{self.total} chunks "
            f"({rate:.0f}/s, ~{remaining:.0f}s left)"
        )


def plan_collection(
    collection_name: str,
    label: str,
    records: list[dict[str, Any]],
    manifest: IndexManifest | None,
    force: bool,
) -> SeedPlan:
    """Decide whether a collection needs rebuilding, without writing anything."""
    chunks = chunk_records(records)
    digest = content_hash(chunks)

    if force:
        reason, needs_rebuild = "forced", True
    elif manifest is None:
        reason, needs_rebuild = "no manifest — provenance unknown", True
    elif manifest.collection_is_current(collection_name, digest):
        reason, needs_rebuild = "unchanged", False
    elif collection_name not in manifest.collections:
        reason, needs_rebuild = "not in manifest", True
    else:
        previous = manifest.collections[collection_name]
        reason = (
            f"corpus changed ({previous.chunks} -> {len(chunks)} chunks)"
            if previous.chunks != len(chunks)
            else "corpus content changed"
        )
        needs_rebuild = True

    return SeedPlan(
        collection_name=collection_name,
        label=label,
        documents=len(records),
        chunks=chunks,
        digest=digest,
        reason=reason,
        needs_rebuild=needs_rebuild,
    )


def _existing_vectors(
    vector_service: VectorService, collection_name: str, chunks: list[dict[str, Any]]
) -> dict[str, list[float]]:
    """
    Vectors from the live index for chunks whose content has not changed.

    Re-embedding text that did not change is the bulk of a re-seed's cost and
    buys nothing: the same model over the same string is the same vector. The
    hash is stored on each row so this comparison needs no second source of
    truth.

    Failure here is not fatal -- an unreadable live collection just means
    everything is embedded fresh, which is correct, only slower.
    """
    if collection_name not in vector_service.list_collection_names():
        return {}

    wanted = {c["id"]: chunk_hash(c) for c in chunks}
    try:
        collection = vector_service._get_or_create_collection(collection_name)
        found = collection.get(
            ids=list(wanted), include=["embeddings", "metadatas"]
        )
    except Exception as error:
        # Broad on purpose: reuse is an optimisation, and failing to read the
        # old vectors must cost speed, never correctness.
        logger.warning(f"could not read existing vectors from {collection_name}: {error}")
        return {}

    embeddings = found.get("embeddings")
    if embeddings is None or len(embeddings) == 0:
        return {}

    reusable: dict[str, list[float]] = {}
    for index, doc_id in enumerate(found.get("ids", [])):
        metadata = (found.get("metadatas") or [{}] * len(found["ids"]))[index] or {}
        if metadata.get("content_hash") == wanted.get(doc_id):
            reusable[doc_id] = list(embeddings[index])
    return reusable


def _write_batch(
    vector_service: VectorService,
    staging: str,
    batch: list[dict[str, Any]],
    reusable: dict[str, list[float]],
) -> tuple[int, int]:
    """
    Write one batch into staging, embedding only what changed.

    Returns (embedded, reused).
    """
    embedding_service = get_embedding_service()

    fresh = [c for c in batch if c["id"] not in reusable]
    computed: dict[str, list[float]] = {}
    if fresh:
        vectors = embedding_service.embed_texts([c["text"] for c in fresh])
        computed = {c["id"]: v for c, v in zip(fresh, vectors, strict=True)}

    collection = vector_service._get_or_create_collection(staging)
    collection.upsert(
        documents=[c["text"] for c in batch],
        metadatas=[c["metadata"] for c in batch],
        ids=[c["id"] for c in batch],
        embeddings=[computed.get(c["id"]) or reusable[c["id"]] for c in batch],
    )
    return len(fresh), len(batch) - len(fresh)


def seed_collection(
    vector_service: VectorService, plan: SeedPlan
) -> SeedOutcome:
    """
    Rebuild one collection atomically.

    Everything is written into a staging collection; the live one is replaced
    only after every batch has landed and the row count has been verified. Any
    failure abandons staging and leaves the live index exactly as it was.
    """
    started = time.monotonic()
    if not plan.needs_rebuild:
        logger.info(
            f"✓ {plan.collection_name}: {plan.reason} "
            f"({plan.chunk_count} chunks) — skipped"
        )
        return SeedOutcome(plan.collection_name, skipped=True, reason=plan.reason)

    logger.info(
        f"Rebuilding {plan.collection_name}: {plan.documents} {plan.label} "
        f"-> {plan.chunk_count} chunks ({plan.reason})"
    )

    # The hash travels with the row, so the next run can tell which chunks
    # changed without re-reading the corpus.
    for chunk in plan.chunks:
        chunk["metadata"]["content_hash"] = chunk_hash(chunk)

    reusable = _existing_vectors(vector_service, plan.collection_name, plan.chunks)
    if reusable:
        logger.info(
            f"  {plan.collection_name}: {len(reusable)} of {plan.chunk_count} chunks "
            "unchanged — reusing their vectors"
        )

    staging = vector_service.begin_rebuild(plan.collection_name)
    progress = _Progress(total=plan.chunk_count)
    embedded = reused = 0

    try:
        for start in range(0, plan.chunk_count, BATCH_SIZE):
            batch = plan.chunks[start:start + BATCH_SIZE]
            for attempt in range(1, MAX_WRITE_ATTEMPTS + 1):
                try:
                    new, old = _write_batch(vector_service, staging, batch, reusable)
                    embedded += new
                    reused += old
                    break
                except Exception as error:
                    # Broad on purpose: retried below, re-raised on the last attempt.
                    if attempt == MAX_WRITE_ATTEMPTS:
                        raise
                    pause = RETRY_BACKOFF_SECONDS * attempt
                    logger.warning(
                        f"  {plan.collection_name}: batch at {start} failed "
                        f"(attempt {attempt}/{MAX_WRITE_ATTEMPTS}): {error}. "
                        f"retrying in {pause:.1f}s"
                    )
                    time.sleep(pause)
            progress.log(plan.collection_name, min(start + BATCH_SIZE, plan.chunk_count))

        vector_service.promote_rebuild(plan.collection_name, plan.chunk_count)
    except Exception:
        # The live collection was never touched; drop the partial build so the
        # next run does not find a staging collection holding half a corpus.
        vector_service.abandon_rebuild(plan.collection_name)
        logger.error(
            f"✗ {plan.collection_name}: rebuild failed and was abandoned. "
            "The previous index is still in place and still serving."
        )
        raise

    seconds = time.monotonic() - started
    logger.info(
        f"✓ {plan.collection_name}: {plan.chunk_count} chunks live "
        f"({embedded} embedded, {reused} reused, {seconds:.1f}s)"
    )
    return SeedOutcome(
        plan.collection_name, embedded=embedded, reused=reused, seconds=seconds
    )


COLLECTIONS = (
    (VectorService.BNS_COLLECTION, 'bns', "BNS sections"),
    (VectorService.BNSS_COLLECTION, 'bnss', "BNSS sections"),
    (VectorService.BSA_COLLECTION, 'bsa', "BSA sections"),
    (VectorService.SC_JUDGEMENTS_COLLECTION, 'sc_judgements', "SC judgements"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true",
        help="rebuild every collection even if the corpus is unchanged",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report what would be rebuilt and why, then exit without writing",
    )
    parser.add_argument(
        "--collection", action="append", dest="only",
        help="restrict to one collection (repeatable)",
    )
    args = parser.parse_args()

    try:
        logger.info("=" * 60)
        logger.info("LawAI Vector Database Initialization")
        logger.info("=" * 60)

        vector_service = get_vector_service()
        embedding_service = get_embedding_service()
        data_loader = LegalDataLoader()
        store = vector_service.persist_directory

        current = IndexManifest(
            embedding_model=embedding_service.model_name,
            embedding_dimension=embedding_service.get_embedding_dimension(),
            chunk_max_chars=MAX_CHUNK_CHARS,
            chunk_overlap_chars=CHUNK_OVERLAP_CHARS,
        )
        previous = IndexManifest.read(store)

        # An index built by a different model is not repairable by appending to
        # it: the vectors are incomparable and no query would reveal that.
        force = args.force
        if previous is not None:
            mismatch = current.incompatible_with(previous)
            if mismatch:
                logger.warning(f"Rebuilding the whole index — {mismatch}")
                force = True
            else:
                current.collections = dict(previous.collections)

        selected = [c for c in COLLECTIONS if not args.only or c[0] in args.only]
        if not selected:
            logger.error(f"No such collection: {', '.join(args.only or [])}")
            return 2

        # Recover anything a previous crash left mid-swap before planning, so
        # the counts a plan is based on are the counts that will be read.
        for collection_name, _, _ in selected:
            vector_service.repair_interrupted_rebuild(collection_name)

        logger.info("Loading processed legal corpus...")
        all_data = data_loader.load_all_data()

        plans = [
            plan_collection(
                collection_name, label, all_data[key],
                None if force else previous, force,
            )
            for collection_name, key, label in selected
        ]

        logger.info("\nPlan:")
        for plan in plans:
            verb = "rebuild" if plan.needs_rebuild else "skip"
            logger.info(
                f"  {plan.collection_name:<20} {verb:<8} "
                f"{plan.chunk_count:>5} chunks  ({plan.reason})"
            )

        if args.dry_run:
            logger.info("\n--dry-run: nothing was written.")
            return 0

        outcomes = [seed_collection(vector_service, plan) for plan in plans]

        for plan in plans:
            current.record(
                plan.collection_name, plan.documents, plan.chunk_count, plan.digest
            )
        current.write(store)

        logger.info("\n" + "=" * 60)
        logger.info("Initialization Complete!")
        logger.info("=" * 60)
        logger.info(f"\nStore: {store}")
        logger.info(f"Model: {current.embedding_model} "
                    f"({current.embedding_dimension}d, build "
                    f"{current.build_fingerprint()})")

        logger.info("\nCollection Summary:")
        for plan in plans:
            stats = vector_service.get_collection_stats(plan.collection_name)
            logger.info(f"  • {plan.collection_name}: {stats['count']} chunks")

        rebuilt = [o for o in outcomes if not o.skipped]
        logger.info(
            f"\n{len(rebuilt)} rebuilt, {len(outcomes) - len(rebuilt)} unchanged; "
            f"{sum(o.embedded for o in rebuilt)} chunks embedded, "
            f"{sum(o.reused for o in rebuilt)} reused."
        )
        logger.info("\n✓ Vector database is ready for use!")
        return 0

    except Exception as e:
        logger.error(f"\n✗ Initialization failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
