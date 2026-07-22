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