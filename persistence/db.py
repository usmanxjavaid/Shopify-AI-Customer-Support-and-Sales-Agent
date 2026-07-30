"""
persistence/db.py
------------------
PostgreSQL (Neon) connection and table setup for permanent audit
logging and the ticketing system.
"""

from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String,
    Text, Boolean, DateTime, JSON,
)
from config import settings
from logger import get_logger

logger = get_logger(__name__)

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
metadata = MetaData()

# ------------------------------------------------------------------
# tool_calls — full audit trail of every tool the agent executes
# ------------------------------------------------------------------
tool_calls_table = Table(
    "tool_calls", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("channel", String(50), nullable=False),
    Column("user_id", String(255), nullable=False),
    Column("tool_name", String(100), nullable=False),
    Column("arguments", JSON, nullable=False),
    Column("result_summary", Text, nullable=False),
    Column("success", Boolean, nullable=False, default=True),
    Column("timestamp", DateTime(timezone=True), nullable=False),
)

# ------------------------------------------------------------------
# tickets — replaces the old escalations_table entirely
# ------------------------------------------------------------------
tickets_table = Table(
    "tickets", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("channel", String(50), nullable=False),
    Column("user_id", String(255), nullable=False),
    Column("customer_email", String(255), nullable=True),
    Column("subject", Text, nullable=False),
    Column("status", String(20), nullable=False, default="open"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

ticket_messages_table = Table(
    "ticket_messages", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ticket_id", Integer, nullable=False),
    Column("sender", String(20), nullable=False),
    Column("message", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

# ------------------------------------------------------------------
# pending_replies — fallback delivery for web customers with no
# email on file (widget polls this). This was referenced before but
# never actually defined — that was the bug.
# ------------------------------------------------------------------
pending_replies_table = Table(
    "pending_replies", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("channel", String(50), nullable=False),
    Column("user_id", String(255), nullable=False),
    Column("message", Text, nullable=False),
    Column("delivered", Boolean, nullable=False, default=False),
    Column("timestamp", DateTime(timezone=True), nullable=False),
)


def init_db() -> None:
    """Creates all tables if they don't already exist."""
    logger.info("Initializing database tables")
    try:
        metadata.create_all(engine)
        logger.info("Database tables ready")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


logger.debug("persistence.db loaded successfully")