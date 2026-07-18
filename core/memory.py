"""
core/memory.py
---------------
Conversation memory using Redis (Upstash), with in-memory fallback.

Stores the last N messages per user so the LLM has context across
a conversation. Keyed by "channel:user_id" (e.g. "telegram:123456789").

Resilience:
    If Redis is unreachable (network issue, Upstash outage), we fall
    back to a local in-memory dict so the agent keeps working instead
    of crashing. This fallback is NOT persistent — it resets if the
    app restarts — but keeps things running during a temporary outage.
"""

import json
from upstash_redis import Redis

from config import settings
from logger import get_logger

logger = get_logger(__name__)

MAX_HISTORY = 20

_redis = Redis(
    url=settings.UPSTASH_REDIS_REST_URL,
    token=settings.UPSTASH_REDIS_REST_TOKEN,
)

# Fallback store — only used if Redis calls fail
_fallback_store: dict[str, list[dict]] = {}


def _key(channel: str, user_id: str) -> str:
    """Builds the storage key for a given user's conversation."""
    return f"conversation:{channel}:{user_id}"


def get_history(channel: str, user_id: str) -> list[dict]:
    """
    Retrieves conversation history for a user.

    Tries Redis first. If Redis is unreachable, falls back to
    local in-memory storage so the agent keeps functioning.

    Args:
        channel: Which channel the user is on e.g. "telegram".
        user_id: The user's stable ID within that channel.

    Returns:
        List of {"role": "user"|"assistant", "content": "..."} dicts,
        oldest first. Empty list if no history exists yet.
    """
    key = _key(channel, user_id)

    try:
        raw = _redis.get(key)

        if raw is None:
            logger.debug(f"No existing history for {key}")
            return []

        history = json.loads(raw)
        logger.debug(f"Loaded {len(history)} messages for {key} (Redis)")
        return history

    except Exception as e:
        logger.warning(
            f"Redis unavailable, using in-memory fallback for {key}: {e}"
        )
        return _fallback_store.get(key, [])


def append_turn(channel: str, user_id: str, role: str, content: str) -> None:
    """
    Appends a message to the user's conversation history.

    Tries Redis first. If Redis is unreachable, falls back to
    local in-memory storage so the conversation isn't lost mid-session.

    Args:
        channel: Which channel the user is on e.g. "telegram".
        user_id: The user's stable ID within that channel.
        role:    "user" or "assistant".
        content: The message text.
    """
    key = _key(channel, user_id)
    history = get_history(channel, user_id)
    history.append({"role": role, "content": content})

    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    try:
        _redis.set(key, json.dumps(history))
        logger.debug(f"Appended '{role}' message for {key} (Redis)")

    except Exception as e:
        logger.warning(
            f"Redis unavailable, saving to in-memory fallback for {key}: {e}"
        )
        _fallback_store[key] = history


def clear_history(channel: str, user_id: str) -> None:
    """
    Clears all conversation history for a user, in both Redis
    and the in-memory fallback.

    Args:
        channel: Which channel the user is on.
        user_id: The user's stable ID within that channel.
    """
    key = _key(channel, user_id)

    try:
        _redis.delete(key)
        logger.info(f"Cleared history for {key} (Redis)")

    except Exception as e:
        logger.warning(f"Redis unavailable while clearing {key}: {e}")

    _fallback_store.pop(key, None)


logger.debug("core.memory loaded successfully")