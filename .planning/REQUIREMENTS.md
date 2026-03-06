# Requirements: Polyagents — Sports Mode

**Defined:** 2026-03-03
**Core Value:** Autonomously identify and execute profitable sports trades by combining real-time game state with historical team performance data, reacting faster than manual traders.

## v1 Requirements

Requirements for sports mode launch. Each maps to roadmap phases.

### WebSocket Infrastructure

- [x] **WS-01**: Bot connects to Polymarket sports websocket (`wss://sports-api.polymarket.com/ws`) and maintains persistent connection
- [x] **WS-02**: Bot automatically reconnects on disconnect with last-known state tracking
- [x] **WS-03**: Bot detects silent websocket freeze (no data for configurable threshold) and forces reconnect
- [x] **WS-04**: Bot parses and normalizes game state messages (score, period, elapsed, live, ended, status) into structured `SportGameState` objects
- [x] **WS-05**: Bot handles sport-specific status values and period formats across all supported sports (NFL, NBA, MLB, NHL, CFB, CBB, soccer, esports, tennis)
- [x] **WS-06**: Bot detects period/quarter transitions and triggers trade re-evaluation at each transition
- [x] **WS-07**: Bot handles game edge cases (overtime, rain delays, forfeits, suspensions) with configurable trade rules per edge case

### Market Discovery

- [x] **MKT-01**: Bot identifies sports markets on Polymarket and tags them with metadata (league, teams, game time)
- [x] **MKT-02**: Bot maps websocket `gameId`/`slug` to Polymarket market IDs and token addresses via Gamma API slug lookup
- [x] **MKT-03**: Bot compares external odds against Polymarket price to detect value bets when divergence exceeds configurable threshold

### Trading Pipeline

- [ ] **TRD-01**: Bot runs pre-game analysis pipeline that evaluates sports markets and places trades before game starts
- [ ] **TRD-02**: Bot executes autonomous in-game trades reacting to live game state changes
- [ ] **TRD-03**: Bot triggers trade re-evaluation within 5 seconds of a score change event from the websocket
- [ ] **TRD-04**: Bot uses sports-specific LLM prompts that inject game context (score, period, teams, stats, odds) for trade decisions
- [ ] **TRD-05**: Bot applies score-change debouncing to prevent LLM call queue overflow during rapid game state changes
- [ ] **TRD-06**: Bot uses pre-game LLM probability cache for fast-path live decisions, reserving full LLM calls for major state changes

### External Data

- [x] **DATA-01**: Bot integrates with external sports data API (API-Sports or equivalent) for team stats, season performance, and head-to-head matchup history
- [x] **DATA-02**: Bot fetches current season win rates and recent performance for both teams before each game
- [x] **DATA-03**: Bot fetches historical head-to-head matchup records between teams

### Pipeline Management

- [x] **PIPE-01**: Sports pipeline runs as a separate process alongside general trading pipeline without interference
- [x] **PIPE-02**: Bot has configurable budget split between sports and general trading via environment variable
- [x] **PIPE-03**: Budget coordinator prevents race conditions when both pipelines attempt to read/allocate USDC balance concurrently
- [x] **PIPE-04**: Bot supports configurable per-sport budget caps to limit exposure by sport type
- [x] **PIPE-05**: Sports pipeline supports dry-run mode consistent with existing `EXECUTE_TRADES` flag

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Reliability

- **REL-01**: Multi-provider sports API fallback — switch to backup API if primary is down or rate-limited
- **REL-02**: Confidence-weighted position sizing tuned specifically for sports volatility bands

### Enhanced Signals

- **SIG-01**: Sport-specific prompt fragments per sport category (NBA comeback probability vs NFL clock management)
- **SIG-02**: Injury report integration from official league feeds

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Custom ML odds model | Months of out-of-scope work; use external odds APIs as probability ground truth |
| Backtesting framework | Requires historical order book data; use dry-run mode instead |
| Social/sentiment analysis | Noisy and slower than structured stats data; official stats are more reliable |
| Manual trade confirmation | Eliminates speed advantage; use dry-run mode and position size limits for safety |
| Web UI / dashboard | No trading edge; CLI/autonomous operation per project scope |
| Cross-platform arbitrage | Multi-exchange complexity and regulatory exposure; stay within Polymarket |
| Full order book market-making | Requires continuous inventory management; stay as directional taker |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| WS-01 | Phase 1 | Complete |
| WS-02 | Phase 1 | Complete |
| WS-03 | Phase 1 | Complete |
| WS-04 | Phase 1 | Complete |
| WS-05 | Phase 1 | Complete |
| WS-06 | Phase 1 | Complete |
| WS-07 | Phase 1 | Complete |
| MKT-01 | Phase 2 | Complete |
| MKT-02 | Phase 2 | Complete |
| MKT-03 | Phase 2 | Complete |
| TRD-01 | Phase 3 | Pending |
| TRD-02 | Phase 4 | Pending |
| TRD-03 | Phase 4 | Pending |
| TRD-04 | Phase 3 | Pending |
| TRD-05 | Phase 4 | Pending |
| TRD-06 | Phase 3 | Pending |
| DATA-01 | Phase 2 | Complete |
| DATA-02 | Phase 2 | Complete |
| DATA-03 | Phase 2 | Complete |
| PIPE-01 | Phase 2 | Complete |
| PIPE-02 | Phase 2 | Complete |
| PIPE-03 | Phase 2 | Complete |
| PIPE-04 | Phase 2 | Complete |
| PIPE-05 | Phase 2 | Complete |

**Coverage:**
- v1 requirements: 24 total
- Mapped to phases: 24
- Unmapped: 0

---
*Requirements defined: 2026-03-03*
*Last updated: 2026-03-03 after roadmap creation — all 24 requirements mapped*
