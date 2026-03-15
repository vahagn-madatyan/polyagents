# Phase 7: Code Quality and State Persistence - Context

**Gathered:** 2026-03-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Clean up shared infrastructure (consolidate duplicated env helpers, resolve objects.py TODO) and persist in-memory trading state (_order_log, _ended_games) to survive process restarts. No new features — strictly tech debt resolution and data durability.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion

User delegated all technical decisions for this infrastructure phase. The following guidelines apply:

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

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. User explicitly chose "You decide all" for this infrastructure phase.

Reference pattern: PregameCache in `agents/application/pregame_cache.py` (JSON + filelock, env-configurable path).

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `PregameCache` (`agents/application/pregame_cache.py`): JSON file persistence with filelock — direct pattern to follow for _order_log and _ended_games
- `BudgetCoordinator` (`agents/application/budget.py`): Another filelock-based persistence example with JSON state
- Existing `_env_bool`/`_env_int`/`_env_float` implementations in `executor.py` (most complete versions with edge case handling)

### Established Patterns
- File persistence: JSON format with `filelock` library for cross-process safety
- Env parsing: `_env_bool()` checks for `("1", "true", "yes", "on")`, `_env_int()`/`_env_float()` use `os.environ.get()` with string defaults
- Module location: Utils live in `agents/utils/`, application logic in `agents/application/`
- Error handling: Specific exceptions preferred, print with `[component]` tags for logging

### Integration Points
- `InGameTrader.__init__()` in `agents/application/ingame_trader.py`: Where `_order_log` and `_ended_games` are initialized (lines 134, 136)
- `_record_order()` at line 637: Where `_order_log` is updated — persistence write hook goes here
- `_handle_game_ended()` at line 255: Where `_ended_games` is updated — persistence write hook goes here
- 9+ modules with env helper duplication: `executor.py`, `sports.py`, `ingame_trader.py`, `sports_executor.py`, `pregame_cache.py`, `sports_trader.py`, `sports_data.py`, `sports_ws.py`, `budget.py`

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 07-code-quality-and-state-persistence*
*Context gathered: 2026-03-11*
