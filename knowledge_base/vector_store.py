"""
knowledge_base/vector_store.py
---------------------------------
Thin wrapper around ChromaDB. This file knows ONLY about the vector
database itself — adding chunks, querying, clearing. It has no idea
how documents are read or chunked; that's this package's other
modules' job (document_readers.py, chunker.py).

Lives inside knowledge_base/ rather than integrations/ because it is
only ever used by this RAG pipeline — nothing else in the project
talks to ChromaDB directly, unlike Shopify's client, which is shared
across several independent tools.
"""

from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions

from logger import get_logger

logger = get_logger(__name__)

CHROMA_DIR = Path(__file__).parent.parent / "chroma_db"

# Local embedding model — runs on CPU, no API calls, no ongoing cost.
_embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
_collection = _client.get_or_create_collection(
    name="store_policies",
    embedding_function=_embedding_fn,
)


def clear_collection() -> int:
    """
    Removes all existing chunks from the collection.

    Returns:
        Number of chunks that were removed.
    """
    existing_ids = _collection.get()["ids"]
    if existing_ids:
        _collection.delete(ids=existing_ids)
        logger.info(f"Cleared {len(existing_ids)} existing chunks")
    return len(existing_ids)


def add_chunks(chunks: list[str], ids: list[str], metadatas: list[dict]) -> None:
    """
    Adds text chunks to the vector store.

    Args:
        chunks:    List of text chunks to embed and store.
        ids:       Unique ID for each chunk.
        metadatas: Metadata dict per chunk (e.g. source filename).
    """
    if not chunks:
        return

    _collection.add(documents=chunks, ids=ids, metadatas=metadatas)
    logger.info(f"Added {len(chunks)} chunks to vector store")


def query(query_text: str, top_k: int = 3) -> list[str]:
    """
    Searches the vector store for chunks relevant to a query.

    Args:
        query_text: The search query.
        top_k:      Number of top matching chunks to return.

    Returns:
        List of matching text chunks, most relevant first.
    """
    try:
        results = _collection.query(query_texts=[query_text], n_results=top_k)
        return results.get("documents", [[]])[0]

    except Exception as e:
        logger.error(f"Vector store query failed: {e}")
        return []


logger.debug("knowledge_base.vector_store loaded successfully")