# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A real-time voice avatar agent built on the **Pipecat** framework, deployed to **Pipecat Cloud**. It answers questions *as Marco* (first-person persona) over a Daily WebRTC call, with a Simli lip-synced video avatar and a local RAG knowledge base. `bot.py` is the single production entry point; everything else supports it.

Pipecat's API moves fast. When writing or changing pipeline/processor/transport code, verify current class/method signatures against the installed `pipecat-ai` package (introspection or type stubs) rather than assuming — the `.cursorrules` file elaborates on this expectation.

## Commands

Dependency management is **uv** (`pyproject.toml` + `uv.lock` are authoritative; `requirements.txt` is legacy-only, kept in sync manually).

```bash
uv sync                        # Install deps from lockfile
uv sync --frozen --no-dev      # Reproducible prod install (matches Dockerfile)
uv run python bot.py           # Run locally — requires DAILY_ROOM_URL (+ optional DAILY_TOKEN) in .env

# Build the LanceDB index from knowledge/ (also runs at Docker build time)
uv run python scripts/ingest_documents.py --dir knowledge/ --pattern "*.md" --output ./knowledge_base
# Same script is exposed as a console entry point:
uv run ingest --dir knowledge/ --output ./knowledge_base

# Dev tooling (dev extra)
uv run pytest                  # pytest + pytest-asyncio are configured; note: no tests exist yet
uv run ruff check .
uv run mypy .
```

### Build & deploy (Pipecat Cloud)

Docker build must target `linux/arm64` with the Pipecat base image. On Windows this requires WSL.

```bash
docker buildx build --platform linux/arm64 \
  --build-arg BASE_IMAGE=dailyco/pipecat-base:latest \
  -t sleippnir/marco-voice-avatar:latest --push .

pipecat cloud deploy --no-credentials --force
pipecat cloud agent start marco-voice-avatar --use-daily --force
pipecat cloud agent logs marco-voice-avatar
```

The Dockerfile's `BASE_IMAGE` arg defaults to `python:3.12-slim` (for local test builds); production **must** pass `dailyco/pipecat-base:latest`. The base image auto-runs `bot.py` from `/app` — do **not** add a `CMD` or change `WORKDIR`.

## Architecture

### Runtime frame flow
```
audio in → SileroVAD → Deepgram STT → [RAGContextProcessor] → user aggregator
         → OpenAI LLM → Cartesia TTS → Simli video → transport out → assistant aggregator
```
The processor list is assembled conditionally in `bot.py::main()` (RAG and Simli stages are only inserted when enabled/available). Turn-taking uses **SmartTurn v3** (`LocalSmartTurnAnalyzerV3`, wired into the user aggregator's stop strategy) for intelligent end-of-turn detection, with Silero VAD only for raw speech detection — not silence-based turn ending. `video_out_is_live=True` on `DailyParams` is **required** for Simli output.

### Entry points (`bot.py`)
- `bot(args: DailySessionArguments)` — the Pipecat Cloud entry point. Cloud injects `room_url`/`token`. There's an `ImportError` fallback stub for `DailySessionArguments` so the module imports without the `pipecat-cloud` package locally.
- `run_local()` / `__main__` — local dev path; reads room creds from env.
- Config is centralized in the frozen `BotConfig` dataclass, built by `load_config()` from env vars. `_require_env()` hard-fails on missing required keys.
- An `end_call` LLM function tool lets the user end the call by voice; its handler speaks a goodbye then pushes `EndTaskFrame` upstream.

### RAG subsystem
- **`rag/embeddings.py`** — `LocalEmbeddings`: FastEmbed with `BAAI/bge-small-en-v1.5` (384-dim), fully local, no API key.
- **`rag/retriever.py`** — `LanceDBRetriever`: embedded LanceDB vector search over `./knowledge_base` (`LANCEDB_PATH`). Converts LanceDB's L2 `_distance` to a `1/(1+distance)` similarity and filters by threshold. `retrieve()` is an async wrapper over the sync path (LanceDB is sync but fast).
- **`processors/rag_processor.py`** — `RAGContextProcessor`: a Pipecat `FrameProcessor` that watches `TranscriptionFrame`s, retrieves matching docs, and injects the formatted context into the system prompt of the next `LLMMessagesFrame` (default `AUGMENT_SYSTEM` strategy; alternative `INJECT_CONTEXT`).
- **`scripts/ingest_documents.py`** — reads `knowledge/*.md`, chunks on paragraph boundaries (~2000 chars), embeds, and writes the LanceDB table. Run at Docker build time so the index is baked into the image for zero-latency queries.

The knowledge base is **build-time static**: to change what the avatar knows, edit `knowledge/*.md` and rebuild the image (or re-run ingestion locally).

### Debug / reference scripts (not deployed)
- `simliexample.py` — upstream Daily/Pipecat Simli reference.
- `simli_debug_bot.py` — a copy of the above for local Simli A/B troubleshooting.

## Gotchas & known constraints

- **`prompts.py` is not currently wired into `bot.py`.** The runtime system instruction comes from `SYSTEM_INSTRUCTION` env var or an inline default in `load_config()`, *not* from `prompts.py::PERSONAL_AVATAR_PROMPT`. If you intend the persona in `prompts.py` (default/concise/professional/casual) to take effect, you must connect `get_system_instruction()` into the config path.
- **Windows**: `pipecat-ai[daily]` has no Windows wheels — run everything (local dev and Docker) from WSL.
- **Deploy config is minimal on purpose.** `pcc-deploy.toml` does not accept `env` or `health` keys in the current CLI version. Secret sets are **region-scoped** — the `secret_set` (`marco`) and `region` (`us-east`) must match.
- **Ingestion resilience**: HuggingFace model downloads (for FastEmbed) can time out during Docker build. The Dockerfile falls back to creating an empty `knowledge_base` so a failed ingest doesn't break the build; the retriever degrades gracefully (logs a warning, runs without RAG) when the table is missing.
- Config defaults for RAG (`RAG_MATCH_THRESHOLD=0.5`, `RAG_MIN_QUERY_LENGTH=8`) are duplicated across `bot.py`, the `Dockerfile`, and docs — keep them aligned if you change one.
- LLM is **OpenAI GPT-4o-mini** (switched from Gemini for latency/reliability). Deepgram uses smart endpointing (`endpointing=1200`, `utterance_end_ms=1500`) — the main lever for response-latency tuning.

## Further reading

`README.md` (setup + env var table), `SESSION_HANDOFF.md` (deployment state & tuning notes), `LESSONS_LEARNED.md` (failure modes and verified Pipecat Cloud API details), `INTEGRATION.md` (website click-to-chat integration), and `env.example` (full env var list).
