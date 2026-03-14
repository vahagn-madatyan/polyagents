"""SportsDataConnector — integrates API-Sports and The Odds API for external data."""

from __future__ import annotations

import os
from typing import Optional, TYPE_CHECKING

import httpx
from cachetools import TTLCache
from tenacity import retry, stop_after_attempt, wait_exponential

if TYPE_CHECKING:
    from agents.utils.objects import SportGameState

from agents.utils.env import _env_float, _env_int


def _env_str(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# ---------------------------------------------------------------------------
# League → API-Sports sport identifier mapping
# ---------------------------------------------------------------------------

_LEAGUE_TO_API_SPORT: dict[str, str] = {
    "nfl": "american-football",
    "cfb": "american-football",
    "nba": "basketball",
    "cbb": "basketball",
    "mlb": "baseball",
    "nhl": "hockey",
    "soccer": "football",
    "mls": "football",
    "epl": "football",
    "ucl": "football",
}

# The Odds API sport key mapping
_LEAGUE_TO_ODDS_SPORT: dict[str, str] = {
    "nfl": "americanfootball_nfl",
    "cfb": "americanfootball_ncaaf",
    "nba": "basketball_nba",
    "cbb": "basketball_ncaab",
    "mlb": "baseball_mlb",
    "nhl": "icehockey_nhl",
    "soccer": "soccer_epl",
    "mls": "soccer_usa_mls",
    "epl": "soccer_epl",
}

# API-Sports base URLs per sport
_API_SPORTS_BASE = "https://v1.{sport}.api-sports.io"
_ODDS_API_BASE = "https://api.the-odds-api.com/v4"


class SportsDataConnector:
    """Fetches team stats, H2H records, and bookmaker odds with two-tier TTL caching."""

    def __init__(self) -> None:
        # API keys
        self._stats_api_key = _env_str("SPORTS_DATA_API_KEY")
        self._odds_api_key = _env_str("SPORTS_ODDS_API_KEY")

        # Per-sport stats requirement list
        require_raw = _env_str("SPORTS_REQUIRE_STATS", "nfl,nba,mlb,nhl")
        self._require_stats: set[str] = {
            s.strip().lower() for s in require_raw.split(",") if s.strip()
        }

        # Cache TTLs
        stats_ttl = _env_int("SPORTS_STATS_CACHE_TTL_SECONDS", 86400)
        odds_ttl = _env_int("SPORTS_ODDS_CACHE_TTL_SECONDS", 300)

        # Value-bet divergence threshold
        self._divergence_threshold = _env_float(
            "SPORTS_ODDS_DIVERGENCE_THRESHOLD", 0.05
        )

        # Two-tier caches: stats (24h default) and odds (5min default)
        self._stats_cache: TTLCache = TTLCache(maxsize=500, ttl=stats_ttl)
        self._odds_cache: TTLCache = TTLCache(maxsize=200, ttl=odds_ttl)

        # Shared HTTP client with 10s timeout
        self._http = httpx.Client(timeout=10.0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _map_league_to_api_sport(self, league: str) -> Optional[str]:
        """Map Polymarket league string to API-Sports sport identifier."""
        return _LEAGUE_TO_API_SPORT.get(league.lower())

    def _map_league_to_odds_sport(self, league: str) -> Optional[str]:
        """Map Polymarket league string to The Odds API sport key."""
        return _LEAGUE_TO_ODDS_SPORT.get(league.lower())

    def _requires_stats(self, league: str) -> bool:
        """Return True if this league requires external stats before trading."""
        return league.lower() in self._require_stats

    # ------------------------------------------------------------------
    # Team Statistics (API-Sports)
    # ------------------------------------------------------------------

    def get_team_stats(self, league: str, team_name: str) -> Optional[dict]:
        """Fetch current-season stats for a team. Returns None if stats not required or unavailable."""
        if not self._requires_stats(league):
            return None
        if not self._stats_api_key:
            print(
                f"[sports_data] event=stats_skip reason=no_api_key league={league} team={team_name}"
            )
            return None

        cache_key = f"stats:{league}:{team_name.lower()}"
        if cache_key in self._stats_cache:
            return self._stats_cache[cache_key]

        try:
            result = self._fetch_team_stats(league, team_name)
            if result is not None:
                self._stats_cache[cache_key] = result
            return result
        except Exception as exc:
            print(
                f"[sports_data] event=stats_error league={league} team={team_name} error={exc}"
            )
            return None

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True
    )
    def _fetch_team_stats(self, league: str, team_name: str) -> Optional[dict]:
        sport = self._map_league_to_api_sport(league)
        if not sport:
            return None
        base = _API_SPORTS_BASE.format(sport=sport)
        url = f"{base}/teams/statistics"
        headers = {"x-apisports-key": self._stats_api_key}
        resp = self._http.get(url, headers=headers, params={"search": team_name})
        data = resp.json()
        responses = data.get("response", [])
        if not responses:
            return None
        entry = responses[0]
        games = entry.get("games", {})
        played = games.get("played", {}).get("total", 0)
        wins = games.get("wins", {}).get("total", 0)
        losses = games.get("loses", {}).get("total", 0)
        draws = games.get("draws", {}).get("total", 0)
        win_rate = wins / played if played else 0.0
        form = entry.get("form", "")
        print(
            f"[sports_data] event=stats_fetch league={league} team={team_name} win_rate={win_rate:.3f}"
        )
        return {
            "win_rate": win_rate,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "recent_form": form[-5:] if form else "",
        }

    # ------------------------------------------------------------------
    # Head-to-Head Records (API-Sports)
    # ------------------------------------------------------------------

    def get_head_to_head(
        self, league: str, home_team: str, away_team: str
    ) -> list[dict]:
        """Fetch historical H2H matchup results between two teams."""
        cache_key = f"h2h:{league}:{home_team.lower()}:{away_team.lower()}"
        if cache_key in self._stats_cache:
            return self._stats_cache[cache_key]

        try:
            result = self._fetch_h2h(league, home_team, away_team)
            self._stats_cache[cache_key] = result
            return result
        except Exception as exc:
            print(
                f"[sports_data] event=h2h_error league={league} home={home_team} away={away_team} error={exc}"
            )
            return []

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True
    )
    def _fetch_h2h(self, league: str, home_team: str, away_team: str) -> list[dict]:
        if not self._stats_api_key:
            return []
        sport = self._map_league_to_api_sport(league)
        if not sport:
            return []
        base = _API_SPORTS_BASE.format(sport=sport)
        url = f"{base}/games/h2h"
        headers = {"x-apisports-key": self._stats_api_key}
        resp = self._http.get(
            url, headers=headers, params={"h2h": f"{home_team}-{away_team}"}
        )
        data = resp.json()
        games = data.get("response", [])
        results = []
        for game in games:
            teams = game.get("teams", {})
            scores = game.get("scores", {})
            home_name = teams.get("home", {}).get("name", "")
            away_name = teams.get("away", {}).get("name", "")
            home_score = scores.get("home", {}).get("total")
            away_score = scores.get("away", {}).get("total")
            if home_score is not None and away_score is not None:
                if home_score > away_score:
                    winner = home_name
                elif away_score > home_score:
                    winner = away_name
                else:
                    winner = "draw"
            else:
                winner = "unknown"
            results.append(
                {
                    "date": game.get("date", ""),
                    "home_team": home_name,
                    "away_team": away_name,
                    "home_score": home_score,
                    "away_score": away_score,
                    "winner": winner,
                }
            )
        print(
            f"[sports_data] event=h2h_fetch league={league} home={home_team} away={away_team} count={len(results)}"
        )
        return results

    # ------------------------------------------------------------------
    # External Odds (The Odds API)
    # ------------------------------------------------------------------

    def get_external_odds(
        self, league: str, home_team: str, away_team: str
    ) -> Optional[dict]:
        """Fetch bookmaker odds for a game. Returns implied probabilities for value-bet detection."""
        cache_key = f"odds:{league}:{home_team.lower()}:{away_team.lower()}"
        if cache_key in self._odds_cache:
            return self._odds_cache[cache_key]

        try:
            result = self._fetch_odds(league, home_team, away_team)
            if result is not None:
                self._odds_cache[cache_key] = result
            return result
        except Exception as exc:
            print(
                f"[sports_data] event=odds_error league={league} home={home_team} away={away_team} error={exc}"
            )
            return None

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True
    )
    def _fetch_odds(
        self, league: str, home_team: str, away_team: str
    ) -> Optional[dict]:
        if not self._odds_api_key:
            return None
        sport_key = self._map_league_to_odds_sport(league)
        if not sport_key:
            return None
        url = f"{_ODDS_API_BASE}/sports/{sport_key}/odds"
        resp = self._http.get(
            url,
            params={"apiKey": self._odds_api_key, "regions": "us", "markets": "h2h"},
        )
        events = resp.json()
        # Find the event matching our teams (case-insensitive partial match)
        home_lower = home_team.lower()
        away_lower = away_team.lower()
        for event in events:
            ev_home = event.get("home_team", "").lower()
            ev_away = event.get("away_team", "").lower()
            if home_lower in ev_home or ev_home in home_lower:
                if away_lower in ev_away or ev_away in away_lower:
                    return self._parse_odds_event(event)
        return None

    def _parse_odds_event(self, event: dict) -> Optional[dict]:
        """Extract h2h odds from the first bookmaker offering them."""
        bookmakers = event.get("bookmakers", [])
        for bm in bookmakers:
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                outcomes = market.get("outcomes", [])
                home_team = event.get("home_team", "")
                away_team = event.get("away_team", "")
                home_price = away_price = draw_price = None
                for outcome in outcomes:
                    name = outcome.get("name", "")
                    price = outcome.get("price", 1.0)
                    name_lower = name.lower()
                    home_lower = home_team.lower()
                    away_lower = away_team.lower()
                    if name_lower in home_lower or home_lower in name_lower:
                        home_price = price
                    elif name_lower in away_lower or away_lower in name_lower:
                        away_price = price
                    else:
                        draw_price = price
                if home_price and away_price:
                    # Implied probability = 1 / decimal_odds
                    implied_home = 1.0 / home_price
                    implied_away = 1.0 / away_price
                    return {
                        "home_odds": home_price,
                        "away_odds": away_price,
                        "draw_odds": draw_price,
                        "implied_home_prob": implied_home,
                        "implied_away_prob": implied_away,
                        "source_bookmaker": bm.get("title", bm.get("key", "unknown")),
                    }
        return None

    # ------------------------------------------------------------------
    # Value-Bet Detection
    # ------------------------------------------------------------------

    def detect_value_bet(self, polymarket_price: float, implied_prob: float) -> bool:
        """Return True when |polymarket_price - implied_prob| exceeds configured threshold."""
        return abs(polymarket_price - implied_prob) > self._divergence_threshold

    # ------------------------------------------------------------------
    # Convenience: Full Game Context for LLM Prompts
    # ------------------------------------------------------------------

    def get_game_context(self, game_state: "SportGameState") -> dict:
        """Combine team stats, H2H, and odds into one dict for LLM prompt injection.

        Returns partial data if some sources fail — never raises.
        """
        league = getattr(game_state, "league", "")
        home_team = getattr(game_state, "home_team", "")
        away_team = getattr(game_state, "away_team", "")

        context: dict = {
            "league": league,
            "home_team": home_team,
            "away_team": away_team,
        }

        # Team stats (may be None if league not in SPORTS_REQUIRE_STATS or API error)
        context["home_stats"] = self.get_team_stats(league, home_team)
        context["away_stats"] = self.get_team_stats(league, away_team)

        # H2H history
        context["head_to_head"] = self.get_head_to_head(league, home_team, away_team)

        # External odds
        context["external_odds"] = self.get_external_odds(league, home_team, away_team)

        return context
