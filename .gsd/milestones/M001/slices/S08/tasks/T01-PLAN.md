# T01: 08-pipeline-integration 01

**Slice:** S08 — **Milestone:** M001

## Description

Wire `detect_value_bet()` into the pre-game trading pipeline as an early filter (before LLM analysis), add `refresh_wallet_balance()` to BudgetCoordinator, and augment the cache entry with `implied_home_prob` for downstream in-game fast-path use.

Purpose: Eliminates wasted LLM API calls on games with no odds divergence (PIPE-01), enables live wallet balance updates during trading (PERS-01), and provides the implied probability data that Plan 02 needs for in-game value bet filtering.

Output: Modified `budget.py` with refresh method, modified `sports_trader.py` with value bet filter and cache augmentation, new test classes in both test files.

## Must-Haves

- [ ] "Pre-game analysis calls detect_value_bet() after data fetch and before LLM call"
- [ ] "Games with no odds divergence are skipped with a structured log event and session counter"
- [ ] "Games with missing external_odds pass through without value bet check (optimization filter, not safety gate)"
- [ ] "Cache entry includes implied_home_prob for downstream in-game fast-path consumption"
- [ ] "BudgetCoordinator.refresh_wallet_balance() returns fresh USDC balance with 30-second cooldown"
- [ ] "Wallet refresh falls back to cached balance on API error without raising"
- [ ] "Wallet refresh is skipped in dry-run mode (polymarket=None)"
- [ ] "Pre-game budget gate uses refreshed wallet balance, not stale startup value"

## Files

- `agents/application/budget.py`
- `agents/application/sports_trader.py`
- `tests/test_budget_coordinator.py`
- `tests/test_sports_trader.py`
