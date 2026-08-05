"""
adapters/whatsapp_adapter.py
-------------------------------
WhatsApp Business (Meta Cloud API) frontend for the AI support agent.

This is the ONLY file that knows WhatsApp's message format. It:
    1. Verifies Meta's webhook challenge on setup
    2. Receives incoming WhatsApp messages (text + voice)
    3. Converts them into NormalizedMessage
    4. Passes to core.orchestrator.handle_message()
    5. Sends the AgentResponse back through WhatsApp's Send API

Meta webhooks push messages to us — no polling needed, runs inside
the same FastAPI app as the web widget and admin dashboard.
"""

import requests
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from config import settings
from core.models import NormalizedMessage
from core.orchestrator import handle_message
from integrations.voice_service import transcribe_audio_bytes, synthesize_speech
from logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


def _send_text_message(to: str, text: str) -> None:
    """Sends a plain text WhatsApp message via the Meta Cloud API."""
    url = f"{GRAPH_API_BASE}/{settings.META_WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.META_WHATSAPP_ACCESS_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        logger.info(f"WhatsApp text sent to {to}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send WhatsApp message to {to}: {e}")


def _download_whatsapp_media(media_id: str) -> bytes:
    """
    Downloads a media file (voice note) from Meta's servers.

    WhatsApp media works in two steps: first fetch the temporary
    download URL for the media ID, then fetch the actual bytes.
    """
    headers = {"Authorization": f"Bearer {settings.META_WHATSAPP_ACCESS_TOKEN}"}

    url_response = requests.get(f"{GRAPH_API_BASE}/{media_id}", headers=headers, timeout=15)
    url_response.raise_for_status()
    media_url = url_response.json()["url"]

    media_response = requests.get(media_url, headers=headers, timeout=30)
    media_response.raise_for_status()
    return media_response.content


def _send_voice_message(to: str, audio_bytes: bytes) -> None:
    """
    Sends a voice reply via WhatsApp. WhatsApp requires media to be
    uploaded first (getting a media ID), then referenced in a message.
    """
    upload_url = f"{GRAPH_API_BASE}/{settings.META_WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {settings.META_WHATSAPP_ACCESS_TOKEN}"}

    try:
        files = {"file": ("reply.ogg", audio_bytes, "audio/ogg")}
        data = {"messaging_product": "whatsapp", "type": "audio/ogg"}
        upload_response = requests.post(upload_url, headers=headers, files=files, data=data, timeout=30)
        upload_response.raise_for_status()
        media_id = upload_response.json()["id"]

        send_url = f"{GRAPH_API_BASE}/{settings.META_WHATSAPP_PHONE_NUMBER_ID}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "audio",
            "audio": {"id": media_id},
        }
        send_response = requests.post(send_url, headers=headers, json=payload, timeout=15)
        send_response.raise_for_status()
        logger.info(f"WhatsApp voice reply sent to {to}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send WhatsApp voice message to {to}: {e}")


@router.get("/webhooks/whatsapp")
async def verify_whatsapp_webhook(request: Request):
    """
    Meta calls this once when you register the webhook URL, to confirm
    you control this endpoint. Must echo back the challenge value if
    the verify token matches what you configured in Meta's dashboard.
    """
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.META_WEBHOOK_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verified successfully")
        return PlainTextResponse(content=challenge)

    logger.warning("WhatsApp webhook verification failed")
    return PlainTextResponse(content="Verification failed", status_code=403)


@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Receives incoming WhatsApp messages (text or voice) and runs them
    through the full agent pipeline, same as every other channel.
    """
    payload = await request.json()

    try:
        entry = payload["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            # Could be a status update (delivered/read receipt) — ignore
            return {"ok": True}

        message = value["messages"][0]
        from_number = message["from"]
        message_type = message["type"]

        if message_type == "text":
            text = message["text"]["body"]

        elif message_type == "audio":
            media_id = message["audio"]["id"]
            audio_bytes = _download_whatsapp_media(media_id)
            text = await transcribe_audio_bytes(audio_bytes, filename="voice.ogg")

            if not text:
                _send_text_message(from_number, "Sorry, I couldn't understand that voice message.")
                return {"ok": True}

        else:
            _send_text_message(from_number, "Sorry, I can only understand text and voice messages right now.")
            return {"ok": True}

        logger.info(f"Received WhatsApp message from {from_number}: {text}")

        msg = NormalizedMessage(user_id=from_number, channel="whatsapp", text=text)
        response = handle_message(msg)

        if message_type == "audio":
            audio_reply = await synthesize_speech(response.text)
            if audio_reply:
                _send_voice_message(from_number, audio_reply)
            else:
                _send_text_message(from_number, response.text)
        else:
            _send_text_message(from_number, response.text)

    except (KeyError, IndexError) as e:
        logger.warning(f"Unrecognized WhatsApp webhook payload shape: {e}")

    return {"ok": True}


logger.debug("adapters.whatsapp_adapter loaded successfully")