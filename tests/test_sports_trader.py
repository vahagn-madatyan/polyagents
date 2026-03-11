"""Unit tests for SportsTrader orchestrator.

Tests cover: initialization, full pipeline flow, confidence gate,
budget gate, dry-run mode, live execution, error handling, and cache freshness gating.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers: build test fixtures
# ---------------------------------------------------------------------------


def _game_state(game_id: int = 1, ended: bool = False, league: str = "nba"):
    from agents.utils.objects import SportGameState

    return SportGameState(
        game_id=game_id,
        league=league,
        slug=f"nba-lal-bos-2026-03-07",
        home_team="LAL",
        away_team="BOS",
        status="scheduled",
        score_raw="0-0",
        period="Pre",
        live=False,
        ended=ended,
    )


def _market_tag():
    from agents.utils.objects import SportsMarketTag

    return SportsMarketTag(
        slug="nba-lal-bos-2026-03-07",
        league="nba",
        home_team="LAL",
        away_team="BOS",
        market_id="9001",
        condition_id="0xabc123",
        token_id_yes="tok-yes",
        token_id_no="tok-no",
        question="Will the Lakers win?",
        outcome_prices="0.6,0.4",
    )


def _candidate_trade(
    confidence_gap: float = 0.20,
    suggested_outcome: str = "Yes",
    parsed_side: str = "BUY",
    parsed_size_fraction: float = 0.05,
):
    from agents.utils.objects import CandidateTrade

    return CandidateTrade(
        market_id=9001,
        question="Will the Lakers win?",
        outcomes=["Yes", "No"],
        outcome_prices=[0.6, 0.4],
        token_ids=["tok-yes", "tok-no"],
        suggested_outcome=suggested_outcome,
        parsed_side=parsed_side,
        parsed_price=0.6,
        parsed_size_fraction=parsed_size_fraction,
        confidence_gap=confidence_gap,
        rationale="Strong home advantage based on stats.",
        probabilities=[
            {"outcome": "Yes", "likelihood": 0.75},
            {"outcome": "No", "likelihood": 0.25},
        ],
        risk_factors=["injury risk"],
        counter_case="Away team on hot streak",
        execution_status="NOT_EXECUTED",
        execution_response={
            "superforecast_response": "Home team has 75% chance",
            "trade_recommendation": '{"side": "BUY", "price": 0.6}',
        },
    )


def _make_mocks(
    confidence_gap=0.20, suggested_outcome="Yes", parsed_size_fraction=0.05
):
    """Return a dict of mocked dependencies for SportsTrader."""
    budget = MagicMock()
    budget.can_spend_sports.return_value = True
    budget.get_sport_cap.return_value = 100.0  # cap = $100

    data_connector = MagicMock()
    data_connector.get_game_context.return_value = {
        "stats": {"home_win_pct": 0.62},
        "h2h": [],
        "odds": {"home": 0.6},
    }

    candidate = _candidate_trade(
        confidence_gap=confidence_gap,
        suggested_outcome=suggested_outcome,
        parsed_size_fraction=parsed_size_fraction,
    )
    executor = MagicMock()
    executor.analyze_game.return_value = candidate

    cache = MagicMock()
    cache.is_fresh.return_value = False  # not fresh => should analyze

    polymarket = MagicMock()
    polymarket.execute_market_order_for_token.return_value = "order-123"

    return {
        "budget": budget,
        "data_connector": data_connector,
        "executor": executor,
        "cache": cache,
        "polymarket": polymarket,
        "candidate": candidate,
    }


def _make_trader(
    dry_run=True, mocks=None, min_confidence_gap_env=None, monkeypatch=None
):
    """Build a SportsTrader with mocked deps."""
    from agents.application.sports_trader import SportsTrader

    if mocks is None:
        mocks = _make_mocks()

    if min_confidence_gap_env is not None and monkeypatch is not None:
        monkeypatch.setenv("SPORTS_MIN_CONFIDENCE_GAP", str(min_confidence_gap_env))

    return (
        SportsTrader(
            budget_coordinator=mocks["budget"],
            data_connector=mocks["data_connector"],
            executor=mocks["executor"],
            cache=mocks["cache"],
            dry_run=dry_run,
            polymarket=mocks["polymarket"],
        ),
        mocks,
    )


# ---------------------------------------------------------------------------
# TestSportsTraderInit
# ---------------------------------------------------------------------------


class TestSportsTraderInit:
    def test_stores_all_attributes(self):
        """__init__() stores all dependency params as attributes."""
        from agents.application.sports_trader import SportsTrader

        budget = MagicMock()
        data_connector = MagicMock()
        executor = MagicMock()
        cache = MagicMock()
        polymarket = MagicMock()

        trader = SportsTrader(
            budget_coordinator=budget,
            data_connector=data_connector,
            executor=executor,
            cache=cache,
            dry_run=True,
            polymarket=polymarket,
        )

        assert trader.budget_coordinator is budget
        assert trader.data_connector is data_connector
        assert trader.executor is executor
        assert trader.cache is cache
        assert trader.dry_run is True
        assert trader.polymarket is polymarket

    def test_dry_run_false_stored(self):
        """__init__() stores dry_run=False correctly."""
        from agents.application.sports_trader import SportsTrader

        trader = SportsTrader(
            budget_coordinator=MagicMock(),
            data_connector=MagicMock(),
            executor=MagicMock(),
            cache=MagicMock(),
            dry_run=False,
            polymarket=MagicMock(),
        )
        assert trader.dry_run is False

    def test_default_min_confidence_gap(self, monkeypatch):
        """Default SPORTS_MIN_CONFIDENCE_GAP is 0.10 when env not set."""
        monkeypatch.delenv("SPORTS_MIN_CONFIDENCE_GAP", raising=False)
        from agents.application.sports_trader import SportsTrader

        trader = SportsTrader(
            budget_coordinator=MagicMock(),
            data_connector=MagicMock(),
            executor=MagicMock(),
            cache=MagicMock(),
            dry_run=True,
        )
        assert trader.min_confidence_gap == pytest.approx(0.10)

    def test_env_overrides_min_confidence_gap(self, monkeypatch):
        """SPORTS_MIN_CONFIDENCE_GAP env var overrides the default."""
        monkeypatch.setenv("SPORTS_MIN_CONFIDENCE_GAP", "0.25")
        from agents.application.sports_trader import SportsTrader

        trader = SportsTrader(
            budget_coordinator=MagicMock(),
            data_connector=MagicMock(),
            executor=MagicMock(),
            cache=MagicMock(),
            dry_run=True,
        )
        assert trader.min_confidence_gap == pytest.approx(0.25)

    def test_has_in_flight_set(self):
        """__init__() initializes _in_flight as an empty set."""
        from agents.application.sports_trader import SportsTrader

        trader = SportsTrader(
            budget_coordinator=MagicMock(),
            data_connector=MagicMock(),
            executor=MagicMock(),
            cache=MagicMock(),
            dry_run=True,
        )
        assert hasattr(trader, "_in_flight")
        assert isinstance(trader._in_flight, set)
        assert len(trader._in_flight) == 0

    def test_polymarket_optional(self):
        """polymarket param is optional (defaults to None)."""
        from agents.application.sports_trader import SportsTrader

        trader = SportsTrader(
            budget_coordinator=MagicMock(),
            data_connector=MagicMock(),
            executor=MagicMock(),
            cache=MagicMock(),
            dry_run=True,
        )
        assert trader.polymarket is None


# ---------------------------------------------------------------------------
# TestShouldAnalyze
# ---------------------------------------------------------------------------


class TestShouldAnalyze:
    def test_returns_false_when_cache_is_fresh(self):
        """should_analyze() returns False when cache.is_fresh() is True."""
        trader, mocks = _make_trader(dry_run=True)
        mocks["cache"].is_fresh.return_value = True

        assert trader.should_analyze(1) is False
        mocks["cache"].is_fresh.assert_called_once_with(1)

    def test_returns_true_when_cache_is_stale(self):
        """should_analyze() returns True when cache.is_fresh() is False."""
        trader, mocks = _make_trader(dry_run=True)
        mocks["cache"].is_fresh.return_value = False

        assert trader.should_analyze(1) is True


# ---------------------------------------------------------------------------
# TestRunPregameAnalysis (full pipeline)
# ---------------------------------------------------------------------------


class TestRunPregameAnalysis:
    def test_calls_get_game_context(self):
        """run_pregame_analysis() calls data_connector.get_game_context()."""
        trader, mocks = _make_trader(dry_run=True)
        gs = _game_state()
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        mocks["data_connector"].get_game_context.assert_called_once_with(gs)

    def test_calls_analyze_game(self):
        """run_pregame_analysis() calls executor.analyze_game() with game state, tag, and context."""
        trader, mocks = _make_trader(dry_run=True)
        gs = _game_state()
        tag = _market_tag()
        expected_ctx = mocks["data_connector"].get_game_context.return_value

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        mocks["executor"].analyze_game.assert_called_once_with(gs, tag, expected_ctx)

    def test_skips_when_analyze_game_returns_none(self):
        """run_pregame_analysis() returns without touching cache when analyze_game returns None."""
        trader, mocks = _make_trader(dry_run=True)
        mocks["executor"].analyze_game.return_value = None
        gs = _game_state()
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        mocks["cache"].set.assert_not_called()

    def test_writes_cache_before_trade(self, capsys):
        """run_pregame_analysis() writes cache entry BEFORE attempting trade execution."""
        call_order = []

        def record_cache_set(game_id, entry):
            call_order.append("cache_set")

        def record_execute(token_id, amount):
            call_order.append("trade_execute")
            return "order-ok"

        trader, mocks = _make_trader(dry_run=False)
        mocks["cache"].set.side_effect = record_cache_set
        mocks["polymarket"].execute_market_order_for_token.side_effect = record_execute
        gs = _game_state()
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        assert call_order.index("cache_set") < call_order.index("trade_execute")

    def test_cache_entry_has_required_fields(self):
        """run_pregame_analysis() cache entry contains all SportsAnalysisCache fields."""
        trader, mocks = _make_trader(dry_run=True)
        gs = _game_state()
        tag = _market_tag()
        captured_entry = {}

        def capture_set(game_id, entry):
            captured_entry.update(entry)

        mocks["cache"].set.side_effect = capture_set

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        required_fields = [
            "game_id",
            "league",
            "home_team",
            "away_team",
            "confidence_gap",
            "selected_outcome",
            "selected_side",
            "size_fraction",
            "rationale",
        ]
        for field in required_fields:
            assert field in captured_entry, f"Missing field: {field}"

    def test_skips_ended_games(self):
        """run_pregame_analysis() skips games where game_state.ended=True."""
        trader, mocks = _make_trader(dry_run=True)
        gs = _game_state(ended=True)
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        mocks["data_connector"].get_game_context.assert_not_called()
        mocks["executor"].analyze_game.assert_not_called()
        mocks["cache"].set.assert_not_called()

    def test_in_flight_guard_prevents_duplicate(self):
        """run_pregame_analysis() skips analysis if game_id is already in _in_flight."""
        trader, mocks = _make_trader(dry_run=True)
        gs = _game_state(game_id=42)
        tag = _market_tag()

        trader._in_flight.add(42)

        trader.run_pregame_analysis(42, gs, tag, wallet_balance=500.0)

        mocks["data_connector"].get_game_context.assert_not_called()

    def test_in_flight_cleared_after_completion(self):
        """game_id is removed from _in_flight after run_pregame_analysis completes."""
        trader, mocks = _make_trader(dry_run=True)
        gs = _game_state(game_id=7)
        tag = _market_tag()

        trader.run_pregame_analysis(7, gs, tag, wallet_balance=500.0)

        assert 7 not in trader._in_flight

    def test_computes_trade_amount_from_size_fraction_and_cap(self):
        """run_pregame_analysis() trade_amount = size_fraction * sport_cap."""
        mocks = _make_mocks(confidence_gap=0.20, parsed_size_fraction=0.05)
        mocks["budget"].get_sport_cap.return_value = 200.0  # $200 cap

        trader, mocks = _make_trader(dry_run=False, mocks=mocks)
        gs = _game_state()
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        # trade_amount = 0.05 * 200 = 10.0
        mocks["polymarket"].execute_market_order_for_token.assert_called_once_with(
            token_id="tok-yes",
            amount=pytest.approx(10.0),
        )


# ---------------------------------------------------------------------------
# TestConfidenceGate
# ---------------------------------------------------------------------------


class TestConfidenceGate:
    def test_skips_trade_below_threshold_but_writes_cache(self, monkeypatch):
        """run_pregame_analysis() skips trade but writes cache when confidence_gap < threshold."""
        monkeypatch.setenv("SPORTS_MIN_CONFIDENCE_GAP", "0.10")
        mocks = _make_mocks(confidence_gap=0.05)  # below 0.10 threshold
        trader, mocks = _make_trader(dry_run=False, mocks=mocks)
        gs = _game_state()
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        mocks["cache"].set.assert_called_once()
        mocks["polymarket"].execute_market_order_for_token.assert_not_called()

    def test_executes_trade_above_threshold(self, monkeypatch):
        """run_pregame_analysis() executes trade when confidence_gap >= threshold."""
        monkeypatch.setenv("SPORTS_MIN_CONFIDENCE_GAP", "0.10")
        mocks = _make_mocks(confidence_gap=0.15)  # above 0.10
        trader, mocks = _make_trader(dry_run=False, mocks=mocks)
        gs = _game_state()
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        mocks["polymarket"].execute_market_order_for_token.assert_called_once()


# ---------------------------------------------------------------------------
# TestBudgetGate
# ---------------------------------------------------------------------------


class TestBudgetGate:
    def test_skips_trade_when_cannot_spend_but_writes_cache(self):
        """run_pregame_analysis() skips trade but writes cache when budget exhausted."""
        mocks = _make_mocks(confidence_gap=0.20)
        mocks["budget"].can_spend_sports.return_value = False

        trader, mocks = _make_trader(dry_run=False, mocks=mocks)
        gs = _game_state()
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        mocks["cache"].set.assert_called_once()
        mocks["polymarket"].execute_market_order_for_token.assert_not_called()

    def test_skips_trade_when_zero_size_fraction(self):
        """run_pregame_analysis() skips trade when size_fraction is 0 (trade_amount <= 0)."""
        mocks = _make_mocks(confidence_gap=0.20, parsed_size_fraction=0.0)

        trader, mocks = _make_trader(dry_run=False, mocks=mocks)
        gs = _game_state()
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        mocks["cache"].set.assert_called_once()
        mocks["polymarket"].execute_market_order_for_token.assert_not_called()

    def test_can_spend_called_with_wallet_balance(self):
        """budget.can_spend_sports() is called with correct trade_amount and wallet_balance."""
        mocks = _make_mocks(confidence_gap=0.20, parsed_size_fraction=0.05)
        mocks["budget"].get_sport_cap.return_value = 100.0  # $100 cap

        trader, mocks = _make_trader(dry_run=False, mocks=mocks)
        gs = _game_state()
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=777.0)

        # trade_amount = 0.05 * 100 = 5.0
        mocks["budget"].can_spend_sports.assert_called_once_with(
            pytest.approx(5.0), 777.0
        )


# ---------------------------------------------------------------------------
# TestDryRun
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_does_not_call_execute(self, capsys):
        """dry_run=True does not call polymarket.execute_market_order_for_token()."""
        trader, mocks = _make_trader(dry_run=True)
        gs = _game_state()
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        mocks["polymarket"].execute_market_order_for_token.assert_not_called()

    def test_dry_run_logs_dry_run_output(self, capsys):
        """dry_run=True prints dry_run log line."""
        trader, mocks = _make_trader(dry_run=True)
        gs = _game_state()
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        captured = capsys.readouterr()
        assert "dry_run" in captured.out

    def test_dry_run_still_writes_cache(self):
        """dry_run=True still writes cache entry."""
        trader, mocks = _make_trader(dry_run=True)
        gs = _game_state()
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        mocks["cache"].set.assert_called_once()

    def test_dry_run_does_not_call_record_sports_trade(self):
        """dry_run=True does not call budget_coordinator.record_sports_trade()."""
        trader, mocks = _make_trader(dry_run=True)
        gs = _game_state()
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        mocks["budget"].record_sports_trade.assert_not_called()


# ---------------------------------------------------------------------------
# TestLiveExecution
# ---------------------------------------------------------------------------


class TestLiveExecution:
    def test_live_calls_execute_with_yes_token(self):
        """dry_run=False calls execute_market_order_for_token with token_id_yes for 'Yes' outcome."""
        mocks = _make_mocks(suggested_outcome="Yes")
        trader, mocks = _make_trader(dry_run=False, mocks=mocks)
        gs = _game_state()
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        call_args = mocks["polymarket"].execute_market_order_for_token.call_args
        assert call_args.kwargs["token_id"] == "tok-yes"

    def test_live_calls_execute_with_no_token(self):
        """dry_run=False calls execute_market_order_for_token with token_id_no for 'No' outcome."""
        mocks = _make_mocks(suggested_outcome="No")
        trader, mocks = _make_trader(dry_run=False, mocks=mocks)
        gs = _game_state()
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        call_args = mocks["polymarket"].execute_market_order_for_token.call_args
        assert call_args.kwargs["token_id"] == "tok-no"

    def test_live_calls_record_sports_trade_on_success(self):
        """dry_run=False calls budget_coordinator.record_sports_trade() after successful execution."""
        mocks = _make_mocks(parsed_size_fraction=0.05)
        mocks["budget"].get_sport_cap.return_value = 100.0  # trade_amount = 5.0
        trader, mocks = _make_trader(dry_run=False, mocks=mocks)
        gs = _game_state(league="nba")
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        mocks["budget"].record_sports_trade.assert_called_once_with(
            pytest.approx(5.0), "nba"
        )


# ---------------------------------------------------------------------------
# TestExecutionError
# ---------------------------------------------------------------------------


class TestExecutionError:
    def test_catches_execute_exception_without_crashing(self):
        """Exceptions from execute_market_order_for_token do not propagate."""
        mocks = _make_mocks()
        mocks["polymarket"].execute_market_order_for_token.side_effect = RuntimeError(
            "CLOB unavailable"
        )
        trader, mocks = _make_trader(dry_run=False, mocks=mocks)
        gs = _game_state()
        tag = _market_tag()

        # Should not raise
        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

    def test_logs_trade_error_to_cache_on_exception(self):
        """On trade execution error, cache entry is updated with trade_error field."""
        mocks = _make_mocks()
        mocks["polymarket"].execute_market_order_for_token.side_effect = RuntimeError(
            "network error"
        )
        trader, mocks = _make_trader(dry_run=False, mocks=mocks)
        gs = _game_state()
        tag = _market_tag()

        # Collect all cache.set calls
        set_calls = []
        mocks["cache"].set.side_effect = lambda gid, entry: set_calls.append(
            (gid, dict(entry))
        )

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        # Second set call should have trade_error
        assert len(set_calls) >= 2
        last_entry = set_calls[-1][1]
        assert "trade_error" in last_entry
        assert last_entry["trade_error"] is not None

    def test_does_not_call_record_sports_trade_on_error(self):
        """budget_coordinator.record_sports_trade() is NOT called when execution fails."""
        mocks = _make_mocks()
        mocks["polymarket"].execute_market_order_for_token.side_effect = RuntimeError(
            "timeout"
        )
        trader, mocks = _make_trader(dry_run=False, mocks=mocks)
        gs = _game_state()
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=500.0)

        mocks["budget"].record_sports_trade.assert_not_called()


# ---------------------------------------------------------------------------
# TestHaltGate (Phase 6)
# ---------------------------------------------------------------------------


class TestHaltGate:
    def test_suspended_skips_analysis(self):
        """run_pregame_analysis returns early when game_state.status is 'Suspended'."""
        from unittest.mock import patch as _patch

        trader, mocks = _make_trader(dry_run=True)
        gs = _game_state()
        gs.status = "Suspended"
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=100.0)

        assert gs.game_id not in trader._in_flight
        mocks["data_connector"].get_game_context.assert_not_called()

    def test_forfeit_skips_analysis(self):
        """run_pregame_analysis returns early when game_state.status is 'Forfeit'."""
        trader, mocks = _make_trader(dry_run=True)
        gs = _game_state()
        gs.status = "Forfeit"
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=100.0)

        assert gs.game_id not in trader._in_flight
        mocks["data_connector"].get_game_context.assert_not_called()

    def test_scheduled_proceeds_normally(self):
        """run_pregame_analysis proceeds normally when game_state.status is 'scheduled'."""
        from unittest.mock import patch as _patch

        trader, mocks = _make_trader(dry_run=True)
        gs = _game_state()
        gs.status = "scheduled"
        tag = _market_tag()

        with _patch.object(trader, "_analyze_and_trade") as mock_aat:
            trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=100.0)
            mock_aat.assert_called_once()

    def test_halted_logs_trading_halted(self, capsys):
        """run_pregame_analysis logs event=trading_halted when status is a halt status."""
        trader, mocks = _make_trader(dry_run=True)
        gs = _game_state()
        gs.status = "Suspended"
        tag = _market_tag()

        trader.run_pregame_analysis(gs.game_id, gs, tag, wallet_balance=100.0)

        captured = capsys.readouterr()
        assert "trading_halted" in captured.out
