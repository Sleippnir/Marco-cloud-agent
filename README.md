# Marco Voice Avatar

A personal voice avatar powered by Pipecat that speaks as you, with a local knowledge base about your projects and background.

## What It Does

- **Speaks as you** — Uses a custom prompt to emulate your personality
- **Knows about you** — RAG retrieves relevant info about your projects/background
- **Zero latency** — LanceDB embedded means instant knowledge retrieval
- **Pipecat Cloud ready** — Containerized for easy deployment

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            Frame Pipeline                                │
├─────────┬─────────┬─────────┬─────────┬─────────┬─────────┬─────────────┤
│  Daily  │Deepgram │   RAG   │ Context │ Google  │Cartesia │   Simli     │
│  Input  │   STT   │Processor│  Agg    │ Gemini  │   TTS   │   Avatar    │
│ (Audio) │         │         │         │   LLM   │         │  (Video)    │
└────┬────┴────┬────┴────┬────┴────┬────┴────┬────┴────┬────┴──────┬──────┘
     │         │         │         │         │         │           │
     │         │    ┌────┴────┐    │         │         │           │
     │         │    │ LanceDB │    │         │         │           │
     │         │    │(embedded│    │         │         │           │
     │         │    │ in img) │    │         │         │           │
     │         │    └─────────┘    │         │         │           │
     └─────────┴───────────────────┴─────────┴─────────┴───────────┘
```

## Quick Start

### 1. Add Your Knowledge

Create markdown files in `knowledge/`:

```markdown
# knowledge/about_me.md

# About Me
I'm Marco, a software engineer specializing in real-time voice AI...

# Projects
## Voice Avatar Project
Built a personal voice avatar using Pipecat and Simli...
```

### 2. Configure Environment

```bash
cp env.example .env
# Edit .env with your API keys
```

### 3. Build the Knowledge Base

```bash
# Install dependencies
pip install -e .

# Build LanceDB index
python scripts/ingest_documents.py --dir knowledge/ --pattern "*.md"
```

### 4. Run Locally

```bash
export DAILY_ROOM_URL=https://your-domain.daily.co/test-room
python bot.py
```

## Deploy to Pipecat Cloud

### 1. Create Secret Set

```bash
pip install pipecat-cloud
pipecat-cloud auth login
pipecat-cloud secrets create --name avatar-secrets
```

Add these secrets:
- `DAILY_API_KEY`
- `DEEPGRAM_API_KEY`
- `GOOGLE_API_KEY`
- `CARTESIA_API_KEY`, `CARTESIA_VOICE_ID`
- `SIMLI_API_KEY`, `SIMLI_FACE_ID`

### 2. Build Docker Image

```bash
# Build with knowledge base baked in
docker build \
  --build-arg GOOGLE_API_KEY=$GOOGLE_API_KEY \
  -t your-registry/marco-avatar:latest .

docker push your-registry/marco-avatar:latest
```

### 3. Deploy

Update `pcc-deploy.toml`:
```toml
image = "your-registry/marco-avatar:latest"
secret_set = "avatar-secrets"
```

```bash
pipecat-cloud deploy
```

## Project Structure

```
├── bot.py                  # Pipecat Cloud entry point
├── prompts.py              # Personal avatar prompts
├── processors/
│   └── rag_processor.py    # RAG context injection
├── rag/
│   ├── embeddings.py       # Google embeddings
│   └── retriever.py        # LanceDB retriever
├── knowledge/              # YOUR DOCS GO HERE
│   └── README.md           # Template
├── knowledge_base/         # Built LanceDB index (generated)
├── scripts/
│   └── ingest_documents.py # Build knowledge base
├── tests/
│   ├── test_rag_retriever.py
│   └── test_rag_processor.py
├── Dockerfile
├── pcc-deploy.toml
└── requirements.txt
```

## Customization

### Personality Prompts

Edit `prompts.py` or set `SYSTEM_INSTRUCTION` env var:

```python
from prompts import get_system_instruction

# Available: "default", "concise", "professional", "casual"
instruction = get_system_instruction("professional")
```

### RAG Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_ENABLED` | `true` | Enable/disable RAG |
| `RAG_MATCH_COUNT` | `3` | Documents to retrieve |
| `RAG_MATCH_THRESHOLD` | `0.5` | Similarity threshold |
| `RAG_MIN_QUERY_LENGTH` | `8` | Skip RAG for short utterances |

### Voice/Avatar

| Service | Variables |
|---------|-----------|
| Deepgram STT | `DEEPGRAM_MODEL`, `DEEPGRAM_LANGUAGE` |
| Cartesia TTS | `CARTESIA_VOICE_ID`, `CARTESIA_MODEL` |
| Simli Avatar | `SIMLI_FACE_ID` |

## Testing

```bash
# Install dev deps
pip install -e ".[dev]"

# Run tests
pytest -v
```

## How RAG Works

1. You speak → Deepgram transcribes
2. RAGContextProcessor queries LanceDB for relevant docs
3. Context is injected into the system prompt
4. Gemini generates a response "as you"
5. Cartesia speaks, Simli animates

Since LanceDB is embedded in the container, retrieval takes ~1-5ms vs 50-200ms for external databases.

## License

See LICENSE file.
