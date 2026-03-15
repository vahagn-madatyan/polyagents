# S07: Code Quality And State Persistence

**Goal:** Consolidate duplicated env helper functions into a single shared module and resolve the stale TODO in objects.
**Demo:** Consolidate duplicated env helper functions into a single shared module and resolve the stale TODO in objects.

## Must-Haves


## Tasks

- [x] **T01: 07-code-quality-and-state-persistence 01** `est:15min`
  - Consolidate duplicated env helper functions into a single shared module and resolve the stale TODO in objects.py.

Purpose: Eliminate ~60 lines of duplicated _env_bool/_env_int/_env_float definitions across 9 modules (QUAL-01) and remove the misleading stale comment in objects.py (QUAL-02). This is mechanical refactoring with no behavioral changes.

Output: `agents/utils/env.py` (new shared module), updated imports in 9 consumer modules, cleaned objects.py, passing tests.
- [x] **T02: 07-code-quality-and-state-persistence 02** `est:20min`
  - Persist InGameTrader's _order_log and _ended_games to JSON files so trade history and game-end state survive process restarts.

Purpose: Currently both are in-memory only (lost on restart). Following the PregameCache pattern (JSON + filelock), we add atomic writes on every update and reload on startup. This ensures no trade data or game state is lost during normal restarts or crashes.

Output: Updated `ingame_trader.py` with persistence hooks, `tests/test_ingame_persistence.py` covering round-trip, missing file, and corrupt file scenarios.

## Files Likely Touched

- `agents/utils/env.py`
- `agents/utils/objects.py`
- `agents/application/executor.py`
- `agents/application/ingame_trader.py`
- `agents/application/sports_executor.py`
- `agents/application/pregame_cache.py`
- `agents/application/sports_trader.py`
- `agents/application/budget.py`
- `agents/connectors/sports_data.py`
- `agents/connectors/sports_ws.py`
- `agents/sports.py`
- `tests/test_env_helpers.py`
- `tests/test_objects.py`
- `agents/application/ingame_trader.py`
- `tests/test_ingame_persistence.py`
