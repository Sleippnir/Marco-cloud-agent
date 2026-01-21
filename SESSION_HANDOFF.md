# Session Handoff - January 21, 2026

## Current State

The project is a **Pipecat-based voice agent** with RAG capabilities, designed to deploy to Pipecat Cloud. The bot uses:
- **Daily Transport** for WebRTC audio/video
- **Simli** for avatar video generation
- **Deepgram** for STT
- **Cartesia** for TTS
- **Google Gemini** for LLM
- **LanceDB** (embedded) for local RAG knowledge base

## Latest Fix (Just Committed)

**Commit:** `539b342` - "Fix Simli WSDC timeout: add InputParams with max_session_length and max_idle_time"

### The Problem
The Simli avatar video was disconnecting after ~45-60 seconds with repeated errors:
```
Error sending audio: WSDC Not ready, please wait until self.ready is True
```

Logs showed: `disconnected from room with reason: ClientInitiated` - meaning the Simli SDK was terminating the LiveKit WebSocket Data Channel prematurely due to short default timeout values.

### The Fix
Added `SimliVideoService.InputParams` to `bot.py` (lines 229-237):

```python
simli = SimliVideoService(
    api_key=config.simli_api_key,
    face_id=config.simli_face_id,
    params=SimliVideoService.InputParams(
        max_session_length=3600,  # 1 hour
        max_idle_time=300,        # 5 minutes (matches old SimliConfig default)
    ),
)
```

### Why This Should Work
- The user's old working bot used `SimliConfig(api_key, face_id)` which had proper defaults
- The new Pipecat API (v0.0.92+) deprecated `simli_config` in favor of `api_key`, `face_id`, and `params`
- Without explicit `InputParams`, the SDK uses very short idle timeouts causing disconnect
- Sources: reference-server.pipecat.ai, docs.simli.com (Jan 2026)

## Immediate Next Step: TEST THE FIX

The Docker image needs to be rebuilt and tested:

```powershell
# Rebuild with no-cache to ensure changes are picked up
docker build --no-cache --build-arg GOOGLE_API_KEY="$env:GOOGLE_API_KEY" -t marco-avatar:test .

# Create room and run container
$roomName = "marco-" + (Get-Date -Format "HHmmss")
$headers = @{ "Authorization" = "Bearer $env:DAILY_API_KEY"; "Content-Type" = "application/json" }
$body = '{"name": "' + $roomName + '"}'
$response = Invoke-RestMethod -Uri "https://api.daily.co/v1/rooms" -Method Post -Headers $headers -Body $body
Write-Host "`nJOIN: $($response.url)`n"

docker run `
  -e DAILY_ROOM_URL="$($response.url)" `
  -e DAILY_API_KEY="$env:DAILY_API_KEY" `
  -e SIMLI_API_KEY="$env:SIMLI_API_KEY" `
  -e SIMLI_FACE_ID="$env:SIMLI_FACE_ID" `
  -e DEEPGRAM_API_KEY="$env:DEEPGRAM_API_KEY" `
  -e CARTESIA_API_KEY="$env:CARTESIA_API_KEY" `
  -e CARTESIA_VOICE_ID="$env:CARTESIA_VOICE_ID" `
  -e GOOGLE_API_KEY="$env:GOOGLE_API_KEY" `
  -e BOT_NAME="Marco" `
  marco-avatar:test
```

> **Note:** Load your API keys from your local `.env` file or set them as environment variables before running.

## What to Verify During Testing

1. **Avatar video persists** - Should NOT disconnect after ~1 minute
2. **Audio/video sync** - Lips should match speech
3. **Bot responsiveness** - Should respond naturally to speech
4. **End call function** - Saying "end the call" should trigger graceful disconnect
5. **Initial greeting** - Bot should greet when user joins

## Key Files

| File | Purpose |
|------|---------|
| `bot.py` | Main Pipecat Cloud entry point with pipeline setup |
| `rag/retriever.py` | LanceDB-based semantic search |
| `rag/embeddings.py` | Google text-embedding-004 wrapper |
| `processors/rag_processor.py` | RAGContextProcessor for augmenting LLM context |
| `Dockerfile` | Container definition with LanceDB index build |
| `knowledge/` | Markdown files for RAG knowledge base |

## Environment Variables Required

See `env.example` for the full list. Keys are stored locally in `.env` (gitignored).

Required services:
- **Daily** - WebRTC transport (API key + room URL)
- **Simli** - Avatar video (API key + face ID)
- **Deepgram** - STT (API key)
- **Cartesia** - TTS (API key + voice ID)
- **Google** - LLM + embeddings (API key)

## Remaining TODOs

- [x] Add SimliVideoService.InputParams with max_session_length and max_idle_time
- [ ] Rebuild Docker image and test Simli video stability
- [ ] If working, deploy to Pipecat Cloud

## Technical Context

### Pipecat Version
Running **Pipecat 0.0.99** (per container logs)

### Pipeline Architecture
```
audio in → VAD → STT → [RAG context injection] → LLM → TTS → Simli → audio/video out
```

### Known Deprecation Warnings (Safe to Ignore)
- `OpenAILLMContext` deprecated - should migrate to universal `LLMContext`
- `EmulateUserStartedSpeakingFrame` deprecated
- These don't affect functionality currently

## Previous Session Debug History

The Simli issue went through several debug iterations:
1. Initially thought it was `sync_audio` parameter issue
2. Tried reverting `DailyParams` to match old working bot
3. Discovered the actual cause: missing `InputParams` with session timeouts
4. Key log evidence: `disconnected from room with reason: ClientInitiated` at ~45-69 seconds

## Contact / References

- Pipecat Docs: https://reference-server.pipecat.ai
- Simli Docs: https://docs.simli.com
- Daily Docs: https://docs.daily.co
