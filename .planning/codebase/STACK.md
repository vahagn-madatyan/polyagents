# Technology Stack

**Analysis Date:** 2026-03-03

## Languages

**Primary:**
- Python 3.9 - Core application runtime, agents, API integrations, trading logic

**Secondary:**
- Bash - Docker build and container run scripts in `scripts/bash/`

## Runtime

**Environment:**
- Python 3.9 (specified in Dockerfile and README)
- Virtual environment: `.venv/` directory

**Package Manager:**
- pip - Primary dependency management
- Lockfile: `requirements.txt` with pinned versions (no pip-freeze lock file)

## Frameworks

**Core Web:**
- FastAPI 0.111.0 - REST API framework (via `fastapi`, `fastapi-cli`)
- Uvicorn 0.30.3 - ASGI application server

**AI/LLM:**
- LangChain 0.2.11 - Core LLM orchestration framework
- LangChain OpenAI 0.1.19 - OpenAI integration layer
- LangChain Community 0.2.10 - Community integrations (Chroma, document loaders)
- LangChain Core 0.2.26 - Base types and interfaces
- LangGraph 0.1.17 - Graph-based agent state management

**Blockchain/Web3:**
- Web3.py 6.11.0 - Ethereum/Polygon blockchain interactions
- py-clob-client 0.17.5 - Polymarket CLOB (Central Limit Order Book) client
- py-order-utils 0.3.2 - Order signing and building utilities
- eth-account 0.13.1 - Ethereum account management
- eth-keys 0.5.1 - Ethereum key operations
- Pydantic 2.8.2 - Data validation and serialization

**Vector Database:**
- Chroma/chromadb 0.5.5 - Vector database for RAG
- langchain-chroma 0.1.2 - LangChain integration with Chroma
- chroma-hnswlib 0.7.6 - HNSW indexing for vector search

**Testing:**
- pytest 8.3.2 - Test runner and framework
- pytest plugins: pytest-asyncio (not explicitly listed but used for async tests)

**Build/Dev:**
- pre-commit 3.8.0 - Git hooks for linting and formatting (config: `.pre-commit-config.yaml`)

## Key Dependencies

**Critical:**
- OpenAI 1.37.1 - Why it matters: Powers the ChatOpenAI LLM models for autonomous agent decision-making
- LangChain ecosystem (langchain, langchain-core, langchain-openai) - Why it matters: Provides the foundational framework for building AI agents with LLM integration, memory, tools, and chains
- Web3.py 6.11.0 - Why it matters: Enables blockchain interactions with Polygon network for wallet management and transaction signing
- py-clob-client 0.17.5 - Why it matters: Polymarket-specific trading client; essential for market access and order execution

**Infrastructure:**
- httpx 0.27.0 - Async HTTP client for API calls (used in Gamma market client)
- aiohttp 3.10.0 - Async HTTP library for concurrent requests
- asyncio/uvloop 0.19.0 - Async event loop for concurrent operations
- requests 2.32.3 - Synchronous HTTP library for API interactions
- SQLAlchemy 2.0.31 - ORM framework (may be used in future database models)

**Data Processing:**
- Pydantic 2.8.2 - Data validation and parsing
- Pydantic Core 2.20.1 - Core validation engine
- dataclasses-json 0.6.7 - JSON serialization for dataclasses
- jsonschema 4.23.0 - JSON schema validation

**Cryptography:**
- pycryptodome 3.20.0 - Cryptographic primitives (AES, RSA, etc.)
- bcrypt 4.2.0 - Password hashing (authentication utilities)
- eth-hash 0.7.0 - Ethereum hashing functions
- eip712-structs 1.1.0 - EIP-712 signing for Ethereum

**Observability:**
- OpenTelemetry (instrumentation, SDK, exporters) 0.47b0/1.26.0 - Distributed tracing and metrics
- PostHog 3.5.0 - Product analytics and event tracking

**News/Search:**
- newsapi-python 0.2.7 - News aggregation API client
- tavily-python 0.3.5 - Web search API client for research

**Utilities:**
- python-dotenv 1.0.1 - Environment variable loading from `.env` files
- typer 0.12.3 - CLI framework (for CLI interface in `scripts/python/cli.py`)
- Rich 13.7.1 - Terminal formatting and progress bars
- Kubernetes 30.1.0 - Kubernetes API client (for container orchestration)

## Configuration

**Environment:**
- Configuration: Environment variables via `.env` file (use `.env.example` as template)
- Critical configs: API keys (OPENAI_API_KEY, TAVILY_API_KEY, NEWSAPI_API_KEY), wallet credentials (POLYGON_WALLET_PRIVATE_KEY), RPC endpoints
- See `.env.example` for complete list of 42 environment variables

**Build:**
- Dockerfile at root: Single-stage Python 3.9 build
- Docker scripts: `scripts/bash/build-docker.sh`, `scripts/bash/run-docker-dev.sh`
- Pre-commit hooks: `.pre-commit-config.yaml` for code quality checks

## Platform Requirements

**Development:**
- Python 3.9+ with pip
- Virtual environment support
- UNIX-like shell (bash/zsh) for scripts
- Docker (optional, for containerized deployment)

**Production:**
- Deployment target: Docker containers (Polygon network for blockchain interactions)
- Polygon RPC endpoint (default: https://polygon-rpc.com)
- External API access for: OpenAI, NewsAPI, Tavily, Polymarket Gamma API
- Wallet with USDC balance for trading

---

*Stack analysis: 2026-03-03*
