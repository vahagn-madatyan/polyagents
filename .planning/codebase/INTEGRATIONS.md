# External Integrations

**Analysis Date:** 2026-03-03

## APIs & External Services

**LLM/AI:**
- OpenAI - Powers autonomous trading decisions via ChatGPT models
  - SDK/Client: `openai==1.37.1`
  - Implementation: `langchain_openai.ChatOpenAI` in `agents/application/executor.py`
  - Auth: Environment variable `OPENAI_API_KEY`
  - Model config: `OPENAI_MODEL` env var (default: "gpt-5-mini")
  - Temperature config: `OPENAI_TEMPERATURE` env var

**News & Research:**
- NewsAPI - Aggregates news articles for market context and research
  - SDK/Client: `newsapi-python==0.2.7`
  - Auth: Environment variable `NEWSAPI_API_KEY`
  - Implementation: `agents/connectors/news.py` class `News`
  - Base URL: https://newsapi.org/v2/
  - Endpoints: `/top-headlines`, `/everything`
  - Configuration: Language (en), country (us)
  - Categories: business, entertainment, general, health, science, sports, technology

- Tavily - Web search and research API for real-time information
  - SDK/Client: `tavily-python==0.3.5`
  - Auth: Environment variable `TAVILY_API_KEY`
  - Implementation: `agents/connectors/search.py` (basic instantiation with sample query)
  - Used for: Context search queries to gather market research

**Blockchain/Market Data:**
- Polymarket Gamma API - Market and event data aggregation
  - Base URL: https://gamma-api.polymarket.com
  - Endpoints: `/markets`, `/events`
  - Client: `agents/polymarket/gamma.py` class `GammaMarketClient`
  - HTTP Client: `httpx` with configurable timeouts and connection limits
  - Configuration env vars:
    - `GAMMA_MARKET_FETCH_CONCURRENCY` (default: 24) - Thread pool size for concurrent market fetches
    - `GAMMA_HTTP_MAX_CONNECTIONS` (default: 100)
    - `GAMMA_HTTP_MAX_KEEPALIVE_CONNECTIONS` (default: 40)
    - `GAMMA_HTTP_TIMEOUT_SECONDS` (default: 8)
    - `GAMMA_LOG_MARKET_DETAIL_URL` (default: false)

- Polymarket CLOB API - Order book and trade execution
  - Base URL: https://clob.polymarket.com
  - Endpoints: `/auth/api-key`, order book management, trade endpoints
  - SDK/Client: `py-clob-client==0.17.5`
  - Implementation: `agents/polymarket/polymarket.py` class `Polymarket`
  - Auth: API key generation via CLOB auth endpoint, signature-based authentication
  - Order utilities: `py-order-utils==0.3.2` for signing and building orders

**Blockchain Network:**
- Polygon RPC - Layer 2 blockchain interactions
  - RPC URL: https://polygon-rpc.com (configurable via `POLYGON_RPC_URL`)
  - Chain ID: 137 (Polygon mainnet)
  - Client: Web3.py integration in `agents/polymarket/polymarket.py`
  - Middleware: Geth PoA middleware for Polygon compatibility
  - Used for: Wallet operations, USDC balance checks, contract interactions

## Data Storage

**Databases:**
- None persistent in production. Code includes SQLAlchemy 2.0.31 (may be used for future features)

**Vector Database:**
- Chroma (chromadb 0.5.5) - Local vector store for RAG
  - Client: `langchain_community.vectorstores.Chroma`
  - Embedding model: OpenAI's `text-embedding-3-small` via `langchain_openai.OpenAIEmbeddings`
  - Storage: Local filesystem directories
    - `local_db_events/` - Event descriptions and metadata
    - `local_db_markets/` - Market descriptions with outcome data
  - Implementation: `agents/connectors/chroma.py` class `PolymarketRAG`
  - Fallback: Temporary directories if primary locations not writable

**File Storage:**
- Local filesystem only - JSON files for markets and events data
  - Market data files: `local_db_markets/markets.json`
  - Event data files: `local_db_events/events.json`
  - Format: JSON with metadata extraction via jq schema

**Caching:**
- None explicit (HNSW index via chroma-hnswlib 0.7.6 acts as vector index cache)

## Authentication & Identity

**Auth Provider:**
- Custom Ethereum-based signing (no centralized auth provider)
  - Implementation: Wallet private key signing via Web3.py and py-order-utils
  - Signature types supported:
    - `0`: Browser/EOA wallet mode (funder defaults to signer)
    - `1`: Email/Magic wallet mode (proxy wallet)
    - `2`: Browser + proxy wallet mode
  - Environment vars:
    - `POLYGON_WALLET_PRIVATE_KEY` - Private key for transaction signing
    - `POLYMARKET_SIGNATURE_TYPE` - Auth strategy (0, 1, or 2)
    - `POLYMARKET_FUNDER_ADDRESS` - Optional proxy wallet address for mode 2

## Smart Contracts & On-Chain

**USDC Token (Polygon):**
- Collateral token address: `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` (wrapped USDC)
- Native USDC address: `0x3c499c542cef5e3811e1192ce70d8cc03d5c3359` (native USDC)
- Environment vars: `POLYGON_COLLATERAL_USDC_ADDRESS`, `POLYGON_NATIVE_USDC_ADDRESS`
- Operations: Balance checks, allowance management, transfers for trades

## Monitoring & Observability

**Error Tracking:**
- None explicit (PostHog for analytics below may capture errors)

**Logs:**
- Console/stdout logging via Python logging module
- Log level configured via `APP_LOG_LEVEL` env var (default: INFO)
- OpenAI request logging: `OPENAI_LOG` env var (default: info)

**Analytics & Events:**
- PostHog 3.5.0 - Product analytics and event tracking
  - Used for: User behavior, agent decision tracking, trade metrics

**Distributed Tracing:**
- OpenTelemetry 0.47b0/1.26.0 - Instrumentation for:
  - FastAPI applications (opentelemetry-instrumentation-fastapi)
  - ASGI middleware (opentelemetry-instrumentation-asgi)
  - gRPC exporters for trace/metric collection
  - OTLP protocol export (protobuf and gRPC)

## CI/CD & Deployment

**Hosting:**
- Docker containers on any Docker-compatible platform (Kubernetes support via k8s client library)
- Dockerfile: Single-stage Python 3.9 image with requirements installation

**CI Pipeline:**
- None detected (no GitHub Actions, GitLab CI, or other CI config in `.github/workflows/` - only CONTRIBUTING.md template)
- Pre-commit hooks configured (`.pre-commit-config.yaml`) for local development checks

## Environment Configuration

**Required env vars (Critical for operation):**
- `OPENAI_API_KEY` - OpenAI API authentication
- `TAVILY_API_KEY` - Tavily search API authentication
- `NEWSAPI_API_KEY` - NewsAPI authentication
- `POLYGON_WALLET_PRIVATE_KEY` - Ethereum wallet for signing transactions
- `POLYGON_RPC_URL` - Polygon network RPC endpoint (default provided)

**Trading Configuration:**
- `EXECUTE_TRADES` (true/false) - Enable/disable actual trade execution
- `TRADE_INCLUDE_NEWS` (true/false) - Include news context in decisions
- `TRADE_EXCLUDE_SPORTS` (true/false) - Filter out sports markets
- `TRADE_MIN_ORDER_AMOUNT_USDC` (float, default 1.0) - Minimum trade amount
- `TRADE_CANDIDATE_COUNT` (int, default 5) - Number of markets to analyze
- `TRADE_TOTAL_BUDGET_FRACTION` (float, default 0.30) - Portfolio fraction to deploy
- `TRADE_MAX/MIN_MARKETS_TO_SCORE` (int) - Market selection limits
- `TRADE_NEWS_LIMIT`, `TRADE_NEWS_DAYS` - News article filtering

**Secrets location:**
- `.env` file at project root (template: `.env.example`)
- WARNING: Never commit `.env` file with real keys; use `.gitignore`
- Loaded via `python-dotenv==1.0.1`

## Webhooks & Callbacks

**Incoming:**
- None detected (no webhook endpoints in codebase for external services)

**Outgoing:**
- None detected (trading operations are one-directional via Polymarket CLOB API)

## Rate Limiting & Quotas

**Polymarket APIs:**
- Gamma API: Concurrent fetch limit via thread pool (GAMMA_MARKET_FETCH_CONCURRENCY)
- CLOB API: No explicit rate limiting detected; uses httpx with standard timeouts

**OpenAI API:**
- Subject to OpenAI rate limits (monthly token limits, TPM limits)
- Configuration: temperature via `OPENAI_TEMPERATURE` env var for cost control

**NewsAPI:**
- Subject to NewsAPI tier limits
- Configuration: Article limits via `TRADE_NEWS_LIMIT` (default 5)

---

*Integration audit: 2026-03-03*
