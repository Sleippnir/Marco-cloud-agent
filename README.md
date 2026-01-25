# Marco Voice Avatar

A real-time voice agent with video avatar powered by Pipecat, deployable to Pipecat Cloud.

## Features

- **Voice Conversation**: Deepgram STT + Cartesia TTS for natural speech
- **AI Brain**: Google Gemini 2.5 Flash for fast, intelligent responses
- **Video Avatar**: Simli lip-synced video avatar
- **RAG Knowledge Base**: LanceDB-embedded retrieval for grounded answers
- **Pipecat Cloud Ready**: One-command deployment with auto-scaling

## Architecture

```
Audio In → VAD → Deepgram STT → [RAG Context] → Gemini LLM → Cartesia TTS → Simli Video → Out
```

## Quick Start

### Prerequisites

- Python 3.12+
- API keys for: Daily, Deepgram, Google AI, Cartesia, Simli
- Docker (for deployment)

### Platform Requirements

| Platform | Local Dev | Docker Build |
|----------|-----------|--------------|
| **Linux** | Native | Native |
| **macOS** | Native | Native |
| **Windows** | WSL only | WSL Docker |

> **Windows users**: The `pipecat-ai[daily]` package has no Windows wheels. You must run from WSL (Windows Subsystem for Linux). Install dependencies and run `python bot.py` inside your WSL environment.

### Local Development

1. Clone and install dependencies:
   ```bash
   git clone https://github.com/Sleippnir/Marco-cloud-agent.git
   cd Marco-cloud-agent
   pip install -r requirements.txt
   ```

2. Create `.env` file (see `env.example`):
   ```bash
   cp env.example .env
   # Edit .env with your API keys
   ```

3. Run locally:
   ```bash
   python bot.py
   ```

### Pipecat Cloud Deployment

1. Build and push Docker image:
   ```bash
   docker build -t your-registry/marco-avatar:latest .
   docker push your-registry/marco-avatar:latest
   ```

2. Create secrets in Pipecat Cloud:
   ```bash
   pipecat cloud secrets set avatar-secrets \
     DAILY_API_KEY=xxx \
     DEEPGRAM_API_KEY=xxx \
     GOOGLE_API_KEY=xxx \
     CARTESIA_API_KEY=xxx \
     CARTESIA_VOICE_ID=xxx \
     SIMLI_API_KEY=xxx \
     SIMLI_FACE_ID=xxx
   ```

3. Update `pcc-deploy.toml` with your image registry

4. Deploy:
   ```bash
   pipecat cloud deploy
   ```

5. Start a session:
   ```bash
   pipecat cloud agent start marco-voice-avatar
   ```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DAILY_API_KEY` | Yes | - | Daily.co API key |
| `DEEPGRAM_API_KEY` | Yes | - | Deepgram STT API key |
| `GOOGLE_API_KEY` | Yes | - | Google AI API key |
| `CARTESIA_API_KEY` | Yes | - | Cartesia TTS API key |
| `CARTESIA_VOICE_ID` | Yes | - | Cartesia voice ID |
| `SIMLI_API_KEY` | Yes | - | Simli API key |
| `SIMLI_FACE_ID` | Yes | - | Simli face/avatar ID |
| `RAG_ENABLED` | No | `true` | Enable RAG context injection |
| `BOT_NAME` | No | `Marco` | Bot display name |
| `GOOGLE_MODEL` | No | `gemini-2.5-flash` | Google model to use |

### RAG Knowledge Base

Place markdown files in `knowledge/` directory before building the Docker image. The knowledge base is indexed at build time for zero-latency queries.

```bash
# Add your documents
cp your-docs/*.md knowledge/

# Rebuild with knowledge
docker build -t your-registry/marco-avatar:latest .
```

## Project Structure

```
├── bot.py              # Main Pipecat agent (cloud entry point)
├── simli_debug_bot.py  # Debug bot for Simli testing
├── Dockerfile          # Container build with embedded RAG
├── pcc-deploy.toml     # Pipecat Cloud deployment config
├── requirements.txt    # Python dependencies
├── rag/                # RAG retrieval module
│   ├── embeddings.py   # Local embeddings (fastembed)
│   └── retriever.py    # LanceDB vector search
├── processors/         # Custom frame processors
│   └── rag_processor.py
├── knowledge/          # Source documents for RAG
└── scripts/
    └── ingest_documents.py  # Build LanceDB index
```

## Known Issues

- Simli video avatar initialization can be slow (~30s warmup)
- First response may be delayed while Simli WebSocket connects

## License

MIT
