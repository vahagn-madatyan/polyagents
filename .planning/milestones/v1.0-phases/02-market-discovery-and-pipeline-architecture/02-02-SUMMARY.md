---
phase: 02-market-discovery-and-pipeline-architecture
plan: "02"
subsystem: sports-data-connector
tags: [sports, api-integration, caching, odds, value-bet, tdd]
dependency_graph:
  requires:
    - agents/connectors/sports_ws.py (env helper pattern reference)
    - agents/utils/objects.py (SportGameState type for get_game_context)
  provides:
    - SportsDataConnector class (team stats, H2H, bookmaker odds, value-bet detection)
  affects:
    - Phase 3 LLM prompt construction (game context injection)
tech_stack:
  added:
    - httpx==0.28.1 (async-capable HTTP client)
    - cachetools==7.0.3 (TTLCache for two-tier caching)
    - tenacity==9.1.4 (retry with exponential backoff)
  patterns:
    - TTLCache two-tier pattern (stats 24h, odds 5min)
    - Inlined _env_int/_env_float/_env_str helpers (avoids heavy executor.py import chain)
    - tenacity @retry on all private fetch methods
key_files:
  created:
    - agents/connectors/sports_data.py
    - tests/test_sports_data_connector.py
  modified:
    - .env.example
decisions:
  - "TTLCache maxsize=500 for stats, maxsize=200 for odds — sized for ~500 active teams and ~200 concurrent matchups"
  - "H2H results stored in _stats_cache (24h TTL) not _odds_cache — H2H is historical, not time-sensitive"
  - "League->API-Sports sport mapping via dict (not API call) — avoids round-trip on every stat fetch"
  - "get_game_context() returns partial data on source failure — never raises, so LLM can still trade with available info"
metrics:
  duration: 15
  completed_date: "2026-03-06"
  tasks_completed: 1
  tasks_total: 1
  files_created: 2
  files_modified: 1
---

# Phase 02 Plan 02: SportsDataConnector Summary

**One-liner:** SportsDataConnector with API-Sports and The Odds API integration, two-tier TTLCache (stats 24h / odds 5min), per-sport opt-in, and configurable 5% value-bet divergence threshold.

## What Was Built

`agents/connectors/sports_data.py` — `SportsDataConnector` class providing:

- `get_team_stats(league, team_name)` — fetches win rate, wins, losses, draws, recent form (last 5) from API-Sports. Returns None for leagues not in `SPORTS_REQUIRE_STATS`. Cached 24h.
- `get_head_to_head(league, home_team, away_team)` — fetches H2H game history. Returns list of dicts with date, scores, winner. Cached 24h.
- `get_external_odds(league, home_team, away_team)` — fetches bookmaker odds from The Odds API. Returns implied probabilities for home/away. Cached 5min.
- `detect_value_bet(polymarket_price, implied_prob)` — returns True when `|polymarket_price - implied_prob| > SPORTS_ODDS_DIVERGENCE_THRESHOLD` (default 0.05).
- `get_game_context(game_state)` — convenience method combining all sources into one dict for LLM prompt injection.

All HTTP fetch methods use `tenacity.retry` with `stop_after_attempt(3)` and `wait_exponential(min=1, max=10)`.

## Test Results

15/15 unit tests pass. All HTTP calls are fully mocked via `unittest.mock.patch` on `httpx.Client.get`. Cache behavior verified by asserting `call_count == 1` on second identical request.

## Deviations from Plan

None — plan executed exactly as written.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| TTLCache maxsize=500 for stats, maxsize=200 for odds | Sized for ~500 active teams and ~200 concurrent game matchups |
| H2H stored in `_stats_cache` (24h TTL) | H2H is historical data — not time-sensitive like live odds |
| League mapping via static dict | Avoids extra API round-trip on every stats fetch |
| `get_game_context()` returns partial on source failure | LLM can still evaluate trade with available data |

## Self-Check: PASSED

- agents/connectors/sports_data.py: FOUND
- tests/test_sports_data_connector.py: FOUND
- Commit 260f395: FOUND
- 15/15 tests passing
