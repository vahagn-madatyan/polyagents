# T02: 08-pipeline-integration 02

**Slice:** S08 — **Milestone:** M001

## Description

Wire `detect_value_bet()` into both in-game trading paths (fast-path and slow-path) and add wallet balance refresh before each budget gate check.

Purpose: Prevents in-game trades on games with no odds divergence (PIPE-02), and ensures budget calculations use live wallet balance instead of stale startup value (PERS-01 wiring for in-game).

Output: Modified `ingame_trader.py` with value bet filter in both paths and wallet refresh wiring, new test classes in `test_ingame_trader.py`.

## Must-Haves

- [ ] "In-game fast-path calls detect_value_bet() using live_price and cached implied_home_prob before the divergence gate"
- [ ] "Fast-path skips value bet check when cache entry has no implied_home_prob (allows trade through)"
- [ ] "In-game slow-path calls detect_value_bet() after game_context fetch and before LLM analysis"
- [ ] "Both paths log structured no_value_bet events with session counter"
- [ ] "Both paths update self._wallet_balance via refresh_wallet_balance() before the budget gate"
- [ ] "Wallet refresh uses self._polymarket (None in dry-run, so refresh is skipped)"

## Files

- `agents/application/ingame_trader.py`
- `tests/test_ingame_trader.py`
