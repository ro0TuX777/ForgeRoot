# Azul — Docker image
# ====================
# Multi-stage build. Base image is slim Python 3.11.
# All framework siblings (ForgeHarbor, ForgeScaffold, ForgeWorks, ForgeAtlas)
# are mounted as read-only volumes at runtime — Azul does not bundle them.
#
# Build:
#   docker build -t azul:latest .
#
# Run:
#   docker run -d \
#     -v /path/to/azul_data:/app/azul_data \
#     -v /path/to/ForgeHarbor:/frameworks/ForgeHarbor:ro \
#     -v /path/to/ForgeScaffold:/frameworks/ForgeScaffold:ro \
#     -v /path/to/ForgeScaffold/forgeworks:/frameworks/ForgeWorks:ro \
#     -v /path/to/ForgeAtlas:/frameworks/ForgeAtlas:ro \
#     -e AZUL_DATA_DIR=/app/azul_data \
#     -e FORGE_HARBOR_DAEMON_PATH=/frameworks/ForgeHarbor/daemon.py \
#     -e FORGE_SCAFFOLD_ROOT=/frameworks/ForgeScaffold \
#     -e FORGE_WORKS_SERVICE_WRAPPER_PATH=/frameworks/ForgeWorks/forgeworks/sam/service_wrapper.py \
#     -e FORGE_ATLAS_RUN_PATH=/frameworks/ForgeAtlas/action_discovery_service/run.py \
#     azul:latest

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="azul"
LABEL description="Azul — Agentic Change Verification System"
LABEL version="0.1.0"

# Non-root user for security
RUN useradd -m -u 1000 azul

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy Azul source
COPY azul/ ./azul/

# Data directory (mounted as volume in production)
RUN mkdir -p /app/azul_data/tickets/active \
             /app/azul_data/tickets/completed \
             /app/azul_data/verdicts \
             /app/azul_data/training_pairs \
             /app/azul_data/results \
             /app/azul_data/config/gate_policies \
             && chown -R azul:azul /app/azul_data

COPY azul_data/config/ ./azul_data/config/

# Drop to non-root
USER azul

# ── Environment defaults ─────────────────────────────────────────────────────
ENV AZUL_DATA_DIR=/app/azul_data
ENV AZUL_DEFAULT_MODE=shadow
ENV AZUL_DEFAULT_DOMAIN=ci_change_control
ENV AZUL_QUEUE_WORKERS=4
ENV AZUL_FORGE_HARBOR_ENABLED=true
ENV AZUL_FORGE_SCAFFOLD_ENABLED=true
ENV AZUL_FORGE_ATLAS_ENABLED=false
ENV AZUL_TELEMETRY_ENABLED=false
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Framework paths (overridden by volume mounts at runtime)
ENV FORGE_HARBOR_DAEMON_PATH=/frameworks/ForgeHarbor/daemon.py
ENV FORGE_SCAFFOLD_ROOT=/frameworks/ForgeScaffold
ENV FORGE_WORKS_SERVICE_WRAPPER_PATH=/frameworks/ForgeWorks/forgeworks/sam/service_wrapper.py
ENV FORGE_ATLAS_RUN_PATH=/frameworks/ForgeAtlas/action_discovery_service/run.py

# Unix socket for API access
ENV AZUL_SOCKET_PATH=/app/azul_data/azul.sock

VOLUME ["/app/azul_data"]

# Healthcheck via the daemon's /tmp health probe script
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Default: run as daemon
CMD ["python", "-m", "azul.daemon"]

EXPOSE 8765
