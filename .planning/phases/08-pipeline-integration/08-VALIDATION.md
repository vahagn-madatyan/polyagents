---
phase: 8
slug: pipeline-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-13
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (pyproject.toml `[tool.pytest.ini_options]`) |
| **Config file** | `pyproject.toml` — `testpaths = ["tests"]`, `asyncio_mode = "auto"` |
| **Quick run command** | `python -m pytest tests/test_sports_trader.py tests/test_ingame_trader.py tests/test_budget_coordinator.py -q` |
| **Full suite command** | `python -m pytest -q` |
| **Estimated runtime** | ~1 second |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_sports_trader.py tests/test_ingame_trader.py tests/test_budget_coordinator.py -q`
- **After every plan wave:** Run `python -m pytest -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 2 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 0 | PIPE-01 | unit | `python -m pytest tests/test_sports_trader.py -k "value_bet" -q` | ❌ W0 | ⬜ pending |
| 08-01-02 | 01 | 0 | PIPE-02 | unit | `python -m pytest tests/test_ingame_trader.py -k "value_bet" -q` | ❌ W0 | ⬜ pending |
| 08-01-03 | 01 | 0 | PERS-01 | unit | `python -m pytest tests/test_budget_coordinator.py -k "refresh" -q` | ❌ W0 | ⬜ pending |
| 08-01-04 | 01 | 0 | PIPE-02 | unit | `python -m pytest tests/test_sports_trader.py -k "cache_entry" -q` | ✅ augment | ⬜ pending |
| 08-02-01 | 02 | 1 | PIPE-01 | unit | `python -m pytest tests/test_sports_trader.py -k "value_bet" -q` | ❌ W0 | ⬜ pending |
| 08-02-02 | 02 | 1 | PIPE-01 | unit | `python -m pytest tests/test_sports_trader.py -k "value_bet" -q` | ❌ W0 | ⬜ pending |
| 08-03-01 | 03 | 1 | PIPE-02 | unit | `python -m pytest tests/test_ingame_trader.py -k "value_bet" -q` | ❌ W0 | ⬜ pending |
| 08-03-02 | 03 | 1 | PIPE-02 | unit | `python -m pytest tests/test_ingame_trader.py -k "value_bet" -q` | ❌ W0 | ⬜ pending |
| 08-04-01 | 04 | 1 | PERS-01 | unit | `python -m pytest tests/test_budget_coordinator.py -k "refresh" -q` | ❌ W0 | ⬜ pending |
| 08-04-02 | 04 | 1 | PERS-01 | unit | `python -m pytest tests/test_budget_coordinator.py -k "refresh" -q` | ❌ W0 | ⬜ pending |
| 08-04-03 | 04 | 1 | PERS-01 | unit | `python -m pytest tests/test_ingame_trader.py -k "wallet" -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] New test class `TestValueBetFilter` in `tests/test_sports_trader.py` — stubs for PIPE-01 behaviors (value bet filter in pre-game path)
- [ ] New test class `TestValueBetFilter` in `tests/test_ingame_trader.py` — stubs for PIPE-02 behaviors (value bet filter in fast and slow paths)
- [ ] New test class `TestWalletRefresh` in `tests/test_budget_coordinator.py` — stubs for PERS-01 (refresh method, cooldown, error fallback, dry-run skip)
- [ ] Augment `TestRunPregameAnalysis::test_cache_entry_has_required_fields` to check `implied_home_prob` field

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 2s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
