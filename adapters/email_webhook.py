"""
adapters/email_webhook.py
----------------------------
Receives inbound email replies via Resend, appends them to the
right ticket's thread, and routes the reply to the customer.
"""

import re
import requests
from fastapi import APIRouter, Request

from config import settings
from persistence.queries import get_ticket, add_ticket_message, set_ticket_status, queue_human_reply
from logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/webhooks/resend/inbound")
async def resend_inbound_webhook(request: Request):
    payload = await request.json()

    if payload.get("type") != "email.received":
        return {"ok": True}

    email_data = payload.get("data", {})
    to_addresses = email_data.get("to", [])
    email_id = email_data.get("email_id")

    ticket_id = None
    for addr in to_addresses:
        match = re.search(r"\+ticket(\d+)@", addr)
        if match:
            ticket_id = int(match.group(1))
            break

    if not ticket_id:
        logger.warning(f"Inbound email has no ticket ID: {to_addresses}")
        return {"ok": True}

    try:
        response = requests.get(
            f"https://api.resend.com/emails/{email_id}",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            timeout=10,
        )
        response.raise_for_status()
        reply_text = response.json().get("text", "").strip()
    except Exception as e:
        logger.error(f"Failed to fetch inbound email body: {e}")
        return {"ok": True}

    reply_text = re.split(r"\nOn .+ wrote:\n", reply_text)[0].strip()
    if not reply_text:
        return {"ok": True}

    ticket = get_ticket(ticket_id)
    if not ticket:
        logger.warning(f"No ticket found for #{ticket_id}")
        return {"ok": True}

    add_ticket_message(ticket_id, "agent", reply_text)

    channel = ticket["channel"]
    user_id = ticket["user_id"]

    if channel == "telegram":
        requests.post(
            f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": user_id, "text": f"[Support Team] {reply_text}"},
            timeout=10,
        )
    elif ticket.get("customer_email"):
        requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": "Velvora Support <onboarding@resend.dev>",
                "to": [ticket["customer_email"]],
                "subject": f"Re: Ticket #{ticket_id}",
                "text": reply_text,
            },
            timeout=10,
        )
        queue_human_reply(channel, user_id, reply_text)
    else:
        queue_human_reply(channel, user_id, reply_text)

    set_ticket_status(ticket_id, "pending")  # waiting on customer now
    logger.info(f"Routed reply for ticket #{ticket_id}")

    return {"ok": True}