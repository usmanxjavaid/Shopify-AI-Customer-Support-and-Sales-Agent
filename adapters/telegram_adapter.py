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

from config import settings
from core.models import NormalizedMessage
from telegram.ext import CommandHandler
from core.orchestrator import handle_message
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


def run() -> None:
    """
    Starts the Telegram bot in polling mode.

    Polling mode means the bot actively checks Telegram's servers
    for new messages — simplest setup, no public URL/webhook needed.
    Good for development and small-scale production use.
    """
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
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_message)
    )

    logger.info("Telegram bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    run()