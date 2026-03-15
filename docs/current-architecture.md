# Current System Architecture

This document captures the current architecture implemented in this repository, including the RAG pipeline and all major runtime paths.

## 1) Full System Architecture

```mermaid
flowchart LR
    subgraph Entry["Entrypoints"]
        CLI["Typer CLI<br/>scripts/python/cli.py"]
        TradeMain["Script entry<br/>agents/application/trade.py"]
        CreatorMain["Script entry<br/>agents/application/creator.py"]
        API["FastAPI stub<br/>scripts/python/server.py"]
        Cron["Scheduler stub<br/>agents/application/cron.py"]
    end

    subgraph Core["Core Runtime Components"]
        Trader["Trader"]
        Creator["Creator"]
        Executor["Executor"]
        Prompter["Prompter"]
        Poly["Polymarket"]
        Gamma["GammaMarketClient"]
        RAG["PolymarketRAG (Chroma connector)"]
        News["News connector"]
        Search["Search connector (Tavily demo)"]
        Models["Pydantic models<br/>SimpleEvent / SimpleMarket / CandidateTrade / Article"]
    end

    subgraph Data["Local Persistent Data"]
        EvJSON["local_db_events/events.json"]
        MkJSON["local_db_markets/markets.json"]
        EvChroma["local_db_events/chroma<br/>chroma.sqlite3 + ANN files"]
        MkChroma["local_db_markets/chroma<br/>chroma.sqlite3 + ANN files"]
    end

    subgraph External["External Services"]
        OpenAI["OpenAI API<br/>Chat + text-embedding-3-small"]
        GammaAPI["Polymarket Gamma API<br/>/events /markets"]
        CLOB["Polymarket CLOB API"]
        Polygon["Polygon RPC"]
        NewsAPI["NewsAPI"]
        Tavily["Tavily API"]
    end

    CLI -->|"run-autonomous-trader"| Trader
    CLI -->|"create-market"| Creator
    CLI -->|"ask-llm / ask-superforecaster / ask-polymarket-llm"| Executor
    CLI -->|"get-all-markets / get-all-events"| Poly
    CLI -->|"get-relevant-news"| News
    CLI -->|"create-local-markets-rag / query-local-markets-rag"| RAG

    TradeMain --> Trader
    CreatorMain --> Creator
    Cron -.->|"intended periodic trigger"| Trader
    API -.->|"currently sample endpoints only"| Executor

    Trader --> Executor
    Trader --> Poly
    Creator --> Executor
    Creator --> Poly

    Executor --> Prompter
    Executor --> RAG
    Executor --> Gamma
    Executor --> OpenAI
    Executor --> Poly

    Poly --> GammaAPI
    Poly --> CLOB
    Poly --> Polygon
    Gamma --> GammaAPI
    News --> NewsAPI
    Search -.-> Tavily

    RAG --> EvJSON
    RAG --> MkJSON
    RAG --> EvChroma
    RAG --> MkChroma
    RAG --> OpenAI

    Trader --> Models
    Executor --> Models
    Poly --> Models
    News --> Models
```

## 2) End-to-End Autonomous Trading Sequence

```mermaid
sequenceDiagram
    autonumber
    actor U as "User"
    participant CLI as "CLI: run-autonomous-trader"
    participant T as "Trader.one_best_trade"
    participant P as "Polymarket"
    participant E as "Executor"
    participant R as "PolymarketRAG"
    participant G as "GammaMarketClient"
    participant O as "OpenAI"
    participant DE as "local_db_events/chroma"
    participant DM as "local_db_markets/chroma"
    participant A as "Gamma API"
    participant X as "Polygon RPC"
    participant C as "CLOB API"

    U->>CLI: run-autonomous-trader
    CLI->>T: one_best_trade()
    T->>T: clear_local_dbs()

    T->>P: get_all_tradeable_events()
    P->>A: GET /events (paginated)
    A-->>P: raw events
    P->>P: map + tradeable filtering
    P-->>T: list of SimpleEvent

    T->>E: filter_events_with_rag(events)
    E->>R: events(events, prompt, k)
    R->>R: write events.json + JSONLoader
    R->>O: embed descriptions
    R->>DE: persist Chroma index
    R-->>E: event docs + rag_score
    E-->>T: filtered events

    T->>E: map_filtered_events_to_markets()
    E->>G: get_markets_by_ids(ids)
    G->>A: GET /markets/{id} (concurrent)
    A-->>G: market payloads
    G-->>E: market payloads
    E->>E: map_api_to_market + quality filters
    E-->>T: candidate markets

    T->>E: filter_markets(markets)
    E->>R: markets(markets, prompt, k)
    R->>R: write markets.json + JSONLoader
    R->>O: embed descriptions
    R->>DM: persist Chroma index
    R-->>E: market docs + rag_score
    E-->>T: filtered markets

    T->>E: build_trade_candidates()
    loop per market
        E->>O: superforecaster prompt
        O-->>E: probability narrative
        E->>O: one_best_trade JSON prompt
        O-->>E: trade recommendation JSON/text
        E->>E: parse + confidence_gap + ranking
    end
    E->>E: select + allocate
    E-->>T: selected candidates

    T->>P: get_usdc_balance()
    P->>X: ERC20 balanceOf(wallet)
    X-->>P: USDC balance

    alt EXECUTE_TRADES=false
        T-->>U: dry-run summary table
    else EXECUTE_TRADES=true
        loop each selected candidate
            T->>P: resolve_token_for_outcome()
            T->>P: execute_market_order_for_token()
            P->>C: post FOK market order
            C-->>P: execution response
            P-->>T: status
        end
        T-->>U: executed summary table
    end
```

## 3) RAG Internals + Storage and DB

```mermaid
flowchart TB
    subgraph Prompt["Retriever Prompt Sources"]
        EP["Prompter.filter_events()"]
        MP["Prompter.filter_markets()"]
    end

    subgraph EventsLane["Event RAG Lane"]
        E1["Input: list of SimpleEvent"]
        E2["Write local_db_events/events.json"]
        E3["JSONLoader<br/>jq=.[]; content=description; metadata=id,markets"]
        E4["OpenAIEmbeddings<br/>text-embedding-3-small"]
        E5["Chroma.from_documents<br/>persist_directory=local_db_events/chroma"]
        E6["similarity_search_with_score<br/>k=max(25, TRADE_CANDIDATE_COUNT*5)"]
        E7["Output: top-k (Document, rag_score)"]
    end

    subgraph MarketsLane["Market RAG Lane"]
        M1["Input: list of SimpleMarket"]
        M2["Write local_db_markets/markets.json"]
        M3["JSONLoader<br/>jq=.[]; content=description; metadata=id,question,outcomes,outcome_prices,clob_token_ids,category,tags,event_*"]
        M4["OpenAIEmbeddings<br/>text-embedding-3-small"]
        M5["Chroma.from_documents<br/>persist_directory=local_db_markets/chroma"]
        M6["similarity_search_with_score<br/>k=TRADE_MAX_MARKETS_TO_SCORE"]
        M7["Output: top-k (Document, rag_score)"]
    end

    subgraph Disk["On-Disk Chroma Layout"]
        ES["local_db_events/chroma/chroma.sqlite3"]
        EA["local_db_events/chroma/<uuid>/*.bin + index_metadata.pickle"]
        MS["local_db_markets/chroma/chroma.sqlite3"]
        MA["local_db_markets/chroma/<uuid>/*.bin + index_metadata.pickle"]
    end

    EP --> E6
    MP --> M6

    E1 --> E2 --> E3 --> E4 --> E5 --> E6 --> E7
    M1 --> M2 --> M3 --> M4 --> M5 --> M6 --> M7

    E5 --> ES
    E5 --> EA
    M5 --> MS
    M5 --> MA
```

## 4) CLI and Non-Autonomous Flows

```mermaid
flowchart LR
    CLI["python scripts/python/cli.py <command>"]

    subgraph Cmds["CLI Commands"]
        C1["get-all-markets"]
        C2["get-all-events"]
        C3["get-relevant-news"]
        C4["create-local-markets-rag"]
        C5["query-local-markets-rag"]
        C6["ask-llm"]
        C7["ask-superforecaster"]
        C8["ask-polymarket-llm"]
        C9["create-market"]
        C10["run-autonomous-trader"]
    end

    subgraph Handlers["Main Handler Paths"]
        H1["Polymarket.get_all_markets + filter/sort"]
        H2["Polymarket.get_all_events + filter/sort"]
        H3["News connector<br/>top-headlines fallback everything<br/>optional relevance mode"]
        H4["PolymarketRAG.create_local_markets_rag<br/>Gamma current markets -> local Chroma"]
        H5["PolymarketRAG.query_local_markets_rag<br/>similarity_search_with_score"]
        H6["Executor.get_llm_response"]
        H7["Executor.get_superforecast"]
        H8["Executor.get_polymarket_llm<br/>Gamma current events/markets -> chunked LLM call"]
        H9["Creator.one_best_market<br/>RAG filter -> LLM new market idea"]
        H10["Trader.one_best_trade<br/>full autonomous trading pipeline"]
    end

    CLI --> C1 --> H1
    CLI --> C2 --> H2
    CLI --> C3 --> H3
    CLI --> C4 --> H4
    CLI --> C5 --> H5
    CLI --> C6 --> H6
    CLI --> C7 --> H7
    CLI --> C8 --> H8
    CLI --> C9 --> H9
    CLI --> C10 --> H10
```

## Notes

- RAG database backend in this repo is local Chroma persistence (SQLite metadata + ANN index files), not Postgres/pgvector.
- `scripts/python/server.py` and `agents/application/cron.py` are currently stubs and are not wired into production trading flow by default.
