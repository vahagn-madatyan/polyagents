---
phase: 03-pre-game-analysis-and-llm-integration
plan: 01
subsystem: api
tags: [langchain, openai, pydantic, filelock, llm, sports, pregame-cache]

requires:
  - phase: 02-market-discovery-and-pipeline-architecture
    provides: SportsMarketTag, SportsDataConnector.get_game_context(), budget coordination pattern

provides:
  - SportsExecutor with two-stage LLM analyze_game() producing CandidateTrade
  - Prompter.sports_superforecaster() blind probability prompt (no Polymarket prices)
  - Prompter.sports_trade_decision() prompt with value-bet divergence signal
  - PregameCache file-persisted JSON cache with TTL and filelock
  - SportsAnalysisCache Pydantic model for typed cache entries

affects:
  - 03-02 (SportsTrader orchestrator invokes SportsExecutor.analyze_game() and PregameCache)
  - phase-04 (fast-path reuse of PregameCache entries for score-change events)

tech-stack:
  added:
    - langchain-core (SystemMessage, HumanMessage)
    - langchain-openai (ChatOpenAI)
  patterns:
    - Two-stage LLM analysis: blind superforecaster -> trade decision with market prices
    - Inline env helpers (_env_float, _env_int, _env_bool) in each module to avoid heavy imports
    - File-persisted JSON cache with filelock for concurrent multi-process safety
    - int/str coercion: game_id always stored as str key in JSON for cross-process consistency

key-files:
  created:
    - agents/application/sports_executor.py
    - agents/application/pregame_cache.py
    - tests/test_sports_executor.py
  modified:
    - agents/application/prompts.py
    - agents/utils/objects.py

key-decisions:
  - "sports_superforecaster() blind estimate: no Polymarket prices in stage 1 prompt — pure statistical estimate from team data and external bookmaker odds only"
  - "Value-bet divergence line in sports_trade_decision(): only emitted when external_odds has implied_home_prob — no silent defaults"
  - "SportsExecutor avoids importing Executor.py: all helper functions (_parse_json_object, _parse_trade_fields, env helpers) reimplemented inline to prevent heavy langchain/chroma/gamma dependency chain"
  - "PregameCache game_id coerced to str internally: enables int or str lookup without ambiguity"
  - "langchain-core/langchain-openai installed into lightweight test venv (auto-fix Rule 3): packages are in requirements.txt but were missing from test environment"

patterns-established:
  - "Blind probability pattern: stage 1 LLM sees only team stats and bookmaker odds, never Polymarket prices"
  - "Two-stage LLM commit: superforecaster result passes as context to trade_decision for grounded decision-making"
  - "_format_h2h module-level helper in prompts.py: formats H2H list to readable text, handles empty list gracefully"
  - "PregameCache filelock pattern mirrors BudgetCoordinator: _read/_read_unlocked/_write_unlocked separation"

requirements-completed: [TRD-04, TRD-06]

duration: 5min
completed: 2026-03-06
---

# Phase 3 Plan 01: Sports Analysis Engine Summary

**Two-stage LLM sports analysis with blind superforecaster, value-bet divergence detection, and file-persisted PregameCache using langchain-core SystemMessage/HumanMessage**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-07T06:41:02Z
- **Completed:** 2026-03-07T06:46:00Z
- **Tasks:** 1
- **Files modified:** 5

## Accomplishments

- Built SportsExecutor with two-stage LLM analyze_game(): stage 1 sports_superforecaster (blind probability from team stats, H2H, bookmaker odds) then stage 2 sports_trade_decision (Polymarket prices + divergence signal) returning a fully-populated CandidateTrade
- Added sports_superforecaster() and sports_trade_decision() to the Prompter class using langchain_core SystemMessage/HumanMessage; blind estimate in stage 1 deliberately excludes Polymarket prices to prevent circular reasoning
- Built PregameCache with file-persisted JSON storage, FileLock for concurrent multi-process safety, TTL-based freshness checks, and int/str game_id coercion; survives pipeline restarts
- Added SportsAnalysisCache Pydantic model with all fields needed for Phase 4 fast-path (probabilities, side, size, rationale, trade metadata)
- 51 unit tests covering all behavior: prompt content, LLM call sequencing, CandidateTrade field mapping, cache CRUD/TTL/coercion/remove, model validation

## Task Commits

1. **Task 1: SportsAnalysisCache model, sports prompt methods, SportsExecutor, and PregameCache** - `f024f6a` (feat)

**Plan metadata:** (docs commit to follow)

## Files Created/Modified

- `agents/application/sports_executor.py` - SportsExecutor with analyze_game(), _invoke_llm(), _parse_outcome_prices(), _parse_json_object(), _parse_trade_fields(); inlined env helpers
- `agents/application/pregame_cache.py` - PregameCache with get/set/is_fresh/remove; filelock, TTL, int/str coercion
- `agents/application/prompts.py` - Added sports_superforecaster(), sports_trade_decision(), _format_h2h() helper; added langchain_core import
- `agents/utils/objects.py` - Added SportsAnalysisCache Pydantic model at end of file
- `tests/test_sports_executor.py` - 51 unit tests across TestSportsPrompts, TestSportsExecutor, TestPregameCache, TestSportsAnalysisCacheModel

## Decisions Made

- **Blind estimate in stage 1**: sports_superforecaster() deliberately excludes Polymarket prices — pure statistical estimate from external bookmaker odds and team data prevents circular reasoning where the model anchors on market prices
- **Divergence line gating**: sports_trade_decision() only emits the external-vs-Polymarket divergence line when external_odds includes implied_home_prob; no silent defaults to avoid misleading the model
- **No Executor import**: SportsExecutor reimplements _parse_json_object, _parse_trade_fields, and env helpers inline to avoid pulling in Chroma/Gamma/Polymarket via executor.py
- **str game_id keys**: PregameCache always stores keys as str(game_id) for consistent cross-process JSON serialization regardless of int vs str input

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed langchain-core and langchain-openai into test venv**
- **Found during:** Task 1, GREEN phase (running tests after implementation)
- **Issue:** Test venv had only lightweight packages; langchain-core and langchain-openai were in requirements.txt but absent from the isolated test environment
- **Fix:** Ran `.venv/bin/pip install langchain-core langchain-openai --quiet`
- **Files modified:** None (venv package installation only)
- **Verification:** `.venv/bin/python -c "from langchain_core.messages import HumanMessage, SystemMessage; print('imports OK')"` succeeded
- **Committed in:** f024f6a (part of task 1 commit — code written assuming packages present)

**2. [Rule 1 - Bug] Fixed test_init_uses_openai_model_env_var test approach**
- **Found during:** Task 1, GREEN phase (20/51 tests passing)
- **Issue:** Test used `importlib.reload()` inside patch context, but reload re-imported real ChatOpenAI after patch was active, causing the real ChatOpenAI to run without OPENAI_API_KEY and raise OpenAIError
- **Fix:** Removed reload(); import SportsExecutor directly inside patch context — patches are active on the already-loaded module
- **Files modified:** tests/test_sports_executor.py
- **Verification:** Test passes confirming ChatOpenAI called with model="gpt-4o"
- **Committed in:** f024f6a

**3. [Rule 1 - Bug] Fixed _invoke_llm AttributeError when bypassing __init__**
- **Found during:** Task 1, GREEN phase (21/51 tests failing)
- **Issue:** test_invoke_llm_calls_llm_invoke_and_returns_content used SportsExecutor.__new__() to bypass __init__, so self.model_name was not set; _invoke_llm's print statement raised AttributeError
- **Fix:** Changed `self.model_name` in _invoke_llm print to `getattr(self, "model_name", "unknown")`
- **Files modified:** agents/application/sports_executor.py
- **Verification:** All 51 tests pass
- **Committed in:** f024f6a

---

**Total deviations:** 3 auto-fixed (1 blocking dependency, 2 bugs in tests/implementation)
**Impact on plan:** All auto-fixes required for tests to run correctly. No scope creep. Implementation matches plan spec exactly.

## Issues Encountered

- Python 3.14 deprecation warning from langchain_core Pydantic V1 compat layer — non-blocking, existing known issue with the library version; does not affect functionality
- black reformatted pregame_cache.py, sports_executor.py, and test file on pre-commit hook — files re-staged and committed cleanly

## Next Phase Readiness

- SportsExecutor.analyze_game() is ready for Plan 03-02 SportsTrader orchestrator to invoke with game_state + market_tag + game_context
- PregameCache is ready for Plan 03-02 cache-check fast-path before full LLM analysis
- SportsAnalysisCache model ready for Phase 4 score-change debounce and fast-path reuse
- No blockers

## Self-Check: PASSED

- agents/application/sports_executor.py: FOUND
- agents/application/pregame_cache.py: FOUND
- agents/application/prompts.py: FOUND
- agents/utils/objects.py: FOUND
- tests/test_sports_executor.py: FOUND
- Commit f024f6a: FOUND
- All 51 tests: PASSED

---
*Phase: 03-pre-game-analysis-and-llm-integration*
*Completed: 2026-03-06*
