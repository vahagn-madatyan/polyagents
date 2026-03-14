# Phase 8: Pipeline Integration - Context

**Gathered:** 2026-03-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire `detect_value_bet()` into both pre-game and in-game trading paths as an early filter, and add live wallet balance refresh to BudgetCoordinator. No new trading logic — strictly integrating existing but unused components into the pipeline.

</domain>

<decisions>
## Implementation Decisions

### Value Bet Filter Placement
- Call `detect_value_bet()` BEFORE LLM analysis in both pre-game and in-game paths — saves API cost by skipping analysis on games with no odds divergence
- Pre-game: insert after data fetch (step 1) in `SportsTrader._analyze_and_trade()`, before LLM call
- In-game: insert after market lookup in `InGameTrader._handle_fast_path()`, before LLM call
- Consistent placement in both paths — same position relative to the pipeline

### Skip Behavior
- When `detect_value_bet()` returns False: log a structured skip event AND increment a session counter
- Log format matches existing patterns: `[component] event=no_value_bet game_id=X polymarket_price=Y implied_prob=Z`
- Track filtered count for threshold tuning visibility (e.g., "X/Y games filtered by value bet check")

### Divergence Threshold
- Single threshold for both pre-game and in-game (existing `SPORTS_DIVERGENCE_THRESHOLD` env var)
- Do not split into separate pre-game/in-game thresholds — premature until single threshold is tuned

### Wallet Balance Refresh
- Refresh wallet balance before each trade execution (not on a timer, not per cycle)
- Add `refresh_wallet_balance(polymarket)` method to BudgetCoordinator — single source of truth
- 30-second cooldown: if last refresh was <30s ago, reuse cached value (prevents API spam during rapid in-game trading)
- On API failure: log warning, fall back to last known balance — never halt trading due to balance fetch error
- Skip refresh entirely in dry-run mode (Polymarket client not initialized, env var value is static)

### Implied Probability Source
- Claude's Discretion: pick the best source based on what SportsDataConnector already provides (external odds API preferred if available)
- If implied_prob cannot be determined (missing odds, unsupported sport): skip value bet check and allow the trade through — value bet is an optimization filter, not a safety gate
- In-game path: use pre-game odds (cached from analysis), do not fetch live in-game odds (avoids latency in fast path)

### Dry-Run Behavior
- detect_value_bet() filter is ACTIVE in dry-run — mirrors production behavior exactly
- Wallet refresh is SKIPPED in dry-run — Polymarket client isn't initialized

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SportsDataConnector.detect_value_bet()` (`agents/connectors/sports_data.py:329`): Already implemented — compares `polymarket_price` vs `implied_prob` against `_divergence_threshold`
- `BudgetCoordinator` (`agents/application/budget.py`): Centralized budget management with filelock — wallet_balance refresh method goes here
- `Polymarket.get_usdc_balance()`: Existing method to fetch on-chain USDC balance

### Established Patterns
- Structured logging: `[component] event=X key=value` format throughout all agents
- Skip events: existing patterns like `event=skip_budget_exhausted`, `event=cache_hit` — value bet skip follows same pattern
- Env-configurable thresholds: `_env_float("SPORTS_DIVERGENCE_THRESHOLD", 0.05)` already in SportsDataConnector
- Dry-run gating: `if not self.dry_run:` pattern used consistently for Polymarket API calls

### Integration Points
- Pre-game: `SportsTrader._analyze_and_trade()` in `agents/application/sports_trader.py` — insert after step 1 (data fetch), before step 2 (LLM)
- In-game fast path: `InGameTrader._handle_fast_path()` in `agents/application/ingame_trader.py` — insert after market lookup, before LLM
- In-game slow path: `InGameTrader._handle_slow_path()` — same placement as fast path
- Budget gate: `BudgetCoordinator.can_spend_sports()` at `budget.py:113` — wallet refresh call goes before this
- Pipeline startup: `agents/sports.py:78` — initial wallet_balance fetch stays, refresh logic in BudgetCoordinator handles updates

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches following existing codebase patterns.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 08-pipeline-integration*
*Context gathered: 2026-03-13*
