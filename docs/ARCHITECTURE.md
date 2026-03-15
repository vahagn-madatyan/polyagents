# Polyagents Architecture

## System Overview

```mermaid
graph TB
    subgraph Entry["Entry Points"]
        CLI["CLI<br/>scripts/python/cli.py"]
        SPORTS_MAIN["Sports Main<br/>agents/sports.py"]
        DOCKER["Docker Container"]
    end

    subgraph Pipelines["Trading Pipelines"]
        BATCH["Batch Trader<br/>trade.py"]
        CONTINUOUS["Continuous Strategy<br/>continuous.py"]
        CRYPTO["Crypto Strategy<br/>crypto.py"]
        ARB["BTC Arbitrage<br/>btc_arbitrage.py"]
        SPORTS_PRE["Sports Pre-Game<br/>sports_trader.py"]
        INGAME["In-Game Trader<br/>ingame_trader.py"]
    end

    subgraph Core["Core Engine"]
        EXECUTOR["LLM Executor<br/>executor.py"]
        SPORTS_EXEC["Sports Executor<br/>sports_executor.py"]
        BUDGET["Budget Manager<br/>budget.py"]
        RUNNER["Async Runner<br/>runner.py"]
        PROMPTS["Prompt Templates<br/>prompts.py"]
    end

    subgraph Connectors["Connectors"]
        GAMMA["Gamma API Client<br/>gamma.py"]
        POLY_CLOB["Polymarket CLOB<br/>polymarket.py"]
        CHROMA["Chroma RAG<br/>chroma.py"]
        NEWS["News Connector<br/>news.py"]
        SEARCH["Web Search<br/>search.py"]
        SPORTS_WS["Sports WebSocket<br/>sports_ws.py"]
        SPORTS_DATA["Sports Data<br/>sports_data.py"]
        WS["Price WebSocket<br/>websocket.py"]
    end

    subgraph External["External Services"]
        PM_GAMMA["Polymarket Gamma API"]
        PM_CLOB["Polymarket CLOB API"]
        PM_WS["Polymarket Sports WS"]
        OPENAI["OpenAI API"]
        API_SPORTS["API-Sports"]
        ODDS_API["The Odds API"]
        NEWS_API["NewsAPI"]
        POLYGON["Polygon RPC"]
    end

    subgraph Storage["Data Stores"]
        CHROMA_DB["ChromaDB<br/>(Vector Store)"]
        PREGAME_CACHE["Pregame Cache<br/>(JSON + FileLock)"]
        BUDGET_FILE["Budget State<br/>(JSON + FileLock)"]
        WALLET["USDC Wallet<br/>(On-Chain)"]
    end

    CLI --> BATCH & CONTINUOUS & CRYPTO & ARB
    SPORTS_MAIN --> SPORTS_PRE & INGAME
    DOCKER --> CLI & SPORTS_MAIN

    BATCH --> EXECUTOR & BUDGET
    CONTINUOUS --> EXECUTOR & RUNNER & BUDGET
    CRYPTO --> EXECUTOR & RUNNER & WS
    ARB --> WS
    SPORTS_PRE --> SPORTS_EXEC & BUDGET
    INGAME --> SPORTS_EXEC & SPORTS_WS & BUDGET

    EXECUTOR --> GAMMA & CHROMA & NEWS & SEARCH & PROMPTS
    SPORTS_EXEC --> SPORTS_DATA & PROMPTS
    BUDGET --> BUDGET_FILE

    GAMMA --> PM_GAMMA
    POLY_CLOB --> PM_CLOB & POLYGON
    CHROMA --> CHROMA_DB & OPENAI
    NEWS --> NEWS_API
    SPORTS_WS --> PM_WS
    SPORTS_DATA --> API_SPORTS & ODDS_API
    WS --> PM_CLOB

    EXECUTOR --> OPENAI
    SPORTS_EXEC --> OPENAI
    SPORTS_PRE --> PREGAME_CACHE
    INGAME --> PREGAME_CACHE

    BATCH --> POLY_CLOB
    CONTINUOUS --> POLY_CLOB
    CRYPTO --> POLY_CLOB
    ARB --> POLY_CLOB
    SPORTS_PRE --> POLY_CLOB
    INGAME --> POLY_CLOB
    POLY_CLOB --> WALLET
```

## Data Flow: Batch Trading Pipeline

```mermaid
sequenceDiagram
    participant CLI
    participant Trader
    participant Gamma as Gamma API
    participant RAG as Chroma RAG
    participant LLM as OpenAI LLM
    participant News as NewsAPI
    participant Budget
    participant CLOB as Polymarket CLOB

    CLI->>Trader: run-autonomous-trader
    Trader->>Gamma: get_all_tradeable_events()
    Gamma-->>Trader: PolymarketEvent[]

    Trader->>RAG: filter_events_with_rag()
    RAG-->>Trader: Filtered events

    Trader->>Gamma: map_to_markets()
    Gamma-->>Trader: Market[]

    loop For each candidate market
        Trader->>News: get_articles(keywords)
        News-->>Trader: Article[]
        Trader->>LLM: Stage 1 - Superforecaster (blind probability)
        LLM-->>Trader: Unbiased probability estimate
        Trader->>LLM: Stage 2 - Trade Decision (with market prices)
        LLM-->>Trader: CandidateTrade (side, size, confidence)
    end

    Trader->>Budget: allocate_budget(candidates)
    Budget-->>Trader: Allocated CandidateTrade[]

    loop For each allocated trade
        Trader->>CLOB: execute_market_order()
        CLOB-->>Trader: Order confirmation
    end
```

## Data Flow: Sports In-Game Pipeline

```mermaid
sequenceDiagram
    participant WS as Sports WebSocket
    participant Queue as asyncio.Queue
    participant IGT as InGameTrader
    participant Cache as PregameCache
    participant Exec as SportsExecutor
    participant LLM as OpenAI LLM
    participant Budget
    participant CLOB as Polymarket CLOB

    WS->>Queue: SportGameState (score update)
    Queue->>IGT: tick(game_state)

    alt Score delta > threshold
        IGT->>Cache: lookup(game_id)
        Cache-->>IGT: SportsAnalysisCache
        IGT->>IGT: Fast-path: cache prob vs live price
    else Full re-analysis needed
        IGT->>Exec: asyncio.to_thread(analyze)
        Exec->>LLM: Sports superforecaster + trade decision
        LLM-->>Exec: Updated probabilities
        Exec-->>IGT: CandidateTrade
    end

    IGT->>IGT: Check cooldown (60s per game)
    IGT->>IGT: Check exposure cap (5% per game)
    IGT->>Budget: check_remaining()
    Budget-->>IGT: OK

    IGT->>CLOB: execute_market_order()
    CLOB-->>IGT: Order confirmation
```

## Data Model Transformations

```mermaid
flowchart LR
    subgraph Discovery
        SE[SimpleEvent/<br/>PolymarketEvent]
        SM[SimpleMarket/<br/>Market]
    end

    subgraph Analysis
        CT[CandidateTrade<br/>probabilities, rationale,<br/>confidence, allocation]
    end

    subgraph Execution
        OA[OrderArgs<br/>py-clob-client]
        OID[CLOB Order ID]
        TR[Trade<br/>on-chain settlement]
    end

    subgraph Sports["Sports Extensions"]
        SGS[SportGameState<br/>game_id, score, period]
        SMT[SportsMarketTag<br/>game → market mapping]
        SAC[SportsAnalysisCache<br/>cached LLM analysis]
    end

    SE -->|map to markets| SM
    SM -->|LLM scoring| CT
    CT -->|budget allocation| OA
    OA -->|sign + submit| OID
    OID -->|settlement| TR

    SGS -->|market lookup| SMT
    SMT -->|stats + odds| CT
    CT -->|persist| SAC
    SAC -->|in-game reuse| CT
```

## Two-Stage LLM Analysis Pattern

```mermaid
flowchart TB
    subgraph Stage1["Stage 1: Blind Probability"]
        CTX1[Event description<br/>+ news context<br/>+ base rates]
        SF[Superforecaster Prompt<br/>NO market prices shown]
        PROB[Unbiased probability<br/>estimate]
    end

    subgraph Stage2["Stage 2: Market-Aware Decision"]
        CTX2[Stage 1 probability<br/>+ Polymarket prices<br/>+ spread / volume]
        TD[Trade Decision Prompt]
        TRADE[Side / Size / Confidence<br/>+ Rationale]
    end

    CTX1 --> SF --> PROB
    PROB --> CTX2 --> TD --> TRADE

    style Stage1 fill:#e8f4f8,stroke:#2196F3
    style Stage2 fill:#fff3e0,stroke:#FF9800
```

## Budget Architecture

```mermaid
flowchart TB
    WALLET["USDC Wallet<br/>(on-chain balance)"]

    subgraph Coordination["BudgetCoordinator<br/>(cross-process, file-locked)"]
        SPLIT{Budget Split}
        SF["Sports Fraction<br/>default 30%"]
        GF["General Fraction<br/>default 70%"]
    end

    subgraph Sports["Sports SessionBudgetManager"]
        SB[Sports Budget Pool]
        PG[Per-game exposure cap<br/>max 5% of pool]
        CD[Per-game cooldown<br/>min 60s between trades]
    end

    subgraph General["General SessionBudgetManager"]
        GB[General Budget Pool]
        PM[Per-market cooldown<br/>300s between trades]
        CAT[Category diversification<br/>min/max per bucket]
    end

    WALLET --> SPLIT
    SPLIT --> SF --> SB
    SPLIT --> GF --> GB
    SB --> PG & CD
    GB --> PM & CAT

    style Coordination fill:#f3e5f5,stroke:#9C27B0
```

## Connector Layer & External Services

```mermaid
flowchart LR
    subgraph Connectors
        G[Gamma Client]
        P[CLOB Client]
        C[Chroma RAG]
        N[News Client]
        S[Search Client]
        SW[Sports WS]
        SD[Sports Data]
        MW[Market WS]
    end

    subgraph External
        PG[Polymarket Gamma<br/>gamma-api.polymarket.com]
        PC[Polymarket CLOB<br/>clob.polymarket.com]
        PWS[Polymarket Sports WS<br/>sports-api.polymarket.com/ws]
        OAI[OpenAI API]
        AS[API-Sports<br/>v1.*.api-sports.io]
        OA[The Odds API<br/>api.the-odds-api.com]
        NA[NewsAPI<br/>newsapi.org]
        PR[Polygon RPC]
    end

    G <-->|REST, no auth| PG
    P <-->|REST, API key + Web3 sig| PC
    C <-->|embeddings| OAI
    N <-->|REST, API key| NA
    S <-->|REST, API key| Tavily
    SW <-->|WebSocket, no auth| PWS
    SD <-->|REST, API key| AS
    SD <-->|REST, API key| OA
    MW <-->|WebSocket| PC
    P <-->|Web3 RPC| PR
```

## Process Architecture

```mermaid
flowchart TB
    subgraph Process1["Process 1: General Pipeline"]
        CLI1[CLI Entry Point]
        R1[AsyncRunner]
        STRAT[Strategy<br/>Batch / Continuous / Crypto]
        EX1[LLM Executor]
    end

    subgraph Process2["Process 2: Sports Pipeline"]
        SM1[Sports Main]
        R2[AsyncRunner]
        SPT[Sports Trader]
        IGT[InGame Trader]
        SEX[Sports Executor]
        SWS[Sports WS Loop]
    end

    subgraph Shared["Shared State (File-Locked)"]
        BF["budget.json<br/>(FileLock)"]
        PC["pregame_cache.json<br/>(FileLock)"]
    end

    subgraph OnChain["On-Chain (Shared)"]
        W["USDC Wallet<br/>Single Address"]
        CLOB["Polymarket CLOB"]
    end

    CLI1 --> R1 --> STRAT --> EX1
    SM1 --> R2 --> SPT & IGT
    SPT --> SEX
    IGT --> SEX & SWS

    EX1 --> BF
    SPT --> BF & PC
    IGT --> BF & PC

    EX1 --> CLOB --> W
    SPT --> CLOB
    IGT --> CLOB

    style Shared fill:#fff9c4,stroke:#FFC107
    style OnChain fill:#c8e6c9,stroke:#4CAF50
```

## Sports WebSocket Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Connecting
    Connecting --> Connected: WS handshake OK
    Connecting --> Backoff: Connection failed

    Connected --> Receiving: Game state messages
    Receiving --> Connected: PING/PONG (5s heartbeat)
    Receiving --> ScoreChange: Score delta detected

    ScoreChange --> FastPath: Delta > threshold + cache hit
    ScoreChange --> SlowPath: Full re-analysis needed
    FastPath --> TradeGate
    SlowPath --> TradeGate

    TradeGate --> Execute: All gates pass
    TradeGate --> Skip: Cooldown / Cap / Budget / Halt
    Execute --> Receiving
    Skip --> Receiving

    Connected --> Disconnected: Connection lost
    Disconnected --> Backoff: Exponential backoff + jitter
    Backoff --> Connecting: Retry

    Receiving --> GameEnded: Game final
    GameEnded --> Receiving: Continue other games

    Connected --> [*]: Shutdown signal
```
