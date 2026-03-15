<!-- PROJECT SHIELDS -->
[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![MIT License][license-shield]][license-url]


<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="https://github.com/polymarket/agents">
    <img src="docs/images/cli.png" alt="Logo" width="466" height="262">
  </a>

<h3 align="center">Polymarket Agents</h3>

  <p align="center">
    Trade autonomously on Polymarket using AI Agents
    <br />
    <a href="https://github.com/polymarket/agents"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://github.com/polymarket/agents">View Demo</a>
    ·
    <a href="https://github.com/polymarket/agents/issues/new?labels=bug&template=bug-report---.md">Report Bug</a>
    ·
    <a href="https://github.com/polymarket/agents/issues/new?labels=enhancement&template=feature-request---.md">Request Feature</a>
  </p>
</div>


<!-- CONTENT -->
# Polymarket Agents

Polymarket Agents is a developer framework and set of utilities for building AI agents for Polymarket.

This code is free and publicly available under MIT License open source license ([terms of service](#terms-of-service))!

## Features

- Integration with Polymarket API
- AI agent utilities for prediction markets
- Local and remote RAG (Retrieval-Augmented Generation) support
- Data sourcing from betting services, news providers, and web search
- Comphrehensive LLM tools for prompt engineering

# Getting started

This repo is intended for Python 3.9+.

1. Clone the repository

   ```
   git clone https://github.com/{username}/polymarket-agents.git
   cd polymarket-agents
   ```

2. Create a virtual environment

   ```
   python3 -m venv .venv
   ```

3. Activate the virtual environment

   - On Windows:

   ```
   .venv\Scripts\activate
   ```

   - On macOS and Linux:

   ```
   source .venv/bin/activate
   ```

4. Install dependencies

   ```
   pip install -r requirements.txt
   ```

5. Set up environment variables

   ```
   cp .env.example .env
   ```

   Minimum keys to start:
   - `POLYGON_WALLET_PRIVATE_KEY`
   - `OPENAI_API_KEY`
   - `NEWSAPI_API_KEY` (required for news commands/features)

   Current `.env.example` values:

   ```
   POLYGON_WALLET_PRIVATE_KEY=""
   POLYMARKET_SIGNATURE_TYPE="0"
   POLYMARKET_FUNDER_ADDRESS=""
   OPENAI_API_KEY=""
   TAVILY_API_KEY=""
   NEWSAPI_API_KEY=""
   OPENAI_MODEL="gpt-5-mini"
   OPENAI_LOG="info"
   OPENAI_TEMPERATURE=""
   APP_LOG_LEVEL="INFO"
   ALLOW_RESTRICTED_EVENTS="false"
   EXECUTE_TRADES="false"
   POLYGON_RPC_URL="https://polygon-rpc.com"
   POLYGON_COLLATERAL_USDC_ADDRESS="0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
   POLYGON_NATIVE_USDC_ADDRESS="0x3c499c542cef5e3811e1192ce70d8cc03d5c3359"
   USDC_BALANCE_TOKEN_ADDRESSES=""
   TRADE_CANDIDATE_COUNT="5"
   TRADE_DIVERSITY_MODE="soft_quota"
   TRADE_DIVERSITY_MIN_CATEGORIES="3"
   TRADE_MAX_MARKETS_TO_SCORE="20"
   TRADE_TOTAL_BUDGET_FRACTION="0.30"
   TRADE_MAX_PER_MARKET_FRACTION="0.10"
   TRADE_MIN_PER_MARKET_FRACTION="0.02"
   TRADE_CONTINUE_ON_EXECUTION_ERROR="true"
   TRADE_LOG_RATIONALE="true"
   TRADE_INCLUDE_NEWS="false"
   TRADE_NEWS_LIMIT="5"
   TRADE_NEWS_DAYS="7"
   TRADE_NEWS_RELEVANCE="true"
   TRADE_NEWS_CONTEXT_ARTICLE_CAP="3"
   TRADE_EXCLUDE_SPORTS="false"
   TRADE_MIN_ORDER_AMOUNT_USDC="1.0"
   TRADE_MIN_MARKET_VOLUME="10000"
   TRADE_MIN_MARKET_LIQUIDITY="5000"
   TRADE_MIN_ENTRY_PRICE="0.03"
   TRADE_MAX_ENTRY_PRICE="0.97"
   GAMMA_MARKET_FETCH_CONCURRENCY="24"
   GAMMA_HTTP_MAX_CONNECTIONS="100"
   GAMMA_HTTP_MAX_KEEPALIVE_CONNECTIONS="40"
   GAMMA_HTTP_TIMEOUT_SECONDS="8"
   GAMMA_LOG_MARKET_DETAIL_URL="false"
   ```

   `POLYMARKET_SIGNATURE_TYPE` values:
   - `0`: Browser wallet / EOA wallet mode (funder defaults to signer)
   - `1`: Email / Magic wallet mode (proxy wallet)
   - `2`: Browser wallet + proxy wallet mode (set `POLYMARKET_FUNDER_ADDRESS` to your profile wallet)

6. Load your wallet with USDC.

7. Run the CLI

   ```
   PYTHONPATH=. python scripts/python/cli.py --help
   ```

   If `python` is not available in your shell, use `python3`:

   ```
   PYTHONPATH=. python3 scripts/python/cli.py --help
   ```

   Or run the trader module directly:

   ```
   PYTHONPATH=. python agents/application/trade.py
   ```

8. Optional Docker workflow

   ```
   ./scripts/bash/build-docker.sh
   ./scripts/bash/run-docker-dev.sh
   ```

## Architecture

The Polymarket Agents architecture features modular components that can be maintained and extended by individual community members.

### APIs

Polymarket Agents connectors standardize data sources and order types.

- `Chroma.py`: chroma DB for vectorizing news sources and other API data. Developers are able to add their own vector database implementations.

- `Gamma.py`: defines `GammaMarketClient` class, which interfaces with the Polymarket Gamma API to fetch and parse market and event metadata. Methods to retrieve current and tradable markets, as well as defined information on specific markets and events.

- `Polymarket.py`: defines a Polymarket class that interacts with the Polymarket API to retrieve and manage market and event data, and to execute orders on the Polymarket DEX. It includes methods for API key initialization, market and event data retrieval, and trade execution. The file also provides utility functions for building and signing orders, as well as examples for testing API interactions.

- `Objects.py`: data models using Pydantic; representations for trades, markets, events, and related entities.

### Scripts

Files for managing your local environment, server set-up to run the application remotely, and cli for end-user commands.

`cli.py` is the primary user interface for the repo. Users can run commands to query Polymarket data, gather supporting news, run local RAG, ask LLM helpers, and execute autonomous trading workflows.

General command format:

`PYTHONPATH=. python scripts/python/cli.py <command> [options]`

Run `--help` on any command for full usage:

`PYTHONPATH=. python scripts/python/cli.py <command> --help`

#### CLI command reference

- `get-all-markets [--limit 5] [--sort-by spread]`
- `get-all-events [--limit 5] [--sort-by number_of_markets]`
- `get-relevant-news <keywords> [--limit 10] [--days 7] [--relevance|--no-relevance]`
- `create-local-markets-rag <local_directory>`
- `query-local-markets-rag <vector_db_directory> <query>`
- `ask-superforecaster <event_title> <market_question> <outcome>`
- `create-market`
- `ask-llm <user_input>`
- `ask-polymarket-llm <user_input>`
- `diagnose-usdc-balance`
- `run-autonomous-trader [--event-url URL] [--include-news|--no-include-news] [--news-limit 5] [--news-days 7] [--news-relevance|--no-news-relevance] [--exclude-sports|--no-exclude-sports]`
- `analyze-event-url <event_url> [--news-limit 5] [--news-days 7] [--news-relevance|--no-news-relevance] [--exclude-sports|--no-exclude-sports]`
- `run-continuous [--interval 30] [--session-budget 100] [--cooldown 300] [--include-news] [--exclude-sports] [--volatility-threshold 0.05]`
- `run-crypto [--interval 30] [--session-budget 100] [--symbols BTC,ETH,SOL,XRP] [--min-edge 0.05]`
- `run-crypto-arbitrage [--session-budget 50] [--max-per-trade 5] [--min-edge 0.10] [--price-feed-tolerance 0.001]`

#### Trading command examples

`run-autonomous-trader` (full pipeline across filtered events/markets):

```
PYTHONPATH=. python scripts/python/cli.py run-autonomous-trader \
  --include-news \
  --exclude-sports \
  --news-limit 5 \
  --news-days 7 \
  --news-relevance
```

Single-event mode through the same command:

```
PYTHONPATH=. python scripts/python/cli.py run-autonomous-trader \
  --event-url "https://polymarket.com/event/english-premier-league-winner" \
  --exclude-sports \
  --news-limit 5 \
  --news-days 7 \
  --news-relevance
```

`analyze-event-url` (target one Polymarket event):

```
PYTHONPATH=. python scripts/python/cli.py analyze-event-url \
  "https://polymarket.com/event/english-premier-league-winner" \
  --exclude-sports \
  --news-limit 5 \
  --news-days 7 \
  --news-relevance
```

#### Live trading modes

`run-continuous` (high-speed loop across all market categories):

```
PYTHONPATH=. python scripts/python/cli.py run-continuous \
  --interval 30 \
  --session-budget 100 \
  --cooldown 300 \
  --include-news \
  --exclude-sports
```

`run-crypto` (crypto price prediction markets with live WebSocket prices):

```
PYTHONPATH=. python scripts/python/cli.py run-crypto \
  --interval 30 \
  --session-budget 100 \
  --symbols BTC,ETH,SOL \
  --min-edge 0.05
```

`run-crypto-arbitrage` (algorithmic BTC 5-minute markets, no LLM):

```
PYTHONPATH=. python scripts/python/cli.py run-crypto-arbitrage \
  --session-budget 50 \
  --max-per-trade 5 \
  --min-edge 0.10
```

All live trading modes run until the session budget is exhausted or you press Ctrl+C. They respect `EXECUTE_TRADES=false` for dry-run mode.

#### Live-mode and safety flags

- `EXECUTE_TRADES=false` is the default. Set `EXECUTE_TRADES=true` to place live orders.
- `TRADE_MIN_ORDER_AMOUNT_USDC=1.0` skips allocations below this threshold before execution.
- `TRADE_CONTINUE_ON_EXECUTION_ERROR=true` controls whether execution stops on first failed order.
- `TRADE_INCLUDE_NEWS`, `TRADE_NEWS_LIMIT`, `TRADE_NEWS_DAYS`, `TRADE_NEWS_RELEVANCE`, and `TRADE_EXCLUDE_SPORTS` provide environment-level defaults that CLI flags can override.
- `CONTINUOUS_INTERVAL_SECONDS`, `CONTINUOUS_SESSION_BUDGET`, `CONTINUOUS_COOLDOWN_SECONDS`, `CONTINUOUS_VOLATILITY_THRESHOLD` configure continuous mode defaults.
- `CRYPTO_INTERVAL_SECONDS`, `CRYPTO_SESSION_BUDGET`, `CRYPTO_SYMBOLS`, `CRYPTO_MIN_EDGE` configure crypto mode defaults.
- `ARB_SESSION_BUDGET`, `ARB_MAX_PER_TRADE`, `ARB_MIN_EDGE`, `ARB_PRICE_FEED_TOLERANCE` configure BTC arbitrage mode defaults.

# Contributing

If you would like to contribute to this project, please follow these steps:

1. Fork the repository.
2. Create a new branch.
3. Make your changes.
4. Submit a pull request.

Please run pre-commit hooks before making contributions. To initialize them:

   ```
   pre-commit install
   ```

Run all hooks (including the secret scan) before opening a PR:

   ```
   pre-commit run --all-files
   ```

# Related Repos

- [py-clob-client](https://github.com/Polymarket/py-clob-client): Python client for the Polymarket CLOB
- [python-order-utils](https://github.com/Polymarket/python-order-utils): Python utilities to generate and sign orders from Polymarket's CLOB
- [Polymarket CLOB client](https://github.com/Polymarket/clob-client): Typescript client for Polymarket CLOB
- [Langchain](https://github.com/langchain-ai/langchain): Utility for building context-aware reasoning applications
- [Chroma](https://docs.trychroma.com/getting-started): Chroma is an AI-native open-source vector database

# Prediction markets reading

- Prediction Markets: Bottlenecks and the Next Major Unlocks, Mikey 0x: https://mirror.xyz/1kx.eth/jnQhA56Kx9p3RODKiGzqzHGGEODpbskivUUNdd7hwh0
- The promise and challenges of crypto + AI applications, Vitalik Buterin: https://vitalik.eth.limo/general/2024/01/30/cryptoai.html
- Superforecasting: How to Upgrade Your Company's Judgement, Schoemaker and Tetlock: https://hbr.org/2016/05/superforecasting-how-to-upgrade-your-companys-judgment

# License

This project is licensed under the MIT License. See the [LICENSE](https://github.com/Polymarket/agents/blob/main/LICENSE.md) file for details.

# Contact

For any questions or inquiries, please contact liam@polymarket.com or reach out at www.greenestreet.xyz

Enjoy using the CLI application! If you encounter any issues, feel free to open an issue on the repository.

# Terms of Service

[Terms of Service](https://polymarket.com/tos) prohibit US persons and persons from certain other jurisdictions from trading on Polymarket (via UI & API and including agents developed by persons in restricted jurisdictions), although data and information is viewable globally.


<!-- LINKS -->
[contributors-shield]: https://img.shields.io/github/contributors/polymarket/agents?style=for-the-badge
[contributors-url]: https://github.com/polymarket/agents/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/polymarket/agents?style=for-the-badge
[forks-url]: https://github.com/polymarket/agents/network/members
[stars-shield]: https://img.shields.io/github/stars/polymarket/agents?style=for-the-badge
[stars-url]: https://github.com/polymarket/agents/stargazers
[issues-shield]: https://img.shields.io/github/issues/polymarket/agents?style=for-the-badge
[issues-url]: https://github.com/polymarket/agents/issues
[license-shield]: https://img.shields.io/github/license/polymarket/agents?style=for-the-badge
[license-url]: https://github.com/polymarket/agents/blob/master/LICENSE.md
