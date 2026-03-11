# Phase 3: Pre-Game Analysis and LLM Integration - Research

**Researched:** 2026-03-06
**Domain:** Sports LLM prompt design, probability cache design, pre-game pipeline orchestration, CLOB trade execution integration
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Pre-Game Trigger Timing**
- Dual-trigger: analyze on market discovery (slug table maps game to market) AND re-analyze at a configurable lead time before game start
- Doubles LLM calls but provides the best data freshness — first analysis gives early positioning, refresh ensures latest stats/odds
- On pipeline restart: re-analyze only if cached probability is older than configurable TTL (`SPORTS_PREGAME_CACHE_TTL_MINUTES`). Skip games with fresh cache entries
- Analyze ALL mapped games, not just value-bet flagged ones — let the LLM make the trading decision, don't pre-filter

**Pre-Game Execution Model**
- Immediate per-game execution — each game analyzed independently; if confidence is high enough, place the trade right away
- No batch/ranking across games — fastest to market, consistent with the existing general pipeline approach
- Budget caps and per-sport caps naturally constrain total exposure

**LLM Prompt Design**
- Sports-specialized system prompt: LLM is framed as a sports betting analyst, NOT the generic prediction market superforecaster
- Two-stage prompt (mirrors existing pipeline): Stage 1 = blind probability estimate (no Polymarket price), Stage 2 = price-aware trade decision with Polymarket prices shown
- Include value-bet divergence signal in Stage 2: "External odds imply X% home win vs Polymarket's Y%"
- Inject all game context from `SportsDataConnector.get_game_context()`: team stats (win rates, recent form), H2H records, external bookmaker odds
- Per-sport prompt fragments deferred to v2 (SIG-01) — v1 uses one unified sports prompt for all leagues
- Output format: same JSON schema as existing `one_best_trade` (CandidateTrade-compatible: selected_outcome, side, price, size_fraction, rationale, risk_factors, counter_case). Maximizes code reuse with Executor's parsing logic

**Probability Cache**
- File-persisted JSON — survives pipeline restarts, enables stale-check on restart
- Keyed by `game_id` (from WS gameId) — one cache entry per game
- Full analysis snapshot stored: probability estimate, confidence gap, rationale, risk factors, input data (stats/odds at time of analysis), LLM response text, timestamp
- Staleness: fixed TTL via `SPORTS_PREGAME_CACHE_TTL_MINUTES` (e.g., 30 min default). Re-analysis triggers on next event loop iteration after expiry
- Cache entry retrievable by game_id for Phase 4's fast-path decisions

**Trade Aggressiveness**
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

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TRD-01 | Bot runs pre-game analysis pipeline that evaluates sports markets and places trades before game starts | `SportsExecutor.analyze_game()` + `SportsTrader.run_pregame_pipeline()` wired into `sports.py` event loop on slug-table mapping events |
| TRD-04 | Bot uses sports-specific LLM prompts that inject game context (score, period, teams, stats, odds) for trade decisions | `Prompter.sports_superforecaster()` and `Prompter.sports_trade_decision()` methods; context from `SportsDataConnector.get_game_context()` |
| TRD-06 | Bot uses pre-game LLM probability cache for fast-path live decisions, reserving full LLM calls for major state changes | `PregameCache` class (file-persisted JSON, game_id keyed, TTL-checked) — cache entry written after pre-game analysis, read by Phase 4 live loop |
</phase_requirements>

---

## Summary

Phase 3 wires together all Phase 2 components (WS connector, market discovery, data connector, budget coordinator) into an active pre-game trading loop. The core work is: (1) adding sports-specific prompt methods to the existing `Prompter` class, (2) building `SportsExecutor` that mirrors the existing `Executor.source_best_trade()` two-stage LLM pattern but with sports context injection, (3) building a file-persisted `PregameCache` keyed by `game_id`, and (4) wiring a `SportsTrader` orchestrator into the `sports.py` event loop where the "trade logic is Phase 3+" placeholder sits.

All the hard infrastructure exists: `BudgetCoordinator` is ready to gate spending, `SportsDataConnector.get_game_context()` already aggregates everything the LLM prompt needs, `CandidateTrade` Pydantic model is reusable as the trade output container, and `Executor._parse_trade_decision()` is reusable for JSON parsing if the output schema matches. The primary new code in Phase 3 is the sports prompt templates, the cache file manager, and the orchestration logic that polls the WS connector's game states and drives per-game analysis.

The probability cache is a bridge artifact: written in Phase 3, consumed in Phase 4. Its schema must be designed Phase 4-first: what fields does the live trading fast-path need? Game ID, LLM probability estimate (home_win_prob, away_win_prob), confidence gap, which side was selected, timestamp, and TTL. Designing this now prevents Phase 4 rework.

**Primary recommendation:** Build `SportsExecutor` as a standalone class (not extending `Executor`) that imports and reuses `Executor._invoke_llm()` and `Executor._parse_trade_decision()` via composition. Add two methods to `Prompter`: `sports_superforecaster()` and `sports_trade_decision()`. Use synchronous `self.llm.invoke()` to match existing patterns — `ainvoke()` would require an event loop in `sports.py` which is currently threading-based, not async.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `langchain-openai` | installed in venv | `ChatOpenAI` LLM invocation | Already used by `Executor`; `SportsExecutor` reuses same client |
| `langchain-core` | installed in venv | `SystemMessage`, `HumanMessage` | Same pattern as existing pipeline |
| `pydantic` | v2 (via existing) | `SportsAnalysisCache` model for typed cache entries | All data models in `objects.py` use Pydantic; consistency required |
| `json` (stdlib) | stdlib | File-persisted probability cache | No external dep needed; already used by `BudgetCoordinator` |
| `filelock` | installed in venv | Cache file write safety | Already used by `BudgetCoordinator`; same pattern for cache |
| `time` (stdlib) | stdlib | TTL checking for cache staleness | Consistent with `BudgetCoordinator` timestamp approach |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `os` (stdlib) | stdlib | Env var reading via `_env_float/_env_int/_env_bool` | Inline helpers per project pattern — do NOT import from executor.py |
| `typing` (stdlib) | stdlib | Type hints | All new files use `from typing import Optional, Dict, Any` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Sync `llm.invoke()` | Async `llm.ainvoke()` | `ainvoke()` requires `asyncio.run()` or an async event loop; `sports.py` is threading-based not async; sync is the right call for v1 |
| File-persisted JSON cache | In-memory dict | File cache survives pipeline restarts (required by spec); in-memory would not |
| File-persisted JSON cache | Redis/SQLite | No new infrastructure dependencies needed; JSON file with filelock matches `BudgetCoordinator` pattern already in codebase |
| `CandidateTrade` (reuse) | New `SportsTrade` model | Reusing `CandidateTrade` maximizes code reuse with `Executor._parse_trade_decision()` and existing trade logging |

**Installation:**
```bash
# No new packages needed — all dependencies already installed in .venv
# Verify:
.venv/bin/pip list | grep -E "langchain|pydantic|filelock"
```

---

## Architecture Patterns

### Recommended Project Structure
```
agents/
├── application/
│   ├── prompts.py           # ADD: sports_superforecaster(), sports_trade_decision()
│   ├── sports_executor.py   # NEW: SportsExecutor class
│   └── sports_trader.py     # NEW: SportsTrader orchestrator (pre-game branch)
├── utils/
│   └── objects.py           # ADD: SportsAnalysisCache Pydantic model
├── sports.py                # MODIFY: wire SportsTrader into event loop
tests/
├── test_sports_executor.py  # NEW: unit tests for SportsExecutor
└── test_sports_trader.py    # NEW: unit tests for SportsTrader pre-game path
```

### Pattern 1: Two-Stage LLM Invocation (existing pattern to mirror)

**What:** Stage 1 = blind probability estimate without market prices; Stage 2 = price-aware trade decision with Polymarket prices and divergence signal
**When to use:** Every pre-game analysis call. Mirrors `Executor.source_best_trade()` exactly.
**Example:**
```python
# Source: agents/application/executor.py lines 986-1013 (existing pattern)
# SportsExecutor mirrors this pattern with sports-specific prompts

def analyze_game(
    self,
    game_state: SportGameState,
    market_tag: SportsMarketTag,
    game_context: dict,
) -> CandidateTrade:
    outcomes = ["Yes", "No"]  # moneyline is binary: home team wins or not
    outcome_prices = self._parse_outcome_prices(market_tag.outcome_prices)

    # Stage 1: blind probability estimate (sports persona, no Polymarket price)
    stage1_prompt = self.prompter.sports_superforecaster(
        game_state=game_state,
        game_context=game_context,
    )
    superforecast_content = self._invoke_llm(stage1_prompt, "sports_superforecaster")

    # Stage 2: price-aware trade decision with value-bet divergence signal
    stage2_prompt = self.prompter.sports_trade_decision(
        prediction=superforecast_content,
        game_state=game_state,
        game_context=game_context,
        outcomes=outcomes,
        outcome_prices=outcome_prices,
        polymarket_price=outcome_prices[0],  # YES token price
    )
    trade_content = self._invoke_llm(stage2_prompt, "sports_trade_decision")

    parsed = self._parse_trade_decision(
        superforecast_content=superforecast_content,
        trade_content=trade_content,
        outcomes=outcomes,
        outcome_prices=outcome_prices,
    )
    return CandidateTrade(
        market_id=int(market_tag.market_id),
        question=market_tag.question,
        category_bucket="sports",
        outcomes=outcomes,
        outcome_prices=outcome_prices,
        token_ids=[market_tag.token_id_yes, market_tag.token_id_no],
        **parsed,
    )
```

### Pattern 2: PregameCache File-Persisted JSON

**What:** JSON file keyed by `game_id`, checked for TTL staleness on each access. Filelock for write safety. Written after pre-game analysis, readable by Phase 4.
**When to use:** After every successful `analyze_game()` call. Checked at pipeline start for restart skip logic.
**Example:**
```python
# Source: agents/application/budget.py (BudgetCoordinator pattern — same file/lock approach)
import json
import os
import time
from filelock import FileLock

class PregameCache:
    def __init__(self) -> None:
        self._cache_path = os.environ.get(
            "SPORTS_PREGAME_CACHE_PATH", "/tmp/polyagents_pregame_cache.json"
        )
        self._lock_path = self._cache_path + ".lock"
        self._ttl_minutes = _env_int("SPORTS_PREGAME_CACHE_TTL_MINUTES", 30)

    def is_fresh(self, game_id: int) -> bool:
        """Return True if a non-expired entry exists for game_id."""
        entry = self.get(game_id)
        if entry is None:
            return False
        age_minutes = (time.time() - entry["timestamp"]) / 60
        return age_minutes < self._ttl_minutes

    def get(self, game_id: int) -> Optional[dict]:
        data = self._read()
        return data.get(str(game_id))

    def set(self, game_id: int, entry: dict) -> None:
        lock = FileLock(self._lock_path, timeout=5)
        with lock:
            data = self._read_unlocked()
            data[str(game_id)] = {**entry, "timestamp": time.time()}
            self._write_unlocked(data)

    def _read(self) -> dict:
        lock = FileLock(self._lock_path, timeout=5)
        with lock:
            return self._read_unlocked()

    def _read_unlocked(self) -> dict:
        if not os.path.exists(self._cache_path):
            return {}
        with open(self._cache_path) as f:
            return json.load(f)

    def _write_unlocked(self, data: dict) -> None:
        with open(self._cache_path, "w") as f:
            json.dump(data, f)
```

### Pattern 3: Sports Prompt Template Design

**What:** Two methods added to `Prompter` class: `sports_superforecaster()` and `sports_trade_decision()`
**When to use:** Called by `SportsExecutor.analyze_game()`
**Example:**
```python
# Source: agents/application/prompts.py (adding to Prompter class)
# Mirrors superforecaster() and one_best_trade() but with sports persona

def sports_superforecaster(
    self,
    game_state: "SportGameState",
    game_context: dict,
) -> list:
    home = game_state.home_team
    away = game_state.away_team
    league = game_state.league.upper()

    home_stats = game_context.get("home_stats") or {}
    away_stats = game_context.get("away_stats") or {}
    h2h = game_context.get("head_to_head") or []
    odds = game_context.get("external_odds") or {}

    system = SystemMessage(content=(
        "You are an expert sports betting analyst with deep knowledge of "
        f"{league} team performance, historical trends, and statistical modeling. "
        "Your job is to estimate the true probability of the home team winning "
        "this game based solely on factual data — NOT market prices."
    ))
    human_text = f"""Analyze this upcoming {league} game:

Home team: {home}
Away team: {away}

Team statistics:
- {home} season record: {home_stats.get('wins', 'N/A')}W-{home_stats.get('losses', 'N/A')}L, win rate: {home_stats.get('win_rate', 'N/A'):.3f}, recent form: {home_stats.get('recent_form', 'N/A')}
- {away} season record: {away_stats.get('wins', 'N/A')}W-{away_stats.get('losses', 'N/A')}L, win rate: {away_stats.get('win_rate', 'N/A'):.3f}, recent form: {away_stats.get('recent_form', 'N/A')}

Head-to-head (last {len(h2h)} games): {_format_h2h(h2h, home, away)}

External bookmaker odds:
- {home} implied win probability: {odds.get('implied_home_prob', 'N/A')}
- {away} implied win probability: {odds.get('implied_away_prob', 'N/A')}
- Source: {odds.get('source_bookmaker', 'N/A')}

Estimate the true probability that {home} wins this game.
Give your response as:
I believe {home} has a likelihood `<float>` for outcome of `Yes`.
I believe {home} has a likelihood `<float>` for outcome of `No`.
"""
    return [system, HumanMessage(content=human_text)]


def sports_trade_decision(
    self,
    prediction: str,
    game_state: "SportGameState",
    game_context: dict,
    outcomes: list,
    outcome_prices: list,
    polymarket_price: float,
) -> list:
    odds = game_context.get("external_odds") or {}
    implied_home = odds.get("implied_home_prob")
    divergence_line = ""
    if implied_home is not None:
        divergence_pct = abs(implied_home - polymarket_price) * 100
        divergence_line = (
            f"\nValue-bet signal: External odds imply {implied_home*100:.1f}% "
            f"home win vs Polymarket's {polymarket_price*100:.1f}% "
            f"(divergence: {divergence_pct:.1f}%)"
        )

    system = SystemMessage(content=(
        "You are an expert sports betting analyst. Make precise trade decisions "
        "based on probability estimates versus market prices. Output JSON only."
    ))
    human_text = f"""Your probability estimate:
{prediction}

Current Polymarket market:
- Outcomes: {outcomes}
- Current prices: {outcome_prices}
{divergence_line}

Return JSON only using this schema:
{{
  "probabilities": [{{"outcome": "<string>", "likelihood": <float 0-1>}}],
  "selected_outcome": "<string from outcomes>",
  "side": "<BUY or SELL>",
  "price": <float 0-1>,
  "size_fraction": <float 0-1>,
  "rationale": "<1-2 sentences>",
  "risk_factors": ["<risk 1>", "<risk 2>"],
  "counter_case": "<1 sentence opposing view>"
}}
Constraints:
- size_fraction: fraction of your sport budget cap to risk (0.05-0.50)
- Only select the outcome with clear edge over Polymarket price
- If no edge exists, set size_fraction to 0.0
"""
    return [system, HumanMessage(content=human_text)]
```

### Pattern 4: Pre-Game Pipeline Trigger Points in sports.py

**What:** Two integration points in `sports.py` event loop where `SportsTrader.run_pregame_analysis()` is called
**When to use:** (1) On slug table build/refresh — analyze newly mapped games; (2) On each event loop iteration — check if any mapped games need refresh analysis
**Example:**
```python
# Source: agents/sports.py lines 130-159 (existing event loop to modify)
# Integration pattern — SportsTrader gets called at two points:

# Point 1: After slug table built (market discovery trigger)
slug_table, unmapped = gamma_client.build_slug_table(game_states)
for game_id, market_tag in slug_table.items():
    if not pregame_cache.is_fresh(game_id):
        game_state = game_states.get(game_id)
        if game_state:
            trader.run_pregame_analysis(game_id, game_state, market_tag)

# Point 2: Event loop — TTL expiry check (lead-time refresh trigger)
while True:
    now = time.time()
    if now - last_slug_refresh >= slug_refresh_interval:
        # refresh slug table (existing)
        ...

    # Phase 3: check for stale cache entries and re-analyze
    for game_id, market_tag in slug_table.items():
        if not pregame_cache.is_fresh(game_id):
            game_state = connector.get_all_game_states().get(game_id)
            if game_state and not game_state.ended:
                trader.run_pregame_analysis(game_id, game_state, market_tag)

    time.sleep(1)
```

### Pattern 5: Confidence Gap Gate Before Trade Placement

**What:** After LLM returns `CandidateTrade`, check `confidence_gap >= SPORTS_MIN_CONFIDENCE_GAP` before calling CLOB
**When to use:** Inside `SportsTrader.run_pregame_analysis()`, after `SportsExecutor.analyze_game()`
**Example:**
```python
# Source: pattern derived from CONTEXT.md trade aggressiveness decision
min_gap = _env_float("SPORTS_MIN_CONFIDENCE_GAP", 0.10)

candidate = executor.analyze_game(game_state, market_tag, game_context)

# Gate 1: confidence gap
if candidate.confidence_gap < min_gap:
    print(f"[sports_trader] skip game_id={game_id} gap={candidate.confidence_gap:.3f} min={min_gap}")
    return

# Gate 2: budget
sport_cap = budget_coordinator.get_sport_cap(game_state.league)
trade_amount = (candidate.parsed_size_fraction or 0.0) * sport_cap
if not budget_coordinator.can_spend_sports(trade_amount, wallet_balance):
    print(f"[sports_trader] skip game_id={game_id} budget_exhausted amount={trade_amount:.2f}")
    return

# Gate 3: dry-run vs live
if dry_run:
    print(f"[sports_trader] dry_run game_id={game_id} would_trade outcome={candidate.suggested_outcome} amount={trade_amount:.2f}")
else:
    # execute CLOB order (market order via token_id)
    token_id = (
        market_tag.token_id_yes
        if candidate.suggested_outcome == "Yes"
        else market_tag.token_id_no
    )
    polymarket.execute_market_order_for_token(token_id=token_id, amount=trade_amount)
    budget_coordinator.record_sports_trade(trade_amount, game_state.league)
```

### Anti-Patterns to Avoid

- **Importing `Executor` as a base class for `SportsExecutor`:** `Executor.__init__` imports LangChain, Chroma, and Gamma — pulls in the full heavy dep chain. Use composition (instantiate `ChatOpenAI` directly in `SportsExecutor`) or call specific utility functions via import, never inherit.
- **Hardcoding wallet balance:** `SPORTS_INITIAL_WALLET_USD` is a placeholder. Phase 3 must replace it with `polymarket.get_usdc_balance()` call to get real CLOB balance before computing sport caps.
- **Calling `get_game_context()` on every event loop tick:** `SportsDataConnector` has TTL caches (24h for stats, 5min for odds) but HTTP calls still happen on cache miss. Only call `get_game_context()` when actually running analysis — not on every loop iteration.
- **Writing to cache before verifying trade result:** Write the cache entry before attempting trade execution (TTL skip logic is about the analysis, not the trade outcome). If trade fails, the cache still records the analysis decision with `trade_attempted=True`, `trade_error=str(err)`.
- **Blocking the event loop with LLM calls:** Each `analyze_game()` call makes 2 synchronous LLM calls. For many simultaneous games, use `threading.Thread` per game analysis — same daemon thread pattern used for the WS connector.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON parsing of LLM trade output | Custom regex parser | `Executor._parse_json_object()` + `Executor._parse_trade_decision()` | Already handles markdown code blocks, partial JSON, fallback to regex field extraction |
| Probability extraction from LLM text | New regex | `Executor._parse_probability_lines()` | Handles the `likelihood \`0.65\` for outcome of \`Yes\`` format |
| CLOB trade placement | CLOB API wrapper | `Polymarket.execute_market_order_for_token(token_id, amount)` | Already handles signing, order args, error logging |
| CLOB balance fetch | ERC20 balance polling | `Polymarket.get_usdc_balance()` → calls `get_usdc_balance_report()` | Handles both collateral and CLOB balance endpoints, normalizes to USDC float |
| Budget cross-process locking | Custom filelock | `BudgetCoordinator.can_spend_sports()` + `record_sports_trade()` | Already uses filelock, handles concurrent pipeline race conditions |
| File lock for cache writes | Custom mutex | `filelock.FileLock` | Already installed, already used by `BudgetCoordinator` |
| LLM size_fraction → USDC amount | Custom allocation | `size_fraction * budget_coordinator.get_sport_cap(league)` | This is the established pattern; `allocate_confidence_weighted()` is for multi-candidate batch, sports uses per-game immediate sizing |

**Key insight:** The general pipeline's `Executor` class contains all JSON parsing, LLM invocation, and trade decision parsing logic. Phase 3 should call those functions, not re-implement them. The only net-new code is sports prompt templates, cache file management, and orchestration wiring.

---

## Common Pitfalls

### Pitfall 1: Sync LLM vs Async Confusion
**What goes wrong:** The CONTEXT.md roadmap mentions `llm.ainvoke()` async integration, but `sports.py` is threading-based (not an async event loop). Calling `ainvoke()` from a thread without `asyncio.run()` raises `RuntimeError: no running event loop`.
**Why it happens:** `ainvoke()` is a coroutine; it needs to be awaited in an async context or called via `asyncio.run()`.
**How to avoid:** Use synchronous `self.llm.invoke()` for v1, exactly as `Executor._invoke_llm()` does. If async is desired in future, refactor `sports.py` to use `asyncio.run()` as the main entry point — but that is a separate architectural change, not a Phase 3 concern.
**Warning signs:** `RuntimeError: no running event loop` in logs.

### Pitfall 2: Cache TTL Clock Skew on Restart
**What goes wrong:** Cache file timestamps use `time.time()` (wall clock). If system clock jumps backward (NTP correction) or the process pauses, TTL comparisons may produce wrong results.
**Why it happens:** `time.time()` is affected by system clock changes; `time.monotonic()` is not.
**How to avoid:** Use `time.time()` for cache timestamps (must survive process restarts — monotonic resets on restart). Accept the clock skew risk as acceptable for a 30-minute TTL. Document this as a known limitation.
**Warning signs:** Cache entries that never expire or always appear stale.

### Pitfall 3: game_id Type Mismatch (int vs str)
**What goes wrong:** JSON keys are always strings. `SportGameState.game_id` is typed as `int`. Cache lookups with `data.get(game_id)` (int) on a JSON-loaded dict will always return `None` because JSON keys are strings.
**Why it happens:** `json.load()` returns all keys as strings. Python `dict.get(42)` != `dict.get("42")`.
**How to avoid:** Always coerce to `str(game_id)` for cache reads and writes. Use `data.get(str(game_id))` consistently. Enforce this in `PregameCache.get()` and `PregameCache.set()`.
**Warning signs:** Cache always shows as empty even after writes; every game gets re-analyzed on every loop.

### Pitfall 4: LLM Returns size_fraction=0 or Missing JSON
**What goes wrong:** LLM occasionally returns malformed JSON, empty responses, or `size_fraction: 0` when it sees no edge. The pipeline must handle these gracefully without crashing.
**Why it happens:** GPT model output is probabilistic; prompt formatting or token limits can produce partial responses.
**How to avoid:** Wrap `analyze_game()` in try/except and return `None` on error. Check `candidate.parsed_size_fraction` for None or 0.0 before computing trade amount. The confidence gate (`confidence_gap < min_gap`) naturally drops zero-size trades.
**Warning signs:** `NoneType has no attribute` errors in logs; trades for $0.00 appearing in dry-run output.

### Pitfall 5: Missing outcome_prices on SportsMarketTag
**What goes wrong:** `SportsMarketTag.outcome_prices` is `Optional[str]` — it may be `None` or `"0.6,0.4"` (comma-separated string, not a list). `SportsExecutor` needs to parse this correctly.
**Why it happens:** `outcome_prices` is stored as a serialized string in `SportsMarketTag` (mirrors how `SimpleMarket` stores them as `str`). The list-parsing pattern from `Executor._parse_literal_list()` handles this.
**How to avoid:** Parse `market_tag.outcome_prices` using the same approach as `Executor._parse_literal_list()`. If None or empty, use `[0.5, 0.5]` as fallback (equal priors).
**Warning signs:** `TypeError` when indexing outcome_prices; LLM given wrong price inputs.

### Pitfall 6: Analyzer Blocks Event Loop for Many Games
**What goes wrong:** If 10 games are simultaneously mapped in `slug_table` and each `analyze_game()` call makes 2 LLM round-trips (~3-5 seconds each), the event loop is blocked for 60-100 seconds analyzing all games serially.
**Why it happens:** Synchronous LLM calls block the calling thread; the main event loop also sleeps 1 second per tick.
**How to avoid:** Spawn a daemon `threading.Thread` for each `run_pregame_analysis()` call (same pattern as `sports-ws` daemon thread). Use a set to track `in_flight_game_ids` to prevent duplicate concurrent analyses of the same game.
**Warning signs:** Slug table refreshes falling behind; game states going stale while analysis is running.

---

## Code Examples

Verified patterns from existing codebase:

### LLM Invocation (reuse as-is)
```python
# Source: agents/application/executor.py line 442-469
# SportsExecutor uses the same self.llm.invoke() pattern

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

class SportsExecutor:
    def __init__(self) -> None:
        model_name = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
        llm_kwargs = {"model": model_name}
        if not model_name.lower().startswith("gpt-5"):
            temp = os.environ.get("OPENAI_TEMPERATURE")
            if temp:
                llm_kwargs["temperature"] = float(temp)
        else:
            llm_kwargs["temperature"] = 1
        self.llm = ChatOpenAI(**llm_kwargs)
        self.prompter = Prompter()

    def _invoke_llm(self, payload, operation_name: str) -> str:
        result = self.llm.invoke(payload)
        print(f"[sports_executor] op={operation_name} tokens={getattr(result, 'usage_metadata', {})}")
        return result.content
```

### Budget Check Before Trade (existing pattern)
```python
# Source: agents/application/budget.py lines 132-137
# BudgetCoordinator.can_spend_sports() already enforces min_wallet_usd

wallet_balance = polymarket.get_usdc_balance()  # real CLOB balance
sport_cap = budget_coordinator.get_sport_cap(league)  # respects SPORTS_CAP_{LEAGUE}
trade_amount = size_fraction * sport_cap

if budget_coordinator.can_spend_sports(trade_amount, wallet_balance):
    # proceed with trade
    budget_coordinator.record_sports_trade(trade_amount, league)
```

### CLOB Market Order Placement (existing pattern)
```python
# Source: agents/polymarket/polymarket.py line 818-824
# Use market orders (not limit orders) for pre-game sports — speed matters

def execute_market_order_for_token(self, token_id: str, amount: float) -> str:
    order_args = MarketOrderArgs(token_id=str(token_id), amount=float(amount))
    signed_order = self.client.create_market_order(order_args)
    # ... returns order response string
```

### Real CLOB Balance Fetch (replaces SPORTS_INITIAL_WALLET_USD placeholder)
```python
# Source: agents/polymarket/polymarket.py line 838-840
# In SportsTrader.__init__() or at pipeline startup:

from agents.polymarket.polymarket import Polymarket
polymarket = Polymarket(initialize_clob_client=True)
wallet_balance = polymarket.get_usdc_balance()  # returns float (USDC)
budget_coordinator = BudgetCoordinator(wallet_balance=wallet_balance)
```

### Env Var Inline Helper (mandatory pattern per project conventions)
```python
# Source: agents/sports.py lines 27-54 (same pattern in all sports modules)
# DO NOT import _env_float from executor.py — inline it

def _env_float(key: str, default: float) -> float:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default
```

### SportsAnalysisCache Pydantic Model (new, for objects.py)
```python
# Source: agents/utils/objects.py pattern (all models in this file use Pydantic)
from pydantic import BaseModel, Field
from typing import Any, Optional

class SportsAnalysisCache(BaseModel):
    game_id: int
    league: str
    home_team: str
    away_team: str
    timestamp: float            # time.time() at analysis
    llm_home_win_prob: float    # probability estimate for home team win
    llm_away_win_prob: float    # probability estimate for away team win
    confidence_gap: float       # |top_prob - second_prob|
    selected_outcome: str       # "Yes" or "No"
    selected_side: str          # "BUY" or "SELL"
    size_fraction: float        # LLM-suggested size fraction
    rationale: str
    risk_factors: list[str] = Field(default_factory=list)
    counter_case: str = ""
    polymarket_price_at_analysis: float  # market price when analyzed
    external_implied_prob: Optional[float] = None  # bookmaker implied prob
    trade_attempted: bool = False
    trade_error: Optional[str] = None
    superforecast_response: str = ""    # raw LLM Stage 1 text
    trade_response: str = ""            # raw LLM Stage 2 text
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `SPORTS_INITIAL_WALLET_USD` placeholder | `Polymarket.get_usdc_balance()` real fetch | Phase 3 | Budget allocation is accurate; no hardcoded amounts |
| "trade logic is Phase 3+" placeholder in sports.py | `SportsTrader.run_pregame_analysis()` wired in | Phase 3 | Active pre-game trading enabled |
| No sports-specific prompts | `Prompter.sports_superforecaster()` + `sports_trade_decision()` | Phase 3 | LLM framed as sports betting analyst with full game context |
| No probability cache | `PregameCache` file-persisted JSON | Phase 3 | Phase 4 fast-path enabled; restart-resilient |

**Deprecated/outdated:**
- `SPORTS_INITIAL_WALLET_USD` env var: Replaced by real CLOB balance fetch in Phase 3. Remove the placeholder and fetch real balance on startup. Keep env var as a dry-run override only.

---

## Open Questions

1. **Polymarket init in sports pipeline vs general pipeline — shared or separate client?**
   - What we know: `Polymarket(initialize_clob_client=True)` creates a Web3 connection and CLOB auth; it's expensive to construct
   - What's unclear: Should `SportsTrader` create its own `Polymarket` instance or receive one injected? The general pipeline (`Trader`) creates one in `__init__`
   - Recommendation: `SportsTrader` creates its own `Polymarket` instance. It's a separate process — no sharing needed. Use `initialize_clob_client=False` for dry-run mode to avoid auth overhead.

2. **Thread-per-game vs serial analysis**
   - What we know: Each `analyze_game()` makes 2 LLM calls (~3-5s each); blocking serial analysis is slow for many simultaneous games
   - What's unclear: How many games are typically in `slug_table` simultaneously? If usually 1-3, serial is fine. If 10+, threading matters.
   - Recommendation: Implement with a `threading.Thread` per game analysis and an `_in_flight` set guard. This future-proofs without blocking the event loop.

3. **Cache file location — /tmp vs project directory**
   - What we know: `BudgetCoordinator` uses `/tmp/polyagents_budget.json`; consistent location
   - What's unclear: `/tmp` is cleared on system restart; for long-running deploys this may cause unnecessary re-analysis after OS restart
   - Recommendation: Default to `/tmp/polyagents_pregame_cache.json` (consistent with budget coordinator). Make configurable via `SPORTS_PREGAME_CACHE_PATH`. Document that first restart after OS reboot will re-analyze all games.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (configured in pyproject.toml) |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` testpaths=["tests"] asyncio_mode="auto" |
| Quick run command | `.venv/bin/python -m pytest tests/test_sports_executor.py tests/test_sports_trader.py -x -q` |
| Full suite command | `.venv/bin/python -m pytest tests/test_sports_executor.py tests/test_sports_trader.py tests/test_sports_pipeline.py tests/test_budget_coordinator.py -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRD-01 | Pre-game analysis pipeline runs and places/logs trades for mapped games | integration (mocked LLM + CLOB) | `.venv/bin/python -m pytest tests/test_sports_trader.py::TestPregamePipeline -x` | Wave 0 |
| TRD-01 | Dry-run mode logs would-trade without calling CLOB | unit | `.venv/bin/python -m pytest tests/test_sports_trader.py::TestDryRun -x` | Wave 0 |
| TRD-01 | Pipeline skips games with fresh cache on restart | unit | `.venv/bin/python -m pytest tests/test_sports_trader.py::TestCacheRestartSkip -x` | Wave 0 |
| TRD-04 | sports_superforecaster() includes team stats, H2H, win rates | unit | `.venv/bin/python -m pytest tests/test_sports_executor.py::TestSportsPrompts::test_superforecaster_includes_game_context -x` | Wave 0 |
| TRD-04 | sports_trade_decision() includes value-bet divergence signal | unit | `.venv/bin/python -m pytest tests/test_sports_executor.py::TestSportsPrompts::test_trade_decision_includes_divergence -x` | Wave 0 |
| TRD-04 | analyze_game() returns CandidateTrade with parsed outcome | unit | `.venv/bin/python -m pytest tests/test_sports_executor.py::TestAnalyzeGame -x` | Wave 0 |
| TRD-06 | PregameCache.set() persists entry keyed by game_id | unit | `.venv/bin/python -m pytest tests/test_sports_trader.py::TestPregameCache::test_set_and_get -x` | Wave 0 |
| TRD-06 | PregameCache.is_fresh() returns False after TTL expiry | unit | `.venv/bin/python -m pytest tests/test_sports_trader.py::TestPregameCache::test_ttl_expiry -x` | Wave 0 |
| TRD-06 | PregameCache.get() returns None for unknown game_id | unit | `.venv/bin/python -m pytest tests/test_sports_trader.py::TestPregameCache::test_miss_returns_none -x` | Wave 0 |
| TRD-06 | Cache game_id key coercion: int and str key both hit same entry | unit | `.venv/bin/python -m pytest tests/test_sports_trader.py::TestPregameCache::test_game_id_coercion -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest tests/test_sports_executor.py tests/test_sports_trader.py -x -q`
- **Per wave merge:** `.venv/bin/python -m pytest tests/test_sports_executor.py tests/test_sports_trader.py tests/test_sports_pipeline.py tests/test_budget_coordinator.py -q`
- **Phase gate:** Full sports test suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_sports_executor.py` — covers TRD-04 (prompt content, analyze_game() output)
- [ ] `tests/test_sports_trader.py` — covers TRD-01 (pipeline flow, dry-run) and TRD-06 (cache CRUD, TTL, restart skip)

*(No framework install needed — pytest already configured and working; 173 sports tests pass)*

---

## Sources

### Primary (HIGH confidence)
- Direct read of `agents/application/executor.py` — two-stage LLM pattern, `_invoke_llm`, `_parse_trade_decision`, `_parse_json_object`, `_parse_probability_lines`
- Direct read of `agents/application/prompts.py` — `Prompter` class structure, `superforecaster()`, `one_best_trade()` signatures
- Direct read of `agents/application/budget.py` — `BudgetCoordinator`, `SessionBudgetManager`, filelock pattern
- Direct read of `agents/connectors/sports_data.py` — `SportsDataConnector.get_game_context()` return schema
- Direct read of `agents/sports.py` — event loop structure, integration points for Phase 3
- Direct read of `agents/utils/objects.py` — `CandidateTrade`, `SportGameState`, `SportsMarketTag` schemas
- Direct read of `agents/polymarket/polymarket.py` — `execute_market_order_for_token()`, `get_usdc_balance()`
- Direct read of `.env.example` — existing env var names, convention for naming new vars
- Test suite run: 173 sports tests pass in `test_sports_pipeline.py`, `test_sports_ws.py`, `test_sports_data_connector.py`, `test_budget_coordinator.py`, `test_budget.py`, `test_sports_market_discovery.py`

### Secondary (MEDIUM confidence)
- `pyproject.toml` pytest configuration — `asyncio_mode = "auto"`, testpaths confirmed
- `tests/conftest.py` — event_loop fixture pattern for any async tests added

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed; all patterns verified from existing source
- Architecture: HIGH — mirrors verified existing patterns from `Executor`, `BudgetCoordinator`, `SportsWSConnector`
- Pitfalls: HIGH — identified from direct code inspection (sync/async mismatch, game_id type coercion, cache TTL timing)

**Research date:** 2026-03-06
**Valid until:** 2026-04-06 (stable — no external API changes expected; all risk is internal code)
