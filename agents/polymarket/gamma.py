import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from agents.utils.objects import (
    Market,
    PolymarketEvent,
    ClobReward,
    Tag,
    SportsMarketTag,
)


class GammaMarketClient:
    def __init__(self):
        self.gamma_url = "https://gamma-api.polymarket.com"
        self.gamma_markets_endpoint = self.gamma_url + "/markets"
        self.gamma_events_endpoint = self.gamma_url + "/events"
        self.logger = logging.getLogger(self.__class__.__name__)

        timeout_seconds = float(os.getenv("GAMMA_HTTP_TIMEOUT_SECONDS", "8"))
        max_connections = int(os.getenv("GAMMA_HTTP_MAX_CONNECTIONS", "100"))
        max_keepalive_connections = int(
            os.getenv("GAMMA_HTTP_MAX_KEEPALIVE_CONNECTIONS", "40")
        )
        self.market_fetch_concurrency = max(
            1, int(os.getenv("GAMMA_MARKET_FETCH_CONCURRENCY", "24"))
        )
        self.log_market_detail_url = str(
            os.getenv("GAMMA_LOG_MARKET_DETAIL_URL", "false")
        ).strip().lower() in ("1", "true", "yes", "on")

        timeout = httpx.Timeout(
            timeout_seconds,
            connect=min(5.0, timeout_seconds),
            read=timeout_seconds,
            write=5.0,
            pool=5.0,
        )
        limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            keepalive_expiry=30.0,
        )
        self.http_client = httpx.Client(
            timeout=timeout,
            limits=limits,
            headers={"Accept": "application/json"},
        )

    def parse_pydantic_market(self, market_object: dict) -> Market:
        try:
            if "clobRewards" in market_object:
                clob_rewards: list[ClobReward] = []
                for clob_rewards_obj in market_object["clobRewards"]:
                    clob_rewards.append(ClobReward(**clob_rewards_obj))
                market_object["clobRewards"] = clob_rewards

            if "events" in market_object:
                events: list[PolymarketEvent] = []
                for market_event_obj in market_object["events"]:
                    events.append(self.parse_nested_event(market_event_obj))
                market_object["events"] = events

            # These two fields below are returned as stringified lists from the api
            if "outcomePrices" in market_object:
                market_object["outcomePrices"] = json.loads(
                    market_object["outcomePrices"]
                )
            if "clobTokenIds" in market_object:
                market_object["clobTokenIds"] = json.loads(
                    market_object["clobTokenIds"]
                )

            return Market(**market_object)
        except Exception as err:
            print(f"[parse_market] Caught exception: {err}")
            print("exception while handling object:", market_object)

    # Event parser for events nested under a markets api response
    def parse_nested_event(self, event_object: dict) -> PolymarketEvent:
        print("[parse_nested_event] called with:", event_object)
        try:
            if "tags" in event_object:
                print("tags here", event_object["tags"])
                tags: list[Tag] = []
                for tag in event_object["tags"]:
                    tags.append(Tag(**tag))
                event_object["tags"] = tags

            return PolymarketEvent(**event_object)
        except Exception as err:
            print(f"[parse_event] Caught exception: {err}")
            print("\n", event_object)

    def parse_pydantic_event(self, event_object: dict) -> PolymarketEvent:
        try:
            if "tags" in event_object:
                print("tags here", event_object["tags"])
                tags: list[Tag] = []
                for tag in event_object["tags"]:
                    tags.append(Tag(**tag))
                event_object["tags"] = tags
            return PolymarketEvent(**event_object)
        except Exception as err:
            print(f"[parse_event] Caught exception: {err}")

    def get_markets(
        self, querystring_params=None, parse_pydantic=False, local_file_path=None
    ) -> "list[Market]":
        if parse_pydantic and local_file_path is not None:
            raise Exception(
                'Cannot use "parse_pydantic" and "local_file" params simultaneously.'
            )

        params = querystring_params or {}
        response = self.http_client.get(self.gamma_markets_endpoint, params=params)
        if response.status_code != 200:
            print(f"Error response returned from api: HTTP {response.status_code}")
            raise Exception()

        data = response.json()
        if local_file_path is not None:
            with open(local_file_path, "w+") as out_file:
                json.dump(data, out_file)
            return data
        if not parse_pydantic:
            return data

        markets: list[Market] = []
        for market_object in data:
            markets.append(self.parse_pydantic_market(market_object))
        return markets

    def get_events(
        self, querystring_params=None, parse_pydantic=False, local_file_path=None
    ) -> "list[PolymarketEvent]":
        if parse_pydantic and local_file_path is not None:
            raise Exception(
                'Cannot use "parse_pydantic" and "local_file" params simultaneously.'
            )

        params = querystring_params or {}
        response = self.http_client.get(self.gamma_events_endpoint, params=params)
        if response.status_code != 200:
            raise Exception()

        data = response.json()
        if local_file_path is not None:
            with open(local_file_path, "w+") as out_file:
                json.dump(data, out_file)
            return data
        if not parse_pydantic:
            return data

        events: list[PolymarketEvent] = []
        for market_event_obj in data:
            events.append(self.parse_pydantic_event(market_event_obj))
        return events

    def get_all_markets(self, limit=2) -> "list[Market]":
        return self.get_markets(querystring_params={"limit": limit})

    def get_all_events(self, limit=2) -> "list[PolymarketEvent]":
        return self.get_events(querystring_params={"limit": limit})

    def get_current_markets(self, limit=4) -> "list[Market]":
        return self.get_markets(
            querystring_params={
                "active": True,
                "closed": False,
                "archived": False,
                "limit": limit,
            }
        )

    def get_all_current_markets(self, limit=100) -> "list[Market]":
        offset = 0
        all_markets = []
        while True:
            params = {
                "active": True,
                "closed": False,
                "archived": False,
                "limit": limit,
                "offset": offset,
            }
            market_batch = self.get_markets(querystring_params=params)
            all_markets.extend(market_batch)

            if len(market_batch) < limit:
                break
            offset += limit

        return all_markets

    def get_current_events(self, limit=4) -> "list[PolymarketEvent]":
        return self.get_events(
            querystring_params={
                "active": True,
                "closed": False,
                "archived": False,
                "limit": limit,
            }
        )

    def get_clob_tradable_markets(self, limit=2) -> "list[Market]":
        return self.get_markets(
            querystring_params={
                "active": True,
                "closed": False,
                "archived": False,
                "limit": limit,
                "enableOrderBook": True,
            }
        )

    def get_market(self, market_id: int) -> dict:
        url = self.gamma_markets_endpoint + "/" + str(market_id)
        if self.log_market_detail_url:
            print(url)
        response = self.http_client.get(url)
        response.raise_for_status()
        return response.json()

    def get_markets_by_ids(
        self, market_ids: "list[int | str]", max_workers: int = None
    ) -> "list[dict[str, Any]]":
        ordered_ids = [str(market_id).strip() for market_id in market_ids if market_id]
        if not ordered_ids:
            return []

        unique_ids = list(dict.fromkeys(ordered_ids))
        worker_limit = (
            self.market_fetch_concurrency
            if max_workers is None
            else max(1, max_workers)
        )
        workers = max(1, min(worker_limit, len(unique_ids)))
        fetched_by_id: dict[str, dict[str, Any]] = {}

        if workers == 1:
            for market_id in unique_ids:
                try:
                    fetched_by_id[market_id] = self.get_market(market_id)
                except Exception as err:
                    print(f"[markets] request_failed market_id={market_id} error={err}")
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_market_id = {
                    executor.submit(self.get_market, market_id): market_id
                    for market_id in unique_ids
                }
                for future in as_completed(future_to_market_id):
                    market_id = future_to_market_id[future]
                    try:
                        fetched_by_id[market_id] = future.result()
                    except Exception as err:
                        print(
                            f"[markets] request_failed market_id={market_id} error={err}"
                        )

        return [
            fetched_by_id[market_id]
            for market_id in ordered_ids
            if market_id in fetched_by_id
        ]

    # ------------------------------------------------------------------
    # Sports market discovery: slug-based lookup
    # ------------------------------------------------------------------

    def _is_moneyline_market(self, market: dict) -> bool:
        """Return True if market is a moneyline (who wins) market.

        Moneyline markets have questions containing "win" or "winner".
        Spreads, totals, and props do not match this criterion.
        """
        question = market.get("question", "") or ""
        q_lower = question.lower()
        return "win" in q_lower or "winner" in q_lower

    def _extract_teams_from_slug(self, ws_slug: str) -> tuple[str, list[str]]:
        """Parse a websocket slug into league and team abbreviation list.

        Expected format: "{league}-{team1}-{team2}-{YYYY}-{MM}-{DD}"
        Returns (league, [team1, team2]).  Date parts (4-digit year) are
        stripped; remaining dash-separated tokens after the league are
        treated as team abbreviations.
        """
        parts = ws_slug.split("-")
        if not parts:
            return "", []
        league = parts[0]
        # Exclude date-like tokens: 4-digit numbers are year, 2-digit are month/day
        team_parts = []
        for part in parts[1:]:
            if part.isdigit() and len(part) in (2, 4):
                continue
            team_parts.append(part.lower())
        return league, team_parts

    def _market_dict_to_tag(
        self, event_slug: str, event: dict, market: dict
    ) -> "SportsMarketTag":
        """Convert a raw Gamma market dict and its parent event to a SportsMarketTag."""
        league, teams = self._extract_teams_from_slug(event_slug)
        home_team = teams[0].upper() if len(teams) > 0 else ""
        away_team = teams[1].upper() if len(teams) > 1 else ""

        clob_ids: list[str] = market.get("clobTokenIds") or []
        token_yes = str(clob_ids[0]) if len(clob_ids) > 0 else ""
        token_no = str(clob_ids[1]) if len(clob_ids) > 1 else ""

        prices = market.get("outcomePrices")
        outcome_prices_str: str | None = None
        if isinstance(prices, list):
            outcome_prices_str = ",".join(str(p) for p in prices)
        elif isinstance(prices, str):
            outcome_prices_str = prices

        return SportsMarketTag(
            slug=event_slug,
            league=league,
            home_team=home_team,
            away_team=away_team,
            market_id=str(market.get("id", "")),
            condition_id=str(market.get("conditionId", "")),
            token_id_yes=token_yes,
            token_id_no=token_no,
            question=str(market.get("question", "")),
            outcome_prices=outcome_prices_str,
        )

    def _logger(self) -> logging.Logger:
        """Return instance logger, falling back to module logger if __init__ was bypassed."""
        if hasattr(self, "logger"):
            return self.logger
        return logging.getLogger(__name__)

    def lookup_markets_by_slug(self, ws_slug: str) -> "list[SportsMarketTag]":
        """Fast-path lookup: GET /events/slug/{ws_slug}, filter to moneyline.

        Returns list of SportsMarketTag for each moneyline market found.
        Returns empty list on 404, non-200 status, or any exception.
        """
        url = f"{self.gamma_events_endpoint}/slug/{ws_slug}"
        try:
            response = self.http_client.get(url)
            if response.status_code == 404:
                return []
            if response.status_code != 200:
                self._logger().warning(
                    "[gamma_slug] event=lookup_failed slug=%s status=%d",
                    ws_slug,
                    response.status_code,
                )
                return []
            event = response.json()
            markets: list[dict] = event.get("markets") or []
            result: list[SportsMarketTag] = []
            for market in markets:
                if self._is_moneyline_market(market):
                    result.append(self._market_dict_to_tag(ws_slug, event, market))
            return result
        except Exception as exc:
            self._logger().debug(
                "[gamma_slug] event=lookup_error slug=%s error=%s", ws_slug, exc
            )
            return []

    def lookup_markets_fallback(
        self, league: str, home_team: str, away_team: str
    ) -> "list[SportsMarketTag]":
        """Fallback lookup: GET /events?active=True&closed=False, filter by teams.

        Searches event titles/slugs for both team abbreviations (case-insensitive)
        and the league string. Returns moneyline markets from matching events.
        """
        try:
            params = {"active": True, "closed": False}
            response = self.http_client.get(self.gamma_events_endpoint, params=params)
            if response.status_code != 200:
                return []
            events: list[dict] = response.json() or []
            team_a = home_team.lower()
            team_b = away_team.lower()
            league_lower = league.lower()
            result: list[SportsMarketTag] = []
            for event in events:
                event_slug = (event.get("slug") or "").lower()
                event_title = (event.get("title") or "").lower()
                searchable = event_slug + " " + event_title
                if (
                    league_lower in searchable
                    and team_a in searchable
                    and team_b in searchable
                ):
                    slug_key = event.get("slug") or ""
                    for market in event.get("markets") or []:
                        if self._is_moneyline_market(market):
                            result.append(
                                self._market_dict_to_tag(slug_key, event, market)
                            )
            return result
        except Exception as exc:
            self._logger().debug(
                "[gamma_slug] event=fallback_error league=%s error=%s", league, exc
            )
            return []

    def lookup_single_slug(self, ws_slug: str) -> "list[SportsMarketTag]":
        """On-demand lookup for a single slug (e.g. when WS reports a new gameId).

        Tries fast slug path first; falls back to team-name search on 404.
        """
        tags = self.lookup_markets_by_slug(ws_slug)
        if tags:
            return tags
        # Fallback: derive league + teams from slug
        league, teams = self._extract_teams_from_slug(ws_slug)
        home_team = teams[0] if len(teams) > 0 else ""
        away_team = teams[1] if len(teams) > 1 else ""
        return self.lookup_markets_fallback(league, home_team, away_team)

    def build_slug_table(
        self, game_states: "dict[int, SportGameState]"
    ) -> "tuple[dict[str, list[SportsMarketTag]], list[str]]":
        """Build ws_slug -> list[SportsMarketTag] mapping from active game states.

        For each game:
          1. Try lookup_markets_by_slug (fast path).
          2. If empty, try lookup_markets_fallback.
          3. If still empty, log as unmapped and add to retry list.

        Returns:
            (slug_table, unmapped_slugs) where unmapped_slugs is the retry queue.
        """
        slug_table: dict[str, list[SportsMarketTag]] = {}
        unmapped: list[str] = []
        for game_id, game_state in game_states.items():
            slug = game_state.slug
            tags = self.lookup_markets_by_slug(slug)
            if not tags:
                tags = self.lookup_markets_fallback(
                    game_state.league, game_state.home_team, game_state.away_team
                )
            if tags:
                slug_table[slug] = tags
            else:
                print(f"[gamma_slug] event=unmapped slug={slug} game_id={game_id}")
                unmapped.append(slug)
        return slug_table, unmapped

    def close(self) -> None:
        self.http_client.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


if __name__ == "__main__":
    from agents.polymarket.polymarket import Polymarket

    gamma = GammaMarketClient()
    market = gamma.get_market("253123")
    poly = Polymarket()
    object = poly.map_api_to_market(market)
