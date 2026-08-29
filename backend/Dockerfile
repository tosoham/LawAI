# LawAI backend image.
#
# Two things drive the shape of this file:
#
#   1. sentence-transformers pulls in torch. The default wheel carries the CUDA
#      runtime (~2.5 GB) which is dead weight here -- embeddings run on CPU. We
#      install the CPU-only build first so pip treats the dependency as already
#      satisfied.
#   2. The embedding model is baked into the image rather than downloaded on
#      first request, so a container starts without reaching out to HuggingFace
#      and an offline deployment (ENABLE_LIVE_JUDICIARY=false) really is offline.

# ---------------------------------------------------------------- builder ----
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build toolchain for packages without manylinux wheels (chromadb's hnswlib).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# CPU-only torch first -- see note above.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

# Paths are relative to the repo root -- see the context note in the runtime stage.
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# Pre-download both models into the image: all-MiniLM-L6-v2 builds and queries
# the index, ms-marco-MiniLM-L-6-v2 reranks the candidates.
#
# The reranker has to be baked for the same reason the embedder does, but it
# fails differently and worse. HF_HUB_OFFLINE=1 below means an absent model
# cannot be fetched at runtime, and `services/retrieval/reranker.py` fails soft
# by design -- so a container missing it would start, serve, and quietly return
# bi-encoder rankings, giving up the +0.043 recall@3 with nothing in the
# response to say so. An unbaked embedder at least fails loudly.
ENV HF_HOME=/opt/hf
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('all-MiniLM-L6-v2'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

# ---------------------------------------------------------------- runtime ----
FROM python:3.12-slim AS runtime

# curl is used by the compose healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/hf /opt/hf

ENV PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/opt/hf \
    # The model is already in the image. Without this, sentence-transformers
    # still revalidates every file against huggingface.co on each start --
    # ~20 HTTP round trips, and a hard failure if the host is offline or the
    # anonymous rate limit is hit.
    HF_HUB_OFFLINE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Anonymous telemetry is on by default in chromadb; a legal tool should not
    # phone home about query volume.
    ANONYMIZED_TELEMETRY=False \
    # Written to a named volume by compose. data_loader.py resolves the corpus
    # relative to the backend package, so the repo layout is preserved below.
    CHROMADB_PATH=/data/chroma_db

# The corpus lives at <repo>/data/processed and is resolved as
# backend/../data/processed, so both directories must keep their relative
# positions inside the image.
WORKDIR /app
COPY data/processed /app/data/processed
# data/curated is committed data too, and just as load-bearing: the legal graph
# refuses to build without doctrines.json, which takes the grounded answer path
# and every /offences response down with it. Copying only data/processed left a
# container that passed its health check and 500-ed on the first real question.
COPY data/curated /app/data/curated
COPY backend /app/backend

WORKDIR /app/backend

# Optionally bake the vector index into the image.
#
#   docker build --build-arg BAKE_INDEX=true ...
#
# Off by default, and the default is the interesting decision. Baking makes a
# first start instant instead of ~12 minutes, which matters for a deployment
# and is why this exists. But the layer invalidates whenever `services/` or
# `scripts/` changes, so every local rebuild during development would re-embed
# 9,896 chunks -- paying twelve minutes at build time to save twelve minutes at
# a start that happens once. CI builds pass the flag; `docker compose up
# --build` does not, and keeps the volume-seeding path it always had.
#
# The seed is written to /opt/chroma_seed rather than to CHROMADB_PATH: the
# latter is a mounted volume at run time, so anything written there during the
# build is masked the moment the volume appears. The entrypoint copies it
# across on a first start.
#
# The original argument against baking was that an index is derived data and
# baking it would re-run the whole embedding pass on any layer change. That was
# right when a seed took five minutes and `init_vector_db.py` rebuilt
# everything. It now reconciles against a manifest and rebuilds only what moved,
# so a baked index that is slightly stale is topped up rather than redone -- on
# the run that produced this, 1,624 chunks were reused and only the changed
# collection was rebuilt.
ARG BAKE_INDEX=false
RUN if [ "$BAKE_INDEX" = "true" ]; then \
        echo "Baking the vector index into the image (~12 minutes)..." && \
        CHROMADB_PATH=/opt/chroma_seed python scripts/init_vector_db.py && \
        du -sh /opt/chroma_seed; \
    else \
        echo "BAKE_INDEX not set; the store will be seeded into the volume on first start."; \
    fi

RUN chmod +x docker-entrypoint.sh \
    && useradd --create-home --uid 10001 lawai \
    && mkdir -p /data \
    && chown -R lawai:lawai /data /app \
    && if [ -d /opt/chroma_seed ]; then chown -R lawai:lawai /opt/chroma_seed; fi
USER lawai

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
