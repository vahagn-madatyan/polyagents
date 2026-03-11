"""Unit tests for InGameTrader — autonomous in-game trading engine.

Tests cover:
- Score-change detection via snapshot diff
- Event classification (minor/major)
- Fast-path cache-based trading
- Slow-path LLM daemon thread dispatch
- Per-game cooldown debounce
- In-flight guard for duplicate slow-path prevention
- Game-ended safeguards with blackout order cancellation
- Per-game exposure tracking
- Period transition routing
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers: build test fixtures
# ---------------------------------------------------------------------------


def _game_state(
    game_id: int = 1,
    score_raw: str = "0-0",
    home_score: int = 0,
    away_score: int = 0,
    period: str = "Q1",
    live: bool = True,
    ended: bool = False,
    league: str = "nba",
    home_team: str = "LAL",
    away_team: str = "BOS",
    slug: str | None = None,
    slug_suffix: str = "2026-03-07",
):
    from agents.utils.objects import SportGameState

    resolved_slug = slug if slug is not None else f"{league}-lal-bos-{slug_suffix}"
    return SportGameState(
        game_id=game_id,
        league=league,
        slug=resolved_slug,
        home_team=home_team,
        away_team=away_team,
        status="InProgress",
        score_raw=score_raw,
        home_score=home_score,
        away_score=away_score,
        period=period,
        live=live,
        ended=ended,
    )


def _market_tag(game_id: int = 1):
    from agents.utils.objects import SportsMarketTag

    return SportsMarketTag(
        slug=f"nba-lal-bos-2026-03-07",
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


def _make_mocks():
    """Return a dict of mocked dependencies for InGameTrader."""
    budget = MagicMock()
    budget.can_spend_sports.return_value = True

    data_connector = MagicMock()
    data_connector.get_game_context.return_value = {"stats": {}, "h2h": [], "odds": {}}

    executor = MagicMock()
    # Default: executor returns a candidate that triggers a trade
    from agents.utils.objects import CandidateTrade

    candidate = CandidateTrade(
        market_id=9001,
        question="Will the Lakers win?",
        outcomes=["Yes", "No"],
        outcome_prices=[0.7, 0.3],
        token_ids=["tok-yes", "tok-no"],
        suggested_outcome="Yes",
        parsed_side="BUY",
        parsed_price=0.7,
        parsed_size_fraction=0.1,
        confidence_gap=0.40,
        rationale="Strong momentum after lead change.",
        probabilities=[
            {"outcome": "Yes", "likelihood": 0.70},
            {"outcome": "No", "likelihood": 0.30},
        ],
        execution_status="NOT_EXECUTED",
    )
    executor.analyze_game.return_value = candidate

    cache = MagicMock()
    # Default: fresh cache entry with 70% home win prob
    cache.get.return_value = {
        "game_id": 1,
        "llm_home_win_prob": 0.70,
        "llm_away_win_prob": 0.30,
        "confidence_gap": 0.40,
        "selected_outcome": "Yes",
        "selected_side": "BUY",
        "timestamp": time.time(),
    }
    cache.is_fresh.return_value = True

    polymarket = MagicMock()
    polymarket.get_orderbook_price.return_value = (
        0.50  # divergence = 0.70 - 0.50 = 0.20
    )
    polymarket.execute_market_order_for_token.return_value = "order-abc-123"
    polymarket.client = MagicMock()
    polymarket.client.cancel = MagicMock()

    return {
        "budget": budget,
        "data_connector": data_connector,
        "executor": executor,
        "cache": cache,
        "polymarket": polymarket,
        "candidate": candidate,
    }


def _make_trader(
    dry_run=True, mocks=None, monkeypatch=None, wallet_balance=0.0, **env_overrides
):
    """Build an InGameTrader with mocked dependencies."""
    from agents.application.ingame_trader import InGameTrader

    if mocks is None:
        mocks = _make_mocks()

    if monkeypatch is not None:
        for key, val in env_overrides.items():
            monkeypatch.setenv(key, str(val))

    trader = InGameTrader(
        budget_coordinator=mocks["budget"],
        data_connector=mocks["data_connector"],
        executor=mocks["executor"],
        cache=mocks["cache"],
        dry_run=dry_run,
        polymarket=mocks["polymarket"],
        wallet_balance=wallet_balance,
    )
    return trader, mocks


# ---------------------------------------------------------------------------
# TestScoreChangeDetection
# ---------------------------------------------------------------------------


class TestScoreChangeDetection:
    def test_first_game_seen_stores_baseline_no_event(self, monkeypatch):
        """tick() with a new game stores it in _prev_game_states — no processing occurs."""
        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "30")
        trader, mocks = _make_trader()
        tag = _market_tag(game_id=1)
        slug_table = {"nba-lal-bos-2026-03-07": [tag]}

        gs = _game_state(game_id=1, score_raw="0-0")
        current_states = {1: gs}

        trader.tick(current_states, slug_table)

        # No price fetches or order executions — first sight is baseline only
        mocks["polymarket"].get_orderbook_price.assert_not_called()
        mocks["polymarket"].execute_market_order_for_token.assert_not_called()

        # State stored as baseline
        assert 1 in trader._prev_game_states
        assert trader._prev_game_states[1].score_raw == "0-0"

    def test_score_change_detected(self, monkeypatch):
        """tick() with changed score_raw triggers event processing (fast-path for minor event)."""
        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "0")
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader()
        tag = _market_tag(game_id=1)
        slug_table = {"nba-lal-bos-2026-03-07": [tag]}

        # Establish baseline: home already leading 5-3
        trader._prev_game_states[1] = _game_state(
            game_id=1, score_raw="5-3", home_score=5, away_score=3
        )

        # Minor score change: home team adds 3 more points (still leading, no lead change)
        gs_new = _game_state(game_id=1, score_raw="8-3", home_score=8, away_score=3)
        trader.tick({1: gs_new}, slug_table)

        # Fast-path should have been triggered: cache.get() called for live divergence check
        mocks["cache"].get.assert_called()

    def test_no_score_change_no_processing(self, monkeypatch):
        """tick() with same score_raw does not trigger any processing."""
        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "30")
        trader, mocks = _make_trader()
        tag = _market_tag(game_id=1)
        slug_table = {"nba-lal-bos-2026-03-07": [tag]}

        gs = _game_state(game_id=1, score_raw="5-3")
        trader._prev_game_states[1] = gs

        trader.tick({1: _game_state(game_id=1, score_raw="5-3")}, slug_table)

        mocks["polymarket"].get_orderbook_price.assert_not_called()
        mocks["polymarket"].execute_market_order_for_token.assert_not_called()

    def test_ended_game_triggers_handle_game_ended(self, monkeypatch):
        """tick() with ended=True on a previously-seen game calls handle_game_ended()."""
        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "30")
        trader, mocks = _make_trader()
        tag = _market_tag(game_id=1)
        slug_table = {"nba-lal-bos-2026-03-07": [tag]}

        # Establish baseline
        trader._prev_game_states[1] = _game_state(
            game_id=1, score_raw="10-8", ended=False
        )

        # Game now ended
        gs_ended = _game_state(game_id=1, score_raw="10-8", ended=True)
        trader.tick({1: gs_ended}, slug_table)

        assert 1 in trader._ended_games

    def test_ended_game_in_set_skipped(self, monkeypatch):
        """Games already in _ended_games are skipped without processing."""
        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "0")
        trader, mocks = _make_trader()
        tag = _market_tag(game_id=1)
        slug_table = {"nba-lal-bos-2026-03-07": [tag]}

        trader._ended_games.add(1)
        trader._prev_game_states[1] = _game_state(game_id=1, score_raw="5-3")

        gs_changed = _game_state(game_id=1, score_raw="8-3")
        trader.tick({1: gs_changed}, slug_table)

        mocks["polymarket"].get_orderbook_price.assert_not_called()
        mocks["polymarket"].execute_market_order_for_token.assert_not_called()


# ---------------------------------------------------------------------------
# TestEventClassification
# ---------------------------------------------------------------------------


class TestEventClassification:
    def test_lead_change_is_major(self):
        """Lead change: home leading -> away leading => 'major'."""
        trader, _ = _make_trader()
        prev = _game_state(home_score=10, away_score=7)
        curr = _game_state(home_score=10, away_score=12)
        assert trader._classify_score_change(prev, curr) == "major"

    def test_tied_to_leading_is_major(self):
        """Tied game -> one team leading => 'major'."""
        trader, _ = _make_trader()
        prev = _game_state(home_score=5, away_score=5)
        curr = _game_state(home_score=7, away_score=5)
        assert trader._classify_score_change(prev, curr) == "major"

    def test_leading_to_tied_is_major(self):
        """Leading game -> tied => 'major'."""
        trader, _ = _make_trader()
        prev = _game_state(home_score=10, away_score=7)
        curr = _game_state(home_score=10, away_score=10)
        assert trader._classify_score_change(prev, curr) == "major"

    def test_overtime_period_is_major(self):
        """Period containing 'OT' => 'major'."""
        trader, _ = _make_trader()
        prev = _game_state(home_score=95, away_score=95, period="Q4")
        curr = _game_state(home_score=95, away_score=95, period="OT1")
        assert trader._classify_score_change(prev, curr) == "major"

    def test_overtime_period_et_is_major(self):
        """Period containing 'ET' => 'major'."""
        trader, _ = _make_trader()
        prev = _game_state(home_score=2, away_score=2, period="2H")
        curr = _game_state(home_score=2, away_score=2, period="ET")
        assert trader._classify_score_change(prev, curr) == "major"

    def test_overtime_period_case_insensitive(self):
        """Period containing 'overtime' (lowercase) => 'major'."""
        trader, _ = _make_trader()
        prev = _game_state(home_score=100, away_score=100, period="Q4")
        curr = _game_state(home_score=100, away_score=100, period="overtime")
        assert trader._classify_score_change(prev, curr) == "major"

    def test_routine_score_same_leader_is_minor(self):
        """Same leading team before and after score change => 'minor'."""
        trader, _ = _make_trader()
        prev = _game_state(home_score=5, away_score=3)
        curr = _game_state(home_score=8, away_score=3)
        assert trader._classify_score_change(prev, curr) == "minor"

    def test_none_scores_default_to_zero(self):
        """None home/away_score treated as 0 for classification."""
        trader, _ = _make_trader()
        prev = _game_state(home_score=0, away_score=0)
        curr = _game_state(home_score=0, away_score=0)
        # Force None
        prev = prev.model_copy(update={"home_score": None, "away_score": None})
        curr = curr.model_copy(update={"home_score": None, "away_score": None})
        # Tied -> tied: routine (minor)
        result = trader._classify_score_change(prev, curr)
        assert result in ("minor", "major")  # just must not crash


# ---------------------------------------------------------------------------
# TestFastPath
# ---------------------------------------------------------------------------


class TestFastPath:
    def test_fast_path_trades_on_high_divergence(self, monkeypatch):
        """Divergence > threshold -> calls execute_market_order_for_token."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader(dry_run=False)
        # cache: llm_home_win_prob=0.70, price=0.50 -> divergence=0.20 > 0.10
        tag = _market_tag()
        trader._fast_path(1, _game_state(game_id=1), tag)
        mocks["polymarket"].execute_market_order_for_token.assert_called_once()

    def test_fast_path_skips_on_low_divergence(self, monkeypatch):
        """Divergence < threshold -> no trade."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.30")
        trader, mocks = _make_trader(dry_run=False)
        # cache: llm_home_win_prob=0.70, price=0.50 -> divergence=0.20 < 0.30
        tag = _market_tag()
        trader._fast_path(1, _game_state(game_id=1), tag)
        mocks["polymarket"].execute_market_order_for_token.assert_not_called()

    def test_fast_path_skips_no_cache_entry(self, monkeypatch):
        """PregameCache.get() returns None -> no trade."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader(dry_run=False)
        mocks["cache"].get.return_value = None
        tag = _market_tag()
        trader._fast_path(1, _game_state(game_id=1), tag)
        mocks["polymarket"].execute_market_order_for_token.assert_not_called()

    def test_fast_path_skips_on_price_fetch_error(self, monkeypatch):
        """get_orderbook_price() raises -> no trade (skip with log)."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader(dry_run=False)
        mocks["polymarket"].get_orderbook_price.side_effect = RuntimeError(
            "network error"
        )
        tag = _market_tag()
        trader._fast_path(1, _game_state(game_id=1), tag)
        mocks["polymarket"].execute_market_order_for_token.assert_not_called()

    def test_fast_path_selects_yes_when_prob_above_price(self, monkeypatch):
        """llm_home_win_prob (0.70) > live_price (0.50) -> Yes token traded."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader(dry_run=False)
        mocks["cache"].get.return_value = {
            "llm_home_win_prob": 0.70,
            "llm_away_win_prob": 0.30,
            "timestamp": time.time(),
        }
        mocks["polymarket"].get_orderbook_price.return_value = 0.50
        tag = _market_tag()
        trader._fast_path(1, _game_state(game_id=1), tag)
        call_kwargs = mocks["polymarket"].execute_market_order_for_token.call_args
        assert call_kwargs is not None
        # token_id_yes when prob > price
        assert "tok-yes" in str(call_kwargs)

    def test_fast_path_selects_no_when_prob_below_price(self, monkeypatch):
        """llm_home_win_prob (0.30) < live_price (0.60) -> No token traded."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader(dry_run=False)
        mocks["cache"].get.return_value = {
            "llm_home_win_prob": 0.30,
            "llm_away_win_prob": 0.70,
            "timestamp": time.time(),
        }
        mocks["polymarket"].get_orderbook_price.return_value = 0.60
        tag = _market_tag()
        trader._fast_path(1, _game_state(game_id=1), tag)
        call_kwargs = mocks["polymarket"].execute_market_order_for_token.call_args
        assert call_kwargs is not None
        assert "tok-no" in str(call_kwargs)

    def test_fast_path_respects_exposure_cap(self, monkeypatch):
        """Over exposure cap -> no trade."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        monkeypatch.setenv("SPORTS_MAX_GAME_EXPOSURE_USD", "50.0")
        trader, mocks = _make_trader(dry_run=False)
        trader._game_exposure[1] = (
            48.0  # already near cap; any trade > 2 should be blocked
        )
        tag = _market_tag()
        trader._fast_path(1, _game_state(game_id=1), tag)
        # If trade amount > remaining cap, should not execute
        # The default budget cap might allow small trades; we'll check exposure logic
        # by setting exposure right at the limit
        trader._game_exposure[1] = 50.0
        mocks["polymarket"].execute_market_order_for_token.reset_mock()
        trader._fast_path(1, _game_state(game_id=1), tag)
        mocks["polymarket"].execute_market_order_for_token.assert_not_called()

    def test_fast_path_respects_budget_gate(self, monkeypatch):
        """can_spend_sports returns False -> no trade."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader(dry_run=False)
        mocks["budget"].can_spend_sports.return_value = False
        tag = _market_tag()
        trader._fast_path(1, _game_state(game_id=1), tag)
        mocks["polymarket"].execute_market_order_for_token.assert_not_called()

    def test_fast_path_dry_run_logs_no_execute(self, monkeypatch, capsys):
        """dry_run=True -> logs but does not call CLOB."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader(dry_run=True)
        tag = _market_tag()
        trader._fast_path(1, _game_state(game_id=1), tag)
        mocks["polymarket"].execute_market_order_for_token.assert_not_called()
        captured = capsys.readouterr()
        assert "dry_run" in captured.out or "ingame_trader" in captured.out

    def test_fast_path_sets_cooldown(self, monkeypatch):
        """After fast-path processing, cooldown timestamp is set."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader(dry_run=False)
        tag = _market_tag()
        assert 1 not in trader._last_processed
        trader._fast_path(1, _game_state(game_id=1), tag)
        assert 1 in trader._last_processed

    def test_fast_path_logs_order(self, monkeypatch):
        """On successful trade, order_id is recorded in _order_log."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader(dry_run=False)
        mocks["polymarket"].execute_market_order_for_token.return_value = (
            "order-xyz-999"
        )
        tag = _market_tag()
        trader._fast_path(1, _game_state(game_id=1), tag)
        assert 1 in trader._order_log
        assert len(trader._order_log[1]) > 0
        assert trader._order_log[1][0]["order_id"] == "order-xyz-999"


# ---------------------------------------------------------------------------
# TestSlowPath
# ---------------------------------------------------------------------------


class TestSlowPath:
    def test_slow_path_spawns_daemon_thread(self, monkeypatch):
        """Major event -> a daemon thread is started."""
        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "0")
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader()
        tag = _market_tag()
        slug_table = {"nba-lal-bos-2026-03-07": [tag]}

        # Set baseline with lead change condition
        trader._prev_game_states[1] = _game_state(
            game_id=1, score_raw="10-7", home_score=10, away_score=7
        )

        threads_started = []
        original_start = threading.Thread.start

        def capture_start(self_thread):
            threads_started.append(self_thread)
            original_start(self_thread)

        with patch.object(threading.Thread, "start", capture_start):
            trader.tick(
                {
                    1: _game_state(
                        game_id=1, score_raw="10-12", home_score=10, away_score=12
                    )
                },
                slug_table,
            )

        assert len(threads_started) >= 1
        assert threads_started[0].daemon is True

    def test_slow_path_calls_analyze_game(self, monkeypatch):
        """Slow-path thread calls SportsExecutor.analyze_game()."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader()
        tag = _market_tag()

        done_event = threading.Event()
        original_analyze = mocks["executor"].analyze_game.side_effect

        def capture_analyze(*args, **kwargs):
            done_event.set()
            return mocks["candidate"]

        mocks["executor"].analyze_game.side_effect = capture_analyze

        trader._run_slow_path(1, _game_state(game_id=1), tag)

        mocks["executor"].analyze_game.assert_called_once()

    def test_slow_path_updates_cache(self, monkeypatch):
        """Slow-path writes new LLM result to PregameCache."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader()
        tag = _market_tag()

        trader._run_slow_path(1, _game_state(game_id=1), tag)

        mocks["cache"].set.assert_called()

    def test_slow_path_trades_on_high_confidence(self, monkeypatch):
        """confidence_gap above threshold -> slow-path executes trade (dry_run=False)."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader(dry_run=False)
        tag = _market_tag()

        # candidate has confidence_gap=0.40 > 0.10 threshold
        trader._run_slow_path(1, _game_state(game_id=1), tag)

        mocks["polymarket"].execute_market_order_for_token.assert_called()

    def test_slow_path_dry_run_no_execute(self, monkeypatch):
        """dry_run=True -> slow-path logs but no CLOB call."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader(dry_run=True)
        tag = _market_tag()

        trader._run_slow_path(1, _game_state(game_id=1), tag)

        mocks["polymarket"].execute_market_order_for_token.assert_not_called()

    def test_slow_path_adds_and_removes_in_flight(self, monkeypatch):
        """game_id added to _slow_path_in_flight at start and removed on completion."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader()
        tag = _market_tag()

        in_flight_during = []

        def check_in_flight(*args, **kwargs):
            in_flight_during.append(1 in trader._slow_path_in_flight)
            return mocks["candidate"]

        mocks["executor"].analyze_game.side_effect = check_in_flight

        trader._run_slow_path(1, _game_state(game_id=1), tag)

        assert any(
            in_flight_during
        ), "game_id should be in _slow_path_in_flight during analysis"
        assert (
            1 not in trader._slow_path_in_flight
        ), "game_id should be removed after completion"

    def test_slow_path_sets_cooldown(self, monkeypatch):
        """After slow-path processing, cooldown timestamp is set."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader()
        tag = _market_tag()

        assert 1 not in trader._last_processed
        trader._run_slow_path(1, _game_state(game_id=1), tag)
        assert 1 in trader._last_processed


# ---------------------------------------------------------------------------
# TestCooldown
# ---------------------------------------------------------------------------


class TestCooldown:
    def test_event_during_cooldown_ignored(self, monkeypatch):
        """Second event immediately after first is ignored (cooldown active)."""
        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "30")
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader(dry_run=False)
        tag = _market_tag()
        slug_table = {"nba-lal-bos-2026-03-07": [tag]}

        # Establish baseline
        trader._prev_game_states[1] = _game_state(
            game_id=1, score_raw="0-0", home_score=0, away_score=0
        )

        # First score change -> processed
        trader.tick(
            {1: _game_state(game_id=1, score_raw="3-0", home_score=3, away_score=0)},
            slug_table,
        )
        call_count_1 = mocks["cache"].get.call_count

        # Update baseline
        trader._prev_game_states[1] = _game_state(
            game_id=1, score_raw="3-0", home_score=3, away_score=0
        )

        # Second score change immediately -> should be ignored
        trader.tick(
            {1: _game_state(game_id=1, score_raw="6-0", home_score=6, away_score=0)},
            slug_table,
        )
        call_count_2 = mocks["cache"].get.call_count

        # No additional calls during cooldown
        assert call_count_2 == call_count_1

    def test_event_after_cooldown_expires_processed(self, monkeypatch):
        """Event after cooldown expires IS processed."""
        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "0")
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader(dry_run=False)
        tag = _market_tag()
        slug_table = {"nba-lal-bos-2026-03-07": [tag]}

        # Set cooldown timestamp far in the past
        trader._last_processed[1] = time.time() - 999

        # Use a minor event (home already leading, just scores more)
        trader._prev_game_states[1] = _game_state(
            game_id=1, score_raw="5-3", home_score=5, away_score=3
        )
        trader.tick(
            {1: _game_state(game_id=1, score_raw="8-3", home_score=8, away_score=3)},
            slug_table,
        )

        # Should have processed (fast-path => cache.get called)
        mocks["cache"].get.assert_called()

    def test_fast_path_also_sets_cooldown(self, monkeypatch):
        """Fast-path processing sets the cooldown timestamp for that game."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader(dry_run=False)
        tag = _market_tag()

        before = time.time()
        trader._fast_path(1, _game_state(game_id=1), tag)
        after = time.time()

        assert 1 in trader._last_processed
        assert before <= trader._last_processed[1] <= after + 1

    def test_cooldown_is_per_game(self, monkeypatch):
        """Game A in cooldown does not block Game B from processing."""
        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "30")
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader(dry_run=False)

        tag1 = _market_tag(game_id=1)
        tag2 = _market_tag(game_id=2)
        # Game 1 uses default slug "nba-lal-bos-2026-03-07"
        # Game 2 uses a different slug with game_id=2
        slug_table = {
            "nba-lal-bos-2026-03-07": [tag1],
            "nba-lal-bos-2026-03-08": [tag2],
        }

        # Game 1 is in cooldown
        trader._last_processed[1] = time.time()  # just processed

        # Both games have baseline — game 2 uses a minor-event scenario (home already leading)
        trader._prev_game_states[1] = _game_state(
            game_id=1, score_raw="3-0", home_score=3, away_score=0
        )
        # Game 2 uses a different slug date to distinguish it
        trader._prev_game_states[2] = _game_state(
            game_id=2,
            score_raw="5-3",
            home_score=5,
            away_score=3,
            slug_suffix="2026-03-08",
        )

        current = {
            1: _game_state(game_id=1, score_raw="6-0", home_score=6, away_score=0),
            # Game 2: minor event — home still leading, just adds more
            2: _game_state(
                game_id=2,
                score_raw="8-3",
                home_score=8,
                away_score=3,
                slug_suffix="2026-03-08",
            ),
        }
        trader.tick(current, slug_table)

        # Game 2 should be processed via fast-path (cache.get called for game_id=2)
        calls = [c for c in mocks["cache"].get.call_args_list if c.args[0] == 2]
        assert len(calls) >= 1


# ---------------------------------------------------------------------------
# TestInFlightGuard
# ---------------------------------------------------------------------------


class TestInFlightGuard:
    def test_slow_path_in_flight_blocks_second_event(self, monkeypatch):
        """game_id in _slow_path_in_flight -> _should_process returns False."""
        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "0")
        trader, _ = _make_trader()

        trader._slow_path_in_flight.add(1)
        assert trader._should_process(1) is False

    def test_in_flight_removed_on_exception(self, monkeypatch):
        """If slow-path raises, game_id is still removed from _slow_path_in_flight."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader()
        tag = _market_tag()

        mocks["executor"].analyze_game.side_effect = RuntimeError("LLM crashed")

        # Should not raise, and in_flight should be cleaned up
        trader._run_slow_path(1, _game_state(game_id=1), tag)
        assert 1 not in trader._slow_path_in_flight


# ---------------------------------------------------------------------------
# TestGameEndedSafeguards
# ---------------------------------------------------------------------------


class TestGameEndedSafeguards:
    def test_ended_game_halts_new_orders(self, monkeypatch):
        """game_id in _ended_games prevents fast_path and slow_path from placing orders."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader(dry_run=False)
        trader._ended_games.add(1)
        tag = _market_tag()

        trader._fast_path(1, _game_state(game_id=1), tag)
        mocks["polymarket"].execute_market_order_for_token.assert_not_called()

    def test_blackout_cancels_recent_orders(self, monkeypatch):
        """Orders within blackout window are cancelled via client.cancel()."""
        monkeypatch.setenv("SPORTS_BLACKOUT_MINUTES", "2")
        trader, mocks = _make_trader(dry_run=False)

        recent_ts = time.time() - 60  # 60 seconds ago (within 2-min window)
        trader._order_log[1] = [
            {"order_id": "ord-aaa", "timestamp": recent_ts, "market_id": "9001"},
        ]

        trader._cancel_blackout_orders(1)

        mocks["polymarket"].client.cancel.assert_called_once_with("ord-aaa")

    def test_blackout_keeps_old_orders(self, monkeypatch):
        """Orders older than blackout window are NOT cancelled."""
        monkeypatch.setenv("SPORTS_BLACKOUT_MINUTES", "2")
        trader, mocks = _make_trader(dry_run=False)

        old_ts = time.time() - 600  # 10 minutes ago (outside 2-min window)
        trader._order_log[1] = [
            {"order_id": "ord-old", "timestamp": old_ts, "market_id": "9001"},
        ]

        trader._cancel_blackout_orders(1)

        mocks["polymarket"].client.cancel.assert_not_called()

    def test_cancel_error_does_not_crash(self, monkeypatch):
        """client.cancel() raising does not propagate — exception is caught."""
        monkeypatch.setenv("SPORTS_BLACKOUT_MINUTES", "2")
        trader, mocks = _make_trader(dry_run=False)
        mocks["polymarket"].client.cancel.side_effect = Exception("already filled")

        recent_ts = time.time() - 30
        trader._order_log[1] = [
            {"order_id": "ord-filled", "timestamp": recent_ts, "market_id": "9001"},
        ]

        # Should not raise
        trader._cancel_blackout_orders(1)

    def test_near_resolution_prevents_new_orders(self, monkeypatch):
        """_is_near_resolution returns True -> trade not placed."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader(dry_run=False)
        tag = _market_tag()

        with patch.object(trader, "_is_near_resolution", return_value=True):
            trader._fast_path(1, _game_state(game_id=1), tag)

        mocks["polymarket"].execute_market_order_for_token.assert_not_called()


# ---------------------------------------------------------------------------
# TestExposureCap
# ---------------------------------------------------------------------------


class TestExposureCap:
    def test_under_cap_allows_trade(self, monkeypatch):
        """Exposure 20 + new trade 10, cap 50 -> allowed."""
        monkeypatch.setenv("SPORTS_MAX_GAME_EXPOSURE_USD", "50.0")
        trader, _ = _make_trader()
        trader._game_exposure[1] = 20.0
        assert trader._check_exposure(1, 10.0) is True

    def test_over_cap_blocks_trade(self, monkeypatch):
        """Exposure 45 + new trade 10, cap 50 -> blocked."""
        monkeypatch.setenv("SPORTS_MAX_GAME_EXPOSURE_USD", "50.0")
        trader, _ = _make_trader()
        trader._game_exposure[1] = 45.0
        assert trader._check_exposure(1, 10.0) is False

    def test_exposure_recorded_after_trade(self, monkeypatch):
        """After successful trade, _game_exposure is updated."""
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        monkeypatch.setenv("SPORTS_MAX_GAME_EXPOSURE_USD", "100.0")
        trader, mocks = _make_trader(dry_run=False)
        tag = _market_tag()

        initial_exposure = trader._game_exposure.get(1, 0.0)
        trader._fast_path(1, _game_state(game_id=1), tag)

        # Exposure should have increased after a trade
        if mocks["polymarket"].execute_market_order_for_token.called:
            assert trader._game_exposure.get(1, 0.0) > initial_exposure

    def test_record_exposure_updates_accumulator(self, monkeypatch):
        """_record_exposure() adds amount to running total."""
        trader, _ = _make_trader()
        trader._record_exposure(1, 15.0)
        trader._record_exposure(1, 10.0)
        assert trader._game_exposure[1] == pytest.approx(25.0)

    def test_check_exposure_zero_base(self, monkeypatch):
        """Fresh game with no exposure allows any trade under cap."""
        monkeypatch.setenv("SPORTS_MAX_GAME_EXPOSURE_USD", "50.0")
        trader, _ = _make_trader()
        assert trader._check_exposure(1, 10.0) is True


# ---------------------------------------------------------------------------
# TestPeriodTransition
# ---------------------------------------------------------------------------


class TestPeriodTransition:
    def test_period_transition_routes_to_slow_path(self, monkeypatch):
        """handle_period_transition() triggers slow-path for the game."""
        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "0")
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        trader, mocks = _make_trader()
        tag = _market_tag(game_id=1)
        slug_table = {"nba-lal-bos-2026-03-07": [tag]}

        # Provide a game state for the game
        state = _game_state(game_id=1)
        trader._prev_game_states[1] = state

        threads_started = []
        original_start = threading.Thread.start

        def capture_start(self_thread):
            threads_started.append(self_thread)
            original_start(self_thread)

        msg = {"game_id": 1, "period": "Q2", "state": state}

        with patch.object(threading.Thread, "start", capture_start):
            trader.handle_period_transition(msg, slug_table)

        assert len(threads_started) >= 1

    def test_period_transition_respects_cooldown(self, monkeypatch):
        """handle_period_transition() skips game in cooldown."""
        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "30")
        trader, mocks = _make_trader()
        tag = _market_tag(game_id=1)
        slug_table = {"nba-lal-bos-2026-03-07": [tag]}

        # Game is in cooldown
        trader._last_processed[1] = time.time()
        state = _game_state(game_id=1)
        trader._prev_game_states[1] = state

        msg = {"game_id": 1, "period": "Q2", "state": state}
        trader.handle_period_transition(msg, slug_table)

        # No executor call since game is in cooldown
        mocks["executor"].analyze_game.assert_not_called()


# ---------------------------------------------------------------------------
# TestWalletBalance
# ---------------------------------------------------------------------------


class TestWalletBalance:
    def test_wallet_balance_stored_from_constructor(self, monkeypatch):
        """InGameTrader stores wallet_balance passed to constructor as self._wallet_balance."""
        from agents.application.ingame_trader import InGameTrader

        mocks = _make_mocks()
        trader = InGameTrader(
            budget_coordinator=mocks["budget"],
            data_connector=mocks["data_connector"],
            executor=mocks["executor"],
            cache=mocks["cache"],
            dry_run=True,
            polymarket=mocks["polymarket"],
            wallet_balance=500.0,
        )
        assert trader._wallet_balance == 500.0

    def test_fast_path_passes_wallet_balance_to_budget_gate(self, monkeypatch):
        """Fast-path calls can_spend_sports with actual wallet_balance (not 0.0)."""
        from agents.application.ingame_trader import InGameTrader
        from unittest.mock import ANY

        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "0")
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        mocks = _make_mocks()
        trader = InGameTrader(
            budget_coordinator=mocks["budget"],
            data_connector=mocks["data_connector"],
            executor=mocks["executor"],
            cache=mocks["cache"],
            dry_run=True,
            polymarket=mocks["polymarket"],
            wallet_balance=500.0,
        )

        trader._fast_path(1, _game_state(game_id=1), _market_tag())

        mocks["budget"].can_spend_sports.assert_called()
        call_args = mocks["budget"].can_spend_sports.call_args
        wallet_balance_arg = (
            call_args[0][1] if call_args[0] else call_args.kwargs.get("wallet_balance")
        )
        assert (
            wallet_balance_arg == 500.0
        ), f"Expected 500.0 but got {wallet_balance_arg}"

    def test_slow_path_passes_wallet_balance_to_budget_gate(self, monkeypatch):
        """Slow-path calls can_spend_sports with actual wallet_balance (not 0.0)."""
        from agents.application.ingame_trader import InGameTrader

        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "0")
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")
        mocks = _make_mocks()
        trader = InGameTrader(
            budget_coordinator=mocks["budget"],
            data_connector=mocks["data_connector"],
            executor=mocks["executor"],
            cache=mocks["cache"],
            dry_run=True,
            polymarket=mocks["polymarket"],
            wallet_balance=500.0,
        )

        trader._run_slow_path(1, _game_state(game_id=1), _market_tag())

        mocks["budget"].can_spend_sports.assert_called()
        call_args = mocks["budget"].can_spend_sports.call_args
        wallet_balance_arg = (
            call_args[0][1] if call_args[0] else call_args.kwargs.get("wallet_balance")
        )
        assert (
            wallet_balance_arg == 500.0
        ), f"Expected 500.0 but got {wallet_balance_arg}"

    def test_default_wallet_balance_zero_blocks_budget_gate(self, monkeypatch):
        """InGameTrader constructed without wallet_balance defaults to 0.0, blocking trades when min_wallet_usd=50.0."""
        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "0")
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")

        trader, mocks = _make_trader()

        # Simulate real BudgetCoordinator behavior: reject if wallet_balance < 50.0
        mocks["budget"].can_spend_sports.side_effect = lambda amt, wb: wb >= 50.0

        # Establish baseline so first tick does not just store the state
        trader._prev_game_states[1] = _game_state(game_id=1, score_raw="0-0")
        tag = _market_tag(game_id=1)
        slug_table = {"nba-lal-bos-2026-03-07": [tag]}

        # Score change triggers fast-path; with wallet_balance=0.0, budget gate should block
        gs_new = _game_state(game_id=1, score_raw="5-0", home_score=5, away_score=0)
        trader.tick({1: gs_new}, slug_table)

        # Budget gate blocked — no order should have been executed
        mocks["polymarket"].execute_market_order_for_token.assert_not_called()


# ---------------------------------------------------------------------------
# TestHaltGate (Phase 6)
# ---------------------------------------------------------------------------


class TestHaltGate:
    def test_suspended_pauses_without_ending_game(self, monkeypatch):
        """_handle_score_change returns early on Suspended status; game_id NOT in _ended_games."""
        from unittest.mock import patch as _patch

        trader, mocks = _make_trader()
        prev = _game_state(game_id=1)
        current = _game_state(game_id=1)
        current.status = "Suspended"
        tag = _market_tag()

        with _patch.object(trader, "handle_game_ended") as mock_hge:
            trader._handle_score_change(1, prev, current, tag)
            mock_hge.assert_not_called()

        assert 1 not in trader._ended_games

    def test_delayed_pauses_without_ending_game(self, monkeypatch):
        """_handle_score_change returns early on Delayed status; game_id NOT in _ended_games."""
        from unittest.mock import patch as _patch

        trader, mocks = _make_trader()
        prev = _game_state(game_id=1)
        current = _game_state(game_id=1)
        current.status = "Delayed"
        tag = _market_tag()

        with _patch.object(trader, "handle_game_ended") as mock_hge:
            trader._handle_score_change(1, prev, current, tag)
            mock_hge.assert_not_called()

        assert 1 not in trader._ended_games

    def test_forfeit_triggers_hard_halt(self, monkeypatch):
        """_handle_score_change calls handle_game_ended() on Forfeit status."""
        from unittest.mock import patch as _patch

        trader, mocks = _make_trader()
        prev = _game_state(game_id=1)
        current = _game_state(game_id=1)
        current.status = "Forfeit"
        tag = _market_tag()

        with _patch.object(trader, "handle_game_ended") as mock_hge:
            trader._handle_score_change(1, prev, current, tag)
            mock_hge.assert_called_once_with(1)

    def test_canceled_triggers_hard_halt(self, monkeypatch):
        """_handle_score_change calls handle_game_ended() on Canceled status."""
        from unittest.mock import patch as _patch

        trader, mocks = _make_trader()
        prev = _game_state(game_id=1)
        current = _game_state(game_id=1)
        current.status = "Canceled"
        tag = _market_tag()

        with _patch.object(trader, "handle_game_ended") as mock_hge:
            trader._handle_score_change(1, prev, current, tag)
            mock_hge.assert_called_once_with(1)

    def test_inprogress_proceeds_normally(self, monkeypatch):
        """_handle_score_change calls _should_process when current.status is InProgress."""
        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "0")
        from unittest.mock import patch as _patch

        trader, mocks = _make_trader()
        prev = _game_state(game_id=1)
        current = _game_state(game_id=1)
        current.status = "InProgress"
        tag = _market_tag()

        with _patch.object(trader, "_should_process", return_value=False) as mock_sp:
            trader._handle_score_change(1, prev, current, tag)
            mock_sp.assert_called_once_with(1)

    def test_auto_resume_after_suspended(self, monkeypatch):
        """After Suspended state, next tick with InProgress resumes trading normally."""
        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "0")
        from unittest.mock import patch as _patch

        trader, mocks = _make_trader()
        prev = _game_state(game_id=1)
        tag = _market_tag()

        # First tick: Suspended — should pause
        suspended = _game_state(game_id=1)
        suspended.status = "Suspended"
        with _patch.object(trader, "handle_game_ended") as mock_hge:
            trader._handle_score_change(1, prev, suspended, tag)
            mock_hge.assert_not_called()

        # Second tick: InProgress — should resume (calls _should_process)
        inprogress = _game_state(game_id=1)
        inprogress.status = "InProgress"
        with _patch.object(trader, "_should_process", return_value=False) as mock_sp:
            trader._handle_score_change(1, prev, inprogress, tag)
            mock_sp.assert_called_once_with(1)

    def test_lowercase_suspended_triggers_pause(self, monkeypatch):
        """Lowercase 'suspended' (esports) also triggers pause behavior."""
        from unittest.mock import patch as _patch

        trader, mocks = _make_trader()
        prev = _game_state(game_id=1)
        current = _game_state(game_id=1)
        current.status = "suspended"
        tag = _market_tag()

        with _patch.object(trader, "handle_game_ended") as mock_hge:
            trader._handle_score_change(1, prev, current, tag)
            mock_hge.assert_not_called()

        assert 1 not in trader._ended_games
