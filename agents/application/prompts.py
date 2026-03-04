from typing import List
from datetime import datetime


class Prompter:

    def generate_simple_ai_trader(market_description: str, relevant_info: str) -> str:
        return f"""
            
        You are a trader.
        
        Here is a market description: {market_description}.

        Here is relevant information: {relevant_info}.

        Do you buy or sell? How much?
        """

    def market_analyst(self) -> str:
        return f"""
        You are a market analyst that takes a description of an event and produces a market forecast. 
        Assign a probability estimate to the event occurring described by the user
        """

    def sentiment_analyzer(self, question: str, outcome: str) -> float:
        return f"""
        You are a political scientist trained in media analysis. 
        You are given a question: {question}.
        and an outcome of yes or no: {outcome}.
        
        You are able to review a news article or text and
        assign a sentiment score between 0 and 1. 
        
        """

    def prompts_polymarket(
        self, data1: str, data2: str, market_question: str, outcome: str
    ) -> str:
        current_market_data = str(data1)
        current_event_data = str(data2)
        return f"""
        You are an AI assistant for users of a prediction market called Polymarket.
        Users want to place bets based on their beliefs of market outcomes such as political or sports events.
        
        Here is data for current Polymarket markets {current_market_data} and 
        current Polymarket events {current_event_data}.

        Help users identify markets to trade based on their interests or queries.
        Provide specific information for markets including probabilities of outcomes.
        Give your response in the following format:

        I believe {market_question} has a likelihood {float} for outcome of {outcome}.
        """

    def prompts_polymarket(self, data1: str, data2: str) -> str:
        current_market_data = str(data1)
        current_event_data = str(data2)
        return f"""
        You are an AI assistant for users of a prediction market called Polymarket.
        Users want to place bets based on their beliefs of market outcomes such as political or sports events.

        Here is data for current Polymarket markets {current_market_data} and 
        current Polymarket events {current_event_data}.
        Help users identify markets to trade based on their interests or queries.
        Provide specific information for markets including probabilities of outcomes.
        """

    def routing(self, system_message: str) -> str:
        return f"""You are an expert at routing a user question to the appropriate data source. System message: ${system_message}"""

    def multiquery(self, question: str) -> str:
        return f"""
        You're an AI assistant. Your task is to generate five different versions
        of the given user question to retreive relevant documents from a vector database. By generating
        multiple perspectives on the user question, your goal is to help the user overcome some of the limitations
        of the distance-based similarity search.
        Provide these alternative questions separated by newlines. Original question: {question}

        """

    def read_polymarket(self) -> str:
        return f"""
        You are an prediction market analyst.
        """

    def polymarket_analyst_api(self) -> str:
        return f"""You are an AI assistant for analyzing prediction markets.
                You will be provided with json output for api data from Polymarket.
                Polymarket is an online prediction market that lets users Bet on the outcome of future events in a wide range of topics, like sports, politics, and pop culture. 
                Get accurate real-time probabilities of the events that matter most to you. """

    def filter_events(self) -> str:
        return (
            self.polymarket_analyst_api()
            + f"""
        
        Filter these events for the ones you will be best at trading on profitably.

        """
        )

    def filter_markets(self) -> str:
        return (
            self.polymarket_analyst_api()
            + f"""
        
        Filter these markets for the ones you will be best at trading on profitably.
        Prefer markets with meaningful volume and liquidity.
        Avoid dead/illiquid markets and avoid outcomes priced at extreme tails (near 0 or near 1) unless justified by clear edge.

        """
        )

    def superforecaster(self, question: str, description: str, outcome: str) -> str:
        return f"""
        You are a Superforecaster tasked with correctly predicting the likelihood of events.
        Use the following systematic process to develop an accurate prediction for the following
        question=`{question}` and description=`{description}` combination. 
        
        Here are the key steps to use in your analysis:

        1. Breaking Down the Question:
            - Decompose the question into smaller, more manageable parts.
            - Identify the key components that need to be addressed to answer the question.
        2. Gathering Information:
            - Seek out diverse sources of information.
            - Look for both quantitative data and qualitative insights.
            - Stay updated on relevant news and expert analyses.
        3. Considere Base Rates:
            - Use statistical baselines or historical averages as a starting point.
            - Compare the current situation to similar past events to establish a benchmark probability.
        4. Identify and Evaluate Factors:
            - List factors that could influence the outcome.
            - Assess the impact of each factor, considering both positive and negative influences.
            - Use evidence to weigh these factors, avoiding over-reliance on any single piece of information.
        5. Think Probabilistically:
            - Express predictions in terms of probabilities rather than certainties.
            - Assign likelihoods to different outcomes and avoid binary thinking.
            - Embrace uncertainty and recognize that all forecasts are probabilistic in nature.
        
        Given these steps produce a statement on the probability of outcome=`{outcome}` occuring.

        Give your response in the following format:

        I believe {question} has a likelihood `{float}` for outcome of `{str}`.
        """

    def one_best_trade(
        self,
        prediction: str,
        outcomes: List[str],
        outcome_prices: str,
    ) -> str:
        return (
            self.polymarket_analyst_api()
            + f"""
        You made the following prediction for a market:
        {prediction}

        The current outcomes are {outcomes}.
        The current outcome prices are {outcome_prices}.

        Return JSON only (no markdown, no prose outside JSON) using this schema:
        {{
          "probabilities": [
            {{"outcome": "<string>", "likelihood": <float between 0 and 1>}}
          ],
          "selected_outcome": "<string outcome from outcomes>",
          "side": "<BUY or SELL>",
          "price": <float between 0 and 1>,
          "size_fraction": <float between 0 and 1>,
          "rationale": "<short concise reasoning summary>",
          "risk_factors": ["<short risk factor 1>", "<short risk factor 2>"],
          "counter_case": "<short concise opposing view>"
        }}

        Constraints:
        - Keep rationale and counter_case concise (1-2 sentences each).
        - Provide at most 3 risk_factors.
        - Probabilities should correspond to listed outcomes and sum close to 1.
        - Do not output hidden chain-of-thought. Output only concise summaries.
        """
        )

    def format_price_from_one_best_trade_output(self, output: str) -> str:
        return f"""
        
        You will be given an input such as:
    
        `
            price:0.5,
            size:0.1,
            side:BUY,
        `

        Please extract only the value associated with price.
        In this case, you would return "0.5".

        Only return the number after price:
        
        """

    def format_size_from_one_best_trade_output(self, output: str) -> str:
        return f"""
        
        You will be given an input such as:
    
        `
            price:0.5,
            size:0.1,
            side:BUY,
        `

        Please extract only the value associated with price.
        In this case, you would return "0.1".

        Only return the number after size:
        
        """

    def crypto_price_analyst(
        self,
        symbol: str,
        current_price: float,
        target_price: float,
        direction: str,
        momentum_1m: float,
        momentum_5m: float,
        momentum_15m: float,
        time_remaining_hours: float,
        market_yes_price: float,
        market_no_price: float,
    ) -> str:
        return (
            self.polymarket_analyst_api()
            + f"""
        You are analyzing a crypto price prediction market.

        Asset: {symbol}
        Current live price: ${current_price:,.2f}
        Market question: Will {symbol} be {direction} ${target_price:,.2f}?
        Time remaining: {time_remaining_hours:.1f} hours

        Live price momentum:
        - 1-minute momentum: {momentum_1m:+.4f} ({momentum_1m*100:+.2f}%)
        - 5-minute momentum: {momentum_5m:+.4f} ({momentum_5m*100:+.2f}%)
        - 15-minute momentum: {momentum_15m:+.4f} ({momentum_15m*100:+.2f}%)

        Current market odds:
        - Yes price: {market_yes_price:.4f} (implied {market_yes_price*100:.1f}% probability)
        - No price: {market_no_price:.4f} (implied {market_no_price*100:.1f}% probability)

        Distance to target: {abs(current_price - target_price) / current_price * 100:.2f}% {'above' if current_price > target_price else 'below'} target

        Based on the live price data, momentum, and market odds, is this market mispriced?
        Return JSON only (no markdown, no prose outside JSON) using this schema:
        {{
          "probabilities": [
            {{"outcome": "Yes", "likelihood": <float between 0 and 1>}},
            {{"outcome": "No", "likelihood": <float between 0 and 1>}}
          ],
          "selected_outcome": "<Yes or No>",
          "side": "<BUY or SELL>",
          "price": <float between 0 and 1>,
          "size_fraction": <float between 0 and 1>,
          "rationale": "<short concise reasoning based on price data and momentum>",
          "risk_factors": ["<risk 1>", "<risk 2>"],
          "counter_case": "<short opposing view>"
        }}
        """
        )

    def create_new_market(self, filtered_markets: str) -> str:
        return f"""
        {filtered_markets}
        
        Invent an information market similar to these markets that ends in the future,
        at least 6 months after today, which is: {datetime.today().strftime('%Y-%m-%d')},
        so this date plus 6 months at least.

        Output your format in:
        
        Question: "..."?
        Outcomes: A or B

        With ... filled in and A or B options being the potential results.
        For example:

        Question: "Will Kamala win"
        Outcomes: Yes or No
        
        """
