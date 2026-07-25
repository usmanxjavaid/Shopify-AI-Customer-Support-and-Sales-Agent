"""
adapters/web_adapter.py
-------------------------
Web widget frontend for the AI support agent.

Exposes a simple REST endpoint the chat widget calls. This is the
ONLY file that knows about HTTP request/response shapes for the
web channel — everything else is shared with Telegram unchanged.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from fastapi import UploadFile, File
from fastapi.responses import StreamingResponse
import io
from integrations.voice_service import transcribe_audio_bytes, synthesize_speech
from core.models import NormalizedMessage
from core.orchestrator import handle_message
from logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    """Shape of incoming requests from the widget."""
    session_id: str
    text: str


class ChatResponse(BaseModel):
    """Shape of responses sent back to the widget."""
    reply: str
    escalated: bool


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Handles a single chat message from the web widget.

    Args:
        request: Contains session_id (identifies this browser's
                 conversation) and the message text.

    Returns:
        ChatResponse with the agent's reply and escalation status.
    """
    logger.info(f"Received web message from session {request.session_id}")

    msg = NormalizedMessage(
        user_id=request.session_id,
        channel="web",
        text=request.text,
    )

    response = handle_message(msg)

    logger.info(
        f"Sending web reply to {request.session_id} | "
        f"escalated={response.escalated}"
    )

    return ChatResponse(reply=response.text, escalated=response.escalated)

@router.post("/api/chat/voice")
async def chat_voice(session_id: str, audio: UploadFile = File(...)):
    """
    Handles a voice message from the web widget.

    Accepts an audio file upload, transcribes it, runs it through
    the agent, and returns BOTH the text reply (as a header) and
    the synthesized voice reply (as the response body audio stream).

    Args:
        session_id: The browser session's conversation ID.
        audio:      The recorded audio file (webm/ogg from the browser).

    Returns:
        Streaming WAV audio response, with the reply text in the
        X-Reply-Text header (base64-encoded to safely support any
        language/characters in an HTTP header).
    """
    import base64

    audio_bytes = await audio.read()
    logger.info(f"Received web voice message from session {session_id}")

    text = await transcribe_audio_bytes(audio_bytes, filename="voice.webm")

    if not text:
        return {"error": "Could not transcribe audio"}

    msg = NormalizedMessage(user_id=session_id, channel="web", text=text)
    response = handle_message(msg)

    audio_reply = await synthesize_speech(response.text)

    encoded_text = base64.b64encode(response.text.encode("utf-8")).decode("ascii")

    return StreamingResponse(
        io.BytesIO(audio_reply),
        media_type="audio/wav",
        headers={
            "X-Reply-Text": encoded_text,
            "X-Escalated": str(response.escalated),
        },
    )