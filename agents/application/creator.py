from agents.application.executor import Executor as Agent
from agents.polymarket.gamma import GammaMarketClient as Gamma
from agents.polymarket.polymarket import Polymarket


class Creator:
    def __init__(self):
        self.polymarket = Polymarket()
        self.gamma = Gamma()
        self.agent = Agent()

    def one_best_market(self):
        """

        one_best_trade is a strategy that evaluates all events, markets, and orderbooks

        leverages all available information sources accessible to the autonomous agent

        then executes that trade without any human intervention

        """
        try:
            events = self.polymarket.get_all_tradeable_events()
            print(f"1. FOUND {len(events)} EVENTS")
            if not events:
                print("No tradeable events found. Exiting run.")
                return None

            filtered_events = self.agent.filter_events_with_rag(events)
            print(f"2. FILTERED {len(filtered_events)} EVENTS")
            if not filtered_events:
                print("No events survived filtering. Exiting run.")
                return None

            markets = self.agent.map_filtered_events_to_markets(filtered_events)
            print()
            print(f"3. FOUND {len(markets)} MARKETS")
            if not markets:
                print("No markets found for filtered events. Exiting run.")
                return None

            print()
            filtered_markets = self.agent.filter_markets(markets)
            print(f"4. FILTERED {len(filtered_markets)} MARKETS")
            if not filtered_markets:
                print("No markets survived filtering. Exiting run.")
                return None

            best_market = self.agent.source_best_market_to_create(filtered_markets)
            print(f"5. IDEA FOR NEW MARKET {best_market}")
            return best_market

        except Exception as e:
            print(f"Error {e} \n \n Aborting")
            return None

    def maintain_positions(self):
        pass

    def incentive_farm(self):
        pass


if __name__ == "__main__":
    c = Creator()
    c.one_best_market()
