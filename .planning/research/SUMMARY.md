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
