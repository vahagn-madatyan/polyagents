---
phase: 05-critical-integration-fixes
plan: "01"
subsystem: in-game-trading-pipeline
tags: [bug-fix, tdd, sports-ws, ingame-trader, budget-gate, period-transition]
requirements: [TRD-02, WS-06]

dependency_graph:
  requires: []
  provides:
    - period-transition-event-includes-game-id
    - ingame-trader-wallet-balance-wired-to-budget-gate
  affects:
    - agents/connectors/sports_ws.py
    - agents/application/ingame_trader.py
    - agents/sports.py
    - tests/test_sports_ws.py
    - tests/test_ingame_trader.py

tech_stack:
  added: []
  patterns:
    - TDD RED-GREEN cycle for regression-locking tests
    - Default=0.0 backward-compatible param addition

key_files:
  created:
    - tests/test_ingame_trader.py (TestWalletBalance class — 4 new tests)
  modified:
    - agents/connectors/sports_ws.py (_emit_period_transition event dict)
    - agents/application/ingame_trader.py (__init__ wallet_balance param + 2 call sites)
    - agents/sports.py (InGameTrader construction site)
    - tests/test_sports_ws.py (game_id assertion in test_period_transition_detected)
    - tests/test_ingame_trader.py (_make_trader wallet_balance param)

decisions:
  - wallet_balance defaults to 0.0 to preserve backward compat with all 38+ existing _make_trader() calls
  - wallet_balance added after polymarket param to match positional order of existing 6-param signature

metrics:
  duration_seconds: 141
  completed_date: "2026-03-09"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 5
---

# Phase 05 Plan 01: Critical Integration Bug Fixes Summary

**One-liner:** Fixed two silent pipeline killers: period transitions now carry game_id so slow-path fires, and InGameTrader forwards actual wallet balance (not hardcoded 0.0) to can_spend_sports() at both fast- and slow-path gates.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | RED — Write failing tests for both bugs | 03a914e | tests/test_sports_ws.py, tests/test_ingame_trader.py |
| 2 | GREEN — Apply production fixes for both bugs | bceb1c8 | agents/connectors/sports_ws.py, agents/application/ingame_trader.py, agents/sports.py, tests/test_ingame_trader.py |

## Bugs Fixed

### WS-06: Period Transition Drops game_id

**Root cause:** `_emit_period_transition()` in sports_ws.py built the event dict without a `game_id` key. The consumer `handle_period_transition()` in ingame_trader.py immediately returns when `msg.get("game_id")` is None — meaning every period transition was silently dropped with a log line and no slow-path analysis ever fired.

**Fix:** Added `"game_id": state.game_id` to the event dict in `_emit_period_transition()`. One-line addition alongside the existing `state`, `old_period`, `new_period` keys.

**File:** `agents/connectors/sports_ws.py` line 324

### TRD-02: Budget Gate Always Blocks (Hardcoded 0.0)

**Root cause:** Both fast-path (line 387) and slow-path (line 513) in `InGameTrader._fast_path()` and `_run_slow_path()` called `can_spend_sports(trade_amount, 0.0)`. Since `BudgetCoordinator.min_wallet_usd` defaults to a positive value, passing `wallet_balance=0.0` caused the check `if wallet_balance < self.min_wallet_usd: return False` to always block, regardless of the trader's actual wallet balance. Every in-game trade was permanently blocked.

**Fix:**
- Added `wallet_balance: float = 0.0` parameter to `InGameTrader.__init__()` (after `polymarket`, with default=0.0 for backward compat)
- Stored as `self._wallet_balance`
- Replaced `0.0` with `self._wallet_balance` at both call sites
- Wired `wallet_balance=wallet_balance` in `agents/sports.py` InGameTrader construction (variable already in scope from lines 107-110)
- Updated `_make_trader()` test helper to accept and forward `wallet_balance` kwarg

**Files:** `agents/application/ingame_trader.py`, `agents/sports.py`

## Tests Added

| Test | Type | Confirms |
|------|------|----------|
| `test_period_transition_detected` (extended) | Regression lock | event["game_id"] == 19439 |
| `TestWalletBalance.test_wallet_balance_stored_from_constructor` | Unit | self._wallet_balance == 500.0 |
| `TestWalletBalance.test_fast_path_passes_wallet_balance_to_budget_gate` | Unit | fast-path calls can_spend_sports with 500.0 |
| `TestWalletBalance.test_slow_path_passes_wallet_balance_to_budget_gate` | Unit | slow-path calls can_spend_sports with 500.0 |
| `TestWalletBalance.test_default_wallet_balance_zero_blocks_budget_gate` | Behavioral | default 0.0 correctly blocked by min_wallet_usd check |

## Verification Results

- `test_period_transition_detected`: PASSED (was KeyError in RED)
- `TestWalletBalance` (4 tests): all PASSED (were TypeError/AssertionError in RED)
- Full suite: 323 passed, 0 failed (pre-existing import errors for unrelated langchain/newsapi tests are out of scope — were failing before this plan)
- Grep confirmations:
  - `"game_id": state.game_id` at sports_ws.py:324
  - `self._wallet_balance` at ingame_trader.py:113, 389, 515 (3 occurrences)
  - `wallet_balance=wallet_balance` at sports.py:157

## Deviations from Plan

None — plan executed exactly as written. Both fixes were one-token or one-line additions. The `_make_trader()` update (Fix 2d) was implemented as specified. Black reformatted the test file twice during commits; re-staged and committed successfully both times.

## Decisions Made

- `wallet_balance` defaults to `0.0` in `InGameTrader.__init__()` to maintain backward compatibility with all 38+ existing test constructions via `_make_trader()` — no existing tests needed modification
- `wallet_balance` positioned after `polymarket` in the constructor signature to match the precedent of optional params at end of the argument list

## Self-Check: PASSED

All 5 modified/created files exist on disk. Both task commits (03a914e, bceb1c8) confirmed in git log.
