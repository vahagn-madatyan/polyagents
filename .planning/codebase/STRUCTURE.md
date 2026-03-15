# Codebase Structure

**Analysis Date:** 2026-03-03

## Directory Layout

```
polyagents/
├── agents/                      # Core trading application code
│   ├── application/             # High-level trading logic
│   ├── connectors/              # External API integrations
│   ├── polymarket/              # Polymarket-specific clients
│   └── utils/                   # Shared utilities and data models
├── tests/                       # Unit and integration tests
├── docs/                        # Documentation and images
├── scripts/                     # Helper scripts
├── .planning/                   # GSD planning documents (auto-generated)
├── .agents/                     # Agent skills and configurations
├── .claude/                     # Claude-specific configurations
├── local_db_events/             # Ephemeral Chroma vector DB for events
├── local_db_markets/            # Ephemeral Chroma vector DB for markets
├── .env                         # Environment variables (secrets - not committed)
├── .env.example                 # Example environment variables
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Container configuration
├── .pre-commit-config.yaml      # Pre-commit hooks
├── CONTRIBUTING.md              # Contribution guidelines
├── LICENSE.md                   # License
└── README.md                    # Main documentation
```

## Directory Purposes

**agents/application/:**
- Purpose: Orchestration of the autonomous trading workflow
- Contains: Trader and Executor classes, LLM prompts, configuration
- Key files: `trade.py` (Trader), `executor.py` (Executor), `prompts.py` (LLM prompts), `creator.py`, `cron.py`

**agents/connectors/:**
- Purpose: Abstracts external data sources and trading APIs
- Contains: RAG implementation, market/event API clients, news integration
- Key files: `chroma.py` (vector DB), `gamma.py` (Gamma API client), `polymarket.py` (CLOB client), `news.py` (news API), `search.py`

**agents/polymarket/:**
- Purpose: Polymarket-specific protocol integration
- Contains: CLOB trading client, market data mapping, Web3 utilities
- Key files: `polymarket.py` (main CLOB client), `gamma.py` (market data API)

**agents/utils/:**
- Purpose: Shared data models and utilities
- Contains: Pydantic models for type safety, helper functions
- Key files: `objects.py` (all data models), `utils.py` (utilities)

**tests/:**
- Purpose: Unit and integration tests
- Contains: Trade selection tests, news connector tests, event URL tests
- Key files: `test_trade_selection.py`, `test_news_connector.py`, `test_event_url_trader.py`, `test.py`

**docs/:**
- Purpose: Documentation and visual assets
- Contains: Expansion guides, images

**scripts/:**
- Purpose: Build, deployment, and utility scripts
- Used for: Docker builds, local testing automation

**local_db_events/, local_db_markets/:**
- Purpose: Runtime directories for Chroma vector databases
- Lifecycle: Created during pipeline execution, cleaned up at start of next run
- Generated: Yes (ephemeral)
- Committed: No

**.planning/codebase/:**
- Purpose: GSD (Generative Software Development) planning documents
- Generated: Automatically by mapping commands
- Committed: Yes
- Documents: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, STACK.md, INTEGRATIONS.md, CONCERNS.md

## Key File Locations

**Entry Points:**
- `agents/application/trade.py`: Main Trader class with `one_best_trade()` and `analyze_event_url()` methods
- `agents/application/executor.py`: LLM agent Executor with decision-making methods
- `agents/application/cron.py`: Scheduled execution wrapper

**Configuration:**
- `.env`: Runtime environment variables (API keys, wallet keys, RPC URLs, tuning parameters)
- `.env.example`: Template showing all configurable variables
- `agents/application/executor.py` (lines 32-395): Default values and environment variable loading logic

**Core Logic:**
- `agents/application/executor.py`: Trade selection, candidate scoring, budget allocation
- `agents/application/trade.py`: Workflow orchestration, event/market filtering, news context
- `agents/connectors/chroma.py`: Vector database RAG implementation
- `agents/polymarket/polymarket.py`: Web3 trading execution

**Data Models:**
- `agents/utils/objects.py`: Pydantic models (SimpleMarket, SimpleEvent, CandidateTrade, Article, Market, Trade, etc.)

**Prompts:**
- `agents/application/prompts.py`: All LLM prompt templates (superforecaster, market analyst, filter prompts)

**Testing:**
- `tests/test_trade_selection.py`: Unit tests for candidate selection, allocation, parsing
- `tests/test_news_connector.py`: News integration tests
- `tests/test_event_url_trader.py`: Single-event pipeline tests

## Naming Conventions

**Files:**
- Python modules: `lowercase_with_underscores.py` (e.g., `polymarket.py`, `trade.py`, `chroma.py`)
- Classes per file: One main class per file, named in PascalCase matching file purpose (e.g., Trader, Executor, Polymarket)
- Test files: `test_<feature>.py` (e.g., `test_trade_selection.py`, `test_news_connector.py`)

**Classes:**
- PascalCase: `Trader`, `Executor`, `Polymarket`, `GammaMarketClient`, `PolymarketRAG`
- Pydantic models: `SimpleMarket`, `SimpleEvent`, `CandidateTrade`, `Article`

**Functions:**
- camelCase for private/internal: `_env_bool()`, `_safe_float()`, `_bucket_from_text()`, `_candidate_score_key()`
- snake_case for public methods: `one_best_trade()`, `build_trade_candidates()`, `allocate_selected_candidates()`

**Variables:**
- snake_case: `market_id`, `outcome_prices`, `usdc_balance`, `filtered_markets`
- UPPER_CASE for constants: `TRADE_CANDIDATE_COUNT`, `POLYGON_WALLET_PRIVATE_KEY`
- Suffixes for related concepts: `_by_market_id` (dict), `_json` (JSON string), `_raw` (unparsed), `_normalized` (processed)

**Types:**
- Pydantic models: `SimpleMarket`, `CandidateTrade`, `Article`
- Dict types: Use comment for clarity (e.g., `# Dict[int, str]` or `context_by_market_id: Dict[int, str]`)

## Where to Add New Code

**New Feature (Trading Strategy, Filter, etc.):**
- Primary code: `agents/application/trade.py` (Trader class methods) or `agents/application/executor.py` (Executor class methods)
- Tests: `tests/test_<feature>.py`
- Prompts (if LLM-driven): Add method to `agents/application/prompts.py`
- Data models (if needed): Add Pydantic class to `agents/utils/objects.py`

**New Connector (External API Integration):**
- Implementation: `agents/connectors/<service_name>.py` (new file)
- Pattern: Create class wrapping the external service, expose high-level methods
- Example: `agents/connectors/news.py` wraps NewsAPI, exposes `get_articles_for_cli_keywords()`
- Register in: `agents/application/trade.py` (Trader.__init__)

**New Market/Event Mapping or Transformation:**
- Implementation: `agents/polymarket/polymarket.py` (add method to Polymarket class)
- Pattern: Add `map_api_to_<type>()` method returning Pydantic object
- Data model (if needed): Add to `agents/utils/objects.py`

**Utilities:**
- Shared helpers: `agents/utils/utils.py`
- Type-safe helpers: Consider if they belong in `agents/utils/objects.py` as model methods

**Testing:**
- Unit tests: `tests/test_<module>.py`
- Mocking pattern: Use simple Python classes that mimic interface (see `test_trade_selection.py` for DummyLogger, DummyGamma patterns)
- No external API calls in tests (mock all connectors)

## Special Directories

**local_db_events/:**
- Purpose: Ephemeral Chroma vector database for event embeddings
- Generated: Yes (created at runtime during `Executor.filter_events_with_rag()`)
- Committed: No (in .gitignore)
- Lifecycle: Created fresh each run, cleaned at pipeline start via `Trader.clear_local_dbs()`
- Subdirectory: `chroma/` contains the actual vector DB files

**local_db_markets/:**
- Purpose: Ephemeral Chroma vector database for market embeddings
- Generated: Yes (created at runtime during `Executor.filter_markets()`)
- Committed: No (in .gitignore)
- Lifecycle: Created fresh each run, cleaned at pipeline start via `Trader.clear_local_dbs()`
- Subdirectory: `chroma/` contains the actual vector DB files

**.planning/codebase/:**
- Purpose: Auto-generated GSD planning documents
- Generated: Yes (by `/gsd:map-codebase` command)
- Committed: Yes
- Documents created:
  - `ARCHITECTURE.md` - system design and data flow
  - `STRUCTURE.md` - this file
  - `CONVENTIONS.md` - coding standards
  - `TESTING.md` - test patterns
  - `STACK.md` - technology stack
  - `INTEGRATIONS.md` - external integrations
  - `CONCERNS.md` - technical debt and issues

**.env (forbidden file):**
- Purpose: Environment-specific configuration with secrets
- Generated: No (user-created from .env.example)
- Committed: No (in .gitignore)
- Contains: API keys, private keys, RPC URLs (NEVER commit)
- Never read these contents in code - use `os.getenv()`

## Python Module Organization

```python
# Typical Trader/Executor method structure:
class Trader:
    def __init__(self):
        # Initialize configuration from env vars
        # Initialize connectors (Polymarket, Gamma, Agent, News)
        pass

    def one_best_trade(self):
        """Main pipeline: events → markets → candidates → execution"""
        # 1. Pre-trade setup
        # 2. Event filtering via RAG
        # 3. Market mapping and filtering
        # 4. News context (optional)
        # 5. Candidate generation and selection
        # 6. Execution
        pass

    def _helper_method(self):
        """Private helpers prefixed with _"""
        pass


class Executor:
    def __init__(self):
        # Load environment configuration
        # Initialize LLM, connectors, configuration
        pass

    # Public API methods
    def filter_events_with_rag(self, events: List[SimpleEvent]):
        """Filter events using vector DB similarity search"""
        pass

    def build_trade_candidates(self, markets: List[tuple]):
        """Generate candidates via LLM reasoning"""
        pass

    # Internal helpers
    def _invoke_llm(self, payload, operation_name: str) -> str:
        """Call LLM and log usage"""
        pass

    def _parse_trade_decision(self, superforecast, trade_content, outcomes):
        """Parse LLM responses into structured data"""
        pass
```

