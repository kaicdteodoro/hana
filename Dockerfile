# hana — Hands Are Not APIs
# Production container for the ingestion engine

FROM python:3.12-slim

LABEL maintainer="hana contributors"
LABEL description="Deterministic WordPress Catalog Ingestion Engine"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash hana

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY hana/ ./hana/

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Create directories for runtime data
RUN mkdir -p /app/.hana /data/catalog && \
    chown -R hana:hana /app /data

# Switch to non-root user
USER hana

# Default command
ENTRYPOINT ["hana"]
CMD ["--help"]
