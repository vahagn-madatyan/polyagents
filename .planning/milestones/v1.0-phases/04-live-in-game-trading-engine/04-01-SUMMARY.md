---
phase: 04-live-in-game-trading-engine
plan: 01
subsystem: trading
tags: [sports, in-game, trading, threading, polymarket, llm, cache]

# Dependency graph
requires:
  - phase: 03-pre-game-analysis-and-llm-integration
    provides: PregameCache with llm_home_win_prob, SportsExecutor.analyze_game(), SportsTrader pattern
  - phase: 01-websocket-foundation
    provides: SportGameState model, SportsWSConnector interface
  - phase: 02-market-discovery-and-pipeline-architecture
    provides: SportsMarketTag, BudgetCoordinator, Polymarket CLOB interface
provides:
  - InGameTrader class with tick(), fast-path, slow-path, cooldown, game-ended, exposure tracking
  - Score-change detection via snapshot diff on get_all_game_states()
  - Event classification: major (lead change, tied, OT) vs minor
  - Fast-path: cache probability vs live Polymarket price divergence trading
  - Slow-path: LLM re-analysis via SportsExecutor in daemon thread for major events
  - Per-game cooldown debounce (SPORTS_INGAME_COOLDOWN_SECONDS)
  - In-flight guard preventing duplicate concurrent LLM calls per game
  - Game-ended safeguards: _ended_games set, blackout order cancellation
  - Proactive near-resolution blackout heuristics per sport
  - Per-game exposure cap (SPORTS_MAX_GAME_EXPOSURE_USD)
  - 49 unit tests covering all trading logic behaviors
affects: [04-02-wiring, any future sports trading integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - InGameTrader follows same dependency injection and dry_run patterns as SportsTrader
    - Inline env helpers (_env_float, _env_int, _env_bool) at module level, same as sports_trader.py
    - TYPE_CHECKING imports for all heavy deps (no circular imports, no langchain at import time)
    - Daemon threads for slow-path: threading.Thread(daemon=True, name=f"ingame-slow-{game_id}")
    - In-flight set pattern mirrors SportsTrader._in_flight for concurrency safety

key-files:
  created:
    - agents/application/ingame_trader.py
    - tests/test_ingame_trader.py
  modified: []

key-decisions:
  - "Fast-path uses fixed INGAME_SIZE_FRACTION (0.05) of max_game_exposure_usd as trade amount — no LLM size recommendation needed for speed"
  - "Slow-path sets cooldown timestamp at thread START (not completion) — prevents overlapping analysis triggers during long LLM calls"
  - "Tied-to-leading classified as major event per spec — tests adjusted to use home-already-leading scenarios for minor-path testing"
  - "Fast-path skips cooldown but still calls _mark_processed at every exit point — ensures no double-processing even on skipped trades"
  - "_is_near_resolution() is sport-specific and conservative — logs warnings for uncertain heuristics (e.g. deep OT)"

patterns-established:
  - "Snapshot diff pattern: _prev_game_states dict compared each tick, first-sight is baseline only"
  - "Leader comparison function: home > away = 'home', away > home = 'away', else 'tied' for lead-change detection"
  - "Event routing: classify_score_change() returns 'major'/'minor', routes to _spawn_slow_path or _fast_path"

requirements-completed: [TRD-02, TRD-03, TRD-05]

# Metrics
duration: 7min
completed: 2026-03-07
---

# Phase 4 Plan 01: InGameTrader Summary

**InGameTrader with score-change snapshot diff, fast-path divergence trading and slow-path LLM daemon threads, per-game cooldown and exposure cap**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-07T07:33:25Z
- **Completed:** 2026-03-07T07:40:30Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments

- InGameTrader class (751 lines) with all 15 methods specified in the plan
- 49 unit tests (886 lines) covering all 9 test classes from the plan spec
- Fast-path reads PregameCache.get() and polymarket.get_orderbook_price() — no LLM calls inline
- Slow-path calls SportsExecutor.analyze_game() in daemon thread — no blocking tick loop
- Cooldown applies to both fast and slow path; in-flight guard prevents duplicate LLM calls
- Game-ended sets _ended_games and cancels orders within blackout window via polymarket.client.cancel()
- No regressions — existing 95 sports test suite continues to pass (144 total)

## Task Commits

Each task was committed atomically (TDD: separate RED and GREEN commits):

1. **Task 1 RED: Failing tests** - `284d7eb` (test)
2. **Task 1 GREEN: Implementation** - `42a282c` (feat)

## Files Created/Modified

- `agents/application/ingame_trader.py` - InGameTrader class: tick(), fast-path, slow-path, cooldown, exposure tracking, game-ended safeguards (751 lines)
- `tests/test_ingame_trader.py` - 49 unit tests: all 9 TestCase classes from plan spec (886 lines)

## Decisions Made

- Fast-path uses fixed `_INGAME_SIZE_FRACTION` (0.05) of `max_game_exposure_usd` as trade amount — avoids LLM size recommendation overhead for speed-critical path
- Slow-path sets cooldown timestamp at thread START (not completion) — prevents overlapping analysis triggers during long LLM calls, matching plan spec
- Tied-to-leading (0-0 to 3-0) is correctly classified as "major" per spec; tests adjusted to use pre-existing leading scenarios for minor-path coverage
- Fast-path calls `_mark_processed()` at every exit point (including skips) — prevents double-processing for any exit reason
- `_is_near_resolution()` is sport-specific and conservative; logs warnings when heuristic is uncertain (deep OT periods)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test scenarios for minor-event testing**
- **Found during:** Task 1 GREEN (implementation)
- **Issue:** Three tests used 0-0 to scoring scenarios (tied-to-leading = "major" per classifier), asserting fast-path (cache.get) was called — but major events go to slow-path
- **Fix:** Changed test baselines to use home-already-leading scenarios (e.g. 5-3 → 8-3) which correctly produce minor events and take fast-path
- **Files modified:** tests/test_ingame_trader.py (test_score_change_detected, test_event_after_cooldown_expires_processed, test_cooldown_is_per_game)
- **Verification:** All 49 tests pass after fix

---

**Total deviations:** 1 auto-fixed (Rule 1 - test scenario bug)
**Impact on plan:** Minor test correction to match spec behavior. Classifier behavior is correct per spec. No scope changes.

## Issues Encountered

None — implementation matched plan spec exactly. Test scenarios required adjustment because tied-to-leading IS correctly classified as major, which the test comments had incorrectly described as minor.

## User Setup Required

None - no external service configuration required. New env vars are optional overrides with documented defaults:
- `SPORTS_INGAME_COOLDOWN_SECONDS` (default: 30)
- `SPORTS_INGAME_MIN_CONFIDENCE_GAP` (default: 0.15)
- `SPORTS_BLACKOUT_MINUTES` (default: 2)
- `SPORTS_MAX_GAME_EXPOSURE_USD` (default: 50.0)

## Next Phase Readiness

- InGameTrader is complete and ready for Plan 02 wiring into the main sports pipeline loop
- All public methods are ready: `tick()`, `handle_period_transition()`, `handle_game_ended()`
- Dependency injection pattern matches existing pipeline — plug-in compatible with `sports.py` main loop

---
*Phase: 04-live-in-game-trading-engine*
*Completed: 2026-03-07*
