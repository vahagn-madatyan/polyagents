import os
import json
import ast
import re
import logging
from typing import List, Dict, Any

import math

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agents.polymarket.gamma import GammaMarketClient as Gamma
from agents.connectors.chroma import PolymarketRAG as Chroma
from agents.utils.objects import SimpleEvent, SimpleMarket
from agents.application.prompts import Prompter
from agents.polymarket.polymarket import Polymarket

def retain_keys(data, keys_to_retain):
    if isinstance(data, dict):
        return {
            key: retain_keys(value, keys_to_retain)
            for key, value in data.items()
            if key in keys_to_retain
        }
    elif isinstance(data, list):
        return [retain_keys(item, keys_to_retain) for item in data]
    else:
        return data

class Executor:
    def __init__(self, default_model="gpt-5-mini") -> None:
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
        llm_kwargs = {"model": self.model_name}
        temp_value = os.getenv("OPENAI_TEMPERATURE")
        supports_custom_temperature = not self.model_name.lower().startswith("gpt-5")
        if not supports_custom_temperature:
            # langchain-openai defaults to temperature=0.7 if unset; GPT-5 models only accept default behavior.
            # We pin to 1 to match the supported default and avoid 400 unsupported_value errors.
            llm_kwargs["temperature"] = 1
            self.logger.info(
                "[openai] forcing temperature=1 for model=%s",
                self.model_name,
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
        self.polymarket = Polymarket()

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

    def _parse_probability_lines(self, text: str) -> "list[dict]":
        pattern = re.compile(
            r"likelihood\s*`?([0-9]*\.?[0-9]+)`?\s*for outcome of\s*`?['\"]?([^`'\"\n]+)['\"]?`?",
            re.IGNORECASE,
        )
        probabilities = []
        for match in pattern.finditer(text or ""):
            likelihood_raw = match.group(1)
            outcome = match.group(2).strip()
            try:
                likelihood = float(likelihood_raw)
            except ValueError:
                continue
            probabilities.append({"outcome": outcome, "likelihood": likelihood})
        return probabilities

    def _parse_trade_fields(self, text: str) -> dict:
        def extract(pattern: str) -> str:
            match = re.search(pattern, text or "", flags=re.IGNORECASE)
            return match.group(1).strip() if match else ""

        price = extract(r"price\s*[:=]\s*['`\"]?([0-9]*\.?[0-9]+)")
        size = extract(r"size\s*[:=]\s*['`\"]?([0-9]*\.?[0-9]+)")
        side = extract(r"side\s*[:=]\s*['`\"]?([A-Za-z]+)").upper()

        return {
            "price": price,
            "size": size,
            "side": side,
        }

    def _parse_literal_list(self, value) -> list:
        if isinstance(value, list):
            return value
        if not isinstance(value, str):
            return []
        try:
            parsed = ast.literal_eval(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []

    def get_llm_response(self, user_input: str) -> str:
        system_message = SystemMessage(content=str(self.prompter.market_analyst()))
        human_message = HumanMessage(content=user_input)
        messages = [system_message, human_message]
        return self._invoke_llm(messages, "get_llm_response")

    def get_superforecast(
        self, event_title: str, market_question: str, outcome: str
    ) -> str:
        prompt = self.prompter.superforecaster(
            description=event_title, question=market_question, outcome=outcome
        )
        return self._invoke_llm(prompt, "get_superforecast")


    def estimate_tokens(self, text: str) -> int:
        # This is a rough estimate. For more accurate results, consider using a tokenizer.
        return len(text) // 4  # Assuming average of 4 characters per token

    def process_data_chunk(self, data1: List[Dict[Any, Any]], data2: List[Dict[Any, Any]], user_input: str) -> str:
        system_message = SystemMessage(
            content=str(self.prompter.prompts_polymarket(data1=data1, data2=data2))
        )
        human_message = HumanMessage(content=user_input)
        messages = [system_message, human_message]
        return self._invoke_llm(messages, "process_data_chunk")


    def divide_list(self, original_list, i):
        # Calculate the size of each sublist
        sublist_size = math.ceil(len(original_list) / i)
        
        # Use list comprehension to create sublists
        return [original_list[j:j+sublist_size] for j in range(0, len(original_list), sublist_size)]
    
    def get_polymarket_llm(self, user_input: str) -> str:
        data1 = self.gamma.get_current_events()
        data2 = self.gamma.get_current_markets()
        
        combined_data = str(self.prompter.prompts_polymarket(data1=data1, data2=data2))
        
        # Estimate total tokens
        total_tokens = self.estimate_tokens(combined_data)
        
        # Set a token limit (adjust as needed, leaving room for system and user messages)
        token_limit = self.token_limit
        if total_tokens <= token_limit:
            # If within limit, process normally
            return self.process_data_chunk(data1, data2, user_input)
        else:
            # If exceeding limit, process in chunks
            chunk_size = len(combined_data) // ((total_tokens // token_limit) + 1)
            print(f'total tokens {total_tokens} exceeding llm capacity, now will split and answer')
            group_size = (total_tokens // token_limit) + 1 # 3 is safe factor
            keys_no_meaning = ['image','pagerDutyNotificationEnabled','resolvedBy','endDate','clobTokenIds','negRiskMarketID','conditionId','updatedAt','startDate']
            useful_keys = ['id','questionID','description','liquidity','clobTokenIds','outcomes','outcomePrices','volume','startDate','endDate','question','questionID','events']
            data1 = retain_keys(data1, useful_keys)
            cut_1 = self.divide_list(data1, group_size)
            cut_2 = self.divide_list(data2, group_size)
            cut_data_12 = zip(cut_1, cut_2)

            results = []

            for cut_data in cut_data_12:
                sub_data1 = cut_data[0]
                sub_data2 = cut_data[1]
                sub_tokens = self.estimate_tokens(str(self.prompter.prompts_polymarket(data1=sub_data1, data2=sub_data2)))

                result = self.process_data_chunk(sub_data1, sub_data2, user_input)
                results.append(result)
            
            combined_result = " ".join(results)
            
        
            
            return combined_result
    def filter_events(self, events: "list[SimpleEvent]") -> str:
        prompt = self.prompter.filter_events()
        return self._invoke_llm(prompt, "filter_events")

    def filter_events_with_rag(self, events: "list[SimpleEvent]") -> str:
        prompt = self.prompter.filter_events()
        print()
        print("... prompting ... ", prompt)
        print()
        return self.chroma.events(events, prompt)

    def map_filtered_events_to_markets(
        self, filtered_events: "list[SimpleEvent]"
    ) -> "list[SimpleMarket]":
        markets = []
        for e in filtered_events:
            data = json.loads(e[0].json())
            market_ids = data["metadata"]["markets"].split(",")
            for market_id in market_ids:
                if not market_id:
                    continue
                try:
                    market_data = self.gamma.get_market(market_id)
                    formatted_market_data = self.polymarket.map_api_to_market(market_data)
                    markets.append(formatted_market_data)
                except Exception as err:
                    print(f"[markets] skipped market_id={market_id} error={err}")
        return markets

    def filter_markets(self, markets) -> "list[tuple]":
        prompt = self.prompter.filter_markets()
        print()
        print("... prompting ... ", prompt)
        print()
        return self.chroma.markets(markets, prompt)

    def source_best_trade(self, market_object) -> dict:
        market_document = market_object[0].dict()
        market = market_document["metadata"]
        rag_score = market_object[1] if len(market_object) > 1 else None
        outcome_prices = self._parse_literal_list(market.get("outcome_prices", "[]"))
        outcomes = self._parse_literal_list(market.get("outcomes", "[]"))
        question = market["question"]
        description = market_document["page_content"]

        prompt = self.prompter.superforecaster(question, description, outcomes)
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
            superforecast_content,
            outcomes,
            outcome_prices,
        )
        print("... prompting ... ", prompt)
        print()
        trade_content = self._invoke_llm(prompt, "source_best_trade_action")

        print("result: ", trade_content)
        print()
        probabilities = self._parse_probability_lines(superforecast_content)
        parsed_trade = self._parse_trade_fields(trade_content)
        suggested_outcome = ""
        if probabilities:
            sorted_probs = sorted(
                probabilities,
                key=lambda item: item["likelihood"],
                reverse=True,
            )
            suggested_outcome = sorted_probs[0]["outcome"]

        return {
            "question": question,
            "outcomes": outcomes,
            "outcome_prices": outcome_prices,
            "rag_similarity_score": rag_score,
            "superforecast_response": superforecast_content,
            "trade_recommendation": trade_content,
            "probabilities": probabilities,
            "suggested_outcome": suggested_outcome,
            "parsed_trade": parsed_trade,
        }

    def format_trade_prompt_for_execution(self, best_trade) -> float:
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

        usdc_balance = self.polymarket.get_usdc_balance()
        return float(size) * usdc_balance

    def source_best_market_to_create(self, filtered_markets) -> str:
        prompt = self.prompter.create_new_market(filtered_markets)
        print()
        print("... prompting ... ", prompt)
        print()
        return self._invoke_llm(prompt, "source_best_market_to_create")
