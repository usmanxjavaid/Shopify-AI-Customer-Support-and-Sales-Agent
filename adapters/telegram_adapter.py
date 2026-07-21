"""
adapters/telegram_adapter.py
------------------------------
Telegram frontend for the AI support agent.

This is the ONLY file that knows Telegram's message format. It:
    1. Receives raw Telegram updates
    2. Converts them into NormalizedMessage
    3. Passes to core.orchestrator.handle_message()
    4. Sends the AgentResponse back through Telegram

Run this file directly to start the bot:
    python -m adapters.telegram_adapter
"""

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    filters,
    ContextTypes,
)

import requests
from telegram import Voice
from config import settings
from core.models import NormalizedMessage
from telegram.ext import MessageHandler, filters, CommandHandler
from core.orchestrator import handle_message
from persistence.db import init_db
from logger import get_logger

logger = get_logger(__name__)

async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the /start command — Telegram's standard first message
    when a user opens a bot for the first time.

    Args:
        update:  Telegram's update object.
        context: Telegram bot context (unused here).
    """
    user_id = str(update.effective_chat.id)
    logger.info(f"New conversation started by {user_id}")

    welcome_message = (
        "👋 Hi! I'm Velvora's support assistant.\n\n"
        "I can help you with:\n"
        "• Order status and tracking\n"
        "• Product info and pricing\n"
        "• Refund requests\n\n"
        "Just tell me what you need!"
    )

    await update.message.reply_text(welcome_message)

async def transcribe_voice(voice: Voice, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Downloads a Telegram voice message and transcribes it to text
    using Groq's Whisper API.

    Args:
        voice:   Telegram's Voice object from the incoming message.
        context: Telegram bot context, used to download the file.

    Returns:
        Transcribed text, or an empty string if transcription failed.
    """
    logger.info("Transcribing voice message")

    try:
        # Download the voice file from Telegram's servers
        file = await context.bot.get_file(voice.file_id)
        audio_bytes = await file.download_as_bytearray()

        # Send raw .ogg bytes directly to Groq's Whisper endpoint
        response = requests.post(
            url="https://api.groq.com/openai/v1/audio/transcriptions",
            headers={
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            },
            files={
                "file": ("voice.ogg", bytes(audio_bytes), "audio/ogg"),
            },
            data={
                "model": "whisper-large-v3",
            },
            timeout=30,
        )
        response.raise_for_status()

        text = response.json().get("text", "").strip()
        logger.info(f"Transcription result: {text}")
        return text

    except requests.exceptions.RequestException as e:
        logger.error(f"Voice transcription failed: {e}")
        return ""
    
async def synthesize_speech(text: str) -> bytes:
    """
    Converts text to speech audio using Google AI Studio's TTS API.

    Gemini's TTS returns raw PCM audio (16-bit, 24kHz, mono).
    We wrap it in a proper WAV container so it's valid, playable
    audio — raw PCM alone isn't a real file format players understand.

    Args:
        text: The text to convert to speech.

    Returns:
        WAV-formatted audio bytes, or empty bytes if synthesis failed.
    """
    logger.info("Synthesizing speech for reply")

    try:
        response = requests.post(
            url=(
                "https://generativelanguage.googleapis.com/v1beta/"
                "models/gemini-2.5-flash-preview-tts:generateContent"
                f"?key={settings.GOOGLE_AI_API_KEY}"
            ),
            json={
                "contents": [{"parts": [{"text": text}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {"voiceName": "Kore"}
                        }
                    },
                },
            },
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        audio_b64 = (
            data["candidates"][0]["content"]["parts"][0]
            ["inlineData"]["data"]
        )

        import base64
        pcm_bytes = base64.b64decode(audio_b64)

        # Wrap raw PCM into a proper WAV container
        import io
        import wave

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)        # mono
            wav_file.setsampwidth(2)        # 16-bit
            wav_file.setframerate(24000)    # 24kHz, Gemini's output rate
            wav_file.writeframes(pcm_bytes)

        wav_bytes = wav_buffer.getvalue()
        logger.info("Speech synthesis succeeded (converted to WAV)")
        return wav_bytes

    except Exception as e:
        logger.error(f"Speech synthesis failed: {e}")
        return b""

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles every incoming text message from Telegram.

    Args:
        update:  Telegram's update object containing the message.
        context: Telegram bot context (unused here, required by the API).
    """
    user_id = str(update.effective_chat.id)
    text = update.message.text

    logger.info(f"Received Telegram message from {user_id}: {text}")

    # Convert to our normalized format
    msg = NormalizedMessage(
        user_id=user_id,
        channel="telegram",
        text=text,
    )

    # Show "typing..." while the agent processes
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    # Run the full agent pipeline
    response = handle_message(msg)

    logger.info(
        f"Sending reply to {user_id} | escalated={response.escalated}"
    )

    await update.message.reply_text(response.text)

async def on_voice_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handles incoming voice messages — transcribes then processes
    exactly like a normal text message.

    Args:
        update:  Telegram's update object containing the voice message.
        context: Telegram bot context.
    """
    user_id = str(update.effective_chat.id)
    logger.info(f"Received voice message from {user_id}")

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    text = await transcribe_voice(update.message.voice, context)

    if not text:
        await update.message.reply_text(
            "Sorry, I couldn't understand that voice message. "
            "Could you try again or type your message instead?"
        )
        return

    logger.info(f"Transcribed text: {text}")

    msg = NormalizedMessage(
        user_id=user_id,
        channel="telegram",
        text=text,
    )

    response = handle_message(msg)

    # Customer used voice -> reply with voice only, not text
    audio_bytes = await synthesize_speech(response.text)

    if audio_bytes:
        import io
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "reply.mp3"
        await update.message.reply_audio(audio=audio_file)
    else:
        # If TTS fails for any reason, fall back to text so the
        # customer still gets an answer
        logger.warning("Voice synthesis failed — falling back to text reply")
        await update.message.reply_text(response.text)
        
def run() -> None:
    """
    Starts the Telegram bot in polling mode.

    Polling mode means the bot actively checks Telegram's servers
    for new messages — simplest setup, no public URL/webhook needed.
    Good for development and small-scale production use.
    """
    init_db()
    logger.info("Starting Telegram bot...")

    app = (
        ApplicationBuilder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )
    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(MessageHandler(filters.VOICE, on_voice_message))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_message)
    )

    logger.info("Telegram bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    run()