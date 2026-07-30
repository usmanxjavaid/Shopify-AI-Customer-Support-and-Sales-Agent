"""
tests/test_guardrails.py
--------------------------
Automated tests for core/guardrails.py refund path logic.

These are pure logic tests — no API calls, no network, no credentials
needed. Safe to run in CI on every push.

Covers determine_refund_path(), which decides one of:
    AUTO_REFUND        - order hasn't shipped, safe to refund directly
    REQUIRES_RETURN     - order has been fulfilled, needs a physical
                          return confirmed by a human before refunding
    NOT_ELIGIBLE        - outside the policy window or amount limit
    NOT_PAID            - order isn't in a paid state
    ALREADY_REFUNDED    - order was already refunded

Run with:
    pytest tests/test_guardrails.py -v
"""

from datetime import datetime, timezone, timedelta

from core.guardrails import determine_refund_path, RefundPath


def test_unfulfilled_order_auto_refunds():
    """An order that hasn't shipped should be refunded directly."""
    path, reason = determine_refund_path(
        order_total=49.99,
        order_fulfilled_at=None,
        fulfillment_status=None,
        financial_status="paid",
        tracking_number=None,
    )
    assert path == RefundPath.AUTO_REFUND


def test_fulfilled_order_requires_return():
    """A fulfilled order within policy limits should require a return,
    never be auto-refunded directly."""
    path, reason = determine_refund_path(
        order_total=49.99,
        order_fulfilled_at=datetime.now(timezone.utc) - timedelta(days=5),
        fulfillment_status="fulfilled",
        financial_status="paid",
        tracking_number=None,
    )
    assert path == RefundPath.REQUIRES_RETURN


def test_fulfilled_order_with_tracking_still_requires_return():
    """Presence of a tracking number shouldn't change the outcome —
    any fulfilled order requires a human-confirmed return."""
    path, reason = determine_refund_path(
        order_total=49.99,
        order_fulfilled_at=datetime.now(timezone.utc) - timedelta(days=5),
        fulfillment_status="fulfilled",
        financial_status="paid",
        tracking_number="1Z999AA10123456784",
    )
    assert path == RefundPath.REQUIRES_RETURN


def test_fulfilled_order_too_old_not_eligible():
    """A fulfilled order outside the return window should be blocked
    before ever reaching the return path."""
    path, reason = determine_refund_path(
        order_total=49.99,
        order_fulfilled_at=datetime.now(timezone.utc) - timedelta(days=45),
        fulfillment_status="fulfilled",
        financial_status="paid",
        tracking_number=None,
    )
    assert path == RefundPath.NOT_ELIGIBLE
    assert "return window" in reason


def test_fulfilled_order_too_expensive_not_eligible():
    """A fulfilled order above the auto-return amount limit should
    be blocked, requiring manual review."""
    path, reason = determine_refund_path(
        order_total=2664.85,
        order_fulfilled_at=datetime.now(timezone.utc) - timedelta(days=5),
        fulfillment_status="fulfilled",
        financial_status="paid",
        tracking_number=None,
    )
    assert path == RefundPath.NOT_ELIGIBLE
    assert "exceeds" in reason


def test_unpaid_order_not_eligible():
    """An order that isn't paid should never be refunded."""
    path, reason = determine_refund_path(
        order_total=49.99,
        order_fulfilled_at=None,
        fulfillment_status=None,
        financial_status="pending",
        tracking_number=None,
    )
    assert path == RefundPath.NOT_PAID


def test_already_refunded_order_blocked():
    """An order that's already been refunded should be blocked from
    a duplicate refund."""
    path, reason = determine_refund_path(
        order_total=49.99,
        order_fulfilled_at=datetime.now(timezone.utc) - timedelta(days=5),
        fulfillment_status="fulfilled",
        financial_status="refunded",
        tracking_number=None,
    )
    assert path == RefundPath.ALREADY_REFUNDED


def test_boundary_exact_day_limit_still_eligible():
    """An order exactly at the day limit should still qualify for
    the return path, not be blocked."""
    path, reason = determine_refund_path(
        order_total=49.99,
        order_fulfilled_at=datetime.now(timezone.utc) - timedelta(days=30),
        fulfillment_status="fulfilled",
        financial_status="paid",
        tracking_number=None,
    )
    assert path == RefundPath.REQUIRES_RETURN


def test_boundary_exact_amount_limit_still_eligible():
    """An order exactly at the amount limit should still qualify for
    the return path, not be blocked."""
    path, reason = determine_refund_path(
        order_total=100.00,
        order_fulfilled_at=datetime.now(timezone.utc) - timedelta(days=5),
        fulfillment_status="fulfilled",
        financial_status="paid",
        tracking_number=None,
    )
    assert path == RefundPath.REQUIRES_RETURN