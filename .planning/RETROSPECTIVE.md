# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — Sports Mode

**Shipped:** 2026-03-11
**Phases:** 6 | **Plans:** 13 | **Commits:** 73

### What Was Built
- Complete sports trading pipeline: WebSocket game state → market discovery → pre-game LLM analysis → live in-game trading
- 9-sport normalization (NFL, NBA, MLB, NHL, CFB, CBB, soccer, esports, tennis) with status-aware halt gates
- Two-stage LLM analysis (blind superforecaster + market-aware trade decision) with file-persisted probability cache
- Autonomous in-game trading with fast-path (cached probability) / slow-path (full LLM re-analysis) routing
- Cross-process BudgetCoordinator with filelock for sports/general pipeline USDC split
- Slug retry with exponential backoff and market tag validation for resilient market discovery

### What Worked
- TDD approach: red-green cycles caught integration bugs early (slug_table key type mismatch, period transition game_id drop, budget gate wallet_balance wiring)
- Milestone audit process: identified 4 critical/high gaps that became Phases 5-6 gap closure work — without the audit these would have been runtime failures
- Inline env helper pattern: avoiding heavy executor.py import chain kept test suites fast and isolated
- File-persisted PregameCache: cross-process safety without additional infrastructure (Redis, etc.)
- Phase dependency ordering: strict 1→2→3→4→5→6 made each phase independently verifiable

### What Was Inefficient
- Phase 2 shows "0/3 Not started" in roadmap progress table despite all 3 plans being complete on disk — roadmap_complete flag was never updated (cosmetic)
- Summary files lack `one_liner` field — extraction tool returned null for all 13 summaries; accomplishments had to be manually compiled
- Some decisions accumulated in STATE.md are duplicates of what's in SUMMARY frontmatter — redundant context
- Nyquist validation never reached `compliant: true` for any phase despite all tests passing — process gap

### Patterns Established
- Inline `_env_int`/`_env_float`/`_env_bool` helpers per module to avoid heavy import chains
- Daemon thread pattern for LLM calls (prevent event loop blocking)
- `in_flight` set pattern for duplicate analysis prevention
- Cache-before-trade: always write cache entry before trade gates (downstream always has data)
- TTLCache two-tier pattern: stats=24h, odds=5min (different staleness tolerances)
- Halt gate as first check in trading methods (before cooldown, in-flight, or any trade logic)

### Key Lessons
1. Milestone audit before completion is essential — Phase 5-6 gap closure work would not have been planned otherwise
2. Integration tests at phase boundaries catch issues that unit tests miss (slug key type, event dict shape)
3. Default parameter values (e.g., `wallet_balance=0.0`) provide backward compatibility but can silently mask bugs — consider requiring explicit values at integration points
4. Inline env helpers trade DRY for isolation — acceptable tradeoff for now but monitor for divergence

### Cost Observations
- Model mix: Balanced profile used throughout
- Sessions: ~13 plan execution sessions over 7 days
- Notable: Phases 5-6 (gap closure) took 2 days but were essential for pipeline correctness

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Commits | Phases | Key Change |
|-----------|---------|--------|------------|
| v1.0 | 73 | 6 | Established TDD + milestone audit + gap closure pattern |

### Cumulative Quality

| Milestone | Tests | Phases | LOC Added |
|-----------|-------|--------|-----------|
| v1.0 | 353 | 6 | ~8,976 |

### Top Lessons (Verified Across Milestones)

1. Milestone audit before completion catches integration gaps that phase-level verification misses
2. Strict phase dependency ordering enables independent verification at each step
