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
    instead of a local model. Keeps memory usage minimal since no
    ML model is loaded into our own process.
    """

    def __call__(self, input: list[str]) -> list[list[float]]:
        embeddings = []
        for text in input:
            try:
                response = requests.post(
                    url=(
                        "https://generativelanguage.googleapis.com/v1beta/"
                        "models/text-embedding-004:embedContent"
                        f"?key={settings.GOOGLE_AI_API_KEY}"
                    ),
                    json={"content": {"parts": [{"text": text}]}},
                    timeout=30,
                )
                response.raise_for_status()
                embeddings.append(response.json()["embedding"]["values"])
            except Exception as e:
                logger.error(f"Embedding failed: {e}")
                embeddings.append([0.0] * 768)  # fallback zero-vector
        return embeddings


_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
_collection = _client.get_or_create_collection(
    name="store_policies",
    embedding_function=GeminiEmbeddingFunction(),
)


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