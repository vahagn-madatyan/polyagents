# Phase 2: Market Discovery and Pipeline Architecture - Context

**Gathered:** 2026-03-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Slug-based sports market identification via Gamma API, external stats/odds API connector for team data, budget coordination between sports and general trading pipelines, and graceful pipeline coexistence as separate processes. No trading logic or LLM integration — those are Phase 3+.

</domain>

<decisions>
## Implementation Decisions

### Slug Mapping Strategy
- Unmapped games (no Polymarket market found): log and queue for retry on next refresh cycle — markets may appear after initial listing
- Refresh cadence: periodic full rebuild every 30 minutes PLUS immediate single-slug lookup when WS reports a new gameId not already in the table
- Market type filter: moneyline only (who wins) for v1 — skip spreads, totals, and props. Simplest signal from game state
- Matching approach: exact slug match first, fall back to team-name substring search (extract team names from WS slug, search Gamma markets containing both team names + league tag)

### External Stats API
- Provider: Claude's discretion — research should evaluate API-Sports, The Odds API, and ESPN feeds for coverage across all 9 sports, and recommend the best option
- Uncovered sports handling: configurable per sport — env var list specifying which sports require external stats (e.g., `SPORTS_REQUIRE_STATS="nfl,nba,mlb,nhl"`). Sports not in the list can trade using Polymarket price + LLM reasoning alone
- Odds divergence threshold: Claude's discretion — research should determine a sensible default based on typical Polymarket-vs-bookmaker spreads. Must be configurable via `SPORTS_ODDS_DIVERGENCE_THRESHOLD` env var
- Caching: two-tier TTL — team stats cached for 24 hours (win rates/H2H change slowly), odds cached for 5 minutes (shift constantly). Configurable via env vars

### Budget Coordination
- Budget allocation: fixed fraction of wallet balance read at startup — `SPORTS_BUDGET_FRACTION` env var (e.g., 0.3 = 30% to sports, remaining to general)
- Per-sport caps: fraction of the sports allocation per league — e.g., `SPORTS_CAP_NFL=0.4`, `SPORTS_CAP_NBA=0.3`. Unconfigured leagues share the remainder equally
- Race condition protection: Claude's discretion — pick the best approach (file lock, in-memory lock, or other) based on the separate-process architecture
- Safety floor: configurable minimum wallet balance — stop sports trades when wallet drops below `SPORTS_MIN_WALLET_USD` (e.g., $50). General pipeline keeps its own allocation

### Pipeline Isolation
- Architecture: separate Python process — sports pipeline is its own entry point (`python -m agents.sports` or similar). OS process boundary provides crash isolation
- Launcher: independent start — each pipeline starts on its own (two terminal windows / two containers). No unified orchestrator
- Dry-run mode: dual flag — `EXECUTE_TRADES` is the master flag; `SPORTS_EXECUTE_TRADES` overrides for sports only if set. This allows dry-running sports while live-trading general, or vice versa
- No-game behavior: idle loop — start up, connect to WS, stay alive waiting for game data. Check for upcoming games periodically. Always ready

### Claude's Discretion
- Exact Gamma API query parameters for slug/market lookup
- External stats API selection (research picks best coverage)
- Odds divergence threshold default value
- Race condition protection mechanism (file lock vs in-memory vs other)
- SportsDataAPI class internal structure and error handling
- BudgetCoordinator implementation details

</decisions>

<specifics>
## Specific Ideas

- Slug normalization flagged as concern in STATE.md: "Slug normalization across all 9 sport types needs validation with live Polymarket data before committing to mapping architecture — do not assume NFL/NBA patterns generalize"
- Project init decided: slug-based Gamma lookup bypasses Chroma RAG entirely — do NOT use the existing PolymarketRAG/Chroma vector store for sports market discovery
- Project init decided: separate sports pipeline (not mode toggle) — fundamentally different data flow and timing from general pipeline
- CLOB rate limit (60 orders/min) is shared across pipelines — budget coordinator must account for this in Phase 4+

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `GammaMarketClient` in `agents/polymarket/gamma.py`: existing httpx client for Gamma API — extend with slug-based lookup methods rather than creating a new client
- `SessionBudgetManager` in `agents/application/budget.py`: single-pipeline budget tracking — extend or wrap for multi-pipeline coordination
- `canonicalize_category()` in `agents/application/executor.py`: already identifies sports markets — can inform market type filtering
- `_env_int()`, `_env_bool()`, `_env_float()` helpers (note: inlined in `sports_ws.py` to avoid heavy executor.py imports — same pattern for new code)
- `SportsWSConnector` in `agents/connectors/sports_ws.py`: Phase 1 output — provides `_game_states` dict and `slug` field for mapping

### Established Patterns
- Connectors in `agents/connectors/`: new stats API connector goes here (e.g., `agents/connectors/sports_data.py`)
- Pydantic models in `agents/utils/objects.py`: add `SportsMarketTag` and related models here
- Environment config loaded in `__init__` with sensible defaults
- Logging: `print(f"[tag] key=value")` for structured output

### Integration Points
- `agents/polymarket/gamma.py`: extend `GammaMarketClient` with slug lookup method
- `agents/utils/objects.py`: add `SportsMarketTag` Pydantic model
- `agents/connectors/sports_data.py`: new file for external stats API connector
- `agents/application/budget.py`: extend with `BudgetCoordinator` class
- `.env.example`: add ~10 new env vars (SPORTS_BUDGET_FRACTION, SPORTS_CAP_*, SPORTS_MIN_WALLET_USD, SPORTS_REQUIRE_STATS, SPORTS_ODDS_DIVERGENCE_THRESHOLD, etc.)

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-market-discovery-and-pipeline-architecture*
*Context gathered: 2026-03-06*
