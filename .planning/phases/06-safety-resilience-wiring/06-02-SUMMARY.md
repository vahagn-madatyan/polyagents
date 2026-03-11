---
phase: 06-safety-resilience-wiring
plan: "02"
subsystem: market-discovery
tags: [slug-retry, tag-validation, exponential-backoff, gamma, tdd]
dependency_graph:
  requires: []
  provides: [retry_unmapped_slugs, _validate_market_tag, build_slug_table_validation]
  affects: [agents/polymarket/gamma.py, agents/sports.py]
tech_stack:
  added: []
  patterns: [exponential-backoff, TDD-red-green]
key_files:
  created: []
  modified:
    - agents/polymarket/gamma.py
    - agents/sports.py
    - tests/test_sports_market_discovery.py
decisions:
  - "Backoff formula: min(1.0 * 2^(attempt-1), 8.0) — caps at 8s to avoid excessive delay at slug refresh intervals"
  - "max_attempts reads SPORTS_SLUG_RETRY_MAX_ATTEMPTS env var (default 3) — no new _env_int helper needed, direct os.getenv() inline"
  - "retry_unmapped_slugs() added BEFORE build_slug_table() in gamma.py to keep method order logical"
  - "Validation in both build_slug_table (first pass) and retry_unmapped_slugs (retry pass) — consistent rejection path"
metrics:
  duration_minutes: 2
  completed_date: "2026-03-11"
  tasks_completed: 1
  files_modified: 3
---

# Phase 06 Plan 02: Slug Retry with Exponential Backoff and Tag Validation Summary

**One-liner:** JWT-free slug retry with exponential backoff (1s→2s→4s→8s cap) and pre-insertion token/condition_id validation closing silent CLOB error path.

## What Was Built

Added two new methods to `GammaMarketClient` and wired retry into `sports.py`:

1. `_validate_market_tag(tag)` — returns True only when `token_id_yes`, `token_id_no`, and `condition_id` are all non-empty strings. Guards against silent CLOB API errors downstream.

2. `retry_unmapped_slugs(unmapped, slug_table, max_attempts=None)` — retries each unmapped slug up to `max_attempts` times (default 3 from `SPORTS_SLUG_RETRY_MAX_ATTEMPTS` env var) with exponential backoff (`min(1.0 * 2^(attempt-1), 8.0)` seconds). Validates tags before adding to slug_table. Logs `event=retry_success` or `event=slug_permanently_unmapped` on completion.

3. `build_slug_table()` modified — now filters all returned tags through `_validate_market_tag()`. Tags with empty token/condition ids are moved to the unmapped list with `event=validation_failed` log instead of silently entering slug_table.

4. `sports.py` updated — calls `retry_unmapped_slugs()` after both the initial slug table build (~line 179) and the periodic 30-minute refresh (~line 223). Retry runs inside the slug refresh block (30 min cadence), not in the 1-second main loop tick.

## Commits

| Commit  | Type | Description |
|---------|------|-------------|
| ba98b98 | test | Add 14 failing tests (RED): TestValidateMarketTag, TestBuildSlugTableValidation, TestRetryUnmappedSlugs |
| e66ffe5 | feat | Implement _validate_market_tag, retry_unmapped_slugs, build_slug_table validation, sports.py wiring (GREEN) |

## Test Results

- **41/41 tests pass** in `tests/test_sports_market_discovery.py`
- **27 pre-existing tests**: all still pass (no regressions)
- **14 new tests**: all pass after GREEN implementation
- Pre-existing failures in `test_sports_trader.py::TestHaltGate` (3 tests) confirmed pre-existing — scope of 06-01, not 06-02

## Decisions Made

- **Backoff cap at 8s:** `min(1.0 * 2^(attempt-1), 8.0)` — delay sequence is 0s (attempt 0), 1s, 2s, 4s, 8s, 8s... Caps to avoid excessive blocking at 30-minute refresh intervals.
- **No new _env_int helper:** `os.getenv()` used directly in `retry_unmapped_slugs` since gamma.py had no existing `_env_int` pattern at module level. Consistent with plan spec.
- **Validation in both passes:** Tags are validated in `build_slug_table` on first lookup AND in `retry_unmapped_slugs` on retry — prevents any invalid tag from entering slug_table regardless of lookup path.
- **`time` module imported at top level:** Added `import time` to gamma.py module imports; tests patch `agents.polymarket.gamma.time` to skip real sleep delays.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check

| Item | Status |
|------|--------|
| `_validate_market_tag` exists on GammaMarketClient | FOUND |
| `retry_unmapped_slugs` exists on GammaMarketClient | FOUND |
| `build_slug_table` uses `_validate_market_tag` | FOUND |
| `sports.py` calls `retry_unmapped_slugs` after both builds | FOUND |
| 41 tests pass | FOUND |
| Commits ba98b98 and e66ffe5 exist | FOUND |

## Self-Check: PASSED
