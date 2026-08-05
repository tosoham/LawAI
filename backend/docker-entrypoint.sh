#!/bin/sh
# Seed the vector store on first start, then hand off to the real command.
#
# The ChromaDB directory lives on a named volume rather than in the image: it is
# derived data (~70 MB of binary index), and baking it in would mean re-running
# the whole embedding pass on every unrelated layer change. Seeding here keeps
# `docker compose up` a single step for a new checkout while leaving restarts
# fast.
#
# Set SKIP_DB_INIT=true to bypass this (e.g. when pointing at a pre-seeded
# volume, or running the test suite, which does not need the corpus).
set -e

CHROMADB_PATH="${CHROMADB_PATH:-/data/chroma_db}"
# Written only after init_vector_db.py exits 0. Do NOT test for chroma.sqlite3
# instead: chromadb creates that file the moment a client connects, so a seed
# that crashed part-way would look complete on the next start and the API would
# happily serve an empty corpus.
SEEDED_MARKER="${CHROMADB_PATH}/.lawai-seeded"

if [ "${SKIP_DB_INIT}" = "true" ]; then
    echo "[entrypoint] SKIP_DB_INIT=true - leaving ${CHROMADB_PATH} alone"
elif [ -f "${SEEDED_MARKER}" ]; then
    echo "[entrypoint] Vector store already seeded at ${CHROMADB_PATH} - skipping init"
else
    echo "[entrypoint] No seeded vector store at ${CHROMADB_PATH} - building it now."
    echo "[entrypoint] This embeds ~3,300 chunks and takes a few minutes; it"
    echo "[entrypoint] only happens once, because the volume persists."
    python scripts/init_vector_db.py
    touch "${SEEDED_MARKER}"
    echo "[entrypoint] Vector store ready."
fi

exec "$@"
