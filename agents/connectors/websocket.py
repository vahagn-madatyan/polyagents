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
                    subscribe_msg = json.dumps(
                        {
                            "action": "subscribe",
                            "subscriptions": [
                                {"topic": "crypto_prices", "type": "crypto_prices"},
                                {
                                    "topic": "crypto_prices_chainlink",
                                    "type": "crypto_prices_chainlink",
                                },
                            ],
                        }
                    )
                    await ws.send(subscribe_msg)
                    ping_task = asyncio.create_task(
                        self._ping_loop(ws, RTDS_PING_INTERVAL)
                    )
                    try:
                        async for message in ws:
                            if message == "PONG":
                                continue
                            self._handle_rtds_message(str(message))
                    finally:
                        ping_task.cancel()
            except Exception as err:
                logger.warning(
                    "[ws] rtds disconnected error=%s reconnecting in %.1fs", err, delay
                )
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
                    init_msg = json.dumps(
                        {
                            "assets_ids": token_ids,
                            "type": "market",
                            "initial_dump": True,
                            "level": 2,
                            "custom_feature_enabled": False,
                        }
                    )
                    await ws.send(init_msg)
                    ping_task = asyncio.create_task(
                        self._ping_loop(ws, MARKET_PING_INTERVAL)
                    )
                    try:
                        async for message in ws:
                            if message == "PONG":
                                continue
                            self._handle_market_message(str(message))
                    finally:
                        ping_task.cancel()
            except Exception as err:
                logger.warning(
                    "[ws] market disconnected error=%s reconnecting in %.1fs",
                    err,
                    delay,
                )
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
            msg = json.dumps(
                {
                    "operation": "subscribe",
                    "assets_ids": token_ids,
                    "level": 2,
                    "custom_feature_enabled": False,
                }
            )
            try:
                await self._market_ws.send(msg)
                logger.info("[ws] subscribed tokens=%s", len(token_ids))
            except Exception as err:
                logger.warning("[ws] subscribe_failed error=%s", err)

    async def unsubscribe(self, token_ids: list[str]) -> None:
        if self._market_ws is not None:
            msg = json.dumps(
                {
                    "operation": "unsubscribe",
                    "assets_ids": token_ids,
                }
            )
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
