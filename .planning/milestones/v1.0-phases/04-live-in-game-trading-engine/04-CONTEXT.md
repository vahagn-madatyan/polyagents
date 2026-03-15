# Phase 4: Live In-Game Trading Engine - Context

**Gathered:** 2026-03-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Autonomous in-game trading engine triggered by live score changes from the websocket. Uses cached pre-game probabilities for fast-path decisions on minor changes, reserves full LLM calls for major state changes (lead changes, period transitions, overtime). Includes debounce/cooldown to prevent LLM flooding, game-ended safeguards with order cancellation, and per-game exposure tracking. No new data sources or LLM prompt changes — uses existing SportsExecutor and PregameCache from Phase 3.

</domain>

<decisions>
## Implementation Decisions

### Fast-path vs Slow-path Decision Routing
- Event type classification determines path: classify each score event as minor (routine scoring, no lead change) or major (lead change, period transition, overtime start, game resumption after delay)
- Minor events → fast-path: read cached pre-game probability from PregameCache, compare against current Polymarket price, trade if divergence exceeds threshold. No LLM call
- Major events → slow-path: run full SportsExecutor.analyze_game() with updated game state. Full LLM two-stage pipeline
- Fast-path uses cached probability as-is — no adjustment based on score change. Treat pre-game probability as the anchor; if Polymarket price has moved but cached prob says value exists, trade
- Lead changes always trigger slow-path — momentum shift warrants full LLM re-evaluation

### Debounce and Cooldown
- Per-game cooldown timer: after processing any score event (fast or slow), ignore new events for that game for N seconds
- Default cooldown: 30 seconds, configurable via `SPORTS_INGAME_COOLDOWN_SECONDS` env var
- Cooldown applies to BOTH fast-path and slow-path events — prevents rapid-fire trades that would hit CLOB rate limits (60 orders/min shared across pipelines)
- Per-game cooldowns only — no global rate limit across all games. With 30s cooldowns, even 10 concurrent games max out at ~20 LLM calls/min
- Extend existing `in_flight` set pattern from SportsTrader with timestamps for cooldown tracking

### Game-Ended Safeguards
- On `ended: true`: halt ALL new order placement for that game immediately
- Cancel orders placed within configurable blackout window before game end (e.g., `SPORTS_BLACKOUT_MINUTES` default 2 minutes) — prevents getting filled at stale prices right at resolution
- Proactive blackout: also prevent NEW order placement when game is in final period AND elapsed time suggests resolution is near — don't place orders that would be immediately cancelled
- In-memory order log: dict of `{game_id: [{order_id, timestamp, market_id}]}` for all orders placed during session. On game end, look up and cancel matching orders within blackout window. Lost on restart but sufficient for single session
- Retain game state for settlement window after end — matches existing `SPORTS_WS_ENDED_GAME_TTL_MINUTES` from Phase 1. Allows post-game logging and debugging

### In-Game Position Management
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

</decisions>

<specifics>
## Specific Ideas

- The websocket message queue (`connector.get_message_queue()`) already streams game state changes — InGameTrader should consume this queue for score event detection
- Phase 3's cache entry is always written before trade gates — InGameTrader can always read the probability even if pre-game trade was skipped
- STATE.md concern: "Score-change debounce thresholds are sport-specific and unknown; expose as env vars from day one, never hardcode" — the 30s cooldown default is a starting point
- STATE.md concern: "CLOB rate limit (60 orders/min) is shared across pipelines" — per-game cooldown + per-game exposure cap provides natural throttling
- The 5-second trade re-evaluation requirement (TRD-03) is a processing latency target, not a cooldown — the system should detect the event within 5s even if cooldown defers action

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SportsWSConnector.get_message_queue()`: already streams game state change events — direct feed for InGameTrader
- `PregameCache.get(game_id)`: returns cached analysis with `llm_home_win_prob`, `confidence_gap`, etc. — fast-path reads this
- `SportsExecutor.analyze_game()`: full two-stage LLM pipeline — slow-path calls this
- `SportsTrader._in_flight` set: pattern for preventing duplicate concurrent processing — extend with timestamps for cooldown
- `should_halt_trading(state)` in `sports_ws.py`: already handles edge-case game statuses (Suspended, Forfeit, etc.)
- `BudgetCoordinator.can_spend_sports()` / `record_sports_trade()`: budget gate ready for in-game trades
- `SportsTrader._build_cache_entry()`: cache entry builder — InGameTrader can update cache after in-game analysis

### Established Patterns
- Daemon threads for game analysis (`threading.Thread(target=..., daemon=True)`) — same pattern for in-game event processing
- `_env_int()` / `_env_float()` / `_env_bool()` inlined in each module to avoid heavy executor.py imports
- `print(f"[tag] key=value")` structured logging — use `[ingame_trader]` tag
- Polymarket lazy import inside `main()` — same pattern for InGameTrader's CLOB order operations

### Integration Points
- `agents/sports.py`: main event loop — wire InGameTrader to consume message queue events
- `agents/application/ingame_trader.py`: new file for InGameTrader class
- `agents/application/sports_trader.py`: may need to expose order tracking for shared order log
- `.env.example`: add `SPORTS_INGAME_COOLDOWN_SECONDS`, `SPORTS_BLACKOUT_MINUTES`, `SPORTS_MAX_GAME_EXPOSURE_USD`, `SPORTS_INGAME_MIN_CONFIDENCE_GAP`

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-live-in-game-trading-engine*
*Context gathered: 2026-03-06*
