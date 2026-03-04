# Live Trading Modes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add three new CLI commands (`run-continuous`, `run-crypto`, `run-crypto-arbitrage`) with shared async WebSocket infrastructure, session budget tracking, and market discovery for real-time Polymarket trading.

**Architecture:** Async event loop with persistent WebSocket connections to Polymarket RTDS (crypto prices) and Market Channel (orderbooks). Each trading mode is a strategy that subscribes to the data it needs. Existing sync code (LLM, API) wrapped with `asyncio.to_thread()`.

**Tech Stack:** Python asyncio, `websockets` (already in requirements.txt), existing `py-clob-client`/`langchain`/`httpx` stack. pytest + pytest-asyncio for testing.

**Design doc:** `docs/plans/2026-02-28-live-trading-modes-design.md`

---

### Task 1: Test Infrastructure + pytest-asyncio

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `pyproject.toml` (pytest config section only)

**Step 1: Install pytest-asyncio**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && pip install pytest-asyncio && pip freeze | grep pytest-asyncio >> requirements.txt`

**Step 2: Create test infrastructure**

Create `tests/__init__.py` (empty file).

Create `tests/conftest.py`:

```python
import asyncio

import pytest


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
```

Create `pyproject.toml` with pytest config:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

**Step 3: Verify test infrastructure works**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python -m pytest tests/ -v --co`
Expected: No errors, test collection succeeds (0 tests collected is fine)

**Step 4: Commit**

```bash
git add tests/__init__.py tests/conftest.py pyproject.toml requirements.txt
git commit -m "feat: add test infrastructure with pytest-asyncio"
```

---

### Task 2: Session Budget Manager

**Files:**
- Create: `agents/application/budget.py`
- Create: `tests/test_budget.py`

**Step 1: Write the failing tests**

Create `tests/test_budget.py`:

```python
import time

from agents.application.budget import SessionBudgetManager, TradeRecord


class TestSessionBudgetManager:
    def test_initial_state(self):
        mgr = SessionBudgetManager(total_budget=100.0)
        assert mgr.total_budget == 100.0
        assert mgr.spent == 0.0
        assert mgr.remaining() == 100.0
        assert mgr.trades == []

    def test_can_spend_within_budget(self):
        mgr = SessionBudgetManager(total_budget=100.0)
        assert mgr.can_spend(50.0) is True
        assert mgr.can_spend(100.0) is True
        assert mgr.can_spend(100.01) is False

    def test_record_trade_updates_spent(self):
        mgr = SessionBudgetManager(total_budget=100.0)
        mgr.record_trade(amount=25.0, market_id=123, outcome="Yes")
        assert mgr.spent == 25.0
        assert mgr.remaining() == 75.0
        assert len(mgr.trades) == 1
        assert mgr.trades[0].amount == 25.0
        assert mgr.trades[0].market_id == 123

    def test_can_spend_after_spending(self):
        mgr = SessionBudgetManager(total_budget=100.0)
        mgr.record_trade(amount=90.0, market_id=1, outcome="Yes")
        assert mgr.can_spend(10.0) is True
        assert mgr.can_spend(10.01) is False

    def test_budget_exhausted(self):
        mgr = SessionBudgetManager(total_budget=50.0)
        mgr.record_trade(amount=50.0, market_id=1, outcome="Yes")
        assert mgr.remaining() == 0.0
        assert mgr.can_spend(0.01) is False
        assert mgr.is_exhausted() is True

    def test_summary_output(self):
        mgr = SessionBudgetManager(total_budget=100.0)
        mgr.record_trade(amount=25.0, market_id=1, outcome="Yes")
        mgr.record_trade(amount=10.0, market_id=2, outcome="No")
        summary = mgr.summary()
        assert "100.00" in summary
        assert "35.00" in summary
        assert "65.00" in summary
        assert "2 trades" in summary

    def test_cooldown_tracking(self):
        mgr = SessionBudgetManager(total_budget=100.0)
        mgr.record_trade(amount=10.0, market_id=42, outcome="Yes")
        assert mgr.is_on_cooldown(42, cooldown_seconds=300) is True
        assert mgr.is_on_cooldown(99, cooldown_seconds=300) is False

    def test_zero_budget(self):
        mgr = SessionBudgetManager(total_budget=0.0)
        assert mgr.is_exhausted() is True
        assert mgr.can_spend(0.01) is False
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python -m pytest tests/test_budget.py -v`
Expected: FAIL with ImportError (module not found)

**Step 3: Write minimal implementation**

Create `agents/application/budget.py`:

```python
import time
from dataclasses import dataclass, field


@dataclass
class TradeRecord:
    amount: float
    market_id: int
    outcome: str
    timestamp: float = field(default_factory=time.time)


class SessionBudgetManager:
    def __init__(self, total_budget: float) -> None:
        self.total_budget = max(0.0, float(total_budget))
        self.spent = 0.0
        self.trades: list[TradeRecord] = []

    def remaining(self) -> float:
        return max(0.0, self.total_budget - self.spent)

    def can_spend(self, amount: float) -> bool:
        return float(amount) <= self.remaining()

    def is_exhausted(self) -> bool:
        return self.remaining() <= 0.0

    def record_trade(self, amount: float, market_id: int, outcome: str) -> None:
        record = TradeRecord(amount=float(amount), market_id=market_id, outcome=outcome)
        self.trades.append(record)
        self.spent += record.amount

    def is_on_cooldown(self, market_id: int, cooldown_seconds: float) -> bool:
        now = time.time()
        for trade in reversed(self.trades):
            if trade.market_id == market_id:
                return (now - trade.timestamp) < cooldown_seconds
        return False

    def summary(self) -> str:
        return (
            f"Session budget: ${self.total_budget:.2f} | "
            f"Spent: ${self.spent:.2f} | "
            f"Remaining: ${self.remaining():.2f} | "
            f"{len(self.trades)} trades"
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python -m pytest tests/test_budget.py -v`
Expected: All 8 tests PASS

**Step 5: Commit**

```bash
git add agents/application/budget.py tests/test_budget.py
git commit -m "feat: add session budget manager with cooldown tracking"
```

---

### Task 3: WebSocket Manager

**Files:**
- Create: `agents/connectors/websocket.py`
- Create: `tests/test_websocket.py`

**Step 1: Write the failing tests**

Create `tests/test_websocket.py`:

```python
import asyncio
import json
import time

import pytest

from agents.connectors.websocket import PriceTick, WebSocketManager


class TestPriceTick:
    def test_creation(self):
        tick = PriceTick(timestamp=1000.0, price=97500.0)
        assert tick.timestamp == 1000.0
        assert tick.price == 97500.0


class TestWebSocketManagerOffline:
    """Tests that don't require live WebSocket connections."""

    def test_initial_state(self):
        mgr = WebSocketManager()
        assert mgr.prices == {}
        assert mgr.orderbooks == {}

    def test_get_price_missing(self):
        mgr = WebSocketManager()
        assert mgr.get_price("btcusdt") is None

    def test_get_price_exists(self):
        mgr = WebSocketManager()
        mgr.prices["btcusdt"] = 97500.0
        assert mgr.get_price("btcusdt") == 97500.0

    def test_get_orderbook_missing(self):
        mgr = WebSocketManager()
        assert mgr.get_orderbook("token123") is None

    def test_get_orderbook_exists(self):
        mgr = WebSocketManager()
        book = {"bids": [{"price": "0.48", "size": "30"}], "asks": [{"price": "0.52", "size": "25"}]}
        mgr.orderbooks["token123"] = book
        assert mgr.get_orderbook("token123") == book

    def test_price_history_buffer(self):
        mgr = WebSocketManager(history_size=5)
        for i in range(7):
            mgr._record_price("btcusdt", float(97000 + i), timestamp=float(1000 + i))
        history = mgr.get_price_history("btcusdt", n=10)
        assert len(history) == 5  # capped at history_size
        assert history[-1].price == 97006.0  # latest

    def test_get_momentum_insufficient_data(self):
        mgr = WebSocketManager()
        assert mgr.get_momentum("btcusdt", window_secs=60) == 0.0

    def test_get_momentum_calculation(self):
        mgr = WebSocketManager(history_size=300)
        now = time.time()
        mgr._record_price("btcusdt", 100.0, timestamp=now - 30)
        mgr._record_price("btcusdt", 110.0, timestamp=now)
        momentum = mgr.get_momentum("btcusdt", window_secs=60)
        assert abs(momentum - 0.10) < 0.001  # 10% increase

    def test_callback_registration_and_check(self):
        mgr = WebSocketManager()
        triggered = []
        mgr.on_price_event(
            condition_fn=lambda sym, price: price > 100000,
            callback=lambda sym, price: triggered.append((sym, price)),
        )
        mgr._record_price("btcusdt", 99000.0)
        assert len(triggered) == 0
        mgr._record_price("btcusdt", 101000.0)
        assert len(triggered) == 1
        assert triggered[0] == ("btcusdt", 101000.0)

    def test_handle_rtds_price_message(self):
        mgr = WebSocketManager()
        msg = json.dumps({
            "topic": "crypto_prices",
            "type": "crypto_prices",
            "timestamp": 1000,
            "payload": {"symbol": "btcusdt", "timestamp": 1000, "value": 97500.0},
        })
        mgr._handle_rtds_message(msg)
        assert mgr.get_price("btcusdt") == 97500.0

    def test_handle_rtds_chainlink_message(self):
        mgr = WebSocketManager()
        msg = json.dumps({
            "topic": "crypto_prices_chainlink",
            "type": "crypto_prices_chainlink",
            "timestamp": 1000,
            "payload": {"symbol": "btc/usd", "timestamp": 1000, "value": 97450.0},
        })
        mgr._handle_rtds_message(msg)
        assert mgr.get_price("btc/usd") == 97450.0

    def test_handle_market_book_message(self):
        mgr = WebSocketManager()
        msg = json.dumps({
            "event_type": "book",
            "asset_id": "token_abc",
            "market": "cond_123",
            "bids": [{"price": "0.48", "size": "30"}],
            "asks": [{"price": "0.52", "size": "25"}],
            "timestamp": "1000",
        })
        mgr._handle_market_message(msg)
        book = mgr.get_orderbook("token_abc")
        assert book is not None
        assert book["bids"] == [{"price": "0.48", "size": "30"}]

    def test_handle_market_price_change(self):
        mgr = WebSocketManager()
        mgr.orderbooks["token_abc"] = {
            "bids": [{"price": "0.48", "size": "30"}],
            "asks": [{"price": "0.52", "size": "25"}],
        }
        msg = json.dumps({
            "event_type": "price_change",
            "market": "cond_123",
            "price_changes": [{
                "asset_id": "token_abc",
                "price": "0.50",
                "size": "200",
                "side": "BUY",
                "best_bid": "0.50",
                "best_ask": "0.52",
            }],
            "timestamp": "1001",
        })
        mgr._handle_market_message(msg)
        book = mgr.get_orderbook("token_abc")
        assert book["best_bid"] == "0.50"

    def test_dual_feed_validation(self):
        mgr = WebSocketManager()
        mgr.prices["btcusdt"] = 97500.0
        mgr.prices["btc/usd"] = 97400.0
        valid, avg = mgr.validate_dual_feed("btcusdt", "btc/usd", tolerance=0.001)
        assert valid is True
        assert abs(avg - 97450.0) < 0.1

    def test_dual_feed_validation_diverged(self):
        mgr = WebSocketManager()
        mgr.prices["btcusdt"] = 97500.0
        mgr.prices["btc/usd"] = 90000.0
        valid, avg = mgr.validate_dual_feed("btcusdt", "btc/usd", tolerance=0.001)
        assert valid is False

    def test_dual_feed_validation_missing(self):
        mgr = WebSocketManager()
        mgr.prices["btcusdt"] = 97500.0
        valid, avg = mgr.validate_dual_feed("btcusdt", "btc/usd", tolerance=0.001)
        assert valid is False
        assert avg == 0.0
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python -m pytest tests/test_websocket.py -v`
Expected: FAIL with ImportError

**Step 3: Write implementation**

Create `agents/connectors/websocket.py`:

```python
import asyncio
import json
import logging
import time
from collections import deque
from typing import Any, Callable, NamedTuple, Optional

import websockets

logger = logging.getLogger(__name__)

RTDS_URL = "wss://ws-live-data.polymarket.com"
MARKET_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

RTDS_PING_INTERVAL = 5
MARKET_PING_INTERVAL = 10
RECONNECT_BASE_DELAY = 1.0
RECONNECT_MAX_DELAY = 30.0


class PriceTick(NamedTuple):
    timestamp: float
    price: float


class WebSocketManager:
    def __init__(self, history_size: int = 300) -> None:
        self.prices: dict[str, float] = {}
        self.price_history: dict[str, deque[PriceTick]] = {}
        self.orderbooks: dict[str, dict[str, Any]] = {}
        self._callbacks: list[tuple[Callable, Callable]] = []
        self._history_size = history_size
        self._rtds_ws: Optional[Any] = None
        self._market_ws: Optional[Any] = None
        self._running = False
        self._tasks: list[asyncio.Task] = []

    def get_price(self, symbol: str) -> Optional[float]:
        return self.prices.get(symbol)

    def get_orderbook(self, token_id: str) -> Optional[dict]:
        return self.orderbooks.get(token_id)

    def get_price_history(self, symbol: str, n: int) -> list[PriceTick]:
        history = self.price_history.get(symbol)
        if not history:
            return []
        return list(history)[-n:]

    def get_momentum(self, symbol: str, window_secs: int) -> float:
        history = self.price_history.get(symbol)
        if not history or len(history) < 2:
            return 0.0
        now = time.time()
        cutoff = now - window_secs
        old_price = None
        for tick in history:
            if tick.timestamp >= cutoff:
                old_price = tick.price
                break
        if old_price is None or old_price == 0:
            return 0.0
        latest_price = history[-1].price
        return (latest_price - old_price) / old_price

    def on_price_event(self, condition_fn: Callable, callback: Callable) -> None:
        self._callbacks.append((condition_fn, callback))

    def validate_dual_feed(
        self, binance_key: str, chainlink_key: str, tolerance: float
    ) -> tuple[bool, float]:
        price_a = self.prices.get(binance_key)
        price_b = self.prices.get(chainlink_key)
        if price_a is None or price_b is None:
            return False, 0.0
        avg = (price_a + price_b) / 2.0
        if avg == 0:
            return False, 0.0
        divergence = abs(price_a - price_b) / avg
        return divergence <= tolerance, avg

    def _record_price(
        self, symbol: str, price: float, timestamp: Optional[float] = None
    ) -> None:
        ts = timestamp if timestamp is not None else time.time()
        self.prices[symbol] = price
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=self._history_size)
        self.price_history[symbol].append(PriceTick(timestamp=ts, price=price))
        for condition_fn, callback in self._callbacks:
            try:
                if condition_fn(symbol, price):
                    callback(symbol, price)
            except Exception as err:
                logger.warning("[ws] callback_error symbol=%s error=%s", symbol, err)

    def _handle_rtds_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        topic = data.get("topic", "")
        payload = data.get("payload", {})
        if not isinstance(payload, dict):
            return
        symbol = payload.get("symbol", "")
        value = payload.get("value")
        if symbol and value is not None:
            try:
                self._record_price(symbol, float(value))
            except (TypeError, ValueError):
                pass

    def _handle_market_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        event_type = data.get("event_type", "")
        if event_type == "book":
            asset_id = data.get("asset_id", "")
            if asset_id:
                self.orderbooks[asset_id] = {
                    "bids": data.get("bids", []),
                    "asks": data.get("asks", []),
                    "timestamp": data.get("timestamp"),
                }
        elif event_type == "price_change":
            for change in data.get("price_changes", []):
                asset_id = change.get("asset_id", "")
                if asset_id and asset_id in self.orderbooks:
                    self.orderbooks[asset_id]["best_bid"] = change.get("best_bid")
                    self.orderbooks[asset_id]["best_ask"] = change.get("best_ask")
                    self.orderbooks[asset_id]["timestamp"] = data.get("timestamp")
        elif event_type == "last_trade_price":
            asset_id = data.get("asset_id", "")
            if asset_id and asset_id in self.orderbooks:
                self.orderbooks[asset_id]["last_trade_price"] = data.get("price")
                self.orderbooks[asset_id]["last_trade_side"] = data.get("side")

    async def _rtds_loop(self) -> None:
        delay = RECONNECT_BASE_DELAY
        while self._running:
            try:
                async with websockets.connect(RTDS_URL) as ws:
                    self._rtds_ws = ws
                    delay = RECONNECT_BASE_DELAY
                    logger.info("[ws] rtds connected")
                    subscribe_msg = json.dumps({
                        "action": "subscribe",
                        "subscriptions": [
                            {"topic": "crypto_prices", "type": "crypto_prices"},
                            {"topic": "crypto_prices_chainlink", "type": "crypto_prices_chainlink"},
                        ],
                    })
                    await ws.send(subscribe_msg)
                    ping_task = asyncio.create_task(self._ping_loop(ws, RTDS_PING_INTERVAL))
                    try:
                        async for message in ws:
                            if message == "PONG":
                                continue
                            self._handle_rtds_message(str(message))
                    finally:
                        ping_task.cancel()
            except Exception as err:
                logger.warning("[ws] rtds disconnected error=%s reconnecting in %.1fs", err, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)

    async def _market_loop(self, token_ids: list[str]) -> None:
        delay = RECONNECT_BASE_DELAY
        while self._running:
            try:
                async with websockets.connect(MARKET_URL) as ws:
                    self._market_ws = ws
                    delay = RECONNECT_BASE_DELAY
                    logger.info("[ws] market connected tokens=%s", len(token_ids))
                    init_msg = json.dumps({
                        "assets_ids": token_ids,
                        "type": "market",
                        "initial_dump": True,
                        "level": 2,
                        "custom_feature_enabled": False,
                    })
                    await ws.send(init_msg)
                    ping_task = asyncio.create_task(self._ping_loop(ws, MARKET_PING_INTERVAL))
                    try:
                        async for message in ws:
                            if message == "PONG":
                                continue
                            self._handle_market_message(str(message))
                    finally:
                        ping_task.cancel()
            except Exception as err:
                logger.warning("[ws] market disconnected error=%s reconnecting in %.1fs", err, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)

    async def _ping_loop(self, ws, interval: int) -> None:
        while True:
            try:
                await asyncio.sleep(interval)
                await ws.send("PING")
            except Exception:
                break

    async def subscribe(self, token_ids: list[str]) -> None:
        if self._market_ws is not None:
            msg = json.dumps({
                "operation": "subscribe",
                "assets_ids": token_ids,
                "level": 2,
                "custom_feature_enabled": False,
            })
            try:
                await self._market_ws.send(msg)
                logger.info("[ws] subscribed tokens=%s", len(token_ids))
            except Exception as err:
                logger.warning("[ws] subscribe_failed error=%s", err)

    async def unsubscribe(self, token_ids: list[str]) -> None:
        if self._market_ws is not None:
            msg = json.dumps({
                "operation": "unsubscribe",
                "assets_ids": token_ids,
            })
            try:
                await self._market_ws.send(msg)
            except Exception as err:
                logger.warning("[ws] unsubscribe_failed error=%s", err)

    async def start(self, market_token_ids: Optional[list[str]] = None) -> None:
        self._running = True
        self._tasks.append(asyncio.create_task(self._rtds_loop()))
        if market_token_ids:
            self._tasks.append(asyncio.create_task(self._market_loop(market_token_ids)))
        logger.info("[ws] started rtds=true market=%s", bool(market_token_ids))

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        logger.info("[ws] stopped")
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python -m pytest tests/test_websocket.py -v`
Expected: All 16 tests PASS

**Step 5: Commit**

```bash
git add agents/connectors/websocket.py tests/test_websocket.py
git commit -m "feat: add WebSocket manager for RTDS and Market Channel"
```

---

### Task 4: Market Filter / Discovery

**Files:**
- Create: `agents/application/market_filter.py`
- Create: `tests/test_market_filter.py`

**Step 1: Write the failing tests**

Create `tests/test_market_filter.py`:

```python
import pytest

from agents.application.market_filter import (
    CryptoMarketInfo,
    extract_crypto_price_target,
    is_crypto_price_market,
    is_5min_btc_market,
    parse_market_expiry_seconds,
    SYMBOL_MAP,
)


class TestIsCryptoPriceMarket:
    def test_btc_above_question(self):
        assert is_crypto_price_market("Will BTC be above $100,000 on March 1?") is True

    def test_bitcoin_question(self):
        assert is_crypto_price_market("Will Bitcoin be above $100,000?") is True

    def test_eth_price_question(self):
        assert is_crypto_price_market("Will ETH be above $4,000 by end of March?") is True

    def test_solana_question(self):
        assert is_crypto_price_market("Will SOL reach $200?") is True

    def test_non_crypto_question(self):
        assert is_crypto_price_market("Will the Lakers win the NBA championship?") is False

    def test_crypto_regulation_not_price(self):
        assert is_crypto_price_market("Will Congress pass crypto regulation in 2026?") is False

    def test_xrp_question(self):
        assert is_crypto_price_market("Will XRP price be above $3 on April 1?") is True


class TestExtractCryptoPriceTarget:
    def test_btc_target(self):
        info = extract_crypto_price_target("Will BTC be above $100,000 on March 1?")
        assert info is not None
        assert info.symbol == "BTC"
        assert info.target_price == 100000.0
        assert info.direction == "above"

    def test_eth_below_target(self):
        info = extract_crypto_price_target("Will ETH be below $3,500 by end of February?")
        assert info is not None
        assert info.symbol == "ETH"
        assert info.target_price == 3500.0
        assert info.direction == "below"

    def test_no_price_found(self):
        info = extract_crypto_price_target("Will Bitcoin moon?")
        assert info is None

    def test_decimal_price(self):
        info = extract_crypto_price_target("Will SOL be above $198.50 on March 3?")
        assert info is not None
        assert info.target_price == 198.50


class TestIs5MinBtcMarket:
    def test_five_minute_market(self):
        assert is_5min_btc_market("Will BTC be above $97,500 at 2:05 PM? (5 minutes)") is True

    def test_five_minute_hyphenated(self):
        assert is_5min_btc_market("BTC 5-minute interval: above $98,000?") is True

    def test_hourly_market(self):
        assert is_5min_btc_market("Will BTC be above $97,500 in 1 hour?") is False

    def test_non_btc_5min(self):
        assert is_5min_btc_market("Will ETH be above $4,000 at 2:05 PM? (5 minutes)") is False


class TestSymbolMap:
    def test_btc_symbols(self):
        assert "btcusdt" in SYMBOL_MAP["BTC"]["binance"]
        assert "btc/usd" in SYMBOL_MAP["BTC"]["chainlink"]

    def test_eth_symbols(self):
        assert "ethusdt" in SYMBOL_MAP["ETH"]["binance"]
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python -m pytest tests/test_market_filter.py -v`
Expected: FAIL with ImportError

**Step 3: Write implementation**

Create `agents/application/market_filter.py`:

```python
import re
from dataclasses import dataclass
from typing import Optional


SYMBOL_MAP = {
    "BTC": {"binance": "btcusdt", "chainlink": "btc/usd", "aliases": ["bitcoin", "btc"]},
    "ETH": {"binance": "ethusdt", "chainlink": "eth/usd", "aliases": ["ethereum", "eth", "ether"]},
    "SOL": {"binance": "solusdt", "chainlink": "sol/usd", "aliases": ["solana", "sol"]},
    "XRP": {"binance": "xrpusdt", "chainlink": "xrp/usd", "aliases": ["xrp", "ripple"]},
}

_CRYPTO_PRICE_KEYWORDS = re.compile(
    r"\b(btc|bitcoin|eth|ethereum|ether|sol|solana|xrp|ripple)\b",
    re.IGNORECASE,
)
_PRICE_DIRECTION_PATTERN = re.compile(
    r"\b(above|below|over|under|reach|exceed|hit)\b",
    re.IGNORECASE,
)
_PRICE_AMOUNT_PATTERN = re.compile(
    r"\$([0-9]{1,3}(?:,?[0-9]{3})*(?:\.[0-9]+)?)",
)
_5MIN_PATTERN = re.compile(
    r"5[\s-]?min(?:ute)?",
    re.IGNORECASE,
)


@dataclass
class CryptoMarketInfo:
    symbol: str
    target_price: float
    direction: str  # "above" or "below"
    ws_key_binance: str
    ws_key_chainlink: str


def _detect_symbol(text: str) -> Optional[str]:
    lowered = text.lower()
    for symbol, info in SYMBOL_MAP.items():
        for alias in info["aliases"]:
            if re.search(r"\b" + re.escape(alias) + r"\b", lowered):
                return symbol
    return None


def is_crypto_price_market(question: str) -> bool:
    has_crypto = _CRYPTO_PRICE_KEYWORDS.search(question) is not None
    has_price = _PRICE_AMOUNT_PATTERN.search(question) is not None
    has_direction = _PRICE_DIRECTION_PATTERN.search(question) is not None
    return has_crypto and (has_price or has_direction)


def extract_crypto_price_target(question: str) -> Optional[CryptoMarketInfo]:
    symbol = _detect_symbol(question)
    if symbol is None:
        return None
    price_match = _PRICE_AMOUNT_PATTERN.search(question)
    if price_match is None:
        return None
    price_str = price_match.group(1).replace(",", "")
    try:
        target_price = float(price_str)
    except ValueError:
        return None
    direction_match = _PRICE_DIRECTION_PATTERN.search(question)
    if direction_match:
        raw = direction_match.group(1).lower()
        direction = "below" if raw in ("below", "under") else "above"
    else:
        direction = "above"
    mapping = SYMBOL_MAP[symbol]
    return CryptoMarketInfo(
        symbol=symbol,
        target_price=target_price,
        direction=direction,
        ws_key_binance=mapping["binance"],
        ws_key_chainlink=mapping["chainlink"],
    )


def is_5min_btc_market(question: str) -> bool:
    lowered = question.lower()
    has_btc = any(
        alias in lowered for alias in SYMBOL_MAP["BTC"]["aliases"]
    )
    has_5min = _5MIN_PATTERN.search(question) is not None
    return has_btc and has_5min


def parse_market_expiry_seconds(end_date_iso: str) -> Optional[float]:
    """Return seconds until market expires, or None if unparseable."""
    import datetime
    try:
        end_dt = datetime.datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
        now = datetime.datetime.now(datetime.timezone.utc)
        delta = (end_dt - now).total_seconds()
        return delta if delta > 0 else 0.0
    except (ValueError, TypeError):
        return None
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python -m pytest tests/test_market_filter.py -v`
Expected: All 14 tests PASS

**Step 5: Commit**

```bash
git add agents/application/market_filter.py tests/test_market_filter.py
git commit -m "feat: add crypto market filter and price target extraction"
```

---

### Task 5: Async Runner

**Files:**
- Create: `agents/application/runner.py`
- Create: `tests/test_runner.py`

**Step 1: Write the failing tests**

Create `tests/test_runner.py`:

```python
import asyncio

import pytest

from agents.application.runner import AsyncRunner
from agents.application.budget import SessionBudgetManager
from agents.connectors.websocket import WebSocketManager


class TestAsyncRunner:
    def test_creation(self):
        runner = AsyncRunner(
            session_budget=100.0,
            interval_seconds=30,
        )
        assert isinstance(runner.budget, SessionBudgetManager)
        assert isinstance(runner.ws, WebSocketManager)
        assert runner.interval_seconds == 30
        assert runner.budget.total_budget == 100.0

    def test_should_continue_fresh(self):
        runner = AsyncRunner(session_budget=100.0, interval_seconds=30)
        assert runner.should_continue() is True

    def test_should_continue_exhausted(self):
        runner = AsyncRunner(session_budget=10.0, interval_seconds=30)
        runner.budget.record_trade(10.0, market_id=1, outcome="Yes")
        assert runner.should_continue() is False

    def test_should_continue_stopped(self):
        runner = AsyncRunner(session_budget=100.0, interval_seconds=30)
        runner.stop()
        assert runner.should_continue() is False

    def test_cycle_count(self):
        runner = AsyncRunner(session_budget=100.0, interval_seconds=30)
        assert runner.cycle_count == 0
        runner.cycle_count += 1
        assert runner.cycle_count == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python -m pytest tests/test_runner.py -v`
Expected: FAIL with ImportError

**Step 3: Write implementation**

Create `agents/application/runner.py`:

```python
import asyncio
import logging
import signal
from typing import Callable, Coroutine, Optional

from agents.application.budget import SessionBudgetManager
from agents.connectors.websocket import WebSocketManager

logger = logging.getLogger(__name__)


class AsyncRunner:
    def __init__(
        self,
        session_budget: float,
        interval_seconds: int = 30,
        history_size: int = 300,
    ) -> None:
        self.budget = SessionBudgetManager(total_budget=session_budget)
        self.ws = WebSocketManager(history_size=history_size)
        self.interval_seconds = interval_seconds
        self.cycle_count = 0
        self._running = True

    def should_continue(self) -> bool:
        return self._running and not self.budget.is_exhausted()

    def stop(self) -> None:
        self._running = False

    async def run(
        self,
        strategy_fn: Callable[["AsyncRunner", int], Coroutine],
        market_token_ids: Optional[list[str]] = None,
        connect_rtds: bool = True,
    ) -> None:
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, self.stop)
        loop.add_signal_handler(signal.SIGTERM, self.stop)

        logger.info(
            "[runner] starting budget=%.2f interval=%ds",
            self.budget.total_budget,
            self.interval_seconds,
        )

        if connect_rtds or market_token_ids:
            await self.ws.start(market_token_ids=market_token_ids)
            # brief pause to let initial WS data arrive
            await asyncio.sleep(2)

        try:
            while self.should_continue():
                self.cycle_count += 1
                logger.info(
                    "[runner] cycle=%d remaining=%.2f",
                    self.cycle_count,
                    self.budget.remaining(),
                )
                try:
                    await strategy_fn(self, self.cycle_count)
                except Exception as err:
                    logger.error("[runner] cycle_error cycle=%d error=%s", self.cycle_count, err)

                if self.should_continue():
                    await asyncio.sleep(self.interval_seconds)
        finally:
            await self.ws.stop()
            print()
            print("=" * 60)
            print("SESSION COMPLETE")
            print(self.budget.summary())
            print("=" * 60)


def run_strategy(
    strategy_fn: Callable[[AsyncRunner, int], Coroutine],
    session_budget: float,
    interval_seconds: int = 30,
    market_token_ids: Optional[list[str]] = None,
    connect_rtds: bool = True,
) -> None:
    """Synchronous entry point for CLI commands."""
    runner = AsyncRunner(
        session_budget=session_budget,
        interval_seconds=interval_seconds,
    )
    asyncio.run(
        runner.run(
            strategy_fn=strategy_fn,
            market_token_ids=market_token_ids,
            connect_rtds=connect_rtds,
        )
    )
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python -m pytest tests/test_runner.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add agents/application/runner.py tests/test_runner.py
git commit -m "feat: add async runner with signal handling and lifecycle"
```

---

### Task 6: Crypto Prompt for LLM

**Files:**
- Modify: `agents/application/prompts.py` (add `crypto_price_analyst` method)

**Step 1: Write the failing test**

Add to the bottom of `tests/test_market_filter.py`:

```python
class TestCryptoPrompt:
    def test_prompt_contains_required_fields(self):
        from agents.application.prompts import Prompter
        p = Prompter()
        prompt = p.crypto_price_analyst(
            symbol="BTC",
            current_price=97500.0,
            target_price=100000.0,
            direction="above",
            momentum_1m=0.002,
            momentum_5m=0.01,
            momentum_15m=0.03,
            time_remaining_hours=24.0,
            market_yes_price=0.45,
            market_no_price=0.55,
        )
        assert "97500" in prompt or "97,500" in prompt
        assert "100000" in prompt or "100,000" in prompt
        assert "BTC" in prompt
        assert "momentum" in prompt.lower() or "Momentum" in prompt
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python -m pytest tests/test_market_filter.py::TestCryptoPrompt -v`
Expected: FAIL with AttributeError (no crypto_price_analyst method)

**Step 3: Add method to `agents/application/prompts.py`**

Append before the last method (`create_new_market`) in the Prompter class, add this method. Insert after line 220 (the closing `"""` of `format_size_from_one_best_trade_output`):

```python
    def crypto_price_analyst(
        self,
        symbol: str,
        current_price: float,
        target_price: float,
        direction: str,
        momentum_1m: float,
        momentum_5m: float,
        momentum_15m: float,
        time_remaining_hours: float,
        market_yes_price: float,
        market_no_price: float,
    ) -> str:
        return (
            self.polymarket_analyst_api()
            + f"""
        You are analyzing a crypto price prediction market.

        Asset: {symbol}
        Current live price: ${current_price:,.2f}
        Market question: Will {symbol} be {direction} ${target_price:,.2f}?
        Time remaining: {time_remaining_hours:.1f} hours

        Live price momentum:
        - 1-minute momentum: {momentum_1m:+.4f} ({momentum_1m*100:+.2f}%)
        - 5-minute momentum: {momentum_5m:+.4f} ({momentum_5m*100:+.2f}%)
        - 15-minute momentum: {momentum_15m:+.4f} ({momentum_15m*100:+.2f}%)

        Current market odds:
        - Yes price: {market_yes_price:.4f} (implied {market_yes_price*100:.1f}% probability)
        - No price: {market_no_price:.4f} (implied {market_no_price*100:.1f}% probability)

        Distance to target: {abs(current_price - target_price) / current_price * 100:.2f}% {'above' if current_price > target_price else 'below'} target

        Based on the live price data, momentum, and market odds, is this market mispriced?
        Return JSON only (no markdown, no prose outside JSON) using this schema:
        {{
          "probabilities": [
            {{"outcome": "Yes", "likelihood": <float between 0 and 1>}},
            {{"outcome": "No", "likelihood": <float between 0 and 1>}}
          ],
          "selected_outcome": "<Yes or No>",
          "side": "<BUY or SELL>",
          "price": <float between 0 and 1>,
          "size_fraction": <float between 0 and 1>,
          "rationale": "<short concise reasoning based on price data and momentum>",
          "risk_factors": ["<risk 1>", "<risk 2>"],
          "counter_case": "<short opposing view>"
        }}
        """
        )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python -m pytest tests/test_market_filter.py::TestCryptoPrompt -v`
Expected: PASS

**Step 5: Commit**

```bash
git add agents/application/prompts.py tests/test_market_filter.py
git commit -m "feat: add crypto price analyst LLM prompt"
```

---

### Task 7: Continuous Mode Strategy

**Files:**
- Create: `agents/application/continuous.py`

**Step 1: Write implementation**

Create `agents/application/continuous.py`:

```python
import asyncio
import logging
import os
from typing import Optional

from agents.application.budget import SessionBudgetManager
from agents.application.executor import Executor as Agent
from agents.application.runner import AsyncRunner, run_strategy
from agents.application.trade import Trader
from agents.connectors.websocket import WebSocketManager

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


class ContinuousStrategy:
    def __init__(
        self,
        include_news: bool = False,
        exclude_sports: bool = False,
        news_limit: int = 5,
        news_days: int = 7,
        news_relevance: bool = True,
        cooldown_seconds: int = 300,
        volatility_threshold: float = 0.05,
        events_refresh_cycles: int = 5,
    ) -> None:
        self.trader = Trader()
        self.include_news = include_news
        self.exclude_sports = exclude_sports
        self.news_limit = news_limit
        self.news_days = news_days
        self.news_relevance = news_relevance
        self.cooldown_seconds = cooldown_seconds
        self.volatility_threshold = volatility_threshold
        self.events_refresh_cycles = events_refresh_cycles
        self._cached_events = None
        self._events_fetched_cycle = 0

    async def run_cycle(self, runner: AsyncRunner, cycle: int) -> None:
        budget = runner.budget
        ws = runner.ws

        if not budget.can_spend(self.trader.min_order_amount_usdc):
            logger.info("[continuous] budget_exhausted remaining=%.2f", budget.remaining())
            runner.stop()
            return

        # Refresh events periodically
        if (
            self._cached_events is None
            or (cycle - self._events_fetched_cycle) >= self.events_refresh_cycles
        ):
            logger.info("[continuous] refreshing_events cycle=%d", cycle)
            self._cached_events = await asyncio.to_thread(
                self.trader.polymarket.get_all_tradeable_events
            )
            self._events_fetched_cycle = cycle
            logger.info("[continuous] cached_events=%d", len(self._cached_events or []))

        events = self._cached_events
        if not events:
            logger.info("[continuous] no_events_found")
            return

        # Filter events with RAG
        filtered_events = await asyncio.to_thread(
            self.trader.agent.filter_events_with_rag, events
        )
        if not filtered_events:
            logger.info("[continuous] no_events_after_filter")
            return

        # Map to markets
        markets = await asyncio.to_thread(
            self.trader.agent.map_filtered_events_to_markets, filtered_events
        )
        if not markets:
            logger.info("[continuous] no_markets_found")
            return

        # Filter markets with RAG
        filtered_markets = await asyncio.to_thread(
            self.trader.agent.filter_markets, markets
        )
        if not filtered_markets:
            logger.info("[continuous] no_markets_after_filter")
            return

        # Exclude sports if configured
        if self.exclude_sports:
            filtered_markets = self.trader._exclude_sports_markets(filtered_markets)
            if not filtered_markets:
                return

        # Filter out markets on cooldown
        filtered_markets = self._filter_cooldown_markets(filtered_markets, budget)

        # Prioritize volatile markets (those with big WebSocket price swings)
        filtered_markets = self._prioritize_volatile_markets(filtered_markets, ws)

        if not filtered_markets:
            logger.info("[continuous] no_markets_after_cooldown_and_volatility_filter")
            return

        # Build news context if enabled
        context_by_market_id = None
        if self.include_news:
            context_by_market_id = await asyncio.to_thread(
                self.trader._build_news_context_by_market_id,
                filtered_markets,
                self.news_limit,
                self.news_days,
                self.news_relevance,
            )

        # Build candidates via LLM
        candidates_payload = await asyncio.to_thread(
            self.trader.agent.build_trade_candidates,
            filtered_markets,
            context_by_market_id,
        )

        selected = candidates_payload.get("selected_candidates", [])
        if not selected:
            logger.info("[continuous] no_candidates_selected")
            return

        # Allocate from session budget (not full wallet)
        remaining = budget.remaining()
        self.trader.agent.allocate_selected_candidates(selected, remaining)

        # Execute trades
        for candidate in selected:
            if candidate.allocation_amount_usdc <= 0:
                continue
            if not budget.can_spend(candidate.allocation_amount_usdc):
                candidate.execution_status = "SKIPPED_BUDGET_EXHAUSTED"
                continue

            if self.trader.execute_trades:
                try:
                    token_map = self.trader.polymarket.resolve_token_for_outcome(
                        outcomes=candidate.outcomes,
                        token_ids=candidate.token_ids,
                        selected_outcome=candidate.suggested_outcome,
                        side=candidate.parsed_side,
                    )
                    response = await asyncio.to_thread(
                        self.trader.polymarket.execute_market_order_for_token,
                        token_map["token_id"],
                        candidate.allocation_amount_usdc,
                    )
                    candidate.execution_status = "EXECUTED"
                    candidate.execution_response = response
                    budget.record_trade(
                        amount=candidate.allocation_amount_usdc,
                        market_id=candidate.market_id,
                        outcome=candidate.suggested_outcome,
                    )
                    logger.info(
                        "[continuous] executed market_id=%d amount=%.2f outcome=%s",
                        candidate.market_id,
                        candidate.allocation_amount_usdc,
                        candidate.suggested_outcome,
                    )
                except Exception as err:
                    candidate.execution_status = "FAILED"
                    candidate.execution_response = str(err)
                    logger.error("[continuous] execution_failed market_id=%d error=%s", candidate.market_id, err)
            else:
                candidate.execution_status = "DRY_RUN"
                budget.record_trade(
                    amount=candidate.allocation_amount_usdc,
                    market_id=candidate.market_id,
                    outcome=candidate.suggested_outcome,
                )

        # Print cycle summary
        mode = "DRY_RUN" if not self.trader.execute_trades else "LIVE"
        self.trader._print_trade_summary_table(selected, mode=f"{mode}_C{cycle}")

    def _filter_cooldown_markets(self, markets, budget: SessionBudgetManager):
        result = []
        for market_obj in markets:
            market_doc = market_obj[0] if isinstance(market_obj, (list, tuple)) else None
            metadata = getattr(market_doc, "metadata", {}) or {}
            try:
                market_id = int(metadata.get("id", 0))
            except (TypeError, ValueError):
                market_id = 0
            if not budget.is_on_cooldown(market_id, self.cooldown_seconds):
                result.append(market_obj)
        return result

    def _prioritize_volatile_markets(self, markets, ws: WebSocketManager):
        """Move markets with high orderbook price volatility to the front."""
        # For now, return as-is. Volatility detection requires subscribed orderbooks.
        # Future: track price_change events and reorder by magnitude.
        return markets


def start_continuous(
    interval: int = 30,
    session_budget: float = 100.0,
    cooldown: int = 300,
    include_news: bool = False,
    exclude_sports: bool = False,
    news_limit: int = 5,
    news_days: int = 7,
    news_relevance: bool = True,
    volatility_threshold: float = 0.05,
) -> None:
    strategy = ContinuousStrategy(
        include_news=include_news,
        exclude_sports=exclude_sports,
        news_limit=news_limit,
        news_days=news_days,
        news_relevance=news_relevance,
        cooldown_seconds=cooldown,
        volatility_threshold=volatility_threshold,
    )
    run_strategy(
        strategy_fn=strategy.run_cycle,
        session_budget=session_budget,
        interval_seconds=interval,
        connect_rtds=False,  # continuous mode doesn't need RTDS
    )
```

**Step 2: Smoke test import**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python -c "from agents.application.continuous import ContinuousStrategy; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add agents/application/continuous.py
git commit -m "feat: add continuous mode trading strategy"
```

---

### Task 8: Crypto Mode Strategy

**Files:**
- Create: `agents/application/crypto.py`

**Step 1: Write implementation**

Create `agents/application/crypto.py`:

```python
import asyncio
import logging
import os
from typing import Dict, List, Optional

from agents.application.budget import SessionBudgetManager
from agents.application.executor import Executor as Agent, _safe_float
from agents.application.market_filter import (
    SYMBOL_MAP,
    CryptoMarketInfo,
    extract_crypto_price_target,
    is_crypto_price_market,
    parse_market_expiry_seconds,
)
from agents.application.prompts import Prompter
from agents.application.runner import AsyncRunner, run_strategy
from agents.application.trade import Trader
from agents.connectors.websocket import WebSocketManager

logger = logging.getLogger(__name__)


class CryptoStrategy:
    def __init__(
        self,
        symbols: list[str],
        min_edge: float = 0.05,
    ) -> None:
        self.trader = Trader()
        self.agent = Agent()
        self.prompter = Prompter()
        self.symbols = [s.upper() for s in symbols]
        self.min_edge = min_edge
        self._cached_markets: Optional[list] = None
        self._markets_fetched_cycle = 0
        self._markets_refresh_cycles = 10

    async def run_cycle(self, runner: AsyncRunner, cycle: int) -> None:
        budget = runner.budget
        ws = runner.ws

        if not budget.can_spend(self.trader.min_order_amount_usdc):
            logger.info("[crypto] budget_exhausted")
            runner.stop()
            return

        # Refresh crypto markets periodically
        if (
            self._cached_markets is None
            or (cycle - self._markets_fetched_cycle) >= self._markets_refresh_cycles
        ):
            all_events = await asyncio.to_thread(
                self.trader.polymarket.get_all_tradeable_events
            )
            all_markets_raw = await asyncio.to_thread(
                self.agent.map_filtered_events_to_markets, all_events
            )
            # Filter for crypto price markets only
            self._cached_markets = self._filter_crypto_price_markets(all_markets_raw)
            self._markets_fetched_cycle = cycle
            logger.info("[crypto] cached_crypto_markets=%d", len(self._cached_markets))

        crypto_markets = self._cached_markets
        if not crypto_markets:
            logger.info("[crypto] no_crypto_markets_found")
            return

        # Evaluate each market with live price data
        for market_info, market_data in crypto_markets:
            if not budget.can_spend(self.trader.min_order_amount_usdc):
                break

            if budget.is_on_cooldown(market_data["market_id"], cooldown_seconds=300):
                continue

            # Get live price
            live_price = ws.get_price(market_info.ws_key_binance)
            if live_price is None:
                continue

            # Calculate momentum
            momentum_1m = ws.get_momentum(market_info.ws_key_binance, window_secs=60)
            momentum_5m = ws.get_momentum(market_info.ws_key_binance, window_secs=300)
            momentum_15m = ws.get_momentum(market_info.ws_key_binance, window_secs=900)

            # Time remaining
            time_remaining = parse_market_expiry_seconds(market_data.get("end", ""))
            hours_remaining = (time_remaining or 0) / 3600.0
            if hours_remaining <= 0:
                continue

            # Get market prices
            yes_price = _safe_float(market_data.get("yes_price", 0.5))
            no_price = _safe_float(market_data.get("no_price", 0.5))

            # LLM analysis
            prompt = self.prompter.crypto_price_analyst(
                symbol=market_info.symbol,
                current_price=live_price,
                target_price=market_info.target_price,
                direction=market_info.direction,
                momentum_1m=momentum_1m,
                momentum_5m=momentum_5m,
                momentum_15m=momentum_15m,
                time_remaining_hours=hours_remaining,
                market_yes_price=yes_price,
                market_no_price=no_price,
            )

            try:
                response = await asyncio.to_thread(
                    self.agent._invoke_llm,
                    prompt,
                    "crypto_price_analysis",
                )
                trade_json = self.agent._parse_json_object(response)
            except Exception as err:
                logger.error("[crypto] llm_error market_id=%s error=%s", market_data.get("market_id"), err)
                continue

            # Check edge
            probs = trade_json.get("probabilities", [])
            selected_outcome = trade_json.get("selected_outcome", "")
            side = str(trade_json.get("side", "BUY")).upper()

            model_prob = 0.5
            for p in probs:
                if p.get("outcome") == selected_outcome:
                    model_prob = _safe_float(p.get("likelihood", 0.5))
                    break

            implied_prob = yes_price if selected_outcome == "Yes" else no_price
            edge = abs(model_prob - implied_prob)

            if edge < self.min_edge:
                logger.info(
                    "[crypto] skipped_low_edge market_id=%s edge=%.4f min=%.4f",
                    market_data.get("market_id"), edge, self.min_edge,
                )
                continue

            # Determine allocation
            alloc = min(budget.remaining() * 0.10, budget.remaining())
            alloc = max(alloc, self.trader.min_order_amount_usdc)
            if not budget.can_spend(alloc):
                continue

            # Execute or dry run
            market_id = market_data.get("market_id", 0)
            if self.trader.execute_trades:
                try:
                    token_map = self.trader.polymarket.resolve_token_for_outcome(
                        outcomes=market_data.get("outcomes", []),
                        token_ids=market_data.get("token_ids", []),
                        selected_outcome=selected_outcome,
                        side=side,
                    )
                    await asyncio.to_thread(
                        self.trader.polymarket.execute_market_order_for_token,
                        token_map["token_id"],
                        alloc,
                    )
                    budget.record_trade(alloc, market_id, selected_outcome)
                    logger.info(
                        "[crypto] executed market_id=%d amount=%.2f outcome=%s edge=%.4f",
                        market_id, alloc, selected_outcome, edge,
                    )
                except Exception as err:
                    logger.error("[crypto] execution_failed market_id=%d error=%s", market_id, err)
            else:
                budget.record_trade(alloc, market_id, selected_outcome)
                logger.info(
                    "[crypto] dry_run market_id=%d amount=%.2f outcome=%s edge=%.4f",
                    market_id, alloc, selected_outcome, edge,
                )

        logger.info("[crypto] cycle=%d complete remaining=%.2f", cycle, budget.remaining())

    def _filter_crypto_price_markets(self, markets_raw) -> list:
        """Filter SimpleMarket list for crypto price markets and extract info."""
        results = []
        for market in markets_raw:
            if isinstance(market, dict):
                question = market.get("question", "")
                data = market
            else:
                question = getattr(market, "question", "")
                data = {
                    "market_id": getattr(market, "id", 0),
                    "question": question,
                    "end": getattr(market, "end", ""),
                    "outcomes": self.agent._parse_literal_list(getattr(market, "outcomes", "[]")),
                    "token_ids": self.agent._parse_literal_list(getattr(market, "clob_token_ids", "[]")),
                    "yes_price": 0.5,
                    "no_price": 0.5,
                }
                prices = self.agent._parse_literal_list(getattr(market, "outcome_prices", "[]"))
                if len(prices) >= 2:
                    data["yes_price"] = _safe_float(prices[0], 0.5)
                    data["no_price"] = _safe_float(prices[1], 0.5)

            if not is_crypto_price_market(question):
                continue

            info = extract_crypto_price_target(question)
            if info is None:
                continue

            if info.symbol not in self.symbols:
                continue

            results.append((info, data))

        logger.info("[crypto] found %d crypto price markets for symbols %s", len(results), self.symbols)
        return results


def start_crypto(
    interval: int = 30,
    session_budget: float = 100.0,
    symbols: str = "BTC,ETH,SOL,XRP",
    min_edge: float = 0.05,
) -> None:
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    strategy = CryptoStrategy(
        symbols=symbol_list,
        min_edge=min_edge,
    )
    run_strategy(
        strategy_fn=strategy.run_cycle,
        session_budget=session_budget,
        interval_seconds=interval,
        connect_rtds=True,
    )
```

**Step 2: Smoke test import**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python -c "from agents.application.crypto import CryptoStrategy; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add agents/application/crypto.py
git commit -m "feat: add crypto mode trading strategy with live WebSocket prices"
```

---

### Task 9: BTC 5-Min Arbitrage Strategy

**Files:**
- Create: `agents/application/btc_arbitrage.py`
- Create: `tests/test_btc_arbitrage.py`

**Step 1: Write the failing tests**

Create `tests/test_btc_arbitrage.py`:

```python
import pytest

from agents.application.btc_arbitrage import compute_model_probability


class TestComputeModelProbability:
    def test_price_well_above_target_up_momentum(self):
        prob = compute_model_probability(
            current_price=98000.0,
            target_price=97000.0,
            direction="above",
            momentum_1m=0.001,
            momentum_5m=0.005,
            time_remaining_secs=300,
        )
        assert prob > 0.7  # high confidence target is met

    def test_price_well_below_target_down_momentum(self):
        prob = compute_model_probability(
            current_price=96000.0,
            target_price=97000.0,
            direction="above",
            momentum_1m=-0.001,
            momentum_5m=-0.005,
            time_remaining_secs=300,
        )
        assert prob < 0.3  # low confidence target is met

    def test_price_at_target_no_momentum(self):
        prob = compute_model_probability(
            current_price=97000.0,
            target_price=97000.0,
            direction="above",
            momentum_1m=0.0,
            momentum_5m=0.0,
            time_remaining_secs=300,
        )
        assert 0.3 < prob < 0.7  # uncertain

    def test_probability_clamped(self):
        prob = compute_model_probability(
            current_price=200000.0,
            target_price=97000.0,
            direction="above",
            momentum_1m=0.05,
            momentum_5m=0.10,
            time_remaining_secs=300,
        )
        assert 0.01 <= prob <= 0.99
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python -m pytest tests/test_btc_arbitrage.py -v`
Expected: FAIL with ImportError

**Step 3: Write implementation**

Create `agents/application/btc_arbitrage.py`:

```python
import asyncio
import logging
import os
from typing import Optional

from agents.application.budget import SessionBudgetManager
from agents.application.executor import Executor as Agent, _safe_float
from agents.application.market_filter import (
    SYMBOL_MAP,
    extract_crypto_price_target,
    is_5min_btc_market,
    parse_market_expiry_seconds,
)
from agents.application.runner import AsyncRunner, run_strategy
from agents.application.trade import Trader
from agents.connectors.websocket import WebSocketManager

logger = logging.getLogger(__name__)


def compute_model_probability(
    current_price: float,
    target_price: float,
    direction: str,
    momentum_1m: float,
    momentum_5m: float,
    time_remaining_secs: float,
) -> float:
    """
    Pure algorithmic probability estimate for whether BTC will be
    above/below target within the time window.

    Factors:
    - Distance from target as % of price
    - Momentum (1m and 5m weighted)
    - Time remaining (more time = more uncertainty)
    """
    if target_price == 0:
        return 0.5

    # Distance factor: how far current price is from target
    distance_pct = (current_price - target_price) / target_price

    # For "above" direction: positive distance = favorable
    # For "below" direction: negative distance = favorable
    if direction == "below":
        distance_pct = -distance_pct

    # Momentum factor (weighted: 5m momentum matters more for 5-min markets)
    momentum_signal = momentum_1m * 0.4 + momentum_5m * 0.6
    if direction == "below":
        momentum_signal = -momentum_signal

    # Time decay: less time remaining = distance matters more
    time_factor = max(0.1, min(1.0, time_remaining_secs / 600.0))

    # Combine signals into a raw score
    # distance_pct of 0.01 (1%) is significant for 5-min window
    distance_score = distance_pct * 50  # scale so 1% = 0.5 score units
    momentum_score = momentum_signal * 200  # scale so 0.5% momentum = 1 score unit

    raw_score = 0.5 + distance_score * (1.0 / time_factor) + momentum_score

    # Clamp to [0.01, 0.99]
    return max(0.01, min(0.99, raw_score))


class BtcArbitrageStrategy:
    def __init__(
        self,
        max_per_trade: float = 5.0,
        min_edge: float = 0.10,
        price_feed_tolerance: float = 0.001,
    ) -> None:
        self.trader = Trader()
        self.agent = Agent()
        self.max_per_trade = max_per_trade
        self.min_edge = min_edge
        self.price_feed_tolerance = price_feed_tolerance
        self._cached_markets: Optional[list] = None
        self._markets_fetched_cycle = 0
        self._markets_refresh_cycles = 3  # refresh more frequently for 5-min markets

    async def run_cycle(self, runner: AsyncRunner, cycle: int) -> None:
        budget = runner.budget
        ws = runner.ws

        if not budget.can_spend(self.trader.min_order_amount_usdc):
            logger.info("[arb] budget_exhausted")
            runner.stop()
            return

        # Validate dual price feeds
        valid, avg_price = ws.validate_dual_feed(
            SYMBOL_MAP["BTC"]["binance"],
            SYMBOL_MAP["BTC"]["chainlink"],
            tolerance=self.price_feed_tolerance,
        )
        if not valid:
            binance_price = ws.get_price(SYMBOL_MAP["BTC"]["binance"])
            chainlink_price = ws.get_price(SYMBOL_MAP["BTC"]["chainlink"])
            logger.warning(
                "[arb] dual_feed_invalid binance=%s chainlink=%s tolerance=%s",
                binance_price, chainlink_price, self.price_feed_tolerance,
            )
            return

        current_btc_price = avg_price

        # Refresh 5-min BTC markets
        if (
            self._cached_markets is None
            or (cycle - self._markets_fetched_cycle) >= self._markets_refresh_cycles
        ):
            all_events = await asyncio.to_thread(
                self.trader.polymarket.get_all_tradeable_events
            )
            all_markets = await asyncio.to_thread(
                self.agent.map_filtered_events_to_markets, all_events
            )
            self._cached_markets = self._filter_5min_btc_markets(all_markets)
            self._markets_fetched_cycle = cycle
            logger.info("[arb] cached_5min_markets=%d", len(self._cached_markets))

        markets_5min = self._cached_markets
        if not markets_5min:
            logger.info("[arb] no_5min_btc_markets")
            return

        trades_this_cycle = 0
        for market_info, market_data in markets_5min:
            if not budget.can_spend(self.trader.min_order_amount_usdc):
                break

            market_id = market_data.get("market_id", 0)
            if budget.is_on_cooldown(market_id, cooldown_seconds=300):
                continue

            # Time remaining
            time_remaining = parse_market_expiry_seconds(market_data.get("end", ""))
            if time_remaining is None or time_remaining <= 0:
                continue
            if time_remaining > 600:  # skip if more than 10 minutes out
                continue

            # Momentum
            momentum_1m = ws.get_momentum(SYMBOL_MAP["BTC"]["binance"], window_secs=60)
            momentum_5m = ws.get_momentum(SYMBOL_MAP["BTC"]["binance"], window_secs=300)

            # Model probability
            model_prob = compute_model_probability(
                current_price=current_btc_price,
                target_price=market_info.target_price,
                direction=market_info.direction,
                momentum_1m=momentum_1m,
                momentum_5m=momentum_5m,
                time_remaining_secs=time_remaining,
            )

            # Market implied probability
            yes_price = _safe_float(market_data.get("yes_price", 0.5))
            no_price = _safe_float(market_data.get("no_price", 0.5))

            # Determine trade direction
            if model_prob > yes_price + self.min_edge:
                selected_outcome = "Yes"
                side = "BUY"
                edge = model_prob - yes_price
            elif (1 - model_prob) > no_price + self.min_edge:
                selected_outcome = "No"
                side = "BUY"
                edge = (1 - model_prob) - no_price
            else:
                continue  # no edge

            alloc = min(self.max_per_trade, budget.remaining())
            if alloc < self.trader.min_order_amount_usdc:
                continue

            logger.info(
                "[arb] signal market_id=%d target=%.0f current=%.0f model_prob=%.4f "
                "implied_yes=%.4f edge=%.4f outcome=%s time_left=%.0fs",
                market_id, market_info.target_price, current_btc_price,
                model_prob, yes_price, edge, selected_outcome, time_remaining,
            )

            if self.trader.execute_trades:
                try:
                    token_map = self.trader.polymarket.resolve_token_for_outcome(
                        outcomes=market_data.get("outcomes", []),
                        token_ids=market_data.get("token_ids", []),
                        selected_outcome=selected_outcome,
                        side=side,
                    )
                    await asyncio.to_thread(
                        self.trader.polymarket.execute_market_order_for_token,
                        token_map["token_id"],
                        alloc,
                    )
                    budget.record_trade(alloc, market_id, selected_outcome)
                    trades_this_cycle += 1
                    logger.info("[arb] executed market_id=%d amount=%.2f", market_id, alloc)
                except Exception as err:
                    logger.error("[arb] execution_failed market_id=%d error=%s", market_id, err)
            else:
                budget.record_trade(alloc, market_id, selected_outcome)
                trades_this_cycle += 1
                logger.info("[arb] dry_run market_id=%d amount=%.2f edge=%.4f", market_id, alloc, edge)

        logger.info(
            "[arb] cycle=%d trades=%d remaining=%.2f btc=%.0f",
            cycle, trades_this_cycle, budget.remaining(), current_btc_price,
        )

    def _filter_5min_btc_markets(self, markets_raw) -> list:
        results = []
        for market in markets_raw:
            if isinstance(market, dict):
                question = market.get("question", "")
                data = market
            else:
                question = getattr(market, "question", "")
                data = {
                    "market_id": getattr(market, "id", 0),
                    "question": question,
                    "end": getattr(market, "end", ""),
                    "outcomes": self.agent._parse_literal_list(getattr(market, "outcomes", "[]")),
                    "token_ids": self.agent._parse_literal_list(getattr(market, "clob_token_ids", "[]")),
                    "yes_price": 0.5,
                    "no_price": 0.5,
                }
                prices = self.agent._parse_literal_list(getattr(market, "outcome_prices", "[]"))
                if len(prices) >= 2:
                    data["yes_price"] = _safe_float(prices[0], 0.5)
                    data["no_price"] = _safe_float(prices[1], 0.5)

            if not is_5min_btc_market(question):
                continue

            info = extract_crypto_price_target(question)
            if info is None:
                continue

            results.append((info, data))

        return results


def start_btc_arbitrage(
    session_budget: float = 50.0,
    max_per_trade: float = 5.0,
    min_edge: float = 0.10,
    price_feed_tolerance: float = 0.001,
) -> None:
    strategy = BtcArbitrageStrategy(
        max_per_trade=max_per_trade,
        min_edge=min_edge,
        price_feed_tolerance=price_feed_tolerance,
    )
    run_strategy(
        strategy_fn=strategy.run_cycle,
        session_budget=session_budget,
        interval_seconds=15,  # faster interval for 5-min markets
        connect_rtds=True,
    )
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python -m pytest tests/test_btc_arbitrage.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add agents/application/btc_arbitrage.py tests/test_btc_arbitrage.py
git commit -m "feat: add BTC 5-min arbitrage strategy with dual feed validation"
```

---

### Task 10: CLI Commands

**Files:**
- Modify: `scripts/python/cli.py` (add 3 new commands)

**Step 1: Add imports and commands to cli.py**

Add imports after existing imports (after line 11 `from agents.application.creator import Creator`):

```python
from agents.application.continuous import start_continuous
from agents.application.crypto import start_crypto
from agents.application.btc_arbitrage import start_btc_arbitrage
```

Add three new commands before the `if __name__ == "__main__":` block (before line 195):

```python
@app.command()
def run_continuous(
    interval: int = 30,
    session_budget: float = 100.0,
    cooldown: int = 300,
    include_news: bool = False,
    exclude_sports: bool = False,
    news_limit: int = 5,
    news_days: int = 7,
    news_relevance: bool = True,
    volatility_threshold: float = 0.05,
) -> None:
    """
    Run continuous high-speed trading loop. Trades on trending and breaking events
    every INTERVAL seconds until session budget is exhausted or Ctrl+C.
    """
    start_continuous(
        interval=interval,
        session_budget=session_budget,
        cooldown=cooldown,
        include_news=include_news,
        exclude_sports=exclude_sports,
        news_limit=news_limit,
        news_days=news_days,
        news_relevance=news_relevance,
        volatility_threshold=volatility_threshold,
    )


@app.command()
def run_crypto(
    interval: int = 30,
    session_budget: float = 100.0,
    symbols: str = "BTC,ETH,SOL,XRP",
    min_edge: float = 0.05,
) -> None:
    """
    Trade crypto price prediction markets using live WebSocket price feeds.
    Uses real-time BTC/ETH/SOL/XRP prices + LLM analysis to find mispriced markets.
    """
    start_crypto(
        interval=interval,
        session_budget=session_budget,
        symbols=symbols,
        min_edge=min_edge,
    )


@app.command()
def run_crypto_arbitrage(
    session_budget: float = 50.0,
    max_per_trade: float = 5.0,
    min_edge: float = 0.10,
    price_feed_tolerance: float = 0.001,
) -> None:
    """
    Algorithmic BTC 5-minute interval market arbitrage. No LLM - pure price momentum.
    Uses dual Binance + Chainlink feeds for cross-validation.
    Runs on 15-second intervals to catch short-duration markets.
    """
    start_btc_arbitrage(
        session_budget=session_budget,
        max_per_trade=max_per_trade,
        min_edge=min_edge,
        price_feed_tolerance=price_feed_tolerance,
    )
```

**Step 2: Verify CLI commands register**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python scripts/python/cli.py --help`
Expected: Output shows `run-continuous`, `run-crypto`, `run-crypto-arbitrage` in command list

**Step 3: Verify each command's help**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python scripts/python/cli.py run-continuous --help`
Expected: Shows interval, session-budget, cooldown flags

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python scripts/python/cli.py run-crypto --help`
Expected: Shows interval, session-budget, symbols, min-edge flags

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python scripts/python/cli.py run-crypto-arbitrage --help`
Expected: Shows session-budget, max-per-trade, min-edge flags

**Step 4: Commit**

```bash
git add scripts/python/cli.py
git commit -m "feat: add run-continuous, run-crypto, run-crypto-arbitrage CLI commands"
```

---

### Task 11: Configuration (.env.example)

**Files:**
- Modify: `.env.example`

**Step 1: Append new env vars**

Add to end of `.env.example`:

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

**Step 2: Commit**

```bash
git add .env.example
git commit -m "feat: add env config for continuous, crypto, and arbitrage modes"
```

---

### Task 12: Run Full Test Suite

**Step 1: Run all tests**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python -m pytest tests/ -v`
Expected: All tests PASS (budget: 8, websocket: 16, market_filter: 15, btc_arbitrage: 4, runner: 5 = ~48 tests)

**Step 2: Verify all imports work end-to-end**

Run: `cd /Users/djbeatbug/RoadToMillion/polyagents && PYTHONPATH=. python -c "from agents.application.continuous import start_continuous; from agents.application.crypto import start_crypto; from agents.application.btc_arbitrage import start_btc_arbitrage; print('All imports OK')"`
Expected: `All imports OK`

---

## New Files Summary

| File | Purpose |
|------|---------|
| `agents/connectors/websocket.py` | WebSocket manager (RTDS + Market Channel) |
| `agents/application/budget.py` | Session budget manager with cooldown |
| `agents/application/market_filter.py` | Crypto market detection and price target extraction |
| `agents/application/runner.py` | Async runner with signal handling |
| `agents/application/continuous.py` | Continuous mode strategy |
| `agents/application/crypto.py` | Crypto mode strategy |
| `agents/application/btc_arbitrage.py` | BTC 5-min arbitrage strategy |
| `tests/conftest.py` | Pytest configuration |
| `tests/test_budget.py` | Budget manager tests |
| `tests/test_websocket.py` | WebSocket manager tests |
| `tests/test_market_filter.py` | Market filter tests |
| `tests/test_btc_arbitrage.py` | Arbitrage algorithm tests |
| `tests/test_runner.py` | Async runner tests |

## Modified Files

| File | Change |
|------|--------|
| `scripts/python/cli.py` | Add 3 new CLI commands + imports |
| `agents/application/prompts.py` | Add `crypto_price_analyst` method |
| `.env.example` | Add 12 new env variables |
| `requirements.txt` | Add `pytest-asyncio` |
| `pyproject.toml` | Pytest config (new file) |
