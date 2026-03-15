# Phase 6: Safety & Resilience Wiring - Context

**Gathered:** 2026-03-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Close the last two v1 requirement gaps: (1) WS-07 — configurable trade rules per game edge case (overtime, rain delays, forfeits, suspensions) beyond the existing halt/don't-halt binary, and (2) MKT-02 — verified slug-to-market mapping with retry logic and validation so unmapped games are not silently skipped. These are resilience improvements to existing code, not new features.

</domain>

<decisions>
## Implementation Decisions

### Overtime handling
- Continue trading during overtime — OT is high-volatility opportunity
- Keep both fast-path and slow-path active during overtime periods
- Only halt on actual game-end signals, not on overtime start

### Rain delays and suspensions
- Pause trading during delays, auto-resume when game returns to InProgress
- No manual restart required — when `should_halt_trading()` returns false again, normal fast/slow-path trading resumes automatically
- Extend existing `should_halt_trading()` pattern with pause-resume semantics rather than permanent halt

### Forfeits and cancellations
- Actively cancel open orders for that game via CLOB API, then halt
- Reuse Phase 4's in-memory order log (`{game_id: [{order_id, timestamp, market_id}]}`) to find orders to cancel
- Prevents getting filled at stale prices on a cancelled/forfeited game

### Slug mapping retry and validation
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

</decisions>

<specifics>
## Specific Ideas

- `should_halt_trading()` and `HALT_STATUSES` already exist in sports_ws.py — extend rather than replace
- `build_slug_table()` already returns `(slug_table, unmapped)` tuple — unmapped list is the natural retry queue
- STATE.md concern: "Slug normalization across all 9 sport types needs validation with live Polymarket data" — validation step addresses this
- Phase 4's blackout window order cancellation pattern can be reused for forfeit/cancellation order cleanup

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `should_halt_trading(state)` in sports_ws.py:75 — current halt logic, extend with per-status rules
- `HALT_STATUSES` set in sports_ws.py:62 — categorize statuses into halt/pause/continue groups
- `build_slug_table()` in gamma.py:430 — returns (slug_table, unmapped) tuple, unmapped feeds retry
- `SportsMarketTag` in objects.py:303 — already carries market metadata, check for tokenId fields
- Phase 4 in-memory order log pattern — reuse for forfeit order cancellation

### Established Patterns
- `_env_int()` / `_env_float()` inlined per module for env var config
- `print(f"[tag] event=... key=value")` structured logging
- `should_halt_trading()` called in sports.py event loop — integration point for enhanced edge case logic

### Integration Points
- `agents/connectors/sports_ws.py` — extend should_halt_trading() or add companion functions
- `agents/polymarket/gamma.py` — add retry logic to build_slug_table() or wrapper
- `agents/sports.py` — event loop already calls should_halt_trading() and build_slug_table()
- `agents/application/ingame_trader.py` — may need pause/resume awareness

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-safety-resilience-wiring*
*Context gathered: 2026-03-10*
