"""
Sports pipeline entry point.

Run as: python -m agents.sports

This module wires together all Phase 2 components:
  - SportsWSConnector: live game state via WebSocket
  - GammaMarketClient: slug-to-market lookup table
  - SportsDataConnector: historical stats and live odds
  - BudgetCoordinator: cross-process budget management

Actual trade execution logic is Phase 3+; this module provides the
architectural backbone and event loop that Phase 3 builds on top of.
"""

import os
import queue
import threading
import time

from agents.application.budget import BudgetCoordinator
from agents.connectors.sports_data import SportsDataConnector
from agents.connectors.sports_ws import SportsWSConnector
from agents.polymarket.gamma import GammaMarketClient


def _env_bool(key: str, default: bool = False) -> bool:
    """Read a boolean env var. Accepts 'true'/'false' (case-insensitive)."""
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() == "true"


def _env_float(key: str, default: float) -> float:
    """Read a float env var with a default."""
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    """Read an int env var with a default."""
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _resolve_dry_run() -> bool:
    """
    Resolve whether the sports pipeline should run in dry-run mode.

    Priority:
    1. SPORTS_EXECUTE_TRADES — sports-specific override (if set, use it)
    2. EXECUTE_TRADES — master flag fallback

    Returns True when in dry-run (i.e. not executing real trades).
    """
    sports_flag = os.environ.get("SPORTS_EXECUTE_TRADES")
    if sports_flag is not None:
        execute = sports_flag.strip().lower() == "true"
        print(
            f"[sports_pipeline] event=dry_run_resolved source=SPORTS_EXECUTE_TRADES execute={execute}"
        )
        return not execute

    # Fall back to master flag
    execute = _env_bool("EXECUTE_TRADES", default=False)
    print(
        f"[sports_pipeline] event=dry_run_resolved source=EXECUTE_TRADES execute={execute}"
    )
    return not execute


def main() -> None:
    """
    Main entry point for the sports pipeline.

    Initializes all Phase 2 components and enters the main event loop.
    Trade execution logic will be wired in Phase 3.
    """
    dry_run = _resolve_dry_run()
    print(f"[sports_pipeline] event=startup dry_run={dry_run}")

    # Budget coordination
    wallet_balance = _env_float("SPORTS_INITIAL_WALLET_USD", 1000.0)
    budget_coordinator = BudgetCoordinator(wallet_balance=wallet_balance)
    budget_coordinator.allocate_budget()
    sports_alloc = budget_coordinator.sports_budget
    general_alloc = budget_coordinator.general_budget
    print(
        f"[sports_pipeline] event=budget_allocated "
        f"sports={sports_alloc} "
        f"general={general_alloc}"
    )

    # Market discovery
    gamma_client = GammaMarketClient()

    # Historical data and live odds
    data_connector = SportsDataConnector()

    # Live game state via WebSocket
    connector = SportsWSConnector()
    ws_thread = threading.Thread(target=connector.run, daemon=True, name="sports-ws")
    ws_thread.start()
    print("[sports_pipeline] event=ws_thread_started")

    # Wait for initial game states (up to 30s)
    slug_refresh_interval = _env_int("SPORTS_SLUG_REFRESH_INTERVAL_SECONDS", 1800)
    max_wait = 30
    waited = 0
    try:
        while waited < max_wait:
            game_states = connector.get_all_game_states()
            if game_states:
                break
            time.sleep(1)
            waited += 1

        game_states = connector.get_all_game_states()
        slug_table, unmapped = gamma_client.build_slug_table(game_states)
        print(
            f"[sports_pipeline] event=slug_table_built "
            f"mapped={len(slug_table)} unmapped={len(unmapped)}"
        )

        last_slug_refresh = time.time()

        # Main event loop — trade logic is Phase 3+
        msg_queue = connector.get_message_queue()
        while True:
            # Process any queued game state change messages
            try:
                msg = msg_queue.get_nowait()
                print(f"[sports_pipeline] event=game_state_change data={msg}")
            except Exception:
                pass  # queue empty — normal

            # Periodic slug table refresh
            now = time.time()
            if now - last_slug_refresh >= slug_refresh_interval:
                game_states = connector.get_all_game_states()
                slug_table, unmapped = gamma_client.build_slug_table(game_states)
                print(
                    f"[sports_pipeline] event=slug_table_refreshed "
                    f"mapped={len(slug_table)} unmapped={len(unmapped)}"
                )
                last_slug_refresh = now

            time.sleep(1)

    except KeyboardInterrupt:
        print("[sports_pipeline] event=shutdown_signal")
        connector.stop()
        print("[sports_pipeline] event=shutdown_complete")


if __name__ == "__main__":
    main()
