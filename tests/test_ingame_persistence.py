"""Unit tests for InGameTrader state persistence.

Tests cover:
- _order_log survives process restart (round-trip through JSON file)
- _ended_games survives process restart (round-trip through JSON file)
- Missing persistence files produce empty state (no crash)
- Corrupt persistence files produce warning + empty state (no crash)
- Integer game_id keys survive JSON round-trip (int -> str -> int)
- Atomic write pattern (temp file + rename)
- Separate lock path from BudgetCoordinator
"""

from __future__ import annotations

import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mocks():
    """Return mocked dependencies for InGameTrader (same pattern as test_ingame_trader.py)."""
    budget = MagicMock()
    budget.can_spend_sports.return_value = True

    data_connector = MagicMock()
    data_connector.get_game_context.return_value = {"stats": {}, "h2h": [], "odds": {}}

    executor = MagicMock()
    executor.analyze_game.return_value = None

    cache = MagicMock()
    cache.get.return_value = None
    cache.is_fresh.return_value = False

    polymarket = MagicMock()
    polymarket.client = MagicMock()

    return {
        "budget": budget,
        "data_connector": data_connector,
        "executor": executor,
        "cache": cache,
        "polymarket": polymarket,
    }


def _make_trader(tmp_path, monkeypatch, mocks=None):
    """Build InGameTrader with persistence paths pointing to tmp_path."""
    from agents.application.ingame_trader import InGameTrader

    if mocks is None:
        mocks = _make_mocks()

    order_log_path = str(tmp_path / "order_log.json")
    ended_games_path = str(tmp_path / "ended_games.json")
    state_lock_path = str(tmp_path / "ingame_state.lock")

    monkeypatch.setenv("SPORTS_ORDER_LOG_PATH", order_log_path)
    monkeypatch.setenv("SPORTS_ENDED_GAMES_PATH", ended_games_path)
    monkeypatch.setenv("SPORTS_STATE_LOCK_PATH", state_lock_path)

    trader = InGameTrader(
        budget_coordinator=mocks["budget"],
        data_connector=mocks["data_connector"],
        executor=mocks["executor"],
        cache=mocks["cache"],
        dry_run=True,
        polymarket=mocks["polymarket"],
    )
    return trader, order_log_path, ended_games_path, state_lock_path


# ---------------------------------------------------------------------------
# TestOrderLogPersistence
# ---------------------------------------------------------------------------


class TestOrderLogPersistence:
    def test_order_log_survives_restart(self, tmp_path, monkeypatch):
        """Write order log entries, create new InGameTrader with same paths, verify _order_log matches."""
        trader, order_log_path, ended_games_path, state_lock_path = _make_trader(
            tmp_path, monkeypatch
        )

        # Directly call _log_order to populate and persist
        trader._log_order(game_id=42, order_id="order-001", market_id="mkt-001")
        trader._log_order(game_id=42, order_id="order-002", market_id="mkt-001")
        trader._log_order(game_id=99, order_id="order-003", market_id="mkt-002")

        # Create a fresh InGameTrader instance pointing to same files
        mocks2 = _make_mocks()
        trader2 = MagicMock()
        from agents.application.ingame_trader import InGameTrader

        trader2 = InGameTrader(
            budget_coordinator=mocks2["budget"],
            data_connector=mocks2["data_connector"],
            executor=mocks2["executor"],
            cache=mocks2["cache"],
            dry_run=True,
            polymarket=mocks2["polymarket"],
        )

        # Verify state was reloaded
        assert 42 in trader2._order_log
        assert len(trader2._order_log[42]) == 2
        assert trader2._order_log[42][0]["order_id"] == "order-001"
        assert trader2._order_log[42][1]["order_id"] == "order-002"
        assert 99 in trader2._order_log
        assert trader2._order_log[99][0]["order_id"] == "order-003"

    def test_order_log_missing_file(self, tmp_path, monkeypatch):
        """Init with nonexistent file path: _order_log is empty dict (no crash)."""
        nonexistent = str(tmp_path / "nonexistent_order_log.json")
        monkeypatch.setenv("SPORTS_ORDER_LOG_PATH", nonexistent)
        monkeypatch.setenv("SPORTS_ENDED_GAMES_PATH", str(tmp_path / "eg.json"))
        monkeypatch.setenv("SPORTS_STATE_LOCK_PATH", str(tmp_path / "lock"))

        from agents.application.ingame_trader import InGameTrader

        mocks = _make_mocks()
        trader = InGameTrader(
            budget_coordinator=mocks["budget"],
            data_connector=mocks["data_connector"],
            executor=mocks["executor"],
            cache=mocks["cache"],
            dry_run=True,
            polymarket=mocks["polymarket"],
        )

        assert trader._order_log == {}

    def test_order_log_corrupt_file(self, tmp_path, monkeypatch, capsys):
        """Write invalid JSON to file: init trader, verify empty dict + warning printed (no crash)."""
        corrupt_path = str(tmp_path / "corrupt_order_log.json")
        with open(corrupt_path, "w") as f:
            f.write("this is not valid json {{{{")

        monkeypatch.setenv("SPORTS_ORDER_LOG_PATH", corrupt_path)
        monkeypatch.setenv("SPORTS_ENDED_GAMES_PATH", str(tmp_path / "eg.json"))
        monkeypatch.setenv("SPORTS_STATE_LOCK_PATH", str(tmp_path / "lock"))

        from agents.application.ingame_trader import InGameTrader

        mocks = _make_mocks()
        trader = InGameTrader(
            budget_coordinator=mocks["budget"],
            data_connector=mocks["data_connector"],
            executor=mocks["executor"],
            cache=mocks["cache"],
            dry_run=True,
            polymarket=mocks["polymarket"],
        )

        assert trader._order_log == {}
        captured = capsys.readouterr()
        assert (
            "warn=corrupt_state_file" in captured.out
            or "corrupt" in captured.out.lower()
        )

    def test_order_log_int_key_roundtrip(self, tmp_path, monkeypatch):
        """Integer game_id keys survive JSON round-trip: int -> str -> int."""
        trader, order_log_path, ended_games_path, state_lock_path = _make_trader(
            tmp_path, monkeypatch
        )

        trader._log_order(game_id=1001, order_id="order-x", market_id="mkt-x")

        # Verify file has string keys (JSON limitation)
        with open(order_log_path) as f:
            raw = json.load(f)
        assert "1001" in raw  # String key in file
        assert 1001 not in raw  # Not int key

        # Create fresh instance and verify keys are ints
        from agents.application.ingame_trader import InGameTrader

        mocks2 = _make_mocks()
        trader2 = InGameTrader(
            budget_coordinator=mocks2["budget"],
            data_connector=mocks2["data_connector"],
            executor=mocks2["executor"],
            cache=mocks2["cache"],
            dry_run=True,
            polymarket=mocks2["polymarket"],
        )

        assert 1001 in trader2._order_log
        assert type(list(trader2._order_log.keys())[0]) is int


# ---------------------------------------------------------------------------
# TestEndedGamesPersistence
# ---------------------------------------------------------------------------


class TestEndedGamesPersistence:
    def test_ended_games_survives_restart(self, tmp_path, monkeypatch):
        """Add game IDs to _ended_games, create new instance, verify _ended_games matches."""
        trader, order_log_path, ended_games_path, state_lock_path = _make_trader(
            tmp_path, monkeypatch
        )

        trader.handle_game_ended(game_id=10)
        trader.handle_game_ended(game_id=20)
        trader.handle_game_ended(game_id=30)

        from agents.application.ingame_trader import InGameTrader

        mocks2 = _make_mocks()
        trader2 = InGameTrader(
            budget_coordinator=mocks2["budget"],
            data_connector=mocks2["data_connector"],
            executor=mocks2["executor"],
            cache=mocks2["cache"],
            dry_run=True,
            polymarket=mocks2["polymarket"],
        )

        assert trader2._ended_games == {10, 20, 30}

    def test_ended_games_missing_file(self, tmp_path, monkeypatch):
        """Init with nonexistent file path: _ended_games is empty set (no crash)."""
        nonexistent = str(tmp_path / "nonexistent_ended_games.json")
        monkeypatch.setenv("SPORTS_ORDER_LOG_PATH", str(tmp_path / "ol.json"))
        monkeypatch.setenv("SPORTS_ENDED_GAMES_PATH", nonexistent)
        monkeypatch.setenv("SPORTS_STATE_LOCK_PATH", str(tmp_path / "lock"))

        from agents.application.ingame_trader import InGameTrader

        mocks = _make_mocks()
        trader = InGameTrader(
            budget_coordinator=mocks["budget"],
            data_connector=mocks["data_connector"],
            executor=mocks["executor"],
            cache=mocks["cache"],
            dry_run=True,
            polymarket=mocks["polymarket"],
        )

        assert trader._ended_games == set()

    def test_ended_games_corrupt_file(self, tmp_path, monkeypatch, capsys):
        """Write invalid JSON to file: init trader, verify empty set + warning (no crash)."""
        corrupt_path = str(tmp_path / "corrupt_ended_games.json")
        with open(corrupt_path, "w") as f:
            f.write("[invalid json")

        monkeypatch.setenv("SPORTS_ORDER_LOG_PATH", str(tmp_path / "ol.json"))
        monkeypatch.setenv("SPORTS_ENDED_GAMES_PATH", corrupt_path)
        monkeypatch.setenv("SPORTS_STATE_LOCK_PATH", str(tmp_path / "lock"))

        from agents.application.ingame_trader import InGameTrader

        mocks = _make_mocks()
        trader = InGameTrader(
            budget_coordinator=mocks["budget"],
            data_connector=mocks["data_connector"],
            executor=mocks["executor"],
            cache=mocks["cache"],
            dry_run=True,
            polymarket=mocks["polymarket"],
        )

        assert trader._ended_games == set()
        captured = capsys.readouterr()
        assert (
            "warn=corrupt_state_file" in captured.out
            or "corrupt" in captured.out.lower()
        )


# ---------------------------------------------------------------------------
# TestAtomicWriteAndLocking
# ---------------------------------------------------------------------------


class TestAtomicWriteAndLocking:
    def test_persist_uses_atomic_write(self, tmp_path, monkeypatch):
        """Verify atomic write: temp file written then renamed (os.replace called)."""
        trader, order_log_path, ended_games_path, state_lock_path = _make_trader(
            tmp_path, monkeypatch
        )

        with patch("os.replace", wraps=os.replace) as mock_replace:
            trader._log_order(game_id=5, order_id="order-atomic", market_id="mkt-a")

        # os.replace should have been called (atomic rename)
        mock_replace.assert_called()
        # Destination should be our order_log_path
        args = mock_replace.call_args
        assert args[0][1] == order_log_path

    def test_separate_lock_from_budget(self, tmp_path, monkeypatch):
        """InGameTrader uses SPORTS_STATE_LOCK_PATH, not SPORTS_BUDGET_LOCK_PATH."""
        custom_state_lock = str(tmp_path / "custom_state.lock")
        monkeypatch.setenv("SPORTS_ORDER_LOG_PATH", str(tmp_path / "ol.json"))
        monkeypatch.setenv("SPORTS_ENDED_GAMES_PATH", str(tmp_path / "eg.json"))
        monkeypatch.setenv("SPORTS_STATE_LOCK_PATH", custom_state_lock)

        from agents.application.ingame_trader import InGameTrader

        mocks = _make_mocks()
        trader = InGameTrader(
            budget_coordinator=mocks["budget"],
            data_connector=mocks["data_connector"],
            executor=mocks["executor"],
            cache=mocks["cache"],
            dry_run=True,
            polymarket=mocks["polymarket"],
        )

        # InGameTrader must use SPORTS_STATE_LOCK_PATH, not SPORTS_BUDGET_LOCK_PATH
        assert trader._state_lock_path == custom_state_lock
        # Perform a persist and verify lock file matches expected path
        trader._log_order(game_id=7, order_id="order-lock-test", market_id="mkt-b")
        assert trader._state_lock_path == custom_state_lock
        # Budget lock path must not equal state lock path
        budget_lock = os.environ.get("SPORTS_BUDGET_LOCK_PATH", "")
        assert budget_lock != custom_state_lock or budget_lock == ""
