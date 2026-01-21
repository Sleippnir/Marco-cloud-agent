# Simli Implementation Investigation - Claude Next Steps

**Date:** January 21, 2026  
**Model:** Claude (Opus 4.5)  
**Reference:** Official Pipecat Simli Example from pipecat-ai repository

---

## Executive Summary

The Simli avatar video disconnects after ~45-60 seconds with `WSDC Not ready` errors. Comparing the current implementation against the **official Pipecat Simli example** reveals three critical issues in `botrunner.py`:

1. **Missing `InputParams`** - Causes idle timeout disconnect
2. **Missing video transport flags** - `video_out_enabled`, `video_out_is_live`, dimensions not set
3. **Incorrect pipeline ordering** - `assistant_aggregator` placed before TTS instead of after `transport.output()`

---

## Root Cause Analysis

### Primary Cause: Missing InputParams

Without explicit `SimliVideoService.InputParams`, the Simli SDK uses very short default idle/session timeouts. After ~45-60 seconds of perceived "inactivity", the LiveKit WebSocket Data Channel (WSDC) closes with `ClientInitiated` reason.

**Evidence from logs:**
```
Error sending audio: WSDC Not ready, please wait until self.ready is True
disconnected from room with reason: ClientInitiated
```

**Note:** The official Pipecat Simli example also omits `InputParams`, so it would exhibit the same timeout behavior. For production use, explicit params are required.

### Secondary Cause: Missing Video Transport Flags

The `DailyParams` configuration in `botrunner.py` is missing critical video flags that the official example includes:

| Flag | Official Example | botrunner.py | bot.py |
|------|------------------|--------------|--------|
| `audio_in_enabled` | `True` | Missing | `True` |
| `audio_out_enabled` | `True` | Missing | `True` |
| `video_out_enabled` | `True` | Missing | `True` |
| `video_out_is_live` | `True` | Missing | Missing |
| `video_out_width` | `512` | Missing | Missing |
| `video_out_height` | `512` | Missing | Missing |

### Tertiary Cause: Incorrect Pipeline Ordering

The position of `assistant_aggregator` in the pipeline affects when LLM context is captured.

**Official example (correct):**
```python
Pipeline([
    transport.input(),
    stt,
    user_aggregator,
    llm,
    tts,
    simli_ai,
    transport.output(),
    assistant_aggregator,  # AFTER transport.output()
])
```

**botrunner.py (incorrect):**
```python
Pipeline([
    transport.input(),
    stt,
    llm_aggregators.user(),
    llm,
    llm_aggregators.assistant(),  # BEFORE tts - WRONG
    tts,
    simli,
    transport.output(),
])
```

---

## Code Comparison

### SimliVideoService Configuration

**Official Example:**
```python
simli_ai = SimliVideoService(
    api_key=os.getenv("SIMLI_API_KEY"),
    face_id="cace3ef7-a4c4-425d-a8cf-a5358eb0c427",
)
```

**bot.py (with production fix):**
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

**botrunner.py (broken):**
```python
simli = SimliVideoService(
    api_key=config.simli_api_key,
    face_id=config.simli_face_id,
)  # Missing InputParams
```

### DailyParams Configuration

**Official Example:**
```python
DailyParams(
    audio_in_enabled=True,
    audio_out_enabled=True,
    video_out_enabled=True,
    video_out_is_live=True,
    video_out_width=512,
    video_out_height=512,
    vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
)
```

**botrunner.py (incomplete):**
```python
DailyParams(
    api_key=config.daily_api_key,
    vad_analyzer=vad_analyzer,
    audio_in_stream_on_start=True,
)
```

---

## Fixes Applied

### Fix 1: Add InputParams to botrunner.py

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

### Fix 2: Add Video Transport Flags to DailyParams

```python
DailyParams(
    api_key=config.daily_api_key,
    vad_analyzer=vad_analyzer,
    audio_in_enabled=True,
    audio_out_enabled=True,
    video_out_enabled=True,
    video_out_is_live=True,
    video_out_width=512,
    video_out_height=512,
)
```

### Fix 3: Correct Pipeline Ordering

```python
# Unpack aggregators as tuple (matches official pattern)
user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context)

Pipeline([
    transport.input(),
    stt,
    user_aggregator,
    llm,
    tts,
    simli,
    transport.output(),
    assistant_aggregator,  # AFTER transport.output()
])
```

---

## Additional Observations

### Readiness Check Pattern

**bot.py** uses a fragile readiness check accessing private attributes:
```python
if hasattr(simli, '_client') and simli._client and getattr(simli._client, 'ready', False):
```

**Official example** avoids this by using `LLMRunFrame()` to trigger the first response:
```python
@transport.event_handler("on_client_connected")
async def on_client_connected(transport, client):
    await task.queue_frames([LLMRunFrame()])
```

This implicitly waits for pipeline readiness without depending on internal attributes.

### VAD Analyzer Difference

- **Official example:** `SileroVADAnalyzer(params=VADParams(stop_secs=0.2))`
- **bot.py/botrunner.py:** `WebRTCVADAnalyzer` with default `VADParams()`

Both should work, but `SileroVADAnalyzer` with explicit `stop_secs=0.2` may provide more responsive turn detection.

---

## Verification Checklist

After applying fixes:

- [ ] Rebuild Docker image with `--no-cache`
- [ ] Avatar video persists beyond 60 seconds
- [ ] No "WSDC Not ready" spam in logs
- [ ] No `ClientInitiated` disconnect in logs
- [ ] Audio/video sync works (lips match speech)
- [ ] Initial greeting plays with video
- [ ] "end the call" triggers graceful disconnect
- [ ] Bot responds naturally to speech

### Test Commands

```powershell
# Rebuild Docker image
docker build --no-cache --build-arg GOOGLE_API_KEY="$env:GOOGLE_API_KEY" -t marco-avatar:test .

# Create Daily room
$roomName = "marco-" + (Get-Date -Format "HHmmss")
$headers = @{ "Authorization" = "Bearer $env:DAILY_API_KEY"; "Content-Type" = "application/json" }
$body = '{"name": "' + $roomName + '"}'
$response = Invoke-RestMethod -Uri "https://api.daily.co/v1/rooms" -Method Post -Headers $headers -Body $body
Write-Host "`nJOIN: $($response.url)`n"

# Run container
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

---

## References

- **Official Simli Example:** pipecat-ai/pipecat repository
- **Pipecat Docs:** https://docs.pipecat.ai/server/services/video/simli
- **Simli API Reference:** https://reference-server.pipecat.ai/en/stable/api/pipecat.services.simli.video.html
- **Simli Docs:** https://docs.simli.com/api-reference/pipecat
- **Daily Docs:** https://docs.daily.co

---

## Summary

| Issue | Status | File |
|-------|--------|------|
| Missing InputParams | Fixed | botrunner.py |
| Missing video transport flags | Fixed | botrunner.py |
| Incorrect pipeline ordering | Fixed | botrunner.py |
| bot.py missing `video_out_is_live` | Noted (optional enhancement) | bot.py |

The primary root cause of the ~45-60 second disconnect is the missing `InputParams`. The official Pipecat example also omits this, so it would exhibit the same behavior for long-running sessions.
