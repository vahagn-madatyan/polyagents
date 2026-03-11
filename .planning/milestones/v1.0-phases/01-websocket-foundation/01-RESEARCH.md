# Phase 1: WebSocket Foundation - Research

**Researched:** 2026-03-03
**Domain:** Polymarket Sports WebSocket — Python persistent connection, normalization, watchdog
**Confidence:** HIGH (official docs confirmed, existing codebase patterns verified)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- Common base fields (score, period, elapsed, live, ended, status) plus optional sport-specific extras (possession for NFL/CFB, innings for MLB, sets for tennis)
- Single `SportGameState` Pydantic model with optional sport-specific fields — NOT per-sport subclasses
- Scores stored as raw string from WS AND parsed integers (home_score, away_score) — enables delta computation and debugging
- Primary key: `gameId` from WS; secondary lookup by `slug` (league-team1-team2-date)
- Track `last_updated` timestamp on every state change — needed for watchdog and downstream latency measurement
- On silent freeze: force reconnect AND mark all active game states as stale until refreshed by new WS data
- Freeze timeout: configurable via `SPORTS_WS_FREEZE_TIMEOUT_SECONDS` env var — default 5 minutes
- Reconnect strategy: exponential backoff with jitter (1s, 2s, 4s, 8s... up to configurable max)
- Configurable via `SPORTS_WS_LOG_LEVEL` env var with levels: `all`, `changes`, `minimal`; default `changes`
- Follow existing `print(f"[sports_ws] key=value")` pattern for machine-parseable output
- Ended game state kept in memory for configurable TTL via `SPORTS_WS_ENDED_GAME_TTL_MINUTES`
- Purge automatically after TTL expires; all game state cleared on pipeline restart

### Claude's Discretion

- Exact thread management for WS daemon thread
- Internal queue implementation details (size, blocking behavior)
- Pydantic field validators and normalization logic
- Heartbeat (ping/pong) implementation specifics

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| WS-01 | Bot connects to `wss://sports-api.polymarket.com/ws` and maintains persistent connection | Official Polymarket docs confirm endpoint, ping/pong protocol, and no-auth connection pattern |
| WS-02 | Bot automatically reconnects on disconnect with last-known state tracking | websocket-client 1.8.0 WebSocketApp on_close + reconnect loop pattern; last_updated on SportGameState enables state tracking |
| WS-03 | Bot detects silent websocket freeze (no data for configurable threshold) and forces reconnect | GitHub issue #26 on Polymarket/real-time-data-client confirms this server-side bug at 18-22 min; watchdog thread with last_message_at timestamp is the proven workaround |
| WS-04 | Bot parses and normalizes game state messages (score, period, elapsed, live, ended, status) into structured `SportGameState` objects | Official message format documented with all fields; Pydantic v2 model follows existing objects.py pattern |
| WS-05 | Bot handles sport-specific status values and period formats across all supported sports | Official status tables documented for all 9 sports; period formats vary significantly and are documented |
| WS-06 | Bot detects period/quarter transitions and triggers trade re-evaluation at each transition | Previous period stored in state; compare on_message to detect transitions and emit callback |
| WS-07 | Bot handles game edge cases (overtime, rain delays, forfeits, suspensions) with configurable trade rules | Status values enumerated — Suspended/Delayed/Forfeit/Postponed/Canceled are the edge-case statuses; configurable halt-trading rules via env var |
</phase_requirements>

---

## Summary

The Polymarket sports WebSocket endpoint (`wss://sports-api.polymarket.com/ws`) requires no authentication, sends JSON game-state messages automatically for all active sports events, and uses a server-initiated ping/pong keepalive every 5 seconds. The client must respond with `pong` within 10 seconds or the connection closes. Message format is fully documented with sport-specific status and period values for all 9 supported sports.

A known server-side bug (GitHub issue #26, opened December 2025, still open as of research date) causes the data stream to silently stop after 18-22 minutes even though the connection remains OPEN and ping/pong succeeds. This is confirmed behavior independent of client library or implementation language. The mandated watchdog timeout of 5 minutes (configurable via `SPORTS_WS_FREEZE_TIMEOUT_SECONDS`) is the appropriate response.

The project already has `websocket-client==1.8.0` and `websockets==12.0` in requirements.txt. The preferred library for this use case is `websocket-client` (synchronous, daemon-thread compatible, `WebSocketApp` API), which fits the existing connector pattern and avoids the asyncio-incompatibility of the project's synchronous codebase. All new code follows established patterns from `agents/connectors/`, `agents/utils/objects.py`, and uses `_env_bool`/`_env_int`/`_env_float` helpers from `agents/application/executor.py`.

**Primary recommendation:** Build `agents/connectors/sports_ws.py` using `websocket.WebSocketApp` in a daemon thread with an external reconnect loop, a `threading.Queue` for message delivery, and a watchdog `threading.Timer` (or periodic check) that fires on `SPORTS_WS_FREEZE_TIMEOUT_SECONDS` of silence to force reconnect and mark all game states stale.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| websocket-client | 1.8.0 | Synchronous WebSocket client with `WebSocketApp` | Already in requirements.txt; synchronous threading model compatible with existing codebase; direct ping/pong string handling |
| pydantic | 2.8.2 | `SportGameState` model validation and parsing | Already used for `SimpleMarket`, `SimpleEvent`, `CandidateTrade`; enforces types, provides `.model_dump()` |
| threading (stdlib) | 3.12 | Daemon thread for WS run loop; `threading.Timer` for watchdog; `threading.Lock` for state dict | No additional install; matches existing connector pattern |
| queue (stdlib) | 3.12 | Thread-safe message queue between WS callback and consumer | No additional install; standard producer-consumer between WS thread and caller |
| time / datetime (stdlib) | 3.12 | `last_message_at` timestamp tracking; TTL expiry for ended games | No additional install |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| websockets | 12.0 | Async WebSocket alternative | Already in requirements.txt but NOT for this phase — the sync codebase avoids asyncio; listed only for awareness |
| backoff | 2.2.1 | Exponential backoff decorator | Already in requirements.txt; can be used for retry sleep calculation, but manual backoff loop is simpler and sufficient for this use case |
| python-dotenv | 1.0.1 | Load env vars in `__init__` | Already used everywhere — follow same pattern |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| websocket-client | websockets (asyncio) | websockets is asyncio-only, incompatible with existing synchronous codebase; websocket-client works fine in threads |
| Manual backoff loop | `backoff` library | backoff library is elegant for decorators but manual loop gives direct control over reconnect cycle needed for watchdog integration |
| threading.Queue | asyncio.Queue | asyncio.Queue not usable from sync threads; threading.Queue is the correct choice |

**Installation:** No new packages needed — `websocket-client==1.8.0`, `pydantic==2.8.2`, `backoff==2.2.1`, `python-dotenv==1.0.1` already in requirements.txt.

---

## Architecture Patterns

### Recommended Project Structure

```
agents/
├── connectors/
│   └── sports_ws.py        # New: WebSocket connector class
├── utils/
│   └── objects.py          # Extend: Add SportGameState model
.env.example                # Extend: Add 3 new env vars
tests/
└── test_sports_ws.py       # New: Unit tests (no network required)
```

### Pattern 1: WebSocketApp Daemon Thread with External Reconnect Loop

**What:** `WebSocketApp` runs in a daemon thread via `run_forever()`. An external reconnect loop in the main connector thread watches for disconnection and restarts with exponential backoff. The watchdog fires separately.

**When to use:** Always — this is the only viable pattern for synchronous Python with the existing codebase.

**Why not recursive `on_close`:** Calling `run_forever()` from inside `on_close` can deadlock or cause stack overflow on rapid reconnect cycles. External loop is stable.

```python
# Source: websocket-client 1.8.0 threading docs + production pattern
import websocket
import threading
import queue
import time
import json
import random

class SportsWSConnector:
    WS_URL = "wss://sports-api.polymarket.com/ws"

    def __init__(self):
        self._message_queue: queue.Queue = queue.Queue(maxsize=1000)
        self._game_states: dict[int, SportGameState] = {}
        self._state_lock = threading.Lock()
        self._last_message_at: float = 0.0
        self._ws_app: websocket.WebSocketApp | None = None
        self._running = False
        self._reconnect_attempt = 0
        self._watchdog_timer: threading.Timer | None = None

        # Env config (loaded in __init__ following existing pattern)
        self.freeze_timeout = _env_int("SPORTS_WS_FREEZE_TIMEOUT_SECONDS", 300)
        self.log_level = os.getenv("SPORTS_WS_LOG_LEVEL", "changes")
        self.ended_game_ttl_minutes = _env_int("SPORTS_WS_ENDED_GAME_TTL_MINUTES", 60)

    def _on_message(self, ws, raw):
        if raw == "ping":
            ws.send("pong")
            return  # Ping does NOT reset watchdog — only data messages do
        self._last_message_at = time.monotonic()
        self._reset_watchdog()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        self._process_game_state(data)

    def _on_close(self, ws, code, msg):
        print(f"[sports_ws] event=disconnected code={code}")
        # reconnect loop in run() handles restart

    def run(self):
        self._running = True
        while self._running:
            self._ws_app = websocket.WebSocketApp(
                self.WS_URL,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_open=self._on_open,
            )
            t = threading.Thread(
                target=self._ws_app.run_forever,
                kwargs={"ping_interval": 0, "ping_timeout": None},
                # ping_interval=0 disables library-level ping — server handles it
                daemon=True,
            )
            t.start()
            t.join()  # blocks until WS thread exits (disconnect or error)
            if not self._running:
                break
            self._schedule_reconnect()

    def _schedule_reconnect(self):
        base = min(2 ** self._reconnect_attempt, 60)
        jitter = random.uniform(0, base * 0.25)
        delay = base + jitter
        self._reconnect_attempt += 1
        print(f"[sports_ws] event=reconnect_scheduled delay={delay:.1f}s attempt={self._reconnect_attempt}")
        time.sleep(delay)
```

### Pattern 2: Watchdog Timer — Data Freeze Detection

**What:** A `threading.Timer` resets every time a non-ping message arrives. If it fires, the connection is silently frozen. Force reconnect and mark all game states stale.

**When to use:** Always active — this is the defense against the known Polymarket server-side freeze bug.

**Critical:** Ping/pong messages do NOT reset the watchdog. Only actual game data resets it. This matches the known failure mode where ping/pong succeeds but data stops.

```python
# Source: confirmed freeze behavior from GitHub issue #26
def _reset_watchdog(self):
    if self._watchdog_timer is not None:
        self._watchdog_timer.cancel()
    self._watchdog_timer = threading.Timer(
        self.freeze_timeout, self._on_freeze_detected
    )
    self._watchdog_timer.daemon = True
    self._watchdog_timer.start()

def _on_freeze_detected(self):
    print(f"[sports_ws] event=freeze_detected timeout={self.freeze_timeout}s")
    with self._state_lock:
        for state in self._game_states.values():
            state.stale = True
    # Force disconnect — run() loop will reconnect with backoff
    if self._ws_app:
        self._ws_app.close()
```

### Pattern 3: SportGameState Pydantic Model

**What:** Single model with all fields. Optional sport-specific fields default to None. Score parsing extracts integers from "3-16" string format.

**When to use:** `objects.py` — follows existing `SimpleMarket`/`SimpleEvent` style exactly.

```python
# Source: Pydantic v2.8.2 docs + existing objects.py patterns
from pydantic import BaseModel, Field, field_validator
from typing import Optional
import time

class SportGameState(BaseModel):
    # Core identity
    game_id: int
    league: str                      # nfl, nba, mlb, nhl, cfb, cbb, soccer, cs2, tennis
    slug: str                        # {league}-{team1}-{team2}-{date}
    home_team: str
    away_team: str

    # Core state (always present)
    status: str                      # sport-specific status string (see status tables)
    score_raw: str                   # raw string e.g. "3-16"
    home_score: Optional[int] = None # parsed from score_raw
    away_score: Optional[int] = None # parsed from score_raw
    period: str                      # "Q4", "1H", "End 5", "2/3", "Set 2"
    live: bool
    ended: bool

    # Optional fields
    elapsed: Optional[str] = None    # time within period, sport-specific
    finished_timestamp: Optional[str] = None  # ISO 8601 when ended=True

    # Sport-specific extras
    possession: Optional[str] = None  # NFL/CFB only ("turn" field from WS)
    # (innings for MLB derived from period; sets for tennis derived from period)

    # Lifecycle tracking
    last_updated: float = Field(default_factory=time.monotonic)
    stale: bool = False              # True when watchdog fires; cleared on next real data

    @field_validator("home_score", "away_score", mode="before")
    @classmethod
    def parse_score_field(cls, v):
        # Individual score values parsed by model constructor, not validator
        return v

    class Config:
        # Allow mutation for in-place state updates
        frozen = False
```

### Pattern 4: Score Parsing

**What:** Score string "3-16" is split on "-" to extract home/away integers. Edge cases include "0-0", overtime scores, esports "000-000|2-0|Bo3" format.

```python
def _parse_score(score_raw: str) -> tuple[Optional[int], Optional[int]]:
    """Parse 'home-away' score string into integer pair.

    Handles:
      - Standard: "3-16" -> (3, 16)
      - Esports compound: "000-000|2-0|Bo3" -> use part before first '|'
      - Unknown format: return (None, None) and log warning
    """
    if not score_raw:
        return None, None
    # For esports compound scores, take only the series score portion
    segment = score_raw.split("|")[0] if "|" in score_raw else score_raw
    # But for esports we actually want the series score, which is the middle
    if "|" in score_raw:
        parts = score_raw.split("|")
        if len(parts) >= 2:
            segment = parts[1]  # "2-0" in "000-000|2-0|Bo3"
    try:
        home_str, away_str = segment.split("-", 1)
        return int(home_str), int(away_str)
    except (ValueError, AttributeError):
        return None, None
```

### Pattern 5: Period Transition Detection

**What:** On each message, compare incoming period to stored previous period. If different, emit a transition event.

```python
def _process_game_state(self, data: dict):
    game_id = data.get("gameId")
    new_period = data.get("period", "")

    with self._state_lock:
        existing = self._game_states.get(game_id)
        old_period = existing.period if existing else None

    new_state = self._build_game_state(data)

    with self._state_lock:
        self._game_states[game_id] = new_state

    # Period transition detection
    if existing and old_period and old_period != new_period:
        self._on_period_transition(new_state, old_period, new_period)

def _on_period_transition(self, state: SportGameState, old: str, new: str):
    print(f"[sports_ws] event=period_transition game_id={state.game_id} from={old} to={new}")
    # Emit to queue or callback for downstream trade re-evaluation
    self._message_queue.put({"type": "period_transition", "state": state})
```

### Pattern 6: Edge-Case Status Handling

**What:** When status indicates game is suspended, delayed, or otherwise non-tradeable, halt new orders. Configurable per edge-case category.

**Status values requiring trade halt by default:**
- All sports: `Suspended`, `Postponed`, `Canceled`, `Forfeit`
- MLB only: `Delayed` (rain delay)
- Soccer only: `PenaltyShootout` (configurable — high volatility)

```python
# Edge-case statuses that halt trading (configurable via env)
HALT_STATUSES = {
    "Suspended", "Postponed", "Canceled", "Forfeit",
    "Delayed",         # MLB rain delay
    "NotNecessary",    # game cancelled before start
    "Awarded",         # soccer match awarded to team
}

def should_halt_trading(state: SportGameState) -> bool:
    return state.status in HALT_STATUSES or state.stale
```

### Anti-Patterns to Avoid

- **Calling `run_forever()` from inside `on_close` callback:** Causes deadlock on rapid reconnect cycles. Use external reconnect loop.
- **Resetting watchdog on ping/pong only:** The known freeze bug keeps ping/pong healthy while data stops. Only reset watchdog on actual game data messages.
- **Storing game states without `threading.Lock`:** `on_message` runs on WS thread; consumer runs on caller thread. Always use `_state_lock`.
- **Using `asyncio` for this connector:** `websocket-client` is not compatible with asyncio; existing codebase is synchronous — keep it that way.
- **Setting `ping_interval` on `run_forever()`:** The server sends pings; do not send additional client-side pings. Set `ping_interval=0` to disable library-level pings and handle server pings manually in `on_message`.
- **Parsing esports scores naively:** "000-000|2-0|Bo3" is not a simple "home-away" string. Extract the series score from the middle segment.
- **Treating `ended=True` as immediate purge:** Ended games must be retained for `SPORTS_WS_ENDED_GAME_TTL_MINUTES` for downstream settlement processing.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON parsing with type safety | Custom dict parsing | Pydantic `SportGameState` model | Handles missing fields, type coercion, validation errors gracefully |
| Env var parsing with defaults | `os.getenv()` + manual cast everywhere | `_env_int`, `_env_bool`, `_env_float` from executor.py | Already implemented, handles None/empty/invalid values consistently |
| Thread-safe state store | Custom locking scheme | `threading.Lock` + dict | Sufficient for single-writer (WS thread) + multiple-reader pattern |
| Score parsing edge cases | Regex or split-every-format | `_parse_score()` function with format enum | Esports compound format, overtime scores, tie scores all need explicit handling |
| Backoff with jitter | Sleep fixed intervals | `min(2**attempt, max_delay) + random.uniform(0, base*0.25)` | Prevents thundering herd if server restarts during high-concurrency reconnect |

**Key insight:** The WS message format looks simple but sport-specific edge cases (esports compound scores, soccer "Awarded" status, NHL "F/SO") will break naive implementations. Handle each league's quirks explicitly.

---

## Common Pitfalls

### Pitfall 1: Watchdog Reset on Ping (NOT on Data)

**What goes wrong:** Developer resets `last_message_at` on every raw message including "ping". Watchdog never fires even during data freeze because server pings continue every 5 seconds.

**Why it happens:** The raw `on_message` handler receives both "ping" strings and JSON game data. Treating them identically defeats the watchdog.

**How to avoid:** Check `if raw == "ping": ws.send("pong"); return` BEFORE updating `last_message_at`. Only update the timestamp after confirming the message is JSON game data.

**Warning signs:** Bot runs for hours without watchdog firing despite no game state updates.

---

### Pitfall 2: Library-Level Ping Conflict

**What goes wrong:** Setting `ping_interval=60` on `run_forever()` causes the library to send client-initiated pings in addition to responding to server pings, leading to unexpected connection behavior.

**Why it happens:** `websocket-client` sends its own pings when `ping_interval > 0`. The Polymarket server sends pings every 5 seconds. Two separate ping cycles can confuse the server's pong tracking.

**How to avoid:** Set `ping_interval=0` (or omit it) on `run_forever()`. Handle server "ping" messages manually in `on_message`.

**Warning signs:** Frequent `ping_timeout` disconnections despite healthy network.

---

### Pitfall 3: Reconnect Loop Without Backoff Reset

**What goes wrong:** Reconnect attempt counter never resets after a successful stable connection, so after a brief disruption during a long-running session, the bot waits 60 seconds between reconnects (hitting max backoff) even though the service is healthy.

**Why it happens:** `_reconnect_attempt` increments on each failure but the code never resets it on successful stable connection.

**How to avoid:** Reset `_reconnect_attempt = 0` after the WS thread has been alive for a minimum stable duration (e.g., 60 seconds). Track `_connection_started_at` and reset counter in a condition inside the `run()` loop.

**Warning signs:** Post-brief-disconnect reconnect takes 60+ seconds even when server is healthy.

---

### Pitfall 4: State Lock Held During Queue Put

**What goes wrong:** Holding `_state_lock` while calling `self._message_queue.put(...)` can deadlock if the queue consumer holds another lock the WS thread needs.

**Why it happens:** `queue.Queue.put()` can block if the queue is full. Holding a lock while blocking on a full queue is a deadlock recipe.

**How to avoid:** Update state dict under `_state_lock`, release the lock, THEN put to queue.

**Warning signs:** Bot hangs silently under high message volume.

---

### Pitfall 5: Esports Score Parsing

**What goes wrong:** `score_raw.split("-")` on "000-000|2-0|Bo3" returns `["000", "000|2", "0|Bo3"]` which crashes `int()` conversion.

**Why it happens:** Esports compound scores use both "-" and "|" as delimiters. The raw score encodes map scores AND series scores in one string.

**How to avoid:** Detect "|" in score_raw first. For esports, extract the series portion ("2-0" from "000-000|2-0|Bo3") as the meaningful score for trading decisions.

**Warning signs:** `ValueError: invalid literal for int()` in score parsing during esports events.

---

### Pitfall 6: Ended Game Immediate Purge

**What goes wrong:** Game state is deleted immediately when `ended=True`. Downstream settlement logic (Phase 3+) can't find the game state.

**Why it happens:** Natural cleanup instinct — ended games seem done.

**How to avoid:** Set `ended_at = datetime.utcnow()` when first seeing `ended=True`. Run a periodic cleanup that only purges states where `datetime.utcnow() - ended_at > timedelta(minutes=SPORTS_WS_ENDED_GAME_TTL_MINUTES)`.

**Warning signs:** KeyError when downstream logic looks up just-ended game.

---

## Code Examples

### Connecting and Handling Pings

```python
# Source: https://docs.polymarket.com/developers/sports-websocket/quickstart
# Confirmed from official Polymarket documentation

import websocket
import json

def on_message(ws, raw):
    if raw == "ping":
        ws.send("pong")
        return
    data = json.loads(raw)
    # data is a sport_result dict

def on_open(ws):
    print("[sports_ws] event=connected")
    # No subscription message required — data flows immediately

ws = websocket.WebSocketApp(
    "wss://sports-api.polymarket.com/ws",
    on_message=on_message,
    on_open=on_open,
)
# ping_interval=0: disable library pings (server sends its own)
ws.run_forever(ping_interval=0)
```

### Full Message Structure — NFL Example

```json
{
  "gameId": 19439,
  "leagueAbbreviation": "nfl",
  "slug": "nfl-lac-buf-2025-01-26",
  "homeTeam": "LAC",
  "awayTeam": "BUF",
  "status": "InProgress",
  "score": "3-16",
  "period": "Q4",
  "elapsed": "5:18",
  "live": true,
  "ended": false,
  "turn": "lac"
}
```

### Full Message Structure — Esports Example

```json
{
  "gameId": 1317359,
  "leagueAbbreviation": "cs2",
  "slug": "cs2-arcred-the-glecs-2025-07-20",
  "homeTeam": "ARCRED",
  "awayTeam": "The glecs",
  "status": "finished",
  "score": "000-000|2-0|Bo3",
  "period": "2/3",
  "live": false,
  "ended": true,
  "finished_timestamp": "2025-07-20T18:30:00.000Z"
}
```

### Exponential Backoff with Jitter

```python
# Source: Production pattern — confirmed correct by backoff library docs
import random
import time

def reconnect_delay(attempt: int, base: float = 1.0, max_delay: float = 60.0) -> float:
    """Returns delay in seconds for reconnect attempt N (0-indexed)."""
    exp = min(base * (2 ** attempt), max_delay)
    jitter = random.uniform(0, exp * 0.25)
    return exp + jitter

# Sequence: ~1.0s, ~2.1s, ~4.3s, ~8.6s, ~17s, ~34s, ~60s (cap), ...
```

### SportGameState Construction from WS Dict

```python
def _build_game_state(self, data: dict) -> SportGameState:
    score_raw = data.get("score", "")
    home_score, away_score = _parse_score(score_raw)
    return SportGameState(
        game_id=data["gameId"],
        league=data.get("leagueAbbreviation", "").lower(),
        slug=data.get("slug", ""),
        home_team=data.get("homeTeam", ""),
        away_team=data.get("awayTeam", ""),
        status=data.get("status", ""),
        score_raw=score_raw,
        home_score=home_score,
        away_score=away_score,
        period=data.get("period", ""),
        live=bool(data.get("live", False)),
        ended=bool(data.get("ended", False)),
        elapsed=data.get("elapsed"),
        finished_timestamp=data.get("finished_timestamp"),
        possession=data.get("turn"),  # NFL/CFB only
        last_updated=time.monotonic(),
        stale=False,
    )
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pydantic v1 `Optional[X]` implicit None default | Pydantic v2 requires explicit `Optional[X] = None` | Pydantic v2 (2023) | Must explicitly declare all optional fields with `= None` default |
| `websocket-client` 0.x callback style | `WebSocketApp` with named callbacks | 0.5+ | `on_ping` and `on_pong` are separate from `on_message` in newer versions |
| Trust ping/pong as liveness signal | Data-layer watchdog required | Dec 2025 (issue #26) | Cannot trust connection OPEN status; must track last data message time |

**Deprecated/outdated:**
- `ws.run_forever(reconnect=5)` with `rel` dispatcher: Requires installing `rel` package; overkill and another dependency for this use case. Manual reconnect loop is simpler and more controllable.
- Per-sport Pydantic subclasses: Decided against by user — single model with optional fields chosen instead.

---

## Open Questions

1. **MLB "Top/Bot" half-inning format**
   - What we know: Period for MLB is documented as "End 1", "End 2", ... "End 9". The word "half" (top/bottom inning) is not explicitly documented for the `period` field.
   - What's unclear: Does the MLB period field include "Top 3" / "Bot 3" style values for mid-inning state, or only "End N" at inning completion?
   - Recommendation: Accept any `period` string for MLB; do NOT try to parse it as a fixed enum. Store raw and let downstream use it. Log any unseen period values in `changes` log level for discovery.

2. **NHL "F/SO" shootout period format**
   - What we know: "F/SO" (Final/Shootout) appears in status table for NHL. Period value during a shootout is not documented.
   - What's unclear: Does `period` show "SO" or continue from "OT"? Does the score update during shootout or only on resolution?
   - Recommendation: Treat any NHL game with `status == "F/SO"` or `period` containing "SO" as an edge case. Mark as stale for trading purposes (same as Suspended) until confirmed resolution.

3. **Tennis score format**
   - What we know: Period is "Set 1", "Set 2", etc. Score format is not shown in an example — unlike NFL "3-16" it might include game scores within sets.
   - What's unclear: Exact score string format for tennis (e.g., "6-4,3-6,2-1" or just sets won "1-1").
   - Recommendation: Store tennis `score_raw` verbatim; attempt simple home-away split and fall back gracefully to `None` integers. Log unseen formats.

4. **CBB/CFB "Half" vs quarter periods**
   - What we know: CFB uses quarters (Q1-Q4) same as NFL. CBB (college basketball) likely uses halves like soccer (1H/2H) since college basketball has halves, not quarters.
   - What's unclear: Documentation does not show explicit CBB period examples. NFL/NBA Q1-Q4 is confirmed; CBB might be different.
   - Recommendation: Accept all period strings as raw. Period transition detection compares string equality regardless of format — no assumptions needed.

---

## Validation Architecture

> nyquist_validation is enabled in .planning/config.json.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.2 (already in requirements.txt) |
| Config file | None — no pytest.ini found; run from project root |
| Quick run command | `pytest tests/test_sports_ws.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WS-01 | `SportGameState` constructed from valid WS dict | unit | `pytest tests/test_sports_ws.py::test_build_game_state_nfl -x` | ❌ Wave 0 |
| WS-01 | Ping message triggers pong (no state change) | unit | `pytest tests/test_sports_ws.py::test_ping_message_handled -x` | ❌ Wave 0 |
| WS-02 | Reconnect attempt counter increments and delay grows | unit | `pytest tests/test_sports_ws.py::test_reconnect_backoff_sequence -x` | ❌ Wave 0 |
| WS-02 | Last game state preserved in `_game_states` after disconnect | unit | `pytest tests/test_sports_ws.py::test_state_preserved_on_disconnect -x` | ❌ Wave 0 |
| WS-03 | Watchdog fires after timeout when no data received | unit | `pytest tests/test_sports_ws.py::test_watchdog_fires_on_freeze -x` | ❌ Wave 0 |
| WS-03 | Watchdog does NOT fire if data arrives within timeout | unit | `pytest tests/test_sports_ws.py::test_watchdog_reset_on_data -x` | ❌ Wave 0 |
| WS-03 | All game states marked stale when watchdog fires | unit | `pytest tests/test_sports_ws.py::test_watchdog_marks_states_stale -x` | ❌ Wave 0 |
| WS-04 | `SportGameState` fields parsed correctly for NFL, NBA, MLB, soccer, esports, tennis | unit | `pytest tests/test_sports_ws.py::test_parse_all_sports -x` | ❌ Wave 0 |
| WS-04 | Score "3-16" parsed to home_score=3, away_score=16 | unit | `pytest tests/test_sports_ws.py::test_parse_score_standard -x` | ❌ Wave 0 |
| WS-04 | Esports "000-000|2-0|Bo3" parsed to home_score=2, away_score=0 | unit | `pytest tests/test_sports_ws.py::test_parse_score_esports -x` | ❌ Wave 0 |
| WS-05 | Edge-case status values (Suspended, Forfeit, Delayed) recognized and halt trading | unit | `pytest tests/test_sports_ws.py::test_edge_case_statuses -x` | ❌ Wave 0 |
| WS-06 | Period transition from Q3→Q4 emits period_transition event | unit | `pytest tests/test_sports_ws.py::test_period_transition_detected -x` | ❌ Wave 0 |
| WS-06 | No event emitted when period unchanged between messages | unit | `pytest tests/test_sports_ws.py::test_no_false_period_transition -x` | ❌ Wave 0 |
| WS-07 | `should_halt_trading()` returns True for Suspended/Forfeit/Delayed/Canceled | unit | `pytest tests/test_sports_ws.py::test_halt_trading_statuses -x` | ❌ Wave 0 |
| WS-07 | `should_halt_trading()` returns False for InProgress | unit | `pytest tests/test_sports_ws.py::test_trading_allowed_inprogress -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_sports_ws.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_sports_ws.py` — covers all WS-01 through WS-07 requirements; no network calls needed (all tests use static dicts and mock WS objects)
- [ ] No pytest.ini or conftest.py needed — project runs pytest from root without config

---

## WebSocket Message Reference

### All Sport Status Values (from official Polymarket docs)

| Sport | Status Values |
|-------|---------------|
| NFL, NHL, NBA, CBB, CFB | `Scheduled`, `InProgress`, `Final`, `F/OT`, `F/SO` (NHL only), `Suspended`, `Postponed`, `Delayed`, `Canceled`, `Forfeit`, `NotNecessary` |
| MLB | `Scheduled`, `InProgress`, `Final`, `Suspended`, `Delayed`, `Postponed`, `Canceled`, `Forfeit`, `NotNecessary` |
| Soccer | `Scheduled`, `InProgress`, `Break`, `Suspended`, `PenaltyShootout`, `Final`, `Awarded`, `Postponed`, `Canceled` |
| Esports | `not_started`, `running`, `finished`, `postponed`, `canceled` |
| Tennis | `scheduled`, `inprogress`, `suspended`, `finished`, `postponed`, `cancelled` |

**Note:** Status value casing is inconsistent across sports. NFL/NBA use PascalCase; esports/tennis use lowercase. Normalization should preserve raw status and provide a `status_normalized` lowercase comparison field if needed downstream.

### All Sport Period Values (from official Polymarket docs)

| Sport | Period Format |
|-------|---------------|
| NFL, NBA, CFB (football) | `Q1`, `Q2`, `Q3`, `Q4`, `HT`, `FT`, `FT OT` |
| Soccer, Rugby | `1H`, `2H`, `HT`, `FT`, `FT OT`, `FT NR` |
| MLB | `End 1` through `End 9` (and extra innings) |
| Esports Bo3 | `1/3`, `2/3`, `3/3` |
| Esports Bo5 | `1/5`, `2/5`, `3/5`, `4/5`, `5/5` |
| Tennis | `Set 1`, `Set 2`, `Set 3`, `Set 4`, `Set 5` |

### Message Trigger Events (when does the WS send data)

- Match goes live (`Scheduled` → `InProgress`)
- Score change (any goal/point scored)
- Period change (Q1→Q2, HT, etc.)
- Match completion (`ended: true`)
- Possession change (NFL/CFB only — `turn` field changes)

### New Env Vars to Add to `.env.example`

```bash
# Sports WebSocket
SPORTS_WS_FREEZE_TIMEOUT_SECONDS="300"    # 5 min default; fires before 18min known freeze
SPORTS_WS_LOG_LEVEL="changes"             # all | changes | minimal
SPORTS_WS_ENDED_GAME_TTL_MINUTES="60"     # How long to keep ended game states in memory
```

---

## Sources

### Primary (HIGH confidence)

- `https://docs.polymarket.com/developers/sports-websocket/message-format` — Complete message field table, status enumerations, period format table, sport-specific examples including NFL and esports JSON
- `https://docs.polymarket.com/developers/sports-websocket/overview` — Connection endpoint, ping/pong protocol, message trigger events
- `https://docs.polymarket.com/developers/sports-websocket/quickstart` — JavaScript heartbeat handler pattern (translated to Python)
- `https://docs.polymarket.com/market-data/websocket/sports` — Full status/period reference tables cross-confirmed
- `https://websocket-client.readthedocs.io/en/latest/threading.html` — Daemon thread pattern for `run_forever()`
- `https://websocket-client.readthedocs.io/en/latest/examples.html` — WebSocketApp ping/pong, `run_forever` params
- `agents/utils/objects.py` (local) — Existing Pydantic model patterns (SimpleMarket, SimpleEvent style)
- `agents/application/executor.py` (local) — `_env_int`, `_env_bool`, `_env_float` helpers; `canonicalize_category` as sport-type reference
- `requirements.txt` (local) — Confirmed `websocket-client==1.8.0`, `pydantic==2.8.2`, `backoff==2.2.1` already installed

### Secondary (MEDIUM confidence)

- `https://github.com/Polymarket/real-time-data-client/issues/26` — Silent freeze bug: confirmed server-side, 18-22 minute timing, ping/pong healthy during freeze. Opened Dec 2025, still open. Multiple independent developers confirmed same behavior.
- `https://github.com/websocket-client/websocket-client/issues/580` — Threading reconnect pattern discussion; confirms external loop over recursive on_close

### Tertiary (LOW confidence)

- `https://oneuptime.com/blog/post/2026-02-03-python-websocket-clients/` — Exponential backoff pattern with jitter; not independently verified from official source but matches backoff library docs
- Tennis and CBB period format examples — Not shown in official docs; inferred from sport structure. Treat as LOW confidence until confirmed with live data.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in requirements.txt; official Polymarket docs confirm endpoint and protocol
- Architecture: HIGH — WebSocketApp daemon thread pattern confirmed from library docs; freeze bug confirmed from official GitHub issue; Pydantic model pattern confirmed from existing codebase
- Pitfalls: HIGH (items 1-5) — directly derived from documented bug reports, library docs, and code inspection; MEDIUM (item 6 on esports score format) — confirmed by example JSON; LOW (open questions about CBB/Tennis formats)
- Status/period values: HIGH for documented sports; LOW for undocumented edge cases (CBB halves, NHL shootout period value)

**Research date:** 2026-03-03
**Valid until:** 2026-04-03 for stable items; 2026-03-10 for freeze bug status (monitor Polymarket/real-time-data-client issue #26 for server-side fix)
