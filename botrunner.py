import asyncio
import os
import sys
from dataclasses import dataclass

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from deepgram import LiveOptions  # type: ignore[import-not-found]

from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.simli.video import SimliVideoService
from pipecat.transports.daily.transport import DailyParams, DailyTransport, WebRTCVADAnalyzer
from pipecat.transcriptions.language import Language


@dataclass(frozen=True)
class BotConfig:
    daily_api_key: str
    daily_room_url: str
    daily_token: str | None
    simli_api_key: str
    simli_face_id: str
    deepgram_api_key: str
    deepgram_model: str
    deepgram_language: Language
    cartesia_api_key: str
    cartesia_voice_id: str
    cartesia_model: str
    google_api_key: str
    google_model: str
    system_instruction: str
    bot_name: str


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_config() -> BotConfig:
    return BotConfig(
        daily_api_key=_require_env("DAILY_API_KEY"),
        daily_room_url=_require_env("DAILY_ROOM_URL"),
        daily_token=os.getenv("DAILY_TOKEN"),
        simli_api_key=_require_env("SIMLI_API_KEY"),
        simli_face_id=_require_env("SIMLI_FACE_ID"),
        deepgram_api_key=_require_env("DEEPGRAM_API_KEY"),
        deepgram_model=os.getenv("DEEPGRAM_MODEL", "nova-3-general"),
        deepgram_language=Language(os.getenv("DEEPGRAM_LANGUAGE", "en-US")),
        cartesia_api_key=_require_env("CARTESIA_API_KEY"),
        cartesia_voice_id=_require_env("CARTESIA_VOICE_ID"),
        cartesia_model=os.getenv("CARTESIA_MODEL", "sonic-3"),
        google_api_key=_require_env("GOOGLE_API_KEY"),
        google_model=os.getenv("GOOGLE_MODEL", "gemini-2.5-flash"),
        system_instruction=os.getenv(
            "SYSTEM_INSTRUCTION",
            "You are a concise, friendly voice assistant. Keep responses short.",
        ),
        bot_name=os.getenv("BOT_NAME", "Pipecat Bot"),
    )


def build_pipeline(config: BotConfig) -> Pipeline:
    vad_analyzer = WebRTCVADAnalyzer(
        sample_rate=16000,
        params=VADParams(),
    )
    transport = DailyTransport(
        room_url=config.daily_room_url,
        token=config.daily_token,
        bot_name=config.bot_name,
        params=DailyParams(
            api_key=config.daily_api_key,
            vad_analyzer=vad_analyzer,
            audio_in_enabled=True,
            audio_out_enabled=True,
            video_out_enabled=True,
            video_out_is_live=True,
            video_out_width=512,
            video_out_height=512,
        ),
    )

    stt = DeepgramSTTService(
        api_key=config.deepgram_api_key,
        live_options=LiveOptions(
            model=config.deepgram_model,
            language=config.deepgram_language,
        ),
    )

    llm = GoogleLLMService(
        api_key=config.google_api_key,
        model=config.google_model,
        system_instruction=config.system_instruction,
    )

    tts = CartesiaTTSService(
        api_key=config.cartesia_api_key,
        voice_id=config.cartesia_voice_id,
        model=config.cartesia_model,
    )

    simli = SimliVideoService(
        api_key=config.simli_api_key,
        face_id=config.simli_face_id,
        params=SimliVideoService.InputParams(
            max_session_length=3600,  # 1 hour
            max_idle_time=300,        # 5 minutes
        ),
    )

    llm_context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context=llm_context)

    return Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            simli,
            transport.output(),
            assistant_aggregator,
        ]
    )


async def run() -> None:
    config = load_config()
    pipeline = build_pipeline(config)
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
        ),
    )
    runner = PipelineRunner()
    await runner.run(task)


def main() -> None:
    try:
        asyncio.run(run())
    except Exception as exc:
        print(f"Bot failed to start: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
