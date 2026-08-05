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


# def _send_text_message(to: str, text: str) -> None:
#     """Sends a plain text WhatsApp message via the Meta Cloud API."""
#     url = f"{GRAPH_API_BASE}/{settings.META_WHATSAPP_PHONE_NUMBER_ID}/messages"
#     headers = {"Authorization": f"Bearer {settings.META_WHATSAPP_ACCESS_TOKEN}"}
#     payload = {
#         "messaging_product": "whatsapp",
#         "to": to,
#         "type": "text",
#         "text": {"body": text},
#     }
#     try:
#         response = requests.post(url, headers=headers, json=payload, timeout=15)
#         response.raise_for_status()
#         logger.info(f"WhatsApp text sent to {to}")
#     except requests.exceptions.RequestException as e:
#         logger.error(f"Failed to send WhatsApp message to {to}: {e}")

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
            "body": text,
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


# def _send_voice_message(to: str, audio_bytes: bytes) -> None:
#     """
#     Sends a voice reply via WhatsApp. WhatsApp requires media to be
#     uploaded first (getting a media ID), then referenced in a message.
#     """
#     upload_url = f"{GRAPH_API_BASE}/{settings.META_WHATSAPP_PHONE_NUMBER_ID}/media"
#     headers = {"Authorization": f"Bearer {settings.META_WHATSAPP_ACCESS_TOKEN}"}

#     try:
#         files = {"file": ("reply.ogg", audio_bytes, "audio/ogg")}
#         data = {"messaging_product": "whatsapp", "type": "audio/ogg"}
#         upload_response = requests.post(upload_url, headers=headers, files=files, data=data, timeout=30)
#         upload_response.raise_for_status()
#         media_id = upload_response.json()["id"]

#         send_url = f"{GRAPH_API_BASE}/{settings.META_WHATSAPP_PHONE_NUMBER_ID}/messages"
#         payload = {
#             "messaging_product": "whatsapp",
#             "to": to,
#             "type": "audio",
#             "audio": {"id": media_id},
#         }
#         send_response = requests.post(send_url, headers=headers, json=payload, timeout=15)
#         send_response.raise_for_status()
#         logger.info(f"WhatsApp voice reply sent to {to}")

#     except requests.exceptions.RequestException as e:
#         logger.error(f"Failed to send WhatsApp voice message to {to}: {e}")

def _send_voice_message(to: str, audio_bytes: bytes) -> None:
    """
    Uploads an audio file to WhatsApp and sends it as a voice message.
    """

    upload_url = f"{GRAPH_API_BASE}/{settings.META_WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {
        "Authorization": f"Bearer {settings.META_WHATSAPP_ACCESS_TOKEN}"
    }

    try:
        # Step 1: Upload the audio
        files = {
            "file": ("reply.ogg", audio_bytes, "audio/ogg")
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


# @router.post("/webhooks/whatsapp")
# async def whatsapp_webhook(request: Request):
#     """
#     Receives incoming WhatsApp messages (text or voice) and runs them
#     through the full agent pipeline, same as every other channel.
#     """
#     payload = await request.json()

#     try:
#         entry = payload["entry"][0]
#         changes = entry["changes"][0]
#         value = changes["value"]

#         if "messages" not in value:
#             # Could be a status update (delivered/read receipt) — ignore
#             return {"ok": True}

#         message = value["messages"][0]
#         from_number = message["from"]
#         message_type = message["type"]

#         if message_type == "text":
#             text = message["text"]["body"]

#         elif message_type == "audio":
#             media_id = message["audio"]["id"]
#             audio_bytes = _download_whatsapp_media(media_id)
#             text = await transcribe_audio_bytes(audio_bytes, filename="voice.ogg")

#             if not text:
#                 _send_text_message(from_number, "Sorry, I couldn't understand that voice message.")
#                 return {"ok": True}

#         else:
#             _send_text_message(from_number, "Sorry, I can only understand text and voice messages right now.")
#             return {"ok": True}

#         logger.info(f"Received WhatsApp message from {from_number}: {text}")

#         msg = NormalizedMessage(user_id=from_number, channel="whatsapp", text=text)
#         response = handle_message(msg)

#         if message_type == "audio":
#             audio_reply = await synthesize_speech(response.text)
#             if audio_reply:
#                 _send_voice_message(from_number, audio_reply)
#             else:
#                 _send_text_message(from_number, response.text)
#         else:
#             _send_text_message(from_number, response.text)

#     except (KeyError, IndexError) as e:
#         logger.warning(f"Unrecognized WhatsApp webhook payload shape: {e}")

#     return {"ok": True}


# logger.debug("adapters.whatsapp_adapter loaded successfully")

import json
import traceback

@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request):
    logger.info("=" * 80)
    logger.info("WHATSAPP WEBHOOK HIT")

    try:
        body = await request.body()
        logger.info(f"Raw Body: {body.decode('utf-8')}")

        payload = json.loads(body)

        logger.info("Parsed JSON:")
        logger.info(json.dumps(payload, indent=2))

        entry = payload["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        logger.info(f"Webhook Value: {value}")

        if "messages" not in value:
            logger.info("No messages field (probably status update).")
            return {"ok": True}

        message = value["messages"][0]

        logger.info(f"Message Object: {message}")

        from_number = message["from"]
        message_type = message["type"]

        logger.info(f"Sender: {from_number}")
        logger.info(f"Message Type: {message_type}")

        if message_type == "text":
            text = message["text"]["body"]

        elif message_type == "audio":
            media_id = message["audio"]["id"]
            logger.info(f"Audio Media ID: {media_id}")

            audio_bytes = _download_whatsapp_media(media_id)
            text = await transcribe_audio_bytes(audio_bytes, filename="voice.ogg")

            if not text:
                _send_text_message(
                    from_number,
                    "Sorry, I couldn't understand that voice message."
                )
                return {"ok": True}

        else:
            logger.warning(f"Unsupported message type: {message_type}")
            _send_text_message(
                from_number,
                "Unsupported message type."
            )
            return {"ok": True}

        logger.info(f"Received Text: {text}")

        msg = NormalizedMessage(
            user_id=from_number,
            channel="whatsapp",
            text=text,
        )

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

        logger.info("Webhook processing completed successfully.")

    except Exception:
        logger.error("EXCEPTION INSIDE WEBHOOK")
        logger.error(traceback.format_exc())

    logger.info("=" * 80)

    return {"ok": True}