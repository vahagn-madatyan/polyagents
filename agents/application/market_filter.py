import re
from dataclasses import dataclass
from typing import Optional


SYMBOL_MAP = {
    "BTC": {
        "binance": "btcusdt",
        "chainlink": "btc/usd",
        "aliases": ["bitcoin", "btc"],
    },
    "ETH": {
        "binance": "ethusdt",
        "chainlink": "eth/usd",
        "aliases": ["ethereum", "eth", "ether"],
    },
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
    has_btc = any(alias in lowered for alias in SYMBOL_MAP["BTC"]["aliases"])
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
