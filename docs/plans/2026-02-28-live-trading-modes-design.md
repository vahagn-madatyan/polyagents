# Live Trading Modes Design

**Date**: 2026-02-28
**Status**: Approved

## Overview

Three new real-time trading modes for the polyagents CLI, all powered by a shared asyncio runtime with persistent WebSocket connections to Polymarket's data feeds.

### Modes

1. **Continuous Mode** (`run-continuous`): High-speed loop (30-60s) trading across all market categories, prioritizing trending/breaking events via volatility detection.
2. **Crypto Mode** (`run-crypto`): Trades crypto price prediction markets (BTC, ETH, SOL, XRP) using real-time WebSocket price feeds + LLM analysis.
3. **BTC 5-Min Arbitrage** (`run-crypto-arbitrage`): Algorithmic trading on BTC 5-minute interval markets using dual price feeds (Binance + Chainlink) and momentum signals. No LLM.

## Architecture: Async Event Loop

```
+-------------------------------------------+
|           AsyncIO Event Loop              |
+----------+----------+--------------------+
| WS: RTDS | WS: CLOB |   Cycle Timer     |
| (prices) | (books)  |   (30-60s)        |
+----------+----------+--------------------+
|        Strategy Layer (per mode)          |
|  continuous | crypto | btc-arbitrage      |
+-------------------------------------------+
|     Shared: LLM, Polymarket API,         |
|     Budget Manager, Trade Executor        |
+-------------------------------------------+
```

Existing sync code (LLM calls, API fetches) is wrapped with `asyncio.to_thread()` to avoid blocking the event loop.

## WebSocket Infrastructure

**New file**: `agents/connectors/websocket.py`

### RTDS Connection (`wss://ws-live-data.polymarket.com`)

- Subscribes to `crypto_prices` (Binance) and `crypto_prices_chainlink` topics
- PING every 5 seconds
- Stores latest prices + rolling history buffer (300 data points, ~5 min at 1/sec)
- Supports event callbacks (e.g., fire when price crosses threshold)

### Market Channel (`wss://ws-subscriptions-clob.polymarket.com/ws/market`)

- Subscribes to specific token IDs for orderbook snapshots + price deltas
- PING every 10 seconds
- Maintains live orderbook state per subscribed market
- Dynamic subscribe/unsubscribe as markets are discovered

### WebSocketManager API

```python
class PriceTick(NamedTuple):
    timestamp: float
    price: float

class WebSocketManager:
    prices: dict[str, float]                    # Latest prices {"btcusdt": 97500.0}
    price_history: dict[str, deque[PriceTick]]  # Rolling buffer per symbol
    orderbooks: dict[str, dict]                 # {token_id: {"bids": [...], "asks": [...]}}
    _callbacks: list[tuple[Callable, Callable]]  # (condition_fn, callback)

    async def start()                           # Connect both WebSockets
    async def stop()                            # Clean disconnect
    async def connect_rtds()
    async def connect_market(token_ids: list[str])
    async def subscribe(token_ids: list[str])
    async def unsubscribe(token_ids: list[str])
    def on_price_event(condition_fn, callback)   # Register callback
    def get_price(symbol: str) -> float
    def get_momentum(symbol: str, window_secs: int) -> float  # % change over window
    def get_price_history(symbol: str, n: int) -> list[PriceTick]
    def get_orderbook(token_id: str) -> dict
```

### Reconnection

Auto-reconnect with exponential backoff (1s, 2s, 4s, max 30s). Log disconnects but don't crash the trading loop.

## Mode 1: Continuous (`run-continuous`)

**File**: `agents/application/continuous.py`

### Flow per cycle (30-60s)

1. Fetch tradeable events (cached, refreshed every 5 cycles)
2. **Volatility filter**: Prioritize markets with unusual WebSocket price movement (>threshold % swing in last N minutes)
3. RAG filter for high-potential markets (existing logic)
4. Get fresh orderbook prices from WebSocket (not REST)
5. Lightweight LLM superforecaster on top candidates
6. Execute trades within session budget
7. Record trades, apply cooldown to traded markets

### Differences from `one_best_trade`

- **Session budget manager**: Tracks total spent, stops at cap
- **Market dedup/cooldown**: Don't re-analyze recently traded markets
- **Cached events**: Refresh every ~5 minutes, not every cycle
- **WebSocket prices**: Live orderbook data, not fetched per-cycle
- **Volatility prioritization**: Breaking events surface faster
- **Graceful shutdown**: Ctrl+C closes WebSockets, logs session summary

### CLI

```
run-continuous --interval 30 --session-budget 100 --cooldown 300 \
               --include-news --exclude-sports --volatility-threshold 0.05
```

## Mode 2: Crypto (`run-crypto`)

**File**: `agents/application/crypto.py`

### Market Discovery

- Filter Polymarket events/markets for crypto price markets only
- Match symbols: BTC, ETH, SOL, XRP (configurable)
- Pattern match titles: "Will BTC be above $X by Y?"

### Decision Engine per cycle

1. Get real-time price from RTDS WebSocket
2. Compare to market target price
3. Calculate distance to target as % of current price
4. Factor in momentum (1-min, 5-min, 15-min from history buffer)
5. LLM call: given current price, momentum, time remaining, market odds — is market mispriced?
6. Trade if LLM identifies edge > threshold

### Features

- Live price overlay: each market shows current price vs. target
- Time decay awareness: tighter edge for near-expiry markets
- Multi-timeframe momentum signals

### CLI

```
run-crypto --interval 30 --session-budget 100 --symbols BTC,ETH,SOL --min-edge 0.05
```

## Mode 3: BTC 5-Min Arbitrage (`run-crypto-arbitrage`)

**File**: `agents/application/btc_arbitrage.py`

### Market Discovery

- Scan for active BTC markets with <=5 minute resolution
- Pattern match: "5 minutes", "5-minute", time-stamped titles
- Re-scan periodically as new markets open

### Decision Engine (pure algorithmic, no LLM)

1. Get real-time BTC price from BOTH Binance and Chainlink feeds
2. **Dual feed validation**: Only proceed if feeds agree within 0.1% tolerance
3. Get market target price and expiry time
4. Calculate:
   - **Distance**: `(current_price - target) / target`
   - **Momentum**: 1-min and 5-min price change from history
   - **Time remaining**: Seconds until expiry
   - **Market odds**: Yes/No prices from Market Channel WebSocket
5. **Signal**:
   - BTC comfortably above target + momentum flat/up → bet YES if odds offer value
   - BTC below target + momentum down → bet NO if odds offer value
   - Require: `|implied_prob - model_prob| > min_edge`
6. Execute trade

### Risk Controls

- Max bet per market: Small fixed amount ($2-5 default)
- Session budget cap
- Cooldown: Don't re-bet on same 5-min market
- Skip if momentum is ambiguous or price too close to target

### CLI

```
run-crypto-arbitrage --session-budget 50 --max-per-trade 5 --min-edge 0.10
```

## Shared Infrastructure

### Session Budget Manager

**File**: `agents/application/budget.py`

```python
class SessionBudgetManager:
    total_budget: float          # Session cap (USDC)
    spent: float                 # Running total
    trades: list[TradeRecord]    # Audit trail

    def can_spend(amount: float) -> bool
    def record_trade(amount: float, market_id: int, outcome: str)
    def remaining() -> float
    def summary() -> str         # End-of-session report
```

### Market Discovery

**File**: `agents/application/market_filter.py`

- Shared logic for discovering crypto price markets and 5-min interval markets
- Pattern matching on titles/descriptions
- Caching layer with configurable refresh interval

### Async Runner

**File**: `agents/application/runner.py`

- Main asyncio entry point called by each CLI command
- Manages WebSocket lifecycle
- Graceful shutdown on SIGINT/SIGTERM
- Session logging and summary on exit

## Configuration

New `.env` variables:

```
# Continuous mode
CONTINUOUS_INTERVAL_SECONDS="30"
CONTINUOUS_SESSION_BUDGET="100"
CONTINUOUS_COOLDOWN_SECONDS="300"
CONTINUOUS_VOLATILITY_THRESHOLD="0.05"

# Crypto mode
CRYPTO_INTERVAL_SECONDS="30"
CRYPTO_SESSION_BUDGET="100"
CRYPTO_SYMBOLS="BTC,ETH,SOL,XRP"
CRYPTO_MIN_EDGE="0.05"

# BTC arbitrage
ARB_SESSION_BUDGET="50"
ARB_MAX_PER_TRADE="5"
ARB_MIN_EDGE="0.10"
ARB_PRICE_FEED_TOLERANCE="0.001"
```

## File Structure

```
agents/
  application/
    trade.py              # Existing (untouched)
    continuous.py          # NEW: Continuous mode strategy
    crypto.py              # NEW: Crypto mode strategy
    btc_arbitrage.py       # NEW: BTC 5-min arbitrage strategy
    budget.py              # NEW: Session budget manager
    runner.py              # NEW: Async runner + lifecycle
    market_filter.py       # NEW: Crypto/5-min market discovery
  connectors/
    websocket.py           # NEW: WebSocket manager
scripts/python/
    cli.py                 # MODIFIED: Add 3 new commands
```

## New Dependency

- `websockets` — async-native Python WebSocket library

## Python Performance Notes

- 30-60s intervals are well within Python async capabilities
- LLM calls (~5-10s each) are the real bottleneck, not Python
- BTC arbitrage mode avoids LLM entirely for speed
- `asyncio.to_thread()` wraps existing sync code without rewriting
- WebSocket keepalive tasks run concurrently without blocking trading logic
