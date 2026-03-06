# Roadmap: Polyagents — Sports Mode

## Overview

The sports mode milestone adds a live, event-driven trading pipeline alongside the existing batch-oriented general trading pipeline. Starting from a reliable WebSocket data stream, each phase delivers one complete, independently verifiable capability: first the data foundation, then market discovery and pipeline architecture, then pre-game LLM analysis, and finally live in-game autonomous execution. Nothing in phase N can be built or tested until phase N-1 is stable — the hard build dependency order dictates the structure.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: WebSocket Foundation** - Reliable `SportGameState` stream from Polymarket sports websocket with reconnect, freeze detection, and normalization across all sports (completed 2026-03-05)
- [ ] **Phase 2: Market Discovery and Pipeline Architecture** - Slug-based sports market identification, external stats/odds API connector, budget coordination, and graceful pipeline coexistence
- [ ] **Phase 3: Pre-Game Analysis and LLM Integration** - Sports-specific LLM prompts, pre-game trade positioning pipeline, and probability cache for fast-path live decisions
- [ ] **Phase 4: Live In-Game Trading Engine** - Score-change triggered autonomous execution with debounce, fast-path decisions, and game-ended guards

## Phase Details

### Phase 1: WebSocket Foundation
**Goal**: The bot reliably streams live game state from Polymarket's sports websocket, normalizing events across all supported sports into `SportGameState` objects, and automatically recovers from disconnects and silent data freezes.
**Depends on**: Nothing (first phase)
**Requirements**: WS-01, WS-02, WS-03, WS-04, WS-05, WS-06, WS-07
**Success Criteria** (what must be TRUE):
  1. Bot connects to `wss://sports-api.polymarket.com/ws` and maintains persistent connection; game state messages appear in logs within seconds of startup
  2. Bot automatically reconnects on disconnect and after 5 minutes of no game messages (watchdog fires even when ping/pong is healthy)
  3. Bot parses game state into structured `SportGameState` objects with correct score, period, elapsed, live, and ended fields for NFL, NBA, MLB, NHL, CFB, CBB, soccer, esports, and tennis events
  4. Bot logs a period/quarter transition event and triggers trade re-evaluation at each detected transition
  5. Bot applies configurable rules for overtime, rain delays, and forfeits — halting new orders rather than trading on suspended/ambiguous markets
**Plans:** 2/2 plans complete

Plans:
- [ ] 01-01-PLAN.md — SportGameState model, SportsWSConnector with ping handling, message parsing, period transition detection
- [ ] 01-02-PLAN.md — Reconnect with exponential backoff, watchdog freeze detection, edge-case status handling, ended game TTL purge

### Phase 2: Market Discovery and Pipeline Architecture
**Goal**: The bot identifies which Polymarket markets correspond to each active game (via slug-based Gamma lookup, bypassing Chroma RAG), integrates the external sports data API for team stats and odds, and enforces a configurable budget split between sports and general trading with race-condition protection.
**Depends on**: Phase 1
**Requirements**: MKT-01, MKT-02, MKT-03, DATA-01, DATA-02, DATA-03, PIPE-01, PIPE-02, PIPE-03, PIPE-04, PIPE-05
**Success Criteria** (what must be TRUE):
  1. Bot builds a `ws_slug -> [market_ids]` lookup table at startup via Gamma API and refreshes it every 30 minutes; unmapped game events are logged and skipped without crashing
  2. Bot fetches current season win rates, recent form, and head-to-head matchup records for both teams before each game via the external stats API
  3. Bot detects when external odds diverge from Polymarket price beyond the configurable threshold and flags those markets as value-bet candidates
  4. Sports pipeline runs as a separate process alongside the general pipeline; a crash in one does not terminate the other
  5. A single `SPORTS_BUDGET_FRACTION` environment variable controls the sports budget share; concurrent pipeline budget reads are protected from race conditions; per-sport caps are configurable
**Plans:** 3 plans

Plans:
- [ ] 02-01-PLAN.md — SportsMarketTag model, slug-based Gamma lookup, moneyline market filtering
- [ ] 02-02-PLAN.md — SportsDataConnector with API-Sports team stats/H2H and The Odds API odds divergence detection
- [ ] 02-03-PLAN.md — BudgetCoordinator with filelock, per-sport caps, sports pipeline entry point, dry-run mode

### Phase 3: Pre-Game Analysis and LLM Integration
**Goal**: The bot runs a complete pre-game analysis pipeline that combines external stats, live odds, and sports-specific LLM prompts to select and place pre-game trades, producing a per-game probability cache that downstream live trading uses as its fast path.
**Depends on**: Phase 2
**Requirements**: TRD-01, TRD-04, TRD-06
**Success Criteria** (what must be TRUE):
  1. Bot generates pre-game trade candidates using LLM prompts that include score context, period, team names, season win rates, H2H records, and external odds — not generic market analysis text
  2. Bot places pre-game trades (or logs dry-run orders) before a game starts, drawing from the sports budget allocation and using confidence-weighted sizing
  3. Bot stores a per-game LLM probability estimate in a cache after pre-game analysis; the cache entry is retrievable by game ID for use during live trading
**Plans**: TBD

Plans:
- [ ] 03-01: Build `SportsExecutor` with sports-specific prompt templates and `llm.ainvoke()` async integration
- [ ] 03-02: Implement pre-game trade positioning pipeline, probability cache, and `SportsTrader` orchestrator (pre-game branch)

### Phase 4: Live In-Game Trading Engine
**Goal**: The bot autonomously executes in-game trades triggered by score changes, using cached pre-game probabilities for fast-path decisions and reserving full LLM calls for major state changes, while guarding against trading resolved markets and rate-limit exhaustion.
**Depends on**: Phase 3
**Requirements**: TRD-02, TRD-03, TRD-05
**Success Criteria** (what must be TRUE):
  1. Bot triggers trade re-evaluation within 5 seconds of a score change event from the websocket
  2. Bot uses the pre-game probability cache for fast-path decisions on minor score changes without calling the LLM; full LLM calls fire only for configurable major state changes (late score, OT start)
  3. Bot debounces rapid score change events and does not queue multiple simultaneous LLM calls for the same game
  4. Bot halts all new order placement on `ended: true` events and cancels orders placed within the configurable pre-expiry blackout window
**Plans**: TBD

Plans:
- [ ] 04-01: Implement score-change event handler with debounce, cooldown, and fast-path/slow-path decision routing
- [ ] 04-02: Add game-ended guard, pre-expiry order cancellation, concurrent game handling, and full end-to-end dry-run validation

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. WebSocket Foundation | 2/2 | Complete   | 2026-03-05 |
| 2. Market Discovery and Pipeline Architecture | 0/3 | Not started | - |
| 3. Pre-Game Analysis and LLM Integration | 0/2 | Not started | - |
| 4. Live In-Game Trading Engine | 0/2 | Not started | - |
