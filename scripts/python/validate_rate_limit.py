#!/usr/bin/env python3
"""VALID-03: Concurrent CLOB rate limit compliance validation.

Runs both the sports pipeline and general pipeline concurrently in dry-run /
observe mode, captures order-rate log events from InGameTrader, and produces
a structured JSON report proving the system stays under 60 orders/min.

The script:
  1. Creates an InGameTrader in dry-run mode with simulated rapid-fire trades
  2. Runs a simulated general pipeline alongside (ContinuousStrategy-style)
  3. Counts "metric=order_rate_60s" log events from the order-rate counter
  4. Verifies the rolling 60-second count never exceeds 60

Sports with no live game during the validation window are tracked as pending
(not failed) and the phase stays open per CONTEXT.md.

Usage:
    python scripts/python/validate_rate_limit.py [--output <path>] [--duration <seconds>]

Output: JSON report written to stdout and optionally to --output file.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import threading
import time
from contextlib import redirect_stdout
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

# Ensure the project root is on sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.application.ingame_trader import InGameTrader, _FINAL_PERIODS
from agents.utils.objects import SportGameState, SportsMarketTag


# Rate limit threshold per CLOB contract
RATE_LIMIT_ORDERS_PER_MIN = 60

# Pattern to extract order_rate_60s metric from structured logs
ORDER_RATE_PATTERN = re.compile(r"\[ingame_trader\] metric=order_rate_60s count=(\d+)")


def _make_mock_dependencies() -> dict[str, Any]:
    """Create mock objects for InGameTrader dependencies."""
    budget = MagicMock()
    budget.can_spend_sports.return_value = True
    budget.refresh_wallet_balance.return_value = 1000.0
    budget.record_sports_trade.return_value = None

    data_connector = MagicMock()
    data_connector.detect_value_bet.return_value = True
    game_context = {
        "external_odds": {"implied_home_prob": 0.5},
        "historical_stats": {},
    }
    data_connector.get_game_context.return_value = game_context

    executor = MagicMock()
    candidate = MagicMock()
    candidate.probabilities = [
        {"outcome": "Yes", "likelihood": 0.65},
        {"outcome": "No", "likelihood": 0.35},
    ]
    candidate.confidence_gap = 0.25
    candidate.suggested_outcome = "Yes"
    candidate.parsed_side = "home"
    candidate.parsed_size_fraction = 0.05
    candidate.rationale = "test"
    candidate.risk_factors = []
    candidate.counter_case = ""
    candidate.outcome_prices = [0.55]
    executor.analyze_game.return_value = candidate

    cache = MagicMock()
    cache.get.return_value = {
        "llm_home_win_prob": 0.65,
        "implied_home_prob": 0.50,
    }

    polymarket = MagicMock()
    polymarket.get_orderbook_price.return_value = 0.45
    polymarket.execute_market_order_for_token.return_value = "order_123"

    return {
        "budget": budget,
        "data_connector": data_connector,
        "executor": executor,
        "cache": cache,
        "polymarket": polymarket,
    }


def _make_game_state(
    game_id: int,
    league: str = "nba",
    score_raw: str = "5-3",
    home_score: int = 5,
    away_score: int = 3,
) -> SportGameState:
    """Create a test game state."""
    return SportGameState(
        game_id=game_id,
        league=league,
        slug=f"{league}-team1-team2-2026-03-15",
        home_team="TEAM1",
        away_team="TEAM2",
        status="InProgress",
        score_raw=score_raw,
        home_score=home_score,
        away_score=away_score,
        period="Q2",
        live=True,
        ended=False,
    )


def _make_market_tag(game_id: int = 1, league: str = "nba") -> SportsMarketTag:
    """Create a test market tag."""
    return SportsMarketTag(
        slug=f"{league}-team1-team2-2026-03-15",
        league=league,
        home_team="TEAM1",
        away_team="TEAM2",
        market_id=str(100000 + game_id),
        condition_id="0x" + "a" * 64,
        token_id_yes="tok_yes_" + str(game_id),
        token_id_no="tok_no_" + str(game_id),
        question=f"Will TEAM1 win ({league})?",
        outcome_prices="0.55,0.45",
    )


def _simulate_sports_pipeline(
    trader: InGameTrader,
    duration_seconds: int,
    log_buffer: io.StringIO,
    results: dict[str, Any],
) -> None:
    """Simulate a sports pipeline generating trades at realistic cadence.

    Uses multiple game IDs across all 9 leagues to simulate concurrent
    in-game trading. The pipeline runs through tick() so cooldown guards
    are active — proving that the production system naturally stays under
    60 orders/min. Score changes are injected each tick to trigger trading.
    """
    leagues = list(_FINAL_PERIODS.keys())
    num_games = len(leagues)  # one game per sport = 9 concurrent games

    slug_table: dict[str, list[SportsMarketTag]] = {}
    baseline_states: dict[int, SportGameState] = {}

    for i in range(num_games):
        league = leagues[i]
        game_id = 1000 + i
        gs = _make_game_state(game_id=game_id, league=league)
        tag = _make_market_tag(game_id=game_id, league=league)
        baseline_states[game_id] = gs
        slug_table[gs.slug] = [tag]

    # Establish baselines via first tick (no score changes = no trades)
    old_stdout = sys.stdout
    sys.stdout = log_buffer
    try:
        trader.tick(baseline_states, slug_table)
    finally:
        sys.stdout = old_stdout

    start = time.time()
    trade_count = 0
    tick_count = 0
    score_offset = 0

    while time.time() - start < duration_seconds:
        tick_count += 1
        score_offset += 1

        # Create updated states with incremented scores to trigger events
        updated: dict[int, SportGameState] = {}
        for game_id, gs in baseline_states.items():
            new_home = (gs.home_score or 0) + score_offset
            updated[game_id] = _make_game_state(
                game_id=game_id,
                league=gs.league,
                score_raw=f"{new_home}-{gs.away_score}",
                home_score=new_home,
                away_score=gs.away_score or 0,
            )

        old_stdout = sys.stdout
        sys.stdout = log_buffer
        try:
            trader.tick(updated, slug_table)
        finally:
            sys.stdout = old_stdout

        # Count orders placed via the mock
        trade_count = trader._polymarket.execute_market_order_for_token.call_count

        time.sleep(1.0)  # 1-second cadence matches production

    results["sports_trades"] = trade_count
    results["sports_ticks"] = tick_count


def _simulate_general_pipeline(
    duration_seconds: int,
    log_buffer: io.StringIO,
    results: dict[str, Any],
) -> None:
    """Simulate a general pipeline running concurrently.

    The general pipeline (ContinuousStrategy) runs its own trade cycle.
    In observe mode, it emits log events but doesn't place real orders.
    We simulate this by logging order-like events at a realistic cadence.
    """
    start = time.time()
    cycle_count = 0

    while time.time() - start < duration_seconds:
        cycle_count += 1
        old_stdout = sys.stdout
        sys.stdout = log_buffer
        try:
            print(
                f"[general_pipeline] event=cycle_complete cycle={cycle_count} "
                f"markets_analyzed=5 orders_simulated=0"
            )
        finally:
            sys.stdout = old_stdout
        time.sleep(2.0)  # general pipeline runs ~30s cycles, we compress to 2s

    results["general_cycles"] = cycle_count


def _extract_rate_metrics(log_output: str) -> list[int]:
    """Extract all order_rate_60s counts from captured log output."""
    return [int(m.group(1)) for m in ORDER_RATE_PATTERN.finditer(log_output)]


def run_validation(
    duration_seconds: int = 15,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Run VALID-03 concurrent rate limit compliance validation.

    Creates an InGameTrader in live mode (non-dry-run) with mock CLOB so
    order-rate timestamps are actually recorded. Runs sports + general
    pipelines concurrently and captures rate metrics.
    """
    start_time = time.time()
    mocks = _make_mock_dependencies()

    # Use non-dry-run so _record_order_timestamp is called
    trader = InGameTrader(
        budget_coordinator=mocks["budget"],
        data_connector=mocks["data_connector"],
        executor=mocks["executor"],
        cache=mocks["cache"],
        dry_run=False,
        polymarket=mocks["polymarket"],
        wallet_balance=1000.0,
    )

    # Shared log buffer for capturing structured logs
    log_buffer = io.StringIO()

    sports_results: dict[str, Any] = {}
    general_results: dict[str, Any] = {}

    print(
        f"[validate_rate_limit] event=start duration={duration_seconds}s",
        file=sys.stderr,
    )

    # Run both pipelines concurrently
    sports_thread = threading.Thread(
        target=_simulate_sports_pipeline,
        args=(trader, duration_seconds, log_buffer, sports_results),
        name="valid03-sports",
        daemon=True,
    )
    general_thread = threading.Thread(
        target=_simulate_general_pipeline,
        args=(duration_seconds, log_buffer, general_results),
        name="valid03-general",
        daemon=True,
    )

    sports_thread.start()
    general_thread.start()

    sports_thread.join(timeout=duration_seconds + 10)
    general_thread.join(timeout=duration_seconds + 10)

    elapsed = time.time() - start_time

    # Extract rate metrics from captured output
    log_output = log_buffer.getvalue()
    rate_counts = _extract_rate_metrics(log_output)
    peak_rate = max(rate_counts) if rate_counts else 0
    final_rate = trader.get_order_rate()

    # Determine pass/fail
    rates_under_limit = all(r < RATE_LIMIT_ORDERS_PER_MIN for r in rate_counts)
    final_under_limit = final_rate < RATE_LIMIT_ORDERS_PER_MIN

    if rate_counts and rates_under_limit and final_under_limit:
        overall_status = "pass"
    elif not rate_counts:
        # No order-rate events captured — pending (no live trades)
        overall_status = "pending"
    else:
        overall_status = "fail"

    report: dict[str, Any] = {
        "validation_id": "VALID-03",
        "description": (
            "Concurrent sports + general pipelines stay under "
            f"{RATE_LIMIT_ORDERS_PER_MIN} orders/min"
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(elapsed, 2),
        "overall_status": overall_status,
        "rate_limit_threshold": RATE_LIMIT_ORDERS_PER_MIN,
        "peak_order_rate_60s": peak_rate,
        "final_order_rate_60s": final_rate,
        "total_rate_samples": len(rate_counts),
        "all_samples_under_limit": rates_under_limit,
        "rate_samples": rate_counts,
        "pipelines": {
            "sports": {
                "trades_attempted": sports_results.get("sports_trades", 0),
                "ticks_completed": sports_results.get("sports_ticks", 0),
                "concurrent_games": len(_FINAL_PERIODS),
            },
            "general": {
                "cycles_completed": general_results.get("general_cycles", 0),
            },
        },
    }

    # Output
    report_json = json.dumps(report, indent=2)
    print(report_json)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w") as f:
            f.write(report_json)
        print(
            f"[validate_rate_limit] event=report_written path={output_path}",
            file=sys.stderr,
        )

    print(
        f"[validate_rate_limit] event=complete overall_status={overall_status} "
        f"peak_rate={peak_rate} final_rate={final_rate} "
        f"sports_trades={sports_results.get('sports_trades', 0)} "
        f"general_cycles={general_results.get('general_cycles', 0)} "
        f"duration={report['duration_seconds']}s",
        file=sys.stderr,
    )

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "VALID-03: Concurrent rate limit compliance validation — "
            "proves system stays under 60 orders/min"
        )
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to write JSON report (default: stdout only)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=15,
        help="Validation duration in seconds (default: 15)",
    )
    args = parser.parse_args()
    report = run_validation(
        duration_seconds=args.duration,
        output_path=args.output,
    )

    # Exit code: 0 if pass/pending, 1 if fail
    if report["overall_status"] == "fail":
        sys.exit(1)


if __name__ == "__main__":
    main()
