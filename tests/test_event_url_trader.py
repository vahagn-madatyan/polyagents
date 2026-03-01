import pytest

from agents.application.trade import Trader
from agents.utils.objects import SimpleEvent


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


def test_resolve_event_by_slug_returns_direct_match_even_when_restricted() -> None:
    class GammaStub:
        def get_events(self, querystring_params=None):
            return [
                {
                    "id": "42",
                    "ticker": "",
                    "slug": "english-premier-league-winner",
                    "title": "English Premier League Winner",
                    "description": "",
                    "endDate": "",
                    "active": True,
                    "closed": False,
                    "archived": False,
                    "restricted": True,
                    "new": False,
                    "featured": False,
                    "markets": [{"id": "1001"}, {"id": "1002"}],
                }
            ]

    class PolyStub:
        def map_api_to_event(self, event):
            return {
                "id": int(event["id"]),
                "ticker": event.get("ticker") or "",
                "slug": event.get("slug") or "",
                "title": event.get("title") or "",
                "description": event.get("description") or "",
                "active": bool(event.get("active")),
                "closed": bool(event.get("closed")),
                "archived": bool(event.get("archived")),
                "new": bool(event.get("new")),
                "featured": bool(event.get("featured")),
                "restricted": bool(event.get("restricted")),
                "end": event.get("endDate") or "",
                "markets": ",".join([str(x.get("id")) for x in event.get("markets", [])]),
            }

        def get_all_events(self):
            raise AssertionError("full scan should not be used when direct match exists")

    trader = _trader_without_init()
    trader.gamma = GammaStub()
    trader.polymarket = PolyStub()

    event = trader._resolve_event_by_slug("english-premier-league-winner")

    assert event is not None
    assert event.slug == "english-premier-league-winner"
    assert event.restricted is True


def test_resolve_event_by_slug_uses_full_scan_fallback() -> None:
    class GammaStub:
        def get_events(self, querystring_params=None):
            return []

    class PolyStub:
        def map_api_to_event(self, event):
            raise AssertionError("map_api_to_event should not be called with empty direct results")

        def get_all_events(self):
            return [
                SimpleEvent(
                    id=77,
                    ticker="",
                    slug="english-premier-league-winner",
                    title="English Premier League Winner",
                    description="",
                    end="",
                    active=True,
                    closed=False,
                    archived=False,
                    restricted=True,
                    new=False,
                    featured=False,
                    markets="2001,2002",
                )
            ]

    trader = _trader_without_init()
    trader.gamma = GammaStub()
    trader.polymarket = PolyStub()

    event = trader._resolve_event_by_slug("english-premier-league-winner")

    assert event is not None
    assert event.id == 77
