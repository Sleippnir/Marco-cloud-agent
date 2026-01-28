# Lessons Learned (Jan 28, 2026)

## Deployment + Runtime

- Pipecat Cloud deploy config does not accept `env` or `health` keys in this CLI version.
- Secret sets are region-scoped; region must match the deployment region.
- Base image runs `/app/app.py` which imports `bot.py` from `/app` (do not set `WORKDIR /bot`).
- Do not override `CMD` when using `dailyco/pipecat-base` (it already runs `bot.py`).
- Current deployment: image `sleippnir/marco-voice-avatar:latest`, secret set `marco`, region `us-east`.

## Dependencies

- SmartTurn requires `pipecat-ai[local-smart-turn-v3]` and `torch`.
- Pipecat runner requires `pipecat-ai[runner]`, plus FastAPI/uvicorn.
- Base image expects `pipecatcloud` to be installed in the app environment.
- Using `uv` for dependency management (`uv sync --frozen`); lockfile is `uv.lock`.
- `requirements.txt` kept for legacy compatibility but `pyproject.toml` + `uv.lock` are authoritative.

## Build + Packaging

- Use WSL for Docker buildx on Windows.
- HuggingFace model downloads can timeout during ingestion; add a fallback to create an empty `knowledge_base` on failure.
- Docker build uses `uv sync --frozen --no-dev` for reproducible installs.

## LLM + Services

- Switched from Google Gemini to OpenAI GPT-4o-mini for better latency and reliability.
- RAG uses local FastEmbed embeddings (no API key required for embeddings).
- Deepgram STT with smart endpointing (1200ms endpointing, 1500ms utterance_end_ms).

## Pipecat Cloud API (Verified)

- API base: `https://api.pipecat.daily.co`
- Start session: `POST /v1/public/{agent_name}/start` with `Authorization: Bearer {API_KEY}`
- Request body: `{ "createDailyRoom": true }` returns `{ room_url, token, session_id }`
- Dashboard: `https://pipecat.daily.co`

## Common Failures and Fixes

- **Simli 401**: Invalid `SIMLI_API_KEY` in secret set.
- **Cartesia 401**: Invalid `CARTESIA_API_KEY`.
- **Deepgram 401**: Invalid `DEEPGRAM_API_KEY`.
- **OpenAI 401**: Invalid `OPENAI_API_KEY` in secret set.
- **Missing DAILY_ROOM_URL**: Caused by running local entrypoint in Cloud; rely on base image runner.
- **`/bot/app.py` not found**: Caused by `WORKDIR /bot`; use `/app`.
