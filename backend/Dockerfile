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

# Pre-download all-MiniLM-L6-v2 into the image.
ENV HF_HOME=/opt/hf
RUN python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2')"

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
COPY backend /app/backend

WORKDIR /app/backend

RUN chmod +x docker-entrypoint.sh \
    && useradd --create-home --uid 10001 lawai \
    && mkdir -p /data \
    && chown -R lawai:lawai /data /app
USER lawai

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
