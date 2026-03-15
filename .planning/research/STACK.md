# Stack Research

**Domain:** Sports data integration and live in-game trading for autonomous Polymarket bot
**Researched:** 2026-03-03
**Confidence:** HIGH (websocket), HIGH (HTTP clients), MEDIUM (sports APIs — pricing tiers change)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `websocket-client` | 1.9.0 | Polymarket sports WebSocket consumer | Already in requirements.txt (as 1.8.0). Thread-based with `run_forever()` and callback hooks — fits existing synchronous Trader architecture without requiring async rewrite. Supports Python 3.9+. Latest: 1.9.0 (Oct 2025). |
| `aiohttp` | 3.13.3 | Async HTTP for sports API polling | Already in requirements.txt. Python 3.9 compatible. Use for concurrent sports API calls when pre-game analysis needs to fan out to multiple endpoints simultaneously. |
| `tenacity` | 9.1.4 | Retry logic for WS reconnection and API calls | Already in requirements.txt (as 8.5.0). Upgrade to 9.1.4 (Feb 2026). Handles WS disconnects, API rate limit backoff, and transient HTTP failures. Supports both sync and async contexts. |

### Sports Data APIs

| Library / API | Version | Purpose | Why Recommended |
|---------------|---------|---------|-----------------|
| **API-Sports** (api-sports.io) | REST v3 | Live scores, fixtures, odds, team stats for NFL, NBA, MLB, NHL, soccer, tennis, esports | Broadest sport coverage matching Polymarket's full sports catalog. Free tier: 100 req/day per API (sufficient for research/dev). Paid plans start at $10/month. No Python SDK — use `requests` or `aiohttp` directly. Coverage: NFL, NBA, MLB, NHL, soccer (50+ leagues), tennis, esports. |
| **The Odds API** (the-odds-api.com) | REST v4 | Live and pre-game betting odds from 40+ bookmakers | Best odds source for calibrating Polymarket prices against consensus. Supports NFL, NBA, MLB, NHL, soccer, tennis. Live scores update ~30s. Free tier: 500 requests/month. No Python SDK — standard REST. Use as a signal for market mispricing. |
| **BallDontLie** | 0.1.6 (official Python SDK) | NBA, NFL, MLB live box scores and historical stats | Official Python SDK (`pip install balldontlie`). Live data updates every second during games. Free tier with generous limits. Covers NBA, NFL, MLB only — not NHL, soccer, or esports. Install: `pip install balldontlie`. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `requests` | 2.32.3 (already pinned) | Synchronous REST calls to sports APIs | Use for pre-game stat fetching in the existing synchronous pipeline. Already in requirements.txt. |
| `apscheduler` | 3.11.x | Cron-style scheduling for pre-game analysis triggers | Use if you need time-based triggers (e.g., "fetch stats 30 min before game start") separate from WS events. `AsyncIOScheduler` works with asyncio; `BackgroundScheduler` works in the current sync setup. Optional — the WS `status` field can also trigger analysis. |
| `python-dateutil` | 2.9.0 (already pinned) | Parse game start times from API responses | Already in requirements.txt. Sports APIs return varied timestamp formats. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pytest` (existing) | Unit tests for sports pipeline | Already installed. Mock WS messages using `unittest.mock` — no extra test library needed. |
| `python-dotenv` (existing) | Env var management for API keys | Already in requirements.txt. Add `API_SPORTS_KEY`, `ODDS_API_KEY`, `BALLDONTLIE_API_KEY` to `.env`. |

---

## Installation

```bash
# Upgrade existing packages to current versions
pip install "tenacity==9.1.4"
pip install "websocket-client==1.9.0"
pip install "aiohttp==3.13.3"

# Sports data API SDK (BallDontLie has official Python SDK)
pip install "balldontlie==0.1.6"

# Optional: if scheduling pre-game analysis by clock time
pip install "apscheduler==3.11.2"

# No pip install needed for API-Sports or The Odds API — use requests/aiohttp directly
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `websocket-client` (sync, `run_forever`) | `websockets` 16.x (asyncio) | If the entire trading pipeline were rewritten as async-first. `websockets` 16.x requires Python >=3.10 — incompatible with the stated Python 3.9 constraint. Do not use. |
| API-Sports (broadest sport coverage) | SportsDataIO | If budget is not a concern and you need enterprise SLAs. SportsDataIO covers more sports with cleaner data but costs significantly more. No official Python SDK — use REST. |
| API-Sports (broadest sport coverage) | MySportsFeeds | Free for non-commercial use, covers NFL/NBA/MLB/NHL only. Missing soccer and esports. Adequate if sports mode only targets North American leagues. |
| BallDontLie Python SDK | sportsipy / sportsreference | Do NOT use sportsipy. Last commit: January 2021. 90 open issues. Explicitly marked "no longer under active development." Will break on current season data. |
| The Odds API | odds-api.io | 250+ bookmakers vs 40+. More expensive. Only use if you need maximum bookmaker coverage for arbitrage detection. |
| `tenacity` (already in stack) | `backoff` (already in stack) | `backoff` is already present and works. `tenacity` is more expressive for complex retry policies (jitter, conditional retry on exception type). Either works — prefer `tenacity` for new sports code to match future pattern. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `websockets` >= 13.x | Requires Python >=3.10. Project is pinned to Python 3.9. The existing `websockets==12.0` in requirements.txt is already the highest compatible version for 3.9. Do not upgrade past 12.x unless Python runtime is also upgraded. | `websocket-client==1.9.0` for the sports WS consumer |
| `sportsipy` / `sportsreference` | Abandoned since Jan 2021. Scrapes sports-reference.com (fragile to DOM changes). 90 unresolved issues. Stats break mid-season. No maintenance. | BallDontLie SDK (NBA/NFL/MLB) or API-Sports (all leagues) |
| Polling the Polymarket sports WS by REST | The sports data is pushed over WS in real time. Polling `https://sports-api.polymarket.com` as HTTP would miss sub-second state changes. | Connect as persistent WebSocket using `websocket-client` |
| Building a custom odds model | Out of scope per PROJECT.md. LLM+external odds data is sufficient. Custom models require backtesting infrastructure (also out of scope). | Feed external odds from The Odds API directly into the LLM prompt context |
| `asyncio.run()` at the top of the sports pipeline | Mixing sync (existing Trader) and async (new sports WS) at the top level causes event loop conflicts in Python 3.9. | Run the WS consumer in a dedicated thread using `websocket-client`'s threaded mode, communicating with the main trading logic via a thread-safe `queue.Queue`. |

---

## Stack Patterns by Variant

**For the Polymarket sports WebSocket consumer:**
- Use `websocket-client` with `WebSocketApp.run_forever()` in a daemon thread
- Pass game state updates via `queue.Queue` to the main sports trading loop
- Because the existing `Trader` class is synchronous — adding a full asyncio layer would require rewriting the LangChain agent calls which use sync OpenAI client

**For pre-game static stat fetching:**
- Use `requests` (sync) when running inside the existing synchronous Trader flow
- Use `aiohttp` only if you add a dedicated async pre-game pipeline that runs independently
- Because mixing sync/async in the same call stack without careful thread management causes deadlocks

**For live in-game trading reaction:**
- Receive WS game state → put into queue → trading thread consumes → calls existing `polymarket.execute_market_order_for_token()` synchronously
- Because the CLOB client (`py-clob-client`) is synchronous and already handles order execution

**If Python runtime is upgraded to 3.10+:**
- Replace `websocket-client` WS consumer with `websockets` >= 14.x for native asyncio integration
- Migrate entire sports pipeline to `async def` with `asyncio.gather()` for concurrent API calls
- Not recommended for this milestone — keep the runtime constraint

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| `websocket-client==1.9.0` | Python 3.9–3.13 | Drop-in upgrade from 1.8.0 already in requirements.txt |
| `websockets==12.0` (existing) | Python 3.9 | Do NOT upgrade past 12.x — 13.x+ drops Python 3.9 support |
| `aiohttp==3.13.3` | Python 3.9–3.14 | Safe upgrade from 3.10.0 in requirements.txt |
| `tenacity==9.1.4` | Python 3.9+ | Safe upgrade from 8.5.0 in requirements.txt |
| `balldontlie==0.1.6` | Python 3.8+ | New addition; no conflict with existing packages |
| `apscheduler==3.11.x` | Python 3.9+ | Only add if clock-based pre-game triggers are needed |

---

## API Coverage Matrix

Polymarket sports catalog vs available APIs:

| Sport | API-Sports | BallDontLie | The Odds API | MySportsFeeds |
|-------|-----------|-------------|-------------|---------------|
| NFL | YES | YES | YES | YES |
| NBA | YES | YES | YES | YES |
| MLB | YES | YES | YES | YES |
| NHL | YES | NO | YES | YES |
| CFB (College Football) | YES | NO | YES | NO |
| CBB (College Basketball) | YES | NO | YES | NO |
| Soccer (EPL, etc.) | YES (50+ leagues) | NO | YES | NO |
| Esports | YES | NO | NO | NO |
| Tennis | YES | NO | YES | NO |

**Conclusion:** API-Sports is the only single API that covers the full Polymarket sports catalog (NFL through esports). Use BallDontLie as a supplemental source for NBA/NFL/MLB where its real-time 1-second update frequency and official Python SDK simplify integration.

---

## Sources

- PyPI: `websocket-client` — version 1.9.0, Python 3.9+, October 2025 release — HIGH confidence
- PyPI: `websockets` — version 16.0, Python >=3.10, January 2026 — HIGH confidence (confirmed Python 3.9 NOT supported)
- PyPI: `aiohttp` — version 3.13.3, Python 3.9+, January 2026 — HIGH confidence
- PyPI: `tenacity` — version 9.1.4, February 2026 — HIGH confidence
- PyPI: `balldontlie` — version 0.1.6, December 2024, Python 3.8+ — HIGH confidence
- github.com/roclark/sportsipy — last commit January 2021, explicitly abandoned — HIGH confidence (do not use)
- balldontlie.io docs — NBA, NFL, MLB coverage confirmed, live data every 1 second — MEDIUM confidence
- api-sports.io — 100 req/day free tier, $10/month paid, broad sport coverage — MEDIUM confidence (pricing may change)
- the-odds-api.com/liveapi/guides/v4 — v4 REST API, live scores ~30s update, 500 req/month free — MEDIUM confidence
- websockets.readthedocs.io 16.0 — asyncio reconnect pattern confirmed — HIGH confidence
- Existing requirements.txt — `websocket-client==1.8.0`, `websockets==12.0`, `aiohttp==3.10.0`, `tenacity==8.5.0` all present

---

*Stack research for: Sports mode — Polymarket autonomous trading bot*
*Researched: 2026-03-03*
