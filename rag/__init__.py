"""RAG (Retrieval-Augmented Generation) module for Pipecat voice agents.

Provides fast, local vector storage and retrieval using LanceDB for
grounding LLM responses in personal knowledge.
"""

from rag.retriever import LanceDBRetriever, RetrievedDocument
from rag.embeddings import GoogleEmbeddings

# Backward compatibility alias
SupabaseRAGRetriever = LanceDBRetriever

__all__ = ["LanceDBRetriever", "SupabaseRAGRetriever", "GoogleEmbeddings", "RetrievedDocument"]
