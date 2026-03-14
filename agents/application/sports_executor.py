"""SportsExecutor — two-stage LLM analysis for sports games.

Mirrors the Executor.source_best_trade() pattern but tailored for sports:
- Stage 1: sports_superforecaster() — blind probability estimate from team data
- Stage 2: sports_trade_decision() — trade action with Polymarket price and divergence signal

Does NOT import Executor, Chroma, Gamma, or Polymarket to avoid the heavy dependency chain.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from langchain_openai import ChatOpenAI

from agents.application.prompts import Prompter
from agents.utils.env import _env_bool, _env_float, _env_int
from agents.utils.objects import CandidateTrade, SportGameState, SportsMarketTag


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class SportsExecutor:
    """Two-stage LLM analysis executor for sports games.

    Stage 1 (superforecaster): Builds a blind probability estimate from team stats,
    H2H records, and external bookmaker odds — NO Polymarket prices.

    Stage 2 (trade_decision): Incorporates Polymarket prices and value-bet divergence
    to produce a structured JSON trade recommendation.
    """

    def __init__(self) -> None:
        configured_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.model_name = configured_model

        llm_kwargs = {"model": self.model_name}
        supports_custom_temperature = not self.model_name.lower().startswith("gpt-5")
        if not supports_custom_temperature:
            # GPT-5 models only accept default temperature behavior via value 1.
            llm_kwargs["temperature"] = 1
            print(
                f"[sports_executor] forcing temperature=1 for model={self.model_name}"
            )
        else:
            temp_value = os.getenv("OPENAI_TEMPERATURE")
            if temp_value is not None and temp_value != "":
                try:
                    llm_kwargs["temperature"] = float(temp_value)
                except ValueError:
                    print(
                        f"[sports_executor] invalid OPENAI_TEMPERATURE={temp_value!r}, using model default"
                    )

        self.llm = ChatOpenAI(**llm_kwargs)
        self.prompter = Prompter()

    def _invoke_llm(self, payload, operation_name: str) -> str:
        """Call self.llm.invoke(payload) and return result.content."""
        result = self.llm.invoke(payload)
        model_name = getattr(self, "model_name", "unknown")
        print(f"[sports_executor] op={operation_name} model={model_name}")
        return result.content

    def _parse_outcome_prices(self, prices_str: Optional[str]) -> list[float]:
        """Parse SportsMarketTag.outcome_prices (comma-separated string) into [float, float].

        Returns [0.5, 0.5] if prices_str is None or malformed.
        """
        if not prices_str:
            return [0.5, 0.5]
        try:
            parts = [p.strip() for p in prices_str.split(",")]
            parsed = [float(p) for p in parts if p]
            if len(parsed) >= 2:
                return [parsed[0], parsed[1]]
            if len(parsed) == 1:
                return [parsed[0], 1.0 - parsed[0]]
        except (ValueError, TypeError):
            pass
        return [0.5, 0.5]

    def _parse_json_object(self, text: str) -> dict:
        """Extract JSON object from LLM response text.

        Strips markdown code blocks if present. Returns {} on parse failure.
        Same logic as Executor._parse_json_object() — reimplemented to avoid importing Executor.
        """
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

    def _parse_trade_fields(self, text: str) -> dict:
        """Regex fallback for extracting side/price/size from LLM response.

        Used when JSON parse fails. Same approach as Executor._parse_trade_fields().
        """

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

    def analyze_game(
        self,
        game_state: SportGameState,
        market_tag: SportsMarketTag,
        game_context: dict,
    ) -> Optional[CandidateTrade]:
        """Run two-stage LLM analysis and return a CandidateTrade.

        Stage 1: sports_superforecaster() — blind probability estimate
        Stage 2: sports_trade_decision() — trade recommendation with Polymarket prices

        Returns None on any error (LLM failure, JSON parse failure, etc.).
        """
        try:
            outcome_prices = self._parse_outcome_prices(market_tag.outcome_prices)
            outcomes = ["Yes", "No"]

            # Stage 1: blind probability estimate
            stage1_payload = self.prompter.sports_superforecaster(
                game_state, game_context
            )
            stage1_result = self._invoke_llm(stage1_payload, "sports_superforecaster")

            # Stage 2: trade decision with Polymarket prices
            stage2_payload = self.prompter.sports_trade_decision(
                prediction=stage1_result,
                game_state=game_state,
                game_context=game_context,
                outcomes=outcomes,
                outcome_prices=outcome_prices,
                polymarket_price=outcome_prices[0],
            )
            stage2_result = self._invoke_llm(stage2_payload, "sports_trade_decision")

            # Parse JSON from stage 2 response
            trade_json = self._parse_json_object(stage2_result)
            regex_trade = self._parse_trade_fields(stage2_result)

            # Extract parsed fields
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
                parsed_price = outcome_prices[0]

            parsed_size_fraction = trade_json.get("size_fraction")
            if parsed_size_fraction is None:
                parsed_size_fraction = regex_trade.get("size")
            parsed_size_fraction = _safe_float(parsed_size_fraction, default=-1.0)
            if parsed_size_fraction < 0:
                parsed_size_fraction = None

            selected_outcome = str(trade_json.get("selected_outcome", "")).strip()
            if not selected_outcome:
                selected_outcome = outcomes[0]

            rationale = str(trade_json.get("rationale", "")).strip()

            risk_factors = trade_json.get("risk_factors", [])
            if not isinstance(risk_factors, list):
                risk_factors = []
            risk_factors = [
                str(item).strip() for item in risk_factors if str(item).strip()
            ]

            counter_case = str(trade_json.get("counter_case", "")).strip()

            # Parse probabilities
            raw_probs = trade_json.get("probabilities", [])
            probabilities = []
            if isinstance(raw_probs, list):
                for item in raw_probs:
                    if not isinstance(item, dict):
                        continue
                    outcome = str(item.get("outcome", "")).strip()
                    likelihood = _safe_float(item.get("likelihood"), default=-1.0)
                    if not outcome or likelihood < 0:
                        continue
                    probabilities.append(
                        {
                            "outcome": outcome,
                            "likelihood": max(0.0, min(1.0, likelihood)),
                        }
                    )

            # Confidence gap: max(probs) - second highest
            confidence_gap = 0.0
            if len(probabilities) >= 2:
                values = sorted(
                    [_safe_float(p.get("likelihood"), 0.0) for p in probabilities],
                    reverse=True,
                )
                confidence_gap = max(0.0, values[0] - values[1])

            return CandidateTrade(
                market_id=int(market_tag.market_id),
                question=market_tag.question,
                category_bucket="sports",
                outcomes=outcomes,
                outcome_prices=outcome_prices,
                token_ids=[market_tag.token_id_yes, market_tag.token_id_no],
                probabilities=probabilities,
                suggested_outcome=selected_outcome,
                parsed_side=parsed_side,
                parsed_price=parsed_price,
                parsed_size_fraction=parsed_size_fraction,
                confidence_gap=confidence_gap,
                rationale=rationale,
                risk_factors=risk_factors,
                counter_case=counter_case,
                execution_status="NOT_EXECUTED",
                execution_response={
                    "superforecast_response": stage1_result,
                    "trade_recommendation": stage2_result,
                },
            )

        except Exception as exc:
            print(
                f"[sports_executor] error analyzing game_id={game_state.game_id} error={exc}"
            )
            return None
