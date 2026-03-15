import pytest

from agents.application.trade import Trader
from agents.utils.objects import CandidateTrade, SimpleEvent


def _trader_without_init() -> Trader:
    return Trader.__new__(Trader)


class _MarketDocStub:
    def __init__(self, metadata, page_content: str = ""):
        self.metadata = metadata
        self.page_content = page_content


def _candidate(market_id: int, gap: float) -> CandidateTrade:
    return CandidateTrade(
        market_id=market_id,
        question=f"Market {market_id}",
        category_bucket="crypto",
        outcomes=["Yes", "No"],
        outcome_prices=[0.5, 0.5],
        token_ids=[str(market_id * 2), str(market_id * 2 + 1)],
        probabilities=[
            {"outcome": "Yes", "likelihood": 0.5 + gap / 2.0},
            {"outcome": "No", "likelihood": 0.5 - gap / 2.0},
        ],
        suggested_outcome="Yes",
        parsed_side="BUY",
        confidence_gap=gap,
        rag_score=float(market_id),
    )


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
def test_extract_event_slug_from_url_success(
    event_url: str, expected_slug: str
) -> None:
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
                "markets": ",".join(
                    [str(x.get("id")) for x in event.get("markets", [])]
                ),
            }

        def get_all_events(self):
            raise AssertionError(
                "full scan should not be used when direct match exists"
            )

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
            raise AssertionError(
                "map_api_to_event should not be called with empty direct results"
            )

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


def test_build_market_news_keywords_falls_back_to_market_metadata_when_target_event_missing() -> (
    None
):
    trader = _trader_without_init()
    market_obj = (
        _MarketDocStub(
            {
                "event_title": "English Premier League Winner",
                "event_slug": "english-premier-league-winner",
                "question": "Will Arsenal win the EPL?",
                "category": "sports",
                "tags": "soccer,premier league",
            }
        ),
        0.12,
    )

    keywords = trader._build_market_news_keywords(market_obj, target_event=None)

    assert "English Premier League Winner" in keywords
    assert "Will Arsenal win the EPL?" in keywords


def test_build_market_news_keywords_prefers_target_event_metadata() -> None:
    trader = _trader_without_init()
    market_obj = (
        _MarketDocStub(
            {
                "event_title": "Stale event title",
                "event_slug": "stale-event-slug",
                "question": "Will Team A win the final?",
                "category": "sports",
                "tags": "football,champions league",
            }
        ),
        0.02,
    )
    target_event = SimpleEvent(
        id=101,
        ticker="",
        slug="uefa-champions-league-winner",
        title="UEFA Champions League Winner",
        description="",
        end="",
        active=True,
        closed=False,
        archived=False,
        restricted=False,
        new=False,
        featured=False,
        markets="1,2",
    )

    keywords = trader._build_market_news_keywords(market_obj, target_event=target_event)

    assert "UEFA Champions League Winner" in keywords


def test_exclude_sports_markets_removes_sports_bucket_entries() -> None:
    trader = _trader_without_init()
    sports_market = (
        _MarketDocStub(
            {
                "id": "1",
                "question": "Will Team A win?",
                "category": "sports",
                "tags": "nba,playoffs",
            }
        ),
        0.1,
    )
    crypto_market = (
        _MarketDocStub(
            {
                "id": "2",
                "question": "Will ETH reach 10k?",
                "category": "crypto",
                "tags": "ethereum",
            }
        ),
        0.2,
    )

    filtered = trader._exclude_sports_markets([sports_market, crypto_market])

    assert len(filtered) == 1
    assert filtered[0][0].metadata["id"] == "2"


def test_apply_minimum_order_constraints_reallocates_after_pruning() -> None:
    class AgentStub:
        @staticmethod
        def allocate_selected_candidates(candidates, usdc_balance):
            if not candidates:
                return candidates
            amount = 3.0 / float(len(candidates))
            for candidate in candidates:
                candidate.allocation_amount_usdc = amount
                candidate.allocation_fraction = amount / max(usdc_balance, 1.0)
            return candidates

    trader = _trader_without_init()
    trader.agent = AgentStub()
    trader.min_order_amount_usdc = 1.0

    candidates = [
        _candidate(1, 0.9),
        _candidate(2, 0.8),
        _candidate(3, 0.7),
        _candidate(4, 0.6),
        _candidate(5, 0.5),
    ]

    adjusted = trader._apply_minimum_order_constraints(candidates, usdc_balance=10.0)

    executable = [
        c for c in adjusted if c.execution_status != "SKIPPED_BELOW_MIN_ORDER"
    ]
    skipped = [c for c in adjusted if c.execution_status == "SKIPPED_BELOW_MIN_ORDER"]

    assert len(executable) == 3
    assert len(skipped) == 2
    for candidate in executable:
        assert candidate.allocation_amount_usdc >= 1.0
    assert skipped[0].allocation_amount_usdc == 0.0
    assert skipped[1].allocation_amount_usdc == 0.0


def test_extract_min_order_error_details_parses_amounts() -> None:
    trader = _trader_without_init()
    details = trader._extract_min_order_error_details(
        "PolyApiException[status_code=400, error_message={'error': 'invalid amount for a marketable BUY order ($0.7), min size: $1'}]"
    )

    assert details is not None
    assert details["attempted_amount_usdc"] == 0.7
    assert details["minimum_amount_usdc"] == 1.0
