"""PregameCache — file-persisted JSON cache for pre-game LLM analysis results.

Survives pipeline restarts. Supports TTL-based freshness checks.
Uses filelock for safe concurrent access across processes.
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

from filelock import FileLock

from agents.utils.env import _env_int


class PregameCache:
    """File-persisted JSON cache for pre-game analysis entries.

    Keyed by game_id (coerced to str internally). Supports TTL-based freshness
    checks and safe concurrent access via filelock.
    """

    def __init__(
        self,
        cache_path: Optional[str] = None,
        ttl_minutes: Optional[int] = None,
    ) -> None:
        self.cache_path = cache_path or os.environ.get(
            "SPORTS_PREGAME_CACHE_PATH", "/tmp/polyagents_pregame_cache.json"
        )
        self.lock_path = self.cache_path + ".lock"
        self.ttl_seconds = (
            ttl_minutes * 60
            if ttl_minutes is not None
            else _env_int("SPORTS_PREGAME_CACHE_TTL_MINUTES", 30) * 60
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_fresh(self, game_id: int) -> bool:
        """Return True when entry is within TTL, False when expired or missing."""
        entry = self.get(game_id)
        if entry is None:
            return False
        timestamp = entry.get("timestamp")
        if timestamp is None:
            return False
        age = time.time() - float(timestamp)
        return age < self.ttl_seconds

    def get(self, game_id: int) -> Optional[dict]:
        """Return cache entry for game_id, or None if not found.

        Always coerces game_id to str for lookup.
        """
        data = self._read()
        return data.get(str(game_id))

    def set(self, game_id: int, entry: dict) -> None:
        """Persist entry to JSON file under filelock.

        Always stores under str(game_id). Adds/overwrites timestamp.
        """
        lock = FileLock(self.lock_path)
        with lock:
            data = self._read_unlocked()
            data[str(game_id)] = {**entry, "timestamp": time.time()}
            self._write_unlocked(data)

    def remove(self, game_id: int) -> None:
        """Delete entry for game_id if present. No-op if not found."""
        lock = FileLock(self.lock_path)
        with lock:
            data = self._read_unlocked()
            data.pop(str(game_id), None)
            self._write_unlocked(data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read(self) -> dict:
        """Read cache JSON (no lock — caller responsible or safe for read-only)."""
        if not os.path.exists(self.cache_path):
            return {}
        try:
            with open(self.cache_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _read_unlocked(self) -> dict:
        """Read cache JSON without acquiring lock (caller must hold lock)."""
        return self._read()

    def _write_unlocked(self, data: dict) -> None:
        """Write cache JSON without acquiring lock (caller must hold lock)."""
        with open(self.cache_path, "w") as f:
            json.dump(data, f)
