# Polyagents — Sports Mode

## What This Is

An autonomous Polymarket trading bot with a dedicated **sports mode** pipeline. The sports pipeline connects to Polymarket's sports websocket for real-time game state, integrates external sports data APIs (team stats, odds, H2H matchups), and autonomously trades sports markets both pre-game (LLM analysis) and live in-game (score-change triggered fast-path/slow-path execution). Runs alongside the existing general prediction market pipeline with cross-process budget coordination.

## Core Value

Autonomously identify and execute profitable sports trades by combining real-time game state from Polymarket's sports websocket with historical team performance data, reacting to live score and state changes faster than manual traders.

## Requirements

### Validated

- ✓ Autonomous general market trading pipeline (events → markets → candidates → execution) — existing
- ✓ LLM-driven trade decision making with superforecasting — existing
- ✓ RAG-based event and market filtering via Chroma — existing
- ✓ Polymarket CLOB order execution with USDC budget allocation — existing
- ✓ News context integration for market analysis — existing
- ✓ Single-event analysis mode — existing
- ✓ Category-based market classification and filtering — existing
- ✓ Configurable dry-run vs live execution — existing
- ✓ Confidence-weighted budget allocation across candidates — existing
- ✓ Polymarket sports websocket integration for live game state — v1.0
- ✓ External sports data API integration (team stats, matchup history, season performance, odds) — v1.0
- ✓ Sports-specific market identification and tagging with metadata (league, teams, game time) — v1.0
- ✓ Pre-game analysis and trade positioning pipeline — v1.0
- ✓ Live in-game autonomous trading reacting to score/state changes — v1.0
- ✓ Configurable budget split between sports and general trading — v1.0
- ✓ Sports-specific LLM prompts incorporating game context and stats — v1.0
- ✓ Support for all Polymarket sports (NFL, NBA, MLB, NHL, CFB, CBB, soccer, esports, tennis) — v1.0

### Active

(None — define in next milestone)

### Out of Scope

- Mobile app or web UI — CLI/autonomous operation only
- Manual trade confirmation for live games — fully autonomous
- Custom odds modeling — use external odds data and LLM reasoning
- Social/sentiment analysis for sports — use structured stats data
- Backtesting framework — forward-looking execution only
- Multi-provider sports API fallback — single provider sufficient for v1
- Offline mode — real-time data is core value

## Context

- **Shipped:** v1.0 Sports Mode (2026-03-11) — 6 phases, 13 plans, 24 requirements, 353 tests
- **Codebase:** ~8,976 new Python LOC across 19 files; total project ~306k LOC Python
- **Tech stack:** Python 3.9, LangChain, OpenAI, Chroma, py-clob-client, FastAPI, websocket-client, httpx, cachetools, tenacity, filelock
- **Architecture:** Separate sports pipeline (`agents/sports.py`) runs alongside general pipeline; cross-process BudgetCoordinator with filelock for USDC allocation; SportsWSConnector streams game state; SportsTrader handles pre-game; InGameTrader handles live in-game
- **Known tech debt:** `detect_value_bet()` orphaned, `wallet_balance` stale after startup, in-memory `_order_log`/`_ended_games` lost on restart

## Constraints

- **Tech stack**: Python 3.9, must integrate with existing LangChain/OpenAI pipeline
- **API compatibility**: Must use Polymarket CLOB API for execution (same as general pipeline)
- **Budget**: Sports and general trading share the same USDC wallet, configurable split via `SPORTS_BUDGET_FRACTION`
- **Latency**: Live in-game trades react within seconds of game state changes (fast-path uses cached probabilities)
- **Architecture**: Sports pipeline coexists with general pipeline without interference (separate process, filelock coordination)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Separate pipeline (not mode toggle) | Sports requires fundamentally different data flow (websocket vs polling) and timing (continuous vs periodic) | ✓ Good — clean separation, independent crash isolation |
| Slug-based Gamma lookup (not Chroma RAG) | Direct slug→market mapping more reliable than vector search for known game IDs | ✓ Good — deterministic, fast, no embedding drift |
| Two-stage LLM analysis (blind + market-aware) | First stage gives unbiased probability; second incorporates market prices for value detection | ✓ Good — prevents anchoring bias |
| File-persisted PregameCache with filelock | Cross-process safety for pre-game probabilities shared between SportsTrader and InGameTrader | ✓ Good — survives process restart |
| Fast-path/slow-path in-game routing | Minor scores use cached probability (no LLM call); major events trigger full re-analysis | ✓ Good — balances speed vs accuracy |
| Dedicated sports data API for stats | LLM knowledge alone insufficient for current season stats and real-time odds | ✓ Good — structured data beats LLM knowledge cutoff |
| All sports from v1 | Polymarket WS already streams all sports; normalization handles differences | ✓ Good — no artificial limitation |
| Configurable budget split | Flexibility to adjust risk between sports and general trading | ✓ Good — environment variable control |
| Inline env helpers per module | Avoids heavy executor.py import chain (langchain/openai deps) in lightweight modules | ⚠️ Revisit — some duplication across modules |

---
*Last updated: 2026-03-11 after v1.0 milestone*
