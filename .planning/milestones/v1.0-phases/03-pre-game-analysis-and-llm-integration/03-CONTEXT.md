# Phase 3: Pre-Game Analysis and LLM Integration - Context

**Gathered:** 2026-03-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Complete pre-game analysis pipeline that combines external stats, live odds, and sports-specific LLM prompts to select and place pre-game trades, producing a per-game probability cache that Phase 4's live trading engine uses as its fast path. No live in-game trading logic — that's Phase 4.

</domain>

<decisions>
## Implementation Decisions

### Pre-Game Trigger Timing
- Dual-trigger: analyze on market discovery (slug table maps game to market) AND re-analyze at a configurable lead time before game start
- Doubles LLM calls but provides the best data freshness — first analysis gives early positioning, refresh ensures latest stats/odds
- On pipeline restart: re-analyze only if cached probability is older than configurable TTL (`SPORTS_PREGAME_CACHE_TTL_MINUTES`). Skip games with fresh cache entries
- Analyze ALL mapped games, not just value-bet flagged ones — let the LLM make the trading decision, don't pre-filter

### Pre-Game Execution Model
- Immediate per-game execution — each game analyzed independently; if confidence is high enough, place the trade right away
- No batch/ranking across games — fastest to market, consistent with the existing general pipeline approach
- Budget caps and per-sport caps naturally constrain total exposure

### LLM Prompt Design
- Sports-specialized system prompt: LLM is framed as a sports betting analyst, NOT the generic prediction market superforecaster
- Two-stage prompt (mirrors existing pipeline): Stage 1 = blind probability estimate (no Polymarket price), Stage 2 = price-aware trade decision with Polymarket prices shown
- Include value-bet divergence signal in Stage 2: "External odds imply X% home win vs Polymarket's Y%"
- Inject all game context from `SportsDataConnector.get_game_context()`: team stats (win rates, recent form), H2H records, external bookmaker odds
- Per-sport prompt fragments deferred to v2 (SIG-01) — v1 uses one unified sports prompt for all leagues
- Output format: same JSON schema as existing `one_best_trade` (CandidateTrade-compatible: selected_outcome, side, price, size_fraction, rationale, risk_factors, counter_case). Maximizes code reuse with Executor's parsing logic

### Probability Cache
- File-persisted JSON — survives pipeline restarts, enables stale-check on restart
- Keyed by `game_id` (from WS gameId) — one cache entry per game
- Full analysis snapshot stored: probability estimate, confidence gap, rationale, risk factors, input data (stats/odds at time of analysis), LLM response text, timestamp
- Staleness: fixed TTL via `SPORTS_PREGAME_CACHE_TTL_MINUTES` (e.g., 30 min default). Re-analysis triggers on next event loop iteration after expiry
- Cache entry retrievable by game_id for Phase 4's fast-path decisions

### Trade Aggressiveness
- Minimum confidence gap threshold: only trade when `|LLM_probability - polymarket_price|` exceeds `SPORTS_MIN_CONFIDENCE_GAP` (configurable, e.g., 0.10). Filters low-conviction trades
- Position sizing: use LLM's `size_fraction` output multiplied by per-sport budget cap — same approach as general pipeline. LLM controls sizing
- No limit on simultaneous open positions — budget caps and per-sport caps naturally constrain exposure
- One side only per game — LLM picks the outcome with the highest edge. No both-sides trading

### Claude's Discretion
- Exact sports analyst system prompt wording
- SportsExecutor class structure and method design
- Async vs sync LLM calls (roadmap mentions `ainvoke()` but existing code uses sync `invoke()`)
- Probability cache file location and JSON structure
- How the pre-game refresh timer integrates with the sports.py event loop
- Error handling when LLM or data sources fail mid-analysis
- Real CLOB balance fetch to replace `SPORTS_INITIAL_WALLET_USD` placeholder

</decisions>

<specifics>
## Specific Ideas

- Two-stage prompt mirrors existing general pipeline (superforecaster -> one_best_trade) but with sports-specific persona and data injection
- Value-bet divergence from `SportsDataConnector.detect_value_bet()` included as explicit signal in trade decision prompt
- `get_game_context()` already aggregates everything needed — prompt just needs to format it clearly for the LLM
- Cache must be readable by game_id for Phase 4's fast-path — design the file format with this lookup pattern in mind

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Executor.source_best_trade()`: two-stage LLM call pattern (superforecast + trade decision) — same pattern for SportsExecutor but with sports prompt
- `Executor._invoke_llm()` / `self.llm.invoke()`: LangChain ChatOpenAI invocation — reuse for sports LLM calls
- `Executor._parse_trade_decision()`: parses JSON output into CandidateTrade fields — reusable if output schema matches
- `SportsDataConnector.get_game_context()`: aggregates stats/H2H/odds into one dict — direct input to prompt formatting
- `BudgetCoordinator.can_spend_sports()` / `record_sports_trade()` / `get_sport_cap()`: ready for trade execution
- `SessionBudgetManager`: in-process budget tracking with cooldown detection

### Established Patterns
- LangChain `ChatOpenAI` with `SystemMessage` + `HumanMessage` for LLM invocation
- `Prompter` class in `agents/application/prompts.py` for prompt templates — add sports-specific methods
- `CandidateTrade` Pydantic model for trade data flow — reuse for sports trades
- `_env_int()` / `_env_float()` / `_env_bool()` inlined in sports modules to avoid heavy executor.py import chain
- `print(f"[tag] key=value")` for structured logging

### Integration Points
- `agents/sports.py`: event loop where pre-game analysis wires in — currently has placeholder comment "trade logic is Phase 3+"
- `agents/application/prompts.py`: add sports-specific `sports_superforecaster()` and `sports_trade_decision()` methods
- `agents/utils/objects.py`: may need `SportsAnalysisCache` Pydantic model for typed cache entries
- `.env.example`: add `SPORTS_PREGAME_CACHE_TTL_MINUTES`, `SPORTS_MIN_CONFIDENCE_GAP`, `SPORTS_PREGAME_LEAD_MINUTES`

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-pre-game-analysis-and-llm-integration*
*Context gathered: 2026-03-06*
