# Session Handoff: Marco Voice Avatar (Simli + RAG)

**Branch**: `main`
**Date**: January 28, 2026
**Status**: Deployed to Pipecat Cloud and responding in Daily rooms

## Current State

The agent is deployed and healthy. Daily sessions start and the bot responds with OpenAI + Cartesia + Simli video and RAG enabled.

### What Works

- Pipecat Cloud deployment via dailyco/pipecat-base
- Daily WebRTC sessions (Daily room auto-created by Cloud)
- Deepgram STT with smart endpointing
- OpenAI GPT-4o-mini LLM
- Cartesia TTS
- Simli video avatar (with `video_out_is_live=True`)
- RAG knowledge base (LanceDB + FastEmbed)
- SmartTurn + Silero VAD

### Recent Fixes

- Added `local-smart-turn-v3` extra + `torch` for SmartTurn
- Added `runner` extra + FastAPI/uvicorn dependencies
- Added `pipecatcloud` dependency required by base image `/app/app.py`
- Set WORKDIR to `/app` (base image expects `bot.py` in `/app`)
- Removed Docker CMD override (base image runs `bot.py`)
- Added ingestion fallback to avoid HF timeouts breaking builds
- Adjusted Deepgram endpointing to reduce response latency

## Deployment Configuration

**Region**: `us-east`  
**Secret set**: `marco`  
**Image**: `sleippnir/marco-voice-avatar:latest`

## Commands

```bash
# Build/push (WSL on Windows)
docker buildx build --platform linux/arm64 --build-arg BASE_IMAGE=dailyco/pipecat-base:latest -t sleippnir/marco-voice-avatar:latest --push .

# Deploy
pipecat cloud deploy --no-credentials --force

# Start session (Daily room)
pipecat cloud agent start marco-voice-avatar --use-daily --force

# Logs
pipecat cloud agent logs marco-voice-avatar
```

## RAG Configuration

RAG is enabled by default (`RAG_ENABLED=true`). The knowledge base is built at image build time from `knowledge/` using FastEmbed.

## Remaining Tuning

- Response latency: tighten Deepgram endpointing (currently 1200/1500ms)
- Optional: reduce Silero VAD `stop_secs` if further speed needed

## References

- https://docs.pipecat.ai/deployment/pipecat-cloud/fundamentals/agent-images
- https://docs.simli.com/
