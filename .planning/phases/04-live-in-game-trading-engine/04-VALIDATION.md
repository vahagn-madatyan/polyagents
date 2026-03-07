---
phase: 04
slug: live-in-game-trading-engine
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-06
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (via pyproject.toml `[tool.pytest.ini_options]`) |
| **Config file** | `pyproject.toml` — `testpaths = ["tests"]`, `asyncio_mode = "auto"` |
| **Quick run command** | `python -m pytest tests/test_ingame_trader.py -x -q` |
| **Full suite command** | `python -m pytest tests/test_sports_trader.py tests/test_sports_ws.py tests/test_sports_pipeline.py tests/test_ingame_trader.py -q` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_ingame_trader.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/test_sports_trader.py tests/test_sports_ws.py tests/test_sports_pipeline.py tests/test_ingame_trader.py -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 3 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | TRD-02 | unit | `pytest tests/test_ingame_trader.py::TestEventClassification -x` | ❌ W0 | ⬜ pending |
| 04-01-01 | 01 | 1 | TRD-03 | unit | `pytest tests/test_ingame_trader.py::TestDetectionLatency -x` | ❌ W0 | ⬜ pending |
| 04-01-01 | 01 | 1 | TRD-05 | unit | `pytest tests/test_ingame_trader.py::TestCooldown -x` | ❌ W0 | ⬜ pending |
| 04-01-01 | 01 | 1 | TRD-05 | unit | `pytest tests/test_ingame_trader.py::TestInFlightGuard -x` | ❌ W0 | ⬜ pending |
| 04-01-01 | 01 | 1 | TRD-02 | unit | `pytest tests/test_ingame_trader.py::TestFastPath -x` | ❌ W0 | ⬜ pending |
| 04-01-01 | 01 | 1 | TRD-02 | unit | `pytest tests/test_ingame_trader.py::TestSlowPath -x` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 2 | TRD-02 | unit | `pytest tests/test_ingame_trader.py::TestGameEndedSafeguards -x` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 2 | TRD-02 | unit | `pytest tests/test_ingame_trader.py::TestExposureCap -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ingame_trader.py` — stubs for TRD-02, TRD-03, TRD-05
- [ ] No new framework/fixture infrastructure needed — existing `conftest.py` sufficient

*Existing infrastructure covers framework and fixture requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 5-second latency under real WS load | TRD-03 | Requires live websocket connection | Connect to live WS, trigger score change, measure time to trade evaluation |
| CLOB rate limit behavior under concurrent games | TRD-05 | Requires live CLOB API | Run dry-run with 5+ concurrent games, monitor order placement rate |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 3s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
