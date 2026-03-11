---
phase: 2
slug: market-discovery-and-pipeline-architecture
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-06
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.2 (already in requirements.txt) |
| **Config file** | pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `python -m pytest tests/test_slug_index.py tests/test_sports_data.py tests/test_budget_coordinator.py -x --tb=short` |
| **Full suite command** | `python -m pytest tests/ -x --tb=short` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_slug_index.py tests/test_sports_data.py tests/test_budget_coordinator.py -x --tb=short`
- **After every plan wave:** Run `python -m pytest tests/ -x --tb=short`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 2-01-01 | 01 | 1 | MKT-01 | unit | `python -m pytest tests/test_slug_index.py::test_market_tag_extraction -x` | ❌ W0 | ⬜ pending |
| 2-01-02 | 01 | 1 | MKT-02 | unit | `python -m pytest tests/test_slug_index.py::test_lookup_returns_market_ids -x` | ❌ W0 | ⬜ pending |
| 2-01-03 | 01 | 1 | MKT-02 | unit | `python -m pytest tests/test_slug_index.py::test_fallback_triggered_on_404 -x` | ❌ W0 | ⬜ pending |
| 2-02-01 | 02 | 1 | DATA-01 | unit | `python -m pytest tests/test_sports_data.py::test_connector_init -x` | ❌ W0 | ⬜ pending |
| 2-02-02 | 02 | 1 | DATA-02 | unit | `python -m pytest tests/test_sports_data.py::test_stats_cache_hit -x` | ❌ W0 | ⬜ pending |
| 2-02-03 | 02 | 1 | DATA-03 | unit | `python -m pytest tests/test_sports_data.py::test_h2h_returns_empty_on_error -x` | ❌ W0 | ⬜ pending |
| 2-02-04 | 02 | 1 | MKT-03 | unit | `python -m pytest tests/test_sports_data.py::test_detect_value_bet -x` | ❌ W0 | ⬜ pending |
| 2-03-01 | 03 | 2 | PIPE-02 | unit | `python -m pytest tests/test_budget_coordinator.py::test_allocate_sports_budget -x` | ❌ W0 | ⬜ pending |
| 2-03-02 | 03 | 2 | PIPE-03 | unit | `python -m pytest tests/test_budget_coordinator.py::test_lock_contention -x` | ❌ W0 | ⬜ pending |
| 2-03-03 | 03 | 2 | PIPE-04 | unit | `python -m pytest tests/test_budget_coordinator.py::test_per_sport_caps -x` | ❌ W0 | ⬜ pending |
| 2-03-04 | 03 | 2 | PIPE-01, PIPE-05 | unit | `python -m pytest tests/test_sports_pipeline.py::test_no_heavy_imports tests/test_sports_pipeline.py::test_dry_run_flag_override -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_slug_index.py` — stubs for MKT-01, MKT-02
- [ ] `tests/test_sports_data.py` — stubs for MKT-03, DATA-01, DATA-02, DATA-03
- [ ] `tests/test_budget_coordinator.py` — stubs for PIPE-02, PIPE-03, PIPE-04
- [ ] `tests/test_sports_pipeline.py` — stubs for PIPE-01, PIPE-05

*Existing infrastructure covers pytest framework — no install needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live Gamma API slug lookup | MKT-02 | Requires real network endpoint | Run slug lookup against live Gamma API, verify market IDs returned |
| Live API-Sports fetch | DATA-01 | Requires API key and network | Set API key, fetch standings for NFL, verify JSON structure |
| Cross-process lock contention | PIPE-03 | Requires two real processes | Start two pipeline processes, trigger concurrent budget reads, verify no corruption |
| Sports pipeline crash isolation | PIPE-01 | Requires process crash simulation | Start both pipelines, kill sports process, verify general continues |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
