# Phase 5: Critical Integration Fixes - Research

**Researched:** 2026-03-08
**Domain:** Python in-process wiring fixes — event dict augmentation and constructor dependency injection
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Wallet balance sourcing**
- Pass the startup `wallet_balance` (fetched in `sports.py` from CLOB or env var) to `InGameTrader.__init__()` as a new constructor parameter
- Store it as `self._wallet_balance` and use it in both `can_spend_sports()` call sites (lines 387 and 513)
- Use startup snapshot throughout the session — do NOT decrement after trades or query CLOB live. `BudgetCoordinator` independently tracks remaining sports budget via `record_sports_trade()`; the wallet_balance param is just the minimum-balance safety floor ($50 default), not the spending limit
- `sports.py` passes the existing `wallet_balance` variable to InGameTrader constructor (same pattern as `SportsTrader.run_pregame_analysis()`)

**Wallet floor policy**
- Keep existing `SPORTS_MIN_WALLET_USD` blocking behavior as-is — if wallet is below threshold, budget gate rejects trade
- Once actual balance is passed instead of 0.0, this will work correctly for wallets above the floor

**Period transition fix**
- Add `"game_id": state.game_id` to the event dict in `_emit_period_transition()` in `sports_ws.py` (line 322-326)
- No other changes needed to `handle_period_transition()` — it already correctly reads `msg.get("game_id")` and routes to slow-path

### Claude's Discretion
- Whether to add any additional keys to the period transition event dict beyond `game_id`
- Test structure and organization for verifying the fixes
- Whether to update the `_emit_period_transition` print statement to match the event dict structure

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TRD-02 | Bot executes autonomous in-game trades reacting to live game state changes | Fix wallet_balance=0.0 bug so budget gate permits trades when wallet above floor; confirmed `can_spend_sports(amount, wallet_balance)` API unchanged |
| WS-06 | Bot detects period/quarter transitions and triggers trade re-evaluation at each transition | Fix missing `game_id` in event dict so `handle_period_transition()` does not drop events; consumer-side guard already correct |
</phase_requirements>

---

## Summary

Phase 5 closes two critical integration gaps identified by the v1.0 audit. Both are surgical wiring fixes to existing code — no new modules, no new abstractions, no architectural changes.

**Bug 1 (WS-06):** `_emit_period_transition()` in `sports_ws.py` emits an event dict that is missing `"game_id"`. The consumer `handle_period_transition()` in `ingame_trader.py` correctly guards on `msg.get("game_id") is None` and returns early — dropping every period transition silently. The fix is a one-line addition to the event dict. Confirmed by reading `sports_ws.py:322-327` (event dict) and `ingame_trader.py:203-206` (guard). The existing test `test_period_transition_detected` passes today but does NOT assert that `game_id` is in the event dict — a new test is needed to lock the fix.

**Bug 2 (TRD-02):** `InGameTrader` calls `self._budget.can_spend_sports(trade_amount, 0.0)` at two sites (lines 387 and 513). `can_spend_sports()` first checks `wallet_balance < self.min_wallet_usd` (default $50) before checking remaining budget — with hardcoded 0.0 this check always fails, blocking every in-game trade. The fix is adding `wallet_balance` as a 7th constructor parameter, storing it as `self._wallet_balance`, and replacing both 0.0 literals. The call site in `sports.py:150` already has `wallet_balance` in scope.

**Primary recommendation:** Implement both fixes as a single logical change in one plan wave. Each fix is 3-5 lines of production code and 1-2 new test assertions. Total implementation scope is small and well-bounded.

---

## Standard Stack

### Core (unchanged — no new dependencies)

| Component | Location | Role |
|-----------|----------|------|
| `SportsWSConnector` | `agents/connectors/sports_ws.py` | Emits `period_transition` events to message queue |
| `InGameTrader` | `agents/application/ingame_trader.py` | Consumes events, gates trades via budget |
| `BudgetCoordinator` | `agents/application/budget.py` | `can_spend_sports(amount, wallet_balance)` API |
| `sports.py` | `agents/sports.py` | Pipeline entry point, constructs all objects |
| pytest | `tests/` | Test framework (95 tests passing on current branch) |

**Installation:** None required — no new packages.

---

## Architecture Patterns

### Pattern 1: Constructor Dependency Injection (established in codebase)

**What:** Add a new required (or keyword-only) parameter to `__init__()`. Store on `self`. Use throughout the instance lifecycle.

**When to use:** When a value is known at construction time, doesn't change after startup, and is needed by multiple methods.

**Established signature before fix:**
```python
# agents/application/ingame_trader.py:97
def __init__(
    self,
    budget_coordinator: "BudgetCoordinator",
    data_connector: "SportsDataConnector",
    executor: "SportsExecutor",
    cache: "PregameCache",
    dry_run: bool,
    polymarket: Optional["Polymarket"] = None,
) -> None:
```

**After fix — add wallet_balance as 7th param (keyword, with default for backward-compat in tests):**
```python
def __init__(
    self,
    budget_coordinator: "BudgetCoordinator",
    data_connector: "SportsDataConnector",
    executor: "SportsExecutor",
    cache: "PregameCache",
    dry_run: bool,
    polymarket: Optional["Polymarket"] = None,
    wallet_balance: float = 0.0,
) -> None:
    ...
    self._wallet_balance = wallet_balance
```

**NOTE:** Giving `wallet_balance` a default of `0.0` means existing test helpers that call `InGameTrader(...)` with 6 params continue to compile without changes. Tests that want to verify the budget gate works correctly should pass a non-zero value explicitly.

### Pattern 2: Event Dict Augmentation (established in codebase)

**What:** Add a key-value pair to the dict constructed before `queue.put_nowait()`.

**Current event dict (sports_ws.py:322-327):**
```python
event = {
    "type": "period_transition",
    "state": state,
    "old_period": old_period,
    "new_period": new_period,
}
```

**After fix:**
```python
event = {
    "type": "period_transition",
    "game_id": state.game_id,   # <-- added
    "state": state,
    "old_period": old_period,
    "new_period": new_period,
}
```

`state.game_id` is already available (it is a field of `SportGameState`). The print statement on lines 318-321 already logs `game_id={state.game_id}` — it is consistent and does not need updating.

### Pattern 3: Call Site Replacement

**What:** Replace a literal constant with a stored instance attribute.

**Current (ingame_trader.py lines 387 and 513):**
```python
if not self._budget.can_spend_sports(trade_amount, 0.0):
```

**After fix:**
```python
if not self._budget.can_spend_sports(trade_amount, self._wallet_balance):
```

Both call sites are identical — the same one-token replacement at two locations.

### Construction site in sports.py (line 150)

**Current:**
```python
ingame_trader = InGameTrader(
    budget_coordinator=budget_coordinator,
    data_connector=data_connector,
    executor=executor,
    cache=pregame_cache,
    dry_run=dry_run,
    polymarket=polymarket,
)
```

**After fix:**
```python
ingame_trader = InGameTrader(
    budget_coordinator=budget_coordinator,
    data_connector=data_connector,
    executor=executor,
    cache=pregame_cache,
    dry_run=dry_run,
    polymarket=polymarket,
    wallet_balance=wallet_balance,
)
```

`wallet_balance` is in scope at line 150 — it is set at lines 107-110 (live) or line 110 (dry-run).

### Anti-Patterns to Avoid

- **Decrementing wallet_balance after trades:** The wallet_balance param is a minimum-balance safety floor, not a spending limit. `BudgetCoordinator.record_sports_trade()` handles remaining budget tracking.
- **Querying CLOB live during trading:** Startup snapshot only per locked decision.
- **Changing `can_spend_sports()` signature in budget.py:** The API is correct and already used correctly. Only the caller changes.
- **Making wallet_balance a required (non-default) param:** This would break existing tests. Use a default of `0.0` to maintain backward compatibility.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Remaining budget tracking | Decrement `self._wallet_balance` | `BudgetCoordinator.record_sports_trade()` | Already implemented in Phase 2; wallet_balance is floor check only |
| Thread-safe queue dispatch | Custom pub/sub | `queue.Queue.put_nowait()` | Already established; `_emit_period_transition` already uses it |
| game_id lookup | Reverse-map from state | `state.game_id` field | `SportGameState` carries `game_id` directly |

---

## Common Pitfalls

### Pitfall 1: wallet_balance Default Value
**What goes wrong:** Adding `wallet_balance` as a required positional argument breaks the 38 existing `InGameTrader(...)` calls in `test_ingame_trader.py` which use `_make_trader()` without `wallet_balance`.
**Why it happens:** Constructor has 6 params today; tests pass all 6 via keyword args. Making the 7th positional-required forces every test to add it.
**How to avoid:** Add `wallet_balance: float = 0.0` as a keyword argument with default. Existing tests continue to pass. Only `sports.py` construction site needs updating.
**Warning signs:** `TypeError: __init__() missing 1 required positional argument` on test run.

### Pitfall 2: Not Updating Both Call Sites
**What goes wrong:** Only fixing fast-path call site (line 387) leaves slow-path (line 513) still passing 0.0 — period-transition-triggered slow-path trades remain blocked.
**Why it happens:** Two identical code patterns at lines 387 and 513 — easy to fix one, miss the other.
**How to avoid:** Search for `can_spend_sports` in `ingame_trader.py` — there are exactly 2 occurrences. Both must change.
**Warning signs:** Fast-path trades succeed; slow-path (period transition) trades still blocked.

### Pitfall 3: Test Asserts `game_id` NOT Checked in Existing Test
**What goes wrong:** `test_period_transition_detected` passes today WITHOUT the fix (it only checks `type`, `old_period`, `new_period`, `state` fields). If no new assertion is added, the bug fix has no regression protection.
**Why it happens:** Original test was written to verify the plumbing exists, not the exact shape of the event dict.
**How to avoid:** Add `assert event["game_id"] == 19439` (the NFL message gameId) to `test_period_transition_detected`, OR add a dedicated new test.
**Warning signs:** All tests pass both before and after the fix if no new assertion is written.

### Pitfall 4: Modifying consumer (ingame_trader.py) instead of producer (sports_ws.py)
**What goes wrong:** Adding a fallback like `game_id = msg.get("game_id") or msg.get("state").game_id` in `handle_period_transition()` masks the real bug without fixing the event dict.
**Why it happens:** Consumer guard is visible and feels like the right place to "fix" the missing key.
**How to avoid:** Fix the producer. The existing consumer guard is correct defensive code — leave it as-is. The fix belongs in `_emit_period_transition()`.

---

## Code Examples

Verified patterns from direct source inspection (2026-03-08):

### BudgetCoordinator.can_spend_sports — actual signature
```python
# agents/application/budget.py:132
def can_spend_sports(self, amount: float, wallet_balance: float) -> bool:
    """Check if sports pipeline can spend amount given current state."""
    if wallet_balance < self.min_wallet_usd:
        return False
    remaining = self.get_sports_budget()
    return float(amount) <= remaining
```
With `wallet_balance=0.0`, the first check (`0.0 < 50.0`) always returns False regardless of remaining budget.

### wallet_balance in sports.py — already in scope
```python
# agents/sports.py:101-110
if not dry_run:
    from agents.polymarket.polymarket import Polymarket
    polymarket = Polymarket(initialize_clob_client=True)
    wallet_balance = polymarket.get_usdc_balance()
else:
    polymarket = None
    wallet_balance = _env_float("SPORTS_INITIAL_WALLET_USD", 1000.0)
```

### handle_period_transition — consumer guard (unchanged)
```python
# agents/application/ingame_trader.py:203-206
game_id = msg.get("game_id")
if game_id is None:
    print(f"[ingame_trader] event=period_transition_no_game_id msg={msg}")
    return
```
This is correct defensive code. It already does the right thing once the event dict has `game_id`.

### Test helper pattern for new wallet_balance tests
```python
# Extend _make_trader() OR pass wallet_balance directly to InGameTrader
trader = InGameTrader(
    budget_coordinator=mocks["budget"],
    data_connector=mocks["data_connector"],
    executor=mocks["executor"],
    cache=mocks["cache"],
    dry_run=dry_run,
    polymarket=mocks["polymarket"],
    wallet_balance=500.0,   # <-- new param
)
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| `can_spend_sports(amount, 0.0)` | `can_spend_sports(amount, self._wallet_balance)` | Budget gate correctly evaluates; in-game trades unblocked |
| Event dict without `game_id` | Event dict with `"game_id": state.game_id` | Period transitions routed to slow-path instead of dropped |

**Both bugs are silent failures:** no exception is raised, just a log line and early return. This is why they survived code review — the path looks correct in isolation.

---

## Open Questions

1. **Should `wallet_balance` param be keyword-only (after `*`)?**
   - What we know: Project uses keyword arg style everywhere (all 6 current `InGameTrader` params are passed as `param=value` at construction sites)
   - What's unclear: Whether to enforce keyword-only with `*` separator
   - Recommendation: Use `wallet_balance: float = 0.0` as a regular keyword arg with default — consistent with existing `polymarket: Optional["Polymarket"] = None` param pattern. Do not add `*` separator unless project style dictates.

2. **Should print statement in `_emit_period_transition` be updated?**
   - What we know: Print at line 318-321 already logs `game_id={state.game_id}`. The event dict at 322-327 is missing it. No inconsistency in behavior — only in dict vs log.
   - What's unclear: Claude's discretion per CONTEXT.md
   - Recommendation: Leave print as-is. It already correctly logs `game_id`. Only the dict needs updating.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 (detected from `__pycache__` pyc filename) |
| Config file | No dedicated pytest.ini found — pytest discovers by convention |
| Quick run command | `python -m pytest tests/test_ingame_trader.py tests/test_sports_ws.py -v --tb=short` |
| Full suite command | `python -m pytest tests/ -v --tb=short` |

**Baseline:** 95 tests pass, 0 failures (verified 2026-03-08).

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WS-06 | `_emit_period_transition()` includes `game_id` in event dict | unit | `python -m pytest tests/test_sports_ws.py::TestSportsWSConnectorPeriodTransition -x` | Wave 0 gap — assert missing |
| WS-06 | `handle_period_transition()` does not drop event when `game_id` present | unit | `python -m pytest tests/test_ingame_trader.py::TestPeriodTransition -x` | ✅ exists, passes |
| TRD-02 | `InGameTrader` stores `wallet_balance` from constructor | unit | `python -m pytest tests/test_ingame_trader.py -k "wallet" -x` | Wave 0 gap — no test yet |
| TRD-02 | `can_spend_sports` receives actual wallet balance (not 0.0) | unit | `python -m pytest tests/test_ingame_trader.py -k "budget_gate" -x` | Wave 0 gap — existing test mocks budget but doesn't check call args |
| TRD-02 | Fast-path budget gate uses `self._wallet_balance` | unit | `python -m pytest tests/test_ingame_trader.py::TestFastPath::test_fast_path_respects_budget_gate -x` | ✅ exists (mocks `can_spend_sports`, passes) |
| TRD-02 | Slow-path budget gate uses `self._wallet_balance` | unit | `python -m pytest tests/test_ingame_trader.py::TestSlowPath -x` | ✅ exists, passes |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_ingame_trader.py tests/test_sports_ws.py -v --tb=short`
- **Per wave merge:** `python -m pytest tests/ -v --tb=short`
- **Phase gate:** Full suite green (must stay at 95+ passing) before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] Add assertion `assert event["game_id"] == 19439` inside `test_period_transition_detected` in `tests/test_sports_ws.py` — covers WS-06 producer fix
- [ ] Add new test in `tests/test_ingame_trader.py::TestFastPath` or `TestSlowPath` that: (a) constructs trader with `wallet_balance=500.0`, (b) asserts `can_spend_sports` is called with `(amount, 500.0)` not `(amount, 0.0)` — covers TRD-02 call site fix
- [ ] Add test that trader with `wallet_balance=0.0` (default, simulating the bug) fails budget gate, and with `wallet_balance=500.0` passes — covers the floor-check semantics

*(The test infrastructure itself exists and is healthy. Only specific assertions are missing.)*

---

## Sources

### Primary (HIGH confidence)
- Direct source inspection: `agents/connectors/sports_ws.py:311-333` — `_emit_period_transition()` implementation, event dict shape
- Direct source inspection: `agents/application/ingame_trader.py:97-130, 193-241, 387, 513` — constructor, `handle_period_transition()`, call sites
- Direct source inspection: `agents/application/budget.py:132-137` — `can_spend_sports()` signature and logic
- Direct source inspection: `agents/sports.py:101-157` — `wallet_balance` scope and `InGameTrader` construction site
- Direct source inspection: `tests/test_ingame_trader.py` — 38 tests, helper structure, existing `_make_trader()` pattern
- Direct source inspection: `tests/test_sports_ws.py:293-362` — period transition test class, existing assertions
- Pytest run: 95 tests passing (2026-03-08) — baseline state confirmed

### Secondary (MEDIUM confidence)
- `05-CONTEXT.md` — locked decisions cross-referenced with source code; all line numbers verified accurate

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — this is pure in-process Python wiring; no external APIs, no new dependencies
- Architecture: HIGH — all patterns exist in the codebase already; both fixes follow established patterns
- Pitfalls: HIGH — derived from direct code reading, not inference; confirmed by test structure

**Research date:** 2026-03-08
**Valid until:** 2026-05-08 (stable internal codebase; no time-sensitive external APIs)
