# Architecture

**Analysis Date:** 2026-03-03

## Pattern Overview

**Overall:** Layered agent-based autonomous trading system with RAG-powered decision support

**Key Characteristics:**
- Multi-stage filtering pipeline (events → markets → candidates → execution)
- LLM-driven reasoning with OpenAI integration (superforecasting + trade decision)
- Vector database (Chroma) for semantic search over markets and events
- Modular connectors to external APIs (Gamma, Polymarket CLOB, news)
- Dry-run and live execution modes with detailed candidate tracking

## Layers

**Application Layer:**
- Purpose: Orchestrates the autonomous trading workflow and implements LLM-driven decision logic
- Location: `agents/application/`
- Contains: `trade.py` (Trader class - main workflow), `executor.py` (Executor class - LLM agent), `prompts.py` (prompt templates), `creator.py` (market creation), `cron.py` (scheduled execution)
- Depends on: Connector layer, LLM (OpenAI), configuration
- Used by: CLI/external integrations

**Connector Layer:**
- Purpose: Abstracts external data sources and APIs (market data, vectorization, news)
- Location: `agents/connectors/`
- Contains: `chroma.py` (RAG via vector DB), `gamma.py` (market data API), `polymarket.py` (CLOB trading), `search.py` (semantic search), `news.py` (news articles)
- Depends on: Polymarket Gamma API, Chroma vector DB, NewsAPI, Web3/CLOB client libraries
- Used by: Application layer

**Data Models Layer:**
- Purpose: Type definitions and validation for market, event, and trade data
- Location: `agents/utils/objects.py`
- Contains: Pydantic models (SimpleMarket, SimpleEvent, CandidateTrade, Article, Market, Trade)
- Depends on: Pydantic
- Used by: All layers

**Utility Layer:**
- Purpose: Helper functions and shared utilities
- Location: `agents/utils/utils.py`
- Contains: Common utility functions
- Used by: Application and connector layers

## Data Flow

**Main Trading Pipeline (one_best_trade):**

1. **Event Filtering** → Trader fetches all tradeable events, uses RAG to filter relevant ones based on learner-supplied context
   - Input: All events from Gamma API
   - Process: Chroma semantic search on event descriptions
   - Output: Filtered SimpleEvent list

2. **Market Mapping** → Maps filtered events to markets via event-market relationships
   - Input: Filtered events
   - Process: Extract market IDs from event metadata, fetch market details via Gamma API
   - Output: SimpleMarket objects with quality filters (volume, liquidity, price band)

3. **Market Filtering** → RAG filters markets based on relevance
   - Input: Markets mapped from events
   - Process: Chroma semantic search on market descriptions
   - Output: Ranked market tuples (Document, similarity_score)

4. **Category and Sports Filtering** → Optional exclusion of sports markets by category classification
   - Input: Filtered markets
   - Process: Extract category from market metadata/description using `canonicalize_category()`
   - Output: Non-sports markets (if configured)

5. **News Context Building** → Optional supplemental context per market
   - Input: Filtered markets
   - Process: Extract keywords from market/event metadata, fetch relevant news articles
   - Output: Dict mapping market_id → formatted news context string

6. **Candidate Generation** → LLM generates trade candidates for each market
   - Input: Filtered markets with optional news context
   - Process: For each market, invoke LLM in two stages:
     - Superforecaster: Generate probability estimates for outcomes
     - Trade Decision: Select outcome, side (BUY/SELL), price, size based on superforecast
   - Output: List of CandidateTrade objects with LLM reasoning

7. **Candidate Selection** → Rank and filter candidates by confidence gap and category diversity
   - Input: All generated candidates
   - Process: Soft quota selection (minimize diversity while respecting target count)
   - Output: Selected candidates respecting category constraints

8. **Budget Allocation** → Distribute available USDC balance across selected candidates
   - Input: Selected candidates, USDC balance
   - Process: Confidence-weighted allocation with per-market min/max bounds
   - Output: Candidates with allocation_amount_usdc assigned

9. **Execution (Live Mode)** → Place orders on Polymarket CLOB
   - Input: Candidates with allocation amounts
   - Process: Resolve token IDs, execute market orders via Web3
   - Output: Execution status and response per candidate

**Single-Event Pipeline (analyze_event_url):**

Similar to main pipeline but scoped to single event:
1. Parse event URL, resolve to SimpleEvent by slug
2. Check event state (active, not archived/closed)
3. Map to markets, filter, apply news context
4. Generate/select/allocate candidates
5. Execute if EXECUTE_TRADES=true

**State Management:**

- **Configuration State:** Environment variables loaded at Executor/Trader initialization
- **Transient State:** Markets, events, candidates flow through the pipeline in memory
- **Persistent State:**
  - Local vector databases created in `local_db_events/` and `local_db_markets/` directories during RAG operations
  - Cleaned up at start of pipeline (`pre_trade_logic()`)

## Key Abstractions

**Executor:**
- Purpose: LLM agent that makes trading decisions via structured prompts
- Examples: `agents/application/executor.py`
- Pattern: Initialization loads LLM config, provides methods for filtering/scoring/parsing
- Key methods:
  - `filter_events_with_rag()` - semantic search on events
  - `filter_markets()` - semantic search on markets
  - `source_best_trade()` - two-stage LLM call (superforecast + trade decision)
  - `build_trade_candidates()` - batch candidate generation with deduplication
  - `select_trade_candidates()` - soft quota selection by category
  - `allocate_selected_candidates()` - confidence-weighted budget allocation

**Trader:**
- Purpose: Orchestrates end-to-end workflow and handles execution
- Examples: `agents/application/trade.py`
- Pattern: Composes Executor, Polymarket, Gamma, News connectors
- Key methods:
  - `one_best_trade()` - autonomous trading pipeline
  - `analyze_event_url()` - single-event analysis pipeline
  - `_apply_minimum_order_constraints()` - reallocation when orders too small
  - `_execute_candidates()` - places live orders

**PolymarketRAG:**
- Purpose: Vector database abstraction for semantic search
- Examples: `agents/connectors/chroma.py`
- Pattern: Creates ephemeral Chroma databases from JSON data, queries via similarity search
- Key methods:
  - `events()` - index and search events
  - `markets()` - index and search markets
  - Uses OpenAI embeddings (text-embedding-3-small)

**CandidateTrade:**
- Purpose: Immutable data container for a single potential trade
- Examples: `agents/utils/objects.py`
- Pattern: Pydantic BaseModel with nested probability/allocation data
- Tracks: market_id, question, outcomes, LLM reasoning, execution status

**Polymarket:**
- Purpose: Web3 interface to Polymarket CLOB trading
- Examples: `agents/polymarket/polymarket.py`
- Pattern: Wraps py-clob-client, handles authentication and order construction
- Key methods:
  - `execute_market_order_for_token()` - places orders
  - `get_usdc_balance_report()` - fetches wallet state
  - `resolve_token_for_outcome()` - maps outcome to token ID

## Entry Points

**Autonomous Mode:**
- Location: `agents/application/trade.py` (Trader.one_best_trade method)
- Triggers: Cron job or direct invocation
- Responsibilities: Full pipeline execution - events through execution

**Single-Event Mode:**
- Location: `agents/application/trade.py` (Trader.analyze_event_url method)
- Triggers: CLI with event URL parameter
- Responsibilities: Scoped pipeline for specific event

**Executor-Only:**
- Location: `agents/application/executor.py` (Executor class methods)
- Triggers: Direct API calls for testing/analysis
- Responsibilities: LLM reasoning, candidate generation, allocation logic

## Error Handling

**Strategy:** Fail-open with logging; catch and skip problematic items rather than abort entire run

**Patterns:**
- Market fetch failures: Skip individual market, continue pipeline
- LLM parsing failures: Fall back to defaults (e.g., equal probability distribution)
- Event slug resolution: Try direct lookup, then full scan as fallback
- RAG vector DB creation: Fall back to temp directory if filesystem readonly
- Execution failures: Optional skip (TRADE_CONTINUE_ON_EXECUTION_ERROR) or abort
- News fetch failures: Continue without context for that market
- Allocation failures (min order): Remove candidate and reallocate remaining budget

## Cross-Cutting Concerns

**Logging:**
- Uses Python stdlib logging with prefixed operation names: `[openai]`, `[markets]`, `[candidates]`, `[execution]`, `[news]`, `[rag]`, `[portfolio]`, `[run]`, `[rationale]`
- Debug mode via APP_LOG_LEVEL env var
- Controlled verbosity via OPENAI_LOG, TRADE_LOG_RATIONALE flags

**Validation:**
- Pydantic models enforce type safety at boundaries (API responses → internal objects)
- Market quality filters: minimum volume, liquidity, tradeable price bands
- Outcome price validation: must fall in [TRADE_MIN_ENTRY_PRICE, TRADE_MAX_ENTRY_PRICE]
- Candidate tradeable entry price check via `_candidate_has_tradeable_entry_price()`

**Configuration:**
- All runtime behavior controlled via environment variables (no CLI flags except event_url)
- Defaults provided for all config vars
- Type conversion helpers: `_env_bool()`, `_env_int()`, `_env_float()`
- Sensitive values (private keys, API keys) via .env file (not committed)

**Authentication:**
- OpenAI: OPENAI_API_KEY, OPENAI_MODEL, OPENAI_TEMPERATURE
- Polygon wallet: POLYGON_WALLET_PRIVATE_KEY, POLYGON_RPC_URL
- Polymarket: Optional POLYMARKET_SIGNATURE_TYPE, POLYMARKET_FUNDER_ADDRESS
- NewsAPI: Via newsapi-python library (key embedded in connector)

