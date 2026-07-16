"""
config.py
---------
Central configuration loader for the entire project

This is the ONLY file that reads from .env directly.
Every other module imports `settings` from here instead calling os.getenv() function directly.

Why: if we want to change variable name, we can change it in one file, not scattered across 10 files.
"""

import os
from dotenv import load_dotenv

# load the .env file into evironment variables
load_dotenv()

class Settings():
    """
    Holds all configuration values for the project.
    Reads from environment variables (set via .env file)
    """

    # --- Shopify ---
    SHOPIFY_STORE_DOMAIN: str = os.getenv('SHOPIFY_STORE_DOMAIN', '')
    SHOPIFY_CLIENT_ID: str = os.getenv('SHOPIFY_CLIENT_ID', '')
    SHOPIFY_CLIENT_SECRET: str = os.getenv('SHOPIFY_CLIENT_SECRET', '')
    SHOPIFY_API_VERSION: str = os.getenv('SHOPIFY_API_VERSION', '')

    # --- Groq LLM ---
    GROQ_API_KEY: str = os.getenv('GROQ_API_KEY', '')
    GROQ_MODEL: str = os.getenv('GROQ_MODEL', '')

    # --- Telegram ---
    TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    OWNER_TELEGRAM_CHAT_ID: str = os.getenv('OWNER_TELEGRAM_CHAT_ID', '')

    # --- Buiness Rules (used by guardrails) ---
    # Maximun number of days since order fulfillment to allow auto-refund
    REFUND_MAX_DYAS: int = int(os.getenv('REFUND_MAX_DAYS', '30'))

    # Maximm order amount (USD) to allow auto-refund
    REFUND_MAX_AMOUNT: float = float(os.getenv('REFUND_MAX_AMOUNT', '100'))

    def validate(self):
        """
        call this once at startup to detect missing critical settings early,
        rather than getting a confusing error deep inside a function later.
        """
        required = {
            "SHOPIFY_STORE_DOMAIN": self.SHOPIFY_STORE_DOMAIN,
            "SHOPIFY_CLIENT_ID": self.SHOPIFY_CLIENT_ID,
            "SHOPIFY_CLIENT_SECRET": self.SHOPIFY_CLIENT_SECRET,
            "GROQ_API_KEY": self.GROQ_API_KEY,
            "TELEGRAM_BOT_TOKEN": self.TELEGRAM_BOT_TOKEN,
        }

        missing = [key for key, value in required.items() if not value]
        if missing:
            raise EnvironmentError(
                f"Missing required environment variable: {', '.join(missing)}\n"
                f"Please check your .env file."
            )

# Single shared instance — import this everywhere
settings = Settings()




