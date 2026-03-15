---
phase: 3
slug: pre-game-analysis-and-llm-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-06
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (configured in pyproject.toml) |
| **Config file** | `pyproject.toml` — `[tool.pytest.ini_options]` testpaths=["tests"] asyncio_mode="auto" |
| **Quick run command** | `.venv/bin/python -m pytest tests/test_sports_executor.py tests/test_sports_trader.py -x -q` |
| **Full suite command** | `.venv/bin/python -m pytest tests/test_sports_executor.py tests/test_sports_trader.py tests/test_sports_pipeline.py tests/test_budget_coordinator.py -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest tests/test_sports_executor.py tests/test_sports_trader.py -x -q`
- **After every plan wave:** Run `.venv/bin/python -m pytest tests/test_sports_executor.py tests/test_sports_trader.py tests/test_sports_pipeline.py tests/test_budget_coordinator.py -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | TRD-04 | unit | `.venv/bin/python -m pytest tests/test_sports_executor.py::TestSportsPrompts::test_superforecaster_includes_game_context -x` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | TRD-04 | unit | `.venv/bin/python -m pytest tests/test_sports_executor.py::TestSportsPrompts::test_trade_decision_includes_divergence -x` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 1 | TRD-04 | unit | `.venv/bin/python -m pytest tests/test_sports_executor.py::TestAnalyzeGame -x` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 1 | TRD-06 | unit | `.venv/bin/python -m pytest tests/test_sports_trader.py::TestPregameCache::test_set_and_get -x` | ❌ W0 | ⬜ pending |
| 03-02-02 | 02 | 1 | TRD-06 | unit | `.venv/bin/python -m pytest tests/test_sports_trader.py::TestPregameCache::test_ttl_expiry -x` | ❌ W0 | ⬜ pending |
| 03-02-03 | 02 | 1 | TRD-06 | unit | `.venv/bin/python -m pytest tests/test_sports_trader.py::TestPregameCache::test_miss_returns_none -x` | ❌ W0 | ⬜ pending |
| 03-02-04 | 02 | 1 | TRD-06 | unit | `.venv/bin/python -m pytest tests/test_sports_trader.py::TestPregameCache::test_game_id_coercion -x` | ❌ W0 | ⬜ pending |
| 03-02-05 | 02 | 1 | TRD-01 | integration | `.venv/bin/python -m pytest tests/test_sports_trader.py::TestPregamePipeline -x` | ❌ W0 | ⬜ pending |
| 03-02-06 | 02 | 1 | TRD-01 | unit | `.venv/bin/python -m pytest tests/test_sports_trader.py::TestDryRun -x` | ❌ W0 | ⬜ pending |
| 03-02-07 | 02 | 1 | TRD-01 | unit | `.venv/bin/python -m pytest tests/test_sports_trader.py::TestCacheRestartSkip -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_sports_executor.py` — stubs for TRD-04 (prompt content, analyze_game output)
- [ ] `tests/test_sports_trader.py` — stubs for TRD-01 (pipeline flow, dry-run) and TRD-06 (cache CRUD, TTL, restart skip)

*Existing infrastructure covers framework and fixture needs (pytest configured, 173 sports tests passing).*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
