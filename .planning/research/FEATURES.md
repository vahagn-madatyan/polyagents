# Feature Research

**Domain:** Autonomous sports prediction market trading bot (Polymarket sports mode)
**Researched:** 2026-03-03
**Confidence:** MEDIUM — Polymarket sports WS docs verified HIGH; sports bot feature patterns MEDIUM via multiple WebSearch sources; competitor feature sets LOW (no direct access to closed-source competitors)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features the bot must have. Missing these means the sports mode doesn't work at a basic level.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Sports WebSocket connection & reconnect | Without live game state the sports pipeline is dead; Polymarket WS is the source of truth for all live scoring | LOW | `wss://sports-api.polymarket.com/ws` — no auth required; must handle disconnects and resume without missing state |
| Sports market identification & filtering | Bot must distinguish sports markets from general markets and tag with league, teams, game time | LOW | Invert existing `TRADE_EXCLUDE_SPORTS` / `canonicalize_category()` logic; tag with `leagueAbbreviation`, `homeTeam`, `awayTeam` from WS |
| Live score / game state ingestion | Scores, period changes, live/ended flags are the primary signal for in-game trades | LOW | WS fields: `score`, `period`, `elapsed`, `live`, `ended`, `status` — parse and normalize across sports |
| Pre-game trade positioning | Most sports prediction market volume is pre-game; bot must evaluate and enter positions before tip-off / kickoff | MEDIUM | Requires external team stats API to supplement LLM reasoning; timing: trigger before game goes `live` |
| In-game autonomous trade execution | Core value prop — react to score changes faster than manual traders | HIGH | Latency-sensitive; must evaluate, decide, and submit CLOB order within seconds of WS event; LLM call adds ~1-3s latency |
| Sports-specific LLM prompts | General-market prompts lack game context; sports prompts must inject score, period, teams, stats, and odds context | MEDIUM | Extends existing LangChain prompt templates; requires structured game context object |
| Multi-sport support (NFL, NBA, MLB, NHL, CFB, CBB, soccer, esports, tennis) | Polymarket WS streams all sports; restricting to one sport leaves the majority of markets untouched | MEDIUM | Primary complexity is sport-specific data normalization (e.g., possession only for NFL/CFB; innings for MLB) |
| Sports-specific budget allocation | Sports and general markets share a wallet; unconstrained sports trading can exhaust the entire budget | LOW | Configurable `SPORTS_BUDGET_FRACTION` env var; enforce budget cap per sports session |
| Graceful pipeline coexistence | Sports pipeline must run alongside general pipeline without resource contention or state corruption | MEDIUM | Separate async event loop or process; shared USDC wallet with mutex on order submission |

### Differentiators (Competitive Advantage)

Features that create a performance or execution edge over manual traders or simpler bots.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Score-change triggered trade signals | Immediately re-evaluate market prices the moment a score update arrives, before manual traders react | HIGH | WS score delta detection → LLM re-evaluation → order submission pipeline; target <5s from WS event to order |
| External stats API integration (team record, H2H history, season performance) | LLM knowledge is stale; current season win rates and head-to-head matchups dramatically improve pre-game probability estimates | MEDIUM | Best option: The Odds API (historical odds back to 2020) + API-Sports (15yr history, real-time every 15s); one API call per game pre-game |
| Odds comparison vs. Polymarket price | Detect when Polymarket price diverges from external consensus odds — this is the value bet signal | HIGH | Compare external book odds (e.g., from The Odds API) with Polymarket's current YES/NO price; trade toward consensus when gap exceeds threshold |
| Period/quarter transition handling | Halftime, quarter breaks, and overtime starts are predictable volatility windows where prices move before market makers adjust | MEDIUM | Detect `period` change events from WS; trigger re-evaluation at each transition |
| Confidence-weighted position sizing for sports | Sports predictions have wider uncertainty bands than general markets; scale size by LLM confidence and game state | LOW | Extend existing confidence-weighted budget allocation; add sport-specific confidence discount factor |
| Game status edge-case handling | Overtime, rain delays, forfeits, and in-game injuries cause price dislocations | HIGH | Map all `status` enum values from WS; define trade rules for each edge case; avoid trading during suspension/delay |
| Sport-specific prompt context injection | NBA 4th quarter trailing by 3 is very different from NFL 4th quarter trailing by 3; sport-aware prompts outperform generic ones | MEDIUM | Build prompt fragments per sport category (scoring rate, comeback probability, time pressure) |
| Configurable per-sport budget caps | Limit exposure to high-variance sports (e.g., esports) while allowing larger allocation to more predictable ones (e.g., NFL) | LOW | Per-sport env config or config file; allows risk tuning without code changes |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Custom ML odds model (in-house probability engine) | Seems like it would be more accurate than external odds | Requires training data pipeline, model validation, and ongoing maintenance that is out of scope and adds months of work | Use external odds APIs (The Odds API, SportsDataIO) as the probability ground truth; LLM reasons on top of external data |
| Backtesting framework | Validating strategy before risking real money sounds essential | Out of scope per PROJECT.md; building a proper backtester requires historical Polymarket order book data that is difficult to obtain and replicate accurately | Paper trading / dry-run mode (already exists) with conservative position sizes for initial live validation |
| Social / sentiment analysis for sports | Twitter reactions to injury news seem like valuable signals | Structured, official data (box scores, injury reports) is faster and more reliable than social parsing; adds NLP complexity and noise | Integrate official injury report endpoints from SportsDataIO or API-Sports instead |
| Manual trade confirmation popups for live games | Seems safer to have human approval | Eliminates the sub-second speed advantage that is the entire value prop; defeats the purpose of an autonomous bot | Use dry-run mode for testing; set hard position size limits as the safety mechanism instead |
| Full order book market-making for sports | Market makers earn spreads and rebates | Requires continuous inventory management and rapid repricing; exposes the bot to adverse selection when game state changes suddenly | Stay as a taker; enter directional positions based on game state signals |
| Web UI / dashboard | Nice to see positions and P&L visually | Adds frontend development scope with no trading edge; the bot is autonomous and CLI-operated per PROJECT.md | Log structured JSON to a file; use existing CLI output and dry-run logs |
| Arbitrage across Polymarket + Kalshi + sportsbooks | High theoretical profit | Requires multi-exchange account management, cross-platform API integration, and complex settlement tracking; regulatory exposure for sportsbook arbitrage | Focus on directional trading within Polymarket where the existing CLOB infrastructure already works |

---

## Feature Dependencies

```
[Sports WebSocket connection]
    └──required by──> [Live score / game state ingestion]
                          └──required by──> [In-game autonomous trade execution]
                          └──required by──> [Period/quarter transition handling]
                          └──required by──> [Score-change triggered trade signals]

[Sports market identification & filtering]
    └──required by──> [Pre-game trade positioning]
    └──required by──> [In-game autonomous trade execution]
    └──required by──> [Sports-specific budget allocation]

[External stats API integration]
    └──required by──> [Pre-game trade positioning] (provides team stats, H2H history)
    └──enhances──>    [Odds comparison vs. Polymarket price]

[Sports-specific LLM prompts]
    └──required by──> [Pre-game trade positioning]
    └──required by──> [In-game autonomous trade execution]
    └──enhanced by──> [Sport-specific prompt context injection]
    └──enhanced by──> [External stats API integration]

[Odds comparison vs. Polymarket price]
    └──depends on──>  [External stats API integration] (for reference odds)
    └──enhances──>    [In-game autonomous trade execution] (value detection)

[Graceful pipeline coexistence]
    └──required by──> [Sports-specific budget allocation]
    └──required by──> [In-game autonomous trade execution]

[Multi-sport support]
    └──enhanced by──> [Sport-specific prompt context injection]
    └──enhanced by──> [Configurable per-sport budget caps]
```

### Dependency Notes

- **Sports WebSocket connection requires stable reconnect logic:** Game state gaps during reconnect cause stale context, which leads to wrong trades. Must track last-known state and invalidate in-flight decisions on reconnect.
- **Pre-game positioning requires external stats API:** The LLM alone lacks current season data. Without the API, pre-game analysis reduces to general priors.
- **In-game trade execution requires sports market identification:** Cannot place an order without knowing the correct Polymarket market ID and token addresses, which come from the market-tagging step.
- **Odds comparison enhances but does not block in-game execution:** External odds polling adds latency; in-game trades should proceed with LLM-only confidence if external odds are unavailable.
- **Graceful coexistence is a precondition for the entire sports pipeline:** A crash in the sports loop must not kill the general trading loop.

---

## MVP Definition

### Launch With (v1)

Minimum viable sports mode — validates autonomous live sports trading.

- [ ] Sports WebSocket client with reconnect — without this nothing works
- [ ] Sports market identification and metadata tagging (league, teams, game time) — needed to find the right markets
- [ ] Live score ingestion and game state normalization — core data model for all decisions
- [ ] Sports-specific LLM prompts with game context injection — reuses existing LangChain infrastructure
- [ ] Pre-game trade positioning pipeline — captures pre-game volume and validates stats API integration
- [ ] External stats API integration (one provider: The Odds API or API-Sports) — provides current season and H2H data
- [ ] In-game autonomous trade execution triggered by score changes — the primary value prop
- [ ] Configurable sports budget allocation — prevents wallet exhaustion
- [ ] Graceful pipeline coexistence with general trading — safety requirement

### Add After Validation (v1.x)

Add once v1 is profitable and stable for at least 2-3 weeks of live games.

- [ ] Period/quarter transition handling as discrete trade signals — add when score-change trades are proven profitable
- [ ] Odds comparison vs. Polymarket price (value bet detection) — add when external odds integration is stable
- [ ] Configurable per-sport budget caps — add when multi-sport behavior is understood from logs
- [ ] Game status edge-case handling (OT, rain delay, forfeit) — add after seeing first edge cases in production

### Future Consideration (v2+)

Defer until sports mode has demonstrated sustained profitability.

- [ ] Sport-specific prompt context injection per sport category — deferred because single generalized sports prompt is sufficient for v1 validation
- [ ] Confidence-weighted position sizing tuned specifically for sports — existing general confidence weighting is adequate for v1
- [ ] Multi-provider stats API fallback — single provider sufficient for v1; add redundancy after reliability issues are observed

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Sports WebSocket connection & reconnect | HIGH | LOW | P1 |
| Sports market identification & tagging | HIGH | LOW | P1 |
| Live score / game state ingestion | HIGH | LOW | P1 |
| Sports-specific LLM prompts | HIGH | MEDIUM | P1 |
| Pre-game trade positioning pipeline | HIGH | MEDIUM | P1 |
| External stats API integration | HIGH | MEDIUM | P1 |
| In-game autonomous trade execution | HIGH | HIGH | P1 |
| Sports budget allocation | HIGH | LOW | P1 |
| Graceful pipeline coexistence | HIGH | MEDIUM | P1 |
| Score-change triggered trade signals | HIGH | HIGH | P2 |
| Period/quarter transition handling | MEDIUM | MEDIUM | P2 |
| Odds comparison vs. Polymarket price | HIGH | HIGH | P2 |
| Sport-specific prompt context injection | MEDIUM | MEDIUM | P2 |
| Configurable per-sport budget caps | MEDIUM | LOW | P2 |
| Game status edge-case handling (OT, delays) | MEDIUM | HIGH | P2 |
| Confidence-weighted sports position sizing | LOW | LOW | P3 |
| Multi-provider stats API fallback | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Must have for v1 launch — sports mode is non-functional without these
- P2: Should have — adds trading edge and reliability; add after v1 validation
- P3: Nice to have — future optimization once strategy is proven

---

## Competitor Feature Analysis

| Feature | Traditional Sports Betting Bots | Open-Source Polymarket Bots | Our Approach |
|---------|--------------------------------|------------------------------|--------------|
| Live game state | WebSocket or polling of sportsbook data feeds | General market polling; no sports WS support | Native Polymarket sports WS — direct source, lowest latency |
| Pre-game analysis | Rule-based odds models, ML classifiers | LLM with general market context | LLM + external stats API + sports-specific prompts |
| Odds comparison | Core feature — arbitrage between books | Not applicable (single platform) | Compare external consensus odds vs. Polymarket price |
| Team stats integration | SportsDataIO, API-Sports, proprietary feeds | No stats integration; LLM knowledge only | External API (The Odds API or API-Sports) per game |
| Multi-sport support | Yes — unified via API | No explicit sport handling | Yes — all sports on Polymarket WS from v1 |
| Execution | Sportsbook bet placement APIs | Polymarket CLOB taker orders | Polymarket CLOB — same execution as existing general pipeline |
| Position sizing | Kelly criterion, fixed fractional | Confidence-weighted budget | Extend existing confidence-weighted allocation |
| Autonomy | Semi-auto (human approval) or full-auto | Full autonomous | Fully autonomous — no confirmation prompts |

---

## Sources

- [Polymarket Sports WebSocket Documentation](https://docs.polymarket.com/market-data/websocket/sports) — HIGH confidence; official Polymarket docs confirming WS fields and message types
- [The Odds API — Historical Sports Odds](https://the-odds-api.com/historical-odds-data/) — MEDIUM confidence; official API docs confirming historical data availability back to 2020
- [API-Sports](https://api-sports.io/) — MEDIUM confidence; official docs confirming 15yr historical data, real-time updates every 15s
- [SportsDataIO](https://sportsdata.io/) — MEDIUM confidence; official site confirming multi-sport coverage and live odds API
- [OpticOdds — AI Bots in Sports Betting](https://opticodds.com/blog/ai-bots-in-sports-betting) — MEDIUM confidence; industry blog covering AI bot architecture patterns
- [QuantVPS — Sports Betting Bots on Polymarket](https://www.quantvps.com/blog/automated-sports-betting-bots-on-polymarket) — LOW confidence; third-party analysis, unverified claims
- [Polymarket Strategies 2026](https://cryptonews.com/cryptocurrency/polymarket-strategies/) — LOW confidence; journalistic overview, useful for competitive context
- [ReadWrite — Best Sports Betting Bots 2026](https://readwrite.com/gambling/betting/sports-betting-bots/) — LOW confidence; review site, useful for feature landscape
- [Risk.inc — AI Revolutionizing Betting](https://www.risk.inc/blog/how-artificial-intelligence-is-revolutionizing-the-world-of-betting-and-gambling) — LOW confidence; industry blog

---

*Feature research for: Polymarket autonomous sports trading bot — sports mode milestone*
*Researched: 2026-03-03*
