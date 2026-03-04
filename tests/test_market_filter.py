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
        assert (
            is_crypto_price_market("Will ETH be above $4,000 by end of March?") is True
        )

    def test_solana_question(self):
        assert is_crypto_price_market("Will SOL reach $200?") is True

    def test_non_crypto_question(self):
        assert (
            is_crypto_price_market("Will the Lakers win the NBA championship?") is False
        )

    def test_crypto_regulation_not_price(self):
        assert (
            is_crypto_price_market("Will Congress pass crypto regulation in 2026?")
            is False
        )

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
        info = extract_crypto_price_target(
            "Will ETH be below $3,500 by end of February?"
        )
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
        assert (
            is_5min_btc_market("Will BTC be above $97,500 at 2:05 PM? (5 minutes)")
            is True
        )

    def test_five_minute_hyphenated(self):
        assert is_5min_btc_market("BTC 5-minute interval: above $98,000?") is True

    def test_hourly_market(self):
        assert is_5min_btc_market("Will BTC be above $97,500 in 1 hour?") is False

    def test_non_btc_5min(self):
        assert (
            is_5min_btc_market("Will ETH be above $4,000 at 2:05 PM? (5 minutes)")
            is False
        )


class TestSymbolMap:
    def test_btc_symbols(self):
        assert "btcusdt" in SYMBOL_MAP["BTC"]["binance"]
        assert "btc/usd" in SYMBOL_MAP["BTC"]["chainlink"]

    def test_eth_symbols(self):
        assert "ethusdt" in SYMBOL_MAP["ETH"]["binance"]


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
