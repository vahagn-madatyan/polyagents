import ast
import json
import logging
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agents.application.prompts import Prompter
from agents.connectors.chroma import PolymarketRAG as Chroma
from agents.polymarket.gamma import GammaMarketClient as Gamma
from agents.polymarket.polymarket import Polymarket
from agents.utils.env import _env_bool, _env_float, _env_int
from agents.utils.objects import CandidateTrade, SimpleEvent, SimpleMarket


def retain_keys(data, keys_to_retain):
    if isinstance(data, dict):
        return {
            key: retain_keys(value, keys_to_retain)
            for key, value in data.items()
            if key in keys_to_retain
        }
    if isinstance(data, list):
        return [retain_keys(item, keys_to_retain) for item in data]
    return data


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bucket_from_text(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower())
    if not normalized.strip():
        return "other"

    keyword_map = {
        "sports": [
            "sports",
            "nfl",
            "nba",
            "mlb",
            "nhl",
            "soccer",
            "football",
            "premier league",
            "champions league",
            "ufc",
            "mma",
            "tennis",
            "cricket",
            "fifa",
            "world cup",
            "ncaa",
            "lpl",
            "nfl",
        ],
        "politics": [
            "politics",
            "political",
            "election",
            "senate",
            "house",
            "president",
            "prime minister",
            "parliament",
            "democrat",
            "republican",
            "trump",
            "biden",
            "gop",
            "campaign",
            "midterm",
            "vote",
        ],
        "crypto": [
            "cryptocurrency",
            "crypto",
            "bitcoin",
            "ethereum",
            "btc",
            "eth",
            "solana",
            "token",
            "blockchain",
            "airdop",
            "airdrop",
            "defi",
            "onchain",
            "chainlink",
            "polygon",
        ],
    }

    for bucket, keywords in keyword_map.items():
        for keyword in keywords:
            if keyword in normalized:
                return bucket
    return "other"


def canonicalize_category(
    explicit_category: str,
    tags: str,
    question: str,
    description: str,
) -> str:
    bucket = _bucket_from_text(explicit_category)
    if bucket != "other":
        return bucket

    bucket = _bucket_from_text(tags)
    if bucket != "other":
        return bucket

    bucket = _bucket_from_text(f"{question} {description}")
    if bucket != "other":
        return bucket

    return "other"


def compute_confidence_gap(probabilities: List[Dict[str, Any]]) -> float:
    values = []
    for item in probabilities or []:
        likelihood = _safe_float(item.get("likelihood"), default=-1)
        if likelihood >= 0:
            values.append(likelihood)
    if len(values) < 2:
        return 0.0
    values = sorted(values, reverse=True)
    return max(0.0, values[0] - values[1])


def _candidate_score_key(candidate: CandidateTrade) -> Tuple[float, float, int]:
    rag_score = candidate.rag_score if candidate.rag_score is not None else float("inf")
    return (-candidate.confidence_gap, rag_score, candidate.market_id)


def select_soft_quota_candidates(
    candidates: List[CandidateTrade],
    target_count: int,
    min_categories: int,
) -> List[CandidateTrade]:
    if target_count <= 0:
        return []

    ranked = sorted(candidates, key=_candidate_score_key)
    if not ranked:
        return []

    selected: List[CandidateTrade] = []
    selected_ids = set()
    selected_categories = set()

    while len(selected) < target_count and len(selected_categories) < max(
        0, min_categories
    ):
        best_next = None
        for candidate in ranked:
            if candidate.market_id in selected_ids:
                continue
            if candidate.category_bucket in selected_categories:
                continue
            if best_next is None or _candidate_score_key(
                candidate
            ) < _candidate_score_key(best_next):
                best_next = candidate
        if best_next is None:
            break
        selected.append(best_next)
        selected_ids.add(best_next.market_id)
        selected_categories.add(best_next.category_bucket)

    for candidate in ranked:
        if len(selected) >= target_count:
            break
        if candidate.market_id in selected_ids:
            continue
        selected.append(candidate)
        selected_ids.add(candidate.market_id)

    return selected


def allocate_confidence_weighted(
    candidates: List[CandidateTrade],
    usdc_balance: float,
    total_budget_fraction: float,
    min_per_market_fraction: float,
    max_per_market_fraction: float,
) -> List[CandidateTrade]:
    if not candidates:
        return candidates

    balance = max(0.0, float(usdc_balance))
    budget = balance * max(0.0, total_budget_fraction)

    for candidate in candidates:
        candidate.allocation_amount_usdc = 0.0
        candidate.allocation_fraction = 0.0

    if budget <= 0 or balance <= 0:
        return candidates

    weights = [max(0.0, candidate.confidence_gap) for candidate in candidates]
    if sum(weights) <= 0:
        weights = [1.0 for _ in candidates]

    min_amount = balance * max(0.0, min_per_market_fraction)
    max_amount = balance * max(max_per_market_fraction, min_per_market_fraction, 0.0)

    upper_bounds = [max_amount for _ in candidates]
    lower_bounds = [min_amount for _ in candidates]

    budget = min(budget, sum(upper_bounds))

    if sum(lower_bounds) > budget:
        lower_bounds = [0.0 for _ in candidates]

    amounts = _allocate_with_bounds(budget, weights, lower_bounds, upper_bounds)

    for idx, candidate in enumerate(candidates):
        amount = max(0.0, amounts[idx])
        candidate.allocation_amount_usdc = amount
        candidate.allocation_fraction = amount / balance if balance > 0 else 0.0

    return candidates


def _allocate_with_bounds(
    budget: float,
    weights: List[float],
    lower_bounds: List[float],
    upper_bounds: List[float],
) -> List[float]:
    count = len(weights)
    if count == 0:
        return []

    budget = max(0.0, float(budget))
    weights = [max(0.0, float(w)) for w in weights]
    lower_bounds = [max(0.0, float(x)) for x in lower_bounds]
    upper_bounds = [max(lower_bounds[i], float(upper_bounds[i])) for i in range(count)]

    if budget <= 0:
        return [0.0 for _ in range(count)]

    upper_total = sum(upper_bounds)
    if budget >= upper_total:
        return upper_bounds

    lower_total = sum(lower_bounds)
    if lower_total > budget:
        normalized_weight_sum = sum(weights) if sum(weights) > 0 else float(count)
        provisional = []
        for i in range(count):
            w = weights[i] if sum(weights) > 0 else 1.0
            provisional.append((budget * w) / normalized_weight_sum)
        return [min(provisional[i], upper_bounds[i]) for i in range(count)]

    amounts = list(lower_bounds)
    remaining = budget - sum(amounts)

    active = {idx for idx in range(count) if upper_bounds[idx] > amounts[idx] + 1e-9}

    while remaining > 1e-9 and active:
        active_weight = sum(weights[idx] for idx in active)
        if active_weight <= 0:
            per_idx = remaining / float(len(active))
            target_add = {idx: per_idx for idx in active}
        else:
            target_add = {
                idx: remaining * (weights[idx] / active_weight) for idx in active
            }

        distributed = 0.0
        for idx in list(active):
            capacity = upper_bounds[idx] - amounts[idx]
            add = min(capacity, target_add[idx])
            if add > 0:
                amounts[idx] += add
                distributed += add
            if upper_bounds[idx] - amounts[idx] <= 1e-9:
                active.remove(idx)

        if distributed <= 1e-12:
            break

        remaining = budget - sum(amounts)

    residual = budget - sum(amounts)
    if residual > 1e-6:
        for idx in range(count):
            capacity = upper_bounds[idx] - amounts[idx]
            add = min(capacity, residual)
            if add > 0:
                amounts[idx] += add
                residual -= add
            if residual <= 1e-6:
                break

    return amounts


class Executor:
    def __init__(self, default_model: str = "gpt-5-mini") -> None:
        load_dotenv()

        configured_model = os.getenv("OPENAI_MODEL", default_model)
        max_token_model = {
            "gpt-5-mini": 128000,
            "gpt-4.1-mini": 128000,
            "gpt-4o-mini": 128000,
            "gpt-4.1": 128000,
        }
        self.token_limit = max_token_model.get(configured_model, 64000)
        self.prompter = Prompter()
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.model_name = configured_model

        self.trade_candidate_count = _env_int("TRADE_CANDIDATE_COUNT", 5)
        self.trade_diversity_mode = os.getenv("TRADE_DIVERSITY_MODE", "soft_quota")
        self.trade_diversity_min_categories = _env_int(
            "TRADE_DIVERSITY_MIN_CATEGORIES", 3
        )
        self.trade_max_markets_to_score = _env_int("TRADE_MAX_MARKETS_TO_SCORE", 20)
        self.trade_total_budget_fraction = _env_float(
            "TRADE_TOTAL_BUDGET_FRACTION", 0.30
        )
        self.trade_max_per_market_fraction = _env_float(
            "TRADE_MAX_PER_MARKET_FRACTION", 0.10
        )
        self.trade_min_per_market_fraction = _env_float(
            "TRADE_MIN_PER_MARKET_FRACTION", 0.02
        )
        self.trade_log_rationale = _env_bool("TRADE_LOG_RATIONALE", True)
        self.trade_min_market_volume = _env_float("TRADE_MIN_MARKET_VOLUME", 10000.0)
        self.trade_min_market_liquidity = _env_float(
            "TRADE_MIN_MARKET_LIQUIDITY", 5000.0
        )
        self.trade_min_entry_price = _env_float("TRADE_MIN_ENTRY_PRICE", 0.03)
        self.trade_max_entry_price = _env_float("TRADE_MAX_ENTRY_PRICE", 0.97)

        self.logger = logging.getLogger(self.__class__.__name__)
        self.openai_log_level = os.getenv("OPENAI_LOG", "info")
        os.environ.setdefault("OPENAI_LOG", self.openai_log_level)
        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=os.getenv("APP_LOG_LEVEL", "INFO").upper(),
                format="[%(levelname)s] %(name)s %(message)s",
            )

        self.logger.info(
            "[openai] model=%s sdk_log=%s app_log=%s",
            self.model_name,
            os.getenv("OPENAI_LOG"),
            os.getenv("APP_LOG_LEVEL", "INFO").upper(),
        )
        self.logger.info(
            "[trade_cfg] candidate_count=%s diversity_mode=%s min_categories=%s max_markets_to_score=%s budget_fraction=%.4f min_market_fraction=%.4f max_market_fraction=%.4f rationale_logging=%s min_market_volume=%.2f min_market_liquidity=%.2f min_entry_price=%.4f max_entry_price=%.4f",
            self.trade_candidate_count,
            self.trade_diversity_mode,
            self.trade_diversity_min_categories,
            self.trade_max_markets_to_score,
            self.trade_total_budget_fraction,
            self.trade_min_per_market_fraction,
            self.trade_max_per_market_fraction,
            self.trade_log_rationale,
            self.trade_min_market_volume,
            self.trade_min_market_liquidity,
            self.trade_min_entry_price,
            self.trade_max_entry_price,
        )

        llm_kwargs = {"model": self.model_name}
        temp_value = os.getenv("OPENAI_TEMPERATURE")
        supports_custom_temperature = not self.model_name.lower().startswith("gpt-5")
        if not supports_custom_temperature:
            # GPT-5 models only accept default temperature behavior via value 1.
            llm_kwargs["temperature"] = 1
            self.logger.info(
                "[openai] forcing temperature=1 for model=%s", self.model_name
            )
        if temp_value is not None and temp_value != "":
            if supports_custom_temperature:
                try:
                    llm_kwargs["temperature"] = float(temp_value)
                except ValueError:
                    self.logger.warning(
                        "[openai] invalid OPENAI_TEMPERATURE=%r, using model default",
                        temp_value,
                    )
            else:
                self.logger.info(
                    "[openai] ignoring OPENAI_TEMPERATURE for model=%s (uses default temperature only)",
                    self.model_name,
                )
        else:
            self.logger.info("[openai] using model default temperature")

        self.llm = ChatOpenAI(**llm_kwargs)
        self.gamma = Gamma()
        self.chroma = Chroma()
        self.polymarket_mapper = Polymarket(initialize_clob_client=False)

    def _invoke_llm(self, payload, operation_name: str) -> str:
        result = self.llm.invoke(payload)

        response_metadata = getattr(result, "response_metadata", {}) or {}
        usage_metadata = getattr(result, "usage_metadata", {}) or {}

        usage = {}
        if isinstance(usage_metadata, dict):
            usage.update(usage_metadata)
        if isinstance(response_metadata, dict):
            token_usage = response_metadata.get("token_usage")
            if isinstance(token_usage, dict):
                usage.setdefault("input_tokens", token_usage.get("prompt_tokens"))
                usage.setdefault("output_tokens", token_usage.get("completion_tokens"))
                usage.setdefault("total_tokens", token_usage.get("total_tokens"))

        model_name = (
            response_metadata.get("model_name", self.model_name)
            if isinstance(response_metadata, dict)
            else self.model_name
        )
        self.logger.info(
            "[openai] op=%s model=%s usage=%s",
            operation_name,
            model_name,
            usage if usage else "unavailable",
        )

        return result.content

    def _parse_probability_lines(self, text: str) -> List[Dict[str, Any]]:
        pattern = re.compile(
            r"likelihood\s*`?([0-9]*\.?[0-9]+)`?\s*for outcome of\s*`?['\"]?([^`'\"\n]+)['\"]?`?",
            re.IGNORECASE,
        )
        probabilities = []
        for match in pattern.finditer(text or ""):
            likelihood_raw = match.group(1)
            outcome = match.group(2).strip()
            likelihood = _safe_float(likelihood_raw, default=-1.0)
            if likelihood < 0:
                continue
            probabilities.append({"outcome": outcome, "likelihood": likelihood})
        return probabilities

    def _parse_trade_fields(self, text: str) -> Dict[str, Any]:
        def extract(pattern: str) -> str:
            match = re.search(pattern, text or "", flags=re.IGNORECASE)
            return match.group(1).strip() if match else ""

        price = extract(r"price\s*[:=]\s*['`\"]?([0-9]*\.?[0-9]+)")
        size = extract(r"size(?:_fraction)?\s*[:=]\s*['`\"]?([0-9]*\.?[0-9]+)")
        side = extract(r"side\s*[:=]\s*['`\"]?([A-Za-z]+)").upper()

        return {
            "price": _safe_float(price, default=0.0) if price else None,
            "size": _safe_float(size, default=0.0) if size else None,
            "side": side,
        }

    def _parse_literal_list(self, value) -> List[Any]:
        if isinstance(value, list):
            return value
        if not isinstance(value, str):
            return []
        try:
            parsed = ast.literal_eval(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []

    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        if not text:
            return {}

        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```[a-zA-Z]*", "", candidate).strip()
            candidate = re.sub(r"```$", "", candidate).strip()

        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}

        snippet = match.group(0).strip()
        try:
            parsed = json.loads(snippet)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}

        return {}

    def _normalize_probabilities(
        self,
        raw_probabilities: Any,
        outcomes: List[str],
        fill_default: bool = False,
    ) -> List[Dict[str, Any]]:
        normalized = []
        if isinstance(raw_probabilities, list):
            for item in raw_probabilities:
                if not isinstance(item, dict):
                    continue
                outcome = str(item.get("outcome", "")).strip()
                likelihood = _safe_float(item.get("likelihood"), default=-1.0)
                if not outcome or likelihood < 0:
                    continue
                normalized.append(
                    {"outcome": outcome, "likelihood": max(0.0, min(1.0, likelihood))}
                )

        if normalized:
            return normalized

        if fill_default and outcomes:
            even_prob = 1.0 / float(len(outcomes))
            return [
                {"outcome": str(outcome), "likelihood": even_prob}
                for outcome in outcomes
            ]

        return []

    def _fallback_selected_outcome(
        self,
        probabilities: List[Dict[str, Any]],
        outcomes: List[str],
    ) -> str:
        if probabilities:
            ranked = sorted(
                probabilities,
                key=lambda item: _safe_float(item.get("likelihood"), default=0.0),
                reverse=True,
            )
            return str(ranked[0].get("outcome", "")).strip()
        if outcomes:
            return str(outcomes[0])
        return ""

    def _parse_trade_decision(
        self,
        superforecast_content: str,
        trade_content: str,
        outcomes: List[str],
        outcome_prices: List[float],
    ) -> Dict[str, Any]:
        trade_json = self._parse_json_object(trade_content)
        regex_trade = self._parse_trade_fields(trade_content)

        probabilities = self._normalize_probabilities(
            trade_json.get("probabilities", []),
            outcomes,
            fill_default=False,
        )
        if not probabilities:
            probabilities = self._normalize_probabilities(
                self._parse_probability_lines(superforecast_content),
                outcomes,
                fill_default=False,
            )
        if not probabilities:
            probabilities = self._normalize_probabilities(
                [], outcomes, fill_default=True
            )

        selected_outcome = str(trade_json.get("selected_outcome", "")).strip()
        if not selected_outcome:
            selected_outcome = self._fallback_selected_outcome(probabilities, outcomes)

        parsed_side = str(trade_json.get("side", "")).strip().upper()
        if not parsed_side:
            parsed_side = str(regex_trade.get("side") or "BUY").strip().upper()
        if parsed_side not in ("BUY", "SELL"):
            parsed_side = "BUY"

        parsed_price = trade_json.get("price")
        if parsed_price is None:
            parsed_price = regex_trade.get("price")
        parsed_price = _safe_float(parsed_price, default=-1.0)
        if parsed_price < 0:
            parsed_price = None

        parsed_size_fraction = trade_json.get("size_fraction")
        if parsed_size_fraction is None:
            parsed_size_fraction = regex_trade.get("size")
        parsed_size_fraction = _safe_float(parsed_size_fraction, default=-1.0)
        if parsed_size_fraction < 0:
            parsed_size_fraction = None

        if parsed_price is None and selected_outcome in outcomes:
            idx = outcomes.index(selected_outcome)
            if idx < len(outcome_prices):
                parsed_price = _safe_float(outcome_prices[idx], default=0.0)

        rationale = str(trade_json.get("rationale", "")).strip()
        risk_factors = trade_json.get("risk_factors", [])
        if not isinstance(risk_factors, list):
            risk_factors = []
        risk_factors = [str(item).strip() for item in risk_factors if str(item).strip()]
        counter_case = str(trade_json.get("counter_case", "")).strip()

        return {
            "probabilities": probabilities,
            "selected_outcome": selected_outcome,
            "parsed_side": parsed_side,
            "parsed_price": parsed_price,
            "parsed_size_fraction": parsed_size_fraction,
            "rationale": rationale,
            "risk_factors": risk_factors,
            "counter_case": counter_case,
            "confidence_gap": compute_confidence_gap(probabilities),
            "trade_json": trade_json,
        }

    def get_llm_response(self, user_input: str) -> str:
        system_message = SystemMessage(content=str(self.prompter.market_analyst()))
        human_message = HumanMessage(content=user_input)
        messages = [system_message, human_message]
        return self._invoke_llm(messages, "get_llm_response")

    def get_superforecast(
        self, event_title: str, market_question: str, outcome: str
    ) -> str:
        prompt = self.prompter.superforecaster(
            description=event_title,
            question=market_question,
            outcome=outcome,
        )
        return self._invoke_llm(prompt, "get_superforecast")

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    def process_data_chunk(
        self,
        data1: List[Dict[Any, Any]],
        data2: List[Dict[Any, Any]],
        user_input: str,
    ) -> str:
        system_message = SystemMessage(
            content=str(self.prompter.prompts_polymarket(data1=data1, data2=data2))
        )
        human_message = HumanMessage(content=user_input)
        messages = [system_message, human_message]
        return self._invoke_llm(messages, "process_data_chunk")

    def divide_list(self, original_list, i):
        sublist_size = math.ceil(len(original_list) / i)
        return [
            original_list[j : j + sublist_size]
            for j in range(0, len(original_list), sublist_size)
        ]

    def get_polymarket_llm(self, user_input: str) -> str:
        data1 = self.gamma.get_current_events()
        data2 = self.gamma.get_current_markets()

        combined_data = str(self.prompter.prompts_polymarket(data1=data1, data2=data2))
        total_tokens = self.estimate_tokens(combined_data)
        token_limit = self.token_limit

        if total_tokens <= token_limit:
            return self.process_data_chunk(data1, data2, user_input)

        print(
            f"total tokens {total_tokens} exceeding llm capacity, now will split and answer"
        )
        group_size = (total_tokens // token_limit) + 1
        useful_keys = [
            "id",
            "questionID",
            "description",
            "liquidity",
            "clobTokenIds",
            "outcomes",
            "outcomePrices",
            "volume",
            "startDate",
            "endDate",
            "question",
            "questionID",
            "events",
        ]
        data1 = retain_keys(data1, useful_keys)
        cut_1 = self.divide_list(data1, group_size)
        cut_2 = self.divide_list(data2, group_size)

        results = []
        for sub_data1, sub_data2 in zip(cut_1, cut_2):
            result = self.process_data_chunk(sub_data1, sub_data2, user_input)
            results.append(result)

        return " ".join(results)

    def filter_events(self, events: List[SimpleEvent]) -> str:
        prompt = self.prompter.filter_events()
        return self._invoke_llm(prompt, "filter_events")

    def filter_events_with_rag(self, events: List[SimpleEvent]) -> List[tuple]:
        prompt = self.prompter.filter_events()
        event_k = max(25, self.trade_candidate_count * 5)
        print()
        print("... prompting ... ", prompt)
        print()
        self.logger.info("[events] rag_query_k=%s", event_k)
        return self.chroma.events(events, prompt, k=event_k)

    def map_filtered_events_to_markets(
        self,
        filtered_events: List[SimpleEvent],
    ) -> List[SimpleMarket]:
        markets = []
        seen_market_ids = set()
        market_ids_to_fetch = []

        for event_item in filtered_events:
            event_doc = (
                event_item[0] if isinstance(event_item, (list, tuple)) else event_item
            )
            try:
                data = json.loads(event_doc.json())
            except Exception as err:
                print(f"[events] failed_to_parse_filtered_event error={err}")
                continue

            metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
            raw_market_ids = metadata.get("markets")
            if not raw_market_ids:
                raw_market_ids = data.get("markets", "")

            if isinstance(raw_market_ids, list):
                market_ids = [str(market_id).strip() for market_id in raw_market_ids]
            else:
                market_ids = str(raw_market_ids).split(",")

            for market_id in market_ids:
                market_id = str(market_id).strip()
                if not market_id or market_id in seen_market_ids:
                    continue
                seen_market_ids.add(market_id)
                market_ids_to_fetch.append(market_id)

        if not market_ids_to_fetch:
            return markets

        self.logger.info(
            "[markets] fetching_details requested=%s unique=%s concurrency=%s",
            len(market_ids_to_fetch),
            len(seen_market_ids),
            self.gamma.market_fetch_concurrency,
        )

        fetched_markets = []
        if hasattr(self.gamma, "get_markets_by_ids"):
            try:
                fetched_markets = self.gamma.get_markets_by_ids(market_ids_to_fetch)
            except Exception as err:
                print(f"[markets] bulk_fetch_failed error={err}")
        if not fetched_markets:
            for market_id in market_ids_to_fetch:
                try:
                    fetched_markets.append(self.gamma.get_market(market_id))
                except Exception as err:
                    print(f"[markets] skipped market_id={market_id} error={err}")

        skipped_parse = 0
        skipped_quality = 0
        for market_data in fetched_markets:
            try:
                formatted_market_data = self.polymarket_mapper.map_api_to_market(
                    market_data
                )
            except Exception as err:
                skipped_parse += 1
                market_id = (
                    market_data.get("id", "unknown")
                    if isinstance(market_data, dict)
                    else "unknown"
                )
                print(f"[markets] skipped market_id={market_id} map_error={err}")
                continue

            if not self._passes_market_quality_filters(formatted_market_data):
                skipped_quality += 1
                continue
            markets.append(formatted_market_data)

        self.logger.info(
            "[markets] mapped_details fetched=%s mapped=%s skipped_parse=%s skipped_quality=%s",
            len(fetched_markets),
            len(markets),
            skipped_parse,
            skipped_quality,
        )

        return markets

    def _market_depth_snapshot(
        self, market_payload: Dict[str, Any]
    ) -> Dict[str, float]:
        volume_candidates = [
            market_payload.get("volume24hr_clob"),
            market_payload.get("volume24hr"),
            market_payload.get("volume_clob"),
            market_payload.get("volume"),
        ]
        liquidity_candidates = [
            market_payload.get("liquidity_clob"),
            market_payload.get("liquidity"),
        ]

        best_volume = max(
            (_safe_float(value, default=0.0) for value in volume_candidates),
            default=0.0,
        )
        best_liquidity = max(
            (_safe_float(value, default=0.0) for value in liquidity_candidates),
            default=0.0,
        )
        return {"volume": best_volume, "liquidity": best_liquidity}

    def _has_tradeable_price_band(self, outcome_prices: List[float]) -> bool:
        for price in outcome_prices:
            numeric_price = _safe_float(price, default=-1.0)
            if (
                self.trade_min_entry_price
                <= numeric_price
                <= self.trade_max_entry_price
            ):
                return True
        return False

    def _passes_market_quality_filters(self, market_payload: Dict[str, Any]) -> bool:
        depth = self._market_depth_snapshot(market_payload)
        if depth["volume"] < self.trade_min_market_volume:
            return False
        if depth["liquidity"] < self.trade_min_market_liquidity:
            return False

        outcome_prices_raw = self._parse_literal_list(
            market_payload.get("outcome_prices", "[]")
        )
        outcome_prices = [
            _safe_float(price, default=-1.0) for price in outcome_prices_raw
        ]
        if not outcome_prices:
            return False
        if not self._has_tradeable_price_band(outcome_prices):
            return False
        return True

    def filter_markets(self, markets) -> List[tuple]:
        prompt = self.prompter.filter_markets()
        print()
        print("... prompting ... ", prompt)
        print()
        self.logger.info("[markets] rag_query_k=%s", self.trade_max_markets_to_score)
        return self.chroma.markets(markets, prompt, k=self.trade_max_markets_to_score)

    def _dedupe_market_docs(self, markets: List[tuple]) -> List[tuple]:
        best_by_market_id = {}
        for market_obj in markets:
            if not isinstance(market_obj, (list, tuple)) or len(market_obj) == 0:
                continue
            market_doc = market_obj[0]
            rag_score = (
                _safe_float(market_obj[1], default=float("inf"))
                if len(market_obj) > 1
                else float("inf")
            )

            metadata = getattr(market_doc, "metadata", {}) or {}
            market_id = str(metadata.get("id") or "")
            dedupe_key = market_id or str(
                metadata.get("question") or market_doc.page_content
            )

            existing = best_by_market_id.get(dedupe_key)
            if existing is None:
                best_by_market_id[dedupe_key] = market_obj
                continue

            existing_score = (
                _safe_float(existing[1], default=float("inf"))
                if len(existing) > 1
                else float("inf")
            )
            if rag_score < existing_score:
                best_by_market_id[dedupe_key] = market_obj

        deduped = list(best_by_market_id.values())
        deduped.sort(
            key=lambda item: (
                _safe_float(item[1], default=float("inf"))
                if len(item) > 1
                else float("inf")
            )
        )
        return deduped[: self.trade_max_markets_to_score]

    def source_best_trade(
        self,
        market_object,
        supplemental_context: str = "",
    ) -> CandidateTrade:
        market_document = market_object[0].dict()
        market = market_document.get("metadata", {})

        rag_score = market_object[1] if len(market_object) > 1 else None
        market_id = int(_safe_float(market.get("id"), default=0))
        question = str(market.get("question", ""))
        description = str(market_document.get("page_content", ""))
        outcomes = [
            str(item) for item in self._parse_literal_list(market.get("outcomes", "[]"))
        ]
        outcome_prices_raw = self._parse_literal_list(
            market.get("outcome_prices", "[]")
        )
        token_ids = [
            str(item)
            for item in self._parse_literal_list(market.get("clob_token_ids", "[]"))
        ]
        outcome_prices = [
            _safe_float(price, default=0.0) for price in outcome_prices_raw
        ]

        category_bucket = canonicalize_category(
            explicit_category=str(market.get("category", "")),
            tags=str(market.get("tags", "")),
            question=question,
            description=description,
        )

        forecasting_description = description
        if supplemental_context:
            forecasting_description = f"{description}\n\nRecent news context for this market:\n{supplemental_context}"

        prompt = self.prompter.superforecaster(
            question, forecasting_description, outcomes
        )
        print()
        print("... prompting ... ", prompt)
        print()
        superforecast_content = self._invoke_llm(
            prompt,
            "source_best_trade_superforecaster",
        )

        print("result: ", superforecast_content)
        print()

        prompt = self.prompter.one_best_trade(
            prediction=superforecast_content,
            outcomes=outcomes,
            outcome_prices=outcome_prices,
        )
        print("... prompting ... ", prompt)
        print()
        trade_content = self._invoke_llm(prompt, "source_best_trade_action")

        print("result: ", trade_content)
        print()

        parsed = self._parse_trade_decision(
            superforecast_content=superforecast_content,
            trade_content=trade_content,
            outcomes=outcomes,
            outcome_prices=outcome_prices,
        )

        return CandidateTrade(
            market_id=market_id,
            question=question,
            category_bucket=category_bucket,
            outcomes=outcomes,
            outcome_prices=outcome_prices,
            token_ids=token_ids,
            rag_score=(
                _safe_float(rag_score, default=None) if rag_score is not None else None
            ),
            probabilities=parsed["probabilities"],
            suggested_outcome=parsed["selected_outcome"],
            parsed_side=parsed["parsed_side"],
            parsed_price=parsed["parsed_price"],
            parsed_size_fraction=parsed["parsed_size_fraction"],
            confidence_gap=parsed["confidence_gap"],
            rationale=parsed["rationale"],
            risk_factors=parsed["risk_factors"],
            counter_case=parsed["counter_case"],
            execution_status="NOT_EXECUTED",
            execution_response={
                "superforecast_response": superforecast_content,
                "trade_recommendation": trade_content,
            },
        )

    def build_trade_candidates(
        self,
        filtered_markets: List[tuple],
        supplemental_context_by_market_id: Optional[Dict[int, str]] = None,
    ) -> Dict[str, Any]:
        deduped_markets = self._dedupe_market_docs(filtered_markets)
        self.logger.info(
            "[candidates] deduped_markets=%s input_markets=%s",
            len(deduped_markets),
            len(filtered_markets),
        )

        context_by_market = supplemental_context_by_market_id or {}
        all_candidates: List[CandidateTrade] = []
        for index, market_obj in enumerate(deduped_markets, start=1):
            try:
                self.logger.info(
                    "[candidates] scoring_market=%s/%s", index, len(deduped_markets)
                )
                market_doc = (
                    market_obj[0] if isinstance(market_obj, (list, tuple)) else None
                )
                metadata = getattr(market_doc, "metadata", {}) or {}
                market_id = int(_safe_float(metadata.get("id"), default=0))
                supplemental_context = context_by_market.get(market_id, "")

                candidate = self.source_best_trade(
                    market_obj,
                    supplemental_context=supplemental_context,
                )
                if not self._candidate_has_tradeable_entry_price(candidate):
                    self.logger.info(
                        "[candidates] dropped_price_out_of_band market_id=%s parsed_price=%s min=%.4f max=%.4f",
                        candidate.market_id,
                        candidate.parsed_price,
                        self.trade_min_entry_price,
                        self.trade_max_entry_price,
                    )
                    continue
                all_candidates.append(candidate)
            except Exception as err:
                self.logger.warning("[candidates] skipped_market error=%s", err)

        selected_candidates = self.select_trade_candidates(all_candidates)

        return {
            "input_markets": len(filtered_markets),
            "deduped_markets": len(deduped_markets),
            "evaluated_candidates": len(all_candidates),
            "selected_candidates": selected_candidates,
            "all_candidates": all_candidates,
        }

    def _candidate_has_tradeable_entry_price(self, candidate: CandidateTrade) -> bool:
        candidate_price = candidate.parsed_price
        if (
            candidate_price is None
            and candidate.suggested_outcome in candidate.outcomes
        ):
            idx = candidate.outcomes.index(candidate.suggested_outcome)
            if idx < len(candidate.outcome_prices):
                candidate_price = _safe_float(
                    candidate.outcome_prices[idx], default=-1.0
                )

        if candidate_price is None:
            return False

        numeric_price = _safe_float(candidate_price, default=-1.0)
        return self.trade_min_entry_price <= numeric_price <= self.trade_max_entry_price

    def select_trade_candidates(
        self, candidates: List[CandidateTrade]
    ) -> List[CandidateTrade]:
        ranked = sorted(candidates, key=_candidate_score_key)
        if self.trade_diversity_mode == "soft_quota":
            return select_soft_quota_candidates(
                ranked,
                target_count=self.trade_candidate_count,
                min_categories=self.trade_diversity_min_categories,
            )
        return ranked[: self.trade_candidate_count]

    def allocate_selected_candidates(
        self,
        candidates: List[CandidateTrade],
        usdc_balance: float,
    ) -> List[CandidateTrade]:
        return allocate_confidence_weighted(
            candidates=candidates,
            usdc_balance=usdc_balance,
            total_budget_fraction=self.trade_total_budget_fraction,
            min_per_market_fraction=self.trade_min_per_market_fraction,
            max_per_market_fraction=self.trade_max_per_market_fraction,
        )

    def format_trade_prompt_for_execution(
        self, best_trade, usdc_balance: float
    ) -> float:
        size = ""
        if isinstance(best_trade, dict):
            parsed_trade = best_trade.get("parsed_trade", {})
            size = str(parsed_trade.get("size", "")).strip()
            if not size:
                size_match = re.search(
                    r"size\s*[:=]\s*['`\"]?([0-9]*\.?[0-9]+)",
                    best_trade.get("trade_recommendation", ""),
                    flags=re.IGNORECASE,
                )
                if size_match:
                    size = size_match.group(1)
        else:
            data = str(best_trade).split(",")
            if len(data) > 1:
                size_match = re.findall(r"\d+\.\d+", data[1])
                if size_match:
                    size = size_match[0]

        if not size:
            raise ValueError("Could not parse trade size from LLM output")

        return float(size) * float(usdc_balance)

    def source_best_market_to_create(self, filtered_markets) -> str:
        prompt = self.prompter.create_new_market(filtered_markets)
        print()
        print("... prompting ... ", prompt)
        print()
        return self._invoke_llm(prompt, "source_best_market_to_create")
