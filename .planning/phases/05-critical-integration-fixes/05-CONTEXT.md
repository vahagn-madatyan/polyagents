# Phase 5: Critical Integration Fixes - Context

**Gathered:** 2026-03-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix two critical cross-phase integration bugs identified by the v1.0 milestone audit: (1) period transition events missing `game_id` so they are always dropped by `handle_period_transition()`, and (2) `InGameTrader` passing hardcoded `wallet_balance=0.0` to `can_spend_sports()` so every in-game trade is blocked by the budget gate. These are wiring fixes to existing code, not new features.

</domain>

<decisions>
## Implementation Decisions

### Wallet balance sourcing
- Pass the startup `wallet_balance` (fetched in `sports.py` from CLOB or env var) to `InGameTrader.__init__()` as a new constructor parameter
- Store it as `self._wallet_balance` and use it in both `can_spend_sports()` call sites (lines 387 and 513)
- Use startup snapshot throughout the session — do NOT decrement after trades or query CLOB live. `BudgetCoordinator` independently tracks remaining sports budget via `record_sports_trade()`; the wallet_balance param is just the minimum-balance safety floor ($50 default), not the spending limit
- `sports.py` passes the existing `wallet_balance` variable to InGameTrader constructor (same pattern as `SportsTrader.run_pregame_analysis()`)

### Wallet floor policy
- Keep existing `SPORTS_MIN_WALLET_USD` blocking behavior as-is — if wallet is below threshold, budget gate rejects trade
- Once actual balance is passed instead of 0.0, this will work correctly for wallets above the floor

### Period transition fix
- Add `"game_id": state.game_id` to the event dict in `_emit_period_transition()` in `sports_ws.py` (line 322-326)
- No other changes needed to `handle_period_transition()` — it already correctly reads `msg.get("game_id")` and routes to slow-path

### Claude's Discretion
- Whether to add any additional keys to the period transition event dict beyond `game_id`
- Test structure and organization for verifying the fixes
- Whether to update the `_emit_period_transition` print statement to match the event dict structure

</decisions>

<specifics>
## Specific Ideas

- The audit specifically calls out "E2E flow Period Transition -> Slow-Path Re-Analysis completes without dropping events" as a success criterion — verification should confirm this path works
- `sports.py` line 150 creates `InGameTrader(budget_coordinator=..., ...)` — the wallet_balance param gets added here
- Two call sites in ingame_trader.py need updating: fast-path at line 387 and slow-path at line 513 — both change from `0.0` to `self._wallet_balance`

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_emit_period_transition()` at sports_ws.py:311 — target for game_id fix, already emits to message queue
- `handle_period_transition()` at ingame_trader.py:193 — consumer side, already has correct `msg.get("game_id")` guard
- `BudgetCoordinator.can_spend_sports(amount, wallet_balance)` at budget.py:132 — existing API, no change needed
- `wallet_balance` variable in sports.py:107-110 — already fetched and available at InGameTrader construction site

### Established Patterns
- Constructor dependency injection: InGameTrader takes 6 params, adding wallet_balance as 7th follows pattern
- `_env_float()` inlined in each module for env var parsing
- `print(f"[tag] event=... key=value")` structured logging

### Integration Points
- `agents/connectors/sports_ws.py:322` — event dict construction in `_emit_period_transition()`
- `agents/application/ingame_trader.py:97` — `__init__()` signature, add wallet_balance param
- `agents/application/ingame_trader.py:387,513` — `can_spend_sports()` call sites, replace 0.0 with self._wallet_balance
- `agents/sports.py:150` — InGameTrader construction, pass wallet_balance

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-critical-integration-fixes*
*Context gathered: 2026-03-08*
