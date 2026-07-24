"""Logging helpers for the data platform project."""

from __future__ import annotations

import logging

from src.utils.config import get_settings

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for the provided name."""

    settings = get_settings()
    logger = logging.getLogger(name)

    if not logging.getLogger().handlers:
        logging.basicConfig(level=settings.log_level, format=LOG_FORMAT)

    logger.setLevel(settings.log_level)
    return logger
