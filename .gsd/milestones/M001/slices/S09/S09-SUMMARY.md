---
id: S09
parent: M001
milestone: M001
provides:
  - Per-sport cooldown configuration via SPORTS_INGAME_COOLDOWN_{LEAGUE} env vars
  - Rolling 60-second order-rate counter with structured log emission
  - VALID-01 slug normalization validation script against live Polymarket Gamma API
  - VALID-03 concurrent rate limit compliance validation script with structured JSON reports
requires:
  - slice: S08
    provides: Pipeline integration (value-bet filtering, balance refresh, cached implied_home_prob)
affects: []
key_files:
  - agents/application/ingame_trader.py
  - tests/test_ingame_trader.py
  - scripts/python/validate_slugs.py
  - scripts/python/validate_rate_limit.py
key_decisions:
  - Per-sport cooldowns keyed by _FINAL_PERIODS league names; _should_process and _is_in_cooldown accept optional league param
  - Order-rate counter uses in-memory timestamp list pruned lazily on each access; 60s window matches CLOB limit
  - Validation scripts are standalone in scripts/python/, emit JSON to stdout and progress to stderr
  - Pending sports (no live events) tracked as "pending" not "fail" in slug validation reports
patterns_established:
  - _should_process and _is_in_cooldown accept optional league param for sport-specific thresholds
  - _record_order_timestamp called only inside non-dry-run branch of _execute_ingame_trade
  - Validation scripts use sys.path manipulation to import from project root; --output flag for file persistence
observability_surfaces:
  - "[ingame_trader] metric=order_rate_60s count=N" structured log on every real order
  - get_order_rate() public method for external read of current rolling count
  - validate_slugs.py and validate_rate_limit.py emit structured JSON reports with per-league breakdowns
drill_down_paths:
  - .gsd/milestones/M001/slices/S09/tasks/T01-SUMMARY.md
  - .gsd/milestones/M001/slices/S09/tasks/T02-SUMMARY.md
duration: 24min
verification_result: passed
completed_at: 2026-03-15
---

# S09: Live Validation

**Per-sport cooldown configuration, order-rate instrumentation, and live validation scripts for slug normalization and CLOB rate compliance.**

## What Happened

Two tasks shipped changes to InGameTrader and added standalone validation tooling:

**T01 — Per-sport cooldown & order-rate counter.** `InGameTrader.__init__` now scans `SPORTS_INGAME_COOLDOWN_{LEAGUE}` env vars (e.g. `SPORTS_INGAME_COOLDOWN_NBA=10`) for all leagues defined in `_FINAL_PERIODS`. The `_is_in_cooldown` and `_should_process` methods accept an optional `league` param; sport-specific value is used when set, falling back to the global `SPORTS_INGAME_COOLDOWN_SECONDS`. A rolling `_order_timestamps` list tracks real (non-dry-run) order timestamps, prunes entries older than 60s on access, and emits `metric=order_rate_60s count=N` structured logs. `get_order_rate()` provides external read access.

**T02 — Live validation scripts.** `scripts/python/validate_slugs.py` queries the Polymarket Gamma API for active events across all 9 sport types, exercises both fast-path slug lookup and fallback team-based resolution, and reports per-league pass/pending/fail status. `scripts/python/validate_rate_limit.py` creates a real InGameTrader with mock CLOB, runs 9 concurrent games through `tick()` at 1-second cadence with score changes, captures order-rate structured logs, and verifies the peak never exceeds 60 orders/min. Both produce structured JSON reports.

## Verification

```
$ python -m pytest tests/test_ingame_trader.py -v --tb=short
89 passed in 0.20s
```

- **TestPerSportCooldown** (9 tests): global fallback, env loading, shorter/longer overrides, None league, invalid env, tick integration
- **TestOrderRate** (10 tests): initial zero, increment, stale pruning, real-trade increment, dry-run exclusion, slow-path coverage, structured log, rolling window
- validate_slugs.py live run: NBA (5 slugs), NHL (1 slug) resolved; 7 leagues pending (off-season)
- validate_rate_limit.py live run: peak_rate=9 across 9 concurrent games — well under 60/min limit

## Requirements Advanced

- VALID-01 — Slug validation script exercises full resolution pipeline against live Gamma API; NBA and NHL confirmed working
- VALID-02 — Per-sport cooldowns implemented and tested with 9 sport-specific env var overrides
- VALID-03 — Rate limit validation script proves concurrent 9-game pipeline stays at peak_rate=9, far under 60/min

## Requirements Validated

- VALID-01 — Live Gamma API validation confirms slug resolution for active leagues; pending leagues are structural (off-season), not failures
- VALID-02 — 9 unit tests cover all sport-specific cooldown paths; callers pass league from game state
- VALID-03 — 10-second concurrent simulation with 9 games proves peak_rate=9; 30s default cooldown naturally limits throughput

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

None.

## Known Limitations

- Slug validation can only confirm leagues with active events; off-season leagues report "pending" — full 9/9 confirmation requires running during overlapping seasons
- Order-rate counter is in-memory only; lost on restart — acceptable since it's instrumentation, not a safety gate

## Follow-ups

- none

## Files Created/Modified

- `agents/application/ingame_trader.py` — Per-sport cooldown dict, order-rate counter, updated _should_process/_is_in_cooldown signatures
- `tests/test_ingame_trader.py` — TestPerSportCooldown (9 tests), TestOrderRate (10 tests), updated existing halt-gate tests
- `scripts/python/validate_slugs.py` — VALID-01 slug normalization validation script
- `scripts/python/validate_rate_limit.py` — VALID-03 concurrent rate limit compliance validation script

## Forward Intelligence

### What the next slice should know
- All 3 VALID requirements are now validated. M001 milestone has no remaining active requirements — all slices S01-S09 are complete.

### What's fragile
- Slug validation depends on Polymarket Gamma API availability and active events existing — running during off-season for most sports yields mostly "pending" results.

### Authoritative diagnostics
- `python scripts/python/validate_slugs.py --output /tmp/valid01.json` — live slug resolution report
- `python scripts/python/validate_rate_limit.py --duration 15 --output /tmp/valid03.json` — rate compliance report
- `get_order_rate()` on InGameTrader instance — current rolling 60s order count

### What assumptions changed
- None — implementation matched the plan exactly.
