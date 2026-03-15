# S08: Pipeline Integration

**Goal:** Wire `detect_value_bet()` into the pre-game trading pipeline as an early filter (before LLM analysis), add `refresh_wallet_balance()` to BudgetCoordinator, and augment the cache entry with `implied_home_prob` for downstream in-game fast-path use.
**Demo:** Wire `detect_value_bet()` into the pre-game trading pipeline as an early filter (before LLM analysis), add `refresh_wallet_balance()` to BudgetCoordinator, and augment the cache entry with `implied_home_prob` for downstream in-game fast-path use.

## Must-Haves


## Tasks

- [x] **T01: 08-pipeline-integration 01** `est:13 min`
  - Wire `detect_value_bet()` into the pre-game trading pipeline as an early filter (before LLM analysis), add `refresh_wallet_balance()` to BudgetCoordinator, and augment the cache entry with `implied_home_prob` for downstream in-game fast-path use.

Purpose: Eliminates wasted LLM API calls on games with no odds divergence (PIPE-01), enables live wallet balance updates during trading (PERS-01), and provides the implied probability data that Plan 02 needs for in-game value bet filtering.

Output: Modified `budget.py` with refresh method, modified `sports_trader.py` with value bet filter and cache augmentation, new test classes in both test files.
- [x] **T02: 08-pipeline-integration 02** `est:6 min`
  - Wire `detect_value_bet()` into both in-game trading paths (fast-path and slow-path) and add wallet balance refresh before each budget gate check.

Purpose: Prevents in-game trades on games with no odds divergence (PIPE-02), and ensures budget calculations use live wallet balance instead of stale startup value (PERS-01 wiring for in-game).

Output: Modified `ingame_trader.py` with value bet filter in both paths and wallet refresh wiring, new test classes in `test_ingame_trader.py`.

## Files Likely Touched

- `agents/application/budget.py`
- `agents/application/sports_trader.py`
- `tests/test_budget_coordinator.py`
- `tests/test_sports_trader.py`
- `agents/application/ingame_trader.py`
- `tests/test_ingame_trader.py`
