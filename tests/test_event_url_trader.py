import pytest

from agents.application.trade import Trader


def _trader_without_init() -> Trader:
    return Trader.__new__(Trader)


@pytest.mark.parametrize(
    "event_url,expected_slug",
    [
        (
            "https://polymarket.com/event/english-premier-league-winner",
            "english-premier-league-winner",
        ),
        (
            "https://polymarket.com/event/english-premier-league-winner?tid=123",
            "english-premier-league-winner",
        ),
        (
            "english-premier-league-winner",
            "english-premier-league-winner",
        ),
    ],
)
def test_extract_event_slug_from_url_success(event_url: str, expected_slug: str) -> None:
    trader = _trader_without_init()
    assert trader._extract_event_slug_from_url(event_url) == expected_slug


def test_extract_event_slug_from_url_invalid_raises() -> None:
    trader = _trader_without_init()
    with pytest.raises(ValueError):
        trader._extract_event_slug_from_url("https://polymarket.com/markets")
