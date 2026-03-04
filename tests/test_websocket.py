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
        book = {
            "bids": [{"price": "0.48", "size": "30"}],
            "asks": [{"price": "0.52", "size": "25"}],
        }
        mgr.orderbooks["token123"] = book
        assert mgr.get_orderbook("token123") == book

    def test_price_history_buffer(self):
        mgr = WebSocketManager(history_size=5)
        for i in range(7):
            mgr._record_price("btcusdt", float(97000 + i), timestamp=float(1000 + i))
        history = mgr.get_price_history("btcusdt", n=10)
        assert len(history) == 5
        assert history[-1].price == 97006.0

    def test_get_momentum_insufficient_data(self):
        mgr = WebSocketManager()
        assert mgr.get_momentum("btcusdt", window_secs=60) == 0.0

    def test_get_momentum_calculation(self):
        mgr = WebSocketManager(history_size=300)
        now = time.time()
        mgr._record_price("btcusdt", 100.0, timestamp=now - 30)
        mgr._record_price("btcusdt", 110.0, timestamp=now)
        momentum = mgr.get_momentum("btcusdt", window_secs=60)
        assert abs(momentum - 0.10) < 0.001

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
        msg = json.dumps(
            {
                "topic": "crypto_prices",
                "type": "crypto_prices",
                "timestamp": 1000,
                "payload": {"symbol": "btcusdt", "timestamp": 1000, "value": 97500.0},
            }
        )
        mgr._handle_rtds_message(msg)
        assert mgr.get_price("btcusdt") == 97500.0

    def test_handle_rtds_chainlink_message(self):
        mgr = WebSocketManager()
        msg = json.dumps(
            {
                "topic": "crypto_prices_chainlink",
                "type": "crypto_prices_chainlink",
                "timestamp": 1000,
                "payload": {"symbol": "btc/usd", "timestamp": 1000, "value": 97450.0},
            }
        )
        mgr._handle_rtds_message(msg)
        assert mgr.get_price("btc/usd") == 97450.0

    def test_handle_market_book_message(self):
        mgr = WebSocketManager()
        msg = json.dumps(
            {
                "event_type": "book",
                "asset_id": "token_abc",
                "market": "cond_123",
                "bids": [{"price": "0.48", "size": "30"}],
                "asks": [{"price": "0.52", "size": "25"}],
                "timestamp": "1000",
            }
        )
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
        msg = json.dumps(
            {
                "event_type": "price_change",
                "market": "cond_123",
                "price_changes": [
                    {
                        "asset_id": "token_abc",
                        "price": "0.50",
                        "size": "200",
                        "side": "BUY",
                        "best_bid": "0.50",
                        "best_ask": "0.52",
                    }
                ],
                "timestamp": "1001",
            }
        )
        mgr._handle_market_message(msg)
        book = mgr.get_orderbook("token_abc")
        assert book["best_bid"] == "0.50"

    def test_dual_feed_validation(self):
        mgr = WebSocketManager()
        mgr.prices["btcusdt"] = 97500.0
        mgr.prices["btc/usd"] = 97400.0
        valid, avg = mgr.validate_dual_feed("btcusdt", "btc/usd", tolerance=0.002)
        assert valid is True
        assert abs(avg - 97450.0) < 0.1

    def test_dual_feed_validation_diverged(self):
        mgr = WebSocketManager()
        mgr.prices["btcusdt"] = 97500.0
        mgr.prices["btc/usd"] = 90000.0
        valid, avg = mgr.validate_dual_feed("btcusdt", "btc/usd", tolerance=0.002)
        assert valid is False

    def test_dual_feed_validation_missing(self):
        mgr = WebSocketManager()
        mgr.prices["btcusdt"] = 97500.0
        valid, avg = mgr.validate_dual_feed("btcusdt", "btc/usd", tolerance=0.002)
        assert valid is False
        assert avg == 0.0
