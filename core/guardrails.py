"""
core/guardrails.py
------------------
Business rules enforced in plain Python code — no AI involved.

This is the most important safety layer in the entire project.

Why this exists:
    The LLM is great at understanding language and deciding WHAT to do,
    but it should never have unchecked authority over real actions like
    issuing refunds or cancelling orders.

    This file is the final gatekeeper. Before any "action" tool runs
    (refund, cancellation), it must pass through here first.
    If the rules say no → the action is blocked, regardless of what
    the LLM decided.

Escalation decisions:
    Escalation is handled by the LLM itself via intent detection —
    not by keyword matching here. The LLM detects frustration, legal
    threats, and human-agent requests from context and natural language,
    which is far more accurate than hardcoded keywords.

Key principle:
    These rules are deterministic and testable. A refund either is or
    isn't within the 30-day window — no ambiguity, no LLM judgment needed.
    This makes the system auditable and explainable to clients.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from enum import Enum
from config import settings
from logger import get_logger

logger = get_logger(__name__)


# ------------------------------------------------------------------
# Result shape
# ------------------------------------------------------------------

@dataclass
class EligibilityResult:
    """
    Result of a refund eligibility check.

    Attributes:
        eligible: True if the refund can be auto-processed.
        reason:   Human-readable explanation of why eligible or not.
                  This gets passed back to the LLM so it can explain
                  the decision to the customer in natural language.
    """
    eligible: bool
    reason: str


# ------------------------------------------------------------------
# Refund eligibility rules
# ------------------------------------------------------------------


class RefundPath(Enum):
    """The specific automated path a refund request should take."""
    NOT_PAID = "not_paid"
    ALREADY_REFUNDED = "already_refunded"
    AUTO_REFUND = "auto_refund"                # not fulfilled — refund now
    CANCEL_AND_REFUND = "cancel_and_refund"     # fulfilled, not shipped — cancel + refund
    REQUIRES_RETURN = "requires_return"         # shipped — needs physical return first
    NOT_ELIGIBLE = "not_eligible"               # outside policy window/amount


def determine_refund_path(
    order_total: float,
    order_fulfilled_at: Optional[datetime],
    fulfillment_status: Optional[str],
    financial_status: str,
    tracking_number: Optional[str],  # kept in signature for compatibility, unused now
) -> tuple[RefundPath, str]:
    """
    Decides which automated refund path applies.

    Only two real, safely-automatable outcomes exist, based on what
    Shopify's API can actually confirm:

        Unfulfilled  -> AUTO_REFUND (nothing physical to return)
        Fulfilled    -> REQUIRES_RETURN (always — Shopify doesn't
                        reliably expose "shipped but recoverable"
                        as a distinct, cancellable state; a human
                        must confirm any fulfilled order's return)

    This matches Shopify's own guidance: any fulfilled order goes
    through a return process before refunding, regardless of whether
    tracking exists yet.
    """
    if financial_status == "refunded":
        return RefundPath.ALREADY_REFUNDED, "This order has already been refunded."

    if financial_status != "paid":
        return RefundPath.NOT_PAID, f"Order financial status is '{financial_status}', not 'paid'."

    now = datetime.now(timezone.utc)

    if fulfillment_status not in ("fulfilled", "partial"):
        return RefundPath.AUTO_REFUND, "Order has not shipped — refunding directly."

    if order_fulfilled_at:
        if order_fulfilled_at.tzinfo is None:
            order_fulfilled_at = order_fulfilled_at.replace(tzinfo=timezone.utc)
        days_since = (now - order_fulfilled_at).days

        if days_since > settings.REFUND_MAX_DAYS:
            return RefundPath.NOT_ELIGIBLE, (
                f"Order was fulfilled {days_since} days ago, exceeding "
                f"the {settings.REFUND_MAX_DAYS}-day return window."
            )

    if order_total > settings.REFUND_MAX_AMOUNT:
        return RefundPath.NOT_ELIGIBLE, (
            f"Order total ({order_total:.2f}) exceeds the auto-return "
            f"limit of {settings.REFUND_MAX_AMOUNT:.2f}. Requires manual review."
        )

    return RefundPath.REQUIRES_RETURN, (
        "Order has been fulfilled. A physical return is required before "
        "a refund can be issued."
    )