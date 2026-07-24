"""Tests for logger configuration."""

import logging

from src.utils.config import get_settings
from src.utils.logger import get_logger


def test_get_logger_applies_configured_log_level(monkeypatch) -> None:
    """Logger should use the configured environment log level."""

    monkeypatch.setenv("LOG_LEVEL", "debug")
    get_settings.cache_clear()

    logger = get_logger("tests.logger")

    assert logger.level == logging.DEBUG
