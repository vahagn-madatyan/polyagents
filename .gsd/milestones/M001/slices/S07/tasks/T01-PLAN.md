# T01: 07-code-quality-and-state-persistence 01

**Slice:** S07 — **Milestone:** M001

## Description

Consolidate duplicated env helper functions into a single shared module and resolve the stale TODO in objects.py.

Purpose: Eliminate ~60 lines of duplicated _env_bool/_env_int/_env_float definitions across 9 modules (QUAL-01) and remove the misleading stale comment in objects.py (QUAL-02). This is mechanical refactoring with no behavioral changes.

Output: `agents/utils/env.py` (new shared module), updated imports in 9 consumer modules, cleaned objects.py, passing tests.

## Must-Haves

- [ ] "All env helper calls across 9 modules route through agents/utils/env.py with zero duplication"
- [ ] "agents/utils/env.py imports only os from stdlib — no dotenv, langchain, openai, or any project module"
- [ ] "The stale TODO comment at objects.py line 107 is removed and PolymarketEvent parses correctly"
- [ ] "All existing tests pass unchanged after the refactor"

## Files

- `agents/utils/env.py`
- `agents/utils/objects.py`
- `agents/application/executor.py`
- `agents/application/ingame_trader.py`
- `agents/application/sports_executor.py`
- `agents/application/pregame_cache.py`
- `agents/application/sports_trader.py`
- `agents/application/budget.py`
- `agents/connectors/sports_data.py`
- `agents/connectors/sports_ws.py`
- `agents/sports.py`
- `tests/test_env_helpers.py`
- `tests/test_objects.py`
