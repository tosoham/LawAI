#!/bin/sh
# Bring the vector store up to date, then hand off to the real command.
#
# The ChromaDB directory lives on a named volume rather than in the image: it is
# derived data (~70 MB of binary index), and baking it in would mean re-running
# the whole embedding pass on every unrelated layer change.
#
# This used to gate on a marker file: seed if absent, skip if present. That
# answered "has a seed ever finished here?" when the question worth asking is
# "does this store match this image?" -- and the two come apart every time the
# corpus is updated, because a new image with new data would find the old
# marker and serve the old corpus, silently and indefinitely.
#
# init_vector_db.py now answers the real question itself. It reads the manifest
# written beside the store, compares the embedding model, dimension and chunk
# parameters against its own, hashes each collection's contents, and rebuilds
# only what actually moved. On an unchanged store that is a few seconds of
# hashing and no embedding at all, so it is cheap enough to run on every start
# and correct in the cases a marker got wrong:
#
#   fresh volume           -> full build
#   unchanged image        -> no-op
#   corpus updated         -> rebuild the collections that changed
#   embedding model swapped-> full rebuild (the vectors are not comparable)
#   previous seed crashed  -> partial build discarded, rebuilt from scratch
#
# The rebuild is atomic per collection, so a container killed mid-seed leaves
# the previous index in place and serving rather than a half-filled one.
#
# Set SKIP_DB_INIT=true to bypass entirely (a pre-seeded volume, or the test
# suite, which does not need the corpus).
set -e

if [ "${SKIP_DB_INIT}" = "true" ]; then
    echo "[entrypoint] SKIP_DB_INIT=true - leaving ${CHROMADB_PATH:-/data/chroma_db} alone"
else
    echo "[entrypoint] Reconciling the vector store with this image's corpus."
    echo "[entrypoint] A first build embeds ~3,200 chunks and takes a few minutes;"
    echo "[entrypoint] an unchanged store is a no-op and starts immediately."
    python scripts/init_vector_db.py
    echo "[entrypoint] Vector store ready."
fi

exec "$@"
