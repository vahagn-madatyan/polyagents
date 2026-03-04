from typing import Optional

import typer
from devtools import pprint

from agents.polymarket.polymarket import Polymarket
from agents.connectors.chroma import PolymarketRAG
from agents.connectors.news import News
from agents.application.trade import Trader
from agents.application.executor import Executor
from agents.application.creator import Creator

app = typer.Typer()
polymarket = Polymarket(initialize_clob_client=False)
newsapi_client = News()
polymarket_rag = PolymarketRAG()


@app.command()
def get_all_markets(limit: int = 5, sort_by: str = "spread") -> None:
    """
    Query Polymarket's markets
    """
    print(f"limit: int = {limit}, sort_by: str = {sort_by}")
    markets = polymarket.get_all_markets()
    markets = polymarket.filter_markets_for_trading(markets)
    if sort_by == "spread":
        markets = sorted(markets, key=lambda x: x.spread, reverse=True)
    markets = markets[:limit]
    pprint(markets)


@app.command()
def get_relevant_news(
    keywords: str, limit: int = 10, days: int = 7, relevance: bool = False
) -> None:
    """
    Use NewsAPI to query the internet
    """
    articles, used_fallback = newsapi_client.get_articles_for_cli_keywords(
        keywords=keywords, limit=limit, days=days, relevance=relevance
    )
    if relevance:
        print(
            f"Using global relevance search in article bodies from the last {max(days, 1)} day(s)."
        )
    elif used_fallback:
        print(
            f"No US top headlines matched '{keywords}'. "
            f"Showing global results from the last {max(days, 1)} day(s)."
        )
    pprint(articles)


@app.command()
def get_all_events(limit: int = 5, sort_by: str = "number_of_markets") -> None:
    """
    Query Polymarket's events
    """
    print(f"limit: int = {limit}, sort_by: str = {sort_by}")
    events = polymarket.get_all_events()
    events = polymarket.filter_events_for_trading(events)
    if sort_by == "number_of_markets":
        events = sorted(events, key=lambda x: len(x.markets), reverse=True)
    events = events[:limit]
    pprint(events)


@app.command()
def create_local_markets_rag(local_directory: str) -> None:
    """
    Create a local markets database for RAG
    """
    polymarket_rag.create_local_markets_rag(local_directory=local_directory)


@app.command()
def query_local_markets_rag(vector_db_directory: str, query: str) -> None:
    """
    RAG over a local database of Polymarket's events
    """
    response = polymarket_rag.query_local_markets_rag(
        local_directory=vector_db_directory, query=query
    )
    pprint(response)


@app.command()
def ask_superforecaster(event_title: str, market_question: str, outcome: str) -> None:
    """
    Ask a superforecaster about a trade
    """
    print(
        f"event: str = {event_title}, question: str = {market_question}, outcome (usually yes or no): str = {outcome}"
    )
    executor = Executor()
    response = executor.get_superforecast(
        event_title=event_title, market_question=market_question, outcome=outcome
    )
    print(f"Response:{response}")


@app.command()
def create_market() -> None:
    """
    Format a request to create a market on Polymarket
    """
    c = Creator()
    market_description = c.one_best_market()
    print(f"market_description: str = {market_description}")


@app.command()
def ask_llm(user_input: str) -> None:
    """
    Ask a question to the LLM and get a response.
    """
    executor = Executor()
    response = executor.get_llm_response(user_input)
    print(f"LLM Response: {response}")


@app.command()
def ask_polymarket_llm(user_input: str) -> None:
    """
    What types of markets do you want trade?
    """
    executor = Executor()
    response = executor.get_polymarket_llm(user_input=user_input)
    print(f"LLM + current markets&events response: {response}")


@app.command()
def run_autonomous_trader(
    event_url: Optional[str] = None,
    include_news: bool = False,
    news_limit: int = 5,
    news_days: int = 7,
    news_relevance: bool = True,
    exclude_sports: bool = False,
) -> None:
    """
    Let an autonomous system trade for you.
    Optionally scope to a single event URL and/or inject recent news context.
    """
    trader = Trader()
    if event_url:
        trader.analyze_event_url(
            event_url=event_url,
            news_limit=news_limit,
            news_days=news_days,
            news_relevance=news_relevance,
            exclude_sports=exclude_sports,
        )
        return

    trader.one_best_trade(
        include_news=include_news,
        news_limit=news_limit,
        news_days=news_days,
        news_relevance=news_relevance,
        exclude_sports=exclude_sports,
    )


@app.command()
def diagnose_usdc_balance() -> None:
    """
    Print wallet and USDC balance diagnostics used by live trading mode.
    """
    pprint(polymarket.get_usdc_balance_report())


@app.command()
def analyze_event_url(
    event_url: str,
    news_limit: int = 5,
    news_days: int = 7,
    news_relevance: bool = True,
    exclude_sports: bool = False,
) -> None:
    """
    Run the prediction + trade suggestion pipeline for a specific Polymarket event URL.
    """
    trader = Trader()
    trader.analyze_event_url(
        event_url=event_url,
        news_limit=news_limit,
        news_days=news_days,
        news_relevance=news_relevance,
        exclude_sports=exclude_sports,
    )


@app.command()
def run_continuous(
    interval: int = 30,
    session_budget: float = 100.0,
    cooldown: int = 300,
    include_news: bool = False,
    exclude_sports: bool = False,
    news_limit: int = 5,
    news_days: int = 7,
    news_relevance: bool = True,
    volatility_threshold: float = 0.05,
) -> None:
    """
    Run continuous high-speed trading loop. Trades on trending and breaking events
    every INTERVAL seconds until session budget is exhausted or Ctrl+C.
    """
    from agents.application.continuous import start_continuous

    start_continuous(
        interval=interval,
        session_budget=session_budget,
        cooldown=cooldown,
        include_news=include_news,
        exclude_sports=exclude_sports,
        news_limit=news_limit,
        news_days=news_days,
        news_relevance=news_relevance,
        volatility_threshold=volatility_threshold,
    )


@app.command()
def run_crypto(
    interval: int = 30,
    session_budget: float = 100.0,
    symbols: str = "BTC,ETH,SOL,XRP",
    min_edge: float = 0.05,
) -> None:
    """
    Trade crypto price prediction markets using live WebSocket price feeds.
    Uses real-time BTC/ETH/SOL/XRP prices + LLM analysis to find mispriced markets.
    """
    from agents.application.crypto import start_crypto

    start_crypto(
        interval=interval,
        session_budget=session_budget,
        symbols=symbols,
        min_edge=min_edge,
    )


@app.command()
def run_crypto_arbitrage(
    session_budget: float = 50.0,
    max_per_trade: float = 5.0,
    min_edge: float = 0.10,
    price_feed_tolerance: float = 0.001,
) -> None:
    """
    Algorithmic BTC 5-minute interval market arbitrage. No LLM - pure price momentum.
    Uses dual Binance + Chainlink feeds for cross-validation.
    Runs on 15-second intervals to catch short-duration markets.
    """
    from agents.application.btc_arbitrage import start_btc_arbitrage

    start_btc_arbitrage(
        session_budget=session_budget,
        max_per_trade=max_per_trade,
        min_edge=min_edge,
        price_feed_tolerance=price_feed_tolerance,
    )


if __name__ == "__main__":
    app()
