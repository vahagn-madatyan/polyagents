---
phase: 6
slug: safety-resilience-wiring
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (pyproject.toml `[tool.pytest.ini_options]`) |
| **Config file** | pyproject.toml |
| **Quick run command** | `pytest tests/test_sports_ws.py tests/test_ingame_trader.py tests/test_sports_trader.py tests/test_sports_market_discovery.py -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_sports_ws.py tests/test_ingame_trader.py tests/test_sports_trader.py tests/test_sports_market_discovery.py -x -q`
- **After every plan wave:** Run `pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | WS-07 | unit | `pytest tests/test_sports_ws.py -k "status_categorization" -x` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | WS-07 | unit | `pytest tests/test_ingame_trader.py -k "halt" -x` | ❌ W0 | ⬜ pending |
| 06-01-03 | 01 | 1 | WS-07 | unit | `pytest tests/test_sports_trader.py -k "halt" -x` | ❌ W0 | ⬜ pending |
| 06-01-04 | 01 | 1 | WS-07 | unit | `pytest tests/test_ingame_trader.py -k "resume" -x` | ❌ W0 | ⬜ pending |
| 06-02-01 | 02 | 1 | MKT-02 | unit | `pytest tests/test_sports_market_discovery.py -k "retry" -x` | ❌ W0 | ⬜ pending |
| 06-02-02 | 02 | 1 | MKT-02 | unit | `pytest tests/test_sports_market_discovery.py -k "valid" -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ingame_trader.py` — `TestHaltGate` class: pause (Suspended/Delayed), hard-halt (Forfeit/Canceled), auto-resume
- [ ] `tests/test_sports_trader.py` — `TestHaltGate` class: halt gate in `run_pregame_analysis()`
- [ ] `tests/test_sports_market_discovery.py` — `TestRetryUnmappedSlugs` and `TestValidateMarketTag` classes
- [ ] `tests/test_sports_ws.py` — `TestStatusCategorization` class: PAUSE_STATUSES | HARD_HALT_STATUSES == HALT_STATUSES

*Existing infrastructure covers framework install — pytest already configured.*

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
