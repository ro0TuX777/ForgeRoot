FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Expect build context at repo root so both forgeworks and forgegate are available.
COPY forgeworks /app/forgeworks
COPY forgegate /app/forgegate

RUN pip install --no-cache-dir -e /app/forgegate
RUN pip install --no-cache-dir -e /app/forgeworks

RUN chmod +x /app/forgeworks/docker/entrypoint.sh /app/forgeworks/scripts/run_pack.sh /app/forgeworks/scripts/run_demo.sh || true

WORKDIR /app/forgeworks
ENTRYPOINT ["/app/forgeworks/docker/entrypoint.sh"]
CMD ["forgeworks", "--help"]
