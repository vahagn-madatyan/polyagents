from agents.application.executor import Executor as Agent
from agents.polymarket.gamma import GammaMarketClient as Gamma
from agents.polymarket.polymarket import Polymarket

import shutil
import os


class Trader:
    def __init__(self):
        self.polymarket = Polymarket()
        self.gamma = Gamma()
        self.agent = Agent()
        self.execute_trades = (
            str(os.getenv("EXECUTE_TRADES", "false")).strip().lower()
            in ("1", "true", "yes", "on")
        )

    def pre_trade_logic(self) -> None:
        self.clear_local_dbs()

    def clear_local_dbs(self) -> None:
        try:
            shutil.rmtree("local_db_events")
        except:
            pass
        try:
            shutil.rmtree("local_db_markets")
        except:
            pass

    def _truncate(self, value, max_len: int = 140) -> str:
        text = str(value)
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    def _format_probabilities(self, probabilities: list) -> str:
        if not probabilities:
            return "n/a"
        parts = []
        for item in probabilities:
            outcome = item.get("outcome", "unknown")
            likelihood = item.get("likelihood")
            try:
                likelihood_str = f"{float(likelihood):.6f}"
            except (TypeError, ValueError):
                likelihood_str = str(likelihood)
            parts.append(f"{outcome}={likelihood_str}")
        return "; ".join(parts)

    def _confidence_gap(self, probabilities: list) -> str:
        if len(probabilities) < 2:
            return "n/a"
        try:
            sorted_probs = sorted(
                probabilities,
                key=lambda item: float(item.get("likelihood", 0.0)),
                reverse=True,
            )
            gap = float(sorted_probs[0]["likelihood"]) - float(sorted_probs[1]["likelihood"])
            return f"{gap:.6f}"
        except (TypeError, ValueError, KeyError):
            return "n/a"

    def _print_trade_summary(
        self,
        summary: dict,
        mode: str,
        execution_result: str = "",
    ) -> None:
        parsed_trade = summary.get("parsed_trade", {})
        outcomes = summary.get("outcomes", [])
        outcome_prices = summary.get("outcome_prices", [])
        outcome_price_pairs = []
        for index, outcome in enumerate(outcomes):
            price = outcome_prices[index] if index < len(outcome_prices) else "n/a"
            outcome_price_pairs.append(f"{outcome}:{price}")

        rows = [
            ("Market", self._truncate(summary.get("question", "n/a"))),
            ("Suggested Outcome", summary.get("suggested_outcome", "n/a")),
            ("AI Probabilities", self._truncate(self._format_probabilities(summary.get("probabilities", [])))),
            ("Confidence Gap", self._confidence_gap(summary.get("probabilities", []))),
            ("Order Side", parsed_trade.get("side", "n/a") or "n/a"),
            ("Order Price", parsed_trade.get("price", "n/a") or "n/a"),
            ("Size (% funds)", parsed_trade.get("size", "n/a") or "n/a"),
            ("Book Prices", self._truncate(", ".join(outcome_price_pairs) if outcome_price_pairs else "n/a")),
            ("RAG Score", summary.get("rag_similarity_score", "n/a")),
            ("Mode", mode),
        ]
        if execution_result:
            rows.append(("Execution", self._truncate(execution_result)))

        key_width = max(max(len("Metric"), *(len(str(k)) for k, _ in rows)), 6)
        value_width = max(max(len("Value"), *(len(str(v)) for _, v in rows)), 5)
        border = f"+-{'-' * key_width}-+-{'-' * value_width}-+"

        print()
        print(border)
        print(f"| {'Metric'.ljust(key_width)} | {'Value'.ljust(value_width)} |")
        print(border)
        for key, value in rows:
            print(f"| {str(key).ljust(key_width)} | {str(value).ljust(value_width)} |")
        print(border)
        print()

    def one_best_trade(self) -> None:
        """

        one_best_trade is a strategy that evaluates all events, markets, and orderbooks

        leverages all available information sources accessible to the autonomous agent

        then executes that trade without any human intervention

        """
        try:
            self.pre_trade_logic()

            events = self.polymarket.get_all_tradeable_events()
            print(f"1. FOUND {len(events)} EVENTS")
            if not events:
                print("No tradeable events found. Exiting run.")
                return

            filtered_events = self.agent.filter_events_with_rag(events)
            print(f"2. FILTERED {len(filtered_events)} EVENTS")
            if not filtered_events:
                print("No events survived filtering. Exiting run.")
                return

            markets = self.agent.map_filtered_events_to_markets(filtered_events)
            print()
            print(f"3. FOUND {len(markets)} MARKETS")
            if not markets:
                print("No markets found for filtered events. Exiting run.")
                return

            print()
            filtered_markets = self.agent.filter_markets(markets)
            print(f"4. FILTERED {len(filtered_markets)} MARKETS")
            if not filtered_markets:
                print("No markets survived filtering. Exiting run.")
                return

            market = filtered_markets[0]
            best_trade = self.agent.source_best_trade(market)
            print(f"5. CALCULATED TRADE {best_trade.get('trade_recommendation', 'n/a')}")

            if not self.execute_trades:
                self._print_trade_summary(best_trade, mode="DRY_RUN")
                print("6. DRY RUN complete (set EXECUTE_TRADES=true to place an order).")
                return

            amount = self.agent.format_trade_prompt_for_execution(best_trade)
            # Please refer to TOS before enabling trade execution: polymarket.com/tos
            trade = self.polymarket.execute_market_order(market, amount)
            self._print_trade_summary(
                best_trade,
                mode="EXECUTED",
                execution_result=f"amount={amount}, response={trade}",
            )
            print(f"6. TRADED {trade}")

        except Exception as e:
            print(f"Error {e} \n \n Aborting")
            return

    def maintain_positions(self):
        pass

    def incentive_farm(self):
        pass


if __name__ == "__main__":
    t = Trader()
    t.one_best_trade()
