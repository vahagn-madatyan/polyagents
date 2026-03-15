# T01: 09-live-validation 01

**Slice:** S09 — **Milestone:** M001

## Description

Add per-sport cooldown configuration and order-rate instrumentation to InGameTrader.

Purpose: VALID-02 requires sport-specific debounce thresholds instead of one global cooldown. VALID-03 requires order-rate visibility so concurrent pipeline throughput can be measured. Both changes modify the same file and extend the same class.

Output: Updated `agents/application/ingame_trader.py` with per-sport cooldown dict and rolling order-rate counter; new test classes in `tests/test_ingame_trader.py` covering both features.

## Must-Haves

- [ ] "InGameTrader uses a sport-specific cooldown for each league instead of one global value"
- [ ] "Per-sport cooldowns are loaded from SPORTS_INGAME_COOLDOWN_{LEAGUE} env vars with a global default fallback"
- [ ] "InGameTrader records a timestamp on every real (non-dry-run) order and emits a rolling 60-second order count"
- [ ] "Order-rate counter is never incremented during dry-run execution"

## Files

- `agents/application/ingame_trader.py`
- `tests/test_ingame_trader.py`
