"""Shared environment variable parsing helpers.

This module must import ONLY stdlib (os). It exists to eliminate
per-module duplication of _env_bool/_env_int/_env_float. The original
duplication was intentional to avoid pulling heavy dependencies
(langchain, openai) from executor.py into lightweight modules.
"""

import os


def _env_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
