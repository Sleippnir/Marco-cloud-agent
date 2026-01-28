# =============================================================================
# Personal Voice Avatar - Pipecat Cloud Dockerfile
# =============================================================================
# Builds a self-contained voice agent with embedded LanceDB knowledge base.
# The knowledge base is built at image build time for zero-latency RAG.
#
# For Pipecat Cloud: use dailyco/pipecat-base:latest
# For local testing: use python:3.12-slim
# =============================================================================

# Use pipecat-base for production, python:3.12-slim for local testing
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

# Install system dependencies (ffmpeg for audio processing, curl for uv install)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Use base image working directory
WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install Python dependencies with uv (frozen from lockfile)
RUN uv sync --frozen --no-dev

# Copy RAG module and processors
COPY rag/ ./rag/
COPY processors/ ./processors/
COPY prompts.py .

# Copy knowledge base source files
# Place your personal docs in knowledge/ directory before building
COPY knowledge/ ./knowledge/

# Copy ingestion script
COPY scripts/ingest_documents.py ./scripts/

# Build the LanceDB index at image build time
# This bakes your knowledge into the container for instant queries
# Note: fastembed runs locally, no API key needed for embeddings
RUN if [ -d "knowledge" ] && [ "$(ls -A knowledge 2>/dev/null)" ]; then \
        uv run python scripts/ingest_documents.py --dir knowledge/ --pattern "*.md" --output ./knowledge_base || (echo "Ingestion failed, creating empty knowledge_base"; mkdir -p ./knowledge_base); \
    else \
        echo "No knowledge files found, skipping index build"; \
        mkdir -p ./knowledge_base; \
    fi

# Copy main bot entry point
COPY bot.py .

# Environment defaults
ENV RAG_ENABLED=true
ENV RAG_MATCH_COUNT=3
ENV RAG_MATCH_THRESHOLD=0.5
ENV RAG_MIN_QUERY_LENGTH=8
ENV LANCEDB_PATH=./knowledge_base
ENV BOT_NAME="Marco"
ENV DEEPGRAM_MODEL=nova-3-general
ENV DEEPGRAM_LANGUAGE=en-US
ENV CARTESIA_MODEL=sonic-3
ENV OPENAI_MODEL=gpt-4o-mini
ENV LOG_LEVEL=INFO

# Labels
LABEL org.opencontainers.image.title="Marco Voice Avatar"
LABEL org.opencontainers.image.description="Personal voice avatar with embedded knowledge base"
LABEL org.opencontainers.image.version="1.0.0"
LABEL ai.pipecat.agent="true"

# Note: No CMD needed. Pipecat base image runs bot.py.
