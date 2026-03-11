"""Shared utility helpers used across the application."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def safe_json_loads(value: str | None, fallback: Any) -> Any:
    """Parse a JSON string, returning *fallback* on missing value or decode error.

    Logs a warning when the stored value cannot be parsed so that data
    corruption is visible in logs without raising an unhandled exception.
    """
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        logger.warning(
            "Invalid JSON in DB field, using fallback. value=%r",
            value[:100],
        )
        return fallback
