"""RAG Context Processor for Pipecat pipelines.

This processor intercepts transcription frames and augments the LLM context
with relevant documents from the knowledge base before the LLM generates a response.

Frame flow:
    TranscriptionFrame → RAGContextProcessor → (augmented) LLMMessagesFrame

This approach is more portable than relying on LLM-specific function calling
APIs which vary between providers and Pipecat versions.
"""

import logging
from typing import Optional

from pipecat.frames.frames import (
    Frame,
    TextFrame,
    TranscriptionFrame,
    LLMMessagesFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from rag import SupabaseRAGRetriever


logger = logging.getLogger(__name__)


class RAGContextProcessor(FrameProcessor):
    """Augments LLM context with retrieved documents from knowledge base.

    This processor monitors incoming transcription frames and performs
    semantic search to find relevant documents. The context is then
    injected into the conversation flow.

    Strategies:
    1. AUGMENT_SYSTEM: Append context to system prompt (default)
    2. INJECT_CONTEXT: Add context as a system message before user message

    For voice agents, AUGMENT_SYSTEM is preferred as it doesn't add
    visible "context messages" to the conversation flow.
    """

    def __init__(
        self,
        retriever: SupabaseRAGRetriever,
        strategy: str = "AUGMENT_SYSTEM",
        min_query_length: int = 10,
        **kwargs,
    ) -> None:
        """Initialize the RAG context processor.

        Args:
            retriever: The Supabase RAG retriever instance.
            strategy: Context injection strategy ('AUGMENT_SYSTEM' or 'INJECT_CONTEXT').
            min_query_length: Minimum characters in transcription to trigger RAG.
            **kwargs: Additional arguments passed to FrameProcessor.
        """
        super().__init__(**kwargs)
        self._retriever = retriever
        self._strategy = strategy
        self._min_query_length = min_query_length
        self._last_context: Optional[str] = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process incoming frames and augment with RAG context.

        Args:
            frame: The incoming frame to process.
            direction: Frame flow direction (upstream/downstream).
        """
        await super().process_frame(frame, direction)

        # Only process downstream transcription frames
        if direction != FrameDirection.DOWNSTREAM:
            await self.push_frame(frame, direction)
            return

        # Check if this is a transcription we should augment
        if isinstance(frame, TranscriptionFrame):
            await self._handle_transcription(frame, direction)
        elif isinstance(frame, LLMMessagesFrame):
            await self._handle_llm_messages(frame, direction)
        else:
            # Pass through all other frames unchanged
            await self.push_frame(frame, direction)

    async def _handle_transcription(
        self, frame: TranscriptionFrame, direction: FrameDirection
    ) -> None:
        """Handle transcription frames by performing RAG lookup.

        Args:
            frame: The transcription frame containing user speech.
            direction: Frame flow direction.
        """
        text = frame.text.strip()

        # Skip short queries (likely incomplete utterances)
        if len(text) < self._min_query_length:
            logger.debug(f"Skipping RAG for short query: {text}")
            await self.push_frame(frame, direction)
            return

        # Perform RAG retrieval
        try:
            documents = self._retriever.retrieve_sync(text)

            if documents:
                self._last_context = self._retriever.format_context(documents)
                logger.info(
                    f"RAG retrieved {len(documents)} documents for: {text[:50]}..."
                )
            else:
                self._last_context = None
                logger.debug(f"No RAG results for: {text[:50]}...")

        except Exception as e:
            logger.error(f"RAG retrieval error: {e}")
            self._last_context = None

        # Pass the transcription through (context will be injected in LLMMessagesFrame)
        await self.push_frame(frame, direction)

    async def _handle_llm_messages(
        self, frame: LLMMessagesFrame, direction: FrameDirection
    ) -> None:
        """Handle LLM message frames by injecting RAG context.

        Args:
            frame: The LLM messages frame to augment.
            direction: Frame flow direction.
        """
        if not self._last_context:
            # No context to inject
            await self.push_frame(frame, direction)
            return

        # Get current messages
        messages = list(frame.messages) if frame.messages else []

        if self._strategy == "AUGMENT_SYSTEM":
            # Find and augment the system message
            messages = self._augment_system_message(messages)
        elif self._strategy == "INJECT_CONTEXT":
            # Inject context as a separate system message
            messages = self._inject_context_message(messages)

        # Clear the context after use (single-use)
        self._last_context = None

        # Create new frame with augmented messages
        augmented_frame = LLMMessagesFrame(messages=messages)
        await self.push_frame(augmented_frame, direction)

    def _augment_system_message(self, messages: list) -> list:
        """Augment the system message with RAG context.

        Args:
            messages: List of conversation messages.

        Returns:
            Messages with augmented system prompt.
        """
        augmented = []
        system_found = False

        for msg in messages:
            if msg.get("role") == "system" and not system_found:
                # Append RAG context to existing system message
                original_content = msg.get("content", "")
                augmented_content = f"{original_content}\n\n{self._last_context}"
                augmented.append({**msg, "content": augmented_content})
                system_found = True
            else:
                augmented.append(msg)

        # If no system message exists, prepend one with just the context
        if not system_found:
            augmented.insert(0, {"role": "system", "content": self._last_context})

        return augmented

    def _inject_context_message(self, messages: list) -> list:
        """Inject RAG context as a separate system message.

        Args:
            messages: List of conversation messages.

        Returns:
            Messages with injected context message.
        """
        # Find insertion point (after system message, before first user message)
        insert_idx = 0
        for i, msg in enumerate(messages):
            if msg.get("role") == "system":
                insert_idx = i + 1
            elif msg.get("role") == "user":
                break

        context_message = {
            "role": "system",
            "content": f"[Retrieved Context]\n{self._last_context}",
        }

        messages.insert(insert_idx, context_message)
        return messages

    @property
    def last_context(self) -> Optional[str]:
        """Get the last retrieved context (for testing/debugging)."""
        return self._last_context
