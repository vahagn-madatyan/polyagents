---
phase: 9
slug: live-validation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-15
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (pyproject.toml: `testpaths = ["tests"]`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `pytest tests/test_ingame_trader.py tests/test_sports_market_discovery.py tests/test_budget_coordinator.py -q` |
| **Full suite command** | `pytest tests/ -q --ignore=tests/test_event_url_trader.py --ignore=tests/test_news_connector.py --ignore=tests/test_trade_selection.py` |
| **Estimated runtime** | ~1 second |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_ingame_trader.py tests/test_sports_market_discovery.py tests/test_budget_coordinator.py -q`
- **After every plan wave:** Run `pytest tests/ -q --ignore=tests/test_event_url_trader.py --ignore=tests/test_news_connector.py --ignore=tests/test_trade_selection.py`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 2 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | VALID-02 | unit | `pytest tests/test_ingame_trader.py::TestPerSportCooldown -q` | ❌ W0 | ⬜ pending |
| 09-01-02 | 01 | 1 | VALID-02 | unit | `pytest tests/test_ingame_trader.py::TestPerSportCooldown -q` | ❌ W0 | ⬜ pending |
| 09-02-01 | 02 | 1 | VALID-03 | unit | `pytest tests/test_ingame_trader.py::TestOrderRateCounter -q` | ❌ W0 | ⬜ pending |
| 09-02-02 | 02 | 1 | VALID-03 | unit | `pytest tests/test_ingame_trader.py::TestOrderRateCounter -q` | ❌ W0 | ⬜ pending |
| 09-01-03 | 01 | 2 | VALID-01 | live/manual | `python scripts/validate_slugs.py` | ❌ W0 | ⬜ pending |
| 09-02-03 | 02 | 2 | VALID-03 | live/manual | `python scripts/validate_rate_limit.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ingame_trader.py` — new test class `TestPerSportCooldown` covering VALID-02 (4-6 new test cases in existing file)
- [ ] `tests/test_ingame_trader.py` — new test class `TestOrderRateCounter` covering VALID-03 counter unit tests (3-4 new test cases in existing file)
- [ ] `scripts/validate_slugs.py` — live VALID-01 validation runner (new file)
- [ ] `scripts/validate_rate_limit.py` — live VALID-03 concurrent rate validation runner (new file)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Slug normalization for all 9 sports against live Polymarket | VALID-01 | Requires active Polymarket connection and live game windows | Run `python scripts/validate_slugs.py` during peak multi-sport window; review JSON report |
| Concurrent pipeline rate under 60 orders/min | VALID-03 | Requires both pipelines running against live Polymarket | Run `python scripts/validate_rate_limit.py` for 10-minute window; verify `peak_per_60s < 60` in JSON report |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 2s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
