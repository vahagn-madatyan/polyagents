---
phase: 03-pre-game-analysis-and-llm-integration
plan: 02
subsystem: sports-trading-pipeline
tags: [sports, llm, pre-game, trading, orchestration, budget, cache, dry-run]
dependency_graph:
  requires:
    - 03-01  # SportsExecutor, PregameCache, SportsAnalysisCache from Plan 01
    - 02-03  # BudgetCoordinator, sports.py event loop skeleton
  provides:
    - SportsTrader orchestrator with full pre-game trading pipeline
    - Updated sports.py event loop with active pre-game analysis triggers
    - Real CLOB wallet balance integration for live mode
  affects:
    - 04-01  # Phase 4 live trade triggers read PregameCache set by SportsTrader
tech_stack:
  added:
    - SportsTrader class (new module agents/application/sports_trader.py)
  patterns:
    - Inline env helpers (_env_float, _env_int, _env_bool) without heavy imports
    - in_flight set for concurrent duplicate analysis prevention
    - Daemon threads per game to prevent event loop blocking during LLM calls
    - Cache-before-trade pattern (Phase 4 always has probability data available)
    - Lazy Polymarket import inside main() to avoid heavy dep chain in tests
key_files:
  created:
    - agents/application/sports_trader.py
    - tests/test_sports_trader.py
  modified:
    - agents/sports.py
    - .env.example
    - tests/test_sports_pipeline.py
decisions:
  - SportsTrader lazy-imports Polymarket inside sports.py main() rather than at module level — same pattern as gamma.py to prevent heavy dep chain in tests and dry-run mode
  - Cache entry always written before trade gates — Phase 4 can read LLM probabilities even when trade is skipped (low confidence, budget exhausted, dry-run)
  - in_flight set in SportsTrader prevents duplicate concurrent analyses of same game_id across daemon threads
  - game_states_snapshot refreshed each loop iteration before TTL check — ensures stale cache loop uses current game states, not stale snapshot
  - trade_error written back to cache on CLOB exception — Phase 4 can detect failed trades without re-querying
metrics:
  duration_seconds: 361
  completed_date: "2026-03-07"
  tasks_completed: 2
  files_modified: 5
---

# Phase 3 Plan 02: SportsTrader Orchestrator and Event Loop Wiring Summary

SportsTrader with complete pre-game pipeline (data fetch -> two-stage LLM -> cache write -> confidence + budget gates -> dry-run/live CLOB execution), wired into sports.py event loop at two trigger points with daemon threads per game.

## What Was Built

### Task 1: SportsTrader Orchestrator (TDD)

Created `agents/application/sports_trader.py` with the `SportsTrader` class:

- `__init__()`: accepts `budget_coordinator`, `data_connector`, `executor`, `cache`, `dry_run`, optional `polymarket`; reads `SPORTS_MIN_CONFIDENCE_GAP` from env (default 0.10); initializes `_in_flight: set[int]`
- `should_analyze(game_id)`: returns `not cache.is_fresh(game_id)` — simple TTL gate
- `run_pregame_analysis(game_id, game_state, market_tag, wallet_balance)`:
  1. Skip ended games
  2. Skip if `game_id in _in_flight` (duplicate concurrent guard)
  3. Fetch game context via `data_connector.get_game_context()`
  4. Run LLM analysis via `executor.analyze_game()`
  5. Build `SportsAnalysisCache`-compatible dict and call `cache.set()` before gates
  6. Gate 1: confidence gap vs. `SPORTS_MIN_CONFIDENCE_GAP`
  7. Gate 2: `trade_amount = size_fraction * sport_cap`, then `budget.can_spend_sports()`
  8. Gate 3: dry-run mode logs but does not call CLOB
  9. Live: selects `token_id_yes` (Yes outcome) or `token_id_no` (No), calls `polymarket.execute_market_order_for_token()`, then `budget.record_sports_trade()`
  10. On CLOB exception: logs error, updates cache with `trade_error`, does not propagate

TDD workflow: 32 failing tests written first (RED), then implementation made all pass (GREEN).

### Task 2: Event Loop Wiring

Updated `agents/sports.py`:

- Added module-level imports for `SportsExecutor`, `SportsTrader`, `PregameCache`
- Replaced `SPORTS_INITIAL_WALLET_USD` placeholder with real CLOB balance in live mode:
  - Live: lazy `from agents.polymarket.polymarket import Polymarket` inside `main()`, then `polymarket.get_usdc_balance()`
  - Dry-run: env fallback `_env_float("SPORTS_INITIAL_WALLET_USD", 1000.0)`, `polymarket=None`
- Initialized `SportsExecutor`, `PregameCache`, `SportsTrader` after `BudgetCoordinator`
- **Trigger point 1** (slug table build): iterates newly mapped games, spawns `threading.Thread(target=trader.run_pregame_analysis, ..., name="pregame-{game_id}")` for stale cache entries
- **Trigger point 2** (TTL loop): refreshes `game_states_snapshot`, re-checks all slug table entries for stale cache, spawns threads for expired games

Updated `.env.example` with three new env vars:
```
SPORTS_PREGAME_CACHE_TTL_MINUTES="30"
SPORTS_MIN_CONFIDENCE_GAP="0.10"
SPORTS_PREGAME_CACHE_PATH="/tmp/polyagents_pregame_cache.json"
```

Updated `tests/test_sports_pipeline.py`:
- Added `SportsExecutor`, `SportsTrader`, `PregameCache` `@patch` decorators to all existing `main()` tests
- Added 4 new integration tests: trader instantiation, slug table thread trigger, dry-run env balance, live CLOB balance fetch

## Test Results

```
140 passed, 1 warning in 3.81s

- test_sports_executor.py: 51 passed
- test_sports_trader.py: 32 passed
- test_sports_pipeline.py: 22 passed (13 existing + 4 new integration + 5 pre-existing)
- test_budget_coordinator.py: 22 passed
- test_sports_data_connector.py: 13 passed
```

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| Hash    | Type  | Description |
|---------|-------|-------------|
| 582d873 | test  | Add failing tests for SportsTrader orchestrator (RED) |
| 7017d57 | feat  | Implement SportsTrader pre-game trading orchestrator (GREEN) |
| cc18781 | feat  | Wire SportsTrader into sports.py event loop; add Phase 3 env vars |

## Self-Check: PASSED

All files present and all commits verified:
- agents/application/sports_trader.py: FOUND
- tests/test_sports_trader.py: FOUND
- agents/sports.py: FOUND
- .env.example: FOUND
- tests/test_sports_pipeline.py: FOUND
- Commit 582d873: FOUND
- Commit 7017d57: FOUND
- Commit cc18781: FOUND
