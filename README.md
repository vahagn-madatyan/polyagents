# predikt

Autonomous AI trading agent for [Polymarket](https://polymarket.com) prediction markets. Trade sports, crypto, news, and general markets — autonomously or with a single command.

---

## Install

```bash
pip install predikt
```

## Quick Start

1. **Set up your keys** — create a `.env` file:

   ```env
   POLYGON_WALLET_PRIVATE_KEY=<your-polygon-private-key>
   POLYMARKET_FUNDER_ADDRESS=<your-funder-address>
   OPENAI_API_KEY=<your-openai-key>
   ```

   Optional for extended features:
   ```env
   NEWSAPI_API_KEY=<your-newsapi-key>        # news-enriched analysis
   TAVILY_API_KEY=<your-tavily-key>          # web search context
   SPORTS_DATA_API_KEY=<your-sportsdata-key> # live sports stats
   SPORTS_ODDS_API_KEY=<your-odds-key>       # live odds feeds
   ```

2. **Run it:**

   ```bash
   predikt run-autonomous-trader
   ```

   That's it. The agent scans Polymarket events, runs LLM-powered superforecaster analysis, and executes trades when it finds mispriced markets.

---

## Pipelines

predikt ships with five autonomous trading pipelines:

| Pipeline | Command | What it does |
|----------|---------|-------------|
| **General** | `predikt run-autonomous-trader` | Scans all Polymarket events, filters candidates via RAG, runs two-stage LLM analysis, executes best trades |
| **Continuous** | `predikt run-continuous` | High-speed loop — trades trending/breaking events every N seconds |
| **Sports** | `predikt-sports` | Live sports trading via WebSocket — pre-game positioning + in-game score-change reactions |
| **Crypto** | `predikt run-crypto` | Real-time crypto price feeds + LLM analysis for BTC/ETH/SOL/XRP markets |
| **BTC Arbitrage** | `predikt run-crypto-arbitrage` | Pure algorithmic — no LLM. Dual Binance + Chainlink price feeds, 15-second intervals |

---

## CLI Reference

### Autonomous Trading

```bash
# Default: scan all markets, pick the best trade
predikt run-autonomous-trader

# Scope to a single event
predikt run-autonomous-trader --event-url "https://polymarket.com/event/..."

# Include news context in analysis
predikt run-autonomous-trader --include-news --news-limit 10 --news-days 3

# Exclude sports markets
predikt run-autonomous-trader --exclude-sports
```

### Analyze a Specific Event

```bash
# Run prediction pipeline without executing (respects EXECUTE_TRADES env var)
predikt analyze-event-url "https://polymarket.com/event/..."

# With news enrichment
predikt analyze-event-url "https://polymarket.com/event/..." --news-limit 10
```

### Continuous Trading

```bash
# Trade every 30 seconds, $100 session budget
predikt run-continuous

# Custom interval and budget
predikt run-continuous --interval 60 --session-budget 250

# With cooldown between trades on the same market
predikt run-continuous --cooldown 600 --volatility-threshold 0.08
```

### Sports Trading

```bash
# Start the live sports pipeline
predikt-sports

# Connects to Polymarket sports WebSocket, streams live game state,
# executes pre-game + in-game trades autonomously.
```

Sports pipeline features:
- **Pre-game**: Two-stage LLM analysis (blind probability → market-aware value detection)
- **In-game**: Fast-path (cached probability, no LLM) and slow-path (full re-analysis) on score changes
- **All sports**: NFL, NBA, MLB, NHL, CFB, CBB, soccer, esports, tennis
- **Budget coordination**: Cross-process filelock with configurable per-sport caps

Key environment variables:
```env
SPORTS_BUDGET_FRACTION="0.30"         # fraction of wallet for sports
SPORTS_EXECUTE_TRADES="false"         # sports-specific trade toggle
SPORTS_CAP_NFL="0.4"                  # per-sport budget caps
SPORTS_CAP_NBA="0.3"
SPORTS_CAP_MLB="0.15"
SPORTS_CAP_NHL="0.15"
SPORTS_INGAME_COOLDOWN_SECONDS="30"   # per-game cooldown
SPORTS_MAX_GAME_EXPOSURE_USD="50.0"   # max USD per game
```

### Crypto Trading

```bash
# Trade crypto price markets with live WebSocket feeds
predikt run-crypto

# Custom symbols and edge threshold
predikt run-crypto --symbols "BTC,ETH,SOL" --min-edge 0.08 --session-budget 200

# BTC 5-minute interval arbitrage (no LLM, pure price momentum)
predikt run-crypto-arbitrage --session-budget 50 --min-edge 0.10
```

### Market Exploration

```bash
# Browse markets sorted by spread
predikt get-all-markets --limit 10 --sort-by spread

# Browse events sorted by number of markets
predikt get-all-events --limit 10

# Search news for market context
predikt get-relevant-news "bitcoin ETF" --limit 5 --days 3

# Check wallet and USDC balance
predikt diagnose-usdc-balance
```

### LLM & Forecasting

```bash
# Ask the superforecaster about a specific market
predikt ask-superforecaster "US Election" "Will Biden win?" "yes"

# General LLM query
predikt ask-llm "What factors affect prediction market liquidity?"

# LLM query with live Polymarket context
predikt ask-polymarket-llm "What are the best crypto markets to trade right now?"
```

### RAG (Local Market Database)

```bash
# Build a local vector database of Polymarket events
predikt create-local-markets-rag ./local_db_events

# Query the local database
predikt query-local-markets-rag ./local_db_events "upcoming elections"
```

---

## Configuration

All configuration is via environment variables. Create a `.env` file in the project root — predikt loads it automatically.

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `POLYGON_WALLET_PRIVATE_KEY` | — | Your Polygon wallet private key |
| `POLYMARKET_FUNDER_ADDRESS` | — | Polymarket funder address |
| `OPENAI_API_KEY` | — | OpenAI API key for LLM analysis |
| `OPENAI_MODEL` | `gpt-5-mini` | Model to use for analysis |
| `EXECUTE_TRADES` | `false` | Master trade execution toggle — set `true` for live trading |
| `APP_LOG_LEVEL` | `INFO` | Logging verbosity |

### Trade Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `TRADE_TOTAL_BUDGET_FRACTION` | `0.30` | Fraction of wallet to use per session |
| `TRADE_MAX_PER_MARKET_FRACTION` | `0.10` | Max fraction per single market |
| `TRADE_CANDIDATE_COUNT` | `5` | Number of candidates to evaluate |
| `TRADE_DIVERSITY_MODE` | `soft_quota` | Diversification strategy |
| `TRADE_MIN_MARKET_VOLUME` | `10000` | Minimum market volume filter |
| `TRADE_MIN_MARKET_LIQUIDITY` | `5000` | Minimum market liquidity filter |

### Continuous Mode

| Variable | Default | Description |
|----------|---------|-------------|
| `CONTINUOUS_INTERVAL_SECONDS` | `30` | Seconds between trade cycles |
| `CONTINUOUS_SESSION_BUDGET` | `100` | Session budget in USDC |
| `CONTINUOUS_COOLDOWN_SECONDS` | `300` | Per-market cooldown |
| `CONTINUOUS_VOLATILITY_THRESHOLD` | `0.05` | Minimum volatility to trade |

### Crypto Mode

| Variable | Default | Description |
|----------|---------|-------------|
| `CRYPTO_SYMBOLS` | `BTC,ETH,SOL,XRP` | Symbols to trade |
| `CRYPTO_MIN_EDGE` | `0.05` | Minimum edge to execute |
| `ARB_MIN_EDGE` | `0.10` | Minimum edge for BTC arbitrage |
| `ARB_PRICE_FEED_TOLERANCE` | `0.001` | Cross-feed price tolerance |

See `.env.example` for the full list of 60+ configuration variables.

---

## Architecture

```
predikt
├── agents/
│   ├── application/          # trading pipelines and strategies
│   │   ├── trade.py          # general autonomous trader
│   │   ├── continuous.py     # high-speed continuous loop
│   │   ├── crypto.py         # crypto price market strategy
│   │   ├── btc_arbitrage.py  # pure algorithmic BTC arb
│   │   ├── sports_trader.py  # pre-game sports trading
│   │   ├── ingame_trader.py  # live in-game trading engine
│   │   ├── executor.py       # two-stage LLM analysis engine
│   │   ├── budget.py         # cross-process budget coordinator
│   │   └── ...
│   ├── connectors/           # external data sources
│   │   ├── sports_ws.py      # Polymarket sports WebSocket
│   │   ├── sports_data.py    # external sports stats API
│   │   ├── chroma.py         # ChromaDB RAG connector
│   │   ├── news.py           # NewsAPI connector
│   │   └── ...
│   ├── polymarket/           # Polymarket API clients
│   │   ├── polymarket.py     # CLOB order execution
│   │   └── gamma.py          # Gamma API market discovery
│   ├── utils/
│   └── sports.py             # sports pipeline entry point
└── scripts/
    └── python/
        └── cli.py            # CLI entry point (typer)
```

### How It Works

1. **Discovery** — Scans Polymarket events via Gamma API, filters by category, volume, liquidity
2. **Context** — Enriches candidates with news (NewsAPI), web search (Tavily), and RAG (ChromaDB)
3. **Analysis** — Two-stage LLM superforecaster: blind probability estimate → market-aware value detection
4. **Execution** — Places orders via Polymarket CLOB API with confidence-weighted budget allocation
5. **Coordination** — Cross-process budget management with filelock for multi-pipeline operation

---

## Safety

- **Dry-run by default** — `EXECUTE_TRADES=false` out of the box. No trades execute until you explicitly enable it.
- **Paper mode first** — Test with small budgets before going live.
- **Budget caps** — Per-market, per-sport, and per-session limits prevent runaway spending.
- **Cross-process safety** — Filelock-based budget coordination when running multiple pipelines.
- **Minimum order guards** — Configurable floor on order size and market quality filters.

---

## Build from Source

```bash
git clone https://github.com/vahagn-madatyan/predikt.git
cd predikt
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run tests:

```bash
pytest tests/ -q
```

---

## Attribution

This project was forked from Polymarket's [agents](https://github.com/polymarket/agents) repository, extended with autonomous sports, crypto, and continuous trading pipelines.

---

## Disclaimer

This software is for educational and research purposes. Trading on prediction markets involves risk — you can lose money. No trading system is guaranteed to be profitable. Always start with paper/dry-run mode. The authors are not responsible for any financial losses incurred through use of this software.

This code is free and publicly available under the [MIT License](LICENSE.md).
