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
