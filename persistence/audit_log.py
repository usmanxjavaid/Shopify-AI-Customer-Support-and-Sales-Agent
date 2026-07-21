"""
persistence/audit_log.py
--------------------------
Functions to write audit records to PostgreSQL.

Called centrally from core/orchestrator.py — every tool execution
and every escalation gets logged here, so we have a permanent,
queryable record independent of Redis conversation memory.
"""

from datetime import datetime, timezone

from persistence.db import engine, tool_calls_table, escalations_table
from logger import get_logger

logger = get_logger(__name__)


def log_tool_call(
    channel: str,
    user_id: str,
    tool_name: str,
    arguments: dict,
    result_summary: str,
    success: bool = True,
) -> None:
    """
    Records a tool execution to the permanent audit log.

    Args:
        channel:         Which channel the user is on e.g. "telegram".
        user_id:         The user's stable ID within that channel.
        tool_name:        Name of the tool that was executed.
        arguments:       Arguments passed to the tool.
        result_summary:  The tool's returned result (truncated if huge).
        success:         Whether the tool executed without an exception.
    """
    try:
        with engine.begin() as conn:
            conn.execute(
                tool_calls_table.insert().values(
                    channel=channel,
                    user_id=user_id,
                    tool_name=tool_name,
                    arguments=arguments,
                    result_summary=result_summary[:2000],  # cap length
                    success=success,
                    timestamp=datetime.now(timezone.utc),
                )
            )
        logger.debug(f"Logged tool call: {tool_name} for {channel}:{user_id}")

    except Exception as e:
        # Audit logging failures should NEVER break the actual agent
        # flow — log the error and move on.
        logger.error(f"Failed to log tool call: {e}")


def log_escalation(channel: str, user_id: str, reason: str) -> None:
    """
    Records an escalation to the permanent audit log.

    Args:
        channel: Which channel the user is on.
        user_id: The user's stable ID within that channel.
        reason:  Why the conversation was escalated.
    """
    try:
        with engine.begin() as conn:
            conn.execute(
                escalations_table.insert().values(
                    channel=channel,
                    user_id=user_id,
                    reason=reason,
                    resolved=False,
                    timestamp=datetime.now(timezone.utc),
                )
            )
        logger.info(f"Logged escalation for {channel}:{user_id}")

    except Exception as e:
        logger.error(f"Failed to log escalation: {e}")


logger.debug("persistence.audit_log loaded successfully")