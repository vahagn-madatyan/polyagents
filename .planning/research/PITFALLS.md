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
