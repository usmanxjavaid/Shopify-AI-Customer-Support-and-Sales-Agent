"""
tests/test_guardrails.py
--------------------------
Automated tests for core/guardrails.py refund eligibility rules.

These are pure logic tests — no API calls, no network, no credentials
needed. Safe to run in CI on every push.

Run with:
    pytest tests/test_guardrails.py -v
"""

from datetime import datetime, timezone, timedelta

from core.guardrails import check_refund_eligibility


def test_eligible_refund():
    """A recent, small, fulfilled, paid order should be eligible."""
    result = check_refund_eligibility(
        order_total=49.99,
        order_fulfilled_at=datetime.now(timezone.utc) - timedelta(days=5),
        fulfillment_status="fulfilled",
        financial_status="paid",
    )
    assert result.eligible is True


def test_refund_blocked_too_old():
    """An order fulfilled more than the policy window ago should be blocked."""
    result = check_refund_eligibility(
        order_total=49.99,
        order_fulfilled_at=datetime.now(timezone.utc) - timedelta(days=45),
        fulfillment_status="fulfilled",
        financial_status="paid",
    )
    assert result.eligible is False
    assert "return window" in result.reason


def test_refund_blocked_too_expensive():
    """An order above the auto-approve amount limit should be blocked."""
    result = check_refund_eligibility(
        order_total=2664.85,
        order_fulfilled_at=datetime.now(timezone.utc) - timedelta(days=5),
        fulfillment_status="fulfilled",
        financial_status="paid",
    )
    assert result.eligible is False
    assert "exceeds the auto-refund limit" in result.reason


def test_refund_blocked_not_fulfilled():
    """An unfulfilled order should never be auto-refunded."""
    result = check_refund_eligibility(
        order_total=49.99,
        order_fulfilled_at=None,
        fulfillment_status=None,
        financial_status="paid",
    )
    assert result.eligible is False


def test_refund_blocked_not_paid():
    """An order that isn't paid (e.g. already refunded) should be blocked."""
    result = check_refund_eligibility(
        order_total=49.99,
        order_fulfilled_at=datetime.now(timezone.utc) - timedelta(days=5),
        fulfillment_status="fulfilled",
        financial_status="refunded",
    )
    assert result.eligible is False
    assert "not 'paid'" in result.reason


def test_refund_boundary_exact_day_limit():
    """An order exactly at the day limit should still be eligible."""
    result = check_refund_eligibility(
        order_total=49.99,
        order_fulfilled_at=datetime.now(timezone.utc) - timedelta(days=30),
        fulfillment_status="fulfilled",
        financial_status="paid",
    )
    assert result.eligible is True


def test_refund_boundary_exact_amount_limit():
    """An order exactly at the amount limit should still be eligible."""
    result = check_refund_eligibility(
        order_total=100.00,
        order_fulfilled_at=datetime.now(timezone.utc) - timedelta(days=5),
        fulfillment_status="fulfilled",
        financial_status="paid",
    )
    assert result.eligible is True