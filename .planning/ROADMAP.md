# Roadmap: Polyagents — Sports Mode

## Milestones

- ✅ **v1.0 Sports Mode** — Phases 1-6 (shipped 2026-03-11)
- 🚧 **v1.1 Hardening** — Phases 7-9 (in progress)

## Phases

<details>
<summary>✅ v1.0 Sports Mode (Phases 1-6) — SHIPPED 2026-03-11</summary>

- [x] Phase 1: WebSocket Foundation (2/2 plans) — completed 2026-03-05
- [x] Phase 2: Market Discovery and Pipeline Architecture (3/3 plans) — completed 2026-03-06
- [x] Phase 3: Pre-Game Analysis and LLM Integration (2/2 plans) — completed 2026-03-07
- [x] Phase 4: Live In-Game Trading Engine (3/3 plans) — completed 2026-03-08
- [x] Phase 5: Critical Integration Fixes (1/1 plan) — completed 2026-03-09
- [x] Phase 6: Safety & Resilience Wiring (2/2 plans) — completed 2026-03-11

Full details: `.planning/milestones/v1.0-ROADMAP.md`

</details>

### 🚧 v1.1 Hardening (In Progress)

**Milestone Goal:** Resolve all v1.0 tech debt, harden persistence and pipeline integration, and validate robustness under live conditions.

- [x] **Phase 7: Code Quality and State Persistence** - Consolidate env helper duplication, resolve objects.py TODO, and persist in-memory trading state to survive restarts
- [ ] **Phase 8: Pipeline Integration** - Wire `detect_value_bet()` into pre-game and in-game fast-path, and add live wallet balance refresh
- [ ] **Phase 9: Live Validation** - Validate slug normalization across all 9 sports, tune per-sport debounce thresholds, and confirm CLOB rate limiting under concurrent load

## Phase Details

### Phase 7: Code Quality and State Persistence
**Goal**: Shared infrastructure is clean and trading state survives process restarts
**Depends on**: Phase 6 (v1.0 complete)
**Requirements**: QUAL-01, QUAL-02, PERS-02, PERS-03
**Success Criteria** (what must be TRUE):
  1. All env helper calls across 7+ modules route through a single shared module with no duplication
  2. The TODO in `agents/utils/objects.py:107` is resolved — forward reference either validated or corrected
  3. `_order_log` is written to a file on each update and reloaded on startup so no trade history is lost on restart
  4. `_ended_games` is written to a file on each update and reloaded on startup so no game-end state is lost on restart
**Plans:** 2/2 plans executed

Plans:
- [x] 07-01-PLAN.md — Consolidate env helpers into shared module and fix objects.py TODO
- [x] 07-02-PLAN.md — Persist _order_log and _ended_games to survive restarts

### Phase 8: Pipeline Integration
**Goal**: `detect_value_bet()` actively filters trades in both pre-game and in-game paths, and wallet balance reflects live state
**Depends on**: Phase 7
**Requirements**: PIPE-01, PIPE-02, PERS-01
**Success Criteria** (what must be TRUE):
  1. Pre-game analysis calls `detect_value_bet()` and trades are only placed when a value opportunity is flagged
  2. In-game fast-path calls `detect_value_bet()` and skips execution when no odds divergence is detected
  3. `wallet_balance` is refreshed at runtime (not just at startup) so budget calculations reflect current USDC holdings
**Plans**: TBD

### Phase 9: Live Validation
**Goal**: The system behaves correctly under live Polymarket conditions across all sports and concurrent pipeline load
**Depends on**: Phase 8
**Requirements**: VALID-01, VALID-02, VALID-03
**Success Criteria** (what must be TRUE):
  1. Slug normalization produces a valid Polymarket slug for all 9 sport types when tested against live Polymarket market data
  2. Debounce thresholds are configurable per sport type (e.g., NFL uses a different threshold than NBA) and apply correctly to score-change events
  3. The system does not exceed 60 CLOB orders/min when both sports and general pipelines are running concurrently under representative load
**Plans**: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. WebSocket Foundation | v1.0 | 2/2 | Complete | 2026-03-05 |
| 2. Market Discovery and Pipeline Architecture | v1.0 | 3/3 | Complete | 2026-03-06 |
| 3. Pre-Game Analysis and LLM Integration | v1.0 | 2/2 | Complete | 2026-03-07 |
| 4. Live In-Game Trading Engine | v1.0 | 3/3 | Complete | 2026-03-08 |
| 5. Critical Integration Fixes | v1.0 | 1/1 | Complete | 2026-03-09 |
| 6. Safety & Resilience Wiring | v1.0 | 2/2 | Complete | 2026-03-11 |
| 7. Code Quality and State Persistence | v1.1 | 2/2 | Complete | 2026-03-13 |
| 8. Pipeline Integration | v1.1 | 0/TBD | Not started | - |
| 9. Live Validation | v1.1 | 0/TBD | Not started | - |
