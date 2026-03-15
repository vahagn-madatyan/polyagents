# S09: Live Validation

**Goal:** Add per-sport cooldown configuration and order-rate instrumentation to InGameTrader.
**Demo:** Add per-sport cooldown configuration and order-rate instrumentation to InGameTrader.

## Must-Haves


## Tasks

- [x] **T01: 09-live-validation 01**
  - Add per-sport cooldown configuration and order-rate instrumentation to InGameTrader.

Purpose: VALID-02 requires sport-specific debounce thresholds instead of one global cooldown. VALID-03 requires order-rate visibility so concurrent pipeline throughput can be measured. Both changes modify the same file and extend the same class.

Output: Updated `agents/application/ingame_trader.py` with per-sport cooldown dict and rolling order-rate counter; new test classes in `tests/test_ingame_trader.py` covering both features.
- [x] **T02: 09-live-validation 02**
  - Create live validation scripts for slug normalization (VALID-01) and concurrent CLOB rate limit compliance (VALID-03).

Purpose: VALID-01 requires evidence that slug normalization works for all 9 sport types against live Polymarket data. VALID-03 requires evidence that concurrent sports + general pipelines stay under 60 orders/min. Both produce structured JSON reports per CONTEXT.md evidence standard.

Output: Two standalone scripts in `scripts/python/` that exercise the production pipeline in observe-first mode and emit structured pass/fail JSON reports.

## Files Likely Touched

- `agents/application/ingame_trader.py`
- `tests/test_ingame_trader.py`
- `scripts/python/validate_slugs.py`
- `scripts/python/validate_rate_limit.py`
