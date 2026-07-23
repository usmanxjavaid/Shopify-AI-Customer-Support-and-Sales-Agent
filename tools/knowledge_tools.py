"""
tools/knowledge_tools.py
---------------------------
LLM-callable tool for answering policy/FAQ questions using the
store's knowledge base documents (shipping, returns, warranty, etc.)

This lets the agent answer from real store policy instead of
guessing or hallucinating an answer.
"""

from knowledge_base.vector_store import query as query_vector_store
from logger import get_logger

logger = get_logger(__name__)


def search_knowledge_base(question: str) -> str:
    """
    Searches the store's policy documents (shipping, returns,
    warranty, FAQ, terms of service) for an answer to a customer's
    question.

    Use this whenever a customer asks something about store policy
    that ISN'T covered by order/product lookup tools — e.g. shipping
    times, return windows, warranty coverage, payment methods, sizing.

    Args:
        question: The customer's question, in their own words.

    Returns:
        Plain text containing the most relevant policy information
        found. If nothing relevant is found, says so explicitly.
    """
    logger.info(f"Searching knowledge base: {question}")

    chunks = query_vector_store(question, top_k=3)

    if not chunks:
        return (
            "No relevant information found in the store's policy "
            "documents. Consider escalating to a human if the "
            "customer needs a definitive answer."
        )

    result = "\n\n---\n\n".join(chunks)
    logger.info(f"Knowledge base returned {len(chunks)} relevant chunks")
    return result


logger.debug("tools.knowledge_tools loaded successfully")