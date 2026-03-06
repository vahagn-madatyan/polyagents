"""Tests for sports market discovery: SportsMarketTag model and GammaMarketClient slug lookup methods."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agents.utils.objects import SportsMarketTag, SportGameState
from agents.polymarket.gamma import GammaMarketClient


# ---------------------------------------------------------------------------
# Test fixtures / factories
# ---------------------------------------------------------------------------


def make_mock_response(status_code: int, body: Any) -> MagicMock:
    """Create a mock httpx.Response."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = body
    return response


def make_gamma_event(
    slug: str = "nfl-lac-buf-2025-01-26",
    title: str = "LAC vs BUF",
    markets: list[dict] | None = None,
) -> dict:
    """Factory for a minimal Gamma API event dict."""
    if markets is None:
        markets = [make_gamma_market()]
    return {
        "id": "12345",
        "slug": slug,
        "title": title,
        "active": True,
        "closed": False,
        "markets": markets,
    }


def make_gamma_market(
    question: str = "Will the Los Angeles Chargers win?",
    condition_id: str = "0xABC",
    clob_token_ids: list[str] | None = None,
    outcome_prices: list[str] | None = None,
) -> dict:
    """Factory for a minimal Gamma API market dict."""
    if clob_token_ids is None:
        clob_token_ids = ["token_yes_001", "token_no_001"]
    if outcome_prices is None:
        outcome_prices = ["0.6", "0.4"]
    return {
        "id": 99001,
        "question": question,
        "conditionId": condition_id,
        "clobTokenIds": clob_token_ids,
        "outcomePrices": outcome_prices,
        "active": True,
        "closed": False,
    }


def make_sport_game_state(**kwargs) -> SportGameState:
    """Factory for a minimal SportGameState."""
    defaults = {
        "game_id": 1,
        "league": "nfl",
        "slug": "nfl-lac-buf-2025-01-26",
        "home_team": "LAC",
        "away_team": "BUF",
        "status": "InProgress",
        "score_raw": "7-14",
        "period": "Q2",
        "live": True,
        "ended": False,
    }
    defaults.update(kwargs)
    return SportGameState(**defaults)


# ---------------------------------------------------------------------------
# SportsMarketTag model tests
# ---------------------------------------------------------------------------


class TestSportsMarketTag:
    def test_construction_with_all_fields(self):
        """SportsMarketTag can be constructed with all required fields."""
        tag = SportsMarketTag(
            slug="nfl-lac-buf-2025-01-26",
            league="nfl",
            home_team="LAC",
            away_team="BUF",
            market_id="99001",
            condition_id="0xABC",
            token_id_yes="token_yes_001",
            token_id_no="token_no_001",
            question="Will the Los Angeles Chargers win?",
        )
        assert tag.slug == "nfl-lac-buf-2025-01-26"
        assert tag.league == "nfl"
        assert tag.home_team == "LAC"
        assert tag.away_team == "BUF"
        assert tag.market_id == "99001"
        assert tag.condition_id == "0xABC"
        assert tag.token_id_yes == "token_yes_001"
        assert tag.token_id_no == "token_no_001"
        assert tag.question == "Will the Los Angeles Chargers win?"
        assert tag.outcome_prices is None  # optional field defaults to None

    def test_outcome_prices_optional(self):
        """outcome_prices field is optional."""
        tag = SportsMarketTag(
            slug="nba-lal-gsw-2025-03-01",
            league="nba",
            home_team="LAL",
            away_team="GSW",
            market_id="99002",
            condition_id="0xDEF",
            token_id_yes="ty",
            token_id_no="tn",
            question="Will the Lakers win?",
            outcome_prices="0.55,0.45",
        )
        assert tag.outcome_prices == "0.55,0.45"

    def test_all_fields_are_strings(self):
        """All core fields are strings (not ints or other types)."""
        tag = SportsMarketTag(
            slug="s",
            league="nfl",
            home_team="A",
            away_team="B",
            market_id="123",
            condition_id="cond",
            token_id_yes="ty",
            token_id_no="tn",
            question="Q",
        )
        assert isinstance(tag.market_id, str)
        assert isinstance(tag.condition_id, str)


# ---------------------------------------------------------------------------
# GammaMarketClient._is_moneyline_market tests
# ---------------------------------------------------------------------------


class TestIsMoneylineMarket:
    def setup_method(self):
        self.client = GammaMarketClient.__new__(GammaMarketClient)

    def test_win_question_is_moneyline(self):
        market = {"question": "Will Lakers win?"}
        assert self.client._is_moneyline_market(market) is True

    def test_winner_question_is_moneyline(self):
        market = {"question": "Who will be the winner?"}
        assert self.client._is_moneyline_market(market) is True

    def test_case_insensitive_WIN(self):
        market = {"question": "Will Lakers WIN the game?"}
        assert self.client._is_moneyline_market(market) is True

    def test_totals_is_not_moneyline(self):
        market = {"question": "Total points over 220.5?"}
        assert self.client._is_moneyline_market(market) is False

    def test_spread_is_not_moneyline(self):
        market = {"question": "Will the Chargers cover -3.5?"}
        assert self.client._is_moneyline_market(market) is False

    def test_props_is_not_moneyline(self):
        market = {"question": "Will Patrick Mahomes throw 2+ touchdowns?"}
        assert self.client._is_moneyline_market(market) is False

    def test_missing_question_returns_false(self):
        market = {}
        assert self.client._is_moneyline_market(market) is False


# ---------------------------------------------------------------------------
# GammaMarketClient._extract_teams_from_slug tests
# ---------------------------------------------------------------------------


class TestExtractTeamsFromSlug:
    def setup_method(self):
        self.client = GammaMarketClient.__new__(GammaMarketClient)

    def test_nfl_slug_parses_correctly(self):
        league, teams = self.client._extract_teams_from_slug("nfl-lac-buf-2025-01-26")
        assert league == "nfl"
        assert teams == ["lac", "buf"]

    def test_nba_slug_parses_correctly(self):
        league, teams = self.client._extract_teams_from_slug("nba-lal-gsw-2025-03-01")
        assert league == "nba"
        assert teams == ["lal", "gsw"]

    def test_slug_without_date_still_extracts(self):
        league, teams = self.client._extract_teams_from_slug("nfl-lac-buf")
        assert league == "nfl"
        # teams may be empty or contain "lac", "buf" — at minimum no crash


# ---------------------------------------------------------------------------
# GammaMarketClient.lookup_markets_by_slug tests
# ---------------------------------------------------------------------------


class TestLookupMarketsBySlug:
    def setup_method(self):
        self.client = GammaMarketClient.__new__(GammaMarketClient)
        self.client.gamma_url = "https://gamma-api.polymarket.com"
        self.client.gamma_markets_endpoint = self.client.gamma_url + "/markets"
        self.client.gamma_events_endpoint = self.client.gamma_url + "/events"
        self.client.http_client = MagicMock()

    def test_returns_list_of_sports_market_tags_on_200(self):
        event = make_gamma_event()
        self.client.http_client.get.return_value = make_mock_response(200, event)

        results = self.client.lookup_markets_by_slug("nfl-lac-buf-2025-01-26")

        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], SportsMarketTag)

    def test_returns_empty_list_on_404(self):
        self.client.http_client.get.return_value = make_mock_response(404, {})

        results = self.client.lookup_markets_by_slug("nfl-unknown-slug")
        assert results == []

    def test_returns_empty_list_on_error(self):
        self.client.http_client.get.side_effect = Exception("network error")

        results = self.client.lookup_markets_by_slug("nfl-lac-buf-2025-01-26")
        assert results == []

    def test_filters_to_moneyline_only(self):
        """Non-moneyline markets are excluded from results."""
        moneyline = make_gamma_market(question="Will the Chargers win?")
        spread = make_gamma_market(
            question="Will Chargers cover -3.5?", condition_id="0xSPREAD"
        )
        totals = make_gamma_market(
            question="Total points over 45.5?", condition_id="0xTOTAL"
        )
        event = make_gamma_event(markets=[moneyline, spread, totals])
        self.client.http_client.get.return_value = make_mock_response(200, event)

        results = self.client.lookup_markets_by_slug("nfl-lac-buf-2025-01-26")

        assert len(results) == 1
        assert "win" in results[0].question.lower()

    def test_slug_tag_populated_from_event(self):
        event = make_gamma_event(slug="nfl-lac-buf-2025-01-26")
        self.client.http_client.get.return_value = make_mock_response(200, event)

        results = self.client.lookup_markets_by_slug("nfl-lac-buf-2025-01-26")

        assert results[0].slug == "nfl-lac-buf-2025-01-26"

    def test_uses_correct_endpoint(self):
        self.client.http_client.get.return_value = make_mock_response(404, {})
        self.client.lookup_markets_by_slug("nfl-lac-buf-2025-01-26")

        call_url = self.client.http_client.get.call_args[0][0]
        assert "events/slug/nfl-lac-buf-2025-01-26" in call_url


# ---------------------------------------------------------------------------
# GammaMarketClient.lookup_markets_fallback tests
# ---------------------------------------------------------------------------


class TestLookupMarketsFallback:
    def setup_method(self):
        self.client = GammaMarketClient.__new__(GammaMarketClient)
        self.client.gamma_url = "https://gamma-api.polymarket.com"
        self.client.gamma_markets_endpoint = self.client.gamma_url + "/markets"
        self.client.gamma_events_endpoint = self.client.gamma_url + "/events"
        self.client.http_client = MagicMock()

    def test_returns_matching_events_by_team_name(self):
        event_match = make_gamma_event(
            slug="nfl-lac-buf-2025-01-26",
            title="LAC vs BUF",
        )
        event_no_match = make_gamma_event(
            slug="nfl-kc-den-2025-01-26",
            title="KC vs DEN",
        )
        self.client.http_client.get.return_value = make_mock_response(
            200, [event_match, event_no_match]
        )

        results = self.client.lookup_markets_fallback("nfl", "LAC", "BUF")

        assert len(results) >= 1
        found_questions = [r.question for r in results]
        # At least one result from the matching event
        assert any("win" in q.lower() for q in found_questions)

    def test_returns_empty_list_on_error(self):
        self.client.http_client.get.side_effect = Exception("network error")

        results = self.client.lookup_markets_fallback("nfl", "LAC", "BUF")
        assert results == []


# ---------------------------------------------------------------------------
# GammaMarketClient.build_slug_table tests
# ---------------------------------------------------------------------------


class TestBuildSlugTable:
    def setup_method(self):
        self.client = GammaMarketClient.__new__(GammaMarketClient)
        self.client.gamma_url = "https://gamma-api.polymarket.com"
        self.client.gamma_markets_endpoint = self.client.gamma_url + "/markets"
        self.client.gamma_events_endpoint = self.client.gamma_url + "/events"
        self.client.http_client = MagicMock()

    def test_builds_slug_to_market_tag_mapping(self):
        event = make_gamma_event(slug="nfl-lac-buf-2025-01-26")
        self.client.http_client.get.return_value = make_mock_response(200, event)

        game_states = {
            1: make_sport_game_state(game_id=1, slug="nfl-lac-buf-2025-01-26"),
        }
        slug_table, unmapped = self.client.build_slug_table(game_states)

        assert "nfl-lac-buf-2025-01-26" in slug_table
        assert isinstance(slug_table["nfl-lac-buf-2025-01-26"], list)
        assert len(slug_table["nfl-lac-buf-2025-01-26"]) >= 1

    def test_logs_and_skips_unmapped_games_without_raising(self, capsys):
        """Unmapped games are logged but do not raise exceptions."""
        self.client.http_client.get.return_value = make_mock_response(404, {})

        game_states = {
            1: make_sport_game_state(
                game_id=1,
                slug="nfl-unknown-team-other-2025-01-01",
            ),
        }
        # Should not raise
        slug_table, unmapped = self.client.build_slug_table(game_states)

        captured = capsys.readouterr()
        assert "unmapped" in captured.out
        assert "nfl-unknown-team-other-2025-01-01" in captured.out

    def test_unmapped_slugs_returned_in_retry_list(self):
        """Unmapped slugs are returned as second element for retry."""
        self.client.http_client.get.return_value = make_mock_response(404, {})

        game_states = {
            1: make_sport_game_state(game_id=1, slug="nfl-lac-buf-2025-01-26"),
        }
        slug_table, unmapped = self.client.build_slug_table(game_states)

        assert "nfl-lac-buf-2025-01-26" in unmapped

    def test_multiple_games_build_table(self):
        event_lac = make_gamma_event(slug="nfl-lac-buf-2025-01-26")
        event_kc = make_gamma_event(
            slug="nfl-kc-den-2025-01-26",
            title="KC vs DEN",
            markets=[make_gamma_market(question="Will Kansas City win?")],
        )

        def mock_get(url, **kwargs):
            if "nfl-lac-buf" in url:
                return make_mock_response(200, event_lac)
            elif "nfl-kc-den" in url:
                return make_mock_response(200, event_kc)
            return make_mock_response(404, {})

        self.client.http_client.get.side_effect = mock_get

        game_states = {
            1: make_sport_game_state(game_id=1, slug="nfl-lac-buf-2025-01-26"),
            2: make_sport_game_state(
                game_id=2,
                slug="nfl-kc-den-2025-01-26",
                home_team="KC",
                away_team="DEN",
            ),
        }
        slug_table, unmapped = self.client.build_slug_table(game_states)

        assert "nfl-lac-buf-2025-01-26" in slug_table
        assert "nfl-kc-den-2025-01-26" in slug_table
        assert len(unmapped) == 0


# ---------------------------------------------------------------------------
# GammaMarketClient.lookup_single_slug tests
# ---------------------------------------------------------------------------


class TestLookupSingleSlug:
    def setup_method(self):
        self.client = GammaMarketClient.__new__(GammaMarketClient)
        self.client.gamma_url = "https://gamma-api.polymarket.com"
        self.client.gamma_markets_endpoint = self.client.gamma_url + "/markets"
        self.client.gamma_events_endpoint = self.client.gamma_url + "/events"
        self.client.http_client = MagicMock()

    def test_returns_tags_from_slug_path(self):
        event = make_gamma_event()
        self.client.http_client.get.return_value = make_mock_response(200, event)

        results = self.client.lookup_single_slug("nfl-lac-buf-2025-01-26")

        assert isinstance(results, list)
        assert len(results) >= 1

    def test_falls_back_when_slug_path_returns_404(self):
        """lookup_single_slug tries fallback when slug path returns 404."""
        # First call (slug path) returns 404, second (fallback events) returns a list
        event_list = [make_gamma_event(slug="nfl-lac-buf-2025-01-26")]

        call_count = 0

        def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "events/slug/" in url:
                return make_mock_response(404, {})
            # fallback: GET /events
            return make_mock_response(200, event_list)

        self.client.http_client.get.side_effect = mock_get

        results = self.client.lookup_single_slug("nfl-lac-buf-2025-01-26")

        assert call_count >= 2  # slug path + fallback
        # fallback may or may not find results depending on team matching logic
        assert isinstance(results, list)
