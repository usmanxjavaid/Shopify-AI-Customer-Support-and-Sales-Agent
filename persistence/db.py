"""
persistence/db.py
------------------
PostgreSQL (Neon) connection and table setup for permanent audit logging.

This is separate from Redis (core/memory.py):
    - Redis: short-term conversation context, rolling 20-message window
    - PostgreSQL: permanent record of every tool call and escalation,
                   for auditing, debugging, and future admin dashboard

Uses SQLAlchemy Core (not ORM) for simplicity — we just need to insert
and query rows, no need for full ORM model complexity here.
"""

from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    JSON,
)
from datetime import datetime, timezone

from config import settings
from logger import get_logger

logger = get_logger(__name__)

# Neon requires SSL — this is handled automatically via the connection
# string itself (Neon's connection strings include sslmode=require)
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

metadata = MetaData()


tool_calls_table = Table(
    "tool_calls",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("channel", String(50), nullable=False),
    Column("user_id", String(255), nullable=False),
    Column("tool_name", String(100), nullable=False),
    Column("arguments", JSON, nullable=False),
    Column("result_summary", Text, nullable=False),
    Column("success", Boolean, nullable=False, default=True),
    Column("timestamp", DateTime(timezone=True), nullable=False),
)



tickets_table = Table(
    "tickets",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("channel", String(50), nullable=False),
    Column("user_id", String(255), nullable=False),
    Column("customer_email", String(255), nullable=True),
    Column("subject", Text, nullable=False),
    Column("status", String(20), nullable=False, default="open"),  # open, pending, resolved
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

ticket_messages_table = Table(
    "ticket_messages",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ticket_id", Integer, nullable=False),
    Column("sender", String(20), nullable=False),  # customer, agent, system
    Column("message", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

def init_db() -> None:
    """
    Creates all tables if they don't already exist.

    Safe to call every time the app starts — SQLAlchemy only
    creates tables that are missing, never recreates existing ones.
    """
    logger.info("Initializing database tables")

    try:
        metadata.create_all(engine)
        logger.info("Database tables ready")

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


logger.debug("persistence.db loaded successfully")