"""Unit tests for SportsDataConnector — mocks all HTTP calls."""

import os
import time
import unittest
from unittest.mock import MagicMock, patch, call

# We test against the connector module (not yet written — RED phase)
from agents.connectors.sports_data import SportsDataConnector


# ---------------------------------------------------------------------------
# Mock response fixtures
# ---------------------------------------------------------------------------


def _api_sports_team_fixture():
    """Realistic API-Sports team statistics response."""
    return {
        "response": [
            {
                "team": {"id": 1, "name": "Kansas City Chiefs"},
                "games": {
                    "played": {"total": 17},
                    "wins": {"total": 13},
                    "loses": {"total": 4},
                    "draws": {"total": 0},
                },
                "form": "WWLWW",
            }
        ]
    }


def _api_sports_h2h_fixture():
    """Realistic API-Sports H2H response."""
    return {
        "response": [
            {
                "date": "2024-01-21",
                "teams": {
                    "home": {"name": "Kansas City Chiefs"},
                    "away": {"name": "Buffalo Bills"},
                },
                "scores": {
                    "home": {"total": 27},
                    "away": {"total": 24},
                },
            },
            {
                "date": "2023-10-16",
                "teams": {
                    "home": {"name": "Buffalo Bills"},
                    "away": {"name": "Kansas City Chiefs"},
                },
                "scores": {
                    "home": {"total": 20},
                    "away": {"total": 17},
                },
            },
        ]
    }


def _odds_api_fixture():
    """Realistic The Odds API response."""
    return [
        {
            "id": "abc123",
            "sport_key": "americanfootball_nfl",
            "home_team": "Kansas City Chiefs",
            "away_team": "Buffalo Bills",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Kansas City Chiefs", "price": 1.65},
                                {"name": "Buffalo Bills", "price": 2.30},
                            ],
                        }
                    ],
                }
            ],
        }
    ]


# ---------------------------------------------------------------------------
# Helper: build a mock httpx response
# ---------------------------------------------------------------------------


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        from httpx import HTTPStatusError, Request, Response

        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


class TestSportsDataConnector(unittest.TestCase):

    def _make_connector(self, extra_env=None):
        env = {
            "SPORTS_DATA_API_KEY": "test-stats-key",
            "SPORTS_ODDS_API_KEY": "test-odds-key",
            "SPORTS_REQUIRE_STATS": "nfl,nba,mlb,nhl",
            "SPORTS_ODDS_DIVERGENCE_THRESHOLD": "0.05",
        }
        if extra_env:
            env.update(extra_env)
        with patch.dict(os.environ, env, clear=False):
            return SportsDataConnector()

    # ------------------------------------------------------------------
    # get_team_stats
    # ------------------------------------------------------------------

    def test_get_team_stats_returns_win_rate_wins_losses_form(self):
        """get_team_stats returns win_rate, wins, losses, recent_form on 200."""
        connector = self._make_connector()
        with patch.object(
            connector._http,
            "get",
            return_value=_mock_response(_api_sports_team_fixture()),
        ) as mock_get:
            result = connector.get_team_stats("nfl", "Kansas City Chiefs")
        self.assertIsNotNone(result)
        self.assertIn("win_rate", result)
        self.assertIn("wins", result)
        self.assertIn("losses", result)
        self.assertIn("recent_form", result)
        self.assertAlmostEqual(result["win_rate"], 13 / 17, places=3)
        self.assertEqual(result["wins"], 13)
        self.assertEqual(result["losses"], 4)

    def test_get_team_stats_returns_none_when_api_key_missing(self):
        """get_team_stats returns None gracefully when SPORTS_DATA_API_KEY is unset."""
        with patch.dict(
            os.environ,
            {"SPORTS_DATA_API_KEY": "", "SPORTS_REQUIRE_STATS": "nfl"},
            clear=False,
        ):
            connector = SportsDataConnector()
        result = connector.get_team_stats("nfl", "Kansas City Chiefs")
        self.assertIsNone(result)

    def test_get_team_stats_returns_none_for_sport_not_in_require_stats(self):
        """Sport not in SPORTS_REQUIRE_STATS returns None without any API call."""
        connector = self._make_connector()
        with patch.object(connector._http, "get") as mock_get:
            result = connector.get_team_stats("esports", "Team Liquid")
        mock_get.assert_not_called()
        self.assertIsNone(result)

    def test_get_team_stats_uses_cache_within_ttl(self):
        """Second call within 24h TTL returns cached value without a second API call."""
        connector = self._make_connector({"SPORTS_STATS_CACHE_TTL_SECONDS": "86400"})
        fixture = _api_sports_team_fixture()
        with patch.object(
            connector._http, "get", return_value=_mock_response(fixture)
        ) as mock_get:
            result1 = connector.get_team_stats("nfl", "Kansas City Chiefs")
            result2 = connector.get_team_stats("nfl", "Kansas City Chiefs")
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(result1, result2)

    # ------------------------------------------------------------------
    # get_head_to_head
    # ------------------------------------------------------------------

    def test_get_head_to_head_returns_list_of_matchup_results(self):
        """get_head_to_head returns a list of past games with date/score/winner."""
        connector = self._make_connector()
        with patch.object(
            connector._http,
            "get",
            return_value=_mock_response(_api_sports_h2h_fixture()),
        ):
            result = connector.get_head_to_head(
                "nfl", "Kansas City Chiefs", "Buffalo Bills"
            )
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        first = result[0]
        self.assertIn("date", first)
        self.assertIn("home_score", first)
        self.assertIn("away_score", first)
        self.assertIn("winner", first)

    def test_get_head_to_head_returns_empty_list_on_error(self):
        """get_head_to_head returns empty list on 404 or network error."""
        connector = self._make_connector()
        with patch.object(
            connector._http, "get", side_effect=Exception("Network error")
        ):
            result = connector.get_head_to_head(
                "nfl", "Kansas City Chiefs", "Buffalo Bills"
            )
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_get_head_to_head_uses_cache(self):
        """Second identical H2H call uses cache without another API hit."""
        connector = self._make_connector()
        with patch.object(
            connector._http,
            "get",
            return_value=_mock_response(_api_sports_h2h_fixture()),
        ) as mock_get:
            connector.get_head_to_head("nfl", "Kansas City Chiefs", "Buffalo Bills")
            connector.get_head_to_head("nfl", "Kansas City Chiefs", "Buffalo Bills")
        self.assertEqual(mock_get.call_count, 1)

    # ------------------------------------------------------------------
    # get_external_odds
    # ------------------------------------------------------------------

    def test_get_external_odds_returns_bookmaker_odds(self):
        """get_external_odds returns home_odds, away_odds, implied probs, and source_bookmaker."""
        connector = self._make_connector()
        with patch.object(
            connector._http, "get", return_value=_mock_response(_odds_api_fixture())
        ):
            result = connector.get_external_odds(
                "nfl", "Kansas City Chiefs", "Buffalo Bills"
            )
        self.assertIsNotNone(result)
        self.assertIn("home_odds", result)
        self.assertIn("away_odds", result)
        self.assertIn("implied_home_prob", result)
        self.assertIn("implied_away_prob", result)
        self.assertIn("source_bookmaker", result)

    def test_get_external_odds_uses_cache_within_ttl(self):
        """Second call within 5min TTL returns cached odds without second API call."""
        connector = self._make_connector({"SPORTS_ODDS_CACHE_TTL_SECONDS": "300"})
        with patch.object(
            connector._http, "get", return_value=_mock_response(_odds_api_fixture())
        ) as mock_get:
            connector.get_external_odds("nfl", "Kansas City Chiefs", "Buffalo Bills")
            connector.get_external_odds("nfl", "Kansas City Chiefs", "Buffalo Bills")
        self.assertEqual(mock_get.call_count, 1)

    # ------------------------------------------------------------------
    # detect_value_bet
    # ------------------------------------------------------------------

    def test_detect_value_bet_returns_true_when_divergence_exceeds_threshold(self):
        """detect_value_bet returns True when |polymarket - implied| > threshold."""
        connector = self._make_connector({"SPORTS_ODDS_DIVERGENCE_THRESHOLD": "0.05"})
        self.assertTrue(connector.detect_value_bet(0.70, 0.60))  # 0.10 > 0.05

    def test_detect_value_bet_returns_false_when_within_threshold(self):
        """detect_value_bet returns False when divergence is within threshold."""
        connector = self._make_connector({"SPORTS_ODDS_DIVERGENCE_THRESHOLD": "0.05"})
        self.assertFalse(connector.detect_value_bet(0.70, 0.68))  # 0.02 < 0.05

    def test_detect_value_bet_uses_configurable_threshold(self):
        """detect_value_bet respects custom SPORTS_ODDS_DIVERGENCE_THRESHOLD."""
        connector = self._make_connector({"SPORTS_ODDS_DIVERGENCE_THRESHOLD": "0.10"})
        # 0.08 divergence: False at 0.10 threshold, True at default 0.05
        self.assertFalse(connector.detect_value_bet(0.70, 0.62))  # 0.08 < 0.10
        connector2 = self._make_connector({"SPORTS_ODDS_DIVERGENCE_THRESHOLD": "0.05"})
        self.assertTrue(connector2.detect_value_bet(0.70, 0.62))  # 0.08 > 0.05

    # ------------------------------------------------------------------
    # _map_league_to_api_sport
    # ------------------------------------------------------------------

    def test_map_league_nfl_returns_american_football(self):
        connector = self._make_connector()
        self.assertEqual(connector._map_league_to_api_sport("nfl"), "american-football")

    def test_map_league_nba_returns_basketball(self):
        connector = self._make_connector()
        self.assertEqual(connector._map_league_to_api_sport("nba"), "basketball")

    def test_map_league_unknown_returns_none(self):
        connector = self._make_connector()
        self.assertIsNone(connector._map_league_to_api_sport("esports"))


if __name__ == "__main__":
    unittest.main()
