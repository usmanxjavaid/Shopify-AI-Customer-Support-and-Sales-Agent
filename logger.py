"""
logger.py
---------
Central logging configuration for the entire project.

Every module imports the logger from here:
    from logger import get_logger
    logger = get_logger(__name__)

Two outputs:
    1. Console  — colored, human-readable output while developing/running
    2. File     — logs/agent.log, permanent record for debugging

Log levels (in order of severity):
    DEBUG    → detailed internal info (only shown in development)
    INFO     → normal operations ("order fetched", "message received")
    WARNING  → something unexpected but not breaking ("scope empty")
    ERROR    → something broke and needs attention
    CRITICAL → something broke so badly the app can't continue
"""

import logging
import os
from logging.handlers import RotatingFileHandler


# --- Settings ---
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "agent.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Format: timestamp | level | module name | message
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str) -> logging.Logger:
    """
    Returns a logger for the given module name.

    Usage in any file:
        from logger import get_logger
        logger = get_logger(__name__)
        logger.info("Something happened")
        logger.error("Something broke")

    Args:
        name: typically __name__ of the calling module,
              so logs show exactly which file the message came from

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if get_logger is called multiple times
    if logger.handlers:
        return logger

    logger.setLevel(LOG_LEVEL)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # --- Handler 1: Console output ---
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # --- Handler 2: File output (rotating) ---
    # RotatingFileHandler caps the log file at 5MB, keeps 3 backups
    # so logs never fill up your disk on a long-running bot
    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger