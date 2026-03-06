# Phase 2: Market Discovery and Pipeline Architecture - Research

**Researched:** 2026-03-06
**Domain:** Polymarket Gamma API slug lookup, external sports data APIs, cross-process budget coordination, process isolation
**Confidence:** HIGH (core architecture), MEDIUM (external API selection), HIGH (race condition approach)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Slug Mapping Strategy**
- Unmapped games (no Polymarket market found): log and queue for retry on next refresh cycle — markets may appear after initial listing
- Refresh cadence: periodic full rebuild every 30 minutes PLUS immediate single-slug lookup when WS reports a new gameId not already in the table
- Market type filter: moneyline only (who wins) for v1 — skip spreads, totals, and props
- Matching approach: exact slug match first, fall back to team-name substring search (extract team names from WS slug, search Gamma markets containing both team names + league tag)

**External Stats API**
- Provider: Claude's discretion (research picks best)
- Uncovered sports handling: configurable per sport via `SPORTS_REQUIRE_STATS` env var list
- Odds divergence threshold: Claude's discretion (must be configurable via `SPORTS_ODDS_DIVERGENCE_THRESHOLD`)
- Caching: two-tier TTL — team stats 24h, odds 5min; both configurable via env vars

**Budget Coordination**
- Budget allocation: fixed fraction of wallet balance at startup — `SPORTS_BUDGET_FRACTION` env var
- Per-sport caps: `SPORTS_CAP_NFL=0.4`, `SPORTS_CAP_NBA=0.3`; unconfigured leagues share remainder equally
- Race condition protection: Claude's discretion (file lock, in-memory, or other)
- Safety floor: `SPORTS_MIN_WALLET_USD` — stop sports trades below this balance

**Pipeline Isolation**
- Architecture: separate Python process — `python -m agents.sports` entry point
- Launcher: independent start (two terminal windows / two containers)
- Dry-run mode: `EXECUTE_TRADES` is master flag; `SPORTS_EXECUTE_TRADES` overrides for sports only
- No-game behavior: idle loop — stay alive, check for upcoming games periodically

### Claude's Discretion
- Exact Gamma API query parameters for slug/market lookup
- External stats API selection (research picks best coverage)
- Odds divergence threshold default value
- Race condition protection mechanism (file lock vs in-memory vs other)
- SportsDataAPI class internal structure and error handling
- BudgetCoordinator implementation details

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| MKT-01 | Bot identifies sports markets on Polymarket and tags them with metadata (league, teams, game time) | Gamma `/events` endpoint with `tag_id` filter + slug field on PolymarketEvent model |
| MKT-02 | Bot maps websocket `gameId`/`slug` to Polymarket market IDs and token addresses via Gamma API slug lookup | `GET /events/slug/{slug}` path endpoint; fallback via team-name substring + league tag filter |
| MKT-03 | Bot compares external odds against Polymarket price to detect value bets when divergence exceeds configurable threshold | The Odds API for NFL/NBA/MLB/NHL/tennis; recommended default 5% threshold via `SPORTS_ODDS_DIVERGENCE_THRESHOLD` |
| DATA-01 | Bot integrates with external sports data API for team stats, season performance, and head-to-head history | API-Sports (api-sports.io) — covers NFL, NBA, MLB, NHL, basketball, baseball, hockey; free 100 req/day |
| DATA-02 | Bot fetches current season win rates and recent performance for both teams before each game | API-Sports team standings + team statistics endpoints; cached 24h via `cachetools.TTLCache` |
| DATA-03 | Bot fetches historical head-to-head matchup records between teams | API-Sports head-to-head endpoint (h2h); cached 24h |
| PIPE-01 | Sports pipeline runs as a separate process alongside general pipeline without interference | Separate Python process with its own entry point; OS process boundary provides isolation |
| PIPE-02 | Bot has configurable budget split via `SPORTS_BUDGET_FRACTION` environment variable | `filelock` for cross-process coordination; lock file at startup for one-time allocation |
| PIPE-03 | Budget coordinator prevents race conditions when both pipelines read/allocate USDC concurrently | `filelock.FileLock` (already in requirements.txt v3.15.4) — OS-level fcntl lock; timeout=5s |
| PIPE-04 | Bot supports configurable per-sport budget caps via env vars | `SPORTS_CAP_{LEAGUE}` pattern parsed at `BudgetCoordinator.__init__` |
| PIPE-05 | Sports pipeline supports dry-run mode consistent with `EXECUTE_TRADES` flag | `SPORTS_EXECUTE_TRADES` env var overrides master flag; same `_env_bool()` helper pattern |
</phase_requirements>

---

## Summary

Phase 2 builds three distinct subsystems that must interoperate cleanly with Phase 1's `SportsWSConnector`: (1) a slug-to-market-ID lookup table backed by Polymarket's Gamma API, (2) a connector to an external sports stats and odds API, and (3) a cross-process budget coordinator that prevents race conditions when the sports and general pipelines run concurrently.

The Gamma API offers a dedicated `GET /events/slug/{slug}` path endpoint (HIGH confidence) that is the fastest lookup path. The fallback is a filtered `/events` query using `tag_id` and team-name substring search. All lookup logic extends the existing `GammaMarketClient` — no new HTTP client needed.

For external sports data, API-Sports (api-sports.io) is the recommended provider: it covers all 9 Polymarket sports (NFL, NBA, MLB, NHL, CFB, CBB via basketball/football endpoints, soccer, MMA; esports and tennis handled separately), has a free tier with 100 requests/day sufficient for dev/test, and provides team stats, standings, and H2H endpoints. The Odds API covers traditional sports odds for NFL/NBA/MLB/NHL/tennis but lacks esports. For esports (CS2), a separate provider like PandaScore or OddsPapi would be needed, but since the `SPORTS_REQUIRE_STATS` env var makes stats optional per sport, esports can be excluded from stats requirement in v1. The `filelock` library (already in requirements.txt at v3.15.4) is the correct choice for cross-process budget coordination — it provides OS-level file locks that work across independent Python processes without a shared memory object.

**Primary recommendation:** Extend `GammaMarketClient` with `lookup_markets_by_slug()` and `bulk_rebuild_slug_table()`; add `agents/connectors/sports_data.py` using `httpx` + `cachetools.TTLCache` for API-Sports; add `BudgetCoordinator` to `agents/application/budget.py` using `filelock.FileLock` for cross-process safety.

---

## Standard Stack

### Core (all already in requirements.txt)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | 0.27.0 | HTTP client for API-Sports and Gamma API calls | Already used by `GammaMarketClient`; sync client; no new dep |
| cachetools | 5.4.0 | TTLCache for two-tier stats/odds caching | Already installed; purpose-built TTL eviction; thread-safe with `@cached` decorator |
| filelock | 3.15.4 | Cross-process budget lock file | Already installed; OS-level fcntl/msvcrt; works across separate processes |
| tenacity | 8.5.0 | Retry logic for API calls | Already installed; exponential backoff for transient API failures |
| pydantic | 2.8.2 | Data models for `SportsMarketTag`, API response parsing | Already used throughout; consistent with codebase |

### External API

| API | Cost | Coverage | Rate Limit |
|-----|------|---------|------------|
| API-Sports (api-sports.io) | Free tier (100 req/day/API), $10+/mo paid | NFL, NBA, MLB, NHL, basketball, football, baseball, hockey, soccer, MMA | 100/day free; higher on paid |
| The Odds API (the-odds-api.com) | Credit-based quota system | NFL, NBA, MLB, NHL, soccer (80+ leagues), tennis (ATP/WTA) — NO esports | per-request credits; no free tier documented |

**Recommendation:** Use API-Sports for team statistics (win rates, H2H). Use The Odds API for bookmaker odds divergence detection. Both keys stored as env vars. Esports (`SPORTS_REQUIRE_STATS` must NOT include `cs2`/`esports` in v1).

### New Env Vars (add to .env.example)

```bash
# External stats API
SPORTS_DATA_API_KEY=""
SPORTS_ODDS_API_KEY=""
SPORTS_REQUIRE_STATS="nfl,nba,mlb,nhl"
SPORTS_STATS_CACHE_TTL_SECONDS="86400"
SPORTS_ODDS_CACHE_TTL_SECONDS="300"
SPORTS_ODDS_DIVERGENCE_THRESHOLD="0.05"

# Budget coordination
SPORTS_BUDGET_FRACTION="0.30"
SPORTS_MIN_WALLET_USD="50.0"
SPORTS_CAP_NFL="0.4"
SPORTS_CAP_NBA="0.3"
SPORTS_CAP_MLB="0.15"
SPORTS_CAP_NHL="0.15"
SPORTS_BUDGET_LOCK_TIMEOUT_SECONDS="5"
SPORTS_BUDGET_LOCK_PATH="/tmp/polyagents_budget.lock"
SPORTS_BUDGET_FILE_PATH="/tmp/polyagents_budget.json"

# Pipeline flags
SPORTS_EXECUTE_TRADES=""

# Gamma slug lookup
SPORTS_SLUG_REFRESH_INTERVAL_SECONDS="1800"
SPORTS_SLUG_RETRY_QUEUE_SIZE="100"
```

---

## Architecture Patterns

### Recommended Project Structure (new files only)

```
agents/
├── connectors/
│   └── sports_data.py        # NEW: SportsDataConnector (API-Sports + The Odds API)
├── polymarket/
│   └── gamma.py              # EXTEND: add slug lookup methods to GammaMarketClient
├── application/
│   └── budget.py             # EXTEND: add BudgetCoordinator class
├── utils/
│   └── objects.py            # EXTEND: add SportsMarketTag Pydantic model
└── sports.py                 # NEW: entry point for sports pipeline
```

### Pattern 1: Gamma Slug Lookup

**What:** Two-method approach on `GammaMarketClient` — fast path uses `/events/slug/{slug}` directly (exact match), slow path falls back to filtered `/events` query with team names and league tag.

**When to use:** Fast path on every incoming WS slug; slow path only when fast path returns 404.

**The slug format from WS (confirmed from Phase 1 test fixtures):**
```
nfl-lac-buf-2025-01-26      (league-team1-team2-date)
soccer-man-city-chelsea-2025-04-12
```

**Example — extending GammaMarketClient:**
```python
# In agents/polymarket/gamma.py — add to GammaMarketClient

def lookup_markets_by_slug(self, ws_slug: str) -> list[dict]:
    """Fast path: exact slug lookup via /events/slug/{slug}.

    Returns list of markets from the event, empty list if not found.
    Moneyline filter: include only markets where question contains 'win' or 'winner'.
    """
    url = f"{self.gamma_events_endpoint}/slug/{ws_slug}"
    try:
        response = self.http_client.get(url)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        event = response.json()
        markets = event.get("markets") or []
        # Moneyline filter — keep only "will X win?" style markets
        return [m for m in markets if self._is_moneyline_market(m)]
    except Exception as err:
        print(f"[gamma_slug] event=lookup_error slug={ws_slug} error={err}")
        return []

def lookup_markets_fallback(self, league: str, home_team: str, away_team: str) -> list[dict]:
    """Slow path: substring search when exact slug match fails.

    Queries /events with active=true, tag_id for the league, checks
    that event title/slug contains both team name fragments.
    """
    # team names extracted from ws_slug; search Gamma events containing both
    params = {
        "active": True,
        "closed": False,
        "limit": 20,
        # tag_id varies by league — discover via GET /tags at startup
    }
    ...

def _is_moneyline_market(self, market: dict) -> bool:
    """Return True if market is a moneyline (winner) market, not spread/total/prop."""
    question = (market.get("question") or "").lower()
    # Moneyline questions: "Will X win?", "Who will win?"
    return any(kw in question for kw in ("win", "winner", "beat", "defeat"))
```

**IMPORTANT: Slug normalization risk (from STATE.md)**
The WS slug format (`nfl-lac-buf-2025-01-26`) may not match the Gamma event slug exactly. Gamma slugs can use full team names instead of abbreviations (e.g., `chargers` vs `lac`). The exact match will fail for some sports. The fallback team-name search is essential for these cases. Validation against live Polymarket data is required before shipping — do not assume NFL abbreviation patterns generalize to all 9 sports.

### Pattern 2: Slug Table (SlugMarketIndex)

**What:** An in-memory dict `{ws_slug: list[market_id]}` built at startup and refreshed every 30 minutes. Separate retry queue for unmapped slugs checked on each refresh cycle.

**When to use:** Every time the sports pipeline needs to resolve a `game_id` from `SportsWSConnector` to Polymarket market IDs.

**Example:**
```python
# In agents/polymarket/slug_index.py (new file) or inline in sports.py

import threading
import time
from collections import deque

class SlugMarketIndex:
    """Thread-safe slug-to-market-ID lookup table.

    Rebuilt every SPORTS_SLUG_REFRESH_INTERVAL_SECONDS (default 1800).
    Unmapped slugs queued for retry on next refresh.
    """

    def __init__(self, gamma: GammaMarketClient) -> None:
        self._gamma = gamma
        self._table: dict[str, list[str]] = {}  # slug -> [market_id, ...]
        self._lock = threading.Lock()
        self._retry_queue: deque[str] = deque(maxlen=100)  # unmapped slugs
        self._refresh_interval = _env_int("SPORTS_SLUG_REFRESH_INTERVAL_SECONDS", 1800)
        self._last_rebuild_at: float = 0.0

    def lookup(self, ws_slug: str) -> list[str]:
        """Return market IDs for a WS slug, or empty list if unmapped."""
        with self._lock:
            if ws_slug in self._table:
                return list(self._table[ws_slug])
        # Miss — try immediate single-slug lookup
        markets = self._gamma.lookup_markets_by_slug(ws_slug)
        if not markets:
            markets = self._resolve_fallback(ws_slug)
        if markets:
            ids = [str(m["id"]) for m in markets if m.get("id")]
            with self._lock:
                self._table[ws_slug] = ids
            return ids
        # Still unmapped — queue for next refresh
        print(f"[slug_index] event=unmapped slug={ws_slug}")
        self._retry_queue.append(ws_slug)
        return []

    def rebuild(self) -> None:
        """Full rebuild: fetch all active sports events from Gamma."""
        ...
```

### Pattern 3: SportsDataConnector (API-Sports + The Odds API)

**What:** Single connector class wrapping two external APIs with two-tier TTL caching. Stats methods use 24h cache (win rates/H2H change slowly). Odds methods use 5-minute cache.

**Example:**
```python
# In agents/connectors/sports_data.py

import os
import threading
import httpx
from cachetools import TTLCache, cached
from cachetools.keys import hashkey

def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class SportsDataConnector:
    """Connector for external sports stats (API-Sports) and odds (The Odds API).

    Two-tier TTL caching:
      - team stats / H2H: 24h (slow-changing)
      - bookmaker odds: 5min (fast-changing)
    """

    APISPORTS_BASE = "https://v1.{sport}.api-sports.io"
    ODDS_BASE = "https://api.the-odds-api.com/v4"

    def __init__(self) -> None:
        stats_ttl = _env_int("SPORTS_STATS_CACHE_TTL_SECONDS", 86400)
        odds_ttl = _env_int("SPORTS_ODDS_CACHE_TTL_SECONDS", 300)

        self._stats_cache: TTLCache = TTLCache(maxsize=500, ttl=stats_ttl)
        self._odds_cache: TTLCache = TTLCache(maxsize=200, ttl=odds_ttl)
        self._cache_lock = threading.Lock()

        self._stats_key = os.getenv("SPORTS_DATA_API_KEY", "")
        self._odds_key = os.getenv("SPORTS_ODDS_API_KEY", "")
        self._divergence_threshold = _env_float("SPORTS_ODDS_DIVERGENCE_THRESHOLD", 0.05)

        timeout = httpx.Timeout(10.0)
        self._http = httpx.Client(timeout=timeout, headers={"Accept": "application/json"})

    def get_team_season_stats(self, league: str, season: int, team_id: int) -> dict:
        """Fetch win rate and recent form. Cached 24h."""
        key = hashkey("season_stats", league, season, team_id)
        with self._cache_lock:
            if key in self._stats_cache:
                return self._stats_cache[key]
        result = self._fetch_team_stats(league, season, team_id)
        with self._cache_lock:
            self._stats_cache[key] = result
        return result

    def get_head_to_head(self, league: str, team1_id: int, team2_id: int, last_n: int = 10) -> list[dict]:
        """Fetch H2H matchup records. Cached 24h."""
        key = hashkey("h2h", league, team1_id, team2_id)
        with self._cache_lock:
            if key in self._stats_cache:
                return self._stats_cache[key]
        result = self._fetch_h2h(league, team1_id, team2_id, last_n)
        with self._cache_lock:
            self._stats_cache[key] = result
        return result

    def get_bookmaker_odds(self, sport_key: str, event_id: str) -> dict | None:
        """Fetch current bookmaker moneyline odds. Cached 5min."""
        key = hashkey("odds", sport_key, event_id)
        with self._cache_lock:
            if key in self._odds_cache:
                return self._odds_cache[key]
        result = self._fetch_odds(sport_key, event_id)
        with self._cache_lock:
            self._odds_cache[key] = result
        return result

    def detect_value_bet(self, polymarket_price: float, bookmaker_prob: float) -> bool:
        """Return True if Polymarket diverges from bookmaker by >= threshold."""
        divergence = abs(polymarket_price - bookmaker_prob)
        return divergence >= self._divergence_threshold

    def _fetch_team_stats(self, league: str, season: int, team_id: int) -> dict:
        """API-Sports standings/statistics endpoint."""
        sport = self._league_to_sport(league)
        url = self.APISPORTS_BASE.format(sport=sport) + "/standings"
        headers = {"x-apisports-key": self._stats_key}
        try:
            resp = self._http.get(url, params={"league": self._league_id(league), "season": season, "team": team_id}, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception as err:
            print(f"[sports_data] event=stats_error league={league} team_id={team_id} error={err}")
            return {}

    def _fetch_h2h(self, league: str, team1_id: int, team2_id: int, last_n: int) -> list[dict]:
        """API-Sports H2H endpoint."""
        sport = self._league_to_sport(league)
        url = self.APISPORTS_BASE.format(sport=sport) + "/games/h2h"
        headers = {"x-apisports-key": self._stats_key}
        try:
            resp = self._http.get(url, params={"h2h": f"{team1_id}-{team2_id}", "last": last_n}, headers=headers)
            resp.raise_for_status()
            return resp.json().get("response", [])
        except Exception as err:
            print(f"[sports_data] event=h2h_error league={league} error={err}")
            return []

    def _fetch_odds(self, sport_key: str, event_id: str) -> dict | None:
        """The Odds API single-event odds."""
        url = f"{self.ODDS_BASE}/sports/{sport_key}/events/{event_id}/odds"
        try:
            resp = self._http.get(url, params={"apiKey": self._odds_key, "markets": "h2h", "regions": "us"})
            if resp.status_code == 422:
                return None  # event not found / not yet listed
            resp.raise_for_status()
            return resp.json()
        except Exception as err:
            print(f"[sports_data] event=odds_error sport={sport_key} event={event_id} error={err}")
            return None

    @staticmethod
    def _league_to_sport(league: str) -> str:
        """Map WS league abbreviation to API-Sports sport subdomain."""
        mapping = {
            "nfl": "american-football",
            "cfb": "american-football",
            "nba": "basketball",
            "cbb": "basketball",
            "mlb": "baseball",
            "nhl": "hockey",
            "soccer": "football",  # API-Sports uses "football" for soccer
        }
        return mapping.get(league.lower(), "american-football")

    @staticmethod
    def _league_id(league: str) -> int:
        """Map WS league abbreviation to API-Sports league ID (approximate).
        IMPORTANT: These IDs must be verified against live API-Sports data.
        """
        # Placeholder IDs — validate against api-sports.io/documentation
        mapping = {
            "nfl": 1,
            "nba": 12,  # NBA = league 12 in basketball API
            "mlb": 1,   # verify
            "nhl": 57,  # verify
        }
        return mapping.get(league.lower(), 1)
```

### Pattern 4: BudgetCoordinator (cross-process)

**What:** `BudgetCoordinator` uses `filelock.FileLock` to protect reads/writes of a shared budget state JSON file. At startup each pipeline reads its allocation once and operates independently thereafter. The lock is only needed for the initial allocation read.

**Why file lock over in-memory lock:** The two pipelines are separate OS processes (`python -m agents.sports` and the general pipeline). In-memory locks (`threading.Lock`, `multiprocessing.Lock`) do NOT work across independent processes started in separate terminal windows. `filelock.FileLock` uses OS-level `fcntl` (POSIX) or `msvcrt` (Windows) which works across unrelated processes on the same machine.

**Why NOT Redis/database:** Unnecessary dependency. The coordination is one-time at startup — the sports pipeline reads its fraction, the general pipeline reads the remainder. After allocation, each manages its own budget independently.

**Example:**
```python
# In agents/application/budget.py — add BudgetCoordinator class

import json
import os
import time
from filelock import FileLock, Timeout

def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class BudgetCoordinator:
    """Cross-process budget allocation using OS-level file lock.

    Two pipelines (sports + general) call allocate_sports_budget() at startup.
    The first caller writes the allocation; the second reads it.
    After startup, each pipeline tracks spending independently via SessionBudgetManager.

    File lock prevents race condition during concurrent startup.
    """

    def __init__(self) -> None:
        self.sports_fraction = _env_float("SPORTS_BUDGET_FRACTION", 0.30)
        self.min_wallet_usd = _env_float("SPORTS_MIN_WALLET_USD", 50.0)
        self.lock_timeout = _env_float("SPORTS_BUDGET_LOCK_TIMEOUT_SECONDS", 5.0)
        self.lock_path = os.getenv("SPORTS_BUDGET_LOCK_PATH", "/tmp/polyagents_budget.lock")
        self.state_path = os.getenv("SPORTS_BUDGET_FILE_PATH", "/tmp/polyagents_budget.json")
        self._per_sport_caps = self._load_sport_caps()

    def allocate_sports_budget(self, total_wallet_usdc: float) -> float:
        """Atomically claim the sports fraction of the wallet.

        Returns the USDC amount allocated to sports pipeline.
        Raises RuntimeError if lock cannot be acquired within timeout.
        """
        sports_budget = max(0.0, total_wallet_usdc * self.sports_fraction)
        lock = FileLock(self.lock_path)
        try:
            with lock.acquire(timeout=self.lock_timeout):
                state = self._read_state()
                state["sports_allocated"] = sports_budget
                state["general_allocated"] = total_wallet_usdc - sports_budget
                state["timestamp"] = time.time()
                self._write_state(state)
        except Timeout:
            raise RuntimeError(
                f"[budget] event=lock_timeout path={self.lock_path} "
                f"timeout={self.lock_timeout}s — is another pipeline holding the lock?"
            )
        print(
            f"[budget] event=sports_allocated total={total_wallet_usdc:.2f} "
            f"sports={sports_budget:.2f} fraction={self.sports_fraction}"
        )
        return sports_budget

    def get_sport_cap(self, league: str, sports_total: float) -> float:
        """Return the USDC cap for a specific league.

        Configured leagues use their fraction. Unconfigured leagues share remainder equally.
        """
        cap_fraction = self._per_sport_caps.get(league.lower())
        if cap_fraction is not None:
            return sports_total * cap_fraction
        # Unconfigured leagues share the uncapped remainder equally
        configured_fraction = sum(self._per_sport_caps.values())
        unconfigured_count = max(1, 9 - len(self._per_sport_caps))  # 9 total sports
        remaining = max(0.0, 1.0 - configured_fraction)
        return sports_total * (remaining / unconfigured_count)

    def is_above_safety_floor(self, wallet_usdc: float) -> bool:
        """Return True if wallet is above the minimum sports trading threshold."""
        return wallet_usdc >= self.min_wallet_usd

    def _load_sport_caps(self) -> dict[str, float]:
        """Parse SPORTS_CAP_{LEAGUE} env vars into a dict."""
        leagues = ["nfl", "nba", "mlb", "nhl", "cfb", "cbb", "soccer", "cs2", "tennis"]
        caps = {}
        for league in leagues:
            env_key = f"SPORTS_CAP_{league.upper()}"
            val = os.getenv(env_key)
            if val is not None:
                try:
                    caps[league] = float(val)
                except (TypeError, ValueError):
                    pass
        return caps

    def _read_state(self) -> dict:
        try:
            with open(self.state_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write_state(self, state: dict) -> None:
        with open(self.state_path, "w") as f:
            json.dump(state, f)
```

### Pattern 5: Sports Pipeline Entry Point

**What:** `agents/sports.py` is a minimal idle-loop entry point that wires together `SportsWSConnector`, `SlugMarketIndex`, `SportsDataConnector`, and `BudgetCoordinator`.

**Example:**
```python
# agents/sports.py
"""Sports pipeline entry point.

Run as: python -m agents.sports

Separate process from general pipeline. Crash here does not affect general pipeline.
"""
import os
import time
from agents.connectors.sports_ws import SportsWSConnector
from agents.polymarket.gamma import GammaMarketClient
from agents.connectors.sports_data import SportsDataConnector
from agents.application.budget import BudgetCoordinator, SessionBudgetManager

def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def main() -> None:
    execute_trades = _env_bool("SPORTS_EXECUTE_TRADES", None)
    if execute_trades is None:
        execute_trades = _env_bool("EXECUTE_TRADES", False)

    print(f"[sports] event=startup execute_trades={execute_trades}")

    gamma = GammaMarketClient()
    ws = SportsWSConnector()
    stats = SportsDataConnector()
    coordinator = BudgetCoordinator()

    # Budget allocation happens at startup — one-time
    # (wallet balance fetch happens here in Phase 3+)

    # Start WS connector in background thread
    import threading
    ws_thread = threading.Thread(target=ws.run, daemon=True, name="sports-ws")
    ws_thread.start()

    print("[sports] event=idle_loop_start")
    while True:
        # Phase 3+ will add market discovery and trade evaluation here
        time.sleep(30)


if __name__ == "__main__":
    main()
```

### Anti-Patterns to Avoid

- **Reusing the Chroma RAG connector for sports market discovery:** Explicitly decided against; use Gamma slug lookup only. `PolymarketRAG` imports langchain/openai and adds heavy deps to the sports process.
- **Creating a new httpx.Client in `sports_data.py`:** Instead, reuse `GammaMarketClient`'s existing client pattern (timeout config from env vars, connection pooling).
- **Threading locks for cross-process coordination:** `threading.Lock` is useless across separate OS processes. Only `filelock.FileLock` works here.
- **Hardcoding API-Sports league IDs:** These must be discoverable at runtime or validated against live API. The mapping table in `_league_id()` is a starting point only.
- **Calling `/events` without `active=True&closed=False`:** Without these filters, the slug table will be polluted with resolved/archived markets.
- **Assuming WS slug == Gamma event slug:** The WS uses team abbreviations (`lac`, `buf`); Gamma slugs may use full names. Always implement the fallback.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TTL-based in-memory cache | Custom dict with timestamp tracking | `cachetools.TTLCache` (already in requirements) | Thread-safe, automatic eviction, well-tested |
| Cross-process lock | Custom file-write lock | `filelock.FileLock` (already in requirements) | OS-level fcntl; survives SIGKILL; handles stale locks |
| HTTP retries | Custom retry loop with sleep | `tenacity` (already in requirements) | Configurable backoff, exception filtering, max attempts |
| HTTP client | `requests` or `urllib` | `httpx.Client` | Already used by `GammaMarketClient`; consistent connection pooling |
| env float parsing | Inline `float(os.getenv(...))` with no guard | `_env_float()` helper (inline, per sports_ws.py pattern) | Avoids heavy executor.py import chain with langchain deps |

**Key insight:** All coordination and caching primitives needed are already installed in `requirements.txt`. No new pip dependencies required for Phase 2.

---

## Common Pitfalls

### Pitfall 1: WS Slug Does Not Match Gamma Slug
**What goes wrong:** `lookup_markets_by_slug("nfl-lac-buf-2025-01-26")` returns 404 because Gamma stores it as `nfl-los-angeles-chargers-buffalo-bills-2025-01-26`.
**Why it happens:** WS uses team abbreviations; Gamma uses full names or different formats.
**How to avoid:** Always implement the fallback substring search. Log slug mismatches to build a mapping correction corpus during dev.
**Warning signs:** High unmapped-slug rate during testing with live WS data.

### Pitfall 2: Slug Table Built from Closed Markets
**What goes wrong:** Slug table maps slugs to market IDs that are already closed/resolved. Subsequent trades fail with "market not active" errors.
**Why it happens:** Forgetting `active=True&closed=False` in the Gamma API query.
**How to avoid:** Always include `active=True, closed=False, archived=False` when querying `/events` for the slug table.
**Warning signs:** Markets fetched from slug table have `active: false` or `closed: true` in their Pydantic model.

### Pitfall 3: API-Sports Rate Limit Exhaustion (Free Tier)
**What goes wrong:** The 100 req/day limit is exhausted by mid-morning if stats are fetched per-game without caching.
**Why it happens:** 9 sports x multiple teams x multiple endpoints = many calls without caching.
**How to avoid:** The 24h TTL cache for stats is critical. For dev/test, use `SPORTS_REQUIRE_STATS=""` (empty) to skip stats fetching. Pre-warm the cache for known team matchups.
**Warning signs:** `429 Too Many Requests` from api-sports.io before noon.

### Pitfall 4: Lock File Left Stale After Crash
**What goes wrong:** If a pipeline crashes while holding the `filelock`, the next startup hangs waiting for lock acquisition.
**Why it happens:** `filelock.FileLock` uses OS-level advisory locks which ARE automatically released on process death (unlike pid-file locks). This is a non-issue for `filelock` specifically.
**How to avoid:** Use `filelock.FileLock` (not `SoftFileLock`). The OS lock is released on process exit/crash automatically.
**Warning signs:** Startup hangs at budget allocation step — check if `lock_timeout` is too long.

### Pitfall 5: Heavy executor.py Import Chain in Sports Process
**What goes wrong:** `from agents.application.executor import Executor` imports langchain, openai, chroma — adding 5-10 second startup time and memory overhead to the sports process.
**Why it happens:** Executor is the general pipeline's LLM agent, not needed in Phase 2 sports pipeline.
**How to avoid:** Inline `_env_bool`, `_env_float`, `_env_int` helpers in new sports modules (exact pattern established in `sports_ws.py`). Do NOT import from `executor.py` in Phase 2.
**Warning signs:** Import of sports module takes >2 seconds or pulls in openai/langchain packages.

### Pitfall 6: Odds Divergence False Positives Near Market Close
**What goes wrong:** Bookmaker odds and Polymarket prices naturally diverge as games approach end — bookmakers suspend betting, but Polymarket stays open. The divergence threshold fires erroneously.
**Why it happens:** Bookmakers pull lines 15-30 minutes before game end; Polymarket doesn't.
**How to avoid:** Check `SportGameState.live` and `SportGameState.period` — only flag divergence during pre-game or early in-game windows. Suppress near end-of-game. This is Phase 3 logic but the threshold env var must be in place now.
**Warning signs:** Value-bet flags firing on obviously-decided games.

---

## Code Examples

### Gamma API Slug Lookup (verified endpoint)

```python
# Source: https://docs.polymarket.com/api-reference/events/get-event-by-slug
# Exact slug: GET https://gamma-api.polymarket.com/events/slug/{slug}
# Query parameter: GET https://gamma-api.polymarket.com/events?slug={slug}

import httpx

client = httpx.Client(timeout=8.0)

# Fast path — path param (404 on miss)
resp = client.get("https://gamma-api.polymarket.com/events/slug/nfl-lac-buf-2025-01-26")
# Returns: event dict with 'markets' list

# Fallback — query param filter
resp = client.get("https://gamma-api.polymarket.com/events", params={
    "active": True,
    "closed": False,
    "archived": False,
    "limit": 20,
})
# Filter client-side by team name substrings
```

### TTLCache with two different TTLs (verified from cachetools docs)

```python
# Source: https://pypi.org/project/cachetools/
from cachetools import TTLCache
import threading

# Stats cache: 24h TTL
_stats_cache: TTLCache = TTLCache(maxsize=500, ttl=86400)
_stats_lock = threading.Lock()

# Odds cache: 5min TTL
_odds_cache: TTLCache = TTLCache(maxsize=200, ttl=300)
_odds_lock = threading.Lock()

# Manual cache get/set (lock required for thread safety)
def get_cached(cache, lock, key):
    with lock:
        return cache.get(key)

def set_cached(cache, lock, key, value):
    with lock:
        cache[key] = value
```

### filelock cross-process lock (verified from py-filelock docs)

```python
# Source: https://py-filelock.readthedocs.io/
from filelock import FileLock, Timeout

lock = FileLock("/tmp/polyagents_budget.lock")
try:
    with lock.acquire(timeout=5.0):
        # Critical section — only one process at a time
        # Read shared budget state, write allocation
        pass
except Timeout:
    print("[budget] event=lock_timeout — another process holds the lock")
    raise
# Lock automatically released when 'with' block exits
# Lock also released if process crashes (OS-level advisory lock)
```

### BudgetCoordinator with per-sport caps

```python
# Pattern for per-sport cap parsing
import os

leagues = ["nfl", "nba", "mlb", "nhl", "cfb", "cbb", "soccer", "cs2", "tennis"]
caps = {}
for league in leagues:
    val = os.getenv(f"SPORTS_CAP_{league.upper()}")
    if val:
        try:
            caps[league] = float(val)
        except ValueError:
            pass
# caps = {"nfl": 0.4, "nba": 0.3} from SPORTS_CAP_NFL=0.4, SPORTS_CAP_NBA=0.3
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Chroma RAG for market discovery | Direct Gamma slug lookup | Eliminates embedding step; no langchain in sports process |
| Single unified trading pipeline | Separate process per pipeline | OS process boundary = crash isolation |
| In-memory dict for multi-process budget | filelock + JSON file | Cross-process safety without Redis/DB dependency |
| Polling all markets for sports | Tag-filtered + slug-indexed lookup | Fewer Gamma API calls; faster market discovery |

**Deprecated/outdated for this phase:**
- ChromaDB / PolymarketRAG: explicitly out of scope for sports market discovery
- `multiprocessing.Lock`: would require a parent process to create; not usable with independently started processes

---

## External API Selection Rationale

### For Team Stats (DATA-01, DATA-02, DATA-03): API-Sports

**Recommendation: API-Sports (api-sports.io)**

- Covers NFL, NBA, MLB, NHL, basketball (CBB), American football (CFB), soccer, hockey, MMA
- Free tier: 100 req/day per API — sufficient for development and low-volume trading
- Paid from $10/mo if higher limits needed
- Consistent REST API with standings, team stats, and H2H endpoints across all sports
- Documentation at https://api-sports.io/documentation/nfl/v1 (similar paths for other sports)

**Esports gap:** API-Sports does not cover CS2/esports. Mitigation: exclude `cs2` and `esports` from `SPORTS_REQUIRE_STATS` env var. Sports pipeline can still trade esports markets using Polymarket price + (Phase 3) LLM reasoning alone.

**Tennis gap:** API-Sports covers tennis but the free tier may be limiting. Mitigation: include `tennis` in `SPORTS_REQUIRE_STATS` only if needed.

### For Bookmaker Odds (MKT-03): The Odds API

**Recommendation: The Odds API (the-odds-api.com)**

- Covers NFL, NBA, MLB, NHL, soccer (80+ leagues), tennis ATP/WTA — aligns with most Polymarket sports
- Credit-based quota; one `h2h` market + one region = 1 credit per request
- No esports coverage — same mitigation as above
- Use `sport_key` param that maps to Polymarket league (e.g., `americanfootball_nfl`, `basketball_nba`)

### Odds Divergence Threshold Default

**Recommended default: 5% (0.05)**

Rationale: Bookmakers build in a 5-10% vig. Polymarket charges ~2% trading fees. A 5% divergence between Polymarket probability and bookmaker implied probability represents a meaningful edge that exceeds transaction costs. Values below 3% produce too many false positives (within typical bid-ask spread noise). Values above 10% are too conservative and will miss most opportunities. Configurable via `SPORTS_ODDS_DIVERGENCE_THRESHOLD`.

---

## Open Questions

1. **Gamma Slug Format Validation**
   - What we know: WS slugs use abbreviations (`nfl-lac-buf-2025-01-26`); Gamma docs show slug-based lookup exists
   - What's unclear: Does Gamma store sports events with abbreviation-style slugs or full-name slugs? Does it vary by sport?
   - Recommendation: Run a manual query against live Gamma API for a known active sports event before finalizing the lookup implementation. Add a slug normalization test that checks both formats.

2. **API-Sports League IDs**
   - What we know: API-Sports uses numeric league IDs in query params; IDs vary by sport
   - What's unclear: Exact numeric IDs for NFL, NBA (international vs US), MLB, NHL in 2025 season
   - Recommendation: Discover IDs via `GET /leagues` at startup and cache; do not hardcode. Flag IDs in code as "verify against live API" until confirmed.

3. **Gamma Tag IDs for Sports Leagues**
   - What we know: Gamma `/events` accepts `tag_id` for filtering by sport/league
   - What's unclear: What are the actual tag IDs for NFL, NBA, MLB, NHL, soccer on Gamma?
   - Recommendation: Fetch `GET /tags` at startup in `SlugMarketIndex.rebuild()` to discover current tag IDs. Build a league→tag_id mapping table dynamically.

4. **The Odds API Sport Keys**
   - What we know: Keys like `americanfootball_nfl`, `basketball_nba` exist
   - What's unclear: Keys for CFB, CBB, soccer sub-leagues that match Polymarket's coverage
   - Recommendation: Call `GET /v4/sports` (no quota cost) at startup to discover available sport keys.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.2 |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `python -m pytest tests/test_slug_index.py tests/test_sports_data.py tests/test_budget_coordinator.py -x` |
| Full suite command | `python -m pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MKT-01 | Sports market metadata tagging via `SportsMarketTag` model | unit | `python -m pytest tests/test_slug_index.py::test_market_tag_extraction -x` | ❌ Wave 0 |
| MKT-02 | Slug lookup returns market IDs; unmapped slugs go to retry queue | unit | `python -m pytest tests/test_slug_index.py::test_lookup_returns_market_ids tests/test_slug_index.py::test_unmapped_slug_queued -x` | ❌ Wave 0 |
| MKT-02 | Fallback team-name search triggered on 404 | unit | `python -m pytest tests/test_slug_index.py::test_fallback_triggered_on_404 -x` | ❌ Wave 0 |
| MKT-03 | Divergence detection returns True/False based on threshold | unit | `python -m pytest tests/test_sports_data.py::test_detect_value_bet -x` | ❌ Wave 0 |
| DATA-01 | `SportsDataConnector` initializes without error | unit | `python -m pytest tests/test_sports_data.py::test_connector_init -x` | ❌ Wave 0 |
| DATA-02 | Stats cache hit returns cached result without HTTP call | unit | `python -m pytest tests/test_sports_data.py::test_stats_cache_hit -x` | ❌ Wave 0 |
| DATA-03 | H2H returns list; empty list on API error (no raise) | unit | `python -m pytest tests/test_sports_data.py::test_h2h_returns_empty_on_error -x` | ❌ Wave 0 |
| PIPE-01 | Sports entry point imports without pulling langchain/openai | unit | `python -m pytest tests/test_sports_pipeline.py::test_no_heavy_imports -x` | ❌ Wave 0 |
| PIPE-02 | `BudgetCoordinator` allocates correct fraction | unit | `python -m pytest tests/test_budget_coordinator.py::test_allocate_sports_budget -x` | ❌ Wave 0 |
| PIPE-03 | Two `BudgetCoordinator` instances with same lock path do not deadlock; one wins | unit | `python -m pytest tests/test_budget_coordinator.py::test_lock_contention -x` | ❌ Wave 0 |
| PIPE-04 | Per-sport caps parsed from env vars correctly | unit | `python -m pytest tests/test_budget_coordinator.py::test_per_sport_caps -x` | ❌ Wave 0 |
| PIPE-05 | `SPORTS_EXECUTE_TRADES` overrides `EXECUTE_TRADES` when set | unit | `python -m pytest tests/test_sports_pipeline.py::test_dry_run_flag_override -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_slug_index.py tests/test_sports_data.py tests/test_budget_coordinator.py -x --tb=short`
- **Per wave merge:** `python -m pytest tests/ -x --tb=short`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_slug_index.py` — covers MKT-01, MKT-02
- [ ] `tests/test_sports_data.py` — covers MKT-03, DATA-01, DATA-02, DATA-03
- [ ] `tests/test_budget_coordinator.py` — covers PIPE-02, PIPE-03, PIPE-04
- [ ] `tests/test_sports_pipeline.py` — covers PIPE-01, PIPE-05
- [ ] `agents/connectors/sports_data.py` — new connector (implementation file)
- [ ] `agents/sports.py` — new entry point

---

## Sources

### Primary (HIGH confidence)
- Polymarket official docs: `GET /events/slug/{slug}` endpoint confirmed — https://docs.polymarket.com/api-reference/events/get-event-by-slug
- Polymarket official docs: Events filtering parameters (`slug`, `tag_id`, `active`, `closed`) — https://docs.polymarket.com/developers/gamma-markets-api/get-events
- filelock PyPI + readthedocs: `FileLock`, `Timeout`, `lock.acquire(timeout=N)` API — https://py-filelock.readthedocs.io/ and https://pypi.org/project/filelock/
- cachetools PyPI: `TTLCache(maxsize=N, ttl=N)` API — https://pypi.org/project/cachetools/
- Existing codebase: `GammaMarketClient` (httpx, env config), `SessionBudgetManager`, `SportsWSConnector`, slug field on `SportGameState`

### Secondary (MEDIUM confidence)
- API-Sports coverage (NFL, NBA, MLB, NHL, soccer, MMA): https://api-sports.io/ — free 100 req/day/API confirmed
- The Odds API sports coverage and endpoint structure: https://the-odds-api.com/liveapi/guides/v4/ — NFL/NBA/MLB/NHL/tennis confirmed; no esports
- BALLDONTLIE API (evaluated, not recommended): free tier only 1 sport and 5 req/min — insufficient coverage
- ESPN hidden API (evaluated, not recommended): unofficial/unsupported; not suitable for production

### Tertiary (LOW confidence — verify before implementing)
- API-Sports league IDs for specific leagues (NFL=1 etc.) — must be verified via `GET /leagues`
- The Odds API sport keys for CFB, CBB — must be verified via `GET /v4/sports`
- Gamma tag IDs for league-specific filtering — must be discovered at runtime via `GET /tags`

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in requirements.txt; APIs verified via official docs
- Architecture: HIGH — extends existing patterns (GammaMarketClient, SessionBudgetManager, connector pattern)
- Pitfalls: HIGH — slug format mismatch and import chain issues confirmed from code inspection and STATE.md
- External API IDs: LOW — league IDs and tag IDs must be discovered from live API calls

**Research date:** 2026-03-06
**Valid until:** 2026-04-06 (stable APIs; API-Sports and The Odds API pricing may change)
