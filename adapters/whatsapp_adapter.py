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
from fastapi import BackgroundTasks
from config import settings
from core.models import NormalizedMessage
from core.orchestrator import handle_message
from integrations.voice_service import transcribe_audio_bytes, synthesize_speech, convert_wav_to_ogg_opus
from logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"

import re

def _convert_to_whatsapp_markdown(text: str) -> str:
    """
    Converts standard **bold** markdown (used by our system prompt,
    which Telegram and the web widget both render correctly) into
    WhatsApp's own single-asterisk bold syntax.
    """
    return re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)

def _send_text_message(to: str, text: str) -> None:
    """Sends a plain text WhatsApp message via the Meta Cloud API."""

    url = f"{GRAPH_API_BASE}/{settings.META_WHATSAPP_PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {settings.META_WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": _convert_to_whatsapp_markdown(text),
        },
    }

    logger.info(f"Phone Number ID = {settings.META_WHATSAPP_PHONE_NUMBER_ID}")
    logger.info(f"Sending reply to = {to}")
    logger.info(f"Payload = {payload}")

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=15,
        )

        logger.info(f"Meta Status Code: {response.status_code}")
        logger.info(f"Meta Response: {response.text}")

        response.raise_for_status()

        logger.info("WhatsApp message sent successfully.")

    except requests.exceptions.RequestException as e:
        logger.error(f"Meta Exception: {e}")

        if e.response is not None:
            logger.error(f"Meta Error Body: {e.response.text}")

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


def _send_voice_message(to: str, wav_audio_bytes: bytes) -> None:
    """
    Uploads an audio file to WhatsApp and sends it as a voice message.

    WhatsApp strictly validates that the file content actually matches
    the declared mimetype (audio/ogg codecs=opus) — our TTS produces
    WAV, so we must genuinely convert it, not just relabel it.
    """
    audio_bytes = convert_wav_to_ogg_opus(wav_audio_bytes)

    if not audio_bytes:
        logger.error("WAV to OGG/Opus conversion failed, cannot send WhatsApp voice reply")
        return

    upload_url = f"{GRAPH_API_BASE}/{settings.META_WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {
        "Authorization": f"Bearer {settings.META_WHATSAPP_ACCESS_TOKEN}"
    }

    try:
        # Step 1: Upload the audio
        files = {
            "file": ("reply.ogg", audio_bytes, "audio/ogg; codecs=opus")
        }

        data = {
            "messaging_product": "whatsapp",
            "type": "audio/ogg"
        }

        upload_response = requests.post(
            upload_url,
            headers=headers,
            files=files,
            data=data,
            timeout=30,
        )

        logger.info(f"Upload Status: {upload_response.status_code}")
        logger.info(f"Upload Response: {upload_response.text}")

        upload_response.raise_for_status()

        media_id = upload_response.json()["id"]

        # Step 2: Send the uploaded media
        send_url = f"{GRAPH_API_BASE}/{settings.META_WHATSAPP_PHONE_NUMBER_ID}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "audio",
            "audio": {
                "id": media_id
            }
        }

        send_response = requests.post(
            send_url,
            headers=headers,
            json=payload,
            timeout=15,
        )

        logger.info(f"Send Status: {send_response.status_code}")
        logger.info(f"Send Response: {send_response.text}")

        send_response.raise_for_status()

        logger.info(f"WhatsApp voice message sent successfully to {to}")

    except requests.exceptions.HTTPError:
        logger.error(f"HTTP Error: {send_response.status_code if 'send_response' in locals() else upload_response.status_code}")
        logger.error(send_response.text if 'send_response' in locals() else upload_response.text)

    except Exception as e:
        logger.exception(f"Failed to send WhatsApp voice message: {e}")

_processed_message_ids = set()

import time

_recent_texts = {}  # (sender, text) -> timestamp
_RECENT_TEXT_WINDOW_SECONDS = 120

def _is_recent_duplicate_content(sender: str, text: str) -> bool:
    """
    Catches the case where the SAME person sends the SAME question
    again within a short window — usually because they didn't see a
    reply in time and resent it themselves, not because anything is
    wrong. This is a heuristic, not perfect: an intentional repeat
    question within 2 minutes would also get silently skipped, but
    that's an acceptable tradeoff to stop redundant processing.
    """
    key = (sender, text.strip().lower())
    now = time.time()

    last_seen = _recent_texts.get(key)
    _recent_texts[key] = now

    if len(_recent_texts) > 500:
        _recent_texts.clear()

    if last_seen and (now - last_seen) < _RECENT_TEXT_WINDOW_SECONDS:
        return True
    return False

def _already_processed(message_id: str) -> bool:
    """
    WhatsApp can redeliver the same webhook event on retry. This
    guards against processing (and replying to) the same inbound
    message twice.
    """
    if message_id in _processed_message_ids:
        return True
    _processed_message_ids.add(message_id)
    if len(_processed_message_ids) > 1000:
        _processed_message_ids.clear()
    return False

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

import json
import traceback

@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Acknowledges Meta's webhook IMMEDIATELY (before any slow work),
    then processes the actual message in the background. This is
    required because Meta retries webhook delivery if it doesn't
    get a fast 200 response — and voice processing (transcribe +
    LLM + TTS + conversion + upload) can easily take 10-20+ seconds,
    well past Meta's timeout, causing duplicate replies otherwise.
    """
    body = await request.body()

    try:
        payload = json.loads(body)
        entry = payload["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            return {"ok": True}

        message = value["messages"][0]
        message_id = message.get("id")

        if message_id and _already_processed(message_id):
            logger.info(f"Skipping duplicate message {message_id}")
            return {"ok": True}

        # Hand off the actual work to run AFTER we respond to Meta
        background_tasks.add_task(_process_whatsapp_message, message)

    except (KeyError, IndexError) as e:
        logger.warning(f"Unrecognized WhatsApp webhook payload shape: {e}")

    return {"ok": True}


async def _process_whatsapp_message(message: dict) -> None:
    """
    Does the actual slow work: transcription, agent processing,
    and sending the reply. Runs as a background task, AFTER we've
    already told Meta the webhook was received successfully.
    """
    logger.info("=" * 80)
    logger.info("Processing WhatsApp message in background")

    try:
        from_number = message["from"]
        message_type = message["type"]

        logger.info(f"Sender: {from_number}")
        logger.info(f"Message Type: {message_type}")

        if message_type == "text":
            text = message["text"]["body"]

        elif message_type == "audio":
            media_id = message["audio"]["id"]
            audio_bytes = _download_whatsapp_media(media_id)
            text = await transcribe_audio_bytes(audio_bytes, filename="voice.ogg")

            if not text:
                _send_text_message(from_number, "Sorry, I couldn't understand that voice message.")
                return

        else:
            _send_text_message(from_number, "Sorry, I can only understand text and voice messages right now.")
            return

        logger.info(f"Received Text: {text}")

        if _is_recent_duplicate_content(from_number, text):
            logger.info(f"Skipping likely accidental resend from {from_number}: {text}")
            return

        msg = NormalizedMessage(user_id=from_number, channel="whatsapp", text=text)
        response = handle_message(msg)

        logger.info(f"AI Reply: {response.text}")

        if message_type == "audio":
            audio_reply = await synthesize_speech(response.text)
            if audio_reply:
                _send_voice_message(from_number, audio_reply)
            else:
                _send_text_message(from_number, response.text)
        else:
            _send_text_message(from_number, response.text)

        logger.info("Background processing completed successfully.")

    except Exception:
        logger.error("EXCEPTION IN BACKGROUND PROCESSING")
        logger.error(traceback.format_exc())

    logger.info("=" * 80)