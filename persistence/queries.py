"""
persistence/queries.py
------------------------
Read/write functions for the admin dashboard and ticketing system.
"""

from datetime import datetime, timezone
from sqlalchemy import select, func, update

from persistence.db import (
    engine, tool_calls_table, tickets_table,
    ticket_messages_table, pending_replies_table,
)
from logger import get_logger

logger = get_logger(__name__)


def get_summary_stats() -> dict:
    """Returns high-level stats for the dashboard overview."""
    try:
        with engine.connect() as conn:
            total_tool_calls = conn.execute(
                select(func.count()).select_from(tool_calls_table)
            ).scalar()

            total_tickets = conn.execute(
                select(func.count()).select_from(tickets_table)
            ).scalar()

            pending_tickets = conn.execute(
                select(func.count())
                .select_from(tickets_table)
                .where(tickets_table.c.status.in_(["open", "pending"]))
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

            distinct_users = conn.execute(
                select(func.count(func.distinct(
                    tool_calls_table.c.channel + ":" + tool_calls_table.c.user_id
                )))
            ).scalar()

        return {
            "total_tool_calls": total_tool_calls or 0,
            "total_conversations": distinct_users or 0,
            "total_escalations": total_tickets or 0,
            "pending_escalations": pending_tickets or 0,
            "refunds_issued": refunds_issued or 0,
            "refunds_blocked": refunds_blocked or 0,
        }

    except Exception as e:
        logger.error(f"Failed to fetch summary stats: {e}")
        return {
            "total_tool_calls": 0, "total_conversations": 0,
            "total_escalations": 0, "pending_escalations": 0,
            "refunds_issued": 0, "refunds_blocked": 0,
        }


def get_recent_tool_calls(limit: int = 50) -> list[dict]:
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


# ------------------------------------------------------------------
# Tickets
# ------------------------------------------------------------------

def create_ticket(channel: str, user_id: str, customer_email: str, subject: str) -> int:
    now = datetime.now(timezone.utc)
    try:
        with engine.begin() as conn:
            result = conn.execute(
                tickets_table.insert().values(
                    channel=channel, user_id=user_id, customer_email=customer_email,
                    subject=subject, status="open", created_at=now, updated_at=now,
                )
            )
            ticket_id = result.inserted_primary_key[0]
            conn.execute(
                ticket_messages_table.insert().values(
                    ticket_id=ticket_id, sender="customer", message=subject, created_at=now,
                )
            )
        logger.info(f"Created ticket #{ticket_id} for {channel}:{user_id}")
        return ticket_id
    except Exception as e:
        logger.error(f"Failed to create ticket: {e}")
        return None


def add_ticket_message(ticket_id: int, sender: str, message: str) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(
                ticket_messages_table.insert().values(
                    ticket_id=ticket_id, sender=sender, message=message,
                    created_at=datetime.now(timezone.utc),
                )
            )
            conn.execute(
                update(tickets_table)
                .where(tickets_table.c.id == ticket_id)
                .values(updated_at=datetime.now(timezone.utc))
            )
        logger.info(f"Added {sender} message to ticket #{ticket_id}")
    except Exception as e:
        logger.error(f"Failed to add ticket message: {e}")


def get_open_ticket(channel: str, user_id: str) -> dict:
    try:
        with engine.connect() as conn:
            row = conn.execute(
                select(tickets_table)
                .where(tickets_table.c.channel == channel)
                .where(tickets_table.c.user_id == user_id)
                .where(tickets_table.c.status.in_(["open", "pending"]))
                .order_by(tickets_table.c.created_at.desc())
                .limit(1)
            ).mappings().first()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to check open ticket: {e}")
        return None


def get_ticket(ticket_id: int) -> dict:
    try:
        with engine.connect() as conn:
            row = conn.execute(
                select(tickets_table).where(tickets_table.c.id == ticket_id)
            ).mappings().first()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to fetch ticket #{ticket_id}: {e}")
        return None


def get_ticket_messages(ticket_id: int) -> list[dict]:
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(ticket_messages_table)
                .where(ticket_messages_table.c.ticket_id == ticket_id)
                .order_by(ticket_messages_table.c.created_at.asc())
            ).mappings().all()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to fetch messages for ticket #{ticket_id}: {e}")
        return []


def get_all_tickets(limit: int = 100) -> list[dict]:
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(tickets_table)
                .order_by(tickets_table.c.updated_at.desc())
                .limit(limit)
            ).mappings().all()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to fetch tickets: {e}")
        return []


def set_ticket_status(ticket_id: int, status: str) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(
                update(tickets_table)
                .where(tickets_table.c.id == ticket_id)
                .values(status=status, updated_at=datetime.now(timezone.utc))
            )
        logger.info(f"Ticket #{ticket_id} status set to {status}")
    except Exception as e:
        logger.error(f"Failed to update ticket #{ticket_id} status: {e}")


# ------------------------------------------------------------------
# Pending replies — fallback delivery for web customers with no
# email on file. Only actually used in that one edge case now;
# most web customers get emailed directly instead.
# ------------------------------------------------------------------

def queue_human_reply(channel: str, user_id: str, message: str) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(
                pending_replies_table.insert().values(
                    channel=channel, user_id=user_id, message=message,
                    delivered=False, timestamp=datetime.now(timezone.utc),
                )
            )
        logger.info(f"Queued human reply for {channel}:{user_id}")
    except Exception as e:
        logger.error(f"Failed to queue human reply: {e}")


def get_undelivered_replies(channel: str, user_id: str) -> list[dict]:
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


logger.debug("persistence.queries loaded successfully")