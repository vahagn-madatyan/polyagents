from __future__ import annotations
import time
from typing import Any, Optional, Union
from pydantic import BaseModel, Field


class Trade(BaseModel):
    id: int
    taker_order_id: str
    market: str
    asset_id: str
    side: str
    size: str
    fee_rate_bps: str
    price: str
    status: str
    match_time: str
    last_update: str
    outcome: str
    maker_address: str
    owner: str
    transaction_hash: str
    bucket_index: str
    maker_orders: list[str]
    type: str


class SimpleMarket(BaseModel):
    id: int
    question: str
    # start: str
    end: str
    description: str
    active: bool
    # deployed: Optional[bool]
    funded: bool
    # orderMinSize: float
    # orderPriceMinTickSize: float
    rewardsMinSize: float
    rewardsMaxSpread: float
    volume: Optional[float] = 0.0
    volume24hr: Optional[float] = 0.0
    volume_clob: Optional[float] = 0.0
    volume24hr_clob: Optional[float] = 0.0
    liquidity: Optional[float] = 0.0
    liquidity_clob: Optional[float] = 0.0
    spread: float
    outcomes: str
    outcome_prices: str
    clob_token_ids: Optional[str]
    category: Optional[str] = ""
    tags: Optional[str] = ""
    event_id: Optional[str] = ""
    event_title: Optional[str] = ""
    event_slug: Optional[str] = ""


class ClobReward(BaseModel):
    id: str  # returned as string in api but really an int?
    conditionId: str
    assetAddress: str
    rewardsAmount: float  # only seen 0 but could be float?
    rewardsDailyRate: int  # only seen ints but could be float?
    startDate: str  # yyyy-mm-dd formatted date string
    endDate: str  # yyyy-mm-dd formatted date string


class Tag(BaseModel):
    id: str
    label: Optional[str] = None
    slug: Optional[str] = None
    forceShow: Optional[bool] = None  # missing from current events data
    createdAt: Optional[str] = None  # missing from events data
    updatedAt: Optional[str] = None  # missing from current events data
    _sync: Optional[bool] = None


class PolymarketEvent(BaseModel):
    id: str  # "11421"
    ticker: Optional[str] = None
    slug: Optional[str] = None
    title: Optional[str] = None
    startDate: Optional[str] = None
    creationDate: Optional[str] = (
        None  # fine in market event but missing from events response
    )
    endDate: Optional[str] = None
    image: Optional[str] = None
    icon: Optional[str] = None
    active: Optional[bool] = None
    closed: Optional[bool] = None
    archived: Optional[bool] = None
    new: Optional[bool] = None
    featured: Optional[bool] = None
    restricted: Optional[bool] = None
    liquidity: Optional[float] = None
    volume: Optional[float] = None
    reviewStatus: Optional[str] = None
    createdAt: Optional[str] = None  # 2024-07-08T01:06:23.982796Z,
    updatedAt: Optional[str] = None  # 2024-07-15T17:12:48.601056Z,
    competitive: Optional[float] = None
    volume24hr: Optional[float] = None
    enableOrderBook: Optional[bool] = None
    liquidityClob: Optional[float] = None
    _sync: Optional[bool] = None
    commentCount: Optional[int] = None
    markets: Optional[list[Market]] = None
    tags: Optional[list[Tag]] = None
    cyom: Optional[bool] = None
    showAllOutcomes: Optional[bool] = None
    showMarketImages: Optional[bool] = None


class Market(BaseModel):
    id: int
    question: Optional[str] = None
    conditionId: Optional[str] = None
    slug: Optional[str] = None
    resolutionSource: Optional[str] = None
    endDate: Optional[str] = None
    liquidity: Optional[float] = None
    startDate: Optional[str] = None
    image: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    outcome: Optional[list] = None
    outcomePrices: Optional[list] = None
    volume: Optional[float] = None
    active: Optional[bool] = None
    closed: Optional[bool] = None
    marketMakerAddress: Optional[str] = None
    createdAt: Optional[str] = None  # date type worth enforcing for dates?
    updatedAt: Optional[str] = None
    new: Optional[bool] = None
    featured: Optional[bool] = None
    submitted_by: Optional[str] = None
    archived: Optional[bool] = None
    resolvedBy: Optional[str] = None
    restricted: Optional[bool] = None
    groupItemTitle: Optional[str] = None
    groupItemThreshold: Optional[int] = None
    questionID: Optional[str] = None
    enableOrderBook: Optional[bool] = None
    orderPriceMinTickSize: Optional[float] = None
    orderMinSize: Optional[int] = None
    volumeNum: Optional[float] = None
    liquidityNum: Optional[float] = None
    endDateIso: Optional[str] = None  # iso format date = None
    startDateIso: Optional[str] = None
    hasReviewedDates: Optional[bool] = None
    volume24hr: Optional[float] = None
    clobTokenIds: Optional[list] = None
    umaBond: Optional[int] = None  # returned as string from api?
    umaReward: Optional[int] = None  # returned as string from api?
    volume24hrClob: Optional[float] = None
    volumeClob: Optional[float] = None
    liquidityClob: Optional[float] = None
    acceptingOrders: Optional[bool] = None
    negRisk: Optional[bool] = None
    commentCount: Optional[int] = None
    _sync: Optional[bool] = None
    events: Optional[list[PolymarketEvent]] = None
    ready: Optional[bool] = None
    deployed: Optional[bool] = None
    funded: Optional[bool] = None
    deployedTimestamp: Optional[str] = None  # utc z datetime string
    acceptingOrdersTimestamp: Optional[str] = None  # utc z datetime string,
    cyom: Optional[bool] = None
    competitive: Optional[float] = None
    pagerDutyNotificationEnabled: Optional[bool] = None
    reviewStatus: Optional[str] = None  # deployed, draft, etc.
    approved: Optional[bool] = None
    clobRewards: Optional[list[ClobReward]] = None
    rewardsMinSize: Optional[int] = (
        None  # would make sense to allow float but we'll see
    )
    rewardsMaxSpread: Optional[float] = None
    spread: Optional[float] = None


class ComplexMarket(BaseModel):
    id: int
    condition_id: str
    question_id: str
    tokens: Union[str, str]
    rewards: str
    minimum_order_size: str
    minimum_tick_size: str
    description: str
    category: str
    end_date_iso: str
    game_start_time: str
    question: str
    market_slug: str
    min_incentive_size: str
    max_incentive_spread: str
    active: bool
    closed: bool
    seconds_delay: int
    icon: str
    fpmm: str
    name: str
    description: Union[str, None] = None
    price: float
    tax: Union[float, None] = None


class SimpleEvent(BaseModel):
    id: int
    ticker: str
    slug: str
    title: str
    description: str
    end: str
    active: bool
    closed: bool
    archived: bool
    restricted: bool
    new: bool
    featured: bool
    restricted: bool
    markets: str


class Source(BaseModel):
    id: Optional[str]
    name: Optional[str]


class Article(BaseModel):
    source: Optional[Source]
    author: Optional[str]
    title: Optional[str]
    description: Optional[str]
    url: Optional[str]
    urlToImage: Optional[str]
    publishedAt: Optional[str]
    content: Optional[str]


class CandidateTrade(BaseModel):
    market_id: int
    question: str
    category_bucket: str = "other"
    outcomes: list[str] = Field(default_factory=list)
    outcome_prices: list[float] = Field(default_factory=list)
    token_ids: list[str] = Field(default_factory=list)
    rag_score: Optional[float] = None
    probabilities: list[dict[str, Any]] = Field(default_factory=list)
    suggested_outcome: str = ""
    parsed_side: str = ""
    parsed_price: Optional[float] = None
    parsed_size_fraction: Optional[float] = None
    confidence_gap: float = 0.0
    rationale: str = ""
    risk_factors: list[str] = Field(default_factory=list)
    counter_case: str = ""
    allocation_fraction: float = 0.0
    allocation_amount_usdc: float = 0.0
    execution_status: str = "NOT_EXECUTED"
    execution_response: Optional[Any] = None


class SportGameState(BaseModel):
    """Live game state from Polymarket sports WebSocket.

    A single model covers all 9 supported sports (NFL, NBA, MLB, NHL, CFB,
    CBB, soccer, esports, tennis) with optional sport-specific fields.
    """

    # Core identity
    game_id: int
    league: str  # nfl, nba, mlb, nhl, cfb, cbb, soccer, cs2, tennis, etc.
    slug: str  # {league}-{team1}-{team2}-{date}
    home_team: str
    away_team: str

    # Core state (always present)
    status: str  # sport-specific status string (InProgress, finished, etc.)
    score_raw: str  # raw string from WS e.g. "3-16" or "000-000|2-0|Bo3"
    home_score: Optional[int] = None  # parsed from score_raw
    away_score: Optional[int] = None  # parsed from score_raw
    period: str  # "Q4", "1H", "End 5", "2/3", "Set 2", etc.
    live: bool
    ended: bool

    # Optional fields
    elapsed: Optional[str] = None  # time within period, sport-specific
    finished_timestamp: Optional[str] = None  # ISO 8601 when ended=True

    # Sport-specific extras
    possession: Optional[str] = None  # NFL/CFB only — maps from WS "turn" field

    # Lifecycle tracking
    last_updated: float = Field(default_factory=time.monotonic)
    stale: bool = False  # True when watchdog fires; cleared on next real data message


class SportsMarketTag(BaseModel):
    """Links a sports WebSocket game slug to a specific Polymarket market.

    Produced by GammaMarketClient slug-lookup methods and consumed by the
    trading pipeline to place orders on the correct CLOB token pair.
    """

    slug: str  # ws_slug that sourced this tag, e.g. "nfl-lac-buf-2025-01-26"
    league: str  # sport league abbreviation, e.g. "nfl", "nba"
    home_team: str  # home team abbreviation, e.g. "LAC"
    away_team: str  # away team abbreviation, e.g. "BUF"
    market_id: str  # Gamma market id (str form of int)
    condition_id: str  # CLOB condition id (0x hex string)
    token_id_yes: str  # CLOB token id for YES outcome
    token_id_no: str  # CLOB token id for NO outcome
    question: str  # market question text, e.g. "Will the Chargers win?"
    outcome_prices: Optional[str] = None  # JSON-encoded prices e.g. "0.6,0.4"


class SportsAnalysisCache(BaseModel):
    """Persisted pre-game analysis entry produced by SportsExecutor.

    Stored in PregameCache keyed by game_id for fast-path reuse during Phase 4.
    """

    game_id: int
    league: str
    home_team: str
    away_team: str
    timestamp: float
    llm_home_win_prob: float
    llm_away_win_prob: float
    confidence_gap: float
    selected_outcome: str
    selected_side: str
    size_fraction: float
    rationale: str
    risk_factors: list[str] = Field(default_factory=list)
    counter_case: str = ""
    polymarket_price_at_analysis: float
    external_implied_prob: Optional[float] = None
    trade_attempted: bool = False
    trade_error: Optional[str] = None
    superforecast_response: str = ""
    trade_response: str = ""
