---
phase: 01-websocket-foundation
plan: 01
subsystem: sports-websocket
tags: [websocket, pydantic, game-state, tdd, sports]
dependency_graph:
  requires: []
  provides:
    - SportGameState Pydantic model (agents/utils/objects.py)
    - SportsWSConnector class (agents/connectors/sports_ws.py)
    - Unit test suite for WS connector (tests/test_sports_ws.py)
  affects:
    - Phase 1 Plan 02: reconnect/watchdog logic builds on SportsWSConnector
    - Phase 2: slug-based market discovery uses SportGameState.slug
    - Phase 3: settlement uses SportGameState.ended / ended_game_ttl_minutes
tech_stack:
  added:
    - websocket-client==1.8.0 (WebSocketApp daemon thread pattern)
  patterns:
    - Pydantic v2 model with Optional sport-specific fields (no per-sport subclasses)
    - Module-level _parse_score() and _build_game_state() for testability without class instantiation
    - threading.Lock for game state dict (single writer WS thread, multiple readers)
    - Lock released BEFORE queue.put() to prevent deadlock on full queue
    - Watchdog timer reset only on game data messages (NOT ping/pong)
key_files:
  created:
    - agents/connectors/sports_ws.py
    - tests/test_sports_ws.py
  modified:
    - agents/utils/objects.py
    - .env.example
decisions:
  - "_env_int inline in sports_ws.py: avoided importing from agents.application.executor because executor.py has a heavy langchain/openai import chain that breaks the minimal venv. The helper is 8 lines and self-contained — keeping it local avoids a transitive dep on the full LLM stack for a utility used only at startup."
  - "MagicMock wrapping real lock for thread-safety test: Python 3.14 made _thread.lock.acquire read-only so direct monkey-patching is impossible. Replaced with MagicMock(wraps=real_lock) — still validates that _state_lock.__enter__ is called without modifying C-level lock internals."
metrics:
  duration: "5 minutes 15 seconds"
  completed: "2026-03-05"
  tasks_completed: 2
  files_created: 2
  files_modified: 2
  tests_added: 20
---

# Phase 1 Plan 01: SportGameState Model and SportsWSConnector Summary

**One-liner:** SportGameState Pydantic model + SportsWSConnector using WebSocketApp daemon thread with ping/pong handling, period transition detection, and thread-safe state storage.

## What Was Built

### SportGameState model (`agents/utils/objects.py`)

Single Pydantic v2 model covering all 9 sports (NFL, NBA, MLB, NHL, CFB, CBB, soccer, esports, tennis):

```python
class SportGameState(BaseModel):
    game_id: int
    league: str
    slug: str
    home_team: str
    away_team: str
    status: str
    score_raw: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    period: str
    live: bool
    ended: bool
    elapsed: Optional[str] = None
    finished_timestamp: Optional[str] = None
    possession: Optional[str] = None  # NFL/CFB "turn" field
    last_updated: float = Field(default_factory=time.monotonic)
    stale: bool = False
```

### Score parsing (`agents/connectors/sports_ws.py`)

Module-level `_parse_score()` handles:
- Standard: `"3-16"` → `(3, 16)`
- Esports compound: `"000-000|2-0|Bo3"` → extracts middle segment → `(2, 0)`
- Empty/None → `(None, None)`
- Malformed → `(None, None)` with warning log

### SportsWSConnector (`agents/connectors/sports_ws.py`)

- `WS_URL = "wss://sports-api.polymarket.com/ws"` — no auth required
- `_on_message`: ping → pong immediately, return (does NOT update `_last_message_at`)
- `_on_message`: game data → update `_last_message_at`, reset watchdog, process state
- `_process_game_state`: thread-safe via `_state_lock`, releases lock BEFORE queue.put()
- Period transitions: detected by comparing old vs new period, emitted as `{"type": "period_transition", ...}` to `_message_queue`
- Watchdog timer: `threading.Timer` fires on `SPORTS_WS_FREEZE_TIMEOUT_SECONDS` of silence, marks all states `stale=True`, closes connection
- Reconnect: exponential backoff `min(2**attempt, 60)` + jitter, resets after 60s stable connection
- Public API: `get_game_state(id)`, `get_all_game_states()`, `get_message_queue()`

### Env vars (`.env.example`)

```bash
SPORTS_WS_FREEZE_TIMEOUT_SECONDS="300"
SPORTS_WS_LOG_LEVEL="changes"
SPORTS_WS_ENDED_GAME_TTL_MINUTES="60"
```

## Tests

20 unit tests in `tests/test_sports_ws.py` — all pass, no network calls:

| Test Class | Tests | Coverage |
|---|---|---|
| TestSportGameStateModel | 7 | NFL, soccer, esports, tennis, MLB construction; stale default; last_updated |
| TestParseScore | 4 | standard, esports compound, empty/None, malformed |
| TestSportsWSConnectorPing | 3 | ping→pong no state change; data updates timestamp; data stores state |
| TestSportsWSConnectorPeriodTransition | 3 | Q3→Q4 emits event; same period no event; first message no event |
| TestSportsWSConnectorThreadSafety | 3 | lock acquired; get_game_state returns/None; get_all_game_states snapshot |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Inlined _env_int instead of importing from executor.py**

- **Found during:** Task 2 GREEN phase
- **Issue:** `agents/application/executor.py` imports `langchain_core`, `langchain_openai`, and other LLM packages not installed in the project venv. Importing from executor.py fails with `ModuleNotFoundError: No module named 'langchain_core'` in the test environment. The PLAN specifies `from agents.application.executor import _env_int` as the import pattern, but this creates a transitive dependency on the full LLM stack for a 3-line utility.
- **Fix:** Defined `_env_int` directly in `sports_ws.py` (8 lines, identical logic to executor.py version). The key_links pattern in the PLAN frontmatter (`from agents.application.executor import _env_int`) was not achievable without installing the full LLM dependency chain.
- **Files modified:** `agents/connectors/sports_ws.py`
- **Commit:** 8116b9d

**2. [Rule 1 - Bug] Fixed lock spy test for Python 3.14 compatibility**

- **Found during:** Task 2 GREEN phase (test run)
- **Issue:** `_thread.lock` attributes are read-only in Python 3.14 — direct monkey-patching via `connector._state_lock.acquire = spy_acquire` raises `AttributeError`.
- **Fix:** Replaced spy pattern with `MagicMock(wraps=real_lock)` — still validates `__enter__` is called during `_process_game_state`, but without modifying C-level lock internals.
- **Files modified:** `tests/test_sports_ws.py`
- **Commit:** 455234e

## Self-Check: PASSED

- [x] `agents/utils/objects.py` — FOUND (contains `class SportGameState`)
- [x] `agents/connectors/sports_ws.py` — FOUND (396 lines, min 150 required)
- [x] `tests/test_sports_ws.py` — FOUND (411 lines, min 100 required; 20 tests pass)
- [x] `.env.example` — FOUND (contains `SPORTS_WS_FREEZE_TIMEOUT_SECONDS`)
- [x] Commit 455234e — FOUND (SportGameState model + tests)
- [x] Commit 8116b9d — FOUND (SportsWSConnector)
- [x] Key link: `class SportGameState` in objects.py — VERIFIED
- [x] Key link: `wss://sports-api.polymarket.com/ws` in sports_ws.py — VERIFIED
- [x] `grep -c SPORTS_WS_ .env.example` returns 3 — VERIFIED
