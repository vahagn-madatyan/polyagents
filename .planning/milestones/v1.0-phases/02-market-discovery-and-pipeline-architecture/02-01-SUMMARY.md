---
phase: 02-market-discovery-and-pipeline-architecture
plan: "01"
subsystem: market-discovery
tags: [pydantic, gamma-api, slug-lookup, sports, moneyline-filter, tdd]
dependency_graph:
  requires:
    - Phase 01 SportsWS connector (provides SportGameState with slug field)
    - agents/polymarket/gamma.py GammaMarketClient base class
  provides:
    - SportsMarketTag model (slug, league, teams, market_id, condition_id, token_ids, question)
    - GammaMarketClient.lookup_markets_by_slug (fast path)
    - GammaMarketClient.lookup_markets_fallback (team-name fallback)
    - GammaMarketClient.build_slug_table (full table refresh)
    - GammaMarketClient.lookup_single_slug (on-demand new gameId)
  affects:
    - Phase 03 trading pipeline (consumes SportsMarketTag to place CLOB orders)
    - Phase 02-03 pipeline architecture (slug table used as cache between WS and trader)
tech_stack:
  added: []
  patterns:
    - TDD red-green cycle with unittest.mock.patch for httpx isolation
    - Lazy import of heavy Polymarket class moved to __main__ block to avoid requests dep
    - _logger() guard pattern for __new__-constructed test instances
key_files:
  created:
    - tests/test_sports_market_discovery.py
  modified:
    - agents/utils/objects.py
    - agents/polymarket/gamma.py
    - .env.example
decisions:
  - "Moneyline filter uses 'win'/'winner' keyword check on question text — simple and robust across all 9 sport types without sport-specific logic"
  - "build_slug_table returns (slug_table, unmapped) tuple rather than side-effecting a queue — keeps method pure and testable"
  - "Lazy import for Polymarket in __main__ block removes transitive requests dep from module import, enabling tests without full dep chain"
  - "_logger() helper guards against AttributeError when tests use GammaMarketClient.__new__ to bypass __init__"
metrics:
  duration_minutes: 25
  completed_date: "2026-03-06"
  tasks_completed: 1
  files_modified: 4
---

# Phase 02 Plan 01: Sports Market Discovery Summary

**One-liner:** Slug-based Gamma API market discovery with moneyline filter, team-name fallback, and full slug table refresh for sports trading pipeline.

## What Was Built

`SportsMarketTag` Pydantic model added to `agents/utils/objects.py` — links a WebSocket game slug to the exact Polymarket CLOB token pair needed to place orders. Five new methods added to `GammaMarketClient` in `agents/polymarket/gamma.py`:

| Method | Purpose |
|--------|---------|
| `_is_moneyline_market` | Filters markets by "win"/"winner" keyword — excludes spreads, totals, props |
| `_extract_teams_from_slug` | Parses "nfl-lac-buf-2025-01-26" into `("nfl", ["lac", "buf"])` |
| `lookup_markets_by_slug` | Fast path: GET `/events/slug/{slug}`, returns empty list on 404/error |
| `lookup_markets_fallback` | GET `/events?active=True&closed=False`, filters by team names + league in title/slug |
| `build_slug_table` | Maps all active game states to markets; logs unmapped and returns retry list |
| `lookup_single_slug` | On-demand lookup for new gameIds from WS — slug path then fallback |

27 unit tests cover all happy paths, 404/error paths, moneyline filtering, slug parsing, unmapped logging, and retry list construction.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Moved Polymarket import to avoid transitive `requests` dependency**
- **Found during:** Task 1 GREEN phase — test collection failed with `ModuleNotFoundError: No module named 'requests'`
- **Issue:** `gamma.py` imported `from agents.polymarket.polymarket import Polymarket` at module level; `polymarket.py` imports `requests` which is not installed in the test venv path. The `Polymarket` class is only used in the `__main__` block.
- **Fix:** Moved `from agents.polymarket.polymarket import Polymarket` inside the `if __name__ == "__main__":` block
- **Files modified:** `agents/polymarket/gamma.py`
- **Commit:** cae92ab

**2. [Rule 1 - Bug] Added `_logger()` guard for `__new__`-constructed test instances**
- **Found during:** Task 1 GREEN phase — `AttributeError: 'GammaMarketClient' object has no attribute 'logger'`
- **Issue:** Tests use `GammaMarketClient.__new__(GammaMarketClient)` to bypass `__init__` (so no real httpx client is created), but new methods called `self.logger` which doesn't exist without `__init__`.
- **Fix:** Added `_logger()` helper method that returns `self.logger` if set, else falls back to `logging.getLogger(__name__)`
- **Files modified:** `agents/polymarket/gamma.py`
- **Commit:** cae92ab

## Self-Check: PASSED

Files verified:
- `agents/utils/objects.py` — contains `class SportsMarketTag` (count: 1)
- `agents/polymarket/gamma.py` — contains `lookup_markets_by_slug`, `lookup_markets_fallback`, `build_slug_table` (count: 9 matches)
- `tests/test_sports_market_discovery.py` — 27 tests all pass
- `.env.example` — contains `SPORTS_SLUG_REFRESH_INTERVAL_SECONDS`

Commits verified:
- `fe5047b` — test(02-01): failing tests RED
- `cae92ab` — feat(02-01): implementation GREEN
