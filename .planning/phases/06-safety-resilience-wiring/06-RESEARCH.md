# Phase 6: Safety & Resilience Wiring - Research

**Researched:** 2026-03-10
**Domain:** Python code integration — wiring existing safety functions into live trading paths; slug-lookup retry with exponential backoff
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Overtime handling**
- Continue trading during overtime — OT is high-volatility opportunity
- Keep both fast-path and slow-path active during overtime periods
- Only halt on actual game-end signals, not on overtime start

**Rain delays and suspensions**
- Pause trading during delays, auto-resume when game returns to InProgress
- No manual restart required — when `should_halt_trading()` returns false again, normal fast/slow-path trading resumes automatically
- Extend existing `should_halt_trading()` pattern with pause-resume semantics rather than permanent halt

**Forfeits and cancellations**
- Actively cancel open orders for that game via CLOB API, then halt
- Reuse Phase 4's in-memory order log (`{game_id: [{order_id, timestamp, market_id}]}`) to find orders to cancel
- Prevents getting filled at stale prices on a cancelled/forfeited game

**Slug mapping retry and validation**
- Retry unmapped slugs 2-3 times with exponential backoff during slug table refresh cycles
- If still unmapped after retries, log warning and skip that game for trading
- After slug lookup, validate each market has non-empty tokenId/conditionId before adding to slug_table — reject markets missing trading data
- Builds on existing `build_slug_table()` return shape `(slug_table, unmapped)` — unmapped list feeds retry queue

### Claude's Discretion
- Exact retry backoff timing and max attempts for slug mapping
- How to detect overtime vs regular period transitions per sport
- Whether to add env vars for per-edge-case behavior or hardcode the decided policies
- Test structure and organization for edge case verification
- Whether pause-resume needs a configurable timeout (auto-halt if paused too long)

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| WS-07 | Bot handles game edge cases (overtime, rain delays, forfeits, suspensions) with configurable trade rules per edge case | `should_halt_trading()` in sports_ws.py:75 already exists; extend with per-status routing: pause-resume for Suspended/Delayed, active cancel+halt for Forfeit/Canceled; integrate calls into `InGameTrader._handle_score_change()` and `SportsTrader.run_pregame_analysis()` |
| MKT-02 | Bot maps websocket gameId/slug to Polymarket market IDs and token addresses via Gamma API slug lookup | `build_slug_table()` in gamma.py:430 already returns `(slug_table, unmapped)` tuple; add retry wrapper with exponential backoff (reusing `reconnect_delay()` pattern) and validation that `token_id_yes`, `token_id_no`, `condition_id` are non-empty before table insertion |
</phase_requirements>

---

## Summary

Phase 6 is a pure wiring phase — no new subsystems, no new data flows. All key building blocks already exist and unit-tested: `should_halt_trading()` in `sports_ws.py`, `build_slug_table()` returning `(slug_table, unmapped)` in `gamma.py`, and the CLOB order cancellation pattern from Phase 4's `_cancel_blackout_orders()` in `ingame_trader.py`. The work is (1) adding `should_halt_trading()` call sites in two places where they are currently absent, and (2) wrapping the slug refresh cycle with retry logic for the unmapped list.

The largest design decision is distinguishing between pause-resume states (Suspended, Delayed, Postponed — trading should resume automatically when `should_halt_trading()` returns False again) versus hard-halt states (Forfeit, Canceled — trading must stop permanently for the game and open orders must be cancelled). This distinction is NOT captured in the current flat `HALT_STATUSES` set and must be added. The existing `should_halt_trading()` function signature is `(state) -> bool` — it should remain unchanged; callers decide what to do based on the return value, which is sufficient because the per-status policies are implemented at the call sites.

The slug retry wrapper is entirely internal to `gamma.py` or `sports.py` — `build_slug_table()` already surfaces the unmapped list; the wrapper just calls `lookup_single_slug()` in a retry loop for each unmapped slug, applying exponential backoff, then merges results back into the slug table.

**Primary recommendation:** Two focused code changes with accompanying tests. Do not refactor existing interfaces; extend call sites and add retry/validation logic inline.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `time` | built-in | exponential backoff timing | already used throughout codebase |
| Python stdlib `threading` | built-in | daemon threads for order cancellation (already used) | no new deps |
| Python stdlib `random` | built-in | jitter in backoff | already used in `reconnect_delay()` |

### No New Dependencies

This phase adds zero new third-party dependencies. All functionality is achieved by wiring existing assets.

**Installation:**
```bash
# No new packages required
```

---

## Architecture Patterns

### Recommended Project Structure

No new files or directories are required. All changes are modifications to existing files:

```
agents/
├── connectors/
│   └── sports_ws.py         # Add PAUSE_STATUSES / HARD_HALT_STATUSES categorization
├── polymarket/
│   └── gamma.py             # Add _retry_unmapped_slugs() and _validate_market_tag()
├── application/
│   ├── ingame_trader.py     # Add should_halt_trading() call in _handle_score_change()
│   └── sports_trader.py     # Add should_halt_trading() call in run_pregame_analysis()
└── sports.py                # Call retry wrapper after slug table build/refresh
tests/
└── test_sports_ws.py        # New tests for pause-resume and hard-halt routing
    test_sports_market_discovery.py  # New tests for retry and validation
    test_ingame_trader.py    # New tests for halt gate in _handle_score_change()
    test_sports_trader.py    # New tests for halt gate in run_pregame_analysis()
```

### Pattern 1: Status Categorization

The current `HALT_STATUSES` set in `sports_ws.py:62` is a single flat set. It needs to be split into two subsets to support the locked decisions:

```python
# sports_ws.py — extend existing constants

# Statuses where trading is PAUSED (auto-resume when status changes back to InProgress)
PAUSE_STATUSES = {
    "Suspended",
    "Postponed",
    "Delayed",
}

# Statuses where trading is PERMANENTLY HALTED for the game
# (active order cancellation required, game will not resume)
HARD_HALT_STATUSES = {
    "Forfeit",
    "Canceled",
    "NotNecessary",
    "Awarded",
}

# Backward-compatible union used by existing should_halt_trading() logic
HALT_STATUSES = PAUSE_STATUSES | HARD_HALT_STATUSES
```

This preserves the existing `should_halt_trading()` signature and test coverage (all 7 statuses still halt trading). Callers use new helper functions to determine *which kind* of halt occurred.

### Pattern 2: Per-Call-Site Halt Gate with Status Routing

In `InGameTrader._handle_score_change()` and `SportsTrader.run_pregame_analysis()`, add a halt check BEFORE any trade logic:

```python
# ingame_trader.py — inside _handle_score_change()
from agents.connectors.sports_ws import should_halt_trading, HARD_HALT_STATUSES

def _handle_score_change(self, game_id, prev, current, market_tag):
    # --- Phase 6: safety gate ---
    if should_halt_trading(current):
        if current.status in HARD_HALT_STATUSES or current.status.lower() in {s.lower() for s in HARD_HALT_STATUSES}:
            print(
                f"[ingame_trader] event=hard_halt game_id={game_id} "
                f"status={current.status} cancelling_orders=true"
            )
            self.handle_game_ended(game_id)  # reuses existing cancel+halt logic
        else:
            # Pause state: just skip this tick, do NOT add to _ended_games
            print(
                f"[ingame_trader] event=trading_paused game_id={game_id} "
                f"status={current.status}"
            )
        return
    # --- end Phase 6 gate ---

    if not self._should_process(game_id):
        ...
```

```python
# sports_trader.py — inside run_pregame_analysis()
from agents.connectors.sports_ws import should_halt_trading, HARD_HALT_STATUSES

def run_pregame_analysis(self, game_id, game_state, market_tag, wallet_balance):
    # Guard: skip ended games
    if game_state.ended:
        ...

    # --- Phase 6: safety gate ---
    if should_halt_trading(game_state):
        print(
            f"[sports_trader] event=trading_halted game_id={game_id} "
            f"status={game_state.status}"
        )
        return
    # --- end Phase 6 gate ---

    # Guard: prevent duplicate concurrent analysis
    if game_id in self._in_flight:
        ...
```

**Key insight:** `SportsTrader.run_pregame_analysis()` does not have access to `InGameTrader._order_log`, so it cannot cancel orders. The order cancellation is the responsibility of `InGameTrader` (which owns the order log). `SportsTrader` just skips — this is correct because `SportsTrader` runs pre-game analysis and does not place in-game orders.

### Pattern 3: Slug Retry Wrapper with Exponential Backoff

Add a `_retry_unmapped_slugs()` method to `GammaMarketClient` (or a module-level function in `gamma.py`). Reuse the `reconnect_delay()` backoff formula pattern from `sports_ws.py`.

```python
# gamma.py — new method on GammaMarketClient

def _env_int_local(name: str, default: int) -> int:
    """Read an int env var (inline, avoids heavy import chain)."""
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _validate_market_tag(self, tag: "SportsMarketTag") -> bool:
    """Return True if tag has non-empty tokenId and conditionId fields."""
    return bool(tag.token_id_yes and tag.token_id_no and tag.condition_id)


def retry_unmapped_slugs(
    self,
    unmapped: list[str],
    slug_table: dict[str, list["SportsMarketTag"]],
    max_attempts: int | None = None,
) -> tuple[dict[str, list["SportsMarketTag"]], list[str]]:
    """Retry unmapped slugs with exponential backoff.

    For each slug in unmapped:
      1. Try lookup_single_slug() up to max_attempts times
      2. On success, validate each tag (non-empty token/condition ids)
      3. If validated tags found, add to slug_table
      4. If exhausted attempts, keep in still_unmapped

    Returns:
        (updated_slug_table, still_unmapped)
    """
    _max = max_attempts or _env_int_local("SPORTS_SLUG_RETRY_MAX_ATTEMPTS", 3)
    still_unmapped: list[str] = []

    for slug in unmapped:
        found = False
        for attempt in range(_max):
            if attempt > 0:
                # Exponential backoff between retries (1s, 2s, 4s)
                delay = min(1.0 * (2 ** (attempt - 1)), 8.0)
                time.sleep(delay)

            tags = self.lookup_single_slug(slug)
            # Validate: only accept tags with complete trading data
            valid_tags = [t for t in tags if self._validate_market_tag(t)]

            if valid_tags:
                slug_table[slug] = valid_tags
                print(
                    f"[gamma_slug] event=retry_success slug={slug} "
                    f"attempt={attempt + 1} tags={len(valid_tags)}"
                )
                found = True
                break

            print(
                f"[gamma_slug] event=retry_failed slug={slug} "
                f"attempt={attempt + 1}/{_max}"
            )

        if not found:
            print(f"[gamma_slug] event=slug_permanently_unmapped slug={slug} attempts={_max}")
            still_unmapped.append(slug)

    return slug_table, still_unmapped
```

**Call site in `sports.py`** — after each `build_slug_table()` call:

```python
# sports.py — after initial build and after each refresh
slug_table, unmapped = gamma_client.build_slug_table(game_states)
if unmapped:
    slug_table, unmapped = gamma_client.retry_unmapped_slugs(unmapped, slug_table)
print(
    f"[sports_pipeline] event=slug_table_built "
    f"mapped={len(slug_table)} unmapped_after_retry={len(unmapped)}"
)
```

### Pattern 4: Market Tag Validation in `build_slug_table()`

Add validation to `build_slug_table()` so that tags with empty `token_id_yes`, `token_id_no`, or `condition_id` are rejected before entering the slug table. This prevents downstream CLOB API errors caused by markets that are fetched but not tradable.

```python
# gamma.py — inside build_slug_table(), replace:
#   if tags:
#       slug_table[slug] = tags
# with:
valid_tags = [t for t in tags if self._validate_market_tag(t)]
if valid_tags:
    slug_table[slug] = valid_tags
elif tags:
    # Had tags but all failed validation — still unmapped for retry
    print(f"[gamma_slug] event=validation_failed slug={slug} tags_invalid={len(tags)}")
    unmapped.append(slug)
else:
    unmapped.append(slug)
```

### Anti-Patterns to Avoid

- **Refactoring `should_halt_trading()` signature:** The function is stable and tested. Do not change it — add callers, not a new API.
- **Adding `_ended_games` to `SportsTrader`:** `SportsTrader` is stateless per-game. It does not own order logs, so it cannot cancel orders. The halt gate in `SportsTrader` is a skip, not a cancel.
- **Blocking slug retry loop:** `retry_unmapped_slugs()` runs during slug refresh (every 30 min by default). Up to 3 attempts with 1s/2s delays is acceptable latency (max ~4 seconds per slug). Do NOT retry inside the tight 1-second main loop.
- **Importing from `ingame_trader.py` in `sports_ws.py`:** Creates a circular import. Import direction is `ingame_trader -> sports_ws`, not the reverse. Pass status constants, not objects.
- **Hardcoding backoff delays as literal numbers inline:** Use `_env_int_local()` pattern or named constants for testability.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Exponential backoff | Custom delay loop | `reconnect_delay()` pattern (already in sports_ws.py) | Already tested, has jitter |
| CLOB order cancel on halt | New cancel API integration | `_cancel_blackout_orders()` in InGameTrader | Already tested, handles errors gracefully |
| Status classification | New status parsing | Extend `HALT_STATUSES` set split into `PAUSE_STATUSES` + `HARD_HALT_STATUSES` | Avoids breaking existing 7-status tests |
| Market validation | New Gamma API calls | Field presence checks on existing `SportsMarketTag` | `token_id_yes`, `token_id_no`, `condition_id` are already on the model |

**Key insight:** Every mechanism needed exists and is tested. The planner should instruct the executor to wire — not to build.

---

## Common Pitfalls

### Pitfall 1: Breaking Existing `should_halt_trading()` Tests

**What goes wrong:** Changing `HALT_STATUSES` or `should_halt_trading()` signature causes the 7 existing tests in `test_sports_ws.py:TestShouldHaltTrading` to fail.

**Why it happens:** Tests assert `len(HALT_STATUSES) == 7` and check all 7 statuses individually.

**How to avoid:** `HALT_STATUSES` must remain a set of all 7 statuses (as a union of `PAUSE_STATUSES | HARD_HALT_STATUSES`). The `should_halt_trading()` signature and return semantics do not change.

**Warning signs:** Any test failure in `test_sports_ws.py::TestShouldHaltTrading` class.

### Pitfall 2: Adding `handle_game_ended()` for Pause States

**What goes wrong:** Calling `self.handle_game_ended(game_id)` on a Suspended/Delayed game adds it to `_ended_games`, permanently blocking trading even after the game resumes.

**Why it happens:** The locked decision says pause states should auto-resume when `should_halt_trading()` returns False again. But `handle_game_ended()` permanently marks the game as ended.

**How to avoid:** Only call `handle_game_ended()` for `HARD_HALT_STATUSES` (Forfeit, Canceled, NotNecessary, Awarded). For `PAUSE_STATUSES` (Suspended, Delayed, Postponed), just return early without adding to `_ended_games`. Auto-resume happens naturally because `should_halt_trading()` is checked every tick.

**Warning signs:** Tests that simulate game resuming after Suspended status show no trading activity.

### Pitfall 3: Slug Retry Delays Blocking Main Loop

**What goes wrong:** `retry_unmapped_slugs()` with `time.sleep()` called from the main event loop makes the entire pipeline unresponsive for seconds.

**Why it happens:** The main loop has a 1-second `time.sleep(1)` at the bottom. Additional blocking in the loop body compounds to unresponsive behavior.

**How to avoid:** Call `retry_unmapped_slugs()` only at slug refresh intervals (every 30 minutes by default), not in the main 1-second tick loop. The slug refresh block in `sports.py` is the correct call site.

**Warning signs:** Log events show gaps of multiple seconds between tick iterations.

### Pitfall 4: `SportsTrader` Halting Without Cancelling Orders

**What goes wrong:** `SportsTrader.run_pregame_analysis()` sees a Forfeit status and just returns — but `InGameTrader` still has open orders for the game and doesn't know to cancel them.

**Why it happens:** `SportsTrader` and `InGameTrader` share no state directly (neither owns the other's `_order_log`).

**How to avoid:** The order cancellation responsibility is `InGameTrader`'s. `InGameTrader._handle_score_change()` must call `handle_game_ended()` on hard-halt statuses. `SportsTrader` only needs to skip — it never places in-game orders that need cancellation.

**Warning signs:** After a Forfeit event, `ingame_trader` log shows no `event=handle_game_ended` or `event=blackout_cancel` lines.

### Pitfall 5: Market Tags with Empty Token IDs Silently Passing Validation

**What goes wrong:** A Gamma API response returns a market with empty `clobTokenIds` (`[]`). `_market_dict_to_tag()` produces a `SportsMarketTag` with `token_id_yes=""` and `token_id_no=""`. Trading on an empty token ID fails at the CLOB API level with an opaque error.

**Why it happens:** `_market_dict_to_tag()` in `gamma.py:307` uses `clob_ids[0]` with a fallback of `""` when the list is empty. This is intentional for non-trading use cases but must be filtered before entering `slug_table`.

**How to avoid:** The `_validate_market_tag()` check (`bool(tag.token_id_yes and tag.token_id_no and tag.condition_id)`) catches this before any tag enters `slug_table`.

**Warning signs:** CLOB API errors with `token_id=""` in the error payload.

---

## Code Examples

Verified patterns from reading actual source code:

### Existing `should_halt_trading()` (sports_ws.py:75)
```python
# Source: agents/connectors/sports_ws.py:75
def should_halt_trading(state: "SportGameState") -> bool:
    if state.stale:
        return True
    return state.status in HALT_STATUSES or state.status.lower() in _HALT_STATUSES_LOWER
```

### Existing CLOB Cancel Pattern (ingame_trader.py:673)
```python
# Source: agents/application/ingame_trader.py:673
def _cancel_blackout_orders(self, game_id: int) -> None:
    orders = self._order_log.get(game_id, [])
    if not orders:
        return
    blackout_cutoff = time.time() - (self.blackout_minutes * 60)
    for order in orders:
        order_ts = order.get("timestamp", 0)
        if order_ts < blackout_cutoff:
            continue
        order_id = order.get("order_id")
        if not order_id:
            continue
        try:
            self._polymarket.client.cancel(order_id)
        except Exception as exc:
            print(f"[ingame_trader] event=blackout_cancel_error ...")
```

### Existing `build_slug_table()` Return Shape (gamma.py:430)
```python
# Source: agents/polymarket/gamma.py:430
def build_slug_table(
    self, game_states: "dict[int, SportGameState]"
) -> "tuple[dict[str, list[SportsMarketTag]], list[str]]":
    slug_table: dict[str, list[SportsMarketTag]] = {}
    unmapped: list[str] = []
    for game_id, game_state in game_states.items():
        slug = game_state.slug
        tags = self.lookup_markets_by_slug(slug)
        if not tags:
            tags = self.lookup_markets_fallback(...)
        if tags:
            slug_table[slug] = tags
        else:
            unmapped.append(slug)
    return slug_table, unmapped
```

### Existing `_env_int` Inline Pattern (sports_ws.py:30)
```python
# Source: agents/connectors/sports_ws.py:30
def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
```

### Existing Test Pattern for `_handle_score_change` (test_ingame_trader.py)
```python
# Source: tests/test_ingame_trader.py
def _make_trader(dry_run=True, mocks=None, monkeypatch=None, wallet_balance=0.0, **env_overrides):
    from agents.application.ingame_trader import InGameTrader
    trader = InGameTrader(
        budget_coordinator=mocks["budget"],
        ...
    )
    return trader, mocks
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Flat `HALT_STATUSES` set, no call sites | Split into `PAUSE_STATUSES` + `HARD_HALT_STATUSES`, called in two places | Phase 6 | Games in bad states blocked from trading |
| `build_slug_table()` logs unmapped and discards | Retry with backoff + validation before table insertion | Phase 6 | Fewer games permanently lost due to timing |

**Deprecated/outdated:**
- Nothing is deprecated — this phase extends existing code only.

---

## Open Questions

1. **Retry backoff for slug lookup: should it block the refresh iteration?**
   - What we know: Slug refresh runs every 30 minutes (configurable via `SPORTS_SLUG_REFRESH_INTERVAL_SECONDS=1800`). The main loop sleeps 1 second per iteration.
   - What's unclear: Whether 3 retries at 1s/2s delays (max ~4 seconds per slug) is acceptable. With many unmapped slugs, total wait could be significant.
   - Recommendation: Cap total retry time per refresh cycle with `SPORTS_SLUG_RETRY_MAX_ATTEMPTS` env var (default 3). If more than ~5 slugs unmapped, run retries concurrently in a thread pool to bound total latency.

2. **Auto-halt timeout for paused games**
   - What we know: Locked decision says games in Suspended/Delayed auto-resume when `should_halt_trading()` returns False.
   - What's unclear: Claude's Discretion explicitly leaves "whether pause-resume needs a configurable timeout" as a decision for the planner/executor.
   - Recommendation: Implement without a pause timeout in Phase 6 (YAGNI). If a game is suspended indefinitely, it will never return to InProgress and `should_halt_trading()` will always return True. No runaway trading is possible without the timeout. Add timeout only if a real operational need is observed.

3. **Thread safety of `slug_table` dict during retry**
   - What we know: `slug_table` is a local variable in `sports.py:main()`, not shared across threads. `retry_unmapped_slugs()` mutates it in place.
   - What's unclear: Whether concurrent slug lookups in retry_unmapped_slugs could cause races.
   - Recommendation: Retry is sequential (one slug at a time) within the refresh block. No concurrent mutation occurs. No lock needed.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (pyproject.toml `[tool.pytest.ini_options]`) |
| Config file | `/Users/djbeatbug/RoadToMillion/polyagents/pyproject.toml` |
| Quick run command | `pytest tests/test_sports_ws.py tests/test_ingame_trader.py tests/test_sports_trader.py tests/test_sports_market_discovery.py -x -q` |
| Full suite command | `pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WS-07 | `should_halt_trading()` called in `InGameTrader._handle_score_change()` — paused status skips tick without adding to `_ended_games` | unit | `pytest tests/test_ingame_trader.py -k "halt" -x` | ❌ Wave 0 — add to existing test file |
| WS-07 | `should_halt_trading()` called in `InGameTrader._handle_score_change()` — hard-halt status calls `handle_game_ended()` and cancels orders | unit | `pytest tests/test_ingame_trader.py -k "halt" -x` | ❌ Wave 0 |
| WS-07 | `should_halt_trading()` called in `SportsTrader.run_pregame_analysis()` — skips analysis on any halt status | unit | `pytest tests/test_sports_trader.py -k "halt" -x` | ❌ Wave 0 |
| WS-07 | After Suspended state, next tick with InProgress status resumes trading (auto-resume) | unit | `pytest tests/test_ingame_trader.py -k "resume" -x` | ❌ Wave 0 |
| WS-07 | `HALT_STATUSES == PAUSE_STATUSES | HARD_HALT_STATUSES` still contains all 7 statuses | unit | `pytest tests/test_sports_ws.py::TestShouldHaltTrading -x` | ✅ existing |
| MKT-02 | `retry_unmapped_slugs()` retries up to N times and adds to slug_table on success | unit | `pytest tests/test_sports_market_discovery.py -k "retry" -x` | ❌ Wave 0 |
| MKT-02 | `retry_unmapped_slugs()` logs warning and keeps slug in unmapped after exhausting retries | unit | `pytest tests/test_sports_market_discovery.py -k "retry" -x` | ❌ Wave 0 |
| MKT-02 | `_validate_market_tag()` rejects tags with empty `token_id_yes`, `token_id_no`, or `condition_id` | unit | `pytest tests/test_sports_market_discovery.py -k "valid" -x` | ❌ Wave 0 |
| MKT-02 | `build_slug_table()` validation: tags with empty token IDs go to unmapped, not slug_table | unit | `pytest tests/test_sports_market_discovery.py -k "valid" -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_sports_ws.py tests/test_ingame_trader.py tests/test_sports_trader.py tests/test_sports_market_discovery.py -x -q`
- **Per wave merge:** `pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

New test classes to add to **existing** test files (no new test files needed):

- [ ] `tests/test_ingame_trader.py` — `TestHaltGate` class: tests for `should_halt_trading()` gate in `_handle_score_change()` covering pause (Suspended/Delayed), hard-halt (Forfeit/Canceled), and auto-resume
- [ ] `tests/test_sports_trader.py` — `TestHaltGate` class: tests for `should_halt_trading()` gate in `run_pregame_analysis()` covering all halt statuses
- [ ] `tests/test_sports_market_discovery.py` — `TestRetryUnmappedSlugs` class: tests for retry backoff, success on retry, exhaustion, env var override; `TestValidateMarketTag` class: tests for valid/invalid tag detection
- [ ] `tests/test_sports_ws.py` — `TestStatusCategorization` class: tests that `PAUSE_STATUSES | HARD_HALT_STATUSES == HALT_STATUSES` and each status is in the correct subset

No framework install needed — pytest already configured.

---

## Sources

### Primary (HIGH confidence)
- Direct source code reading — `agents/connectors/sports_ws.py` (all functions verified)
- Direct source code reading — `agents/polymarket/gamma.py` (all methods verified)
- Direct source code reading — `agents/application/ingame_trader.py` (all methods verified)
- Direct source code reading — `agents/application/sports_trader.py` (all methods verified)
- Direct source code reading — `agents/sports.py` (event loop structure verified)
- Direct source code reading — `tests/test_ingame_trader.py`, `tests/test_sports_trader.py`, `tests/test_sports_ws.py`, `tests/test_sports_market_discovery.py` (test patterns verified)
- `.planning/phases/06-safety-resilience-wiring/06-CONTEXT.md` (all locked decisions)
- `.planning/REQUIREMENTS.md` (WS-07, MKT-02 requirements)
- `pyproject.toml` (pytest configuration verified)

### Secondary (MEDIUM confidence)
- `.planning/STATE.md` — established project patterns confirmed (e.g., `_env_int` inline pattern, structured log format)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; all existing code read directly
- Architecture: HIGH — exact call sites identified, exact line numbers and method signatures verified
- Pitfalls: HIGH — derived from reading actual test assertions and understanding exact data flow
- Test gaps: HIGH — existing test files read in full; new tests needed are precisely specified

**Research date:** 2026-03-10
**Valid until:** 2026-06-10 (stable codebase, no fast-moving deps)
