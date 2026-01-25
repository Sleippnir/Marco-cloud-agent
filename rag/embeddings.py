"""Embedding generation using FastEmbed (local, no API required).

Lightweight wrapper for generating embeddings compatible with LanceDB.
Uses BAAI/bge-small-en-v1.5 by default (384 dimensions).
"""

from typing import List

from fastembed import TextEmbedding


class LocalEmbeddings:
    """Generate text embeddings using FastEmbed (local model).

    Uses BAAI/bge-small-en-v1.5 by default (384 dimensions).
    No API key required - runs locally.
    """

    DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIMENSION = 384

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
    ) -> None:
        """Initialize the embedding model.

        Args:
            model: FastEmbed model name.
        """
        self._model = TextEmbedding(model_name=model)
        self._model_name = model

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text.

        Args:
            text: The text to embed.

        Returns:
            List of floats representing the embedding vector.
        """
        embeddings = list(self._model.embed([text]))
        return list(embeddings[0])

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple documents.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.
        """
        embeddings = list(self._model.embed(texts))
        return [list(e) for e in embeddings]

    @property
    def dimension(self) -> int:
        """Return the embedding dimension."""
        return self.EMBEDDING_DIMENSION


# Alias for backward compatibility
Embeddings = LocalEmbeddings
