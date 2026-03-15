# Phase 8: Pipeline Integration - Research

**Researched:** 2026-03-13
**Domain:** Python pipeline integration — wiring existing components into trading paths, wallet lifecycle management
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Call `detect_value_bet()` BEFORE LLM analysis in both pre-game and in-game paths — saves API cost by skipping analysis on games with no odds divergence
- Pre-game: insert after data fetch (step 1) in `SportsTrader._analyze_and_trade()`, before LLM call
- In-game: insert after market lookup in `InGameTrader._handle_fast_path()`, before LLM call
- In-game slow path: `InGameTrader._handle_slow_path()` — same placement as fast path
- When `detect_value_bet()` returns False: log a structured skip event AND increment a session counter
- Log format matches existing patterns: `[component] event=no_value_bet game_id=X polymarket_price=Y implied_prob=Z`
- Track filtered count for threshold tuning visibility (e.g., "X/Y games filtered by value bet check")
- Single threshold for both pre-game and in-game (existing `SPORTS_DIVERGENCE_THRESHOLD` env var)
- Do not split into separate pre-game/in-game thresholds
- Refresh wallet balance before each trade execution (not on a timer, not per cycle)
- Add `refresh_wallet_balance(polymarket)` method to BudgetCoordinator — single source of truth
- 30-second cooldown: if last refresh was <30s ago, reuse cached value (prevents API spam during rapid in-game trading)
- On API failure: log warning, fall back to last known balance — never halt trading due to balance fetch error
- Skip refresh entirely in dry-run mode (Polymarket client not initialized, env var value is static)
- Claude's Discretion: pick implied_prob source based on what SportsDataConnector already provides (external odds API preferred if available)
- If implied_prob cannot be determined (missing odds, unsupported sport): skip value bet check and allow the trade through
- detect_value_bet() filter is ACTIVE in dry-run — mirrors production behavior exactly
- Wallet refresh is SKIPPED in dry-run — Polymarket client isn't initialized

### Claude's Discretion
- Implied Probability Source: pick the best source based on what SportsDataConnector already provides (external odds API preferred if available)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PIPE-01 | Pre-game analysis calls `detect_value_bet()` to flag value opportunities before placing trades | Verified: `detect_value_bet()` at `sports_data.py:329` is ready; insertion point is `_analyze_and_trade()` after Step 1 (data fetch), before Step 2 (LLM call) |
| PIPE-02 | In-game fast-path calls `detect_value_bet()` to validate trades against external odds divergence | Verified: `_handle_fast_path()` structure is clear; insertion point is after cache read + live price fetch (Step 2), before divergence gate (Step 3); same pattern applies to `_run_slow_path()` |
| PERS-01 | `wallet_balance` is periodically refreshed during pipeline execution (not just at startup) | Verified: `get_usdc_balance()` at `polymarket.py:838` is the fetch method; `BudgetCoordinator` is the right home for `refresh_wallet_balance()`; 30s cooldown pattern follows existing `_is_in_cooldown()` approach |
</phase_requirements>

## Summary

Phase 8 is a pure integration phase — no new algorithms, no new external dependencies. Three existing but disconnected components (`detect_value_bet()`, `get_usdc_balance()`, and `BudgetCoordinator`) need to be wired into the live trading pipeline at specific, well-defined insertion points.

The research confirms the codebase is in a clean state to receive these changes. All three integration points are unambiguous. The `detect_value_bet()` function (line 329, `sports_data.py`) is a one-liner that compares `abs(polymarket_price - implied_prob) > _divergence_threshold`. The implied probability source is `game_context["external_odds"]` from `get_game_context()` — this is already fetched in Step 1 of both pipelines, so no new API calls are needed. The wallet refresh belongs in `BudgetCoordinator` as `refresh_wallet_balance(polymarket)`, using a `_last_wallet_refresh` timestamp to enforce the 30-second cooldown, and falls back to `self.wallet_balance` on API error.

The test suite (121 passing, 0.30s) is healthy and structured for surgical extension. New tests for the value-bet filter and wallet refresh fit cleanly into the existing test class pattern.

**Primary recommendation:** Wire `detect_value_bet()` into both paths using `game_context["external_odds"]` as the implied probability source. When odds are unavailable (None), skip the check and allow the trade through. Add `refresh_wallet_balance()` to `BudgetCoordinator` with timestamp-gated cooldown. Call it from `InGameTrader._fast_path()` and `SportsTrader._analyze_and_trade()` just before `can_spend_sports()`.

## Standard Stack

### Core (all already installed — no new deps)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `filelock` | existing | Thread/process-safe lock for BudgetCoordinator | Already used in BudgetCoordinator and InGameTrader persistence |
| `time` | stdlib | Timestamp tracking for wallet refresh cooldown | Already used for `_last_processed` cooldown in InGameTrader |
| `agents.utils.env._env_float` | internal | Read `SPORTS_ODDS_DIVERGENCE_THRESHOLD` | Already imported in sports_data.py |

### No New Dependencies Required
This phase introduces zero new packages. All functionality derives from wiring existing code.

## Architecture Patterns

### Existing Pattern: Skip + Log + Counter
The codebase has well-established skip event patterns (e.g., `event=skip_budget_exhausted`, `event=skip_low_confidence`, `event=fast_path_skip reason=no_cache_entry`). The value-bet skip follows this exact structure.

```python
# Pattern from ingame_trader.py (existing)
print(
    f"[ingame_trader] event=fast_path_skip game_id={game_id} "
    f"reason=low_divergence divergence={divergence:.4f} "
    f"threshold={self.min_confidence_gap:.4f}"
)

# New value-bet skip (same structure):
print(
    f"[ingame_trader] event=no_value_bet game_id={game_id} "
    f"polymarket_price={polymarket_price:.4f} implied_prob={implied_prob:.4f}"
)
```

### Existing Pattern: Dry-Run Gating
All Polymarket API calls are guarded by `if not self.dry_run:`. The wallet refresh follows this exactly:

```python
# Existing pattern (sports.py:73-81)
if not dry_run:
    from agents.polymarket.polymarket import Polymarket
    polymarket = Polymarket(initialize_clob_client=True)
    wallet_balance = polymarket.get_usdc_balance()
else:
    polymarket = None
    wallet_balance = _env_float("SPORTS_INITIAL_WALLET_USD", 1000.0)

# New refresh_wallet_balance() method — same gate:
def refresh_wallet_balance(self, polymarket) -> float:
    if polymarket is None:
        return self.wallet_balance  # dry-run: return static value
    ...
```

### Existing Pattern: Cooldown via Timestamp
`InGameTrader._is_in_cooldown()` uses `_last_processed: dict[int, float]` + `time.time()`. The wallet refresh cooldown uses the same approach but with a single scalar timestamp:

```python
# Existing (ingame_trader.py:638-643)
def _is_in_cooldown(self, game_id: int) -> bool:
    last = self._last_processed.get(game_id)
    if last is None:
        return False
    return (time.time() - last) < self.cooldown_seconds

# New BudgetCoordinator refresh cooldown:
_WALLET_REFRESH_COOLDOWN_SECONDS = 30

def refresh_wallet_balance(self, polymarket) -> float:
    if polymarket is None:
        return self.wallet_balance
    now = time.time()
    if (now - self._last_wallet_refresh) < _WALLET_REFRESH_COOLDOWN_SECONDS:
        return self.wallet_balance  # cache hit
    try:
        balance = polymarket.get_usdc_balance()
        self.wallet_balance = balance
        self._last_wallet_refresh = now
        print(f"[budget_coordinator] event=wallet_refreshed balance={balance:.2f}")
        return balance
    except Exception as exc:
        print(f"[budget_coordinator] warn=wallet_refresh_failed error={exc} "
              f"using_cached={self.wallet_balance:.2f}")
        return self.wallet_balance
```

### Existing Pattern: Implied Probability from game_context
`game_context` is a dict returned by `SportsDataConnector.get_game_context()`. It always contains `"external_odds"` which is either a dict with `"implied_home_prob"` / `"implied_away_prob"` or `None` if the odds API returned nothing.

The value-bet caller must:
1. Extract `game_context["external_odds"]`
2. If None: skip the check, allow trade through (optimization filter, not safety gate)
3. If present: determine which implied_prob to compare (home vs away based on candidate outcome or Polymarket token being Yes/No)

For pre-game, the candidate is not yet computed at insertion point (Step 1.5, after data fetch, before LLM). The comparison uses the Polymarket price for the YES outcome (`market_tag.outcome_prices` parsed as first value), compared against `implied_home_prob` (since Yes = home win on most Polymarket sports markets).

For fast-path in-game: `live_price` is the Polymarket Yes token price, so `implied_home_prob` is the comparison target.

```python
# Implied probability extraction pattern:
external_odds = game_context.get("external_odds")
if external_odds is None:
    # Cannot determine — skip check, allow through
    pass
else:
    polymarket_price = ...  # the Yes-outcome Polymarket price
    implied_prob = external_odds.get("implied_home_prob", 0.0)
    if not self.data_connector.detect_value_bet(polymarket_price, implied_prob):
        self._no_value_bet_count += 1
        print(
            f"[sports_trader] event=no_value_bet game_id={game_id} "
            f"polymarket_price={polymarket_price:.4f} implied_prob={implied_prob:.4f}"
        )
        return
```

### Recommended Insertion Points

**Pre-game (`SportsTrader._analyze_and_trade()`):**
```
Step 1: game_context = self.data_connector.get_game_context(game_state)
>>> INSERT VALUE-BET FILTER HERE (after Step 1, before Step 2)
Step 2: candidate = self.executor.analyze_game(...)
Step 3: cache.set(...)
Step 4: confidence gate
Step 5: budget gate (call refresh_wallet_balance before can_spend_sports)
Step 6: dry-run gate
Step 7: execute
```

The Polymarket Yes price for pre-game filter: use `market_tag.outcome_prices`. This is a comma-separated string (e.g., `"0.6,0.4"`). Parse as `float(market_tag.outcome_prices.split(",")[0])`. This is consistent with how `_build_cache_entry()` extracts `polymarket_price_at_analysis` via `candidate.outcome_prices[0]` — same logical price, available earlier from `market_tag`.

**In-game fast path (`InGameTrader._fast_path()`):**
```
Step 1: cache read
Step 2: live_price = polymarket.get_orderbook_price(...)
>>> INSERT VALUE-BET FILTER HERE (using live_price as polymarket_price, implied_home_prob from game_context)
Step 3: divergence = abs(llm_prob - live_price)  [existing fast-path divergence — different concept]
Step 4: outcome determination
Step 5: exposure cap
Step 6: budget gate (call refresh_wallet_balance before can_spend_sports)
Step 7: execute
```

Note: The fast path does NOT fetch `game_context` — that's the slow path's job. To get `external_odds` in the fast path, use the PregameCache entry: the cache already stores `polymarket_price_at_analysis` but not `implied_prob`. There are two options:
- **Option A (preferred per CONTEXT.md):** Store `implied_prob` in the PregameCache entry during pre-game analysis, read it back in fast path
- **Option B:** Accept that fast-path skips value-bet check when no implied_prob is in cache (allows through as optimization, not safety gate)

Given CONTEXT.md says "use pre-game odds (cached from analysis), do not fetch live in-game odds" — Option A is correct. The pre-game analysis should persist `implied_home_prob` into the cache entry, and fast path reads it from cache.

**In-game slow path (`InGameTrader._run_slow_path()`):**
The slow path already fetches `game_context` (Step 1). Insert value-bet filter after Step 1, before LLM call (Step 2). Same pattern as pre-game.

**Session counter placement:**
Add `self._no_value_bet_count: int = 0` to `__init__` of both `SportsTrader` and `InGameTrader`. Increment on each filtered-out call. Log the running total periodically (or log it on each skip as "filtered={count}" appended to the existing log line).

### Anti-Patterns to Avoid
- **Fetching live odds in the fast path:** The fast path is latency-sensitive. Never call `get_external_odds()` from `_fast_path()`. Use cached pre-game odds only.
- **Raising exceptions on wallet refresh failure:** The refresh must always return a float. API errors become warnings and the cached value is returned.
- **Blocking the main thread on wallet refresh:** `get_usdc_balance()` uses an HTTP client with 10s timeout. Call refresh before the budget gate, not inside a lock. The 30s cooldown prevents repeated blocking.
- **Splitting the divergence threshold:** CONTEXT.md is explicit — one threshold for both paths. Do not add a second env var.
- **Making value-bet a hard gate for unsupported sports:** When odds unavailable (None), allow trade through. This is a filter, not a blocker.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cooldown timestamp | Custom timer class | `time.time()` + scalar `_last_wallet_refresh` | Already established pattern in InGameTrader |
| Thread-safe budget update | Custom locking | Existing `FileLock` in BudgetCoordinator | Already implemented and tested |
| Odds divergence calculation | Custom math | `detect_value_bet(polymarket_price, implied_prob)` | Already implemented, one-liner |
| USDC balance fetch | Direct chain call | `polymarket.get_usdc_balance()` | Already implemented in Polymarket class |

## Common Pitfalls

### Pitfall 1: Fast-Path Has No game_context
**What goes wrong:** Trying to call `data_connector.get_external_odds()` directly inside `_fast_path()` adds latency that defeats the fast path's purpose.
**Why it happens:** Assuming game_context is available everywhere like it is in the slow path.
**How to avoid:** Store `implied_home_prob` in the PregameCache entry during pre-game analysis. Fast path reads it from cache. If the cache entry has no `implied_home_prob` key, skip the value-bet check (allow through).
**Warning signs:** Any import of `SportsDataConnector.get_external_odds` inside `_fast_path()`.

### Pitfall 2: Wallet Refresh Called Inside FileL ock
**What goes wrong:** If `refresh_wallet_balance()` is called while a `FileLock` is held, and the HTTP request takes 5-10 seconds, other processes waiting on the lock will time out.
**Why it happens:** Placing the refresh call inside `record_sports_trade()` or another locked method.
**How to avoid:** Call `refresh_wallet_balance()` before entering any filelock scope, not inside one. The refresh method itself should NOT acquire the budget file lock.
**Warning signs:** `refresh_wallet_balance()` called from `record_sports_trade()` or `_write_budget_file()`.

### Pitfall 3: Session Counter Not Initialized
**What goes wrong:** `AttributeError: 'SportsTrader' object has no attribute '_no_value_bet_count'` at runtime when the first no_value_bet event fires.
**Why it happens:** Adding the counter log line before adding `self._no_value_bet_count = 0` to `__init__`.
**How to avoid:** Initialize counter in `__init__` before any code that uses it. Tests will catch this quickly.

### Pitfall 4: market_tag.outcome_prices Parsing
**What goes wrong:** `market_tag.outcome_prices` is a string `"0.6,0.4"`, not a list. Using `[0]` directly fails.
**Why it happens:** Assuming the field is already parsed, consistent with `CandidateTrade.outcome_prices` which is a list.
**How to avoid:** Parse as `float(market_tag.outcome_prices.split(",")[0])` before passing to `detect_value_bet()` as the Polymarket price. Add a guard for empty/malformed string — if parsing fails, skip the check.

### Pitfall 5: BudgetCoordinator._last_wallet_refresh Not Initialized
**What goes wrong:** `AttributeError` or `UnboundLocalError` on first call to `refresh_wallet_balance()` when comparing `time.time() - self._last_wallet_refresh`.
**Why it happens:** Forgetting to initialize `self._last_wallet_refresh = 0.0` in `BudgetCoordinator.__init__()`.
**How to avoid:** Initialize to `0.0` so first call always triggers a real refresh (since `time.time() - 0.0 >> 30`).

### Pitfall 6: wallet_balance Argument to can_spend_sports Stays Stale
**What goes wrong:** `can_spend_sports(trade_amount, wallet_balance)` is called with the startup wallet_balance parameter, not the refreshed value. Refresh runs but result is discarded.
**Why it happens:** Refreshed value not captured and substituted into the budget gate call.
**How to avoid:** Replace `wallet_balance` argument with the return value from `refresh_wallet_balance()` at each call site. In SportsTrader, the `wallet_balance` parameter in `run_pregame_analysis()` / `_analyze_and_trade()` must be replaced. In InGameTrader, `self._wallet_balance` must be updated.

## Code Examples

### detect_value_bet() Signature (sports_data.py:329)
```python
# Source: /agents/connectors/sports_data.py line 329
def detect_value_bet(self, polymarket_price: float, implied_prob: float) -> bool:
    """Return True when |polymarket_price - implied_prob| exceeds configured threshold."""
    return abs(polymarket_price - implied_prob) > self._divergence_threshold
```
Threshold env var: `SPORTS_ODDS_DIVERGENCE_THRESHOLD` (default 0.05).

### get_usdc_balance() Signature (polymarket.py:838)
```python
# Source: /agents/polymarket/polymarket.py line 838
def get_usdc_balance(self) -> float:
    report = self.get_usdc_balance_report()
    return float(report.get("available_usdc_balance", 0.0))
```

### Existing Wallet Balance Fetch at Startup (sports.py:73-81)
```python
# Source: /agents/sports.py lines 73-81
if not dry_run:
    from agents.polymarket.polymarket import Polymarket
    polymarket = Polymarket(initialize_clob_client=True)
    wallet_balance = polymarket.get_usdc_balance()
else:
    polymarket = None
    wallet_balance = _env_float("SPORTS_INITIAL_WALLET_USD", 1000.0)
```

### BudgetCoordinator.__init__ Current State (budget.py:61)
```python
# Source: /agents/application/budget.py lines 61-85
def __init__(self, wallet_balance: float) -> None:
    self.wallet_balance = max(0.0, float(wallet_balance))
    # ... rest of init
```
`refresh_wallet_balance()` stores its timestamp as `self._last_wallet_refresh = 0.0` added here.

### Pre-Game Value-Bet Insertion (SportsTrader._analyze_and_trade)
Insert between existing Step 1 and Step 2:
```python
# After: game_context = self.data_connector.get_game_context(game_state)
# Before: candidate = self.executor.analyze_game(...)

external_odds = game_context.get("external_odds")
if external_odds is not None:
    try:
        polymarket_price = float(market_tag.outcome_prices.split(",")[0])
        implied_prob = external_odds.get("implied_home_prob", 0.0)
        if not self.data_connector.detect_value_bet(polymarket_price, implied_prob):
            self._no_value_bet_count += 1
            print(
                f"[sports_trader] event=no_value_bet game_id={game_id} "
                f"polymarket_price={polymarket_price:.4f} implied_prob={implied_prob:.4f} "
                f"filtered={self._no_value_bet_count}"
            )
            return
    except (ValueError, AttributeError):
        pass  # malformed outcome_prices — skip check, allow through
```

### Cache Entry Augmentation for Fast-Path
In `SportsTrader._build_cache_entry()`, add `implied_home_prob` so fast-path can use it:
```python
# Add to the returned dict:
"implied_home_prob": (
    game_context.get("external_odds", {}) or {}
).get("implied_home_prob", None),
```
In `InGameTrader._fast_path()`, read it back:
```python
implied_prob = cache_entry.get("implied_home_prob")
if implied_prob is not None:
    live_price_for_vb = live_price  # live_price already fetched (Step 2)
    if not self._data_connector.detect_value_bet(live_price_for_vb, implied_prob):
        self._no_value_bet_count += 1
        print(
            f"[ingame_trader] event=no_value_bet game_id={game_id} "
            f"polymarket_price={live_price_for_vb:.4f} implied_prob={implied_prob:.4f} "
            f"filtered={self._no_value_bet_count}"
        )
        self._mark_processed(game_id)
        return
```

## State of the Art

This phase deals with internal codebase integration only. No external library changes are relevant.

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Startup-only wallet_balance | Runtime refresh via `refresh_wallet_balance()` | Phase 8 (now) | Budget gate uses live balance, not stale startup value |
| detect_value_bet() unused in pipeline | Wired as pre-LLM filter in both paths | Phase 8 (now) | LLM calls skipped on non-divergent games, saves API cost |

## Open Questions

1. **Which side's implied probability to compare in pre-game?**
   - What we know: Polymarket sports markets use Yes = home win, No = away win. `implied_home_prob` from external odds maps to the Yes token. The pre-game value-bet filter should compare Polymarket Yes price against `implied_home_prob`.
   - What's unclear: For some markets this mapping may not hold (e.g., "Will Team X cover the spread?"). However, per CONTEXT.md the filter is not a safety gate, so any mismatch merely allows an extra trade through.
   - Recommendation: Use `implied_home_prob` and Polymarket Yes price. Document assumption. No action needed if wrong — trade is allowed through.

2. **Where to call refresh_wallet_balance() in InGameTrader?**
   - What we know: InGameTrader stores `self._wallet_balance` set at construction. The budget gate in both fast and slow paths passes `self._wallet_balance` to `can_spend_sports()`.
   - What's unclear: Should `self._wallet_balance` be updated in-place, or should refresh return a value used only for the gate call?
   - Recommendation: Update `self._wallet_balance` in-place from the return value of `refresh_wallet_balance()`. Call before each budget gate check. The 30-second cooldown in BudgetCoordinator prevents excessive API calls.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (pyproject.toml `[tool.pytest.ini_options]`) |
| Config file | `pyproject.toml` — `testpaths = ["tests"]`, `asyncio_mode = "auto"` |
| Quick run command | `python -m pytest tests/test_sports_trader.py tests/test_ingame_trader.py tests/test_budget_coordinator.py -q` |
| Full suite command | `python -m pytest -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PIPE-01 | Pre-game calls `detect_value_bet()` before LLM; skips and logs when False | unit | `python -m pytest tests/test_sports_trader.py -k "value_bet" -q` | Wave 0 (new tests needed) |
| PIPE-01 | Pre-game allows trade through when external_odds is None | unit | `python -m pytest tests/test_sports_trader.py -k "value_bet" -q` | Wave 0 |
| PIPE-01 | Session counter increments on each filtered game | unit | `python -m pytest tests/test_sports_trader.py -k "value_bet" -q` | Wave 0 |
| PIPE-02 | Fast-path calls `detect_value_bet()` using cached implied_prob; returns early when False | unit | `python -m pytest tests/test_ingame_trader.py -k "value_bet" -q` | Wave 0 |
| PIPE-02 | Fast-path skips value-bet check when no implied_prob in cache | unit | `python -m pytest tests/test_ingame_trader.py -k "value_bet" -q` | Wave 0 |
| PIPE-02 | Slow-path calls `detect_value_bet()` after game_context fetch | unit | `python -m pytest tests/test_ingame_trader.py -k "value_bet" -q` | Wave 0 |
| PIPE-02 | implied_home_prob stored in cache entry during pre-game build | unit | `python -m pytest tests/test_sports_trader.py -k "cache_entry" -q` | Existing test augmented |
| PERS-01 | `refresh_wallet_balance(polymarket)` returns fresh balance on first call | unit | `python -m pytest tests/test_budget_coordinator.py -k "refresh" -q` | Wave 0 |
| PERS-01 | Cooldown returns cached value when <30s since last refresh | unit | `python -m pytest tests/test_budget_coordinator.py -k "refresh" -q` | Wave 0 |
| PERS-01 | API failure returns cached balance (no exception raised) | unit | `python -m pytest tests/test_budget_coordinator.py -k "refresh" -q` | Wave 0 |
| PERS-01 | Dry-run (polymarket=None) returns static wallet_balance immediately | unit | `python -m pytest tests/test_budget_coordinator.py -k "refresh" -q` | Wave 0 |
| PERS-01 | `self._wallet_balance` in InGameTrader updated after successful refresh | unit | `python -m pytest tests/test_ingame_trader.py -k "wallet" -q` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_sports_trader.py tests/test_ingame_trader.py tests/test_budget_coordinator.py -q`
- **Per wave merge:** `python -m pytest -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] New test class `TestValueBetFilter` in `tests/test_sports_trader.py` — covers PIPE-01 behaviors (value bet filter in pre-game path)
- [ ] New test class `TestValueBetFilter` in `tests/test_ingame_trader.py` — covers PIPE-02 behaviors (value bet filter in fast and slow paths)
- [ ] New test class `TestWalletRefresh` in `tests/test_budget_coordinator.py` — covers PERS-01 (refresh method, cooldown, error fallback, dry-run skip)
- [ ] Augment `TestRunPregameAnalysis::test_cache_entry_has_required_fields` to check `implied_home_prob` field

## Sources

### Primary (HIGH confidence)
- Direct code read: `/agents/connectors/sports_data.py:329` — `detect_value_bet()` signature and implementation verified
- Direct code read: `/agents/application/budget.py:61-179` — `BudgetCoordinator.__init__`, `can_spend_sports()`, file lock patterns verified
- Direct code read: `/agents/application/sports_trader.py:114-283` — `_analyze_and_trade()` step sequence verified, exact insertion point confirmed
- Direct code read: `/agents/application/ingame_trader.py:353-444` — `_fast_path()` step sequence verified, exact insertion point confirmed
- Direct code read: `/agents/application/ingame_trader.py:450-577` — `_run_slow_path()` step sequence verified
- Direct code read: `/agents/polymarket/polymarket.py:838-840` — `get_usdc_balance()` signature verified
- Direct code read: `/agents/sports.py:59-244` — startup wallet fetch pattern and pipeline wiring verified
- Test run: `python -m pytest tests/test_sports_trader.py tests/test_ingame_trader.py tests/test_budget_coordinator.py -q` — 121 passed, 0 failures

### Secondary (MEDIUM confidence)
- None required — all research done from live source code inspection

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new deps; all code read directly from source
- Architecture: HIGH — all insertion points verified by reading actual method bodies
- Pitfalls: HIGH — derived from reading the actual code structure (e.g., `market_tag.outcome_prices` string format confirmed in `_build_cache_entry`)
- Test strategy: HIGH — existing test pattern verified, 121 tests pass

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (stable codebase, low churn expected)