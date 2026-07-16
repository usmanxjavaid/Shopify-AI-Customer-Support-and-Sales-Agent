"""
core/models.py
--------------
Shared data models used across the entire project.

These are common 'shapes' that flow between layers:
Adapter -> Orchestrator -> Tools -> back up

Rules:
    - No Channel-specific fields here
    - Pure, clean, channel-agnostic data structures

Why dataclasses:
    - Simple, readable, no extra dependencies, built into Python
    - We use pydantic only where we need validation (e.g. API responses)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Literal
from logger import get_logger

logger = get_logger(__name__)

# Supported channels
Channel = Literal['telegram', 'whatsapp', 'web']

@dataclass
class NormalizedMessage:
    """
    A customer message, normalized from any channel into a common shape.

    The adapter layer creates this from a raw Telegram/WhatsApp/web payload.
    Everything downstream works with this — never with raw platform objects.

    Attributes:
        user_id:         Stable identifier for this user within their channel.
                         e.g. Telegram chat_id "123456789"
                              WhatsApp number "whatsapp:+92xxxxxxxxxx"
                              Web session id  "sess_abc123"

        channel:         Which platform this message came from.

        text:            The actual message text the customer sent.

        timestamp:       When the message was received (UTC).

        customer_email:  Shopify customer email, once we've identified who
                         this user is. Starts as None, gets filled in after
                         the customer provides their email or order number.
    """
    user_id: str
    channel: Channel
    text: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    customer_email: Optional[str] = None

@dataclass
class AgentResponse:
    """
    The agent's reply to a customer message.

    Created by the orchestrator and handed back to the adapter,
    which translates it into the channel's actual reply format.

    Attributes:
        text:       The reply text to send to the customer.

        escalated:  True if this conversation was handed off to a human.
                    The adapter uses this to stop auto-replying further
                    (we don't want the bot and a human both replying).

        tool_used:  Name of the tool that was called to generate this
                    response, if any. Useful for logging/debugging.
                    e.g. "get_order_status", "initiate_refund", None
    """
    text: str
    escalated: bool = False
    tool_used: Optional[str] = None


@dataclass
class ToolCallLog:
    """
    Audit trail entry — every tool call the agent makes gets recorded.

    This is what lets us show clients:
    "Here is every action the agent took, when, and what it decided."
    That audit trail is a genuine production-grade selling point.

    Attributes:
        user_id:         Who triggered this tool call.
        channel:         Which channel they came from.
        tool_name:       Which tool was called (e.g. "get_order_status").
        arguments:       What arguments were passed to the tool.
        result_summary:  Short summary of what the tool returned.
        timestamp:       When the tool was called (UTC).
    """
    user_id: str
    channel: str
    tool_name: str
    arguments: dict
    result_summary: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class OrderSummary:
    """
    A clean, simplified view of a Shopify order.

    The Shopify API returns massive JSON with 100+ fields.
    We extract only what the agent actually needs and store
    it here — nothing else leaks into the agent layer.

    Attributes:
        order_id:           Shopify's internal numeric ID.
        order_number:       Human-readable number e.g. "#1001".
        status:             Financial status e.g. "paid", "refunded".
        fulfillment_status: Shipping status e.g. "fulfilled", None (unfulfilled).
        total_price:        Order total as a float.
        currency:           Currency code e.g. "USD".
        line_items:         List of product names in the order.
        created_at:         When the order was placed.
        customer_email:     Customer's email if available.
    """
    order_id: int
    order_number: str
    status: str
    fulfillment_status: Optional[str]
    total_price: float
    currency: str
    line_items: list[str]
    created_at: datetime
    customer_email: Optional[str] = None

logger.debug("core.models loaded successfully")