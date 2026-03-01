import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from agents.polymarket.polymarket import Polymarket
from agents.utils.objects import Market, PolymarketEvent, ClobReward, Tag


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
        self.log_market_detail_url = (
            str(os.getenv("GAMMA_LOG_MARKET_DETAIL_URL", "false")).strip().lower()
            in ("1", "true", "yes", "on")
        )

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
            self.market_fetch_concurrency if max_workers is None else max(1, max_workers)
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

    def close(self) -> None:
        self.http_client.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


if __name__ == "__main__":
    gamma = GammaMarketClient()
    market = gamma.get_market("253123")
    poly = Polymarket()
    object = poly.map_api_to_market(market)
