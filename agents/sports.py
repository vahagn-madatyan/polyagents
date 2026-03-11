"""
Sports pipeline entry point.

Run as: python -m agents.sports

This module wires together all Phase 2, Phase 3, and Phase 4 components:
  - SportsWSConnector: live game state via WebSocket
  - GammaMarketClient: slug-to-market lookup table
  - SportsDataConnector: historical stats and live odds
  - BudgetCoordinator: cross-process budget management
  - SportsExecutor: two-stage LLM analysis engine
  - PregameCache: file-persisted analysis result cache
  - SportsTrader: orchestrates pre-game analysis and trade execution
  - InGameTrader: autonomous in-game score-change trading engine (Phase 4)
"""

import os
import queue
import threading
import time

from agents.application.budget import BudgetCoordinator
from agents.application.ingame_trader import InGameTrader
from agents.application.pregame_cache import PregameCache
from agents.application.sports_executor import SportsExecutor
from agents.application.sports_trader import SportsTrader
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

    Initializes all Phase 2, Phase 3, and Phase 4 components and enters the main event loop.
    Triggers pre-game analysis at two points:
      1. After initial slug table build (newly mapped games)
      2. On each loop iteration for cache-expired games (TTL refresh)
    In-game trading (Phase 4) runs each loop iteration via ingame_trader.tick().
    """
    dry_run = _resolve_dry_run()
    print(f"[sports_pipeline] event=startup dry_run={dry_run}")

    # Wallet balance: real CLOB balance in live mode; env fallback in dry-run
    if not dry_run:
        # Lazy import to avoid heavy dep chain in tests / dry-run mode
        from agents.polymarket.polymarket import Polymarket

        polymarket = Polymarket(initialize_clob_client=True)
        wallet_balance = polymarket.get_usdc_balance()
    else:
        polymarket = None
        wallet_balance = _env_float("SPORTS_INITIAL_WALLET_USD", 1000.0)

    print(
        f"[sports_pipeline] event=wallet_balance "
        f"source={'clob' if not dry_run else 'env'} "
        f"balance={wallet_balance:.2f}"
    )

    # Budget coordination
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

    # Phase 3: LLM analysis engine and cache
    executor = SportsExecutor()
    pregame_cache = PregameCache()

    # Phase 3: SportsTrader orchestrates pre-game analysis and trade execution
    trader = SportsTrader(
        budget_coordinator=budget_coordinator,
        data_connector=data_connector,
        executor=executor,
        cache=pregame_cache,
        dry_run=dry_run,
        polymarket=polymarket,
    )

    # Phase 4: InGameTrader runs alongside SportsTrader with shared dependencies
    ingame_trader = InGameTrader(
        budget_coordinator=budget_coordinator,
        data_connector=data_connector,
        executor=executor,
        cache=pregame_cache,
        dry_run=dry_run,
        polymarket=polymarket,
        wallet_balance=wallet_balance,
    )

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
        if unmapped:
            slug_table, unmapped = gamma_client.retry_unmapped_slugs(
                unmapped, slug_table
            )
        print(
            f"[sports_pipeline] event=slug_table_built "
            f"mapped={len(slug_table)} unmapped_after_retry={len(unmapped)}"
        )

        # Trigger point 1: Pre-game analysis for newly mapped games on slug table build
        for slug, market_tags in slug_table.items():
            game_state = next(
                (gs for gs in game_states.values() if gs.slug == slug),
                None,
            )
            if (
                game_state
                and not game_state.ended
                and trader.should_analyze(game_state.game_id)
            ):
                tag = market_tags[0] if isinstance(market_tags, list) else market_tags
                threading.Thread(
                    target=trader.run_pregame_analysis,
                    args=(game_state.game_id, game_state, tag, wallet_balance),
                    daemon=True,
                    name=f"pregame-{game_state.game_id}",
                ).start()

        last_slug_refresh = time.time()

        # Main event loop
        msg_queue = connector.get_message_queue()
        while True:
            # Drain all queued game state change messages; route period transitions
            while True:
                try:
                    msg = msg_queue.get_nowait()
                    print(f"[sports_pipeline] event=game_state_change data={msg}")
                    if msg.get("type") == "period_transition":
                        ingame_trader.handle_period_transition(msg, slug_table)
                except Exception:
                    break  # queue empty

            # Periodic slug table refresh
            now = time.time()
            if now - last_slug_refresh >= slug_refresh_interval:
                game_states = connector.get_all_game_states()
                slug_table, unmapped = gamma_client.build_slug_table(game_states)
                if unmapped:
                    slug_table, unmapped = gamma_client.retry_unmapped_slugs(
                        unmapped, slug_table
                    )
                print(
                    f"[sports_pipeline] event=slug_table_refreshed "
                    f"mapped={len(slug_table)} unmapped_after_retry={len(unmapped)}"
                )
                last_slug_refresh = now

            # Trigger point 2: Re-analyze games with stale/expired cache entries
            game_states_snapshot = connector.get_all_game_states()

            # Phase 4: In-game trading — detect score changes and trade on events
            ingame_trader.tick(game_states_snapshot, slug_table)

            for slug, market_tags in slug_table.items():
                game_state = next(
                    (gs for gs in game_states_snapshot.values() if gs.slug == slug),
                    None,
                )
                if (
                    game_state
                    and not game_state.ended
                    and trader.should_analyze(game_state.game_id)
                ):
                    tag = (
                        market_tags[0] if isinstance(market_tags, list) else market_tags
                    )
                    threading.Thread(
                        target=trader.run_pregame_analysis,
                        args=(game_state.game_id, game_state, tag, wallet_balance),
                        daemon=True,
                        name=f"pregame-{game_state.game_id}",
                    ).start()

            time.sleep(1)

    except KeyboardInterrupt:
        print("[sports_pipeline] event=shutdown_signal")
        connector.stop()
        print("[sports_pipeline] event=shutdown_complete")


if __name__ == "__main__":
    main()
