"""Embedding generation using Google's text-embedding API.

Lightweight wrapper for generating embeddings compatible with LanceDB.
"""

import os
from typing import List

from google import genai


class GoogleEmbeddings:
    """Generate text embeddings using Google's embedding model.

    Uses text-embedding-004 by default (768 dimensions).
    """

    DEFAULT_MODEL = "text-embedding-004"
    EMBEDDING_DIMENSION = 768

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        """Initialize the embedding client.

        Args:
            api_key: Google API key. Falls back to GOOGLE_API_KEY env var.
            model: Embedding model name.
        """
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self._api_key:
            raise ValueError("Google API key required for embeddings")
        self._client = genai.Client(api_key=self._api_key)
        self._model = model

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text.

        Args:
            text: The text to embed.

        Returns:
            List of floats representing the embedding vector.
        """
        result = self._client.models.embed_content(
            model=self._model,
            contents=text,
        )
        return list(result.embeddings[0].values)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple documents.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.
        """
        embeddings = []
        for text in texts:
            result = self._client.models.embed_content(
                model=self._model,
                contents=text,
            )
            embeddings.append(list(result.embeddings[0].values))
        return embeddings

    @property
    def dimension(self) -> int:
        """Return the embedding dimension."""
        return self.EMBEDDING_DIMENSION
