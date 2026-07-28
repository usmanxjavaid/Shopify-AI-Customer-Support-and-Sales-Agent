"""
persistence/queries.py
------------------------
Read/query functions for the admin dashboard.

Separate from audit_log.py (which only WRITES records) — this file
only READS and aggregates data for display purposes.
"""

from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, update
from persistence.db import pending_replies_table
from persistence.db import engine, tool_calls_table, escalations_table
from logger import get_logger

logger = get_logger(__name__)



def queue_human_reply(channel: str, user_id: str, message: str) -> None:
    """
    Queues a human agent's reply to be delivered to a customer.

    For Telegram, this is typically bypassed (delivered instantly via
    the bot API instead). For web, the widget polls and picks this up.
    """
    try:
        with engine.begin() as conn:
            conn.execute(
                pending_replies_table.insert().values(
                    channel=channel,
                    user_id=user_id,
                    message=message,
                    delivered=False,
                    timestamp=datetime.now(timezone.utc),
                )
            )
        logger.info(f"Queued human reply for {channel}:{user_id}")
    except Exception as e:
        logger.error(f"Failed to queue human reply: {e}")


def get_undelivered_replies(channel: str, user_id: str) -> list[dict]:
    """Fetches and marks-as-delivered any pending human replies for a user."""
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(pending_replies_table)
                .where(pending_replies_table.c.channel == channel)
                .where(pending_replies_table.c.user_id == user_id)
                .where(pending_replies_table.c.delivered == False)
                .order_by(pending_replies_table.c.timestamp.asc())
            ).mappings().all()

            if rows:
                ids = [r["id"] for r in rows]
                conn.execute(
                    update(pending_replies_table)
                    .where(pending_replies_table.c.id.in_(ids))
                    .values(delivered=True)
                )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to fetch pending replies: {e}")
        return []

def get_summary_stats() -> dict:
    """
    Returns high-level stats for the dashboard overview.

    Returns:
        Dict with total_conversations, total_escalations,
        pending_escalations, refunds_issued, refunds_blocked —
        all-time counts.
    """
    try:
        with engine.connect() as conn:
            total_tool_calls = conn.execute(
                select(func.count()).select_from(tool_calls_table)
            ).scalar()

            total_escalations = conn.execute(
                select(func.count()).select_from(escalations_table)
            ).scalar()

            pending_escalations = conn.execute(
                select(func.count())
                .select_from(escalations_table)
                .where(escalations_table.c.resolved == False)
            ).scalar()

            refunds_issued = conn.execute(
                select(func.count())
                .select_from(tool_calls_table)
                .where(tool_calls_table.c.tool_name == "initiate_refund")
                .where(tool_calls_table.c.result_summary.like("Refund successfully%"))
            ).scalar()

            refunds_blocked = conn.execute(
                select(func.count())
                .select_from(tool_calls_table)
                .where(tool_calls_table.c.tool_name == "initiate_refund")
                .where(tool_calls_table.c.result_summary.like("REFUND_NOT_ELIGIBLE%"))
            ).scalar()

            # Distinct conversations = distinct (channel, user_id) pairs
            distinct_users = conn.execute(
                select(func.count(func.distinct(
                    tool_calls_table.c.channel + ":" + tool_calls_table.c.user_id
                )))
            ).scalar()

        return {
            "total_tool_calls": total_tool_calls or 0,
            "total_conversations": distinct_users or 0,
            "total_escalations": total_escalations or 0,
            "pending_escalations": pending_escalations or 0,
            "refunds_issued": refunds_issued or 0,
            "refunds_blocked": refunds_blocked or 0,
        }

    except Exception as e:
        logger.error(f"Failed to fetch summary stats: {e}")
        return {
            "total_tool_calls": 0,
            "total_conversations": 0,
            "total_escalations": 0,
            "pending_escalations": 0,
            "refunds_issued": 0,
            "refunds_blocked": 0,
        }


def get_escalations(limit: int = 50) -> list[dict]:
    """
    Returns recent escalations, newest first.

    Args:
        limit: Maximum number of records to return.

    Returns:
        List of dicts with id, channel, user_id, reason, resolved, timestamp.
    """
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(escalations_table)
                .order_by(escalations_table.c.timestamp.desc())
                .limit(limit)
            ).mappings().all()

        return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Failed to fetch escalations: {e}")
        return []


def get_recent_tool_calls(limit: int = 50) -> list[dict]:
    """
    Returns recent tool call activity, newest first.

    Args:
        limit: Maximum number of records to return.

    Returns:
        List of dicts with tool call details.
    """
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(tool_calls_table)
                .order_by(tool_calls_table.c.timestamp.desc())
                .limit(limit)
            ).mappings().all()

        return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Failed to fetch tool calls: {e}")
        return []


def mark_escalation_resolved(escalation_id: int) -> bool:
    """
    Marks an escalation as resolved.

    Args:
        escalation_id: The ID of the escalation record.

    Returns:
        True if updated successfully, False otherwise.
    """
    try:
        with engine.begin() as conn:
            conn.execute(
                update(escalations_table)
                .where(escalations_table.c.id == escalation_id)
                .values(resolved=True)
            )
        logger.info(f"Marked escalation {escalation_id} as resolved")
        return True

    except Exception as e:
        logger.error(f"Failed to resolve escalation {escalation_id}: {e}")
        return False

from persistence.db import pending_returns_table


def create_pending_return(
    order_number: str, channel: str, user_id: str,
    customer_email: str, tracking_number: str
) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(
                pending_returns_table.insert().values(
                    order_number=order_number,
                    channel=channel,
                    user_id=user_id,
                    customer_email=customer_email,
                    tracking_number=tracking_number,
                    status="awaiting_return",
                    created_at=datetime.now(timezone.utc),
                )
            )
        logger.info(f"Created pending return for order #{order_number}")
    except Exception as e:
        logger.error(f"Failed to create pending return: {e}")


def get_pending_returns() -> list[dict]:
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(pending_returns_table)
                .where(pending_returns_table.c.status == "awaiting_return")
                .order_by(pending_returns_table.c.created_at.desc())
            ).mappings().all()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to fetch pending returns: {e}")
        return []


def mark_return_refunded(return_id: int) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(
                update(pending_returns_table)
                .where(pending_returns_table.c.id == return_id)
                .values(status="refunded", refunded_at=datetime.now(timezone.utc))
            )
        logger.info(f"Marked return {return_id} as refunded")
    except Exception as e:
        logger.error(f"Failed to mark return refunded: {e}")

logger.debug("persistence.queries loaded successfully")