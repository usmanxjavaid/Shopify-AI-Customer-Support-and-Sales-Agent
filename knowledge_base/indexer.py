"""
knowledge_base/indexer.py
----------------------------
Orchestrates the full indexing pipeline: read files from knowledge/,
chunk them, and store them in the vector database.

This is the only file that ties document_readers, chunker, and
vector_store together — each of those stays independently simple
and testable.
"""

from pathlib import Path

from knowledge_base.document_readers import read_document, READERS
from knowledge_base.chunker import chunk_text
from knowledge_base.vector_store import clear_collection, add_chunks, collection_is_empty
from logger import get_logger

logger = get_logger(__name__)

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"


def build_index() -> int:
    """
    Rebuilds the entire knowledge base index from scratch.

    Reads every supported file in knowledge/, chunks it, and stores
    all chunks in the vector database. Clears any previous index
    first, so this is safe to re-run whenever documents change.

    Returns:
        Total number of chunks indexed.
    """
    if not KNOWLEDGE_DIR.exists():
        logger.warning(f"Knowledge directory does not exist: {KNOWLEDGE_DIR}")
        return 0

    clear_collection()

    files = [
        f for f in KNOWLEDGE_DIR.iterdir()
        if f.suffix.lower() in READERS
    ]

    if not files:
        logger.warning(f"No knowledge documents found in {KNOWLEDGE_DIR}")
        return 0

    all_chunks = []
    all_ids = []
    all_metadatas = []

    for file_path in files:
        try:
            text = read_document(file_path)
        except Exception as e:
            logger.error(f"Failed to read {file_path.name}: {e}")
            continue

        chunks = chunk_text(text)
        logger.info(f"{file_path.name}: {len(chunks)} chunks")

        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            all_ids.append(f"{file_path.stem}_{i}")
            all_metadatas.append({"source": file_path.name})

    add_chunks(all_chunks, all_ids, all_metadatas)

    logger.info(f"Knowledge base indexed: {len(all_chunks)} total chunks")
    return len(all_chunks)


def ensure_index_built() -> None:
    """
    Builds the knowledge base index automatically if it's currently
    empty — called on app startup. Safe to call every time the app
    starts: does nothing (no API calls, no cost) if the index already
    has data, only builds if genuinely missing (e.g. first deploy,
    fresh container, wiped volume).

    If you update documents in knowledge/, still run build_index.py
    manually to force a rebuild — this function only fills a gap,
    it doesn't detect changed documents.
    """
    if collection_is_empty():
        logger.info("Knowledge base index is empty — building automatically")
        count = build_index()
        logger.info(f"Auto-build complete: indexed {count} chunks")
    else:
        logger.debug("Knowledge base index already populated, skipping auto-build")


logger.debug("knowledge_base.indexer loaded successfully")