# Session Handoff: Marco Voice Avatar (Simli + RAG)

**Branch**: `main`
**Date**: January 28, 2026
**Status**: Ready for deployment (verify with `pipecat cloud agent logs marco-voice-avatar`)

## Current State

The agent is configured for Pipecat Cloud deployment with OpenAI + Cartesia TTS + Simli video avatar and RAG knowledge base.

### What Works

- Pipecat Cloud deployment via `dailyco/pipecat-base`
- Daily WebRTC sessions (Daily room auto-created by Cloud)
- Deepgram STT with smart endpointing (1200ms/1500ms)
- OpenAI GPT-4o-mini LLM
- Cartesia TTS (sonic-3)
- Simli video avatar (with `video_out_is_live=True`)
- RAG knowledge base (LanceDB + FastEmbed, local embeddings)
- SmartTurn v3 + Silero VAD for intelligent turn-taking
- `end_call` function tool for user-initiated call termination

### Recent Fixes

- Switched from Google Gemini to OpenAI GPT-4o-mini
- Switched to `uv` for dependency management (`pyproject.toml` + `uv.lock`)
- Added `local-smart-turn-v3` extra + `torch` for SmartTurn
- Added `runner` extra + FastAPI/uvicorn dependencies
- Added `pipecatcloud` dependency required by base image `/app/app.py`
- Set WORKDIR to `/app` (base image expects `bot.py` in `/app`)
- Removed Docker CMD override (base image runs `bot.py`)
- Added ingestion fallback to avoid HF timeouts breaking builds
- Adjusted Deepgram endpointing to reduce response latency
- Aligned RAG defaults (threshold=0.5, min_query_length=8) across all config files

## Deployment Configuration

**Region**: `us-east`  
**Secret set**: `marco`  
**Image**: `sleippnir/marco-voice-avatar:latest`  
**Agent profile**: `agent-1x` (0.5 vCPU, 1GB RAM)

## Commands

```bash
# Local development
uv sync                        # Install dependencies
uv run python bot.py           # Run locally (requires DAILY_ROOM_URL in .env)

# Build/push (WSL on Windows)
docker buildx build --platform linux/arm64 --build-arg BASE_IMAGE=dailyco/pipecat-base:latest -t sleippnir/marco-voice-avatar:latest --push .

# Deploy to Pipecat Cloud
pipecat cloud deploy --no-credentials --force

# Start session (Daily room)
pipecat cloud agent start marco-voice-avatar --use-daily --force

# Check logs
pipecat cloud agent logs marco-voice-avatar
```

## RAG Configuration

RAG is enabled by default (`RAG_ENABLED=true`). The knowledge base is built at image build time from `knowledge/` using local FastEmbed embeddings (no API key needed).

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_ENABLED` | `true` | Enable RAG context injection |
| `RAG_MATCH_COUNT` | `3` | Number of chunks to retrieve |
| `RAG_MATCH_THRESHOLD` | `0.5` | Similarity threshold |
| `RAG_MIN_QUERY_LENGTH` | `8` | Min chars to trigger RAG |

## Remaining Tuning

- Response latency: current Deepgram endpointing is 1200/1500ms (tunable)
- Optional: reduce Silero VAD `stop_secs` (currently 0.2s) if further speed needed
- Consider `gpt-4o` instead of `gpt-4o-mini` for higher quality responses

## Next Steps

See **[INTEGRATION.md](./INTEGRATION.md)** for full v0 website integration guide (headshot → avatar click-to-chat).

## References

- https://docs.pipecat.ai/deployment/pipecat-cloud/fundamentals/agent-images
- https://docs.simli.com/
- https://docs.daily.co/reference/rest-api