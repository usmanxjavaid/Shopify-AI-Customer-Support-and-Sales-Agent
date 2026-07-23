"""
knowledge_base/chunker.py
----------------------------
Splits raw document text into overlapping chunks suitable for
embedding. Knows nothing about files or databases — just
"text in, list of chunks out."
"""

from logger import get_logger

logger = get_logger(__name__)


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """
    Splits text into overlapping chunks.

    Overlap ensures we don't lose context at chunk boundaries — e.g.
    a sentence split across two chunks still has enough surrounding
    text in at least one of them to be understood on its own.

    Args:
        text:       Full document text.
        chunk_size: Target characters per chunk.
        overlap:    Characters shared between consecutive chunks.

    Returns:
        List of non-empty, stripped text chunks.
    """
    if not text.strip():
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap

    return [c.strip() for c in chunks if c.strip()]


logger.debug("knowledge_base.chunker loaded successfully")