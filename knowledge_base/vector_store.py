"""
knowledge_base/vector_store.py
---------------------------------
Thin wrapper around ChromaDB. Uses Google's Gemini embedding API
instead of a local sentence-transformers model, since running a
local ML model requires far more memory than free-tier hosting
typically provides (Render's free tier is 512MB, PyTorch alone
can exceed that).
"""

from pathlib import Path
import chromadb
import requests

from config import settings
from logger import get_logger

logger = get_logger(__name__)

CHROMA_DIR = Path(__file__).parent.parent / "chroma_db"


class GeminiEmbeddingFunction:
    """
    Custom ChromaDB embedding function using Google's Gemini API
    instead of a local model.

    Implements BOTH __call__ (used for batch operations like adding
    documents) and embed_query (used internally by ChromaDB for
    single-query searches) — newer ChromaDB versions call embed_query
    directly for queries rather than always going through __call__.
    """

    def name(self) -> str:
        """Required by ChromaDB to identify this embedding function."""
        return "gemini-text-embedding-004"

    def _embed_one(self, text: str) -> list[float]:
        try:
            response = requests.post(
                url=(
                    "https://generativelanguage.googleapis.com/v1beta/"
                    "models/gemini-embedding-001:embedContent"
                    f"?key={settings.GOOGLE_AI_API_KEY}"
                ),
                json={"content": {"parts": [{"text": text}]}},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()["embedding"]["values"]
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return [0.0] * 768

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in input]

    def embed_query(self, input) -> list[list[float]]:
        """
        ChromaDB calls this the same way as __call__ (same 'input'
        keyword), just for query-time embedding rather than document
        indexing. Delegate straight to __call__ for consistency.
        """
        if isinstance(input, str):
            input = [input]
        return self.__call__(input)

    def embed_documents(self, input) -> list[list[float]]:
        """Some ChromaDB code paths call this instead of __call__ directly."""
        if isinstance(input, str):
            input = [input]
        return self.__call__(input)


_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
_collection = _client.get_or_create_collection(
    name="store_policies",
    embedding_function=GeminiEmbeddingFunction(),
)

def collection_is_empty() -> bool:
    """
    Checks whether the vector store currently has any indexed chunks.

    Used at startup to decide whether we need to build the index
    automatically — avoids wasting API calls re-embedding on every
    restart when the index already exists, while still guaranteeing
    it gets built at least once on a fresh deployment.
    """
    try:
        existing_ids = _collection.get()["ids"]
        return len(existing_ids) == 0
    except Exception as e:
        logger.error(f"Failed to check if collection is empty: {e}")
        return True

def clear_collection() -> int:
    existing_ids = _collection.get()["ids"]
    if existing_ids:
        _collection.delete(ids=existing_ids)
        logger.info(f"Cleared {len(existing_ids)} existing chunks")
    return len(existing_ids)


def add_chunks(chunks: list[str], ids: list[str], metadatas: list[dict]) -> None:
    if not chunks:
        return
    _collection.add(documents=chunks, ids=ids, metadatas=metadatas)
    logger.info(f"Added {len(chunks)} chunks to vector store")


def query(query_text: str, top_k: int = 3) -> list[str]:
    try:
        results = _collection.query(query_texts=[query_text], n_results=top_k)
        return results.get("documents", [[]])[0]
    except Exception as e:
        logger.error(f"Vector store query failed: {e}")
        return []


logger.debug("knowledge_base.vector_store loaded successfully")