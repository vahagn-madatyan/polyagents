# M001: Sports Mode Pipeline

**Vision:** An autonomous Polymarket trading bot with a dedicated **sports mode** pipeline.

## Success Criteria


## Slices

- [x] **S01: WebSocket Foundation** `risk:medium` `depends:[]`
  > After this: Sports WebSocket client connects, streams game state, and reconnects on failure
- [x] **S02: Market Discovery and Pipeline Architecture** `risk:medium` `depends:[S01]`
  > After this: Sports markets are discovered via slug lookup with budget coordination between pipelines
- [x] **S03: Pre-Game Analysis and LLM Integration** `risk:medium` `depends:[S02]`
  > After this: Pre-game trades are positioned using LLM analysis with sports-specific prompts and external stats
- [x] **S04: Live In-Game Trading Engine** `risk:medium` `depends:[S03]`
  > After this: In-game trades execute autonomously on score changes via fast-path and slow-path routing
- [x] **S05: Critical Integration Fixes** `risk:medium` `depends:[S04]`
  > After this: Cross-component integration issues from v1.0 are resolved and tested
- [x] **S06: Safety & Resilience Wiring** `risk:medium` `depends:[S05]`
  > After this: Pipeline handles edge cases gracefully with proper error recovery and safety guards
- [x] **S07: Code Quality And State Persistence** `risk:medium` `depends:[S06]`
  > After this: Consolidate duplicated env helper functions into a single shared module and resolve the stale TODO in objects.
- [x] **S08: Pipeline Integration** `risk:medium` `depends:[S07]`
  > After this: Wire `detect_value_bet()` into the pre-game trading pipeline as an early filter (before LLM analysis), add `refresh_wallet_balance()` to BudgetCoordinator, and augment the cache entry with `implied_home_prob` for downstream in-game fast-path use.
- [ ] **S09: Live Validation** `risk:medium` `depends:[S08]`
  > After this: Add per-sport cooldown configuration and order-rate instrumentation to InGameTrader.
