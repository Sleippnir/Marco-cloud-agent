"""Minimal Simli debug bot for isolating audio/video sync issues.

This is a stripped-down test harness separate from bot.py.
Pipeline: Daily transport → Deepgram STT → LLM → Cartesia TTS → Simli → Daily output

Debug logging timestamps:
  [TTS_EMIT] - When TTS emits an audio chunk
  [SIMLI_AUDIO_IN] - When audio is sent to Simli
  [SIMLI_VIDEO_OUT] - When Simli emits a video frame
"""

import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass

from pipecat.frames.frames import (
    AudioRawFrame,
    EndFrame,
    Frame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    TextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from deepgram import LiveOptions

from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.simli.video import SimliVideoService
from pipecat.transports.daily.transport import DailyParams, DailyTransport, WebRTCVADAnalyzer
from pipecat.transcriptions.language import Language

# Configure debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("simli_debug")
logger.setLevel(logging.DEBUG)

# Reduce noise from other loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.INFO)


# =============================================================================
# DEBUG FRAME PROCESSORS
# =============================================================================


class TTSDebugProcessor(FrameProcessor):
    """Logs TTS audio chunks with timestamps."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._chunk_count = 0
        self._tts_start_time: float | None = None
        self._total_audio_bytes = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TTSStartedFrame):
            self._tts_start_time = time.perf_counter()
            self._chunk_count = 0
            self._total_audio_bytes = 0
            logger.info("[TTS_EMIT] === TTS Started ===")

        elif isinstance(frame, TTSAudioRawFrame):
            self._chunk_count += 1
            audio_len = len(frame.audio) if frame.audio else 0
            self._total_audio_bytes += audio_len
            elapsed = (
                (time.perf_counter() - self._tts_start_time) * 1000
                if self._tts_start_time
                else 0
            )
            logger.info(
                f"[TTS_EMIT] chunk={self._chunk_count:03d} "
                f"bytes={audio_len:5d} "
                f"total={self._total_audio_bytes:7d} "
                f"elapsed={elapsed:7.1f}ms "
                f"sample_rate={frame.sample_rate} "
                f"channels={frame.num_channels}"
            )

        elif isinstance(frame, TTSStoppedFrame):
            elapsed = (
                (time.perf_counter() - self._tts_start_time) * 1000
                if self._tts_start_time
                else 0
            )
            logger.info(
                f"[TTS_EMIT] === TTS Stopped === "
                f"chunks={self._chunk_count} "
                f"total_bytes={self._total_audio_bytes} "
                f"duration={elapsed:.1f}ms"
            )
            self._tts_start_time = None

        await self.push_frame(frame, direction)


class SimliInputDebugProcessor(FrameProcessor):
    """Logs TTS audio frames going INTO Simli (ignores user mic to reduce noise)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tts_chunk_count = 0
        self._session_start = time.perf_counter()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # Only log TTS audio, not user microphone (reduces log spam)
        if isinstance(frame, TTSAudioRawFrame):
            self._tts_chunk_count += 1
            audio_len = len(frame.audio) if frame.audio else 0
            session_elapsed = (time.perf_counter() - self._session_start) * 1000
            logger.info(
                f"[SIMLI_AUDIO_IN] tts_chunk={self._tts_chunk_count:04d} "
                f"bytes={audio_len:5d} "
                f"session_time={session_elapsed:8.1f}ms"
            )

        await self.push_frame(frame, direction)


class AudioPassthroughForSimli(FrameProcessor):
    """Passes TTS audio directly to output while ALSO sending to Simli.
    
    This fixes the issue where SimliVideoService consumes audio but doesn't
    pass it through (it expects Simli to return lip-synced audio, but that
    may not always work).
    
    Place this AFTER Simli in the pipeline - it will receive:
    - Video frames from Simli (pass through)
    - TTS audio from the Simli audio iterator (if any)
    
    But we also need audio to reach output even if Simli doesn't return it.
    So we use a different approach: duplicate audio BEFORE Simli.
    """
    pass  # Placeholder - see actual fix below


class AudioDuplicator(FrameProcessor):
    """Duplicates TTS audio frames to a secondary output.
    
    This allows audio to bypass Simli and go directly to Daily output
    while Simli still receives it for video generation.
    """
    
    def __init__(self, audio_sink: FrameProcessor, **kwargs):
        super().__init__(**kwargs)
        self._audio_sink = audio_sink
        self._chunk_count = 0
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        
        # Duplicate TTS audio to the secondary sink (bypassing Simli)
        if isinstance(frame, (TTSAudioRawFrame, TTSStartedFrame, TTSStoppedFrame)):
            self._chunk_count += 1
            if isinstance(frame, TTSAudioRawFrame) and self._chunk_count % 20 == 1:
                logger.debug(f"[AUDIO_DUP] Duplicating audio chunk {self._chunk_count} to bypass")
            # Send copy directly to audio sink (transport output)
            await self._audio_sink.process_frame(frame, direction)
        
        # Also pass frame downstream (to Simli for video generation)
        await self.push_frame(frame, direction)


class SimliOutputDebugProcessor(FrameProcessor):
    """Logs video/image AND audio frames coming OUT of Simli."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._video_frame_count = 0
        self._audio_frame_count = 0
        self._session_start = time.perf_counter()
        self._last_video_time: float | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        frame_name = type(frame).__name__
        now = time.perf_counter()
        session_elapsed = (now - self._session_start) * 1000

        # Simli outputs OutputImageRawFrame for video (not VideoRawFrame!)
        if "Image" in frame_name and "Raw" in frame_name:
            self._video_frame_count += 1
            
            # Calculate frame interval
            interval_ms = 0.0
            if self._last_video_time:
                interval_ms = (now - self._last_video_time) * 1000
            self._last_video_time = now

            # Try to get frame dimensions
            size = getattr(frame, "size", (0, 0))
            width = size[0] if isinstance(size, tuple) else "?"
            height = size[1] if isinstance(size, tuple) else "?"

            logger.info(
                f"[SIMLI_VIDEO_OUT] frame={self._video_frame_count:05d} "
                f"size={width}x{height} "
                f"interval={interval_ms:6.1f}ms "
                f"session_time={session_elapsed:8.1f}ms"
            )
        
        # Simli also outputs its own TTSAudioRawFrame (lip-synced audio)
        elif isinstance(frame, TTSAudioRawFrame):
            self._audio_frame_count += 1
            audio_len = len(frame.audio) if frame.audio else 0
            # Only log every 10th audio frame to reduce noise
            if self._audio_frame_count % 10 == 1:
                logger.info(
                    f"[SIMLI_AUDIO_OUT] frame={self._audio_frame_count:05d} "
                    f"bytes={audio_len:5d} "
                    f"session_time={session_elapsed:8.1f}ms"
                )

        await self.push_frame(frame, direction)


# =============================================================================
# CONFIGURATION (mirrors bot.py pattern)
# =============================================================================


@dataclass(frozen=True)
class DebugBotConfig:
    """Minimal configuration for debug bot."""

    # Daily transport
    daily_api_key: str
    daily_room_url: str
    daily_token: str | None

    # Simli avatar
    simli_api_key: str
    simli_face_id: str

    # Deepgram STT
    deepgram_api_key: str
    deepgram_model: str
    deepgram_language: Language

    # Cartesia TTS
    cartesia_api_key: str
    cartesia_voice_id: str
    cartesia_model: str

    # Google LLM
    google_api_key: str
    google_model: str

    # Bot identity
    bot_name: str


def _require_env(name: str) -> str:
    """Get required environment variable or raise."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_debug_config(room_url: str | None = None, token: str | None = None) -> DebugBotConfig:
    """Load configuration from environment (same env vars as bot.py)."""
    return DebugBotConfig(
        daily_api_key=_require_env("DAILY_API_KEY"),
        daily_room_url=room_url or _require_env("DAILY_ROOM_URL"),
        daily_token=token or os.getenv("DAILY_TOKEN"),
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
        bot_name=os.getenv("BOT_NAME", "DebugBot"),
    )


# =============================================================================
# MAIN PIPELINE
# =============================================================================

# Simple system prompt - no RAG, no complex persona
DEBUG_SYSTEM_PROMPT = "You are a test assistant. Respond in one short sentence."


async def main(room_url: str, token: str | None = None, enable_simli: bool = True) -> None:
    """Run the minimal debug pipeline."""
    config = load_debug_config(room_url=room_url, token=token)

    logger.info("=" * 60)
    logger.info("SIMLI DEBUG BOT STARTING")
    logger.info("=" * 60)
    logger.info(f"Room URL: {config.daily_room_url}")
    logger.info(f"Simli Face ID: {config.simli_face_id}")
    logger.info(f"Deepgram Model: {config.deepgram_model}")
    logger.info(f"Cartesia Voice: {config.cartesia_voice_id}")
    logger.info(f"LLM Model: {config.google_model}")
    logger.info("=" * 60)

    # VAD for turn detection
    vad_analyzer = WebRTCVADAnalyzer(
        sample_rate=16000,
        params=VADParams(),
    )

    # Daily WebRTC transport
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
            transcription_enabled=False,
        ),
    )

    # Deepgram STT
    stt = DeepgramSTTService(
        api_key=config.deepgram_api_key,
        live_options=LiveOptions(
            model=config.deepgram_model,
            language=config.deepgram_language,
        ),
    )

    # Google Gemini LLM - no tools, no function calling
    llm = GoogleLLMService(
        api_key=config.google_api_key,
        model=config.google_model,
        system_instruction=DEBUG_SYSTEM_PROMPT,
    )

    # Cartesia TTS
    tts = CartesiaTTSService(
        api_key=config.cartesia_api_key,
        voice_id=config.cartesia_voice_id,
        model=config.cartesia_model,
    )

    # Debug processors
    tts_debug = TTSDebugProcessor(name="TTSDebug")
    simli_input_debug = SimliInputDebugProcessor(name="SimliInputDebug")
    simli_output_debug = SimliOutputDebugProcessor(name="SimliOutputDebug")

    # Simli avatar video (optional)
    simli = None
    if enable_simli:
        simli = SimliVideoService(
            api_key=config.simli_api_key,
            face_id=config.simli_face_id,
            params=SimliVideoService.InputParams(
                max_session_length=3600,
                max_idle_time=300,
            ),
        )
        logger.info("[CONFIG] Simli ENABLED")
    else:
        logger.info("[CONFIG] Simli DISABLED - audio only mode")

    # LLM context (minimal - no system message in context, uses system_instruction)
    context = OpenAILLMContext([])
    context_aggregator = llm.create_context_aggregator(context)

    # Build pipeline with debug processors interspersed
    if enable_simli:
        # Flow: input → STT → context → LLM → TTS → [TTS_DEBUG] → [SIMLI_IN_DEBUG] → Simli → [SIMLI_OUT_DEBUG] → output
        pipeline = Pipeline([
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            tts_debug,              # Log TTS output
            simli_input_debug,      # Log audio going to Simli
            simli,
            simli_output_debug,     # Log video coming from Simli
            transport.output(),
            context_aggregator.assistant(),
        ])
    else:
        # Flow WITHOUT Simli: input → STT → context → LLM → TTS → [TTS_DEBUG] → output
        pipeline = Pipeline([
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            tts_debug,              # Log TTS output
            transport.output(),
            context_aggregator.assistant(),
        ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    # Event handlers
    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        logger.info(f"[EVENT] First participant joined: {participant['id']}")
        await transport.capture_participant_transcription(participant["id"])

        if enable_simli and simli:
            # Wait for Simli ready - check _simli_client (not _client)
            max_wait = 30
            waited = 0.0
            while waited < max_wait:
                # Check if SimliClient is initialized and connected
                if hasattr(simli, '_simli_client') and simli._simli_client:
                    client = simli._simli_client
                    # SimliClient has a 'ready' property when connected
                    if getattr(client, 'ready', False):
                        logger.info(f"[EVENT] Simli ready after {waited:.1f}s")
                        break
                    # Also check if initialized flag is set
                    if hasattr(simli, '_initialized') and simli._initialized:
                        logger.info(f"[EVENT] Simli initialized after {waited:.1f}s")
                        break
                await asyncio.sleep(0.5)
                waited += 0.5
            else:
                # Log more details about Simli state
                client = getattr(simli, '_simli_client', None)
                initialized = getattr(simli, '_initialized', False)
                ready = getattr(client, 'ready', False) if client else False
                logger.warning(
                    f"[EVENT] Simli not ready after {max_wait}s timeout "
                    f"(initialized={initialized}, client_ready={ready})"
                )

        # Send test greeting
        logger.info("[EVENT] Sending test greeting")
        await task.queue_frames([TextFrame("Hello! I am ready for testing.")])

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        logger.info(f"[EVENT] Participant left: {participant['id']}, reason: {reason}")
        await task.queue_frame(EndFrame())

    runner = PipelineRunner()
    logger.info("[PIPELINE] Starting runner...")
    await runner.run(task)
    logger.info("[PIPELINE] Runner finished")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Simli Debug Bot - Minimal Test Harness")
    parser.add_argument(
        "--no-simli", 
        action="store_true", 
        help="Disable Simli video (audio-only mode for testing)"
    )
    args = parser.parse_args()
    
    enable_simli = not args.no_simli
    
    print("\n" + "=" * 60)
    print("SIMLI DEBUG BOT - Minimal Test Harness")
    print("=" * 60)
    if enable_simli:
        print("Mode: FULL (Daily → Deepgram STT → Gemini → Cartesia TTS → Simli)")
        print("Watch for [TTS_EMIT], [SIMLI_AUDIO_IN], [SIMLI_VIDEO_OUT] log lines")
    else:
        print("Mode: AUDIO ONLY (Daily → Deepgram STT → Gemini → Cartesia TTS)")
        print("Watch for [TTS_EMIT] log lines (Simli disabled)")
    print("=" * 60 + "\n")

    try:
        config = load_debug_config()
        asyncio.run(main(config.daily_room_url, config.daily_token, enable_simli=enable_simli))
    except KeyboardInterrupt:
        print("\n[EXIT] Interrupted by user")
    except Exception as exc:
        print(f"\n[ERROR] Bot failed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
