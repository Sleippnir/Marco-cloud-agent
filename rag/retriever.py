"""LanceDB retriever for local RAG pipeline.

Provides fast, zero-latency semantic search using an embedded LanceDB index.
Perfect for small, static knowledge bases baked into the Docker image.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import lancedb
from lancedb.table import Table

from rag.embeddings import GoogleEmbeddings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievedDocument:
    """A document retrieved from the knowledge base."""

    id: str
    content: str
    metadata: dict
    similarity: float


class LanceDBRetriever:
    """Vector retrieval using embedded LanceDB.

    LanceDB stores the index locally, making it ideal for:
    - Small, static knowledge bases
    - Zero network latency queries
    - Self-contained Docker deployments

    The index is typically built at Docker image build time and
    baked into the container.
    """

    DEFAULT_DB_PATH = "./knowledge_base"
    DEFAULT_TABLE = "documents"
    DEFAULT_MATCH_COUNT = 3
    DEFAULT_MATCH_THRESHOLD = 0.7

    def __init__(
        self,
        db_path: str | None = None,
        embeddings: GoogleEmbeddings | None = None,
        table_name: str = DEFAULT_TABLE,
        match_count: int = DEFAULT_MATCH_COUNT,
        match_threshold: float = DEFAULT_MATCH_THRESHOLD,
    ) -> None:
        """Initialize the retriever.

        Args:
            db_path: Path to LanceDB directory. Falls back to LANCEDB_PATH env var.
            embeddings: Embedding generator. Creates GoogleEmbeddings if not provided.
            table_name: Name of the documents table.
            match_count: Number of documents to retrieve.
            match_threshold: Minimum similarity score (0-1).
        """
        self._db_path = db_path or os.getenv("LANCEDB_PATH", self.DEFAULT_DB_PATH)
        self._embeddings = embeddings or GoogleEmbeddings()
        self._table_name = table_name
        self._match_count = match_count
        self._match_threshold = match_threshold

        # Connect to database
        self._db = lancedb.connect(self._db_path)
        self._table: Optional[Table] = None

        # Try to open existing table
        try:
            if self._table_name in self._db.table_names():
                self._table = self._db.open_table(self._table_name)
                logger.info(
                    f"Opened LanceDB table '{self._table_name}' with "
                    f"{self._table.count_rows()} documents"
                )
            else:
                logger.warning(
                    f"Table '{self._table_name}' not found in {self._db_path}. "
                    "Run ingestion script to create it."
                )
        except Exception as e:
            logger.error(f"Failed to open LanceDB table: {e}")

    def retrieve_sync(
        self,
        query: str,
        match_count: int | None = None,
        match_threshold: float | None = None,
    ) -> List[RetrievedDocument]:
        """Retrieve relevant documents for a query.

        Args:
            query: The search query (typically user's transcribed speech).
            match_count: Override default number of results.
            match_threshold: Override default similarity threshold.

        Returns:
            List of RetrievedDocument objects sorted by relevance.
        """
        if self._table is None:
            logger.warning("No table available for retrieval")
            return []

        try:
            # Generate query embedding
            query_embedding = self._embeddings.embed_text(query)

            # Perform vector search
            results = (
                self._table.search(query_embedding)
                .limit(match_count or self._match_count)
                .to_list()
            )

            # Filter by threshold and convert to RetrievedDocument
            threshold = match_threshold or self._match_threshold
            documents = []

            for row in results:
                # LanceDB returns _distance (L2) by default, convert to similarity
                # For cosine distance: similarity = 1 - distance
                # For L2 distance: similarity = 1 / (1 + distance)
                distance = row.get("_distance", 0)
                similarity = 1 / (1 + distance)  # Convert L2 to similarity

                if similarity >= threshold:
                    documents.append(
                        RetrievedDocument(
                            id=row.get("id", str(hash(row.get("content", "")))),
                            content=row.get("content", ""),
                            metadata=row.get("metadata", {}),
                            similarity=similarity,
                        )
                    )

            logger.debug(f"Retrieved {len(documents)} documents for query: {query[:50]}...")
            return documents

        except Exception as e:
            logger.error(f"RAG retrieval failed: {e}")
            return []

    async def retrieve(
        self,
        query: str,
        match_count: int | None = None,
        match_threshold: float | None = None,
    ) -> List[RetrievedDocument]:
        """Async wrapper for retrieve_sync (LanceDB is sync but fast)."""
        return self.retrieve_sync(query, match_count, match_threshold)

    def format_context(self, documents: List[RetrievedDocument]) -> str:
        """Format retrieved documents as context for LLM injection.

        Args:
            documents: List of retrieved documents.

        Returns:
            Formatted context string for prompt augmentation.
        """
        if not documents:
            return ""

        context_parts = ["Relevant information about me:"]
        for i, doc in enumerate(documents, 1):
            context_parts.append(f"\n[{i}] {doc.content}")

        return "\n".join(context_parts)

    def add_documents(self, documents: List[dict]) -> int:
        """Add documents to the knowledge base.

        Args:
            documents: List of dicts with 'content' and optional 'metadata', 'id' keys.

        Returns:
            Number of documents added.
        """
        if not documents:
            return 0

        # Generate embeddings
        contents = [doc["content"] for doc in documents]
        embeddings = self._embeddings.embed_documents(contents)

        # Prepare records
        records = []
        for i, (doc, embedding) in enumerate(zip(documents, embeddings)):
            records.append({
                "id": doc.get("id", f"doc_{i}"),
                "content": doc["content"],
                "metadata": doc.get("metadata", {}),
                "vector": embedding,
            })

        # Create or append to table
        if self._table is None:
            self._table = self._db.create_table(self._table_name, records)
            logger.info(f"Created table '{self._table_name}' with {len(records)} documents")
        else:
            self._table.add(records)
            logger.info(f"Added {len(records)} documents to '{self._table_name}'")

        return len(records)

    @property
    def document_count(self) -> int:
        """Get the number of documents in the knowledge base."""
        if self._table is None:
            return 0
        return self._table.count_rows()


# Alias for backward compatibility
SupabaseRAGRetriever = LanceDBRetriever
