"""
logger.py
---------
Central logging configuration for the entire project.

Two independent log levels:
    CONSOLE_LOG_LEVEL - what you see in the terminal (default: INFO)
    FILE_LOG_LEVEL    - what gets written to logs/agent.log (default: DEBUG)

This means the log FILE always captures full detail for debugging,
while the terminal stays clean during normal operation. No need to
toggle anything — just check logs/agent.log when you need DEBUG detail,
regardless of what LOG_LEVEL your console is set to.
"""

import logging
import os
from logging.handlers import RotatingFileHandler


LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "agent.log")

CONSOLE_LOG_LEVEL = os.getenv("CONSOLE_LOG_LEVEL", "INFO").upper()
FILE_LOG_LEVEL = os.getenv("FILE_LOG_LEVEL", "DEBUG").upper()

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str) -> logging.Logger:
    """
    Returns a logger for the given module name.

    Console shows CONSOLE_LOG_LEVEL and above.
    File (logs/agent.log) always captures FILE_LOG_LEVEL and above,
    independent of what the console is showing.

    Usage:
        from logger import get_logger
        logger = get_logger(__name__)
        logger.debug("Detailed info -> file only, unless console is DEBUG too")
        logger.info("Normal info -> shows in both by default")
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    # Logger itself must allow the lowest level any handler needs
    logger.setLevel("DEBUG")

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(CONSOLE_LOG_LEVEL)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(FILE_LOG_LEVEL)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger