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


escalations_table = Table(
    "escalations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("channel", String(50), nullable=False),
    Column("user_id", String(255), nullable=False),
    Column("reason", Text, nullable=False),
    Column("resolved", Boolean, nullable=False, default=False),
    Column("timestamp", DateTime(timezone=True), nullable=False),
)

pending_replies_table = Table(
    "pending_replies",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("channel", String(50), nullable=False),
    Column("user_id", String(255), nullable=False),
    Column("message", Text, nullable=False),
    Column("delivered", Boolean, nullable=False, default=False),
    Column("timestamp", DateTime(timezone=True), nullable=False),
)

pending_returns_table = Table(
    "pending_returns",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("order_number", String(50), nullable=False),
    Column("channel", String(50), nullable=False),
    Column("user_id", String(255), nullable=False),
    Column("customer_email", String(255), nullable=True),
    Column("tracking_number", String(255), nullable=True),
    Column("status", String(20), nullable=False, default="awaiting_return"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("refunded_at", DateTime(timezone=True), nullable=True),
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