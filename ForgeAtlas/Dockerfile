# ForgeAtlas — ActionDiscovery Service
# Multi-stage build: deps stage caches pip install separately from code.
#
# Usage:
#   docker build -t action-discovery-service .
#   docker run -v /path/to/action_catalogs:/app/action_catalogs \
#              -v /path/to/DAWN:/app/DAWN \
#              action-discovery-service
#
# Environment variables (all have defaults):
#   DAWN_ROOT                          — path to the DAWN package root (default /app/DAWN)
#   FORGE_ATLAS_CATALOG_PATH           — path to action_catalogs/ dir (default /app/action_catalogs)
#   FORGE_ATLAS_DEFAULT_MAX_RESULTS    — max results per query (default 10)
#   FORGE_ATLAS_EMBEDDING_MODEL        — sentence-transformers model (default all-MiniLM-L6-v2)
#   ACTION_DISCOVERY_SIMILARITY_THRESHOLD — cosine similarity floor (default 0.3)

# ── Stage 1: deps ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS deps

WORKDIR /install

COPY requirements.txt .

# Install CPU-only torch to avoid pulling in CUDA (saves ~3GB).
RUN pip install --no-cache-dir \
        torch==2.7.1 \
        --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model into the image so the container starts
# without network access.  Remove this RUN step to pull at startup instead.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy installed packages from deps stage.
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy HuggingFace model cache from deps stage.
COPY --from=deps /root/.cache /root/.cache

# Copy service code.
COPY action_discovery_service/ /app/action_discovery_service/

# DAWN is mounted at runtime (see docker run -v).
# The DAWN_ROOT env var tells run.py where to find it.
ENV DAWN_ROOT=/app/DAWN

# Catalog is a mounted volume — not baked into the image.
# FORGE_ATLAS_CATALOG_PATH tells the service where to find it.
ENV FORGE_ATLAS_CATALOG_PATH=/app/action_catalogs

# Suppress progress bars and verbose library output in container logs.
ENV TQDM_DISABLE=1
ENV TOKENIZERS_PARALLELISM=false
ENV TRANSFORMERS_VERBOSITY=error

# Default model and search settings.
ENV FORGE_ATLAS_EMBEDDING_MODEL=all-MiniLM-L6-v2
ENV ACTION_DISCOVERY_SIMILARITY_THRESHOLD=0.3
ENV FORGE_ATLAS_DEFAULT_MAX_RESULTS=10

# Health-check: run the startup sequence and exit with correct code.
HEALTHCHECK --interval=30s --timeout=30s --start-period=60s --retries=3 \
    CMD python -m action_discovery_service || exit 1

# Default command: run the startup sequence (logs summary, exits 0 if healthy).
CMD ["python", "-m", "action_discovery_service"]
