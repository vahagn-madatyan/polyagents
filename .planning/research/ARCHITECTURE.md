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
