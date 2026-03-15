---
id: T01
parent: S09
milestone: M001
provides:
  - Per-sport cooldown configuration via SPORTS_INGAME_COOLDOWN_{LEAGUE} env vars
  - Rolling 60-second order-rate counter with structured log emission
key_files:
  - agents/application/ingame_trader.py
  - tests/test_ingame_trader.py
key_decisions:
  - Per-sport cooldowns stored in _sport_cooldowns dict, loaded from _FINAL_PERIODS keys at init
  - Order-rate timestamps stored as in-memory list, pruned on each access — no persistence needed
patterns_established:
  - _should_process and _is_in_cooldown accept optional league param for sport-specific thresholds
  - _record_order_timestamp called only inside the non-dry-run branch of _execute_ingame_trade
observability_surfaces:
  - "[ingame_trader] metric=order_rate_60s count=N" structured log on every real order
  - get_order_rate() public method for external read of current rolling count
duration: 12min
verification_result: passed
completed_at: 2026-03-15
blocker_discovered: false
---

# T01: 09-live-validation 01

**Added per-sport cooldown configuration and rolling 60-second order-rate instrumentation to InGameTrader.**

## What Happened

Two features added to `agents/application/ingame_trader.py`:

1. **Per-sport cooldown** — `__init__` now scans `SPORTS_INGAME_COOLDOWN_{LEAGUE}` env vars (e.g. `SPORTS_INGAME_COOLDOWN_NBA=10`) for all known leagues from `_FINAL_PERIODS`. The `_is_in_cooldown` and `_should_process` methods accept an optional `league` param; when set, they look up the sport-specific value before falling back to the global `SPORTS_INGAME_COOLDOWN_SECONDS`. All callers (`_handle_score_change`, `handle_period_transition`) now pass the league from the game state.

2. **Order-rate counter** — `_order_timestamps` list tracks timestamps of every real (non-dry-run) order. `_record_order_timestamp()` prunes entries older than 60s, appends the current timestamp, and emits a `metric=order_rate_60s count=N` structured log. It is called only inside `_execute_ingame_trade` after successful order execution, *after* the dry-run early return — so dry runs never increment it. `get_order_rate()` provides a read-only view with stale-entry pruning.

Two existing tests (`TestHaltGate.test_inprogress_proceeds_normally`, `TestHaltGate.test_auto_resume_after_suspended`) were updated to assert `_should_process(1, league="nba")` instead of `_should_process(1)`.

## Verification

```
$ python -m pytest tests/test_ingame_trader.py -v --tb=short
89 passed in 0.20s
```

- **TestPerSportCooldown** (9 tests): global fallback, env loading, shorter/longer overrides, None league, invalid env value, tick integration
- **TestOrderRate** (10 tests): initial zero, increment, stale pruning, real-trade increment, dry-run exclusion, slow-path coverage, structured log emission, rolling window

### Must-have verification:
- ✅ InGameTrader uses sport-specific cooldown per league — `_is_in_cooldown(game_id, league="nba")` uses NBA-specific value
- ✅ Per-sport cooldowns loaded from `SPORTS_INGAME_COOLDOWN_{LEAGUE}` env vars with global default fallback
- ✅ InGameTrader records timestamp on every real order and emits rolling 60-second count
- ✅ Order-rate counter never incremented during dry-run — `_record_order_timestamp` called only after `self.dry_run` early-return

## Diagnostics

No issues encountered. All pre-existing tests continue to pass with the interface change.
