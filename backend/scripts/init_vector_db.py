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

Usage:
    python scripts/init_vector_db.py            # seed, replacing existing data
    python scripts/init_vector_db.py --keep     # add without clearing first
"""
import argparse
import logging
import os
import re
import sys
from typing import Any

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.data_loader import LegalDataLoader
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
    judgement.
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


def init_collection(
    vector_service: VectorService,
    collection_name: str,
    data: list[dict[str, Any]],
    data_type: str,
    reset: bool,
) -> None:
    """Populate a collection from the given records."""
    try:
        if reset:
            vector_service.delete_collection(collection_name)

        chunks = chunk_records(data)
        logger.info(
            f"Initializing {collection_name}: {len(data)} {data_type} "
            f"-> {len(chunks)} chunks"
        )

        for start in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[start:start + BATCH_SIZE]
            vector_service.add_documents(
                collection_name=collection_name,
                documents=[c["text"] for c in batch],
                metadatas=[c["metadata"] for c in batch],
                ids=[c["id"] for c in batch],
            )
            logger.info(
                f"  {collection_name}: {min(start + BATCH_SIZE, len(chunks))}/{len(chunks)}"
            )

        stats = vector_service.get_collection_stats(collection_name)
        logger.info(f"✓ {collection_name}: {stats['count']} chunks loaded")

    except Exception as e:
        logger.error(f"✗ Failed to initialize {collection_name}: {e}")
        raise


def main():
    """Main initialization function"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep", action="store_true",
        help="Add to the existing collections instead of clearing them first",
    )
    args = parser.parse_args()
    reset = not args.keep

    try:
        logger.info("=" * 60)
        logger.info("LawAI Vector Database Initialization")
        logger.info("=" * 60)

        # Initialize services
        logger.info("Initializing services...")
        vector_service = get_vector_service()
        data_loader = LegalDataLoader()

        # Load the ingested corpus
        logger.info("Loading processed legal corpus...")
        all_data = data_loader.load_all_data()

        logger.info(f"\nPopulating collections (reset={reset})...")

        for collection_name, key, label in (
            (VectorService.BNS_COLLECTION, 'bns', "BNS sections"),
            (VectorService.BNSS_COLLECTION, 'bnss', "BNSS sections"),
            (VectorService.BSA_COLLECTION, 'bsa', "BSA sections"),
            (VectorService.SC_JUDGEMENTS_COLLECTION, 'sc_judgements', "SC judgements"),
        ):
            init_collection(vector_service, collection_name, all_data[key], label, reset)

        # Print summary
        logger.info("\n" + "=" * 60)
        logger.info("Initialization Complete!")
        logger.info("=" * 60)

        logger.info("\nCollection Summary:")
        for collection_name in [
            VectorService.BNS_COLLECTION,
            VectorService.BNSS_COLLECTION,
            VectorService.BSA_COLLECTION,
            VectorService.SC_JUDGEMENTS_COLLECTION
        ]:
            stats = vector_service.get_collection_stats(collection_name)
            logger.info(f"  • {collection_name}: {stats['count']} chunks")

        total_docs = sum(len(v) for v in all_data.values())
        logger.info(f"\nTotal source documents: {total_docs}")
        logger.info("\n✓ Vector database is ready for use!")
        logger.info("  You can now run the API server and perform RAG searches.")

    except Exception as e:
        logger.error(f"\n✗ Initialization failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
