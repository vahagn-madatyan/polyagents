# Phase 7: Code Quality and State Persistence - Research

**Researched:** 2026-03-11
**Domain:** Python module refactoring, file-based JSON persistence, Pydantic type hints
**Confidence:** HIGH

## Summary

Phase 7 is purely internal infrastructure work with no new external dependencies. All four requirements (QUAL-01, QUAL-02, PERS-02, PERS-03) are self-contained refactors within the existing codebase using patterns already established in `PregameCache` and `BudgetCoordinator`.

The env helper consolidation (QUAL-01) is a mechanical extraction: 9 modules each define their own `_env_bool`/`_env_int`/`_env_float` functions. The shared module must live in `agents/utils/env.py` and must NOT introduce any new import dependencies — specifically no `dotenv`, `langchain`, or `openai`. The consolidation preserves the exact same function signatures and logic already in use.

The state persistence tasks (PERS-02, PERS-03) follow the `PregameCache` pattern exactly: JSON file + `filelock` for cross-process safety, atomic write via tempfile-rename, env-configurable paths, graceful handling of missing/corrupt files on startup. `_order_log` serializes as a JSON dict (string game_id keys → list of order dicts); `_ended_games` serializes as a JSON array of integers.

**Primary recommendation:** Follow the PregameCache pattern verbatim for persistence. Extract env helpers from `executor.py` (most complete/correct version) as the canonical implementation in `agents/utils/env.py`.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

None — User delegated all technical decisions to Claude for this infrastructure phase.

### Claude's Discretion

**Env Helper Consolidation (QUAL-01):**
- Create a new lightweight shared module (e.g., `agents/utils/env.py`) containing `_env_bool()`, `_env_int()`, `_env_float()`
- MUST NOT import langchain, openai, or any heavy dependencies — this was the original reason for per-module duplication
- All 9+ modules with duplicated helpers should import from the shared module
- Also consider consolidating `load_dotenv()` calls if appropriate
- Follow existing naming conventions (`_env_bool`, `_env_int`, `_env_float`) and signature patterns

**objects.py TODO (QUAL-02):**
- Line 107 has a commented-out `list[str, 'Market']` with TODO — actual code already uses `Optional[list[Market]]` with `from __future__ import annotations`
- Resolve by removing the stale commented line or fixing the type hint comment to match reality
- Verify Pydantic model still parses correctly after cleanup

**Persistence Design (_order_log — PERS-02, _ended_games — PERS-03):**
- Follow PregameCache pattern: JSON file + filelock for cross-process safety
- File paths configurable via environment variables with sensible defaults
- Write on every update (atomic: write to temp file, then rename) — trading data integrity > I/O performance
- Reload on InGameTrader startup from persisted files
- Handle missing files gracefully (fresh start, no error)
- Handle corrupt files with warning log + fresh start (don't crash)
- _order_log serialized as JSON dict (game_id string keys → list of order dicts)
- _ended_games serialized as JSON array of game IDs
- No log rotation needed for v1.1 — games are finite per session

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| QUAL-01 | Env helper functions are centralized in a single shared module (eliminating duplication across 7+ files) | 9 modules confirmed with duplicated definitions; `executor.py` version is canonical; safe to extract to `agents/utils/env.py` with zero new dependencies |
| QUAL-02 | TODO in `agents/utils/objects.py:107` is resolved (forward reference validated or fixed) | Line 107 is a stale comment; `from __future__ import annotations` on line 1 already resolves the forward reference; actual field on line 108 is correct; remove the comment |
| PERS-02 | `_order_log` is persisted to file and survives process restarts | `_order_log` is a `dict[int, list[dict]]` initialized at line 134; `_log_order()` at line 636 is the sole write point; follows PregameCache JSON+filelock pattern |
| PERS-03 | `_ended_games` is persisted to file and survives process restarts | `_ended_games` is a `set[int]` initialized at line 136; `handle_game_ended()` at line 250 is the sole write point; serialize as JSON array |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `filelock` | Already installed | Cross-process file locking | Already used by PregameCache and BudgetCoordinator |
| `json` | stdlib | JSON serialization | Already used throughout persistence layer |
| `os` | stdlib | Path resolution, env vars | Already used by all modules |
| `tempfile` | stdlib | Atomic write via temp-then-rename | Prevents corrupt state on crash during write |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `from __future__ import annotations` | stdlib | Deferred annotation evaluation | Already in objects.py — enables forward references |
| `pydantic` | Already installed | Model validation | objects.py already uses it — no change needed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `filelock` + JSON | `sqlite3` | SQLite is more robust but adds query complexity; JSON is consistent with existing pattern |
| `tempfile` atomic write | Direct overwrite | Direct overwrite risks corruption on crash; atomic is correct for trading data |
| `os.environ.get()` + try/except | `os.getenv()` + str default | `sports_data.py` uses `os.environ.get(key, str(default))` without try/except — this is slightly risky (crashes on non-numeric env value); use try/except pattern from executor.py as canonical |

**Installation:**
```bash
# No new packages needed — filelock, json, os, tempfile all already available
```

---

## Architecture Patterns

### Recommended Project Structure

No new directories needed. Files to create/modify:

```
agents/
├── utils/
│   ├── env.py            # NEW: shared env helpers (QUAL-01)
│   └── objects.py        # MODIFY: remove stale comment line 107 (QUAL-02)
├── application/
│   ├── ingame_trader.py  # MODIFY: add persistence for _order_log, _ended_games (PERS-02, PERS-03)
│   ├── budget.py         # MODIFY: replace inline helpers with import from utils/env (QUAL-01)
│   ├── executor.py       # MODIFY: replace inline helpers with import from utils/env (QUAL-01)
│   ├── ingame_trader.py  # already listed above
│   ├── pregame_cache.py  # MODIFY: replace inline helpers with import from utils/env (QUAL-01)
│   ├── sports_executor.py # MODIFY: replace inline helpers (QUAL-01)
│   └── sports_trader.py  # MODIFY: replace inline helpers (QUAL-01)
├── connectors/
│   ├── sports_ws.py      # MODIFY: replace inline helpers (QUAL-01)
│   └── sports_data.py    # MODIFY: replace inline helpers (QUAL-01)
└── sports.py             # MODIFY: replace inline helpers (QUAL-01)
```

### Pattern 1: Shared Env Module (QUAL-01)

**What:** Extract the three duplicated env helpers into `agents/utils/env.py`.
**When to use:** Any module that needs env-based configuration.
**Example:**
```python
# agents/utils/env.py
# Source: extracted from agents/application/executor.py (canonical version)
import os


def _env_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
```

Each of the 9 modules then replaces its local definitions with:
```python
from agents.utils.env import _env_bool, _env_int, _env_float
```

**Critical constraint:** `agents/utils/env.py` must import ONLY stdlib (`os`). No `dotenv`, `langchain`, or `openai`. The original reason for duplication was that `executor.py` pulled in heavy dependencies — the shared module must not recreate that problem for lightweight modules.

### Pattern 2: Atomic JSON Persistence (PERS-02, PERS-03)

**What:** Write-to-temp-then-rename pattern for crash-safe JSON persistence.
**When to use:** Any in-memory state that must survive process restarts.
**Example:**
```python
# Source: pattern from agents/application/pregame_cache.py + tempfile stdlib
import json
import os
import tempfile
from filelock import FileLock


def _write_atomic(path: str, data) -> None:
    """Write JSON atomically: write to temp file, then rename."""
    dir_ = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp_path, path)  # atomic on POSIX; near-atomic on Windows
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _read_safe(path: str, default):
    """Read JSON file, returning default on missing or corrupt file."""
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[ingame_trader] warn=corrupt_state_file path={path} error={exc} — fresh start")
        return default
```

### Pattern 3: Persistence Integration in InGameTrader (PERS-02, PERS-03)

**What:** Add persistence load at `__init__` and persist writes at update points.
**Integration points (already identified from source):**
- `__init__` (lines 134, 136): load from files on startup
- `_log_order()` (line 636): write `_order_log` after appending
- `handle_game_ended()` (line 255): write `_ended_games` after adding game_id

```python
# In InGameTrader.__init__() — after existing state initialization
self._order_log_path = os.environ.get(
    "SPORTS_ORDER_LOG_PATH", "/tmp/polyagents_order_log.json"
)
self._ended_games_path = os.environ.get(
    "SPORTS_ENDED_GAMES_PATH", "/tmp/polyagents_ended_games.json"
)
self._lock_path = os.environ.get(
    "SPORTS_STATE_LOCK_PATH", "/tmp/polyagents_ingame_state.lock"
)

# Reload persisted state
self._order_log = self._load_order_log()
self._ended_games = self._load_ended_games()
```

```python
# _load_order_log: deserializes dict with int keys
def _load_order_log(self) -> dict[int, list[dict]]:
    raw = _read_safe(self._order_log_path, {})
    # JSON keys are strings — convert back to int
    return {int(k): v for k, v in raw.items()}

# _load_ended_games: deserializes set from JSON array
def _load_ended_games(self) -> set[int]:
    raw = _read_safe(self._ended_games_path, [])
    return set(int(x) for x in raw)

# Persistence write after _log_order
def _persist_order_log(self) -> None:
    lock = FileLock(self._lock_path)
    with lock:
        # JSON requires string keys
        serializable = {str(k): v for k, v in self._order_log.items()}
        _write_atomic(self._order_log_path, serializable)

# Persistence write after handle_game_ended
def _persist_ended_games(self) -> None:
    lock = FileLock(self._lock_path)
    with lock:
        _write_atomic(self._ended_games_path, list(self._ended_games))
```

### Anti-Patterns to Avoid

- **Importing env.py from executor.py indirectly causing circular imports:** `agents/utils/env.py` imports only `os` — no risk. But do NOT import `agents/application/executor` from `agents/utils/env`.
- **Sharing a lock file with BudgetCoordinator:** BudgetCoordinator uses `SPORTS_BUDGET_LOCK_PATH`. InGameTrader state should use a separate lock file (`SPORTS_STATE_LOCK_PATH`) to avoid deadlock.
- **Using `json.dump()` directly to the target file:** If the process crashes mid-write, the file is corrupt. Always use atomic write.
- **Converting JSON string keys to int at write time:** JSON object keys must be strings. Convert int keys to str on write, and str back to int on read.
- **Crashing on corrupt state:** Always wrap file reads in try/except with a log warning + default fallback. Never crash the trader on missing/corrupt persistence files.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-process file locking | Custom lock mechanism | `filelock.FileLock` | Already a project dependency; handles timeout, cleanup |
| Atomic file writes | Lock-and-write-in-place | `tempfile.mkstemp` + `os.replace` | `os.replace` is atomic on POSIX; prevents corrupt state |
| Env var parsing | Custom string parsing | The shared `_env_bool/int/float` pattern | Handles None, TypeError, ValueError edge cases consistently |

**Key insight:** The project already has the exact pattern needed — `PregameCache` and `BudgetCoordinator` both demonstrate the full JSON+filelock persistence pattern. This phase is copying established patterns, not inventing new ones.

---

## Common Pitfalls

### Pitfall 1: JSON Integer Key Round-Trip
**What goes wrong:** `_order_log` uses `dict[int, list[dict]]` in Python but JSON object keys must be strings. When serialized and deserialized, `{1: [...]}` becomes `{"1": [...]}` and Python reads it back as `{"1": [...]}` — a dict with string keys. Code that does `self._order_log[game_id]` with `game_id: int` will miss existing entries.
**Why it happens:** Python's `json.dumps({1: []})` silently converts int keys to strings.
**How to avoid:** On write, convert keys: `{str(k): v for k, v in self._order_log.items()}`. On read, convert back: `{int(k): v for k, v in raw.items()}`.
**Warning signs:** `KeyError` on `_order_log[game_id]` after restart even though data was persisted.

### Pitfall 2: Circular Import via env.py
**What goes wrong:** If `agents/utils/env.py` accidentally imports from `agents/application/` or `agents/connectors/`, it could create a circular dependency.
**Why it happens:** Helper modules occasionally need access to other utils.
**How to avoid:** `agents/utils/env.py` imports ONLY `os` from stdlib. No project imports ever.
**Warning signs:** `ImportError: cannot import name` or `ImportError: circular import` at startup.

### Pitfall 3: sports_data.py Pattern Difference
**What goes wrong:** `sports_data.py` uses a slightly different (less safe) pattern: `int(os.environ.get(key, str(default)))` — no try/except. An invalid env value (e.g., `SPORTS_STATS_CACHE_TTL_SECONDS=abc`) would raise `ValueError` at module import time.
**Why it happens:** The pattern was written without the try/except safety that executor.py uses.
**How to avoid:** When replacing the inline helper in `sports_data.py`, use the canonical try/except version from executor.py, not the local version. This is strictly safer.
**Warning signs:** Module-level `ValueError` or `TypeError` crash on startup when invalid env vars are set.

### Pitfall 4: Shared Lock Collision with BudgetCoordinator
**What goes wrong:** If InGameTrader persistence uses the same lock file as BudgetCoordinator (`SPORTS_BUDGET_LOCK_PATH` = `/tmp/polyagents_budget.lock`), a budget write and a state write could block each other — or worse, cause unexpected timeout.
**Why it happens:** Following the pattern too literally without noticing BudgetCoordinator already owns a lock.
**How to avoid:** Use a separate lock file for InGameTrader state: `SPORTS_STATE_LOCK_PATH` defaulting to `/tmp/polyagents_ingame_state.lock`.
**Warning signs:** Occasional `filelock.Timeout` exceptions during high-frequency trading.

### Pitfall 5: load_dotenv() Consolidation is Out of Scope
**What goes wrong:** `executor.py`, `search.py`, and `polymarket.py` each call `load_dotenv()`. These are in heavy-import modules that already pull in `python-dotenv`. Attempting to consolidate `load_dotenv()` calls risks changing import ordering for these modules.
**Why it happens:** QUAL-01 says "also consider consolidating `load_dotenv()` calls if appropriate."
**How to avoid:** Do NOT consolidate `load_dotenv()` calls. They are in different module-level initialization paths. The env helper module (`agents/utils/env.py`) does NOT call `load_dotenv()`.
**Warning signs:** Env vars not loaded at the right time; subtle test failures where env is not populated.

---

## Code Examples

Verified patterns from existing project source:

### Existing PregameCache Atomic Write (reference pattern)
```python
# Source: agents/application/pregame_cache.py lines 114-117
def _write_unlocked(self, data: dict) -> None:
    """Write cache JSON without acquiring lock (caller must hold lock)."""
    with open(self.cache_path, "w") as f:
        json.dump(data, f)
```
Note: PregameCache does NOT use atomic rename — it writes directly. For trading state (`_order_log`, `_ended_games`), the CONTEXT.md mandates atomic write (temp + rename) for higher durability. Upgrade the pattern.

### BudgetCoordinator Filelock Pattern (reference)
```python
# Source: agents/application/budget.py lines 156-167
def record_sports_trade(self, amount: float, league: str) -> None:
    lock = FileLock(self.lock_path, timeout=self.lock_timeout)
    with lock:
        data = self._read_budget_file_unlocked()
        data["sports"] = round(float(data.get("sports", self.sports_budget)) - float(amount), 10)
        ...
        self._write_budget_file_unlocked(data)
```

### objects.py QUAL-02 Fix
```python
# BEFORE (lines 107-108 in agents/utils/objects.py):
    # markets: list[str, 'Market'] # forward reference Market defined below - TODO: double check this works as intended
    markets: Optional[list[Market]] = None

# AFTER (remove the stale comment, keep the actual field):
    markets: Optional[list[Market]] = None
```
The `from __future__ import annotations` on line 1 already handles the forward reference. The comment is stale and misleading. No runtime behavior changes.

### Import replacement pattern (QUAL-01)
```python
# BEFORE (each module has its own definitions):
def _env_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")

# ... _env_int, _env_float ...

# AFTER:
from agents.utils.env import _env_bool, _env_int, _env_float
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Per-module inline env helpers | Centralized `agents/utils/env.py` | Phase 7 | Eliminates ~60 lines of duplicated code across 9 files |
| In-memory only `_order_log`, `_ended_games` | File-persisted with JSON+filelock | Phase 7 | Trade history and game-end state survive restarts |
| Direct file write (PregameCache pattern) | Atomic temp+rename write | Phase 7 | Prevents corrupt state files on crash during write |

**Deprecated/outdated:**
- Inline `_env_*` definitions in application/connector modules: replaced by `agents/utils/env` import
- Stale comment at `objects.py:107`: removed

---

## Open Questions

1. **load_dotenv() consolidation**
   - What we know: executor.py, search.py, polymarket.py each call `load_dotenv()` at module level
   - What's unclear: Whether unifying them is safe given different import orderings and test isolation
   - Recommendation: Skip load_dotenv consolidation for Phase 7. It is not required by any phase requirement and carries risk of subtle env-loading ordering bugs.

2. **sports_data.py _env_int/_env_float pattern mismatch**
   - What we know: The local helpers use `int(os.environ.get(key, str(default)))` without try/except — different from other modules
   - What's unclear: Whether any tests depend on this raising ValueError on bad input
   - Recommendation: Replace with the canonical try/except version. Check `tests/test_sports_data_connector.py` for any test that depends on error-raising behavior before replacing.

---

## Validation Architecture

> `nyquist_validation: true` in `.planning/config.json` — section included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (pyproject.toml `[tool.pytest.ini_options]`) |
| Config file | `pyproject.toml` |
| Quick run command | `python -m pytest tests/test_ingame_trader.py tests/test_sports_pipeline.py -q --tb=short` |
| Full suite command | `python -m pytest tests/ -q --tb=short --ignore=tests/test_event_url_trader.py --ignore=tests/test_news_connector.py --ignore=tests/test_trade_selection.py` |

Note: 3 test files are excluded from full suite due to `ModuleNotFoundError: No module named 'langchain_community'` — pre-existing condition unrelated to Phase 7.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| QUAL-01 | `agents/utils/env.py` importable with no heavy deps; modules import from it | unit | `python -m pytest tests/test_env_helpers.py -x` | ❌ Wave 0 |
| QUAL-01 | All 9 modules no longer define inline `_env_*` functions | unit | included in test_env_helpers.py | ❌ Wave 0 |
| QUAL-02 | `PolymarketEvent` Pydantic model parses correctly with `markets` field | unit | `python -m pytest tests/test_objects.py -x` | ❌ Wave 0 |
| PERS-02 | `_order_log` survives restart: write on update, reload on init | unit | `python -m pytest tests/test_ingame_persistence.py::test_order_log_survives_restart -x` | ❌ Wave 0 |
| PERS-02 | Missing order log file handled gracefully (fresh start) | unit | `python -m pytest tests/test_ingame_persistence.py::test_order_log_missing_file -x` | ❌ Wave 0 |
| PERS-02 | Corrupt order log file handled gracefully (warning + fresh start) | unit | `python -m pytest tests/test_ingame_persistence.py::test_order_log_corrupt_file -x` | ❌ Wave 0 |
| PERS-03 | `_ended_games` survives restart: write on update, reload on init | unit | `python -m pytest tests/test_ingame_persistence.py::test_ended_games_survives_restart -x` | ❌ Wave 0 |
| PERS-03 | Missing ended_games file handled gracefully (fresh start) | unit | `python -m pytest tests/test_ingame_persistence.py::test_ended_games_missing_file -x` | ❌ Wave 0 |
| PERS-03 | Corrupt ended_games file handled gracefully (warning + fresh start) | unit | `python -m pytest tests/test_ingame_persistence.py::test_ended_games_corrupt_file -x` | ❌ Wave 0 |

Existing tests that must remain green post-Phase 7:
- `tests/test_ingame_trader.py` (60 tests) — covers InGameTrader behavior; changes must not break these
- `tests/test_budget_coordinator.py` (19 tests) — covers BudgetCoordinator; env helper replacement must not break these
- `tests/test_sports_pipeline.py`, `tests/test_sports_executor.py`, `tests/test_sports_ws.py`, `tests/test_sports_data_connector.py`

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_ingame_trader.py tests/test_budget_coordinator.py tests/test_sports_pipeline.py -q --tb=short`
- **Per wave merge:** `python -m pytest tests/ -q --tb=short --ignore=tests/test_event_url_trader.py --ignore=tests/test_news_connector.py --ignore=tests/test_trade_selection.py`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_env_helpers.py` — covers QUAL-01 (import correctness, no heavy deps, all 9 modules updated)
- [ ] `tests/test_objects.py` — covers QUAL-02 (Pydantic model parses correctly after comment removal)
- [ ] `tests/test_ingame_persistence.py` — covers PERS-02 and PERS-03 (file round-trip, missing file, corrupt file)

---

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: `agents/application/ingame_trader.py` — `_order_log`, `_ended_games` init at lines 134/136; `_log_order()` at line 636; `handle_game_ended()` at line 250
- Direct codebase inspection: `agents/application/pregame_cache.py` — canonical JSON+filelock persistence pattern
- Direct codebase inspection: `agents/application/budget.py` — BudgetCoordinator filelock pattern and lock path conventions
- Direct codebase inspection: `agents/utils/objects.py` — line 107 stale comment confirmed; `from __future__ import annotations` on line 1 confirmed
- Direct codebase inspection: all 9 modules with duplicate env helpers confirmed via grep

### Secondary (MEDIUM confidence)
- Python stdlib `tempfile.mkstemp` + `os.replace` for atomic writes — standard POSIX pattern, well-established

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all dependencies already installed; no new packages
- Architecture: HIGH — patterns directly verified from existing project source (PregameCache, BudgetCoordinator)
- Pitfalls: HIGH — derived from direct code inspection (int key round-trip, lock collision, sports_data.py pattern difference verified by grep)

**Research date:** 2026-03-11
**Valid until:** Stable — no external dependencies; valid until codebase changes
