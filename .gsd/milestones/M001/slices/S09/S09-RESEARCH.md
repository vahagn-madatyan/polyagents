# Phase 9: Live Validation - Research

**Researched:** 2026-03-15
**Domain:** Sports pipeline live validation — slug normalization, per-sport debounce configuration, concurrent CLOB rate monitoring
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Validation Safety Mode**
- Default to observe-first validation: dry-run is the baseline for live windows, and real execution should be used only when a requirement truly needs it.
- When live execution is necessary during validation, use the minimum practical live order size rather than normal production sizing.
- Concurrent sports + general pipeline validation should stay below the 60 orders/minute ceiling with margin; do not intentionally probe the cap.
- If a live validation window becomes noisy, unsafe, or otherwise degrades mid-run, immediately drop to dry-run-only and continue collecting evidence instead of continuing live orders.

**Evidence and Completion Standard**
- Phase 9 is not complete until all 9 supported sports are validated against real live Polymarket windows; a representative subset is not enough.
- If a sport does not have a suitable live market during the validation window, keep the phase open rather than closing it with partial coverage.
- Each validation run should produce a structured pass/fail report with observed conditions and captured evidence; short summary-only signoff is not sufficient.
- VALID-03 requires one clean concurrent sports + general pipeline run with captured order-count evidence and clear margin under the cap; repeated or near-limit stress runs are not required.

**Debounce Tuning Posture**
- Tune debounce thresholds per sport type, not as one shared global cooldown.
- Use a conservative tuning bias: prefer fewer, cleaner in-game reactions over maximum responsiveness.
- If some sports receive the shortest debounce despite the conservative posture, that responsiveness should be reserved for low-scoring swing sports where a single score materially changes the game state.
- Near-resolution and other high-leverage late-game situations should become more cautious, not more aggressive.

### Claude's Discretion
- Exact structure of the validation report and evidence artifacts.
- Order in which the 9 sports are scheduled for live validation windows.
- Specific per-sport debounce values and how they are represented in configuration.
- Instrumentation details for counting concurrent orders, provided the output supports the required structured signoff.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| VALID-01 | Slug normalization produces consistent slugs across all 9 sport types with live Polymarket data | GammaMarketClient.build_slug_table + lookup_markets_by_slug + retry_unmapped_slugs already implement the full slug pipeline; Phase 9 must exercise these against live data for all 9 sports and capture pass/fail evidence |
| VALID-02 | Score-change debounce thresholds are configurable per sport type (not just global cooldown) | InGameTrader.cooldown_seconds reads a single SPORTS_INGAME_COOLDOWN_SECONDS env var; Phase 9 must extend this to a per-sport dict keyed by league, with sport-specific env vars (SPORTS_INGAME_COOLDOWN_{LEAGUE}) and a sane default fallback |
| VALID-03 | CLOB rate limiting prevents exceeding 60 orders/min across both sports and general pipelines | BudgetCoordinator.record_sports_trade tracks spend but has no time-windowed order counter; Phase 9 must add order-rate instrumentation and prove both pipelines stay under 60 orders/min during a representative concurrent run |
</phase_requirements>

---

## Summary

Phase 9 is purely a validation and instrumentation phase — no new business logic is invented. All three requirements build directly on code that already exists and is already tested; the work is to (1) extend InGameTrader's global cooldown into a per-sport configurable dict, (2) add order-rate counting so concurrent pipeline throughput is observable, and (3) run the full slug pipeline against live Polymarket data for all 9 supported sports and capture structured evidence.

The codebase is in excellent shape for this phase. The 9 sport types are fully enumerated in `_FINAL_PERIODS` in `ingame_trader.py` (nfl, nba, mlb, nhl, cfb, cbb, soccer, cs2, tennis). The slug resolution pipeline in `GammaMarketClient` covers exact slug lookup, fallback team-name search, tag validation, and exponential-backoff retry. BudgetCoordinator already tracks spend per league via `record_sports_trade`. The dry-run / live-run toggle (`SPORTS_EXECUTE_TRADES` / `EXECUTE_TRADES`) supports the observe-first safety posture from CONTEXT.md.

The three tasks for this phase are: (a) VALID-01 — write a live slug validation script that exercises build_slug_table against a live window and emits a structured sport-by-sport pass/fail report; (b) VALID-02 — replace `self.cooldown_seconds: int` in InGameTrader with a `_per_sport_cooldowns: dict[str, int]` loaded from `SPORTS_INGAME_COOLDOWN_{LEAGUE}` env vars with a default fallback, and add unit tests; (c) VALID-03 — add an order-rate counter to InGameTrader (rolling 60-second window, emits a log line each time it increments) and write a validation script that runs both pipelines concurrently, counts orders, and produces a structured signoff.

**Primary recommendation:** Treat this phase as three independent, well-scoped tasks that share no code dependencies between them. Implement VALID-02 (debounce config) first since it touches production code; do VALID-01 and VALID-03 (validation scripts) in parallel after.

---

## Standard Stack

### Core (already in use — no new dependencies required)

| Component | Location | Purpose | Phase 9 use |
|-----------|----------|---------|-------------|
| `GammaMarketClient` | `agents/polymarket/gamma.py` | Slug lookup, fallback search, retry | VALID-01: exercise against live data, capture results |
| `InGameTrader` | `agents/application/ingame_trader.py` | In-game event classification, cooldown debounce | VALID-02: extend global cooldown to per-sport dict |
| `BudgetCoordinator` | `agents/application/budget.py` | Cross-process spend tracking | VALID-03: extend to count orders per rolling window |
| `agents/sports.py` | pipeline entry point | Wires all components, dry-run flag | VALID-03: start point for concurrent pipeline run |
| `SPORTS_EXECUTE_TRADES` / `EXECUTE_TRADES` | env var | Dry-run toggle | All requirements: safety posture gate |

### Supporting

| Component | Version | Purpose | When to Use |
|-----------|---------|---------|-------------|
| `collections.deque` | stdlib | Rolling time-window order counter | VALID-03: maxlen-based sliding window for 60 orders/min check |
| `time.monotonic()` | stdlib | Timestamp ordering | Already used in `InGameTrader`; use same pattern for order timestamps |
| `pytest` | already installed | Unit test framework | VALID-02 new tests, VALID-03 instrumentation unit tests |
| `filelock` | already installed | Atomic writes | Already used; no change needed |

### No New Dependencies

Phase 9 requires zero new pip installs. All instrumentation uses stdlib (collections.deque, time) and existing project components.

---

## Architecture Patterns

### Recommended Project Structure

No new directories required. New files go in existing locations:

```
agents/
  application/
    ingame_trader.py          # VALID-02: extend cooldown_seconds -> _per_sport_cooldowns
    budget.py                 # VALID-03: add order-rate counter (optional; see below)
scripts/
  validate_slugs.py           # VALID-01: live slug validation runner
  validate_rate_limit.py      # VALID-03: concurrent pipeline rate validation runner
tests/
  test_ingame_trader.py       # VALID-02: new per-sport cooldown tests
  test_ingame_rate_counter.py # VALID-03: order-rate counter unit tests (optional new file)
```

### Pattern 1: Per-Sport Cooldown Dict (VALID-02)

**What:** Replace `self.cooldown_seconds: int` with a `dict[str, int]` keyed by league. Load from `SPORTS_INGAME_COOLDOWN_{LEAGUE}` env vars; fall back to `SPORTS_INGAME_COOLDOWN_SECONDS` global default.

**When to use:** Any time `_is_in_cooldown` or debounce logic needs to check a threshold.

**Lookup helper pattern (matches existing env style):**

```python
# In InGameTrader.__init__
_DEFAULT_COOLDOWN = _env_int("SPORTS_INGAME_COOLDOWN_SECONDS", 30)
_KNOWN_LEAGUES = ("nfl", "nba", "mlb", "nhl", "cfb", "cbb", "soccer", "cs2", "tennis")

self._per_sport_cooldowns: dict[str, int] = {}
for league in _KNOWN_LEAGUES:
    env_key = f"SPORTS_INGAME_COOLDOWN_{league.upper()}"
    val = os.environ.get(env_key)
    if val is not None:
        try:
            self._per_sport_cooldowns[league] = int(val)
        except ValueError:
            pass

# Usage in _is_in_cooldown
def _cooldown_for(self, league: str) -> int:
    return self._per_sport_cooldowns.get(league.lower(), self.cooldown_seconds)
```

**CONTEXT.md constraint:** Conservative bias. Shorter debounces only for low-scoring swing sports (soccer, hockey). Near-resolution caution is handled by existing `_is_near_resolution` — do not change that logic. The conservative defaults recommended by research (see Conservative Debounce Values table below).

### Pattern 2: Rolling Order-Rate Counter (VALID-03)

**What:** In-memory `collections.deque` storing `time.monotonic()` timestamps of placed orders. On each order placement, append timestamp and count entries within the last 60 seconds.

**When to use:** Emit a log line on each order with current 60-second order count; emit a warning if count approaches 50 (leaving margin under 60 cap).

```python
# In InGameTrader.__init__
from collections import deque
self._order_timestamps: deque[float] = deque()

# In _execute_ingame_trade, after successful placement
def _record_order_rate(self) -> None:
    now = time.monotonic()
    self._order_timestamps.append(now)
    # Prune entries older than 60 seconds
    cutoff = now - 60.0
    while self._order_timestamps and self._order_timestamps[0] < cutoff:
        self._order_timestamps.popleft()
    rate = len(self._order_timestamps)
    print(
        f"[ingame_trader] event=order_rate_sample "
        f"orders_per_60s={rate} limit=60"
    )
    if rate >= 50:
        print(
            f"[ingame_trader] warn=order_rate_approaching_limit "
            f"orders_per_60s={rate}"
        )
```

The general pipeline likely has its own order placement path; for VALID-03 the validation script observes combined log output and counts `order_rate_sample` events rather than instrumenting both pipelines at the object level. That keeps the change contained to `InGameTrader`.

### Pattern 3: Structured Validation Report (VALID-01, VALID-03)

**What:** Each validation script emits a structured JSON report file at completion. Follow the existing `[component] event=key value=...` log style for console output; write a summary dict to a file for archival evidence.

**Report fields for VALID-01 (slug validation):**

```python
report = {
    "phase": "VALID-01",
    "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "sports_covered": ["nfl", "nba", ...],   # sports with live games observed
    "sports_pending": ["cs2", ...],           # sports with no live game in window
    "results": {
        "nfl": {
            "slug": "nfl-kc-buf-2026-01-18",
            "lookup_method": "exact|fallback|retry",
            "mapped": True,
            "valid_tag": True,
            "market_id": "...",
        },
        ...
    },
    "pass": True,   # True only if all sports with live games mapped
    "notes": "...",
}
```

**Report fields for VALID-03 (rate limit):**

```python
report = {
    "phase": "VALID-03",
    "run_at": "...",
    "duration_seconds": 600,
    "sports_orders": 12,
    "general_orders": 5,
    "combined_orders": 17,
    "peak_per_60s": 8,
    "limit": 60,
    "margin": 52,
    "pass": True,
}
```

### Anti-Patterns to Avoid

- **Adding a live-only test to the core test suite:** VALID-01 and VALID-03 require live Polymarket connections. They must be standalone scripts in `scripts/`, not in `tests/` — the CI suite must remain runnable offline.
- **Inventing a new logging format:** All evidence output must extend the existing `[component] event=key value=...` style. Do not introduce a separate logging framework or structured logger.
- **Modifying `_is_near_resolution`:** That function already provides conservative late-game caution. Phase 9 must not loosen it; per-sport debounce is an orthogonal concern (pre-event gate, not in-event exit).
- **Making per-sport cooldown dict a global constant:** It must live on the `InGameTrader` instance so tests can override env vars. Do not define it at module level.
- **Probing the 60-order cap:** CONTEXT.md is explicit — the VALID-03 run should demonstrate normal operation with margin, not intentional stress. A single representative 10-minute concurrent window is sufficient evidence.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic order-rate counting across threads | Custom mutex + counter | `collections.deque` + `time.monotonic()` on single-consumer append | InGameTrader already runs single-threaded in tick(); deque append is O(1) and GIL-safe for this usage |
| Slug validation infrastructure | New HTTP client or mock | `GammaMarketClient` (already has retry, validation, fallback logic) | The client is exactly what VALID-01 needs to exercise; calling it directly IS the validation |
| CLOB rate counting across two processes | Inter-process counter | Log aggregation over log output | Both pipelines log to stdout; a validation script counts log lines rather than adding IPC |
| Per-sport env-var parsing | Custom config parser | `os.environ.get(f"SPORTS_INGAME_COOLDOWN_{league.upper()}")` | Already established pattern in BudgetCoordinator (`SPORTS_CAP_{LEAGUE}`) — replicate it |

**Key insight:** The BudgetCoordinator already solves per-sport env-var config with `SPORTS_CAP_{LEAGUE}`. Phase 9 VALID-02 replicates that exact pattern for cooldown thresholds — no new invention needed.

---

## Common Pitfalls

### Pitfall 1: Global Cooldown Variable Not Fully Replaced

**What goes wrong:** `self.cooldown_seconds` is read directly in `_is_in_cooldown`. If a new `_per_sport_cooldowns` dict is added without updating `_is_in_cooldown`, the old global still takes effect for all sports.

**Why it happens:** The attribute is used in one place (`_is_in_cooldown`) but set in another (`__init__`). Easy to update one and miss the other.

**How to avoid:** Update `_is_in_cooldown` to call `self._cooldown_for(league)`. The `league` value must come from the game state, which is not currently passed to `_is_in_cooldown`. The caller `_handle_score_change` has `current: SportGameState`, so pass `current.league` through. Check `handle_period_transition` too — it also calls `_should_process` which calls `_is_in_cooldown`.

**Warning signs:** A test that sets `SPORTS_INGAME_COOLDOWN_NFL=10` still sees 30-second cooldown for NFL games.

### Pitfall 2: VALID-01 Sports Pending vs. Sports Failed Conflation

**What goes wrong:** A sport with no live game in the validation window gets counted as a slug normalization failure.

**Why it happens:** The validation script observes game states from the WebSocket; if a sport has no active game, it produces no evidence but should not be marked "failed."

**How to avoid:** Track two separate lists: `sports_covered` (had a live game, tested slug pipeline) and `sports_pending` (no live game during window — phase stays open). A pass requires `sports_covered` slugs all resolve; `sports_pending` keeps the phase open per CONTEXT.md completion standard.

**Warning signs:** Phase 9 closes with fewer than 9 sports in `sports_covered` and `sports_pending` combined.

### Pitfall 3: Order-Rate Counter Double-Counting in Dry-Run

**What goes wrong:** `_record_order_rate()` is called in `_execute_ingame_trade`, but dry-run returns early before reaching that call. If the counter is moved above the dry-run guard, it inflates the apparent order rate during VALID-03 dry-run evidence collection.

**Why it happens:** Dry-run mode is the default safety posture; the counter must reflect real orders only.

**How to avoid:** Place `_record_order_rate()` inside the `not self.dry_run` branch in `_execute_ingame_trade` — after a successful `polymarket.execute_market_order_for_token` call. Dry-run executions should log `would_trade` but not increment the counter.

**Warning signs:** VALID-03 dry-run evidence shows orders_per_60s > 0 when `dry_run=True`.

### Pitfall 4: Slug Validation Script Timing (Polymarket Gaps)

**What goes wrong:** Running the VALID-01 script at 3am misses all 9 sports because no games are live. The script reports 0 covered, phase stalls indefinitely.

**Why it happens:** Sports seasons and game schedules are temporally sparse. Not all 9 sports will have concurrent live Polymarket markets.

**How to avoid:** Schedule validation windows during peak multi-sport windows (weekday evenings EST, weekends). Per CONTEXT.md, keep the phase open until all 9 are covered — this is the expected behavior, not a failure mode. The validation script should log which sports it observed and which were absent.

**Warning signs:** Phase 9 closes without cs2 or tennis evidence because these are less frequently listed on Polymarket.

### Pitfall 5: `_is_in_cooldown` Receives Wrong League

**What goes wrong:** `handle_period_transition` looks up `_should_process(game_id)` but the game state's league is needed for the per-sport cooldown. If `_should_process` doesn't receive the state, it can't do per-sport lookup.

**Why it happens:** `_should_process` currently only takes `game_id`. Adding league lookup requires either passing the league or reading it from `_prev_game_states`.

**How to avoid:** Read league from `self._prev_game_states.get(game_id)` inside `_is_in_cooldown`, or pass `league` as an explicit parameter. Reading from `_prev_game_states` is simpler and avoids changing the `_should_process` call signature everywhere. If the state is not in `_prev_game_states`, fall back to the global default.

---

## Conservative Debounce Values (VALID-02 Discretion)

These are the research-recommended starting values. They are Claude's discretion per CONTEXT.md — the planner should use these as the defaults unless overridden by later tuning evidence.

| League | Type | Scoring Pattern | Recommended Cooldown | Rationale |
|--------|------|----------------|---------------------|-----------|
| nfl | American football | ~10 scoring events/game | 45s | Slow-paced; scores are rare and high-impact |
| cfb | College football | ~12 scoring events/game | 45s | Same cadence as NFL; big swings between programs |
| nba | Basketball | ~200 points/game | 60s | Frequent scoring; debounce is higher to reduce noise |
| cbb | College basketball | ~140 points/game | 60s | Same reasoning as NBA; slightly higher variance |
| mlb | Baseball | ~9 scoring events/game | 45s | Inning-structured; scores are discrete and meaningful |
| nhl | Hockey | ~6 goals/game | 30s | Low-scoring; each goal is a high-swing event (shortest debounce justified) |
| soccer | Soccer/Football | ~2-3 goals/match | 30s | Extremely low scoring; each goal is maximum-swing (shortest debounce justified) |
| cs2 | Esports (CS2) | ~30 rounds/map | 60s | High-frequency rounds; debounce should suppress round-by-round noise |
| tennis | Tennis | ~50+ points/set | 90s | Set-based resolution; game-level scores are very frequent; want only set-level reactions |

**Env var naming:** `SPORTS_INGAME_COOLDOWN_NFL`, `SPORTS_INGAME_COOLDOWN_NBA`, etc. Matches existing `SPORTS_CAP_{LEAGUE}` pattern in BudgetCoordinator.

---

## Code Examples

### VALID-02: Per-Sport Cooldown Lookup

```python
# Source: InGameTrader.__init__ extension pattern (matches BudgetCoordinator._per_sport_caps)
_KNOWN_LEAGUES = ("nfl", "nba", "mlb", "nhl", "cfb", "cbb", "soccer", "cs2", "tennis")

# In __init__:
self.cooldown_seconds: int = _env_int("SPORTS_INGAME_COOLDOWN_SECONDS", 30)
self._per_sport_cooldowns: dict[str, int] = {}
for league in _KNOWN_LEAGUES:
    env_key = f"SPORTS_INGAME_COOLDOWN_{league.upper()}"
    val = os.environ.get(env_key)
    if val is not None:
        try:
            self._per_sport_cooldowns[league] = int(val)
        except ValueError:
            pass

# New helper method:
def _cooldown_for(self, league: str) -> int:
    """Return per-sport cooldown seconds, falling back to global default."""
    return self._per_sport_cooldowns.get((league or "").lower(), self.cooldown_seconds)
```

### VALID-02: Updated _is_in_cooldown

```python
def _is_in_cooldown(self, game_id: int) -> bool:
    """Return True if game is within its sport-specific cooldown window."""
    last = self._last_processed.get(game_id)
    if last is None:
        return False
    # Read league from prev state to determine sport-specific threshold
    state = self._prev_game_states.get(game_id)
    league = state.league if state else ""
    cooldown = self._cooldown_for(league)
    return (time.time() - last) < cooldown
```

### VALID-03: Rolling Order-Rate Counter

```python
# Source: InGameTrader (new addition)
from collections import deque

# In __init__:
self._order_timestamps: deque = deque()  # timestamps of real (non-dry-run) orders

# New method:
def _record_order_rate(self) -> None:
    """Append order timestamp and emit rate-sample log line."""
    now = time.monotonic()
    self._order_timestamps.append(now)
    cutoff = now - 60.0
    while self._order_timestamps and self._order_timestamps[0] < cutoff:
        self._order_timestamps.popleft()
    rate = len(self._order_timestamps)
    print(
        f"[ingame_trader] event=order_rate_sample "
        f"orders_per_60s={rate} limit=60"
    )
    if rate >= 50:
        print(
            f"[ingame_trader] warn=order_rate_approaching_limit "
            f"orders_per_60s={rate}"
        )

# In _execute_ingame_trade — call only after successful real order:
#   order_id = self._polymarket.execute_market_order_for_token(...)
#   self._record_order_rate()   # <-- add here
```

### VALID-01: Slug Validation Script Structure

```python
# scripts/validate_slugs.py
# Usage: SPORTS_EXECUTE_TRADES=false python scripts/validate_slugs.py
import json, time
from agents.polymarket.gamma import GammaMarketClient
from agents.connectors.sports_ws import SportsWSConnector

connector = SportsWSConnector()
# ... start WS thread, wait for game states ...
client = GammaMarketClient()
game_states = connector.get_all_game_states()
slug_table, unmapped = client.build_slug_table(game_states)
slug_table, still_unmapped = client.retry_unmapped_slugs(unmapped, slug_table)

# Build sport-indexed result
results = {}
for game_id, state in game_states.items():
    league = state.league
    slug = state.slug
    mapped = slug in slug_table and len(slug_table[slug]) > 0
    results[league] = {
        "slug": slug,
        "mapped": mapped,
        "still_unmapped": slug in still_unmapped,
        "tags_count": len(slug_table.get(slug, [])),
    }

report = {
    "phase": "VALID-01",
    "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "sports_covered": [l for l, r in results.items() if not r["still_unmapped"]],
    "sports_failed": [l for l, r in results.items() if r["still_unmapped"]],
    "sports_pending": [],  # filled in if a league has no game in window
    "results": results,
    "pass": all(r["mapped"] for r in results.values()),
}
print(json.dumps(report, indent=2))
```

---

## Existing Test Infrastructure

The 4 key test files are already green (163 tests pass, 0.78s):

| File | Tests | Coverage |
|------|-------|---------|
| `tests/test_sports_market_discovery.py` | 40 | `GammaMarketClient` slug lookup, fallback, validation, retry |
| `tests/test_ingame_trader.py` | ~70 | `InGameTrader` tick, cooldown, classification, fast/slow path, persistence |
| `tests/test_sports_pipeline.py` | ~20 | `agents/sports.py` dry-run resolution, pipeline wiring |
| `tests/test_budget_coordinator.py` | ~33 | `BudgetCoordinator` spend tracking, wallet refresh, filelock |

VALID-02 adds tests to `test_ingame_trader.py` covering: per-sport env var loading, `_cooldown_for` returns per-sport value when set, `_cooldown_for` falls back to global default, `_is_in_cooldown` uses correct sport threshold.

VALID-03 adds tests covering: `_record_order_rate` appends timestamp, pruning removes entries older than 60s, rate counter is not incremented in dry-run mode.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single global cooldown (`SPORTS_INGAME_COOLDOWN_SECONDS`) | Per-sport cooldown dict with global fallback | Phase 9 (this phase) | Lets each sport tune independently without breaking existing deployments |
| No order-rate visibility | Rolling 60-second counter with log sampling | Phase 9 (this phase) | Makes VALID-03 cap compliance provable, not assumed |
| No live slug validation evidence | Structured JSON report per sport per live window | Phase 9 (this phase) | Fulfills VALID-01 completion standard from CONTEXT.md |

**Existing established patterns not changed:**
- `SPORTS_EXECUTE_TRADES` / `EXECUTE_TRADES` dry-run toggle — unchanged
- `[component] event=key value=...` log format — extended, not replaced
- BudgetCoordinator filelock + JSON file state — unchanged
- `_is_near_resolution` conservative late-game logic — unchanged

---

## Open Questions

1. **cs2 and tennis Polymarket availability**
   - What we know: These sports appear in `_FINAL_PERIODS` in ingame_trader.py, confirming they are supported in the codebase.
   - What's unclear: Whether Polymarket regularly lists cs2 or tennis markets. These may be infrequent or seasonal.
   - Recommendation: Per CONTEXT.md, keep the phase open until all 9 are covered. If cs2/tennis have no Polymarket presence at time of running, document that in the report under `sports_pending` and continue; do not proxy with other sports.

2. **General pipeline order rate visibility**
   - What we know: BudgetCoordinator.record_sports_trade exists for the sports side. The general pipeline has a separate execution path not examined here.
   - What's unclear: Whether the general pipeline (non-sports) already has order-rate logging.
   - Recommendation: For VALID-03, run both pipelines, collect combined log output, and count `order_rate_sample` events + any analogous general pipeline order logs. If general pipeline has no order logging, instrument it minimally (one log line per placed order) before running VALID-03.

3. **League field for period transition path in _is_in_cooldown**
   - What we know: `handle_period_transition` calls `_should_process(game_id)` which calls `_is_in_cooldown(game_id)`. At that point the game state IS in `_prev_game_states` (set by tick before the period message is consumed).
   - What's unclear: Edge case where a period transition arrives before the first tick sets the baseline — `_prev_game_states.get(game_id)` would return None.
   - Recommendation: In `_cooldown_for` fallback: if state is None, return `self.cooldown_seconds` (global default). Safe and conservative.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (pyproject.toml: `testpaths = ["tests"]`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/test_ingame_trader.py tests/test_sports_market_discovery.py tests/test_budget_coordinator.py -q` |
| Full suite command | `pytest tests/ -q --ignore=tests/test_event_url_trader.py --ignore=tests/test_news_connector.py --ignore=tests/test_trade_selection.py` |

Note: `test_event_url_trader.py`, `test_news_connector.py`, and `test_trade_selection.py` have collection errors unrelated to Phase 9 (pre-existing). Ignore them in the full suite command.

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VALID-01 | `GammaMarketClient.build_slug_table` + retry maps a slug correctly | unit | `pytest tests/test_sports_market_discovery.py -q` | Yes (40 tests) |
| VALID-01 | Live slug normalization for all 9 sports against Polymarket | live/manual | `python scripts/validate_slugs.py` | No — Wave 0 |
| VALID-02 | `InGameTrader._cooldown_for` returns sport-specific value | unit | `pytest tests/test_ingame_trader.py -q` | No — Wave 0 (new tests needed) |
| VALID-02 | `_is_in_cooldown` uses per-sport threshold | unit | `pytest tests/test_ingame_trader.py -q` | No — Wave 0 |
| VALID-02 | Global cooldown fallback when sport not configured | unit | `pytest tests/test_ingame_trader.py -q` | No — Wave 0 |
| VALID-03 | `_record_order_rate` appends and prunes correctly | unit | `pytest tests/test_ingame_trader.py -q` | No — Wave 0 |
| VALID-03 | Counter not incremented in dry-run | unit | `pytest tests/test_ingame_trader.py -q` | No — Wave 0 |
| VALID-03 | Live concurrent pipeline rate under 60/min | live/manual | `python scripts/validate_rate_limit.py` | No — Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_ingame_trader.py tests/test_sports_market_discovery.py tests/test_budget_coordinator.py -q`
- **Per wave merge:** `pytest tests/ -q --ignore=tests/test_event_url_trader.py --ignore=tests/test_news_connector.py --ignore=tests/test_trade_selection.py`
- **Phase gate:** Full suite green before `/gsd:verify-work`. Live validation scripts (`validate_slugs.py`, `validate_rate_limit.py`) produce JSON reports that are reviewed manually.

### Wave 0 Gaps

- [ ] `tests/test_ingame_trader.py` — new test class `TestPerSportCooldown` covering VALID-02 (4-6 new test cases in existing file)
- [ ] `tests/test_ingame_trader.py` — new test class `TestOrderRateCounter` covering VALID-03 counter unit tests (3-4 new test cases in existing file)
- [ ] `scripts/validate_slugs.py` — live VALID-01 validation runner (new file)
- [ ] `scripts/validate_rate_limit.py` — live VALID-03 concurrent rate validation runner (new file)

---

## Sources

### Primary (HIGH confidence)

- Codebase direct read: `agents/application/ingame_trader.py` — cooldown implementation, 9-sport `_FINAL_PERIODS`, near-resolution logic
- Codebase direct read: `agents/polymarket/gamma.py` — slug lookup, fallback, validation, retry pipeline
- Codebase direct read: `agents/application/budget.py` — `SPORTS_CAP_{LEAGUE}` env-var pattern (template for VALID-02)
- Codebase direct read: `agents/sports.py` — pipeline wiring, dry-run toggle, SPORTS_EXECUTE_TRADES handling
- Codebase direct read: `agents/connectors/sports_ws.py` — 9 supported sports list confirmation, WS URL
- Test run: `pytest tests/test_sports_market_discovery.py tests/test_ingame_trader.py tests/test_sports_pipeline.py tests/test_budget_coordinator.py` — 163 passed, confirms existing suite green

### Secondary (MEDIUM confidence)

- `agents/connectors/sports_data.py` — `_LEAGUE_TO_API_SPORT` and `_LEAGUE_TO_ODDS_SPORT` dicts confirm the 9 supported leagues: nfl, cfb, nba, cbb, mlb, nhl, soccer/mls/epl/ucl, cs2, tennis
- CONTEXT.md (project decisions) — all locked decisions, safety posture, completion standard

### Tertiary (LOW confidence — game scheduling research)

- General sports knowledge about scoring cadence used to derive recommended debounce values; not verified against a reference. The recommended values are starting points for tuning, not hard constraints.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all components examined directly in source code
- Architecture patterns: HIGH — patterns derived from existing production code in the same codebase
- Pitfalls: HIGH — derived from reading the exact methods that will be modified
- Recommended debounce values: LOW — derived from general sports knowledge; treat as tuning starting points, not authoritative

**Research date:** 2026-03-15
**Valid until:** 2026-04-15 (stable codebase — 30 days)