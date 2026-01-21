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

# Install system dependencies (ffmpeg for audio processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /bot

# Install Python dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

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
ARG GOOGLE_API_KEY
ENV GOOGLE_API_KEY=${GOOGLE_API_KEY}
RUN if [ -d "knowledge" ] && [ "$(ls -A knowledge 2>/dev/null)" ]; then \
        python scripts/ingest_documents.py --dir knowledge/ --pattern "*.md" --output ./knowledge_base; \
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
ENV GOOGLE_MODEL=gemini-2.5-flash
ENV LOG_LEVEL=INFO

# Labels
LABEL org.opencontainers.image.title="Marco Voice Avatar"
LABEL org.opencontainers.image.description="Personal voice avatar with embedded knowledge base"
LABEL org.opencontainers.image.version="1.0.0"
LABEL ai.pipecat.agent="true"

# For local testing (pipecat-base handles this in production)
CMD ["python", "bot.py"]
