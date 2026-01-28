# Lessons Learned (Jan 28, 2026)

## Deployment + Runtime

- Pipecat Cloud deploy config does not accept `env` or `health` keys in this CLI version.
- Secret sets are region-scoped; region must match the deployment region.
- Base image runs `/app/app.py` which imports `bot.py` from `/app` (do not set `WORKDIR /bot`).
- Do not override `CMD` when using `dailyco/pipecat-base` (it already runs `bot.py`).

## Dependencies

- SmartTurn requires `pipecat-ai[local-smart-turn-v3]` and `torch`.
- Pipecat runner requires `pipecat-ai[runner]`, plus FastAPI/uvicorn.
- Base image expects `pipecatcloud` to be installed in the app environment.

## Build + Packaging

- Use WSL for Docker buildx on Windows.
- HuggingFace model downloads can timeout during ingestion; add a fallback to create an empty `knowledge_base` on failure.

## Common Failures and Fixes

- **Simli 401**: Invalid `SIMLI_API_KEY` in secret set.
- **Cartesia 401**: Invalid `CARTESIA_API_KEY`.
- **Deepgram 401**: Invalid `DEEPGRAM_API_KEY`.
- **Missing DAILY_ROOM_URL**: Caused by running local entrypoint in Cloud; rely on base image runner.
- **`/bot/app.py` not found**: Caused by `WORKDIR /bot`; use `/app`.
