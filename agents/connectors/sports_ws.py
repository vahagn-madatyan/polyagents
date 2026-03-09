"""
Sports WebSocket connector for Polymarket live game data.

Connects to wss://sports-api.polymarket.com/ws, parses game state messages
across all 9 supported sports, detects period transitions, and handles
server ping/pong keepalive.

Usage:
    connector = SportsWSConnector()
    # Run in a thread: connector.run()
    state = connector.get_game_state(game_id)
    q = connector.get_message_queue()  # consume period_transition events
"""

from __future__ import annotations

import json
import os
import queue
import random
import threading
import time
from typing import Optional

import websocket

from agents.utils.objects import SportGameState


def _env_int(name: str, default: int) -> int:
    """Read an integer from environment variable, returning default on missing/invalid."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Module-level helpers (usable by tests without instantiating connector)
# ---------------------------------------------------------------------------


def reconnect_delay(attempt: int, base: float = 1.0, max_delay: float = 60.0) -> float:
    """Compute exponential backoff delay with jitter for reconnect attempts.

    Args:
        attempt: Zero-based reconnect attempt counter.
        base: Base delay multiplier in seconds (default 1.0).
        max_delay: Maximum delay before jitter in seconds (default 60.0).

    Returns:
        Delay in seconds: min(base * 2^attempt, max_delay) + uniform(0, 25% of that).
    """
    exp = min(base * (2**attempt), max_delay)
    jitter = random.uniform(0, exp * 0.25)
    return exp + jitter


HALT_STATUSES = {
    "Suspended",
    "Postponed",
    "Canceled",
    "Forfeit",
    "Delayed",
    "NotNecessary",
    "Awarded",
}
# Lowercase versions for esports/tennis which use lowercase status values
_HALT_STATUSES_LOWER = {s.lower() for s in HALT_STATUSES}


def should_halt_trading(state: "SportGameState") -> bool:  # noqa: F821
    """Return True if trading should be halted for this game state.

    Halts on: edge-case statuses (Suspended, Forfeit, Delayed, etc.), stale data.
    Case-insensitive matching handles esports/tennis lowercase status values.

    Args:
        state: The current SportGameState to evaluate.

    Returns:
        True if trading should be halted, False if safe to trade.
    """
    if state.stale:
        return True
    return state.status in HALT_STATUSES or state.status.lower() in _HALT_STATUSES_LOWER


def _parse_score(score_raw: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    """Parse a WS score string into (home_score, away_score) integers.

    Handles:
      - Empty/None: returns (None, None)
      - Standard "3-16" -> (3, 16)
      - Esports compound "000-000|2-0|Bo3": extracts series score from middle segment -> (2, 0)
      - Malformed: returns (None, None) with a warning log

    Args:
        score_raw: Raw score string from WebSocket message, or None.

    Returns:
        Tuple of (home_score, away_score) as ints, or (None, None) on failure.
    """
    if not score_raw:
        return None, None

    # Esports compound scores use pipe-separated segments: "000-000|2-0|Bo3"
    # The middle segment is the series score (maps won).
    if "|" in score_raw:
        parts = score_raw.split("|")
        if len(parts) >= 2:
            segment = parts[1]  # "2-0" in "000-000|2-0|Bo3"
        else:
            segment = parts[0]
    else:
        segment = score_raw

    try:
        home_str, away_str = segment.split("-", 1)
        home = int(home_str)
        away = int(away_str)
        return home, away
    except (ValueError, AttributeError):
        print(f"[sports_ws] event=score_parse_error score_raw={score_raw!r}")
        return None, None


def _build_game_state(data: dict) -> SportGameState:
    """Construct a SportGameState from a raw WebSocket message dict.

    Args:
        data: Parsed JSON dict from the Polymarket sports WebSocket.

    Returns:
        A fully populated SportGameState instance.
    """
    score_raw = data.get("score", "") or ""
    home_score, away_score = _parse_score(score_raw)

    return SportGameState(
        game_id=data["gameId"],
        league=(data.get("leagueAbbreviation", "") or "").lower(),
        slug=data.get("slug", "") or "",
        home_team=data.get("homeTeam", "") or "",
        away_team=data.get("awayTeam", "") or "",
        status=data.get("status", "") or "",
        score_raw=score_raw,
        home_score=home_score,
        away_score=away_score,
        period=data.get("period", "") or "",
        live=bool(data.get("live", False)),
        ended=bool(data.get("ended", False)),
        elapsed=data.get("elapsed"),
        finished_timestamp=data.get("finished_timestamp"),
        possession=data.get("turn"),  # NFL/CFB only; None for all other sports
        last_updated=time.monotonic(),
        stale=False,
    )


# ---------------------------------------------------------------------------
# SportsWSConnector
# ---------------------------------------------------------------------------


class SportsWSConnector:
    """Persistent WebSocket connector for Polymarket live sports data.

    Maintains a daemon thread running WebSocketApp. An external reconnect
    loop restarts on disconnect with exponential backoff + jitter. A watchdog
    timer detects silent data freezes (the known Polymarket server-side bug)
    and forces reconnect.

    Critical: only game data messages reset the watchdog — NOT ping/pong.
    This is intentional: the known freeze bug keeps ping/pong healthy while
    stopping game data.
    """

    WS_URL = "wss://sports-api.polymarket.com/ws"

    def __init__(self) -> None:
        # Thread-safe message delivery queue for downstream consumers
        self._message_queue: queue.Queue = queue.Queue(maxsize=1000)

        # Game state storage: game_id -> SportGameState
        self._game_states: dict[int, SportGameState] = {}
        self._state_lock = threading.Lock()

        # Watchdog: tracks last real data message time (NOT ping time)
        self._last_message_at: float = 0.0

        # WebSocket application handle
        self._ws_app: websocket.WebSocketApp | None = None

        # Reconnect loop control
        self._running = False
        self._reconnect_attempt = 0
        self._connection_started_at: float = 0.0

        # Watchdog timer handle
        self._watchdog_timer: threading.Timer | None = None

        # Purge tracking: last time _purge_ended_games() was run
        self._last_purge_at: float = 0.0

        # Config from environment
        self.freeze_timeout = _env_int("SPORTS_WS_FREEZE_TIMEOUT_SECONDS", 300)
        self.ended_game_ttl_minutes = _env_int("SPORTS_WS_ENDED_GAME_TTL_MINUTES", 60)
        self.log_level = os.getenv("SPORTS_WS_LOG_LEVEL", "changes")

    # ------------------------------------------------------------------
    # WebSocket callbacks
    # ------------------------------------------------------------------

    def _on_message(self, ws: websocket.WebSocketApp, raw: str) -> None:
        """Handle incoming WebSocket message.

        Ping messages are responded to with pong but do NOT reset the watchdog
        or update _last_message_at. Only real game data messages update state.
        """
        if raw == "ping":
            ws.send("pong")
            return  # CRITICAL: do NOT update _last_message_at for pings

        # Update last-real-data timestamp and reset watchdog
        self._last_message_at = time.monotonic()
        self._reset_watchdog()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            print(f"[sports_ws] event=json_decode_error raw_preview={raw[:80]!r}")
            return

        self._process_game_state(data)

        if self.log_level == "all":
            game_id = data.get("gameId")
            print(
                f"[sports_ws] event=message game_id={game_id} period={data.get('period')} score={data.get('score')}"
            )

    def _on_open(self, ws: websocket.WebSocketApp) -> None:
        """Called when WebSocket connection is established."""
        print(f"[sports_ws] event=connected url={self.WS_URL}")
        self._connection_started_at = time.monotonic()

    def _on_error(self, ws: websocket.WebSocketApp, error: Exception) -> None:
        """Called on WebSocket error."""
        print(f"[sports_ws] event=error error={error}")

    def _on_close(
        self,
        ws: websocket.WebSocketApp,
        close_status_code: Optional[int],
        close_msg: Optional[str],
    ) -> None:
        """Called when WebSocket connection closes."""
        print(f"[sports_ws] event=disconnected code={close_status_code}")
        # Reconnect loop in run() handles restart — do NOT call run_forever() here.

    # ------------------------------------------------------------------
    # Game state processing
    # ------------------------------------------------------------------

    def _process_game_state(self, data: dict) -> None:
        """Parse incoming game data, store state, and detect period transitions.

        CRITICAL: _state_lock is released BEFORE calling _message_queue.put()
        to prevent potential deadlock if the queue is full.

        Runs periodic ended game TTL purge (at most once per 60 seconds).
        """
        game_id = data.get("gameId")
        if game_id is None:
            return

        # Periodic purge: run at most once per 60 seconds
        if time.monotonic() - self._last_purge_at > 60:
            self._purge_ended_games()

        new_period = data.get("period", "")

        # Snapshot existing state under lock (get old_period before update)
        with self._state_lock:
            existing = self._game_states.get(game_id)
            old_period = existing.period if existing else None

        # Build new state (no lock needed — pure computation)
        new_state = _build_game_state(data)

        # Store new state under lock
        with self._state_lock:
            self._game_states[game_id] = new_state

        # AFTER releasing lock: detect period transition and emit to queue
        # This avoids holding _state_lock while potentially blocking on queue.put()
        if old_period is not None and old_period != new_period:
            self._emit_period_transition(new_state, old_period, new_period)
        elif self.log_level in ("all", "changes") and existing is not None:
            # Log score changes even without period transition
            if existing.score_raw != new_state.score_raw:
                print(
                    f"[sports_ws] event=score_change game_id={game_id} "
                    f"from={existing.score_raw} to={new_state.score_raw}"
                )

    def _emit_period_transition(
        self,
        state: SportGameState,
        old_period: str,
        new_period: str,
    ) -> None:
        """Emit a period_transition event to the message queue."""
        print(
            f"[sports_ws] event=period_transition game_id={state.game_id} "
            f"from={old_period} to={new_period}"
        )
        event = {
            "type": "period_transition",
            "game_id": state.game_id,
            "state": state,
            "old_period": old_period,
            "new_period": new_period,
        }
        try:
            self._message_queue.put_nowait(event)
        except queue.Full:
            print(
                f"[sports_ws] event=queue_full game_id={state.game_id} dropped=period_transition"
            )

    # ------------------------------------------------------------------
    # Watchdog — silent freeze detection
    # ------------------------------------------------------------------

    def _reset_watchdog(self) -> None:
        """Reset the watchdog timer. Called only on real game data, not pings."""
        if self._watchdog_timer is not None:
            self._watchdog_timer.cancel()
        self._watchdog_timer = threading.Timer(
            self.freeze_timeout, self._on_freeze_detected
        )
        self._watchdog_timer.daemon = True
        self._watchdog_timer.start()

    def _on_freeze_detected(self) -> None:
        """Called by watchdog timer when no data received for freeze_timeout seconds.

        Marks all game states stale and forces reconnect. This defends against
        the known Polymarket server-side silent freeze bug (GitHub issue #26).
        """
        print(f"[sports_ws] event=freeze_detected timeout={self.freeze_timeout}s")
        with self._state_lock:
            for state in self._game_states.values():
                state.stale = True
        # Force close — the run() loop will reconnect with backoff
        if self._ws_app is not None:
            self._ws_app.close()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the WebSocket connection with automatic reconnect.

        Runs in a loop: creates WebSocketApp, starts daemon thread,
        waits for disconnect, then schedules reconnect with exponential backoff.

        Call this method from a dedicated thread (it blocks until stop() is called).
        """
        self._running = True
        while self._running:
            self._ws_app = websocket.WebSocketApp(
                self.WS_URL,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_open=self._on_open,
            )

            ws_thread = threading.Thread(
                target=self._ws_app.run_forever,
                kwargs={
                    "ping_interval": 0,  # Server sends pings; disable client-side pings
                    "ping_timeout": None,  # No client ping timeout needed
                },
                daemon=True,
                name="sports-ws-thread",
            )
            ws_thread.start()
            ws_thread.join()  # Block until WS thread exits (disconnect or error)

            if not self._running:
                break

            # Reset attempt counter if connection was stable for >60s
            if self._connection_started_at > 0:
                connection_duration = time.monotonic() - self._connection_started_at
                if connection_duration > 60:
                    self._reconnect_attempt = 0

            self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        """Sleep with exponential backoff + jitter before next reconnect attempt."""
        delay = reconnect_delay(self._reconnect_attempt)
        self._reconnect_attempt += 1
        print(
            f"[sports_ws] event=reconnect_scheduled delay={delay:.1f}s "
            f"attempt={self._reconnect_attempt}"
        )
        time.sleep(delay)

    # ------------------------------------------------------------------
    # Game state lifecycle: ended game TTL purge
    # ------------------------------------------------------------------

    def _purge_ended_games(self) -> None:
        """Remove ended game states older than ended_game_ttl_minutes.

        Called periodically (at most once per 60 seconds) from _process_game_state
        to prevent unbounded memory growth from completed games.
        """
        self._last_purge_at = time.monotonic()
        cutoff = time.monotonic() - (self.ended_game_ttl_minutes * 60)
        to_remove = []
        with self._state_lock:
            for game_id, state in self._game_states.items():
                if state.ended and state.last_updated < cutoff:
                    to_remove.append(game_id)
            for game_id in to_remove:
                del self._game_states[game_id]
        if to_remove:
            print(
                f"[sports_ws] event=purged_ended_games count={len(to_remove)} "
                f"game_ids={to_remove}"
            )

    def stop(self) -> None:
        """Stop the reconnect loop and close the WebSocket connection."""
        self._running = False
        if self._watchdog_timer is not None:
            self._watchdog_timer.cancel()
        if self._ws_app is not None:
            self._ws_app.close()
        print("[sports_ws] event=stopped")

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def get_game_state(self, game_id: int) -> Optional[SportGameState]:
        """Return the current state for a game, or None if not tracked.

        Thread-safe — acquires _state_lock for read.
        """
        with self._state_lock:
            return self._game_states.get(game_id)

    def get_all_game_states(self) -> dict[int, SportGameState]:
        """Return a snapshot copy of all tracked game states.

        Thread-safe — acquires _state_lock for read.
        """
        with self._state_lock:
            return dict(self._game_states)

    def get_message_queue(self) -> queue.Queue:
        """Return the internal message queue for consuming period_transition events."""
        return self._message_queue
