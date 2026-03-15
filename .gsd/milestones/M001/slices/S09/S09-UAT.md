# S09: Live Validation — UAT

**Milestone:** M001
**Written:** 2026-03-15

## UAT Type

- UAT mode: mixed
- Why this mode is sufficient: Per-sport cooldown and order-rate are verified by unit tests (artifact-driven); slug validation and rate limit compliance are verified by live-runtime scripts against real APIs and simulated concurrent load.

## Preconditions

- Python 3.9+ with project dependencies installed
- `SPORTS_API_KEY` set (for validate_slugs.py Gamma API access)
- No running InGameTrader instance (to avoid lock conflicts during rate limit validation)

## Smoke Test

```bash
python -m pytest tests/test_ingame_trader.py -v --tb=short
# Expected: 89 passed
```

## Test Cases

### 1. Per-sport cooldown overrides global default

1. Set `SPORTS_INGAME_COOLDOWN_NBA=5` and `SPORTS_INGAME_COOLDOWN_SECONDS=30`
2. Create InGameTrader, call `_is_in_cooldown(game_id, league="nba")` after a trade
3. **Expected:** Cooldown expires after 5s (not 30s); `_sport_cooldowns["nba"] == 5`

### 2. Order-rate counter tracks real trades only

1. Create InGameTrader with `dry_run=False`, execute a trade via `_execute_ingame_trade`
2. Check `get_order_rate()`
3. **Expected:** Returns 1
4. Set `dry_run=True`, execute another trade
5. **Expected:** `get_order_rate()` still returns 1 (dry-run not counted)

### 3. Slug validation against live Polymarket

1. Run `python scripts/python/validate_slugs.py`
2. **Expected:** JSON report on stdout with per-league results; leagues with active events show "pass"; inactive leagues show "pending"

### 4. Rate limit compliance under concurrent load

1. Run `python scripts/python/validate_rate_limit.py --duration 10`
2. **Expected:** JSON report with `overall_status: "pass"` and `peak_rate < 60`

## Edge Cases

### No active events for a sport

1. Run slug validation during off-season for most sports
2. **Expected:** Those leagues report "pending" status (not "fail"); overall_status is "partial"

### Invalid per-sport cooldown env var

1. Set `SPORTS_INGAME_COOLDOWN_NBA=notanumber`
2. Create InGameTrader
3. **Expected:** Invalid value ignored; NBA falls back to global cooldown; no crash

### Order-rate window rollover

1. Record a trade, wait 61 seconds, check `get_order_rate()`
2. **Expected:** Returns 0 (stale entry pruned)

## Failure Signals

- `python -m pytest tests/test_ingame_trader.py` reports any failures (expected: 89 passed)
- validate_slugs.py crashes or returns leagues with "fail" status for active events
- validate_rate_limit.py reports `peak_rate >= 60` or `overall_status: "fail"`
- Missing `metric=order_rate_60s` structured log after real trade execution

## Requirements Proved By This UAT

- VALID-01 — Slug normalization validated against live Gamma API (test case 3)
- VALID-02 — Per-sport cooldown configuration verified by unit tests and env var override (test case 1)
- VALID-03 — Rate limit compliance proven under concurrent 9-game simulation (test case 4)

## Not Proven By This UAT

- Full 9/9 sport slug validation requires running during overlapping seasons — only active leagues can be confirmed live
- Long-duration rate limit compliance (hours) — validation runs for seconds/minutes, not production-length sessions
- Actual CLOB API rate limit enforcement — validation uses mock CLOB, not live order submission

## Notes for Tester

- Slug validation results vary by season — NBA and NHL are typically active in March; NFL/MLB/CFB/CBB may show "pending"
- Rate limit validation is fast (10s default) — increase `--duration` for higher confidence
- Both scripts write progress to stderr and JSON to stdout; use `--output` flag to save reports to file
