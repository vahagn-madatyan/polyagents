# Project Research Summary

**Project:** Polymarket Autonomous Sports Trading Bot — Sports Mode Milestone
**Domain:** Live event-driven sports prediction market trading pipeline
**Researched:** 2026-03-03
**Confidence:** HIGH (architecture and pitfalls verified against codebase + official docs); MEDIUM (sports APIs — pricing/coverage may evolve)

## Executive Summary

The sports mode milestone adds a live, event-driven trading pipeline alongside the existing batch-oriented general trading pipeline. This is not a feature flag — it is a fundamentally different execution model. The general pipeline polls periodically and analyzes all available markets; the sports pipeline runs continuously, reacts to WebSocket game state events in near real time, and targets only pre-identified game markets. The architectural recommendation is a clean separation: a new `SportsTrader` orchestrator with its own `SportsExecutor`, `SportsWS` connector, and `SportsDataAPI` connector — all sharing only the existing Polymarket CLOB execution layer and `Polymarket` class unchanged.

The recommended approach is to build incrementally: start with the WebSocket consumer and game state data model, add sports market discovery via slug-based Gamma lookup (bypassing the general Chroma RAG entirely), then layer in pre-game analysis before introducing live in-game trade execution. This ordering is dictated by hard build dependencies — no component downstream of the WebSocket can be tested or validated until the WS consumer reliably delivers and normalizes game state events. The stack requires minimal new dependencies: `websocket-client==1.9.0` for the WS consumer thread, BallDontLie SDK for NBA/NFL/MLB live stats, and API-Sports REST for full multi-sport coverage. All other required packages (`aiohttp`, `tenacity`, `requests`) are already present in requirements.txt.

The dominant risks are operational rather than conceptual. A confirmed server-side Polymarket WebSocket bug causes silent data freeze 18-22 minutes into sessions — ping/pong remains healthy while game state messages stop arriving, making stale-state trades the primary failure mode. LLM call latency (3-30s) also threatens the value proposition of sub-5-second in-game reaction. Both risks have known mitigations: a message-gap watchdog for the first, and a pre-game cached probability fast-path for the second. A third structural risk — budget race conditions between concurrent pipelines — requires a `BudgetCoordinator` pattern before both pipelines run live simultaneously.

## Key Findings

### Recommended Stack

The sports pipeline is buildable on top of existing dependencies with two targeted additions. The `websocket-client` library (thread-based, synchronous) is the right choice for the WS consumer because the existing `Trader` class is synchronous and adding an async rewrite of LangChain agent calls is out of scope. The WS consumer runs in a daemon thread and communicates via `queue.Queue` to the main sports trading loop — no asyncio rewrite required at the top level. However, the ARCHITECTURE.md pattern shows `SportsWS` using asyncio internally with `websockets==12.0` (already in requirements); this is valid for an isolated async loop within the WS module.

The only meaningful external additions are sports data APIs. API-Sports (REST, no SDK) is the only single source covering the full Polymarket sports catalog (NFL, NBA, MLB, NHL, CFB, CBB, soccer, esports, tennis). BallDontLie's official Python SDK supplements this with 1-second live updates for NBA/NFL/MLB specifically. The Odds API provides consensus external odds for value-bet detection (500 req/month free). No custom ML model is warranted — external odds data fed directly to the LLM is sufficient and avoids months of backtesting infrastructure work.

**Core technologies:**
- `websocket-client==1.9.0`: Sports WebSocket consumer in daemon thread — fits synchronous Trader architecture without async rewrite
- `websockets==12.0` (existing): Async WS pattern within `SportsWS` module — DO NOT upgrade past 12.x; Python 3.9 incompatible with 13.x+
- `aiohttp==3.13.3` (upgrade from 3.10.0): Concurrent async HTTP for sports API calls in pre-game pipeline
- `tenacity==9.1.4` (upgrade from 8.5.0): Retry logic for WS reconnect and API backoff with jitter
- `balldontlie==0.1.6` (new): Official Python SDK, NBA/NFL/MLB live stats, 1-second update frequency
- **API-Sports** (REST, no SDK): Full multi-sport coverage including NHL, soccer, esports — use `requests`/`aiohttp` directly
- **The Odds API v4** (REST, no SDK): Consensus external odds from 40+ bookmakers for value-bet signal

**What NOT to use:** `sportsipy`/`sportsreference` (abandoned Jan 2021, 90 open issues); `websockets>=13.x` (Python 3.9 incompatible); `asyncio.run()` at the top of the sports pipeline (event loop conflicts); custom ML odds model (out of scope).

### Expected Features

The sports pipeline has nine table-stakes features without which it is non-functional, and a further set of differentiators that create a genuine trading edge. The MVP definition is clear: WebSocket client with reconnect, sports market identification via slug lookup, live game state normalization, sports-specific LLM prompts, pre-game positioning pipeline, external stats API integration, in-game autonomous execution triggered by score changes, configurable sports budget allocation, and graceful coexistence with the general pipeline. All nine must be present for v1.

Post-v1 additions (v1.x): period/quarter transition signals, odds comparison value-bet detection, per-sport budget caps, and game status edge-case handling (OT, delays, forfeits). Deferred to v2+: sport-specific prompt tuning per category, sports-specific confidence weighting, multi-provider API fallback.

**Must have (table stakes — v1 required):**
- Sports WebSocket client with reconnect and message-gap watchdog — without this the pipeline has no data
- Sports market identification and metadata tagging (league, teams, game slug) — prerequisite for all trading
- Live score and game state normalization across sports — core data model for all decisions
- Sports-specific LLM prompts with game context injection — general prompts lack score/period awareness
- Pre-game trade positioning pipeline — captures pre-game volume; validates stats API integration
- External stats API integration (at minimum one: The Odds API or API-Sports) — LLM lacks current season data
- In-game autonomous trade execution triggered by score-change threshold — the primary value proposition
- Configurable sports budget allocation (`SPORTS_BUDGET_FRACTION`) — prevents wallet exhaustion
- Graceful coexistence with general trading pipeline — crash isolation; independent budget enforcement

**Should have (competitive edge — v1.x):**
- Score-change triggered trade signals with debounce and cooldown — prevents LLM queue saturation
- Odds comparison vs. Polymarket price for value-bet detection — identifies market mispricing
- Period/quarter/halftime transition handling as discrete trade signals — predictable volatility windows
- Game status edge-case handling (OT, rain delays, forfeits) — avoids trading on suspended markets
- Configurable per-sport budget caps — limits exposure to high-variance sports (esports, tennis)

**Defer (v2+):**
- Sport-specific prompt context injection per sport category — single generalized sports prompt is sufficient for v1 validation
- Confidence-weighted position sizing tuned specifically for sports — existing general weighting is adequate for v1
- Multi-provider stats API fallback — single provider is sufficient for v1; add after reliability issues are observed

**Anti-features to reject:** Custom ML odds model, backtesting framework, social/sentiment analysis, manual trade confirmation popups, market-making for sports, web UI/dashboard, cross-platform arbitrage (Polymarket + Kalshi + sportsbooks).

### Architecture Approach

The sports pipeline is built as a parallel lane to the existing general pipeline, sharing only the Polymarket CLOB execution layer. A new `SportsTrader` orchestrator (mirroring `Trader`) dispatches to a new `SportsExecutor` (mirroring `Executor`), consumes game state from `SportsWS` via an `asyncio.Queue`, and supplements decisions with `SportsDataAPI` REST calls. The key insight is that sports market discovery is slug-based, not RAG-based — the Polymarket WS already provides the game slug, which maps directly to a Gamma API event lookup. Chroma is bypassed entirely for sports. New Pydantic models (`SportGameState`, `SportsMarketTag`) extend `objects.py` rather than duplicating it.

**Major components:**
1. `SportsWS` (`connectors/sports_ws.py`) — asyncio WS client; PING/PONG heartbeat; message-gap watchdog; emits `SportGameState` to queue
2. `SportsDataAPI` (`connectors/sports_data.py`) — REST client for external stats/odds (team records, H2H history, live odds)
3. `GameStateRouter` — state machine (PREGAME / LIVE / ENDED) that determines which pipeline branch to invoke per game event
4. `SportsExecutor` (`application/sports_executor.py`) — LLM agent with sport-aware prompts; calls `llm.ainvoke()` to avoid blocking event loop
5. `SportsTrader` (`application/sports_trade.py`) — orchestrator; owns budget split; merges WS state + stats context before LLM call; dispatches to Polymarket execution
6. `SportGameState` / `SportsMarketTag` (`utils/objects.py` extended) — Pydantic models for game state and game-to-market mapping

**Build order (hard dependencies):** `SportGameState` → `SportsWS` (parallel with `SportsDataAPI`) → `SportsMarketTag` → `SportsExecutor` → `GameStateRouter` → `SportsTrader` → CLI integration → budget split configuration.

**Key patterns:**
- Asyncio queue decouples WS producer from trade consumer — WS can restart independently
- Game state machine branches pre-game vs. in-game logic explicitly per `gameId`
- Slug-based Gamma lookup replaces RAG — faster, more reliable for known games
- All blocking calls (`LLM.invoke`, synchronous HTTP) must use `ainvoke()` or `run_in_executor` to avoid dropping WS heartbeats

### Critical Pitfalls

1. **Silent WebSocket data freeze (18-22 min pattern)** — Polymarket WS enters zombie state: ping/pong passes but no game messages arrive. Mitigation: maintain `last_game_message_at` separately from `last_pong_at`; watchdog fires reconnect at 5-minute data gap; on reconnect, re-derive state from first message rather than resuming from cached state. This is a confirmed server-side bug (GitHub issue #26 in real-time-data-client repo).

2. **LLM latency makes live decisions stale** — GPT-4o averages 3-8s per call, can spike to 30-80s during incidents. Sub-5s total latency is required to capture in-game mispricing. Mitigation: two-layer decision architecture — fast path uses pre-computed pre-game LLM probabilities + threshold check (no live LLM call); slow path invokes LLM only for major state changes (late turnover, OT start, injury). Use `gpt-5-mini` for live decisions (3x faster than GPT-4o).

3. **Budget race condition between concurrent pipelines** — Both pipelines independently read `get_usdc_balance_report()` and can over-allocate. Mitigation: `BudgetCoordinator` singleton with reservation map; for MVP, a simpler `sports_execution_in_progress` mutex flag prevents overlap.

4. **gameId-to-market mapping instability** — WS `gameId` does not map 1:1 to Polymarket market/token IDs; slug formats differ between WS and Gamma; one game can have multiple markets (winner, OT, totals). Mitigation: build explicit `ws_slug → [market_ids]` lookup at pipeline startup via Gamma query; refresh every 30 minutes; skip/log events with no mapping rather than guessing.

5. **asyncio event loop blocking from synchronous LangChain calls** — Existing `self.llm.invoke()` is synchronous; calling it inside an async WS handler drops heartbeats and disconnects. Mitigation: use `self.llm.ainvoke()` throughout the sports async pipeline; run any unavoidable sync calls via `run_in_executor`.

6. **Trading resolved markets** — Markets remain technically open during the 2-hour settlement challenge window after a game ends. Mitigation: halt all new orders on `ended: true`; implement pre-expiry blackout (stop trading N minutes before scheduled market close); cancel orders placed in the 60 seconds before `ended` message arrives.

7. **Chroma RAG misfit for sports** — General pipeline's RAG filter scores sports markets poorly against the general embedding corpus; sports candidates get filtered out before LLM sees them. Mitigation: sports pipeline bypasses Chroma entirely; uses rule-based filtering (league tag, active status, volume threshold) then slug lookup.

## Implications for Roadmap

Based on research dependencies and pitfall-to-phase mapping, a 4-phase structure is recommended. Phases are ordered by hard build dependencies, not arbitrary milestones.

### Phase 1: Sports WebSocket Foundation

**Rationale:** Nothing in the sports pipeline can be built or tested without reliable, normalized game state. The WS consumer and data models are zero-dependency starting points. The silent-freeze and async-blocking pitfalls must be addressed here — if deferred, they corrupt all downstream components.

**Delivers:** Reliable `SportGameState` stream from Polymarket WS; message-gap watchdog; data model for all downstream use; game state router (pre-game/live/ended branching).

**Features addressed:** Sports WebSocket connection with reconnect; live score/game state ingestion; game state machine foundation.

**Pitfalls to address:** Silent WebSocket data freeze (Pitfall 1); asyncio event loop blocking from synchronous calls (Pitfall 5).

**Stack used:** `websocket-client==1.9.0` (thread-based) OR `websockets==12.0` async pattern; `SportGameState` Pydantic model; `asyncio.Queue` producer/consumer pattern.

**Research flag:** Standard pattern — asyncio WS + Pydantic is well-documented. No research phase needed; implementation can proceed directly from ARCHITECTURE.md patterns.

### Phase 2: Sports Market Discovery and Pipeline Architecture

**Rationale:** Once game state flows reliably, the pipeline must know which Polymarket markets correspond to which games. This slug-based discovery layer is a prerequisite for any trade execution. The budget coordination problem must also be solved here — before any live execution — to prevent the race condition that can drain the wallet.

**Delivers:** `ws_slug → [market_ids]` mapping table built from Gamma API at startup; sports market filtering (rule-based, not RAG); `SportsMarketTag` data model; `BudgetCoordinator` with `SPORTS_BUDGET_FRACTION` enforcement; `SportsDataAPI` REST connector for team stats and pre-match odds.

**Features addressed:** Sports market identification and metadata tagging; graceful pipeline coexistence; sports budget allocation; external stats API integration (connector layer).

**Pitfalls to address:** gameId-to-market mapping instability (Pitfall 4); budget race condition (Pitfall 3); Chroma RAG misfit for sports (Pitfall 7).

**Stack used:** API-Sports (REST via `aiohttp`) or The Odds API; `requests` for sync pre-game fetches; `python-dotenv` for new API key env vars.

**Research flag:** May benefit from a research phase to validate slug normalization patterns across all 9 sport types against live Polymarket data before committing to the mapping strategy.

### Phase 3: Pre-Game Analysis and LLM Integration

**Rationale:** Pre-game trading captures the majority of sports prediction market volume and is lower risk than live trading (no sub-second latency requirement). Building and validating the sports LLM pipeline here — before adding live trading — isolates prompt quality from execution speed concerns. This phase also establishes the pre-computed probability cache that the fast-path live trading in Phase 4 depends on.

**Delivers:** `SportsExecutor` with sports-specific LLM prompts; pre-game trade positioning pipeline; LLM probability cache per game/market; `SportsTrader` orchestrator (pre-game branch only); confidence-weighted candidate selection for sports markets; end-to-end dry-run for pre-game trades.

**Features addressed:** Sports-specific LLM prompts with game context injection; pre-game trade positioning pipeline; external stats API integration (connected to LLM pipeline); configurable sports budget allocation (enforced through `SportsTrader`).

**Pitfalls to address:** LLM latency for live decisions (Pitfall 2) — pre-game cache architecture established here; asyncio blocking in `SportsExecutor` — use `llm.ainvoke()` throughout.

**Stack used:** LangChain `ainvoke()` (async); `Prompter` sports methods; BallDontLie SDK for NBA/NFL/MLB; API-Sports for NHL/soccer/esports.

**Research flag:** Standard pattern — extends existing LangChain/LangGraph prompt infrastructure. No research phase needed; follow ARCHITECTURE.md `SportsExecutor` patterns directly.

### Phase 4: Live In-Game Trading Engine

**Rationale:** This is the highest-complexity, highest-risk phase and is deferred until the full infrastructure is validated in dry-run. Live in-game execution requires all previous phases to be stable. The fast-path (cached probabilities + threshold check) established in Phase 3 enables this phase to avoid the LLM latency trap. All edge cases (OT, game ended guard, order cancellation on `ended`) are addressed here.

**Delivers:** In-game score-change triggered trade execution with debounce and cooldown; fast-path decision using pre-game cached probabilities; game-ended guard cancelling orders on `ended: true`; per-game re-evaluation cooldown (configurable threshold); concurrent game handling; live in-game dry-run validation; full end-to-end live trading mode.

**Features addressed:** In-game autonomous trade execution; score-change triggered signals; game status edge-case handling; period/quarter transition handling (v1.x); odds comparison vs. Polymarket price (v1.x).

**Pitfalls to address:** LLM latency making live decisions stale (Pitfall 2); trading resolved markets post-game (Pitfall 6); budget race conditions under concurrent live games (Pitfall 3 — BudgetCoordinator must be live, not flag-based).

**Stack used:** `asyncio.gather()` for concurrent order submission; CLOB rate limit tracking (60 orders/min shared across pipelines); `gpt-5-mini` for fast live decisions.

**Research flag:** Needs a research phase before implementation. Score-change debounce thresholds, per-sport cooldown tuning, and CLOB rate limit interaction under concurrent game load are nontrivial and need validation against real Polymarket data.

### Phase Ordering Rationale

- Phase 1 before Phase 2: Market discovery has no WS events to react to until game state flows; the `SportGameState` model is required by `SportsMarketTag`.
- Phase 2 before Phase 3: `SportsExecutor` needs to know which markets to score; the stats API connector is built in Phase 2 and consumed in Phase 3.
- Phase 3 before Phase 4: Live trading requires the pre-game probability cache (fast path); without it, every live trigger invokes LLM at 3-8s latency, queue saturates, and trades fire on stale prices.
- Budget coordination in Phase 2 (not Phase 4): The race condition is possible the moment both pipelines can execute concurrently — must be enforced before any live orders go through.
- Chroma bypass decided in Phase 2 (not Phase 1): The decision affects market discovery architecture; confirming slug-based lookup works for all 9 sport types should be validated before the general pipeline's RAG is permanently bypassed for sports.

### Research Flags

Phases needing deeper research during planning:
- **Phase 2:** Slug normalization across all 9 sport types — Polymarket WS slug format vs. Gamma API slug format may differ by sport; must validate with live data before committing to the mapping architecture
- **Phase 4:** Score-change debounce thresholds and per-sport cooldown values — no established benchmarks; needs empirical tuning against real game data; consider a dry-run observability phase before live execution

Phases with standard patterns (skip research-phase):
- **Phase 1:** asyncio WebSocket + Pydantic data modeling — fully documented in ARCHITECTURE.md with working code examples; implementation can proceed directly
- **Phase 3:** LangChain sports prompt extension — extends existing `Executor`/`Prompter` patterns; the `ainvoke()` async migration is well-documented in LangChain docs

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core dependencies verified against PyPI, requirements.txt, and Python 3.9 compatibility. Sports API pricing tiers may change — budget for paid tier if free tier limits are hit in production. |
| Features | MEDIUM | Polymarket sports WS fields and message format are HIGH confidence (official docs). Feature prioritization for sports bots is MEDIUM — based on multiple secondary sources; no direct access to competitor implementations. |
| Architecture | HIGH | Based on direct codebase inspection of `trade.py`, `executor.py`, `gamma.py`, `objects.py` + official Polymarket WS docs. Build order and component boundaries are well-defined. |
| Pitfalls | HIGH | Silent WS freeze confirmed by GitHub issue #26 in Polymarket's own repo. Asyncio blocking documented in LangChain GitHub issues. Budget race condition and gameId mapping failure are inferred from codebase analysis but not directly observed in this codebase. |

**Overall confidence:** HIGH for the architectural approach and implementation path; MEDIUM for sports API reliability and multi-sport slug normalization specifics.

### Gaps to Address

- **Slug normalization across all 9 sports:** The exact format of WS slugs vs. Gamma API event slugs for NHL, CFB, CBB, soccer, esports, and tennis has not been validated with live data. Address in Phase 2 — do not assume NFL/NBA patterns generalize.
- **Score-change threshold tuning:** Optimal debounce thresholds (how many points = significant change triggering LLM re-evaluation) are sport-specific and unknown without empirical data. Expose as env vars from day one; do not hardcode.
- **CLOB rate limit interaction under concurrent live games:** 60 orders/minute is shared between sports and general pipelines. During peak hours (NFL Sunday afternoon, 8+ concurrent games), the sports pipeline alone could saturate the limit. Validate against real Polymarket trading session data in Phase 4 dry-run.
- **API-Sports free tier sufficiency:** 100 req/day per API may be insufficient for multi-sport live trading across a full NFL Sunday card. Budget for paid tier ($10/month) before Phase 3 begins.
- **`gpt-5-mini` model availability:** PITFALLS.md references `gpt-5-mini` as the fast-path model; verify this model ID is available and correctly configured in the existing `ChatOpenAI` setup (the codebase already handles `temperature=1` for gpt-5 models — confirm sports pipeline inherits this pattern).

## Sources

### Primary (HIGH confidence)
- Polymarket Sports WebSocket official docs — message format, heartbeat protocol, field definitions, supported sports
- Polymarket CLOB API docs — rate limits (60 orders/min, 3000/10 min), execution patterns
- Polymarket real-time-data-client GitHub issue #26 — confirmed silent WS freeze bug (18-22 min pattern)
- `websockets` readthedocs v12 — async reconnect pattern, asyncio integration
- LangChain GitHub issues #8494, #9014 — asyncio blocking from synchronous `invoke()` calls
- Existing codebase: `agents/application/trade.py`, `agents/application/executor.py`, `agents/connectors/chroma.py`, `agents/polymarket/gamma.py`, `agents/utils/objects.py`
- Existing `requirements.txt` — confirmed versions of `websocket-client`, `websockets`, `aiohttp`, `tenacity`
- PyPI: `websocket-client==1.9.0`, `websockets==12.0/16.x`, `aiohttp==3.13.3`, `tenacity==9.1.4`, `balldontlie==0.1.6`

### Secondary (MEDIUM confidence)
- api-sports.io official docs — 100 req/day free tier, real-time every 15s, 15yr historical data, full sport coverage
- the-odds-api.com v4 docs — 500 req/month free, live scores ~30s update, 40+ bookmakers, historical data to 2020
- balldontlie.io docs — NBA/NFL/MLB, 1-second live updates, official Python SDK
- OpenAI latency optimization guide — `gpt-5-mini` speed comparison, P99 latency benchmarks
- OpticOdds blog — AI bot architecture patterns in sports betting

### Tertiary (LOW confidence)
- QuantVPS blog — Polymarket sports bot patterns (unverified third-party claims; used only for feature landscape)
- ReadWrite, Risk.inc — sports betting bot feature landscape (review site; low verification bar)
- CryptoNews — Polymarket strategies overview (journalistic; useful only for competitive context)

---
*Research completed: 2026-03-03*
*Ready for roadmap: yes*

# Architecture Research

**Domain:** Live sports trading pipeline integration into an existing layered agent-based Polymarket bot
**Researched:** 2026-03-03
**Confidence:** HIGH (based on direct codebase inspection + official Polymarket docs verification)

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          APPLICATION LAYER                                    │
├───────────────────────────────────┬──────────────────────────────────────────┤
│  EXISTING (General Pipeline)      │  NEW (Sports Pipeline)                    │
│                                   │                                           │
│  ┌──────────────────────────┐     │  ┌──────────────────────────────────────┐ │
│  │  Trader                  │     │  │  SportsTrader                        │ │
│  │  one_best_trade()        │     │  │  run_pre_game()                      │ │
│  │  analyze_event_url()     │     │  │  run_in_game_loop()                  │ │
│  └──────────┬───────────────┘     │  └────────────┬─────────────────────────┘ │
│             │                     │               │                           │
│  ┌──────────▼───────────────┐     │  ┌────────────▼─────────────────────────┐ │
│  │  Executor (LLM agent)    │     │  │  SportsExecutor                      │ │
│  │  build_trade_candidates()│     │  │  score_sports_market()               │ │
│  │  source_best_trade()     │     │  │  build_sports_candidates()           │ │
│  └──────────────────────────┘     │  └──────────────────────────────────────┘ │
├───────────────────────────────────┴──────────────────────────────────────────┤
│                          CONNECTOR LAYER                                      │
├──────────┬──────────────┬──────────────────┬────────────────────────────────┤
│  Gamma   │  Chroma RAG  │  News            │  NEW: SportsConnectors          │
│  (HTTP)  │  (embeddings)│  (NewsAPI)       │                                 │
│          │              │                  │  ┌──────────────┐               │
│          │              │                  │  │ SportsWS     │               │
│          │              │                  │  │ (asyncio WS  │               │
│          │              │                  │  │  lifecycle)  │               │
│          │              │                  │  └──────┬───────┘               │
│          │              │                  │         │                        │
│          │              │                  │  ┌──────▼───────┐               │
│          │              │                  │  │ SportsDataAPI│               │
│          │              │                  │  │ (REST odds + │               │
│          │              │                  │  │  team stats) │               │
│          │              │                  │  └──────────────┘               │
├──────────┴──────────────┴──────────────────┴────────────────────────────────┤
│                          POLYMARKET EXECUTION LAYER (shared)                  │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │  Polymarket (py-clob-client)                                          │    │
│  │  execute_market_order_for_token() — used by both pipelines            │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────────────────────────┤
│                          DATA MODEL LAYER (shared + extended)                 │
│                                                                               │
│  Existing: SimpleEvent, SimpleMarket, CandidateTrade, Trade (Pydantic)       │
│  New:      SportGameState, SportsMarketTag, SportsCandidateTrade (extends)   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Layer |
|-----------|----------------|-------|
| `SportsTrader` | Orchestrates the sports pipeline; decides pre-game vs in-game mode; owns budget split | Application |
| `SportsExecutor` | LLM agent for sports markets; sports-specific prompts; game context injection | Application |
| `SportsWS` | Asyncio websocket client for `wss://sports-api.polymarket.com/ws`; PING/PONG heartbeat; reconnect loop; emits `SportGameState` events | Connector |
| `SportsDataAPI` | REST client for external stats/odds (team records, line movement, historical matchups) | Connector |
| `SportGameState` | Pydantic model for a single WS message: `gameId`, `leagueAbbreviation`, `slug`, `homeTeam`, `awayTeam`, `status`, `score`, `period`, `elapsed`, `live`, `ended`, `finished_timestamp` | Data Model |
| `SportsMarketTag` | Links a Polymarket market ID to a game: `game_id`, `market_id`, `league`, `teams`, `game_start_iso`, `is_pregame` | Data Model |
| `Polymarket` | CLOB execution (unchanged) — sports orders go through identical `execute_market_order_for_token()` path | Execution |
| `Executor` (existing) | Unchanged; general pipeline continues in parallel | Application |
| `Gamma` (existing) | Unchanged; used by both pipelines to fetch market data | Connector |
| `Chroma` (existing) | Unchanged; general pipeline only; sports pipeline does not need RAG filtering because WS directly provides the game slug for market lookup | Connector |

## Recommended Project Structure

```
agents/
├── application/
│   ├── trade.py           # existing — unchanged
│   ├── executor.py        # existing — unchanged
│   ├── prompts.py         # existing — add sports prompt methods here
│   ├── sports_trade.py    # NEW: SportsTrader orchestrator
│   └── sports_executor.py # NEW: SportsExecutor with game-context LLM prompts
│
├── connectors/
│   ├── chroma.py          # existing — unchanged
│   ├── news.py            # existing — unchanged
│   ├── search.py          # existing — unchanged
│   ├── sports_ws.py       # NEW: async WS client, heartbeat, reconnect
│   └── sports_data.py     # NEW: REST client for external odds/stats API
│
├── polymarket/
│   ├── gamma.py           # existing — unchanged
│   └── polymarket.py      # existing — unchanged (shared execution)
│
└── utils/
    ├── objects.py         # existing — extend with SportGameState, SportsMarketTag
    └── utils.py           # existing — add sports category inversion helper
```

### Structure Rationale

- **`sports_trade.py`/`sports_executor.py` in `application/`:** Mirrors the existing `trade.py`/`executor.py` split. Both pipelines share the same layer conventions.
- **`sports_ws.py` in `connectors/`:** Websocket is a connector to an external data source, not business logic. Keeps `connectors/` as the integration boundary.
- **`sports_data.py` in `connectors/`:** External REST API for odds/stats follows the same pattern as `news.py`.
- **`objects.py` extended, not duplicated:** New Pydantic models added alongside existing ones. `CandidateTrade` can be subclassed or extended with optional sports fields rather than creating an entirely new parallel model.
- **`prompts.py` extended:** Sports prompts live alongside general prompts; `Prompter` class gains `sports_superforecaster()` and `sports_one_best_trade()` methods.

## Architectural Patterns

### Pattern 1: Asyncio Event Loop with Queue-Based Decoupling

**What:** The WS client (`SportsWS`) runs in an asyncio event loop and puts parsed `SportGameState` objects into an `asyncio.Queue`. A separate consumer coroutine drains the queue and decides whether to trigger a trade evaluation.

**When to use:** Whenever a long-lived connection (websocket) needs to drive short-duration actions (trade evaluation + HTTP calls) without the consumer blocking the producer. This is the standard pattern for market data pipelines.

**Trade-offs:** Adds queue as an intermediate; simplifies reconnect logic because the producer can be restarted independently. Python's GIL is not a problem here because all work is I/O-bound.

**Example:**
```python
import asyncio
import websockets
import json
from agents.utils.objects import SportGameState

class SportsWS:
    WS_URL = "wss://sports-api.polymarket.com/ws"

    def __init__(self, game_state_queue: asyncio.Queue):
        self._queue = game_state_queue

    async def run(self):
        # websockets async-for pattern auto-reconnects on disconnect
        async for ws in websockets.connect(self.WS_URL):
            try:
                async for raw_message in ws:
                    if raw_message == "ping":
                        await ws.send("pong")
                        continue
                    try:
                        data = json.loads(raw_message)
                        state = SportGameState(**data)
                        await self._queue.put(state)
                    except Exception:
                        pass  # malformed message, continue
            except websockets.ConnectionClosed:
                continue  # outer async-for handles reconnect
```

### Pattern 2: Game State Machine (Pre-Game vs In-Game Branching)

**What:** On each `SportGameState` event, the consumer determines which pipeline to invoke based on state transitions. The state machine has three states: `PREGAME` (not started), `LIVE` (in progress), `ENDED`. State transitions trigger different actions.

**When to use:** Whenever the same stream of events drives fundamentally different business logic depending on current state. Sports markets have qualitatively different trade signals pre-game (historical stats, odds) vs in-game (score delta, momentum).

**Trade-offs:** Explicit; state lives in a dict keyed by `gameId`. Risk of stale state if WS disconnects mid-game — mitigate by re-deriving state from the first message after reconnect rather than persisting across sessions.

**Example:**
```python
class GameStateRouter:
    def __init__(self):
        self._known_states: dict[str, str] = {}  # gameId -> "PREGAME"|"LIVE"|"ENDED"

    def route(self, state: SportGameState) -> str:
        """Returns 'PRE_GAME', 'IN_GAME', 'ENDED', or 'NO_OP'."""
        prev = self._known_states.get(state.game_id, "PREGAME")

        if state.ended:
            self._known_states[state.game_id] = "ENDED"
            return "ENDED"
        if state.live and prev == "PREGAME":
            self._known_states[state.game_id] = "LIVE"
            return "IN_GAME_START"   # kickoff signal — evaluate markets now
        if state.live:
            self._known_states[state.game_id] = "LIVE"
            return "IN_GAME"         # score/period update
        return "NO_OP"
```

### Pattern 3: Slug-Based Market Lookup (Bypass RAG for Sports)

**What:** The WS message includes a `slug` field (e.g., `nfl-sf-49ers-kc-chiefs-2025-02-09`). The Gamma API supports querying events by slug. Sports markets are identified by direct slug lookup, not by RAG/embedding similarity. This is faster and more reliable than embedding-based retrieval for sports (the market title IS the slug).

**When to use:** Always for sports pipeline. RAG filtering is designed for "find what to trade among everything" — sports mode already knows exactly which game it is watching.

**Trade-offs:** Bypasses Chroma entirely for sports market identification. Still uses `Gamma.get_events(querystring_params={"slug": slug})` which already exists in the codebase (`_resolve_event_by_slug` in `Trader`). The existing method can be reused directly in `SportsTrader`.

**Example:**
```python
# Already exists in agents/application/trade.py — reuse in SportsTrader
from agents.application.trade import Trader  # or extract _resolve_event_by_slug to utils
```

## Data Flow

### Pre-Game Flow (triggered once before game starts)

```
[Scheduler / cron / startup scan]
    |
    v
[Gamma API] -- query events by category="sports", active=true --> [sports event list]
    |
    v
[SportsDataAPI] -- fetch team stats, odds, matchup history for each event --> [stats context]
    |
    v
[SportsExecutor.score_sports_market()] -- sports-specific LLM prompt + stats context
    |
    v
[CandidateTrade list] -- confidence-weighted allocation (existing logic)
    |
    v
[Polymarket.execute_market_order_for_token()] -- same CLOB execution path
```

### In-Game Flow (triggered by websocket state change)

```
[wss://sports-api.polymarket.com/ws]
    |
    | SportGameState (score, period, live, ended, slug)
    v
[SportsWS producer] --> asyncio.Queue
    |
    v
[GameStateRouter.route()] -- IN_GAME_START | IN_GAME | ENDED
    |
    +-- IN_GAME_START / IN_GAME (score delta threshold met):
    |       |
    |       v
    |   [Gamma._resolve_event_by_slug(slug)] -- find Polymarket event
    |       |
    |       v
    |   [SportsDataAPI] -- fetch live odds update (optional, if score changed significantly)
    |       |
    |       v
    |   [SportsExecutor.score_sports_market(game_state + stats + live_odds)]
    |       |
    |       v
    |   [Polymarket.execute_market_order_for_token()]
    |
    +-- ENDED:
            |
            v
        [Clean up game state; log final result; no new orders]
```

### Shared Execution Path

Both pipelines converge at the same execution layer:

```
CandidateTrade
    |
    v
Trader._finalize_candidates() OR SportsTrader._finalize_sports_candidates()
    |
    v
Polymarket.resolve_token_for_outcome()
    |
    v
Polymarket.execute_market_order_for_token()    <-- identical for both pipelines
    |
    v
py-clob-client CLOB API
```

### Budget Split Data Flow

```
[USDC wallet balance]
    |
    v
[SPORTS_BUDGET_FRACTION env var] -- e.g., 0.30 (30% for sports, 70% for general)
    |
    +-- sports_budget = balance * SPORTS_BUDGET_FRACTION
    |       |
    |       v
    |   SportsTrader._finalize_sports_candidates(budget=sports_budget)
    |
    +-- general_budget = balance * (1 - SPORTS_BUDGET_FRACTION)
            |
            v
        Trader._finalize_candidates(usdc_balance=general_budget)
```

The two pipelines do NOT share a global mutex on the USDC balance at trade time. Each reads the wallet balance at the start of its run and allocates from its configured fraction. For a bot running both pipelines concurrently, this is acceptable: overshooting the total budget by the configured fractions is bounded and predictable.

## Scaling Considerations

This is a single-bot system. Scaling concerns are about throughput and reliability during live games, not user concurrency.

| Concern | Current state | At peak (6+ concurrent games) |
|---------|---------------|-------------------------------|
| WS message rate | 1 ws stream, all games, push-only | Single connection handles all games; no fan-out needed |
| LLM call latency | 2-3s per market (superforecast + trade) | In-game trigger must debounce: only re-evaluate if score delta crosses threshold; else queue fills faster than LLM drains it |
| CLOB execution | Sequential per candidate; ~1-2s per order | Sports trades are typically 1-3 markets per game; throughput is fine |
| Market lookup | Gamma HTTP GET by slug | Cache slug→event_id mapping after first lookup; invalidate on game end |

### Scaling Priorities

1. **First bottleneck: LLM call throughput during concurrent live games.** If 4 games score simultaneously, 4 in-game evaluations queue up. Mitigation: debounce (only trigger if score delta > N points in last M seconds), and set a per-game re-evaluation cooldown (e.g., 60 seconds minimum between trades on the same market).

2. **Second bottleneck: Score delta debounce logic becoming too conservative or too aggressive.** This is a product tuning problem, not an architecture problem. Expose the threshold as an env var.

## Anti-Patterns

### Anti-Pattern 1: Blocking the Event Loop with Synchronous HTTP Calls

**What people do:** Call `requests.get()` or `httpx.Client.get()` (synchronous) inside an `async` coroutine that is supposed to handle websocket messages.

**Why it's wrong:** Blocks the asyncio event loop during the HTTP call. If a Gamma API call takes 2 seconds, all incoming WS messages accumulate unprocessed. The PING/PONG deadline (10 seconds) may be missed, causing disconnection.

**Do this instead:** Use `httpx.AsyncClient` for any HTTP calls made inside asyncio context. The existing `httpx.Client` in `GammaMarketClient` is synchronous — run it in a thread pool executor (`loop.run_in_executor`) or create an async variant specifically for sports use: `AsyncGammaClient`. The LLM call via LangChain should be run via `asyncio.to_thread()` for the same reason.

### Anti-Pattern 2: Triggering a Trade on Every Websocket Message

**What people do:** Call `SportsExecutor.score_sports_market()` (which invokes two LLM calls) on every incoming `SportGameState` message.

**Why it's wrong:** The WS emits updates on every score, period change, possession change (NFL/CFB), and match-start. During an active NFL game this can be dozens of messages per minute. Two LLM calls per message = hundreds of API calls per hour, most redundant.

**Do this instead:** Implement a per-game evaluation cooldown and a score-delta threshold. Only re-evaluate when: (a) the game goes live for the first time (`IN_GAME_START`), (b) the score changes by more than N points since last evaluation, or (c) period transitions occur (halftime, 4th quarter, OT). Track `last_evaluated_score` and `last_evaluated_at` per `gameId`.

### Anti-Pattern 3: Reusing the Chroma RAG Filter for Sports Market Discovery

**What people do:** Feed sports markets into `Chroma.markets()` using the same general prompt ("filter these markets for the ones you will be best at trading on profitably").

**Why it's wrong:** The general RAG filter works by embedding similarity to a general prompt. Sports markets cluster together in embedding space regardless of which game they cover. RAG adds no selection value when the bot is already watching a specific game via websocket.

**Do this instead:** Use slug-based direct lookup (`Gamma.get_events(querystring_params={"slug": slug})`) to find the markets for the game currently in play. Skip Chroma entirely for sports.

### Anti-Pattern 4: Treating Sports Mode as a Flag on the Existing Trader

**What people do:** Add `if sports_mode: ...` branches throughout `Trader.one_best_trade()`.

**Why it's wrong:** The existing pipeline is polling-based and batch-oriented (run once, analyze all markets, pick best candidates). Sports mode is event-driven and continuous (react to each WS message indefinitely). Grafting continuous behavior onto a polling loop requires deep surgery and couples two fundamentally different execution models.

**Do this instead:** Create `SportsTrader` as a separate class that shares the `Polymarket` execution layer but has its own orchestration loop. The CLI entry point (`run_autonomous_trader`) dispatches to either `Trader` or `SportsTrader` based on a `--sports-mode` flag, but the internal logic is cleanly separated.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| `wss://sports-api.polymarket.com/ws` | Persistent asyncio websocket; `async for ws in websockets.connect()` pattern for auto-reconnect; PING→PONG every 5s | No auth required; streams all active sports; `websockets==12.0` already in requirements |
| External sports stats/odds API (e.g., The Odds API, API-Sports) | REST HTTP GET on demand; called during pre-game scan and optionally on significant score changes | Choose API with Python SDK or simple REST; cache responses per game; one-time per pre-game evaluation |
| Gamma API (`https://gamma-api.polymarket.com`) | Existing synchronous `httpx.Client`; extend with slug-based event lookup | Already implemented in `_resolve_event_by_slug()`; reuse directly |
| Polymarket CLOB (`https://clob.polymarket.com`) | Existing `py-clob-client`; no changes needed | Sports trades and general trades use the same CLOB path |

### Internal Boundaries

| Boundary | Communication Pattern | Notes |
|----------|-----------------------|-------|
| `SportsWS` → `SportsTrader` | `asyncio.Queue[SportGameState]` | Queue decouples WS producer from trade consumer; allows independent restart of WS without losing trade state |
| `SportsTrader` → `SportsExecutor` | Direct method call (synchronous, but run via `asyncio.to_thread()` from the event loop) | LLM calls are blocking; must not block the event loop |
| `SportsTrader` → `Polymarket` | Direct method call (same as general pipeline) | Sports and general pipelines share the same `Polymarket` instance; CLOB client is thread-safe per existing use |
| `SportsTrader` ↔ general `Trader` | Independent; no direct coupling | Both pipelines run in separate threads or processes; they share only the USDC wallet address |
| `SportsExecutor` → `Prompter` | Direct method call; new sports-specific methods added to `Prompter` class | Do not modify existing prompt methods; add alongside |
| `SportsWS` → `SportsDataAPI` | Not direct; `SportsTrader` calls both and merges context | WS provides game state; API provides stats; merged in `SportsTrader` before calling `SportsExecutor` |

## Build Order Implications

Components have the following dependency chain. Build in this order to enable testing at each step:

```
1. SportGameState (Pydantic model)          -- no deps; validates WS message format
        |
        v
2. SportsWS (websocket client)              -- depends on SportGameState; testable standalone
        |
        v
3. SportsDataAPI (REST stats connector)     -- independent; can be built in parallel with SportsWS
        |
        v
4. SportsMarketTag (Pydantic model)         -- links game to market; depends on understanding Gamma slug format
        |
        v
5. SportsExecutor (LLM agent)               -- depends on Prompter (sports prompt additions) + existing Executor patterns
        |
        v
6. GameStateRouter (state machine)          -- depends on SportGameState; pure logic; highly testable
        |
        v
7. SportsTrader (orchestrator)              -- depends on all above + existing Polymarket execution
        |
        v
8. CLI integration (sports mode flag)       -- depends on SportsTrader; wires into scripts/python/cli.py
        |
        v
9. Budget split configuration               -- depends on SportsTrader; env var SPORTS_BUDGET_FRACTION
```

The existing category inversion (flipping `TRADE_EXCLUDE_SPORTS` behavior) is a prerequisite change that can be done in Step 1 alongside the data model work.

## Sources

- [Polymarket Sports WebSocket Overview](https://docs.polymarket.com/developers/sports-websocket/overview) — official docs; message format, heartbeat protocol, supported sports (HIGH confidence)
- [Polymarket Sports WebSocket Message Format](https://docs.polymarket.com/developers/sports-websocket/message-format) — official docs; field definitions (HIGH confidence)
- [websockets library documentation — async reconnect pattern](https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html) — `async for ws in connect()` pattern for auto-reconnect (HIGH confidence)
- [The Odds API](https://the-odds-api.com/) — sports odds REST API option; Python-compatible; covers all major sports (MEDIUM confidence)
- [API-Sports](https://api-sports.io/) — alternative stats API with real-time livescores and pre-match odds (MEDIUM confidence)
- Existing codebase: `agents/application/trade.py`, `agents/application/executor.py`, `agents/connectors/chroma.py`, `agents/polymarket/gamma.py`, `agents/utils/objects.py` — direct inspection (HIGH confidence)
- `requirements.txt`: `websockets==12.0`, `aiohttp==3.10.0`, `httpx==0.27.0`, `pydantic==2.8.2` already present — no new major dependencies needed for WS integration (HIGH confidence)

---
*Architecture research for: sports mode — live websocket trading pipeline integration into existing Polymarket agent bot*
*Researched: 2026-03-03*

# Stack Research

**Domain:** Sports data integration and live in-game trading for autonomous Polymarket bot
**Researched:** 2026-03-03
**Confidence:** HIGH (websocket), HIGH (HTTP clients), MEDIUM (sports APIs — pricing tiers change)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `websocket-client` | 1.9.0 | Polymarket sports WebSocket consumer | Already in requirements.txt (as 1.8.0). Thread-based with `run_forever()` and callback hooks — fits existing synchronous Trader architecture without requiring async rewrite. Supports Python 3.9+. Latest: 1.9.0 (Oct 2025). |
| `aiohttp` | 3.13.3 | Async HTTP for sports API polling | Already in requirements.txt. Python 3.9 compatible. Use for concurrent sports API calls when pre-game analysis needs to fan out to multiple endpoints simultaneously. |
| `tenacity` | 9.1.4 | Retry logic for WS reconnection and API calls | Already in requirements.txt (as 8.5.0). Upgrade to 9.1.4 (Feb 2026). Handles WS disconnects, API rate limit backoff, and transient HTTP failures. Supports both sync and async contexts. |

### Sports Data APIs

| Library / API | Version | Purpose | Why Recommended |
|---------------|---------|---------|-----------------|
| **API-Sports** (api-sports.io) | REST v3 | Live scores, fixtures, odds, team stats for NFL, NBA, MLB, NHL, soccer, tennis, esports | Broadest sport coverage matching Polymarket's full sports catalog. Free tier: 100 req/day per API (sufficient for research/dev). Paid plans start at $10/month. No Python SDK — use `requests` or `aiohttp` directly. Coverage: NFL, NBA, MLB, NHL, soccer (50+ leagues), tennis, esports. |
| **The Odds API** (the-odds-api.com) | REST v4 | Live and pre-game betting odds from 40+ bookmakers | Best odds source for calibrating Polymarket prices against consensus. Supports NFL, NBA, MLB, NHL, soccer, tennis. Live scores update ~30s. Free tier: 500 requests/month. No Python SDK — standard REST. Use as a signal for market mispricing. |
| **BallDontLie** | 0.1.6 (official Python SDK) | NBA, NFL, MLB live box scores and historical stats | Official Python SDK (`pip install balldontlie`). Live data updates every second during games. Free tier with generous limits. Covers NBA, NFL, MLB only — not NHL, soccer, or esports. Install: `pip install balldontlie`. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `requests` | 2.32.3 (already pinned) | Synchronous REST calls to sports APIs | Use for pre-game stat fetching in the existing synchronous pipeline. Already in requirements.txt. |
| `apscheduler` | 3.11.x | Cron-style scheduling for pre-game analysis triggers | Use if you need time-based triggers (e.g., "fetch stats 30 min before game start") separate from WS events. `AsyncIOScheduler` works with asyncio; `BackgroundScheduler` works in the current sync setup. Optional — the WS `status` field can also trigger analysis. |
| `python-dateutil` | 2.9.0 (already pinned) | Parse game start times from API responses | Already in requirements.txt. Sports APIs return varied timestamp formats. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pytest` (existing) | Unit tests for sports pipeline | Already installed. Mock WS messages using `unittest.mock` — no extra test library needed. |
| `python-dotenv` (existing) | Env var management for API keys | Already in requirements.txt. Add `API_SPORTS_KEY`, `ODDS_API_KEY`, `BALLDONTLIE_API_KEY` to `.env`. |

---

## Installation

```bash
# Upgrade existing packages to current versions
pip install "tenacity==9.1.4"
pip install "websocket-client==1.9.0"
pip install "aiohttp==3.13.3"

# Sports data API SDK (BallDontLie has official Python SDK)
pip install "balldontlie==0.1.6"

# Optional: if scheduling pre-game analysis by clock time
pip install "apscheduler==3.11.2"

# No pip install needed for API-Sports or The Odds API — use requests/aiohttp directly
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `websocket-client` (sync, `run_forever`) | `websockets` 16.x (asyncio) | If the entire trading pipeline were rewritten as async-first. `websockets` 16.x requires Python >=3.10 — incompatible with the stated Python 3.9 constraint. Do not use. |
| API-Sports (broadest sport coverage) | SportsDataIO | If budget is not a concern and you need enterprise SLAs. SportsDataIO covers more sports with cleaner data but costs significantly more. No official Python SDK — use REST. |
| API-Sports (broadest sport coverage) | MySportsFeeds | Free for non-commercial use, covers NFL/NBA/MLB/NHL only. Missing soccer and esports. Adequate if sports mode only targets North American leagues. |
| BallDontLie Python SDK | sportsipy / sportsreference | Do NOT use sportsipy. Last commit: January 2021. 90 open issues. Explicitly marked "no longer under active development." Will break on current season data. |
| The Odds API | odds-api.io | 250+ bookmakers vs 40+. More expensive. Only use if you need maximum bookmaker coverage for arbitrage detection. |
| `tenacity` (already in stack) | `backoff` (already in stack) | `backoff` is already present and works. `tenacity` is more expressive for complex retry policies (jitter, conditional retry on exception type). Either works — prefer `tenacity` for new sports code to match future pattern. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `websockets` >= 13.x | Requires Python >=3.10. Project is pinned to Python 3.9. The existing `websockets==12.0` in requirements.txt is already the highest compatible version for 3.9. Do not upgrade past 12.x unless Python runtime is also upgraded. | `websocket-client==1.9.0` for the sports WS consumer |
| `sportsipy` / `sportsreference` | Abandoned since Jan 2021. Scrapes sports-reference.com (fragile to DOM changes). 90 unresolved issues. Stats break mid-season. No maintenance. | BallDontLie SDK (NBA/NFL/MLB) or API-Sports (all leagues) |
| Polling the Polymarket sports WS by REST | The sports data is pushed over WS in real time. Polling `https://sports-api.polymarket.com` as HTTP would miss sub-second state changes. | Connect as persistent WebSocket using `websocket-client` |
| Building a custom odds model | Out of scope per PROJECT.md. LLM+external odds data is sufficient. Custom models require backtesting infrastructure (also out of scope). | Feed external odds from The Odds API directly into the LLM prompt context |
| `asyncio.run()` at the top of the sports pipeline | Mixing sync (existing Trader) and async (new sports WS) at the top level causes event loop conflicts in Python 3.9. | Run the WS consumer in a dedicated thread using `websocket-client`'s threaded mode, communicating with the main trading logic via a thread-safe `queue.Queue`. |

---

## Stack Patterns by Variant

**For the Polymarket sports WebSocket consumer:**
- Use `websocket-client` with `WebSocketApp.run_forever()` in a daemon thread
- Pass game state updates via `queue.Queue` to the main sports trading loop
- Because the existing `Trader` class is synchronous — adding a full asyncio layer would require rewriting the LangChain agent calls which use sync OpenAI client

**For pre-game static stat fetching:**
- Use `requests` (sync) when running inside the existing synchronous Trader flow
- Use `aiohttp` only if you add a dedicated async pre-game pipeline that runs independently
- Because mixing sync/async in the same call stack without careful thread management causes deadlocks

**For live in-game trading reaction:**
- Receive WS game state → put into queue → trading thread consumes → calls existing `polymarket.execute_market_order_for_token()` synchronously
- Because the CLOB client (`py-clob-client`) is synchronous and already handles order execution

**If Python runtime is upgraded to 3.10+:**
- Replace `websocket-client` WS consumer with `websockets` >= 14.x for native asyncio integration
- Migrate entire sports pipeline to `async def` with `asyncio.gather()` for concurrent API calls
- Not recommended for this milestone — keep the runtime constraint

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| `websocket-client==1.9.0` | Python 3.9–3.13 | Drop-in upgrade from 1.8.0 already in requirements.txt |
| `websockets==12.0` (existing) | Python 3.9 | Do NOT upgrade past 12.x — 13.x+ drops Python 3.9 support |
| `aiohttp==3.13.3` | Python 3.9–3.14 | Safe upgrade from 3.10.0 in requirements.txt |
| `tenacity==9.1.4` | Python 3.9+ | Safe upgrade from 8.5.0 in requirements.txt |
| `balldontlie==0.1.6` | Python 3.8+ | New addition; no conflict with existing packages |
| `apscheduler==3.11.x` | Python 3.9+ | Only add if clock-based pre-game triggers are needed |

---

## API Coverage Matrix

Polymarket sports catalog vs available APIs:

| Sport | API-Sports | BallDontLie | The Odds API | MySportsFeeds |
|-------|-----------|-------------|-------------|---------------|
| NFL | YES | YES | YES | YES |
| NBA | YES | YES | YES | YES |
| MLB | YES | YES | YES | YES |
| NHL | YES | NO | YES | YES |
| CFB (College Football) | YES | NO | YES | NO |
| CBB (College Basketball) | YES | NO | YES | NO |
| Soccer (EPL, etc.) | YES (50+ leagues) | NO | YES | NO |
| Esports | YES | NO | NO | NO |
| Tennis | YES | NO | YES | NO |

**Conclusion:** API-Sports is the only single API that covers the full Polymarket sports catalog (NFL through esports). Use BallDontLie as a supplemental source for NBA/NFL/MLB where its real-time 1-second update frequency and official Python SDK simplify integration.

---

## Sources

- PyPI: `websocket-client` — version 1.9.0, Python 3.9+, October 2025 release — HIGH confidence
- PyPI: `websockets` — version 16.0, Python >=3.10, January 2026 — HIGH confidence (confirmed Python 3.9 NOT supported)
- PyPI: `aiohttp` — version 3.13.3, Python 3.9+, January 2026 — HIGH confidence
- PyPI: `tenacity` — version 9.1.4, February 2026 — HIGH confidence
- PyPI: `balldontlie` — version 0.1.6, December 2024, Python 3.8+ — HIGH confidence
- github.com/roclark/sportsipy — last commit January 2021, explicitly abandoned — HIGH confidence (do not use)
- balldontlie.io docs — NBA, NFL, MLB coverage confirmed, live data every 1 second — MEDIUM confidence
- api-sports.io — 100 req/day free tier, $10/month paid, broad sport coverage — MEDIUM confidence (pricing may change)
- the-odds-api.com/liveapi/guides/v4 — v4 REST API, live scores ~30s update, 500 req/month free — MEDIUM confidence
- websockets.readthedocs.io 16.0 — asyncio reconnect pattern confirmed — HIGH confidence
- Existing requirements.txt — `websocket-client==1.8.0`, `websockets==12.0`, `aiohttp==3.10.0`, `tenacity==8.5.0` all present

---

*Stack research for: Sports mode — Polymarket autonomous trading bot*
*Researched: 2026-03-03*

# Feature Research

**Domain:** Autonomous sports prediction market trading bot (Polymarket sports mode)
**Researched:** 2026-03-03
**Confidence:** MEDIUM — Polymarket sports WS docs verified HIGH; sports bot feature patterns MEDIUM via multiple WebSearch sources; competitor feature sets LOW (no direct access to closed-source competitors)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features the bot must have. Missing these means the sports mode doesn't work at a basic level.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Sports WebSocket connection & reconnect | Without live game state the sports pipeline is dead; Polymarket WS is the source of truth for all live scoring | LOW | `wss://sports-api.polymarket.com/ws` — no auth required; must handle disconnects and resume without missing state |
| Sports market identification & filtering | Bot must distinguish sports markets from general markets and tag with league, teams, game time | LOW | Invert existing `TRADE_EXCLUDE_SPORTS` / `canonicalize_category()` logic; tag with `leagueAbbreviation`, `homeTeam`, `awayTeam` from WS |
| Live score / game state ingestion | Scores, period changes, live/ended flags are the primary signal for in-game trades | LOW | WS fields: `score`, `period`, `elapsed`, `live`, `ended`, `status` — parse and normalize across sports |
| Pre-game trade positioning | Most sports prediction market volume is pre-game; bot must evaluate and enter positions before tip-off / kickoff | MEDIUM | Requires external team stats API to supplement LLM reasoning; timing: trigger before game goes `live` |
| In-game autonomous trade execution | Core value prop — react to score changes faster than manual traders | HIGH | Latency-sensitive; must evaluate, decide, and submit CLOB order within seconds of WS event; LLM call adds ~1-3s latency |
| Sports-specific LLM prompts | General-market prompts lack game context; sports prompts must inject score, period, teams, stats, and odds context | MEDIUM | Extends existing LangChain prompt templates; requires structured game context object |
| Multi-sport support (NFL, NBA, MLB, NHL, CFB, CBB, soccer, esports, tennis) | Polymarket WS streams all sports; restricting to one sport leaves the majority of markets untouched | MEDIUM | Primary complexity is sport-specific data normalization (e.g., possession only for NFL/CFB; innings for MLB) |
| Sports-specific budget allocation | Sports and general markets share a wallet; unconstrained sports trading can exhaust the entire budget | LOW | Configurable `SPORTS_BUDGET_FRACTION` env var; enforce budget cap per sports session |
| Graceful pipeline coexistence | Sports pipeline must run alongside general pipeline without resource contention or state corruption | MEDIUM | Separate async event loop or process; shared USDC wallet with mutex on order submission |

### Differentiators (Competitive Advantage)

Features that create a performance or execution edge over manual traders or simpler bots.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Score-change triggered trade signals | Immediately re-evaluate market prices the moment a score update arrives, before manual traders react | HIGH | WS score delta detection → LLM re-evaluation → order submission pipeline; target <5s from WS event to order |
| External stats API integration (team record, H2H history, season performance) | LLM knowledge is stale; current season win rates and head-to-head matchups dramatically improve pre-game probability estimates | MEDIUM | Best option: The Odds API (historical odds back to 2020) + API-Sports (15yr history, real-time every 15s); one API call per game pre-game |
| Odds comparison vs. Polymarket price | Detect when Polymarket price diverges from external consensus odds — this is the value bet signal | HIGH | Compare external book odds (e.g., from The Odds API) with Polymarket's current YES/NO price; trade toward consensus when gap exceeds threshold |
| Period/quarter transition handling | Halftime, quarter breaks, and overtime starts are predictable volatility windows where prices move before market makers adjust | MEDIUM | Detect `period` change events from WS; trigger re-evaluation at each transition |
| Confidence-weighted position sizing for sports | Sports predictions have wider uncertainty bands than general markets; scale size by LLM confidence and game state | LOW | Extend existing confidence-weighted budget allocation; add sport-specific confidence discount factor |
| Game status edge-case handling | Overtime, rain delays, forfeits, and in-game injuries cause price dislocations | HIGH | Map all `status` enum values from WS; define trade rules for each edge case; avoid trading during suspension/delay |
| Sport-specific prompt context injection | NBA 4th quarter trailing by 3 is very different from NFL 4th quarter trailing by 3; sport-aware prompts outperform generic ones | MEDIUM | Build prompt fragments per sport category (scoring rate, comeback probability, time pressure) |
| Configurable per-sport budget caps | Limit exposure to high-variance sports (e.g., esports) while allowing larger allocation to more predictable ones (e.g., NFL) | LOW | Per-sport env config or config file; allows risk tuning without code changes |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Custom ML odds model (in-house probability engine) | Seems like it would be more accurate than external odds | Requires training data pipeline, model validation, and ongoing maintenance that is out of scope and adds months of work | Use external odds APIs (The Odds API, SportsDataIO) as the probability ground truth; LLM reasons on top of external data |
| Backtesting framework | Validating strategy before risking real money sounds essential | Out of scope per PROJECT.md; building a proper backtester requires historical Polymarket order book data that is difficult to obtain and replicate accurately | Paper trading / dry-run mode (already exists) with conservative position sizes for initial live validation |
| Social / sentiment analysis for sports | Twitter reactions to injury news seem like valuable signals | Structured, official data (box scores, injury reports) is faster and more reliable than social parsing; adds NLP complexity and noise | Integrate official injury report endpoints from SportsDataIO or API-Sports instead |
| Manual trade confirmation popups for live games | Seems safer to have human approval | Eliminates the sub-second speed advantage that is the entire value prop; defeats the purpose of an autonomous bot | Use dry-run mode for testing; set hard position size limits as the safety mechanism instead |
| Full order book market-making for sports | Market makers earn spreads and rebates | Requires continuous inventory management and rapid repricing; exposes the bot to adverse selection when game state changes suddenly | Stay as a taker; enter directional positions based on game state signals |
| Web UI / dashboard | Nice to see positions and P&L visually | Adds frontend development scope with no trading edge; the bot is autonomous and CLI-operated per PROJECT.md | Log structured JSON to a file; use existing CLI output and dry-run logs |
| Arbitrage across Polymarket + Kalshi + sportsbooks | High theoretical profit | Requires multi-exchange account management, cross-platform API integration, and complex settlement tracking; regulatory exposure for sportsbook arbitrage | Focus on directional trading within Polymarket where the existing CLOB infrastructure already works |

---

## Feature Dependencies

```
[Sports WebSocket connection]
    └──required by──> [Live score / game state ingestion]
                          └──required by──> [In-game autonomous trade execution]
                          └──required by──> [Period/quarter transition handling]
                          └──required by──> [Score-change triggered trade signals]

[Sports market identification & filtering]
    └──required by──> [Pre-game trade positioning]
    └──required by──> [In-game autonomous trade execution]
    └──required by──> [Sports-specific budget allocation]

[External stats API integration]
    └──required by──> [Pre-game trade positioning] (provides team stats, H2H history)
    └──enhances──>    [Odds comparison vs. Polymarket price]

[Sports-specific LLM prompts]
    └──required by──> [Pre-game trade positioning]
    └──required by──> [In-game autonomous trade execution]
    └──enhanced by──> [Sport-specific prompt context injection]
    └──enhanced by──> [External stats API integration]

[Odds comparison vs. Polymarket price]
    └──depends on──>  [External stats API integration] (for reference odds)
    └──enhances──>    [In-game autonomous trade execution] (value detection)

[Graceful pipeline coexistence]
    └──required by──> [Sports-specific budget allocation]
    └──required by──> [In-game autonomous trade execution]

[Multi-sport support]
    └──enhanced by──> [Sport-specific prompt context injection]
    └──enhanced by──> [Configurable per-sport budget caps]
```

### Dependency Notes

- **Sports WebSocket connection requires stable reconnect logic:** Game state gaps during reconnect cause stale context, which leads to wrong trades. Must track last-known state and invalidate in-flight decisions on reconnect.
- **Pre-game positioning requires external stats API:** The LLM alone lacks current season data. Without the API, pre-game analysis reduces to general priors.
- **In-game trade execution requires sports market identification:** Cannot place an order without knowing the correct Polymarket market ID and token addresses, which come from the market-tagging step.
- **Odds comparison enhances but does not block in-game execution:** External odds polling adds latency; in-game trades should proceed with LLM-only confidence if external odds are unavailable.
- **Graceful coexistence is a precondition for the entire sports pipeline:** A crash in the sports loop must not kill the general trading loop.

---

## MVP Definition

### Launch With (v1)

Minimum viable sports mode — validates autonomous live sports trading.

- [ ] Sports WebSocket client with reconnect — without this nothing works
- [ ] Sports market identification and metadata tagging (league, teams, game time) — needed to find the right markets
- [ ] Live score ingestion and game state normalization — core data model for all decisions
- [ ] Sports-specific LLM prompts with game context injection — reuses existing LangChain infrastructure
- [ ] Pre-game trade positioning pipeline — captures pre-game volume and validates stats API integration
- [ ] External stats API integration (one provider: The Odds API or API-Sports) — provides current season and H2H data
- [ ] In-game autonomous trade execution triggered by score changes — the primary value prop
- [ ] Configurable sports budget allocation — prevents wallet exhaustion
- [ ] Graceful pipeline coexistence with general trading — safety requirement

### Add After Validation (v1.x)

Add once v1 is profitable and stable for at least 2-3 weeks of live games.

- [ ] Period/quarter transition handling as discrete trade signals — add when score-change trades are proven profitable
- [ ] Odds comparison vs. Polymarket price (value bet detection) — add when external odds integration is stable
- [ ] Configurable per-sport budget caps — add when multi-sport behavior is understood from logs
- [ ] Game status edge-case handling (OT, rain delay, forfeit) — add after seeing first edge cases in production

### Future Consideration (v2+)

Defer until sports mode has demonstrated sustained profitability.

- [ ] Sport-specific prompt context injection per sport category — deferred because single generalized sports prompt is sufficient for v1 validation
- [ ] Confidence-weighted position sizing tuned specifically for sports — existing general confidence weighting is adequate for v1
- [ ] Multi-provider stats API fallback — single provider sufficient for v1; add redundancy after reliability issues are observed

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Sports WebSocket connection & reconnect | HIGH | LOW | P1 |
| Sports market identification & tagging | HIGH | LOW | P1 |
| Live score / game state ingestion | HIGH | LOW | P1 |
| Sports-specific LLM prompts | HIGH | MEDIUM | P1 |
| Pre-game trade positioning pipeline | HIGH | MEDIUM | P1 |
| External stats API integration | HIGH | MEDIUM | P1 |
| In-game autonomous trade execution | HIGH | HIGH | P1 |
| Sports budget allocation | HIGH | LOW | P1 |
| Graceful pipeline coexistence | HIGH | MEDIUM | P1 |
| Score-change triggered trade signals | HIGH | HIGH | P2 |
| Period/quarter transition handling | MEDIUM | MEDIUM | P2 |
| Odds comparison vs. Polymarket price | HIGH | HIGH | P2 |
| Sport-specific prompt context injection | MEDIUM | MEDIUM | P2 |
| Configurable per-sport budget caps | MEDIUM | LOW | P2 |
| Game status edge-case handling (OT, delays) | MEDIUM | HIGH | P2 |
| Confidence-weighted sports position sizing | LOW | LOW | P3 |
| Multi-provider stats API fallback | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Must have for v1 launch — sports mode is non-functional without these
- P2: Should have — adds trading edge and reliability; add after v1 validation
- P3: Nice to have — future optimization once strategy is proven

---

## Competitor Feature Analysis

| Feature | Traditional Sports Betting Bots | Open-Source Polymarket Bots | Our Approach |
|---------|--------------------------------|------------------------------|--------------|
| Live game state | WebSocket or polling of sportsbook data feeds | General market polling; no sports WS support | Native Polymarket sports WS — direct source, lowest latency |
| Pre-game analysis | Rule-based odds models, ML classifiers | LLM with general market context | LLM + external stats API + sports-specific prompts |
| Odds comparison | Core feature — arbitrage between books | Not applicable (single platform) | Compare external consensus odds vs. Polymarket price |
| Team stats integration | SportsDataIO, API-Sports, proprietary feeds | No stats integration; LLM knowledge only | External API (The Odds API or API-Sports) per game |
| Multi-sport support | Yes — unified via API | No explicit sport handling | Yes — all sports on Polymarket WS from v1 |
| Execution | Sportsbook bet placement APIs | Polymarket CLOB taker orders | Polymarket CLOB — same execution as existing general pipeline |
| Position sizing | Kelly criterion, fixed fractional | Confidence-weighted budget | Extend existing confidence-weighted allocation |
| Autonomy | Semi-auto (human approval) or full-auto | Full autonomous | Fully autonomous — no confirmation prompts |

---

## Sources

- [Polymarket Sports WebSocket Documentation](https://docs.polymarket.com/market-data/websocket/sports) — HIGH confidence; official Polymarket docs confirming WS fields and message types
- [The Odds API — Historical Sports Odds](https://the-odds-api.com/historical-odds-data/) — MEDIUM confidence; official API docs confirming historical data availability back to 2020
- [API-Sports](https://api-sports.io/) — MEDIUM confidence; official docs confirming 15yr historical data, real-time updates every 15s
- [SportsDataIO](https://sportsdata.io/) — MEDIUM confidence; official site confirming multi-sport coverage and live odds API
- [OpticOdds — AI Bots in Sports Betting](https://opticodds.com/blog/ai-bots-in-sports-betting) — MEDIUM confidence; industry blog covering AI bot architecture patterns
- [QuantVPS — Sports Betting Bots on Polymarket](https://www.quantvps.com/blog/automated-sports-betting-bots-on-polymarket) — LOW confidence; third-party analysis, unverified claims
- [Polymarket Strategies 2026](https://cryptonews.com/cryptocurrency/polymarket-strategies/) — LOW confidence; journalistic overview, useful for competitive context
- [ReadWrite — Best Sports Betting Bots 2026](https://readwrite.com/gambling/betting/sports-betting-bots/) — LOW confidence; review site, useful for feature landscape
- [Risk.inc — AI Revolutionizing Betting](https://www.risk.inc/blog/how-artificial-intelligence-is-revolutionizing-the-world-of-betting-and-gambling) — LOW confidence; industry blog

---

*Feature research for: Polymarket autonomous sports trading bot — sports mode milestone*
*Researched: 2026-03-03*

# Pitfalls Research

**Domain:** Autonomous live sports trading on prediction markets (Polymarket sports mode)
**Researched:** 2026-03-03
**Confidence:** HIGH (verified through official docs, GitHub issues, codebase inspection)

---

## Critical Pitfalls

### Pitfall 1: Polymarket Sports WebSocket Silently Stops Delivering Messages

**What goes wrong:**
The `wss://sports-api.polymarket.com/ws` connection enters a "zombie" state — connection reads OPEN, ping/pong succeeds (99.6% success rate reported), but no game state messages arrive. Reproducibly occurs 18-22 minutes into a session. The sports pipeline assumes data is flowing and continues operating on stale game state, making in-game trading decisions on scores from 20+ minutes ago.

**Why it happens:**
Confirmed server-side infrastructure issue in Polymarket's real-time data backend (documented in `Polymarket/real-time-data-client` issue #26). The WebSocket transport layer is healthy but the server stops pushing messages to the socket — a classic "silent freeze" not caught by standard connection health checks.

**How to avoid:**
Implement a message-gap watchdog independent of ping/pong heartbeat monitoring. Track `last_message_received_at` separately from `last_pong_at`. If no game data message has arrived within a configurable threshold (recommended: 5 minutes), treat the connection as stale and force-reconnect. On reconnect, request or reprocess a full game state snapshot before resuming trading — do not resume trading from cached pre-freeze state.

```python
# Pattern: separate heartbeat tracking from data tracking
self.last_pong_at = time.monotonic()
self.last_game_message_at = time.monotonic()

async def _watchdog(self):
    while True:
        await asyncio.sleep(30)
        gap = time.monotonic() - self.last_game_message_at
        if gap > self.MESSAGE_GAP_THRESHOLD:  # 300 seconds
            self.logger.warning(f"[ws] data_gap={gap:.0f}s — forcing reconnect")
            await self._reconnect_and_resync()
```

**Warning signs:**
- WebSocket shows OPEN state but no log lines for incoming game messages for 5+ minutes during an active game period
- Bot attempts to trade on scores that are several minutes behind what external APIs show
- `last_pong_at` updates frequently while `last_game_message_at` stays frozen

**Phase to address:** Sports WebSocket Integration (Phase 1 — foundational; everything else depends on reliable game state)

---

### Pitfall 2: LLM Latency Makes Live In-Game Trading Decisions Stale Before Execution

**What goes wrong:**
The existing pipeline calls `self.llm.invoke()` synchronously (see `executor.py:_invoke_llm`). GPT-4o averages 3-8 seconds per call under normal conditions and can spike to 30-80 seconds during OpenAI infrastructure incidents. A live-game trigger fires on a score change, the LLM decision takes 15 seconds to return, and by the time the order reaches the CLOB the market price has already repriced — the bot either overpays significantly or the order fails to fill.

**Why it happens:**
The general pipeline was designed for periodic batch analysis (every N minutes) where 5-15 second LLM latency is irrelevant. The sports live mode is event-driven and requires sub-5-second total decision-to-execution latency to capture in-game mispricing before the crowd adjusts. LLM calls are the single biggest latency source.

**How to avoid:**
Two-layer decision architecture:
1. **Fast path (no LLM):** Pre-game, pre-compute LLM probability assessments for each market outcome. Store as structured data (e.g., `{outcome: "Team A wins", llm_prob: 0.65, threshold_to_buy: 0.55}`). During live play, fast path checks: if current market price diverges from stored LLM probability by more than a configured threshold, execute immediately without a new LLM call.
2. **Slow path (with LLM):** Use the LLM only for major game state changes (turnover late in game, injury to key player, overtime) where cached pre-game analysis is no longer valid. Invoke asynchronously and skip if latency exceeds 10 seconds.

Use `gpt-5-mini` (already configured as default model) rather than `gpt-4.1` for live sports decisions — roughly 3x faster with acceptable quality for binary outcomes.

**Warning signs:**
- Time between websocket game state message and CLOB order placement exceeds 5 seconds in logs
- Market price at order time differs substantially from market price at trigger time
- Frequent "order not filled" or fill prices significantly worse than limit prices set

**Phase to address:** Sports Live Trading Engine (Phase 3 — pre-game caching architecture needed before any live trading)

---

### Pitfall 3: Budget Race Condition Between Sports and General Pipelines

**What goes wrong:**
Both pipelines query `get_usdc_balance_report()` independently and compute allocations from that balance. If both pipelines run in overlapping windows (e.g., cron fires general pipeline while sports pipeline is mid-execution), they both see $500 available, both allocate 30% ($150 each), and the second executor submits orders against a balance that's already $150 lower. The second batch of orders hits minimum size requirements or fails due to insufficient collateral — without surfacing a clear error.

**Why it happens:**
The existing `allocate_confidence_weighted()` in `executor.py` reads a live balance at decision time. The sports pipeline is always-on (websocket-driven), while the general pipeline is periodic. There's no shared state or locking mechanism — they both independently observe a stale "full" balance.

**How to avoid:**
Implement a `BudgetCoordinator` singleton that both pipelines reference. It maintains a reserved allocation map: `{"general": 150.0, "sports": 100.0}`. Each pipeline reserves its budget before building candidates, and releases the reservation after execution completes or fails. Use Python's `asyncio.Lock` if both run in the same event loop, or a shared state object with atomic updates if running as separate processes.

As a simpler alternative for MVP: enforce pipeline sequencing. The sports pipeline runs continuously but the general pipeline checks if any sports trades are currently being executed before allocating. Store a `sports_execution_in_progress` flag.

**Warning signs:**
- Execution failures citing minimum order amounts that don't match configured minimums
- `FAILED_MIN_ORDER_SIZE` errors appearing with amounts that look correct in isolation
- Balance reads at start vs. end of a pipeline run show discrepancy not explained by executed trades

**Phase to address:** Pipeline Architecture (Phase 2 — must be solved before both pipelines run concurrently in production)

---

### Pitfall 4: Treating Sports WebSocket gameId as a Stable Market Identifier

**What goes wrong:**
Websocket messages provide `gameId` and `slug` for the game. The code uses these to look up which Polymarket market to trade. But Polymarket can have multiple markets per game (e.g., "Will Team A win?", "Will the game go to overtime?", "Total points over/under 220.5"), and the `gameId` from the sports websocket does not map 1:1 to a market's CLOB token ID. If the bot naively matches on `gameId` alone, it may trade the wrong market or attempt to trade a market that has already resolved.

**Why it happens:**
The Polymarket sports websocket and the Gamma API use different identifiers. The websocket identifies games; Gamma identifies prediction markets. The join between them requires matching on event slug, which itself may differ in format ("nba-2025-03-01-lakers-celtics" vs. the game slug from the websocket).

**How to avoid:**
Build an explicit game-to-market mapping at sports pipeline startup: query Gamma for all active sports events, extract slugs, and build a lookup table mapping `ws_slug → [market_ids]`. Refresh this mapping every 30 minutes. When a websocket event fires, look up markets from the mapping — never guess based on gameId alone. Log and skip any events where the mapping is absent rather than attempting a fallback.

**Warning signs:**
- Bot attempts to execute on a market that was already closed/resolved
- Same game appears to generate trades on multiple unrelated markets
- Slug normalization errors in logs ("no mapping found for game_id=XXX")

**Phase to address:** Sports Market Discovery (Phase 1/2 — mapping must exist before any trading logic)

---

### Pitfall 5: Blocking the asyncio Event Loop with Synchronous LangChain Calls

**What goes wrong:**
The existing `_invoke_llm()` calls `self.llm.invoke()` — a synchronous blocking call. When the sports pipeline wraps this in an asyncio websocket handler, calling it directly blocks the entire event loop. While the LLM is waiting (3-30 seconds), no websocket messages are processed, no heartbeats are sent, and the connection drops (the server closes connections after 10 seconds without a pong response).

**Why it happens:**
LangChain's synchronous `invoke()` uses `requests` or `httpx` in blocking mode. In an asyncio context, any blocking I/O call halts the event loop. This is a documented known issue in LangChain (GitHub issues #8494, #9014) — calling `asyncio.run()` inside an already-running event loop also fails with `RuntimeError`.

**How to avoid:**
Use `self.llm.ainvoke()` (LangChain's async equivalent) within async contexts. For CPU-bound operations or any unavoidable synchronous calls, wrap with `asyncio.get_event_loop().run_in_executor(None, sync_func)` to run in a thread pool. Never call `asyncio.run()` from within an async function. Audit all connectors (Gamma, Chroma, news) for synchronous HTTP calls.

```python
# Wrong — blocks event loop
superforecast = self.llm.invoke(prompt)

# Correct — yields control to event loop while waiting
superforecast = await self.llm.ainvoke(prompt)
```

**Warning signs:**
- Websocket connection drops coincide with LLM call windows in logs
- Websocket pong timeouts occurring specifically when LLM calls are in progress
- The event loop lag (`asyncio.get_event_loop().time()` drift) spikes above 5 seconds

**Phase to address:** Sports WebSocket Integration (Phase 1 — must be verified before any live async pipeline is built)

---

### Pitfall 6: Blindly Trading Live Markets That Are Already Resolved or Near Settlement

**What goes wrong:**
A game ends at 9:47 PM. Polymarket's sports websocket sends `ended: true`. The general prediction market for "Will Team A win the game?" is now in its 2-hour challenge/settlement window — but Polymarket has not yet formally closed the market. The sports pipeline sees a "good" price still showing on the order book (market makers haven't withdrawn yet), computes an "edge," and places an order. The market then resolves and the order either fills at a terrible price or gets caught in the settlement, tying up USDC.

**Why it happens:**
The settlement window (2-hour challenge period minimum) means markets remain technically open after outcomes are clear. Market makers may pull liquidity but the order book isn't immediately empty. The bot doesn't differentiate between "market is open and uncertain" vs. "market is open but outcome is determined."

**How to avoid:**
Check `ended: true` and `status` fields from the sports websocket before initiating any new trade on that game's markets. When `ended` is true, cancel any pending orders for that game's markets immediately and mark all associated markets as "do not trade." Additionally, build a time-based filter: stop placing new orders on a market when the game's `finished_timestamp` (ISO 8601 field present when `ended: true`) is within N minutes of the scheduled market close time.

**Warning signs:**
- Trades placed on markets within 5 minutes of a game's completion
- Higher-than-expected loss rate on trades placed late in games
- Positions that resolve immediately against you after the game ends

**Phase to address:** Sports Live Trading Engine (Phase 3 — guard must be at the order placement decision point)

---

### Pitfall 7: Using the General Pipeline's Chroma RAG for Sports Market Filtering

**What goes wrong:**
The existing `filter_markets()` method in `Executor` uses Chroma RAG with a prompt tuned for general prediction markets (politics, crypto, macro events). If the sports pipeline uses this same filtering step, sports markets will be scored and ranked against embeddings built for general markets — they'll score poorly because sports questions ("Will the Lakers beat the Celtics tonight?") don't match the general market corpus, and the best sports candidates will be filtered out before the LLM ever sees them.

**Why it happens:**
The existing Chroma instance (`local_db_events`, `local_db_markets`) is built once per run and tuned for the general pipeline's use case. The `filter_events()` prompt references geopolitical events and financial outcomes. Sports market embeddings will cluster differently in the vector space.

**How to avoid:**
Sports pipeline uses separate filtering logic — skip RAG-based market filtering entirely, or build a sports-specific Chroma index with sports market embeddings. For MVP, a lightweight rule-based filter is more reliable: filter sports markets by league tag, active status, volume/liquidity thresholds, and time-to-game. Save the LLM call for the actual trade decision, not the filtering step.

**Warning signs:**
- Sports markets consistently return very high RAG distances (scores > 0.8 in Chroma output)
- Zero sports markets surviving the filter step even when valid live games exist
- Filter step returns only one or two sports markets from a full card of 10+ active games

**Phase to address:** Sports Market Discovery (Phase 2 — filtering architecture must be sports-aware from the start)

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Using same `Executor` class for sports decisions | Fast initial implementation | Sports-specific context (score, period, momentum) never reaches the LLM prompt; trade quality suffers | Never — sports prompts need game state fields |
| Single Chroma DB for both pipelines | No extra infrastructure | RAG results polluted across domains; sports and general markets interfere | Never for live trading; acceptable for dry-run testing |
| Polling Gamma API for game state instead of websocket | Simpler code path | Gamma doesn't provide live scores; polling adds 30+ second latency vs. websocket's real-time | Never — websocket is the only real-time source |
| Hardcoding a single sports data provider | One integration to build | Provider outage takes down all sports stats; pricing changes unpredictably | MVP only — abstract the interface from day one |
| Trading all sports from day one with no per-sport validation | Feature parity with PROJECT.md | Different sports have wildly different market structures (NFL vs. tennis); edge cases cause silent failures | Never — validate one sport end-to-end first, then expand |
| Budget split as a single env var fraction | Simple configuration | Race condition between pipelines; no enforcement mechanism | Never for live execution; acceptable for dry-run |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Polymarket Sports WebSocket | Treating ping/pong success as proof data is flowing | Track `last_game_message_at` separately; watchdog on data gap |
| Polymarket Sports WebSocket | No subscription needed — some assume you must send a subscribe message | The endpoint broadcasts all sports automatically; just connect and listen |
| Polymarket CLOB API | 60 orders/minute limit shared across general and sports pipelines | Track order rate globally; sports live trades count against the same quota as general trades |
| Polymarket CLOB API | Retrying failed orders immediately | Use exponential backoff; immediate retry on rate limit burns remaining quota |
| External Sports Data API | Assuming team names match between API and Polymarket slugs | Build a normalization/mapping layer; "LA Lakers" vs. "Los Angeles Lakers" vs. "Lakers" all appear |
| External Sports Data API | Fetching stats on every websocket event | Cache stats at game start; refresh only at halftime or quarter breaks — stats don't change per-possession |
| LangChain `ChatOpenAI` | Calling `.invoke()` inside `async def` | Use `.ainvoke()` or `run_in_executor` to avoid blocking the event loop |
| LangChain `ChatOpenAI` | Assuming temperature controls work on all models | Code already handles this for gpt-5 models (`temperature=1` forced); sports pipeline must inherit same pattern |
| Chroma Vector DB | Sharing the same local DB between pipelines run at overlapping times | Each pipeline run calls `clear_local_dbs()` which deletes shared state; sports pipeline needs persistent or isolated DB |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Calling Gamma API for each game's markets on every websocket event | API request rate spikes; Gamma rate limits trigger; 429 errors in logs | Cache game→market mapping at startup; refresh every 30 minutes | Immediately at scale (>5 games active simultaneously) |
| Running LLM inference on every score change | Decision latency >10 seconds; websocket backlog grows; old events processed after newer ones override them | Pre-game LLM scoring; live path uses cached probabilities + threshold check | Any game with scoring pace > 1 score per 10 seconds (basketball, soccer) |
| Sequential execution of trades per candidate (current pattern) | Total execution time = N × order latency; late candidates placed on stale prices | Submit orders concurrently with `asyncio.gather()` where order book independence is confirmed | More than 3 concurrent trade candidates |
| Chroma `clear_local_dbs()` called by both pipelines on same host | Sports pipeline destroys general pipeline's DB mid-run and vice versa | Each pipeline uses isolated DB paths (`local_db_events_sports`, `local_db_markets_sports`) | First concurrent run of both pipelines |
| Synchronous `requests`-based HTTP calls in async context | Event loop stalls; websocket timeouts; erratic behavior under load | Audit all HTTP calls in connectors; replace `requests` with `aiohttp` or `httpx` async | Whenever LLM or API calls overlap with websocket heartbeat windows |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Logging full sports API responses including odds data | Expose API keys embedded in response URLs or auth headers in log files | Scrub API keys from logs; use structured logging that omits raw response bodies |
| Using the same POLYGON_WALLET_PRIVATE_KEY environment variable for both pipelines running as separate processes | Key exposure surface doubles; a compromise of one process exposes all funds | Same process, same key is fine; if ever split into separate services, use separate signing keys with limited USDC approval |
| No circuit breaker on sports pipeline order execution | A runaway sports loop can drain the entire USDC balance on a single game gone wrong | Configure `SPORTS_MAX_ALLOCATION_PER_GAME_USDC` and `SPORTS_MAX_DAILY_LOSS_USDC`; halt pipeline on breach |
| Trusting sports websocket data without validation | A malformed or spoofed message could trigger trades on nonexistent markets | Validate all required fields present and within expected ranges before any trade trigger; reject and log malformed messages |

---

## "Looks Done But Isn't" Checklist

- [ ] **Sports WebSocket integration:** Appears to receive messages — verify with a message-gap watchdog that fires correctly when server silently freezes (simulate by blocking messages for 6 minutes)
- [ ] **Live trade execution:** Dry run shows trades being computed — verify that the market price at order placement time matches the price at trigger time (not the cached pre-game price)
- [ ] **Budget split:** Config accepts `SPORTS_BUDGET_FRACTION` — verify that both pipelines running concurrently cannot allocate more than 100% of available balance combined
- [ ] **Market mapping:** Bot finds sports markets via Gamma — verify the slug normalization correctly handles all 9 sport types (NFL, NBA, MLB, NHL, CFB, CBB, soccer, esports, tennis) with actual live game data
- [ ] **Reconnection after silence:** Bot reconnects on explicit WebSocket close — verify reconnection also fires on 5-minute data gap (the silent freeze case, not just the disconnect case)
- [ ] **Game ended guard:** Bot stops trading when `ended: true` arrives — verify it also cancels any orders submitted in the last 60 seconds before the `ended` message arrived
- [ ] **Sports pipeline isolation from general pipeline:** Both pipelines run without error — verify they don't delete each other's Chroma DBs (`clear_local_dbs()` conflict)
- [ ] **Async LLM calls:** LLM decisions work in isolation — verify they work while websocket messages are streaming concurrently (no event loop blocking)

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Silent websocket freeze caused stale trades | MEDIUM | 1. Identify affected trades from logs using timestamp gap. 2. Check if orders filled. 3. Manually close positions at market price if game has ended. 4. Increase watchdog sensitivity. |
| LLM latency spike caused orders at wrong prices | MEDIUM | 1. Review filled orders where fill price > 10% from trigger price. 2. Adjust circuit breaker to reject orders when fill price deviates > threshold. 3. Temporarily reduce live trade budget. |
| Budget race condition over-allocated funds | HIGH | 1. Halt both pipelines immediately. 2. Audit all open orders via CLOB API. 3. Cancel unfilled orders. 4. Reconcile actual USDC balance. 5. Implement BudgetCoordinator before restart. |
| Wrong market traded (gameId mapping failure) | LOW-MEDIUM | 1. Check execution logs for market_id mismatches. 2. If position held on wrong market, close at market. 3. Rebuild game→market mapping with corrected slug normalization. |
| LangChain event loop blocking dropped connection | LOW | 1. Reconnect websocket (auto-reconnect should fire). 2. Migrate blocking `invoke()` calls to `ainvoke()`. 3. Add event loop lag monitoring. |
| Post-game order filled after resolution | HIGH | 1. Accept the loss (market resolves against position). 2. Implement `ended` guard with 5-minute pre-expiry blackout period. 3. Add time-to-market-close check before every order. |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Silent WebSocket freeze (Pitfall 1) | Phase 1: Sports WebSocket Integration | Simulate by blocking messages for 6 minutes; confirm watchdog fires and reconnect occurs |
| LLM latency for live decisions (Pitfall 2) | Phase 3: Sports Live Trading Engine | Measure P99 time from websocket trigger to CLOB order submission under simulated load |
| Budget race condition (Pitfall 3) | Phase 2: Pipeline Architecture | Run both pipelines simultaneously in dry-run; verify combined allocation never exceeds 100% |
| Unstable gameId-to-market mapping (Pitfall 4) | Phase 1/2: Sports Market Discovery | Validate mapping for all 9 sports types against live Polymarket data before trading any |
| Asyncio event loop blocking (Pitfall 5) | Phase 1: Sports WebSocket Integration | Test concurrent LLM call + websocket streaming; confirm no pong timeout during LLM wait |
| Trading resolved markets (Pitfall 6) | Phase 3: Sports Live Trading Engine | Feed synthetic `ended: true` message; confirm all pending orders cancelled within 1 second |
| Chroma RAG misfit for sports (Pitfall 7) | Phase 2: Sports Market Discovery | Compare Chroma scores for sports vs. general markets; confirm sports markets aren't uniformly filtered out |

---

## Sources

- Polymarket real-time-data-client GitHub issue #26: Silent data stream freeze (18-22 min pattern) — [https://github.com/Polymarket/real-time-data-client/issues/26](https://github.com/Polymarket/real-time-data-client/issues/26)
- Polymarket Sports WebSocket official docs: heartbeat protocol, message format, trigger events — [https://docs.polymarket.com/developers/sports-websocket/overview](https://docs.polymarket.com/developers/sports-websocket/overview)
- LangChain asyncio event loop blocking issues — [https://github.com/langchain-ai/langchain/issues/8494](https://github.com/langchain-ai/langchain/issues/8494)
- Polymarket CLOB API rate limits (60 orders/minute, 3000/10 minutes) — [https://docs.polymarket.com/quickstart/introduction/rate-limits](https://docs.polymarket.com/quickstart/introduction/rate-limits)
- OpenAI API latency optimization guide — [https://developers.openai.com/api/docs/guides/latency-optimization](https://developers.openai.com/api/docs/guides/latency-optimization)
- Polymarket market settlement and challenge period documentation — [https://docs.polymarket.com/polymarket-learn/markets/how-are-markets-resolved](https://docs.polymarket.com/polymarket-learn/markets/how-are-markets-resolved)
- Automated sports betting bots on Polymarket — [https://www.quantvps.com/blog/automated-sports-betting-bots-on-polymarket](https://www.quantvps.com/blog/automated-sports-betting-bots-on-polymarket)
- Market making on prediction markets pitfalls — [https://newyorkcityservers.com/blog/prediction-market-making-guide](https://newyorkcityservers.com/blog/prediction-market-making-guide)
- Codebase inspection: `agents/application/executor.py`, `agents/application/trade.py`
- Codebase inspection: `TRADE_EXCLUDE_SPORTS` pattern in `trade.py:_exclude_sports_markets()`

---
*Pitfalls research for: Autonomous sports mode trading on Polymarket (Python 3.9, LangChain, asyncio websocket)*
*Researched: 2026-03-03*