# Phase 4: Live In-Game Trading Engine - Research

**Researched:** 2026-03-06
**Domain:** Python in-game event processing, CLOB order management, cooldown/debounce patterns
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Fast-path vs Slow-path Decision Routing**
- Event type classification determines path: classify each score event as minor (routine scoring, no lead change) or major (lead change, period transition, overtime start, game resumption after delay)
- Minor events: fast-path — read cached pre-game probability from PregameCache, compare against current Polymarket price, trade if divergence exceeds threshold. No LLM call
- Major events: slow-path — run full SportsExecutor.analyze_game() with updated game state. Full LLM two-stage pipeline
- Fast-path uses cached probability as-is — no adjustment based on score change. Treat pre-game probability as the anchor; if Polymarket price has moved but cached prob says value exists, trade
- Lead changes always trigger slow-path — momentum shift warrants full LLM re-evaluation

**Debounce and Cooldown**
- Per-game cooldown timer: after processing any score event (fast or slow), ignore new events for that game for N seconds
- Default cooldown: 30 seconds, configurable via `SPORTS_INGAME_COOLDOWN_SECONDS` env var
- Cooldown applies to BOTH fast-path and slow-path events — prevents rapid-fire trades that would hit CLOB rate limits (60 orders/min shared across pipelines)
- Per-game cooldowns only — no global rate limit across all games. With 30s cooldowns, even 10 concurrent games max out at ~20 LLM calls/min
- Extend existing `in_flight` set pattern from SportsTrader with timestamps for cooldown tracking

**Game-Ended Safeguards**
- On `ended: true`: halt ALL new order placement for that game immediately
- Cancel orders placed within configurable blackout window before game end (e.g., `SPORTS_BLACKOUT_MINUTES` default 2 minutes) — prevents getting filled at stale prices right at resolution
- Proactive blackout: also prevent NEW order placement when game is in final period AND elapsed time suggests resolution is near — don't place orders that would be immediately cancelled
- In-memory order log: dict of `{game_id: [{order_id, timestamp, market_id}]}` for all orders placed during session. On game end, look up and cancel matching orders within blackout window. Lost on restart but sufficient for single session
- Retain game state for settlement window after end — matches existing `SPORTS_WS_ENDED_GAME_TTL_MINUTES` from Phase 1. Allows post-game logging and debugging

**In-Game Position Management**
- New `InGameTrader` class — separate from SportsTrader. Clear separation: SportsTrader handles pre-game, InGameTrader handles live. Both share SportsExecutor and PregameCache
- Allow position reversal: slow-path LLM can recommend switching sides (e.g., Yes to No) if game state warrants it. Sell existing position and take opposite side on strong conviction
- Per-game max exposure: track total USD spent per game across all trades (pre-game + in-game). Enforce configurable max via `SPORTS_MAX_GAME_EXPOSURE_USD`. Prevents over-concentrating on one game
- Separate in-game confidence gap threshold: `SPORTS_INGAME_MIN_CONFIDENCE_GAP` (default 0.15, higher than pre-game's 0.10). In-game trades are riskier — tighter conviction bar

### Claude's Discretion
- Exact event classification logic per sport (what constitutes a "lead change" in different scoring systems)
- InGameTrader class structure and method design
- How proactive blackout detects "near resolution" per sport (final period + elapsed time heuristics)
- Order cancellation API calls to CLOB (cancel by order_id)
- How InGameTrader wires into sports.py event loop alongside SportsTrader
- Fast-path Polymarket price fetch mechanism (existing gamma client or CLOB API)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TRD-02 | Bot executes autonomous in-game trades reacting to live game state changes | InGameTrader class consumes `connector.get_message_queue()` events, classifies as minor/major, routes to fast/slow path. CLOB cancel API (`client.cancel()`) confirmed available |
| TRD-03 | Bot triggers trade re-evaluation within 5 seconds of a score change event from the websocket | Message queue is non-blocking (`get_nowait`). Sports.py event loop sleeps 1s per iteration. Event detection is synchronous within the loop; per-game cooldown DEFERS action but does not delay detection |
| TRD-05 | Bot applies score-change debouncing to prevent LLM call queue overflow during rapid game state changes | Per-game cooldown via timestamp dict extending `_in_flight` pattern. Fast-path trades are gated by cooldown too — prevents LLM call stacking |
</phase_requirements>

---

## Summary

Phase 4 adds `InGameTrader` — a new class at `agents/application/ingame_trader.py` that consumes the already-streaming message queue from `SportsWSConnector.get_message_queue()`. Every message is a `period_transition` event dict (keys: `type`, `state`, `old_period`, `new_period`). The websocket already emits score changes via the `score_change` log line but does NOT enqueue them — only period transitions enter the queue. This is a critical gap: for score-change events (which are the primary driver of in-game trading), InGameTrader must read raw game state updates differently.

The existing message queue emits `period_transition` events. Score changes without period transitions are only logged; they never reach the queue. InGameTrader needs to handle BOTH: period transitions (already in queue) AND score changes (need score state comparison on each loop iteration). The clean solution is to extend `_process_game_state` in SportsWSConnector to also enqueue `score_change` events, OR have InGameTrader poll `get_all_game_states()` and diff snapshots each loop — the latter keeps SportsWSConnector unchanged, matching the project's established pattern.

The py_clob_client library has `client.cancel(order_id)` (single, Level 2 Auth) and `client.cancel_orders(order_ids)` (batch, Level 2 Auth). The existing `Polymarket` wrapper does not expose cancel methods yet — InGameTrader will need to call `self.polymarket.client.cancel(order_id)` directly or add a thin wrapper. The `get_orderbook_price(token_id)` method already exists on `Polymarket` for fast-path current price fetch.

**Primary recommendation:** Implement InGameTrader as a snapshot-diff consumer over `get_all_game_states()` for score-change detection, plus consuming the existing queue for period transitions. Wire into sports.py main loop alongside SportsTrader. Extend `_process_game_state` in SportsWSConnector to also enqueue score_change events (simpler, aligns queuing with period_transition pattern).

## Standard Stack

### Core (already present — no new installs required)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `py_clob_client` | installed | CLOB order cancel API | Already used for order placement; `client.cancel()` is Level 2 Auth |
| `threading` | stdlib | Daemon threads for slow-path analysis | Matches Phase 3 pattern exactly |
| `queue` | stdlib | Message queue consumption | `connector.get_message_queue()` already returns `queue.Queue` |
| `time` | stdlib | Cooldown timestamp tracking | Inline `time.time()` for per-game cooldown dict |
| `filelock` | installed | PregameCache concurrent writes | Already used — InGameTrader reads cache without lock (read-safe) |

### No New Dependencies Required

Phase 4 is pure integration of existing infrastructure. No new packages needed. All capabilities are available through:
- `SportsWSConnector` — event source
- `PregameCache` — fast-path probability read
- `SportsExecutor` — slow-path LLM analysis
- `Polymarket.client` — cancel API (via direct `client` attribute access)
- `Polymarket.get_orderbook_price(token_id)` — live price for fast-path divergence check

**Installation:**
```bash
# No new installs — all dependencies satisfied by Phase 3 environment
```

## Architecture Patterns

### Recommended Project Structure

```
agents/
├── application/
│   ├── sports_trader.py      # Phase 3 — pre-game (unchanged)
│   └── ingame_trader.py      # NEW — Phase 4 in-game trading engine
├── sports.py                 # MODIFIED — wire InGameTrader into event loop
agents/connectors/
└── sports_ws.py              # OPTIONALLY MODIFIED — enqueue score_change events
.env.example                  # ADD 4 new env vars
```

### Pattern 1: Per-Game Cooldown via Timestamp Dict

**What:** Extend the `_in_flight` set pattern from SportsTrader with float timestamps. A game is "in cooldown" if it has an entry with timestamp within the last N seconds.

**When to use:** Every event processed (fast or slow path) updates the cooldown timestamp for that game_id.

**Example:**
```python
# Inline env helper (matches established project pattern)
def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default

class InGameTrader:
    def __init__(self, ...):
        self._cooldown_seconds: int = _env_int("SPORTS_INGAME_COOLDOWN_SECONDS", 30)
        # {game_id: timestamp_of_last_processed_event}
        self._last_processed: dict[int, float] = {}
        # {game_id: [{order_id, timestamp, market_id}]}
        self._order_log: dict[int, list[dict]] = {}
        # {game_id: float} — total USD committed per game across all trades
        self._game_exposure: dict[int, float] = {}

    def _is_in_cooldown(self, game_id: int) -> bool:
        last = self._last_processed.get(game_id, 0.0)
        return (time.time() - last) < self._cooldown_seconds

    def _mark_processed(self, game_id: int) -> None:
        self._last_processed[game_id] = time.time()
```

### Pattern 2: Score-Change Event Detection via Snapshot Diff

**What:** InGameTrader holds a previous snapshot of game states. Each loop iteration it compares current snapshot against previous to detect score changes without modifying SportsWSConnector.

**When to use:** Called from the sports.py main loop every iteration (1s sleep).

**Example:**
```python
class InGameTrader:
    def __init__(self, connector: SportsWSConnector, ...):
        self._connector = connector
        self._prev_game_states: dict[int, SportGameState] = {}

    def process_score_changes(self, current_states: dict[int, SportGameState]) -> None:
        for game_id, current in current_states.items():
            prev = self._prev_game_states.get(game_id)
            if prev is None:
                # First time seeing this game — no baseline to compare against
                self._prev_game_states[game_id] = current
                continue
            if current.score_raw != prev.score_raw:
                self._handle_score_change(prev, current)
            self._prev_game_states[game_id] = current
```

### Pattern 3: Event Classification (Lead Change vs Routine Score)

**What:** Classify a score change as minor (no lead change) or major (lead change, period transition, overtime).

**When to use:** Applied to every score_change event before routing to fast/slow path.

**Example:**
```python
def _classify_score_change(
    self,
    prev: SportGameState,
    current: SportGameState,
) -> str:
    """Return 'major' or 'minor' for the score change."""
    prev_home, prev_away = prev.home_score or 0, prev.away_score or 0
    curr_home, curr_away = current.home_score or 0, current.away_score or 0

    # Lead change: team that was trailing is now leading (or tied flipping lead)
    prev_leading = "home" if prev_home > prev_away else ("away" if prev_away > prev_home else "tied")
    curr_leading = "home" if curr_home > curr_away else ("away" if curr_away > curr_home else "tied")
    if prev_leading != curr_leading:
        return "major"

    # Period transitions already trigger slow-path via the message queue
    # Overtime: detect via period string containing "OT" or "OT1", "OT2" etc.
    if current.period != prev.period:
        period_upper = (current.period or "").upper()
        if "OT" in period_upper or "OVERTIME" in period_upper or "ET" in period_upper:
            return "major"

    return "minor"
```

### Pattern 4: Fast-Path Execution

**What:** Read cached probability, fetch current Polymarket price, compute divergence, trade if divergence exceeds `SPORTS_INGAME_MIN_CONFIDENCE_GAP`.

**When to use:** After classifying event as minor.

**Example:**
```python
def _fast_path(
    self,
    game_id: int,
    current: SportGameState,
    market_tag: SportsMarketTag,
) -> None:
    cache_entry = self._cache.get(game_id)
    if cache_entry is None:
        print(f"[ingame_trader] event=fast_path_skip game_id={game_id} reason=no_cache")
        return

    # Fetch live Polymarket price
    try:
        live_price = self._polymarket.get_orderbook_price(market_tag.token_id_yes)
    except Exception as exc:
        print(f"[ingame_trader] event=price_fetch_error game_id={game_id} error={exc}")
        return

    llm_prob = cache_entry.get("llm_home_win_prob", 0.0)
    divergence = abs(llm_prob - live_price)

    if divergence < self._ingame_min_confidence_gap:
        print(
            f"[ingame_trader] event=fast_path_skip game_id={game_id} "
            f"divergence={divergence:.4f} threshold={self._ingame_min_confidence_gap:.4f}"
        )
        return

    # Route to trade execution (same as SportsTrader live execution pattern)
    outcome = "Yes" if llm_prob > live_price else "No"
    token_id = market_tag.token_id_yes if outcome == "Yes" else market_tag.token_id_no
    self._execute_ingame_trade(game_id, token_id, outcome, current)
```

### Pattern 5: Order Log and Cancellation on Game End

**What:** Record every placed order in `_order_log`. On `ended: true`, cancel orders within the blackout window.

**When to use:** `handle_game_ended()` called when `current.ended` is detected.

**Example:**
```python
def _log_order(self, game_id: int, order_id: str, market_id: str) -> None:
    if game_id not in self._order_log:
        self._order_log[game_id] = []
    self._order_log[game_id].append({
        "order_id": order_id,
        "timestamp": time.time(),
        "market_id": market_id,
    })

def _cancel_blackout_orders(self, game_id: int) -> None:
    """Cancel orders placed within SPORTS_BLACKOUT_MINUTES of game end."""
    blackout_secs = _env_int("SPORTS_BLACKOUT_MINUTES", 2) * 60
    cutoff = time.time() - blackout_secs
    orders = self._order_log.get(game_id, [])
    to_cancel = [o for o in orders if o["timestamp"] >= cutoff]

    for order in to_cancel:
        try:
            self._polymarket.client.cancel(order["order_id"])
            print(
                f"[ingame_trader] event=order_cancelled game_id={game_id} "
                f"order_id={order['order_id']}"
            )
        except Exception as exc:
            print(
                f"[ingame_trader] event=cancel_error game_id={game_id} "
                f"order_id={order['order_id']} error={exc}"
            )
```

### Pattern 6: Wiring into sports.py Event Loop

**What:** InGameTrader is instantiated alongside SportsTrader in sports.py `main()`. Each loop iteration calls `ingame_trader.tick(current_states, slug_table)`.

**When to use:** Added to the existing `while True:` loop body in sports.py.

**Example:**
```python
# In sports.py main():
ingame_trader = InGameTrader(
    budget_coordinator=budget_coordinator,
    cache=pregame_cache,
    executor=executor,
    dry_run=dry_run,
    polymarket=polymarket,
)

# Inside the while True loop (after current slug_table usage):
game_states_snapshot = connector.get_all_game_states()
ingame_trader.tick(game_states_snapshot, slug_table)

# Also drain period_transition events from queue for major-event slow-path:
try:
    msg = msg_queue.get_nowait()
    if msg.get("type") == "period_transition":
        ingame_trader.handle_period_transition(msg, slug_table)
except Exception:
    pass  # queue empty -- normal
```

### Pattern 7: Exposure Tracking

**What:** Track total USD committed per game across pre-game + in-game trades. InGameTrader accepts a per-game exposure accumulator and checks `SPORTS_MAX_GAME_EXPOSURE_USD` before each trade.

**Note:** Pre-game trades go through SportsTrader. For InGameTrader to know pre-game spend, it must receive the initial trade amount from sports.py OR SportsTrader must expose a method for this. The simplest approach: InGameTrader tracks only in-game spend; `SPORTS_MAX_GAME_EXPOSURE_USD` applies as a soft cap on in-game additions only (since pre-game spend is already tracked by BudgetCoordinator).

**Example:**
```python
def _check_exposure(self, game_id: int, amount: float) -> bool:
    """Return True if trade is within exposure cap."""
    max_exposure = _env_float("SPORTS_MAX_GAME_EXPOSURE_USD", 50.0)
    current = self._game_exposure.get(game_id, 0.0)
    return (current + amount) <= max_exposure

def _record_exposure(self, game_id: int, amount: float) -> None:
    self._game_exposure[game_id] = self._game_exposure.get(game_id, 0.0) + amount
```

### Anti-Patterns to Avoid

- **Modifying SportsTrader for in-game logic:** SportsTrader is pre-game only. Keep them separate — same reason `SportsExecutor` was separated from `Executor`.
- **Acquiring `_state_lock` in InGameTrader:** Use `connector.get_all_game_states()` (snapshot copy, lock released before return) — never access `_game_states` directly.
- **Global per-process LLM concurrency limit:** The project chose per-game cooldowns, not a global semaphore. Stick to per-game — it's simpler and the math works (30s cooldown * 10 concurrent games = ~20 LLM calls/min, well within limits).
- **Calling `cancel_all()` on game end:** Use the order log to cancel ONLY orders within the blackout window. `cancel_all()` would cancel all open orders across all markets, which would disrupt other pipeline operations.
- **Enqueuing score changes in SportsWSConnector without gating:** If SportsWSConnector emits a `score_change` queue event for every score update, rapid score changes would still flood the queue even with InGameTrader's cooldown. The snapshot-diff approach in InGameTrader is self-contained and naturally rate-limited by the 1s loop sleep.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Thread-safe game state reads | Custom lock management | `connector.get_all_game_states()` | Returns snapshot dict with lock already released — thread-safe by design |
| LLM analysis on major events | Custom prompt/parse pipeline | `SportsExecutor.analyze_game()` | Two-stage pipeline already handles JSON parsing, error recovery, model config |
| File-persisted probability cache | Custom JSON cache | `PregameCache.get(game_id)` | TTL, filelock, str-coercion all handled; Phase 3 guarantees cache always written |
| CLOB order cancellation | HTTP DELETE calls | `self.polymarket.client.cancel(order_id)` | `py_clob_client.ClobClient.cancel()` handles Level 2 auth, signing, and request formatting |
| Live Polymarket price | Custom price endpoint | `self.polymarket.get_orderbook_price(token_id)` | Already implemented, returns `float(client.get_price(token_id))` |
| Budget gating | Per-trader budget tracking | `BudgetCoordinator.can_spend_sports()` / `record_sports_trade()` | Cross-process race condition safe; already in use by SportsTrader |

**Key insight:** All in-game logic builds on Phase 1-3 infrastructure. The work is wiring and policy (classification, cooldown, exposure), not new I/O or parsing infrastructure.

## Common Pitfalls

### Pitfall 1: Score-Change Events Never Reach the Message Queue
**What goes wrong:** `connector.get_message_queue()` only receives `period_transition` events. Score changes that do NOT trigger a period change are logged but never enqueued. InGameTrader that consumes only the queue will miss all routine score changes.
**Why it happens:** `_emit_period_transition` is the only function that calls `_message_queue.put_nowait()`. Score changes are detected in `_process_game_state` but only logged (`score_change` log line).
**How to avoid:** Use snapshot-diff on `get_all_game_states()` for score-change detection. Period transitions from the existing queue remain the trigger for major-event slow-path (since they're already in the queue).
**Warning signs:** InGameTrader only fires on period boundaries, never on mid-period scoring.

### Pitfall 2: The 5-Second Latency Requirement vs. 30-Second Cooldown
**What goes wrong:** Confusing detection latency (TRD-03: 5s) with action deferral (cooldown). The cooldown defers the trade, but the system must DETECT the score change within 5s.
**Why it happens:** The 1-second sleep in the main loop means detection latency is already ~1s maximum. But if InGameTrader is doing blocking LLM calls inline (not in a daemon thread), the loop stalls.
**How to avoid:** Slow-path LLM calls MUST spawn a daemon thread (same pattern as SportsTrader's `run_pregame_analysis` threading). Fast-path CLOB operations are fast enough (~200ms) to do inline. Log the detection time separately from the trade execution time.
**Warning signs:** `event=score_detected` log timestamp more than 5s behind the score_change event timestamp.

### Pitfall 3: Order Log Lost on Restart — Blackout Window Gap
**What goes wrong:** If the pipeline crashes and restarts during a live game that ends, the order log is empty. The blackout cancellation logic has no orders to cancel, but orders placed before the restart may still be open.
**Why it happens:** Order log is in-memory (`dict`). No persistence mechanism.
**How to avoid:** This is acceptable by design (CONTEXT.md: "sufficient for single session"). Document the limitation. Mitigate by ensuring `SPORTS_BLACKOUT_MINUTES` is generous enough that most at-risk orders would be filled or expired before restart.
**Warning signs:** Running the pipeline with short-lived restarts in the final minutes of a game.

### Pitfall 4: `cancel()` Called on Already-Filled FOK Orders
**What goes wrong:** `execute_market_order_for_token` uses `OrderType.FOK` (Fill-or-Kill). A FOK order is either immediately filled or immediately cancelled by the exchange. Calling `cancel()` on a filled or already-cancelled order returns an error.
**Why it happens:** The blackout logic cancels orders from the log without checking if they're already filled.
**How to avoid:** Wrap cancel calls in `try/except` and log — do NOT crash on cancel errors. The CLOB API will return an error if the order is already terminal; treat this as a no-op.
**Warning signs:** Cancel error messages for all orders — indicates they were all filled, which is actually fine.

### Pitfall 5: Per-Game Exposure Double-Counts Pre-Game Trades
**What goes wrong:** If InGameTrader tracks cumulative exposure but doesn't know what SportsTrader spent pre-game, the `SPORTS_MAX_GAME_EXPOSURE_USD` cap only applies to in-game spending, not total per-game exposure.
**Why it happens:** SportsTrader and InGameTrader are separate classes with separate state.
**How to avoid:** Treat `SPORTS_MAX_GAME_EXPOSURE_USD` as an in-game-only cap (pre-game spend is separately bounded by `BudgetCoordinator.get_sport_cap()`). Document this distinction clearly. Alternatively, have sports.py pass pre-game spend into InGameTrader on init.
**Warning signs:** Per-game exposure unexpectedly high if both limits are loose.

### Pitfall 6: Race Between Slow-Path Thread and Cooldown Timer
**What goes wrong:** A slow-path LLM call is still running when the cooldown expires and a new event arrives. A second LLM call fires for the same game, creating concurrent LLM calls.
**Why it happens:** Daemon thread approach doesn't track when the previous thread completes; cooldown is timestamp-based, not thread-completion-based.
**How to avoid:** Add the game_id to an `_in_flight` set at the START of the slow-path thread and remove it when the thread completes. Gate on BOTH cooldown and not-in-flight before dispatching. This mirrors SportsTrader's exact guard pattern.
**Warning signs:** `executor.analyze_game` called twice concurrently for the same game_id in logs.

## Code Examples

### CLOB Cancel API (py_clob_client)

The `cancel()` method on `ClobClient` requires Level 2 Auth (already configured when `initialize_clob_client=True`):

```python
# Source: py_clob_client/client.py line 431 (verified via inspection)
# Single order cancel
response = self.polymarket.client.cancel(order_id)
# order_id is the string order ID returned by post_order()

# Batch cancel
response = self.polymarket.client.cancel_orders([order_id_1, order_id_2])
```

### Live Price Fetch (existing Polymarket wrapper)

```python
# Source: agents/polymarket/polymarket.py line 543 (verified via code read)
live_yes_price = self.polymarket.get_orderbook_price(market_tag.token_id_yes)
# Returns float — mid-market price from CLOB order book
```

### Market Order Execution (existing pattern — same for in-game)

```python
# Source: agents/application/sports_trader.py line 231 (verified via code read)
self.polymarket.execute_market_order_for_token(
    token_id=token_id,
    amount=trade_amount,
)
# Returns order_id string on success, raises Exception on failure
# Uses OrderType.FOK — fill or kill, no partial fills
```

### Daemon Thread for Slow-Path (mirrors SportsTrader pattern)

```python
# Source: agents/sports.py line 183 (verified via code read) — exact pattern to replicate
threading.Thread(
    target=self._run_slow_path,
    args=(game_id, current_state, market_tag),
    daemon=True,
    name=f"ingame-slow-{game_id}",
).start()
```

### In-Flight + Cooldown Combined Guard

```python
def _should_process(self, game_id: int) -> bool:
    """Return True when game is eligible for in-game processing."""
    # Guard 1: not already being processed by a slow-path thread
    if game_id in self._slow_path_in_flight:
        return False
    # Guard 2: not in cooldown window
    if self._is_in_cooldown(game_id):
        return False
    return True
```

### Proactive Blackout — "Near Resolution" Heuristic

This is Claude's Discretion territory. A reasonable starting heuristic per sport:

```python
# Source: Claude's design (LOW confidence on exact thresholds — make configurable)
def _is_near_resolution(self, state: SportGameState) -> bool:
    """Return True if game is likely to end within the blackout window."""
    period = (state.period or "").upper()
    elapsed = (state.elapsed or "").strip()

    # NFL/CFB: 4th quarter with < 2 min elapsed
    if state.league in ("nfl", "cfb") and "Q4" in period:
        # elapsed is typically "MM:SS" in NFL; check for last 2 min of period
        # period is 15 min; last 2 min = > 13:00 elapsed
        if elapsed and ":" in elapsed:
            try:
                mins, secs = elapsed.split(":")[:2]
                total_secs = int(mins) * 60 + int(secs)
                return total_secs >= 13 * 60  # last 2 minutes
            except (ValueError, IndexError):
                pass

    # NBA: 4th quarter (Q4) near end
    if state.league == "nba" and "Q4" in period:
        if elapsed and ":" in elapsed:
            try:
                mins, _ = elapsed.split(":")[:2]
                # NBA quarter is 12 min; near end = < 2 min remaining = > 10 min elapsed
                return int(mins) >= 10
            except (ValueError, IndexError):
                pass

    # OT periods: always treat as near resolution (short periods)
    if "OT" in period or "OVERTIME" in period:
        return True

    return False
```

**Note:** The `elapsed` field format is sport-specific and unverified against live WS data. Expose thresholds as env vars (`SPORTS_BLACKOUT_FINAL_PERIOD_ELAPSED_NFL_SECS`, etc.) from day one — do NOT hardcode.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Global in_flight set (SportsTrader) | Per-game cooldown dict with timestamps | Phase 4 | Enables time-based debouncing instead of binary in-flight |
| LLM for every market event | Fast-path (cache) / slow-path (LLM) split | Designed in Phase 3 | Reduces LLM calls by ~80% during normal in-game activity |
| No order cancellation | Blackout window cancel on game end | Phase 4 | Prevents stale fills at resolution |

**Key architecture:** The snapshot-diff approach for score detection avoids requiring any changes to `SportsWSConnector`, which keeps the connector's responsibility narrow (WS events only). The trading engine owns the diff logic.

## Open Questions

1. **Score-change queue events vs. snapshot diff**
   - What we know: message queue currently only emits `period_transition`. Score changes require InGameTrader to do snapshot diff OR SportsWSConnector to be modified to also enqueue `score_change` events.
   - What's unclear: Modifying SportsWSConnector to emit score_change events (enqueuing every score update) would create high-volume queue events that need their own debounce — same problem moved upstream. The snapshot-diff in InGameTrader is cleaner.
   - Recommendation: Use snapshot-diff in InGameTrader. Do NOT modify SportsWSConnector — keep its queue for period transitions only.

2. **Position reversal: what does "sell existing position" mean for CLOB binary markets?**
   - What we know: `execute_market_order_for_token` places market orders. In binary prediction markets, "selling" a Yes position means buying No tokens (or actually selling Yes via CLOB).
   - What's unclear: Whether `py_clob_client` supports SELL-side market orders or only BUY. The existing code always maps to BUY (see `polymarket.py` comment: "SELL signals are mapped to opposite BUY for binary markets").
   - Recommendation: For position reversal, treat as: buy the opposite token (buy No to counteract a Yes position). Do NOT attempt SELL-side market orders — use the established mapping.

3. **`SPORTS_MAX_GAME_EXPOSURE_USD` — does it include pre-game spend?**
   - What we know: SportsTrader and InGameTrader are separate; no shared exposure tracking.
   - What's unclear: Whether the CONTEXT.md intent was total-per-game or in-game-only.
   - Recommendation: Apply `SPORTS_MAX_GAME_EXPOSURE_USD` to in-game spend only. Pre-game is gated by `BudgetCoordinator.get_sport_cap()`. Document this clearly in `.env.example`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via pyproject.toml `[tool.pytest.ini_options]`) |
| Config file | `pyproject.toml` — `testpaths = ["tests"]`, `asyncio_mode = "auto"` |
| Quick run command | `python -m pytest tests/test_ingame_trader.py -x -q` |
| Full suite command | `python -m pytest tests/test_sports_trader.py tests/test_sports_ws.py tests/test_sports_pipeline.py tests/test_ingame_trader.py -q` |

All 171 sports-related tests pass in 0.79s (excluding known-broken unrelated files). New tests follow the same `_make_mocks()` / `_make_trader()` helper pattern from `test_sports_trader.py`.

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRD-02 | InGameTrader detects score change and routes to fast/slow path | unit | `pytest tests/test_ingame_trader.py::TestEventClassification -x` | Wave 0 |
| TRD-02 | Fast-path reads cache, fetches live price, skips on low divergence | unit | `pytest tests/test_ingame_trader.py::TestFastPath -x` | Wave 0 |
| TRD-02 | Slow-path triggers SportsExecutor.analyze_game() in daemon thread | unit | `pytest tests/test_ingame_trader.py::TestSlowPath -x` | Wave 0 |
| TRD-02 | On ended=True, no new orders placed and blackout cancels fire | unit | `pytest tests/test_ingame_trader.py::TestGameEndedSafeguards -x` | Wave 0 |
| TRD-02 | Exposure cap prevents trades exceeding SPORTS_MAX_GAME_EXPOSURE_USD | unit | `pytest tests/test_ingame_trader.py::TestExposureCap -x` | Wave 0 |
| TRD-03 | Score change is detected within loop cycle (no blocking in tick()) | unit | `pytest tests/test_ingame_trader.py::TestDetectionLatency -x` | Wave 0 |
| TRD-05 | Per-game cooldown ignores events within cooldown window | unit | `pytest tests/test_ingame_trader.py::TestCooldown -x` | Wave 0 |
| TRD-05 | In-flight guard prevents duplicate concurrent slow-path calls | unit | `pytest tests/test_ingame_trader.py::TestInFlightGuard -x` | Wave 0 |
| TRD-05 | Cooldown applies to BOTH fast and slow path events | unit | `pytest tests/test_ingame_trader.py::TestCooldown::test_fast_path_also_sets_cooldown -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_ingame_trader.py -x -q`
- **Per wave merge:** `python -m pytest tests/test_sports_trader.py tests/test_sports_ws.py tests/test_sports_pipeline.py tests/test_ingame_trader.py -q`
- **Phase gate:** Full sports suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_ingame_trader.py` — covers TRD-02, TRD-03, TRD-05 (all phase requirements)
- [ ] No new framework/fixture infrastructure needed — `conftest.py` is sufficient (only provides `event_loop` fixture for asyncio)

## Sources

### Primary (HIGH confidence)
- **Code inspection: `agents/connectors/sports_ws.py`** — Verified: `get_message_queue()` returns `queue.Queue`, only `period_transition` events are enqueued, score changes are logged only.
- **Code inspection: `agents/application/sports_trader.py`** — Verified: `_in_flight` set pattern, `should_analyze()`, `run_pregame_analysis()` threading model.
- **Code inspection: `agents/application/pregame_cache.py`** — Verified: `get(game_id)` is lock-safe for concurrent reads, returns dict or None.
- **Code inspection: `agents/polymarket/polymarket.py`** — Verified: `get_orderbook_price(token_id)` exists, `execute_market_order_for_token()` returns order_id string. No cancel wrapper — must access `self.polymarket.client.cancel()` directly.
- **Code inspection: `venv/lib/.../py_clob_client/client.py`** — Verified: `cancel(order_id)` at line 431, `cancel_orders(order_ids)` at line 443, both require Level 2 Auth.
- **Code inspection: `agents/sports.py`** — Verified: main event loop structure, 1s sleep, queue drain pattern, SportsTrader instantiation pattern.
- **Test suite inspection: `tests/test_sports_trader.py`** — 32 tests passing, all mocking patterns reusable.

### Secondary (MEDIUM confidence)
- **py_clob_client order type behavior** — `OrderType.FOK` (Fill-or-Kill) implied by `execute_market_order_for_token` source. FOK means cancel errors on already-terminal orders are expected and must be caught.

### Tertiary (LOW confidence)
- **`elapsed` field format per sport** — Only NFL/CFB period format documented. NBA, MLB, NHL, soccer `elapsed` formats are unknown from static analysis. Heuristics in `_is_near_resolution()` must be validated against live WS data.
- **Proactive blackout thresholds** — The specific elapsed-time values (13:00 NFL, 10:00 NBA) are reasonable estimates, not validated. Must be exposed as env vars.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already present; no new dependencies. All APIs verified via direct code inspection.
- Architecture: HIGH — patterns directly mirror SportsTrader and sports.py established code. No speculative design.
- Pitfalls: HIGH for items 1-4 (found via direct code analysis). MEDIUM for items 5-6 (design-level reasoning, not yet encountered in code).
- Validation architecture: HIGH — test framework verified running (171 tests pass). Gap file path is prescriptive.

**Research date:** 2026-03-06
**Valid until:** 2026-04-05 (30 days — stable dependencies, no fast-moving ecosystem)
