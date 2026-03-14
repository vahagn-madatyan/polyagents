# Requirements: Polyagents — Sports Mode

**Defined:** 2026-03-10
**Core Value:** Autonomously execute profitable sports trades by combining real-time Polymarket game state with historical team performance data, reacting faster than manual traders.

## v1.1 Requirements

Requirements for hardening release. Each maps to roadmap phases.

### Pipeline Integration

- [ ] **PIPE-01**: Pre-game analysis calls `detect_value_bet()` to flag value opportunities before placing trades
- [ ] **PIPE-02**: In-game fast-path calls `detect_value_bet()` to validate trades against external odds divergence

### Persistence

- [ ] **PERS-01**: `wallet_balance` is periodically refreshed during pipeline execution (not just at startup)
- [ ] **PERS-02**: `_order_log` is persisted to file and survives process restarts
- [ ] **PERS-03**: `_ended_games` is persisted to file and survives process restarts

### Validation

- [ ] **VALID-01**: Slug normalization produces consistent slugs across all 9 sport types with live Polymarket data
- [ ] **VALID-02**: Score-change debounce thresholds are configurable per sport type (not just global cooldown)
- [ ] **VALID-03**: CLOB rate limiting prevents exceeding 60 orders/min across both sports and general pipelines

### Code Quality

- [x] **QUAL-01**: Env helper functions are centralized in a single shared module (eliminating duplication across 7+ files)
- [x] **QUAL-02**: TODO in `agents/utils/objects.py:107` is resolved (forward reference validated or fixed)

## Future Requirements

None — hardening milestone covers all carried-forward items.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-provider sports API fallback | Single provider sufficient; defer to future if reliability issues arise |
| Backtesting framework | Forward-looking execution only per v1.0 decision |
| Mobile app or web UI | CLI/autonomous operation only |
| Custom odds modeling | Use external odds data and LLM reasoning per v1.0 decision |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PIPE-01 | Phase 8 | Pending |
| PIPE-02 | Phase 8 | Pending |
| PERS-01 | Phase 8 | Pending |
| PERS-02 | Phase 7 | Pending |
| PERS-03 | Phase 7 | Pending |
| VALID-01 | Phase 9 | Pending |
| VALID-02 | Phase 9 | Pending |
| VALID-03 | Phase 9 | Pending |
| QUAL-01 | Phase 7 | Complete |
| QUAL-02 | Phase 7 | Complete |

**Coverage:**
- v1.1 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-10*
*Last updated: 2026-03-10 after roadmap creation (v1.1 phases 7-9)*
