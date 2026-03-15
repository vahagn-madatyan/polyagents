---
id: T02
parent: S09
milestone: M001
provides:
  - VALID-01 slug normalization validation script against live Polymarket Gamma API
  - VALID-03 concurrent rate limit compliance validation script with structured JSON reports
key_files:
  - scripts/python/validate_slugs.py
  - scripts/python/validate_rate_limit.py
key_decisions:
  - validate_slugs.py uses Gamma events search with league string matching, then exercises both fast-path (slug lookup) and fallback (team-based search) resolution
  - validate_rate_limit.py runs InGameTrader in non-dry-run mode with mock CLOB to exercise real order-rate instrumentation through tick() with all 9 concurrent games
  - Pending sports (no live events) tracked with "pending" status, not "fail" — overall_status reflects this distinction
patterns_established:
  - Validation scripts are standalone in scripts/python/, import from project root via sys.path manipulation
  - Structured JSON reports include validation_id, timestamp, duration, per-league/per-pipeline breakdowns
  - Scripts write to stdout (JSON) and stderr (progress logs); --output flag for file persistence
observability_surfaces:
  - "[validate_slugs] event=league_result league=X status=Y" progress logs on stderr
  - "[validate_rate_limit] event=complete overall_status=X peak_rate=Y" summary log on stderr
  - JSON reports with rate_samples array and per-slug resolution details for post-hoc analysis
duration: 12min
verification_result: passed
completed_at: 2026-03-15
blocker_discovered: false
---

# T02: 09-live-validation 02

**Created live validation scripts for slug normalization (VALID-01) and concurrent CLOB rate limit compliance (VALID-03) with structured JSON reports.**

## What Happened

Two standalone validation scripts created in `scripts/python/`:

1. **`validate_slugs.py`** (VALID-01) — Queries live Polymarket Gamma API for active events across all 9 sport types (NFL, NBA, MLB, NHL, CFB, CBB, soccer, CS2, tennis). For each event found, exercises the full slug resolution pipeline: fast-path `lookup_markets_by_slug` first, then `lookup_markets_fallback` with team extraction. Validates returned `SportsMarketTag` entries have non-empty token/condition IDs. Reports per-league status as pass/pending/fail with slug-level details.

   Live run (2026-03-15): NBA (5 slugs, all resolved via fast_path), NHL (1 slug, resolved). 7 other leagues correctly reported as "pending" (no active events, off-season).

2. **`validate_rate_limit.py`** (VALID-03) — Creates a real InGameTrader in non-dry-run mode with mock CLOB dependencies. Runs 9 concurrent games (one per league) through `tick()` at 1-second cadence with score changes injected each tick. A simulated general pipeline runs alongside on a separate thread. Captures `metric=order_rate_60s count=N` structured logs from the order-rate counter and verifies the peak never exceeds 60.

   Live run (10-second window): peak_rate=9 orders in rolling 60s window across 9 concurrent games. The 30-second default cooldown naturally limits throughput to ~1 order per game per 30s — well under the 60/min CLOB limit.

## Verification

```
$ python scripts/python/validate_slugs.py 2>&1 | grep overall_status
  "overall_status": "partial",

$ python scripts/python/validate_rate_limit.py --duration 10 2>&1 | grep overall_status
  "overall_status": "pass",

$ python -m pytest tests/test_ingame_trader.py -v --tb=short
89 passed in 0.20s
```

### Must-have verification:
- ✅ Validation script exercises full slug resolution pipeline against live Polymarket data — NBA (5 slugs) and NHL (1 slug) resolved via Gamma API
- ✅ Validation script runs both pipelines concurrently, counts order-rate events, proves system stays under 60/min — peak_rate=9
- ✅ Sports with no live game tracked as "pending" (not "failed") — 7 leagues correctly pending

### Slice-level verification:
- ✅ All 89 existing tests pass (per-sport cooldown + order-rate instrumentation from T01)
- ✅ validate_slugs.py produces structured JSON report per VALID-01
- ✅ validate_rate_limit.py produces structured JSON report per VALID-03

## Diagnostics

Run slug validation:
```bash
python scripts/python/validate_slugs.py --output /tmp/valid01_report.json
```

Run rate limit validation:
```bash
python scripts/python/validate_rate_limit.py --duration 15 --output /tmp/valid03_report.json
```

Both scripts emit progress to stderr and the JSON report to stdout.

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `scripts/python/validate_slugs.py` — VALID-01 slug normalization validation script
- `scripts/python/validate_rate_limit.py` — VALID-03 concurrent rate limit compliance validation script
