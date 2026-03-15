---
phase: 7
slug: code-quality-and-state-persistence
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (pyproject.toml `[tool.pytest.ini_options]`) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `python -m pytest tests/test_ingame_trader.py tests/test_budget_coordinator.py tests/test_sports_pipeline.py -q --tb=short` |
| **Full suite command** | `python -m pytest tests/ -q --tb=short --ignore=tests/test_event_url_trader.py --ignore=tests/test_news_connector.py --ignore=tests/test_trade_selection.py` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_ingame_trader.py tests/test_budget_coordinator.py tests/test_sports_pipeline.py -q --tb=short`
- **After every plan wave:** Run `python -m pytest tests/ -q --tb=short --ignore=tests/test_event_url_trader.py --ignore=tests/test_news_connector.py --ignore=tests/test_trade_selection.py`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 0 | QUAL-01 | unit | `python -m pytest tests/test_env_helpers.py -x` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 0 | QUAL-02 | unit | `python -m pytest tests/test_objects.py -x` | ❌ W0 | ⬜ pending |
| 07-01-03 | 01 | 0 | PERS-02, PERS-03 | unit | `python -m pytest tests/test_ingame_persistence.py -x` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 1 | QUAL-01 | unit | `python -m pytest tests/test_env_helpers.py -x` | ❌ W0 | ⬜ pending |
| 07-02-02 | 02 | 1 | QUAL-01 | regression | `python -m pytest tests/test_ingame_trader.py tests/test_budget_coordinator.py tests/test_sports_pipeline.py -q --tb=short` | ✅ | ⬜ pending |
| 07-03-01 | 03 | 1 | QUAL-02 | unit | `python -m pytest tests/test_objects.py -x` | ❌ W0 | ⬜ pending |
| 07-04-01 | 04 | 2 | PERS-02 | unit | `python -m pytest tests/test_ingame_persistence.py::test_order_log_survives_restart -x` | ❌ W0 | ⬜ pending |
| 07-04-02 | 04 | 2 | PERS-02 | unit | `python -m pytest tests/test_ingame_persistence.py::test_order_log_missing_file -x` | ❌ W0 | ⬜ pending |
| 07-04-03 | 04 | 2 | PERS-02 | unit | `python -m pytest tests/test_ingame_persistence.py::test_order_log_corrupt_file -x` | ❌ W0 | ⬜ pending |
| 07-05-01 | 05 | 2 | PERS-03 | unit | `python -m pytest tests/test_ingame_persistence.py::test_ended_games_survives_restart -x` | ❌ W0 | ⬜ pending |
| 07-05-02 | 05 | 2 | PERS-03 | unit | `python -m pytest tests/test_ingame_persistence.py::test_ended_games_missing_file -x` | ❌ W0 | ⬜ pending |
| 07-05-03 | 05 | 2 | PERS-03 | unit | `python -m pytest tests/test_ingame_persistence.py::test_ended_games_corrupt_file -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_env_helpers.py` — stubs for QUAL-01 (shared module importable, no heavy deps, functions correct)
- [ ] `tests/test_objects.py` — stubs for QUAL-02 (PolymarketEvent parses correctly with markets field)
- [ ] `tests/test_ingame_persistence.py` — stubs for PERS-02, PERS-03 (round-trip, missing file, corrupt file)

*Existing test infrastructure covers regression testing — these are new test files for new behaviors.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| All 9 modules import from `agents/utils/env` | QUAL-01 | Static analysis / grep verification | `grep -rn "def _env_bool\|def _env_int\|def _env_float" agents/ --include="*.py"` should only match `agents/utils/env.py` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
