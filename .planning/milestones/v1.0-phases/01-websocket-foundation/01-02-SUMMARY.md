---
phase: 01-websocket-foundation
plan: 02
subsystem: websocket
tags: [websocket, reconnect, watchdog, backoff, trading-halt, sports-api]

# Dependency graph
requires:
  - phase: 01-websocket-foundation/01-01
    provides: SportsWSConnector base class with ping handling, state tracking, period transitions

provides:
  - reconnect_delay() module-level function with exponential backoff + 25% jitter
  - HALT_STATUSES set and should_halt_trading() for all 7 edge-case statuses
  - _on_freeze_detected() watchdog that marks all states stale and forces reconnect
  - _purge_ended_games() with _last_purge_at for periodic TTL cleanup
  - run() reconnect loop using reconnect_delay(); stop() for clean shutdown
affects:
  - Phase 2 (sports market discovery) — uses should_halt_trading() for trading decisions
  - Phase 4 (live execution) — uses stale flag and halt signals from connector

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Exponential backoff with 25% jitter for reconnect delays
    - Watchdog-only-on-data pattern (ping/pong never resets watchdog — critical for freeze detection)
    - Stale flag cleared on next real data message
    - Periodic purge gated by _last_purge_at to prevent O(n) on every message

key-files:
  created: []
  modified:
    - agents/connectors/sports_ws.py
    - tests/test_sports_ws.py

key-decisions:
  - "reconnect_delay() exposed as module-level function (not method) to enable isolated unit testing without connector instantiation"
  - "HALT_STATUSES uses both original case and lowercase set for esports/tennis which send lowercase status strings"
  - "_purge_ended_games() called at most once per 60s via _last_purge_at gate in _process_game_state (not in a background thread)"
  - "Pre-existing test failures (langchain_core, newsapi) are out-of-scope missing deps — logged, not fixed"

patterns-established:
  - "Watchdog timer pattern: only data messages reset; ping/pong explicitly excluded — critical for detecting Polymarket server-side freeze bug"
  - "Backoff formula: min(base * 2^attempt, max_delay) + uniform(0, 25% of capped value)"
  - "Stale marking: _on_freeze_detected sets all game state stale under _state_lock; _build_game_state always initializes stale=False"

requirements-completed: [WS-02, WS-03, WS-07]

# Metrics
duration: 4min
completed: 2026-03-05
---

# Phase 01 Plan 02: Reconnect, Watchdog, Halt Signals, and TTL Purge Summary

**Production-reliable SportsWSConnector with exponential backoff reconnect, freeze-detecting watchdog timer, 7-status halt signals for trading, and ended-game TTL purge**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-05T05:57:33Z
- **Completed:** 2026-03-05T06:01:24Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added module-level `reconnect_delay(attempt, base, max_delay)` function with exponential backoff + 25% jitter, capped at 60s base, tested across attempts 0/1/5/10
- Implemented `HALT_STATUSES` set + `should_halt_trading()` with case-insensitive matching covering all 7 edge-case statuses (Suspended, Postponed, Canceled, Forfeit, Delayed, NotNecessary, Awarded) plus stale states
- Added `_purge_ended_games()` with time-gated periodic execution (at most once per 60s) to prevent memory growth from completed games
- All 46 tests pass; 98 total non-langchain tests pass with zero regressions

## Task Commits

Each task was committed atomically:

1. **Tasks 1+2: Reconnect backoff, watchdog, halt statuses, TTL purge** - `8103b64` (feat)

_Note: Tasks 1 and 2 were implemented together in the same two files as a single atomic commit since all code modifications touched the same files._

## Files Created/Modified

- `agents/connectors/sports_ws.py` - Added `reconnect_delay()`, `HALT_STATUSES`, `should_halt_trading()`, `_purge_ended_games()`, `_last_purge_at` tracking; refactored `_schedule_reconnect()` to use module-level function
- `tests/test_sports_ws.py` - Added 26 new test functions covering backoff sequence, watchdog firing, stale marking, ping guard, all 7 halt statuses, case-insensitive matching, TTL purge/retain/active-game-protection

## Decisions Made

- `reconnect_delay()` exposed as module-level function (not a method) to enable isolated unit testing without connector instantiation
- `HALT_STATUSES` uses both original case and a pre-computed lowercase set `_HALT_STATUSES_LOWER` for esports/tennis which send lowercase status strings (e.g. "postponed" not "Postponed")
- `_purge_ended_games()` called via time-gated check in `_process_game_state` (not a background thread) — simpler and avoids additional thread management

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added `_last_purge_at` to `_make_connector()` test factory**
- **Found during:** Task 1/2 integration (GREEN phase, test run)
- **Issue:** `_make_connector()` factory used in tests bypasses `__init__`, so `_last_purge_at` was not set; `_process_game_state` then raised `AttributeError`
- **Fix:** Added `connector._last_purge_at = 0.0` to `_make_connector()` factory in tests
- **Files modified:** `tests/test_sports_ws.py`
- **Verification:** All 46 tests pass after fix
- **Committed in:** `8103b64` (included in main task commit after black reformatting)

---

**Total deviations:** 1 auto-fixed (Rule 3 — blocking)
**Impact on plan:** Necessary for correctness. No scope creep.

## Issues Encountered

- Pre-existing test failures: `test_event_url_trader.py`, `test_news_connector.py`, `test_trade_selection.py` fail on import due to missing `langchain_core` and `newsapi` packages. These are environment issues unrelated to this plan — logged as out-of-scope, not fixed. The 98 non-affected tests all pass.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `SportsWSConnector` is fully production-ready: reconnects with backoff, detects silent freezes, marks stale on freeze, provides halt signals for all edge-case game states, purges ended games
- `should_halt_trading()` ready for Phase 2 market discovery and Phase 4 execution to gate trading decisions
- Phase 2 (slug normalization / Gamma market lookup) can build on the complete connector

## Self-Check: PASSED

All created/modified files verified present. Commit `8103b64` confirmed in git log.

---
*Phase: 01-websocket-foundation*
*Completed: 2026-03-05*
