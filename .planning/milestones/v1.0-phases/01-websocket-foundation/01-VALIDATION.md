---
phase: 1
slug: websocket-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-03
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.2 (already in requirements.txt) |
| **Config file** | none — run from project root |
| **Quick run command** | `pytest tests/test_sports_ws.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_sports_ws.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 0 | WS-01..WS-07 | unit stubs | `pytest tests/test_sports_ws.py -x -q` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | WS-04 | unit | `pytest tests/test_sports_ws.py::test_build_game_state_nfl -x` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 1 | WS-04 | unit | `pytest tests/test_sports_ws.py::test_parse_score_standard -x` | ❌ W0 | ⬜ pending |
| 1-01-04 | 01 | 1 | WS-04 | unit | `pytest tests/test_sports_ws.py::test_parse_score_esports -x` | ❌ W0 | ⬜ pending |
| 1-01-05 | 01 | 1 | WS-01 | unit | `pytest tests/test_sports_ws.py::test_ping_message_handled -x` | ❌ W0 | ⬜ pending |
| 1-02-01 | 02 | 1 | WS-02 | unit | `pytest tests/test_sports_ws.py::test_reconnect_backoff_sequence -x` | ❌ W0 | ⬜ pending |
| 1-02-02 | 02 | 1 | WS-03 | unit | `pytest tests/test_sports_ws.py::test_watchdog_fires_on_freeze -x` | ❌ W0 | ⬜ pending |
| 1-02-03 | 02 | 1 | WS-03 | unit | `pytest tests/test_sports_ws.py::test_watchdog_marks_states_stale -x` | ❌ W0 | ⬜ pending |
| 1-02-04 | 02 | 1 | WS-06 | unit | `pytest tests/test_sports_ws.py::test_period_transition_detected -x` | ❌ W0 | ⬜ pending |
| 1-02-05 | 02 | 1 | WS-05, WS-07 | unit | `pytest tests/test_sports_ws.py::test_edge_case_statuses -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_sports_ws.py` — stubs for WS-01 through WS-07; no network calls (all tests use static dicts and mock WS objects)

*Existing infrastructure covers pytest framework — no install needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live WS connection to Polymarket | WS-01 | Requires real network endpoint | Run `python -c "from agents.connectors.sports_ws import SportsWSConnector; c = SportsWSConnector(); c.run()"` and verify game state logs appear |
| Reconnect after real disconnect | WS-02 | Requires killing network | Kill network briefly, verify reconnect in logs |
| Watchdog on real freeze | WS-03 | Server-side bug is intermittent | Monitor logs for 20+ minutes; watchdog should fire if freeze occurs |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
