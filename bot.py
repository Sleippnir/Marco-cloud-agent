"""Pipecat Cloud entry point for the RAG-enabled voice agent.

This module provides the `bot()` function entry point required by Pipecat Cloud.
The platform automatically injects room credentials via DailySessionArguments.

Frame flow:
    audio in → VAD → STT → [RAG context injection] → LLM → TTS → Simli → audio/video out

Interruption policy:
    - Barge-in enabled via PipelineParams
    - SileroVAD for speech detection, SmartTurnAnalyzer for intelligent turn-taking
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass

from pipecat.frames.frames import EndFrame, EndTaskFrame, TextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import FunctionCallParams
from deepgram import LiveOptions

from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.simli.video import SimliVideoService
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.transcriptions.language import Language
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies

from rag import LanceDBRetriever
from processors import RAGContextProcessor

# Configure logging for Pipecat Cloud observability
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BotConfig:
    """Configuration for the voice agent services."""

    # Daily transport (provided by Pipecat Cloud or env)
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

    # OpenAI LLM
    openai_api_key: str
    openai_model: str
    system_instruction: str

    # Bot identity
    bot_name: str

    # RAG configuration
    rag_enabled: bool
    rag_match_count: int
    rag_match_threshold: float
    rag_min_query_length: int


def _require_env(name: str) -> str:
    """Get required environment variable or raise."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_config(room_url: str | None = None, token: str | None = None) -> BotConfig:
    """Load configuration from environment with optional overrides.

    Args:
        room_url: Override DAILY_ROOM_URL (provided by Pipecat Cloud).
        token: Override DAILY_TOKEN (provided by Pipecat Cloud).
    """
    # Default system instruction with RAG context placeholder
    default_instruction = """You are Marco, a knowledgeable and friendly voice assistant.
You are helpful, concise, and conversational in your responses.
When provided with context from the knowledge base, use it to ground your answers.
Keep responses natural and brief - this is a voice conversation, not a text chat.
If you don't know something, say so honestly."""

    return BotConfig(
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
        openai_api_key=_require_env("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        system_instruction=os.getenv("SYSTEM_INSTRUCTION", default_instruction),
        bot_name=os.getenv("BOT_NAME", "Marco"),
        rag_enabled=os.getenv("RAG_ENABLED", "true").lower() == "true",
        rag_match_count=int(os.getenv("RAG_MATCH_COUNT", "3")),
        rag_match_threshold=float(os.getenv("RAG_MATCH_THRESHOLD", "0.5")),
        rag_min_query_length=int(os.getenv("RAG_MIN_QUERY_LENGTH", "8")),
    )


async def main(room_url: str, token: str | None = None) -> None:
    """Main pipeline execution.

    Args:
        room_url: Daily room URL for the session.
        token: Optional Daily room token.
    """
    config = load_config(room_url=room_url, token=token)

    # Initialize RAG retriever if enabled
    retriever = None
    if config.rag_enabled:
        try:
            retriever = LanceDBRetriever(
                match_count=config.rag_match_count,
                match_threshold=config.rag_match_threshold,
            )
            logger.info(f"RAG retriever initialized with {retriever.document_count} documents")
        except Exception as e:
            logger.warning(f"RAG initialization failed, continuing without RAG: {e}")

    # Daily WebRTC transport with video output enabled for Simli
    transport = DailyTransport(
        room_url=config.daily_room_url,
        token=config.daily_token,
        bot_name=config.bot_name,
        params=DailyParams(
            api_key=config.daily_api_key,
            audio_in_enabled=True,
            audio_out_enabled=True,
            video_out_enabled=True,
            video_out_is_live=True,  # Critical for Simli video output!
            video_out_width=512,
            video_out_height=512,
            transcription_enabled=False,  # We use Deepgram directly
            # SileroVAD for speech detection, SmartTurn handles intelligent turn-taking
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
        ),
    )

    # Deepgram STT with smart endpointing for better turn detection
    stt = DeepgramSTTService(
        api_key=config.deepgram_api_key,
        live_options=LiveOptions(
            model=config.deepgram_model,
            language=config.deepgram_language,
            smart_format=True,
            # Endpointing: wait for natural sentence ends, not just silence
            endpointing=1200,  # 1200ms before finalizing
            utterance_end_ms=1500,  # 1.5s max utterance gap
        ),
    )

    # RAG context processor (if enabled and retriever available)
    rag_processor = None
    if config.rag_enabled and retriever:
        rag_processor = RAGContextProcessor(
            retriever=retriever,
            strategy="AUGMENT_SYSTEM",
            min_query_length=config.rag_min_query_length,
        )
        logger.info("RAG context processor enabled")

    # OpenAI LLM with function calling tools
    tools = ToolsSchema(
        standard_tools=[
            FunctionSchema(
                name="end_call",
                description="Ends the conversation and hangs up the call. Only use this when the user explicitly says goodbye, wants to end the call, or indicates they are done.",
                properties={},
                required=[],
            )
        ]
    )

    llm = OpenAILLMService(
        api_key=config.openai_api_key,
        model=config.openai_model,
    )

    # Register end call handler
    async def end_call_handler(params: FunctionCallParams):
        """Handle the end_call function - says goodbye then terminates."""
        logger.info("End call requested by user")
        # Say goodbye first, then end after a delay
        await task.queue_frames([TextFrame("Goodbye! Take care.")])
        await asyncio.sleep(2)  # Wait for TTS to speak
        # Push EndTaskFrame upstream to signal pipeline termination
        await params.llm.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)

    llm.register_function("end_call", end_call_handler)

    # Cartesia TTS
    tts = CartesiaTTSService(
        api_key=config.cartesia_api_key,
        voice_id=config.cartesia_voice_id,
        model=config.cartesia_model,
    )

    # Simli avatar video with logging enabled for debugging
    simli = SimliVideoService(
        api_key=config.simli_api_key,
        face_id=config.simli_face_id,
        params=SimliVideoService.InputParams(
            max_session_length=3600,  # 1 hour
            max_idle_time=300,        # 5 minutes
            enable_logging=True,      # Enable Simli SDK logging
        ),
    )

    # LLM context with system prompt, tools, and SmartTurn analyzer
    messages = [
        {
            "role": "system",
            "content": config.system_instruction + " When the user says goodbye or wants to end the call, use the end_call function.",
        },
    ]
    context = LLMContext(messages, tools=tools)
    
    # Use SmartTurnAnalyzer to detect natural turn-taking (not just silence)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(
                stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3())]
            ),
        ),
    )

    # Build processor chain
    processors = [
        transport.input(),
        stt,
    ]

    # Insert RAG processor after STT if enabled
    if rag_processor:
        processors.append(rag_processor)

    processors.extend([
        user_aggregator,
        llm,
        tts,
    ])
    
    # Add Simli if enabled
    if simli:
        processors.append(simli)
    
    processors.extend([
        transport.output(),
        assistant_aggregator,
    ])

    pipeline = Pipeline(processors)

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    # Event handlers - transport events for participants
    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        logger.info(f"First participant joined: {participant['id']}")
        # Start capturing participant audio
        await transport.capture_participant_transcription(participant["id"])
        # Send greeting
        await task.queue_frames([TextFrame("Hey there! How can I help you?")])

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        logger.info(f"Participant left: {participant['id']}, reason: {reason}")
        await task.queue_frame(EndFrame())

    @transport.event_handler("on_dialin_ready")
    async def on_dialin_ready(transport, cdata):
        logger.info(f"Dialin ready: {cdata}")

    runner = PipelineRunner()
    await runner.run(task)


# =============================================================================
# PIPECAT CLOUD ENTRY POINT
# =============================================================================

try:
    from pipecat_cloud.agent import DailySessionArguments
except ImportError:
    # Fallback for local development without pipecat-cloud package
    from dataclasses import dataclass as _dc

    @_dc
    class DailySessionArguments:
        """Stub for local development."""

        room_url: str
        token: str


async def bot(args: DailySessionArguments) -> None:
    """Pipecat Cloud entry point.

    This function is called by Pipecat Cloud when a session is started.
    The platform provides room credentials via DailySessionArguments.

    Args:
        args: Session arguments containing room_url and token.
    """
    logger.info(f"Bot session starting for room: {args.room_url}")

    try:
        await main(args.room_url, args.token)
    except Exception as e:
        logger.exception(f"Bot session error: {e}")
        raise
    finally:
        logger.info("Bot session ended")


# =============================================================================
# LOCAL DEVELOPMENT ENTRY POINT
# =============================================================================

def run_local() -> None:
    """Run the bot locally for development.

    Reads DAILY_ROOM_URL and DAILY_TOKEN from environment.
    """
    try:
        config = load_config()
        asyncio.run(main(config.daily_room_url, config.daily_token))
    except Exception as exc:
        print(f"Bot failed to start: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    run_local()
