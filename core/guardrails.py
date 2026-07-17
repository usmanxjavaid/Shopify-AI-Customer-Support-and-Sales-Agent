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

def check_refund_eligibility(
    order_total: float,
    order_fulfilled_at: Optional[datetime],
    fulfillment_status: Optional[str],
    financial_status: str,
) -> EligibilityResult:
    """
    Checks whether an order qualifies for an automatic refund.

    Rules (configured via .env so clients can customize):
        1. Order must be in "paid" financial status
        2. Order must be fulfilled (we can't refund unfulfilled orders
           automatically — too many edge cases)
        3. Order must be within REFUND_MAX_DAYS of fulfillment date
        4. Order total must be <= REFUND_MAX_AMOUNT

    If ANY rule fails → not eligible → agent must escalate to human.

    Args:
        order_total:        Total order value in store currency.
        order_fulfilled_at: When the order was fulfilled/shipped.
                            None if order hasn't been fulfilled yet.
        fulfillment_status: Shopify fulfillment status string.
        financial_status:   Shopify financial status string.

    Returns:
        EligibilityResult with eligible=True/False and a reason string.
    """
    logger.debug(
        f"Checking refund eligibility | total={order_total} "
        f"fulfillment_status={fulfillment_status} "
        f"financial_status={financial_status}"
    )

    # Rule 1: Must be paid
    if financial_status != "paid":
        reason = (
            f"Order financial status is '{financial_status}', "
            f"not 'paid'. Cannot auto-refund."
        )
        logger.info(f"Refund not eligible: {reason}")
        return EligibilityResult(eligible=False, reason=reason)

    # Rule 2: Must be fulfilled
    if fulfillment_status != "fulfilled":
        reason = (
            f"Order has not been fulfilled yet "
            f"(status: '{fulfillment_status}'). "
            f"Cannot refund an unshipped order automatically."
        )
        logger.info(f"Refund not eligible: {reason}")
        return EligibilityResult(eligible=False, reason=reason)

    # Rule 3: Fulfillment date must be known
    if order_fulfilled_at is None:
        reason = "Order fulfillment date is unknown. Cannot verify return window."
        logger.info(f"Refund not eligible: {reason}")
        return EligibilityResult(eligible=False, reason=reason)

    # Rule 4: Must be within the time window
    now = datetime.now(timezone.utc)

    # Ensure timezone-aware for comparison
    if order_fulfilled_at.tzinfo is None:
        order_fulfilled_at = order_fulfilled_at.replace(tzinfo=timezone.utc)

    days_since_fulfillment = (now - order_fulfilled_at).days

    if days_since_fulfillment > settings.REFUND_MAX_DAYS:
        reason = (
            f"Order was fulfilled {days_since_fulfillment} days ago, "
            f"which exceeds our {settings.REFUND_MAX_DAYS}-day return window."
        )
        logger.info(f"Refund not eligible: {reason}")
        return EligibilityResult(eligible=False, reason=reason)

    # Rule 5: Must be within amount limit
    if order_total > settings.REFUND_MAX_AMOUNT:
        reason = (
            f"Order total ({order_total:.2f}) exceeds the auto-refund "
            f"limit of {settings.REFUND_MAX_AMOUNT:.2f}. "
            f"Requires human approval."
        )
        logger.info(f"Refund not eligible: {reason}")
        return EligibilityResult(eligible=False, reason=reason)

    # All rules passed
    reason = (
        f"Order is within the {settings.REFUND_MAX_DAYS}-day return window "
        f"({days_since_fulfillment} days since fulfillment) and total "
        f"({order_total:.2f}) is within auto-approve limit."
    )
    logger.info(f"Refund eligible: {reason}")
    return EligibilityResult(eligible=True, reason=reason)


logger.debug("core.guardrails loaded successfully")