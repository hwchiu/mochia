"""Shared utility helpers used across the application."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def safe_json_loads(value: str | None, fallback: Any) -> Any:
    """Safely parse JSON string with a fallback value on failure.

    Args:
        value: JSON string to parse, or None.
        fallback: Value to return if parsing fails or value is None/empty.

    Returns:
        Parsed JSON value, or fallback if parsing fails.
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
