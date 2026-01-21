# Simli Service Debug Investigation - Claude

**Date:** January 21, 2026  
**Model:** Claude (Opus 4.5)  
**Pipecat Version:** 0.0.99  
**Simli SDK Version:** 1.0.3

---

## Summary of Findings

The Simli avatar video disconnects after ~45-60 seconds with `WSDC Not ready` errors. The root cause is **missing session timeout configuration** in the SimliVideoService initialization.

---

## Root Cause Analysis

### Primary Issue: Missing InputParams Configuration

The `SimliVideoService` API changed in Pipecat v0.0.92+:

**Old API (worked):**

```python
SimliConfig(api_key=..., face_id=...)  # Had proper default timeouts
```

**New API (broken without params):**

```python
SimliVideoService(api_key=..., face_id=...)  # Short/no default timeouts
```

Without explicit `InputParams`, the Simli SDK uses very short idle timeouts causing the LiveKit WebSocket Data Channel (WSDC) to disconnect prematurely.

**Evidence from logs:**

- `Error sending audio: WSDC Not ready, please wait until self.ready is True`
- `disconnected from room with reason: ClientInitiated` at ~45-69 seconds

### Technical Explanation

The Simli service uses LiveKit's WebSocket Data Channel (WSDC) for real-time communication. When `InputParams` is not provided:

1. The SDK falls back to internal default timeouts (likely very short values)
2. After ~45-60 seconds of perceived "inactivity" (even during active conversation), the WSDC closes
3. The disconnect reason `ClientInitiated` indicates the Simli SDK itself is terminating the connection
4. Subsequent audio send attempts fail with "WSDC Not ready" because the channel is closed

---

## The Fix Applied (Commit 539b342)

```python
# bot.py lines 229-236
simli = SimliVideoService(
    api_key=config.simli_api_key,
    face_id=config.simli_face_id,
    params=SimliVideoService.InputParams(
        max_session_length=3600,  # 1 hour
        max_idle_time=300,        # 5 minutes
    ),
)
```

Per [Simli docs](https://docs.simli.com), these match the expected defaults:

- `max_session_length`: 3600 seconds (1 hour) - absolute maximum session duration
- `max_idle_time`: 300 seconds (5 minutes) - disconnect after 5 minutes of silence

**Note:** The Pipecat SDK internally adds a 5-second buffer to both values.

---

## Additional Concerns Identified

### 1. `botrunner.py` Not Updated

The `botrunner.py` file (lines 107-110) still lacks the `InputParams` fix:

```python
simli = SimliVideoService(
    api_key=config.simli_api_key,
    face_id=config.simli_face_id,
)  # MISSING: InputParams
```

**Impact:** This file will exhibit the same disconnect behavior if used for local development or testing.

**Recommendation:** Add the same `InputParams` configuration to `botrunner.py`.

### 2. Fragile Simli Readiness Check

The code in `bot.py` lines 289-306 accesses internal/private attributes:

```python
if hasattr(simli, '_client') and simli._client and getattr(simli._client, 'ready', False):
    simli_ready = True
```

**Concerns:**

- `_client` is a private implementation detail (underscore prefix convention)
- May break silently with Simli SDK or Pipecat updates
- No official public API for readiness checking was found in documentation

**Recommendation:** Monitor for SDK updates and consider requesting a public readiness API from Pipecat/Simli.

### 3. Race Condition Risk

The 30-second max wait for Simli readiness may be insufficient under network latency:

```python
max_wait = 30  # seconds
waited = 0.0
# ... polling loop ...
if not simli_ready:
    logger.warning(f"Simli not ready after {max_wait}s timeout, skipping video greeting")
    await task.queue_frames([TextFrame("Hey there!")])  # Still sends audio
```

**Impact:** Users may receive audio-only greetings when video should be expected.

**Recommendation:** Consider increasing the timeout or implementing a retry mechanism.

### 4. Version Dependencies

| Component  | Version | Notes                              |
|------------|---------|-------------------------------------|
| pipecat-ai | 0.0.99  | Uses new SimliVideoService API     |
| simli-ai   | 1.0.3   | Underlying SDK with LiveKit/WSDC   |
| livekit    | (dep)   | Provides WebSocket Data Channel    |

The `simli-ai` SDK depends on `livekit` for the WebSocket Data Channel. Any incompatibility between these packages could cause connection issues.

---

## Debug History (from SESSION_HANDOFF.md)

The Simli issue went through several debug iterations:

1. **Initial hypothesis:** `sync_audio` parameter issue - *incorrect*
2. **Second attempt:** Reverting `DailyParams` to match old working bot - *did not resolve*
3. **Root cause discovery:** Missing `InputParams` with session timeouts - *correct*
4. **Key evidence:** `disconnected from room with reason: ClientInitiated` at ~45-69 seconds

---

## Verification Steps (Not Yet Completed)

The fix has been committed but **not tested**. Test procedure:

### 1. Rebuild Docker Image

```powershell
docker build --no-cache --build-arg GOOGLE_API_KEY="$env:GOOGLE_API_KEY" -t marco-avatar:test .
```

### 2. Create Daily Room and Run Container

```powershell
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

### 3. Verification Checklist

- [ ] Avatar video persists beyond 60 seconds
- [ ] Audio/video sync works (lips match speech)
- [ ] Bot responds naturally to speech
- [ ] "end the call" function triggers graceful disconnect
- [ ] Initial greeting plays with video

---

## Recommendations

1. **Test the fix** - Run the Docker test procedure above
2. **Update botrunner.py** - Add the same `InputParams` configuration for consistency
3. **Add logging for Simli state** - Log when `max_idle_time` is about to trigger
4. **Consider a startup health check** - Fail fast if Simli doesn't become ready within timeout
5. **Document the timeout behavior** - Users should know about the 5-minute idle disconnect

---

## References

- Pipecat Docs: https://reference-server.pipecat.ai
- Simli Docs: https://docs.simli.com
- Daily Docs: https://docs.daily.co
- Pipecat SimliVideoService API: https://reference-server.pipecat.ai/en/stable/api/pipecat.services.simli.video.html
