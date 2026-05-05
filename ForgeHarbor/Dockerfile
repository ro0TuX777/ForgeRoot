# ForgeHarbor Daemon Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY *.py ./
COPY tests/ ./tests/

# Create non-root user
RUN useradd --create-home --shell /bin/bash forgeharbor
USER forgeharbor

# Expose any ports if needed (none for now)

# Default command - can be overridden with env vars
CMD ["python", "-c", "from daemon import ForgeHarborDaemon; d = ForgeHarborDaemon(); d.start(); import time; time.sleep(3600)"]