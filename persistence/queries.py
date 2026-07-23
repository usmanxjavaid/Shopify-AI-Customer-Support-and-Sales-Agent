"""
persistence/queries.py
------------------------
Read/query functions for the admin dashboard.

Separate from audit_log.py (which only WRITES records) — this file
only READS and aggregates data for display purposes.
"""

from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, update

from persistence.db import engine, tool_calls_table, escalations_table
from logger import get_logger

logger = get_logger(__name__)


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


logger.debug("persistence.queries loaded successfully")