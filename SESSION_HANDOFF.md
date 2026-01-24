# Session Handoff: Simli Troubleshooting

**Branch**: `simli-troubleshooting`
**Date**: January 24, 2026
**Status**: Deployment works, but Simli video has issues

## Current State

The voice agent deploys successfully to Pipecat Cloud and handles voice conversations. However, the Simli video avatar integration has reliability issues.

### What Works

- Pipecat Cloud deployment via Docker image
- Deepgram STT (speech-to-text)
- Google Gemini LLM (conversation)
- Cartesia TTS (text-to-speech)
- RAG knowledge base (LanceDB embedded at build time)
- Daily WebRTC transport
- Agent health checks pass
- Sessions start successfully

### What's Problematic

- **Simli video avatar**: Works "barely" - likely timing/initialization issues
- Simli WebSocket connection may timeout before first response
- Video may not appear or sync correctly with audio

## Key Files

| File | Purpose |
|------|---------|
| `bot.py` | Main agent - Pipecat Cloud entry point via `bot()` function |
| `Dockerfile` | Builds image with embedded LanceDB knowledge base |
| `pcc-deploy.toml` | Pipecat Cloud deployment configuration |
| `rag/retriever.py` | LanceDB vector search |
| `processors/rag_processor.py` | Injects RAG context into LLM prompts |

## Simli Integration Details

Located in `bot.py` lines 228-236:

```python
simli = SimliVideoService(
    api_key=config.simli_api_key,
    face_id=config.simli_face_id,
    params=SimliVideoService.InputParams(
        max_session_length=3600,  # 1 hour
        max_idle_time=300,        # 5 minutes
    ),
)
```

The agent waits up to 30s for Simli's WebSocket to be ready before sending greeting (lines 288-313).

## Platform Notes

**Windows**: No native wheels for `pipecat-ai[daily]`. Must run from WSL:
```bash
# In WSL terminal
cd /mnt/c/Projects/GitHub/Marco-cloud-agent
python bot.py
```

## Deployment Commands

```bash
# Build and push image (from WSL on Windows)
docker build -t sleippnir/marco-voice-avatar:latest .
docker push sleippnir/marco-voice-avatar:latest

# Deploy to Pipecat Cloud
pipecat cloud deploy --no-credentials --force

# Check status
pipecat cloud agent status marco-voice-avatar

# View logs
pipecat cloud agent logs marco-voice-avatar

# Start session
pipecat cloud agent start marco-voice-avatar
```

## Secrets Configuration

Secret set: `avatar-secrets` in Pipecat Cloud

Required secrets:
- `DAILY_API_KEY`
- `DEEPGRAM_API_KEY`
- `GOOGLE_API_KEY`
- `CARTESIA_API_KEY`
- `CARTESIA_VOICE_ID`
- `SIMLI_API_KEY`
- `SIMLI_FACE_ID`

## Next Steps to Investigate

1. **Simli WebSocket timing**: Check if the 30s wait is sufficient or if there's a race condition
2. **Simli client state**: The `_client.ready` check may not be the right indicator
3. **Video frame flow**: Verify TTS audio frames are reaching Simli correctly
4. **Simli logs**: Look for errors in Simli's WebSocket connection
5. **Consider Simli's `sync_audio` parameter**: May need adjustment for lip-sync

## References

- [Pipecat Simli integration](https://github.com/pipecat-ai/pipecat/tree/main/src/pipecat/services/simli)
- [Simli API docs](https://docs.simli.com/)
- [Pipecat Cloud docs](https://docs.pipecat.ai/cloud)
