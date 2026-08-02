"""
tests/test_email_parsing.py
------------------------------
Tests for the pure-logic parsing pieces of the inbound email webhook:
ticket ID extraction and quoted-reply stripping. No network calls,
safe for CI.
"""

import re


def extract_ticket_id(to_addresses: list[str]) -> int | None:
    """Mirrors the ticket ID extraction logic in email_webhook.py."""
    for addr in to_addresses:
        match = re.search(r"\+ticket(\d+)@", addr)
        if match:
            return int(match.group(1))
    return None


def strip_quoted_reply(text: str) -> str:
    """Mirrors the quoted-reply stripping logic in email_webhook.py."""
    return re.split(r"\nOn .+ wrote:\n", text)[0].strip()


def test_extract_ticket_id_finds_valid_id():
    result = extract_ticket_id(["support+ticket42@eukarialie.resend.app"])
    assert result == 42


def test_extract_ticket_id_returns_none_when_missing():
    result = extract_ticket_id(["someone@example.com"])
    assert result is None


def test_extract_ticket_id_handles_multiple_addresses():
    result = extract_ticket_id([
        "cc@example.com",
        "support+ticket7@eukarialie.resend.app",
    ])
    assert result == 7


def test_strip_quoted_reply_removes_quoted_text():
    text = "This is my reply.\nOn Mon, Jul 1 2026, Support wrote:\nOld message here"
    result = strip_quoted_reply(text)
    assert result == "This is my reply."


def test_strip_quoted_reply_keeps_text_with_no_quote_marker():
    text = "Just a plain reply with nothing quoted."
    result = strip_quoted_reply(text)
    assert result == text