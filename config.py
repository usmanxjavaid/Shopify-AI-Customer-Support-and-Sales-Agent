"""
config.py
---------
Central configuration loader for the entire project.

This is the ONLY file that reads from .env directly.
Every other module imports `settings` from here instead
of calling os.getenv() on their own.

Why: if a variable name changes, we fix it in one place,
not scattered across 10 files.
"""

import os
from dotenv import load_dotenv

# Load the .env file into environment variables
load_dotenv()


class Settings:
    """
    Holds all configuration values for the project.
    Reads from environment variables (set via .env file).
    """

    # --- Shopify ---
    SHOPIFY_STORE_DOMAIN: str = os.getenv("SHOPIFY_STORE_DOMAIN", "")
    SHOPIFY_CLIENT_ID: str = os.getenv("SHOPIFY_CLIENT_ID", "")
    SHOPIFY_CLIENT_SECRET: str = os.getenv("SHOPIFY_CLIENT_SECRET", "")
    SHOPIFY_API_VERSION: str = os.getenv("SHOPIFY_API_VERSION", "2024-10")

    # --- OpenRouter LLM (primary) ---
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")

    # --- Groq LLM (fallback) ---
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # --- Google AI Studio (TTS) ---
    GOOGLE_AI_API_KEY: str = os.getenv("GOOGLE_AI_API_KEY", "")

    # --- Telegram ---
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    OWNER_TELEGRAM_CHAT_ID: str = os.getenv("OWNER_TELEGRAM_CHAT_ID", "")

    # --- Redis (Upstash) — conversation memory ---
    UPSTASH_REDIS_REST_URL: str = os.getenv("UPSTASH_REDIS_REST_URL", "")
    UPSTASH_REDIS_REST_TOKEN: str = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")

    # --- PostgreSQL (Neon) — persistence, audit logs ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # --- Admin Dashboard ---
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")

    # --- Business Rules (used by guardrails) ---
    # Maximum number of days since order fulfillment to allow auto-refund
    REFUND_MAX_DAYS: int = int(os.getenv("REFUND_MAX_DAYS", "30"))
    # Maximum order amount (USD) to allow auto-refund without human approval
    REFUND_MAX_AMOUNT: float = float(os.getenv("REFUND_MAX_AMOUNT", "100"))

    def validate(self):
        """
        Call this once at startup to catch missing critical settings early,
        rather than getting a confusing error deep inside a function later.
        """
        required = {
            "SHOPIFY_STORE_DOMAIN": self.SHOPIFY_STORE_DOMAIN,
            "SHOPIFY_CLIENT_ID": self.SHOPIFY_CLIENT_ID,
            "SHOPIFY_CLIENT_SECRET": self.SHOPIFY_CLIENT_SECRET,
            "GROQ_API_KEY": self.OPENROUTER_API_KEY,
            "TELEGRAM_BOT_TOKEN": self.TELEGRAM_BOT_TOKEN,
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                f"Please check your .env file."
            )


# Single shared instance — import this everywhere
settings = Settings()