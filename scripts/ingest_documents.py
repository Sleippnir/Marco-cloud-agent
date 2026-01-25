#!/usr/bin/env python3
"""Document ingestion script for building the LanceDB knowledge base.

This script reads markdown documents from a directory and creates a LanceDB
vector index for RAG retrieval.

Usage:
    python scripts/ingest_documents.py --dir knowledge/ --pattern "*.md" --output ./knowledge_base
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.embeddings import LocalEmbeddings
from rag.retriever import LanceDBRetriever

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def read_markdown_files(directory: str, pattern: str = "*.md") -> List[dict]:
    """Read all markdown files from a directory.

    Args:
        directory: Path to the directory containing documents.
        pattern: Glob pattern for matching files.

    Returns:
        List of document dicts with 'id', 'content', and 'metadata' keys.
    """
    documents = []
    dir_path = Path(directory)

    if not dir_path.exists():
        logger.warning(f"Directory does not exist: {directory}")
        return documents

    for file_path in dir_path.glob(pattern):
        if file_path.is_file():
            try:
                content = file_path.read_text(encoding="utf-8")
                
                # Skip empty files
                if not content.strip():
                    logger.debug(f"Skipping empty file: {file_path.name}")
                    continue

                # Split large documents into chunks
                chunks = split_into_chunks(content, max_chars=2000)
                
                for i, chunk in enumerate(chunks):
                    doc_id = f"{file_path.stem}_{i}" if len(chunks) > 1 else file_path.stem
                    documents.append({
                        "id": doc_id,
                        "content": chunk,
                        "metadata": {
                            "source": file_path.name,
                            "chunk_index": i,
                            "total_chunks": len(chunks),
                        },
                    })
                
                logger.info(f"Loaded {len(chunks)} chunk(s) from {file_path.name}")
                
            except Exception as e:
                logger.error(f"Failed to read {file_path}: {e}")

    return documents


def split_into_chunks(text: str, max_chars: int = 2000) -> List[str]:
    """Split text into chunks, preferring paragraph boundaries.

    Args:
        text: The text to split.
        max_chars: Maximum characters per chunk.

    Returns:
        List of text chunks.
    """
    # If text is short enough, return as-is
    if len(text) <= max_chars:
        return [text.strip()]

    chunks = []
    paragraphs = text.split("\n\n")
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # If adding this paragraph exceeds max, save current and start new
        if len(current_chunk) + len(para) + 2 > max_chars:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = para
        else:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para

    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks if chunks else [text[:max_chars]]


def main():
    """Main entry point for document ingestion."""
    parser = argparse.ArgumentParser(
        description="Ingest documents into LanceDB knowledge base"
    )
    parser.add_argument(
        "--dir",
        "-d",
        required=True,
        help="Directory containing documents to ingest",
    )
    parser.add_argument(
        "--pattern",
        "-p",
        default="*.md",
        help="Glob pattern for matching files (default: *.md)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="./knowledge_base",
        help="Output path for LanceDB (default: ./knowledge_base)",
    )
    parser.add_argument(
        "--table",
        "-t",
        default="documents",
        help="Name of the LanceDB table (default: documents)",
    )

    args = parser.parse_args()

    logger.info(f"Reading documents from: {args.dir}")
    logger.info(f"Pattern: {args.pattern}")
    logger.info(f"Output: {args.output}")

    # Read documents
    documents = read_markdown_files(args.dir, args.pattern)

    if not documents:
        logger.warning("No documents found to ingest")
        # Create empty database directory
        Path(args.output).mkdir(parents=True, exist_ok=True)
        sys.exit(0)

    logger.info(f"Found {len(documents)} document chunks to ingest")

    # Initialize retriever (this will create the database)
    try:
        embeddings = LocalEmbeddings()
        retriever = LanceDBRetriever(
            db_path=args.output,
            embeddings=embeddings,
            table_name=args.table,
        )

        # Add documents
        count = retriever.add_documents(documents)
        logger.info(f"Successfully ingested {count} documents into {args.output}")

    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
