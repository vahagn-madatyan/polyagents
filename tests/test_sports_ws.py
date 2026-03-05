"""
Unit tests for SportGameState model and SportsWSConnector.
No network calls — all tests use static dicts and mock WS objects.
"""

from __future__ import annotations

import queue
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from agents.utils.objects import SportGameState
from agents.connectors.sports_ws import (
    SportsWSConnector,
    _parse_score,
    _build_game_state,
)


# ---------------------------------------------------------------------------
# Test fixtures — static WS message dicts
# ---------------------------------------------------------------------------


def _nfl_message() -> dict:
    return {
        "gameId": 19439,
        "leagueAbbreviation": "nfl",
        "slug": "nfl-lac-buf-2025-01-26",
        "homeTeam": "LAC",
        "awayTeam": "BUF",
        "status": "InProgress",
        "score": "3-16",
        "period": "Q4",
        "elapsed": "5:18",
        "live": True,
        "ended": False,
        "turn": "lac",
    }


def _soccer_message() -> dict:
    return {
        "gameId": 55001,
        "leagueAbbreviation": "soccer",
        "slug": "soccer-man-city-chelsea-2025-04-12",
        "homeTeam": "Man City",
        "awayTeam": "Chelsea",
        "status": "Break",
        "score": "1-0",
        "period": "HT",
        "elapsed": None,
        "live": True,
        "ended": False,
    }


def _esports_message() -> dict:
    return {
        "gameId": 1317359,
        "leagueAbbreviation": "cs2",
        "slug": "cs2-arcred-the-glecs-2025-07-20",
        "homeTeam": "ARCRED",
        "awayTeam": "The glecs",
        "status": "finished",
        "score": "000-000|2-0|Bo3",
        "period": "2/3",
        "live": False,
        "ended": True,
        "finished_timestamp": "2025-07-20T18:30:00.000Z",
    }


def _esports_message_1_1() -> dict:
    msg = _esports_message()
    msg["score"] = "000-000|1-1|Bo3"
    return msg


def _tennis_message() -> dict:
    return {
        "gameId": 77001,
        "leagueAbbreviation": "tennis",
        "slug": "tennis-djokovic-nadal-2025-06-05",
        "homeTeam": "Djokovic",
        "awayTeam": "Nadal",
        "status": "inprogress",
        "score": "1-1",
        "period": "Set 2",
        "live": True,
        "ended": False,
    }


def _mlb_message() -> dict:
    return {
        "gameId": 88001,
        "leagueAbbreviation": "mlb",
        "slug": "mlb-nyy-bos-2025-08-15",
        "homeTeam": "NYY",
        "awayTeam": "BOS",
        "status": "InProgress",
        "score": "2-5",
        "period": "End 5",
        "live": True,
        "ended": False,
    }


# ---------------------------------------------------------------------------
# Task 1: SportGameState model construction tests
# ---------------------------------------------------------------------------


class TestSportGameStateModel(unittest.TestCase):

    def test_build_game_state_nfl(self) -> None:
        """NFL dict constructs SportGameState with correct field mappings."""
        data = _nfl_message()
        state = _build_game_state(data)

        self.assertIsInstance(state, SportGameState)
        self.assertEqual(state.game_id, 19439)
        self.assertEqual(state.league, "nfl")
        self.assertEqual(state.slug, "nfl-lac-buf-2025-01-26")
        self.assertEqual(state.home_team, "LAC")
        self.assertEqual(state.away_team, "BUF")
        self.assertEqual(state.status, "InProgress")
        self.assertEqual(state.score_raw, "3-16")
        self.assertEqual(state.home_score, 3)
        self.assertEqual(state.away_score, 16)
        self.assertEqual(state.period, "Q4")
        self.assertEqual(state.elapsed, "5:18")
        self.assertTrue(state.live)
        self.assertFalse(state.ended)
        self.assertEqual(state.possession, "lac")

    def test_stale_defaults_false(self) -> None:
        """New SportGameState has stale=False."""
        state = _build_game_state(_nfl_message())
        self.assertFalse(state.stale)

    def test_last_updated_set(self) -> None:
        """New SportGameState has last_updated > 0."""
        state = _build_game_state(_nfl_message())
        self.assertGreater(state.last_updated, 0)

    def test_build_game_state_soccer(self) -> None:
        """Soccer dict with Break/HT period constructs correctly."""
        state = _build_game_state(_soccer_message())
        self.assertEqual(state.game_id, 55001)
        self.assertEqual(state.league, "soccer")
        self.assertEqual(state.status, "Break")
        self.assertEqual(state.period, "HT")
        self.assertEqual(state.home_score, 1)
        self.assertEqual(state.away_score, 0)
        self.assertTrue(state.live)
        self.assertFalse(state.ended)

    def test_build_game_state_esports(self) -> None:
        """CS2 dict with compound score constructs correctly with parsed series score."""
        state = _build_game_state(_esports_message())
        self.assertEqual(state.game_id, 1317359)
        self.assertEqual(state.league, "cs2")
        self.assertEqual(state.score_raw, "000-000|2-0|Bo3")
        self.assertEqual(state.home_score, 2)
        self.assertEqual(state.away_score, 0)
        self.assertEqual(state.period, "2/3")
        self.assertTrue(state.ended)
        self.assertFalse(state.live)
        self.assertEqual(state.finished_timestamp, "2025-07-20T18:30:00.000Z")

    def test_build_game_state_tennis(self) -> None:
        """Tennis dict with Set 2 period constructs correctly."""
        state = _build_game_state(_tennis_message())
        self.assertEqual(state.game_id, 77001)
        self.assertEqual(state.league, "tennis")
        self.assertEqual(state.period, "Set 2")
        self.assertEqual(state.home_score, 1)
        self.assertEqual(state.away_score, 1)

    def test_build_game_state_mlb(self) -> None:
        """MLB dict with End 5 period constructs correctly."""
        state = _build_game_state(_mlb_message())
        self.assertEqual(state.game_id, 88001)
        self.assertEqual(state.league, "mlb")
        self.assertEqual(state.period, "End 5")
        self.assertEqual(state.home_score, 2)
        self.assertEqual(state.away_score, 5)


# ---------------------------------------------------------------------------
# Task 1: Score parsing tests
# ---------------------------------------------------------------------------


class TestParseScore(unittest.TestCase):

    def test_parse_score_standard(self) -> None:
        """Standard score strings parse to integer tuples."""
        self.assertEqual(_parse_score("3-16"), (3, 16))
        self.assertEqual(_parse_score("0-0"), (0, 0))
        self.assertEqual(_parse_score("21-14"), (21, 14))

    def test_parse_score_esports(self) -> None:
        """Esports compound score extracts series score from middle segment."""
        self.assertEqual(_parse_score("000-000|2-0|Bo3"), (2, 0))
        self.assertEqual(_parse_score("000-000|1-1|Bo3"), (1, 1))

    def test_parse_score_empty(self) -> None:
        """Empty string and None both return (None, None)."""
        self.assertEqual(_parse_score(""), (None, None))
        self.assertEqual(_parse_score(None), (None, None))

    def test_parse_score_malformed(self) -> None:
        """Malformed score strings return (None, None) gracefully."""
        self.assertEqual(_parse_score("abc"), (None, None))
        # "3-" returns either (None, None) or graceful fallback — just no crash
        result = _parse_score("3-")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)


# ---------------------------------------------------------------------------
# Task 2: SportsWSConnector tests
# ---------------------------------------------------------------------------


def _make_connector() -> SportsWSConnector:
    """Create a SportsWSConnector bypassing __init__ (no env deps needed)."""
    connector = SportsWSConnector.__new__(SportsWSConnector)
    connector._message_queue = queue.Queue(maxsize=1000)
    connector._game_states = {}
    connector._state_lock = threading.Lock()
    connector._last_message_at = 0.0
    connector._ws_app = None
    connector._running = False
    connector._reconnect_attempt = 0
    connector._watchdog_timer = None
    connector._connection_started_at = 0.0
    connector.freeze_timeout = 300
    connector.log_level = "changes"
    connector.ended_game_ttl_minutes = 60
    return connector


class TestSportsWSConnectorPing(unittest.TestCase):

    def test_ping_message_handled(self) -> None:
        """Calling _on_message with raw='ping' calls ws.send('pong') and does NOT update _last_message_at."""
        connector = _make_connector()
        ws_mock = MagicMock()
        initial_last_message_at = connector._last_message_at

        connector._on_message(ws_mock, "ping")

        ws_mock.send.assert_called_once_with("pong")
        # _last_message_at must NOT be updated by a ping
        self.assertEqual(connector._last_message_at, initial_last_message_at)

    def test_data_message_updates_last_message_at(self) -> None:
        """Calling _on_message with valid JSON updates _last_message_at."""
        connector = _make_connector()
        ws_mock = MagicMock()

        import json

        raw = json.dumps(_nfl_message())
        connector._on_message(ws_mock, raw)

        self.assertGreater(connector._last_message_at, 0)

    def test_data_message_stores_game_state(self) -> None:
        """After _on_message with NFL JSON, _game_states[19439] is a SportGameState."""
        connector = _make_connector()
        ws_mock = MagicMock()

        import json

        raw = json.dumps(_nfl_message())
        connector._on_message(ws_mock, raw)

        self.assertIn(19439, connector._game_states)
        self.assertIsInstance(connector._game_states[19439], SportGameState)


class TestSportsWSConnectorPeriodTransition(unittest.TestCase):

    def test_period_transition_detected(self) -> None:
        """Process two messages for same gameId with period Q3 then Q4 — message_queue contains period_transition."""
        connector = _make_connector()
        ws_mock = MagicMock()

        import json

        # First message: Q3
        msg1 = _nfl_message()
        msg1["period"] = "Q3"
        connector._on_message(ws_mock, json.dumps(msg1))

        # Second message: Q4
        msg2 = _nfl_message()
        msg2["period"] = "Q4"
        connector._on_message(ws_mock, json.dumps(msg2))

        # Queue should contain a period_transition event
        found = False
        while not connector._message_queue.empty():
            event = connector._message_queue.get_nowait()
            if event.get("type") == "period_transition":
                found = True
                self.assertEqual(event["old_period"], "Q3")
                self.assertEqual(event["new_period"], "Q4")
                self.assertIsInstance(event["state"], SportGameState)
        self.assertTrue(found, "Expected period_transition event in queue")

    def test_no_false_period_transition(self) -> None:
        """Process two messages for same gameId with same period Q4 — no period_transition event."""
        connector = _make_connector()
        ws_mock = MagicMock()

        import json

        msg1 = _nfl_message()
        msg1["period"] = "Q4"
        connector._on_message(ws_mock, json.dumps(msg1))

        msg2 = _nfl_message()
        msg2["period"] = "Q4"
        connector._on_message(ws_mock, json.dumps(msg2))

        # Queue should NOT contain any period_transition event
        while not connector._message_queue.empty():
            event = connector._message_queue.get_nowait()
            self.assertNotEqual(
                event.get("type"),
                "period_transition",
                "Unexpected period_transition event when period unchanged",
            )

    def test_first_message_no_transition(self) -> None:
        """First message for a gameId does not emit period_transition."""
        connector = _make_connector()
        ws_mock = MagicMock()

        import json

        connector._on_message(ws_mock, json.dumps(_nfl_message()))

        while not connector._message_queue.empty():
            event = connector._message_queue.get_nowait()
            self.assertNotEqual(
                event.get("type"),
                "period_transition",
                "Should not emit transition on first message",
            )


class TestSportsWSConnectorThreadSafety(unittest.TestCase):

    def test_game_state_dict_thread_safe(self) -> None:
        """_game_states access uses _state_lock — verify lock is acquired in _process_game_state."""
        connector = _make_connector()

        # Replace the real lock with a MagicMock that wraps a real lock to track calls
        real_lock = threading.Lock()
        mock_lock = MagicMock(wraps=real_lock)
        connector._state_lock = mock_lock

        connector._process_game_state(_nfl_message())

        # __enter__ is called when using 'with lock:' — verify it was called
        self.assertTrue(
            mock_lock.__enter__.called or mock_lock.acquire.called,
            "Expected _state_lock to be acquired during _process_game_state",
        )

    def test_get_game_state_returns_state(self) -> None:
        """get_game_state() returns the stored state (or None if not found)."""
        connector = _make_connector()
        import json

        ws_mock = MagicMock()
        connector._on_message(ws_mock, json.dumps(_nfl_message()))

        state = connector.get_game_state(19439)
        self.assertIsNotNone(state)
        self.assertIsInstance(state, SportGameState)

        missing = connector.get_game_state(99999)
        self.assertIsNone(missing)

    def test_get_all_game_states_snapshot(self) -> None:
        """get_all_game_states() returns dict of current states."""
        connector = _make_connector()
        import json

        ws_mock = MagicMock()
        connector._on_message(ws_mock, json.dumps(_nfl_message()))
        connector._on_message(ws_mock, json.dumps(_soccer_message()))

        all_states = connector.get_all_game_states()
        self.assertIsInstance(all_states, dict)
        self.assertIn(19439, all_states)
        self.assertIn(55001, all_states)


if __name__ == "__main__":
    unittest.main()
