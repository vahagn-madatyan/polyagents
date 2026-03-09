---
phase: 5
slug: critical-integration-fixes
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-08
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | none — pytest discovers by convention |
| **Quick run command** | `python -m pytest tests/test_ingame_trader.py tests/test_sports_ws.py -v --tb=short` |
| **Full suite command** | `python -m pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_ingame_trader.py tests/test_sports_ws.py -v --tb=short`
- **After every plan wave:** Run `python -m pytest tests/ -v --tb=short`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 0 | WS-06 | unit | `python -m pytest tests/test_sports_ws.py::TestSportsWSConnectorPeriodTransition -x` | ❌ W0 — assert missing | ⬜ pending |
| 05-01-02 | 01 | 0 | TRD-02 | unit | `python -m pytest tests/test_ingame_trader.py -k "wallet" -x` | ❌ W0 — no test yet | ⬜ pending |
| 05-01-03 | 01 | 0 | TRD-02 | unit | `python -m pytest tests/test_ingame_trader.py -k "budget_gate" -x` | ❌ W0 — existing test doesn't check call args | ⬜ pending |
| 05-01-04 | 01 | 1 | WS-06 | unit | `python -m pytest tests/test_sports_ws.py::TestSportsWSConnectorPeriodTransition -x` | ✅ | ⬜ pending |
| 05-01-05 | 01 | 1 | TRD-02 | unit | `python -m pytest tests/test_ingame_trader.py -k "wallet_balance" -x` | ✅ | ⬜ pending |
| 05-01-06 | 01 | 1 | TRD-02 | unit | `python -m pytest tests/test_ingame_trader.py::TestFastPath -x` | ✅ | ⬜ pending |
| 05-01-07 | 01 | 1 | TRD-02 | unit | `python -m pytest tests/test_ingame_trader.py::TestSlowPath -x` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Add assertion `assert event["game_id"] == 19439` inside `test_period_transition_detected` in `tests/test_sports_ws.py` — covers WS-06 producer fix
- [ ] Add new test in `tests/test_ingame_trader.py` that constructs trader with `wallet_balance=500.0` and asserts `can_spend_sports` is called with `(amount, 500.0)` not `(amount, 0.0)` — covers TRD-02 call site fix
- [ ] Add test that trader with `wallet_balance=0.0` (default) fails budget gate, and with `wallet_balance=500.0` passes — covers floor-check semantics

*The test infrastructure itself exists and is healthy. Only specific assertions are missing.*

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
