# Polyagents — Sports Mode

## What This Is

An autonomous Polymarket trading bot that currently trades general prediction markets using LLM-driven analysis. We're adding a dedicated **sports mode** — a separate pipeline that connects to Polymarket's sports websocket for live game state, integrates external sports data APIs for team stats and matchup history, and autonomously trades sports markets both pre-game and live in-game.

## Core Value

The bot must autonomously identify and execute profitable sports trades by combining real-time game state from Polymarket's sports websocket with historical team performance data, reacting to live score and state changes faster than manual traders.

## Requirements

### Validated

<!-- Existing capabilities confirmed from codebase -->

- ✓ Autonomous general market trading pipeline (events → markets → candidates → execution) — existing
- ✓ LLM-driven trade decision making with superforecasting — existing
- ✓ RAG-based event and market filtering via Chroma — existing
- ✓ Polymarket CLOB order execution with USDC budget allocation — existing
- ✓ News context integration for market analysis — existing
- ✓ Single-event analysis mode — existing
- ✓ Category-based market classification and filtering — existing
- ✓ Configurable dry-run vs live execution — existing
- ✓ Confidence-weighted budget allocation across candidates — existing

### Active

<!-- New sports mode capabilities to build -->

- [ ] Polymarket sports websocket integration for live game state
- [ ] External sports data API integration (team stats, matchup history, season performance, odds)
- [ ] Sports-specific market identification and tagging with metadata (league, teams, game time)
- [ ] Pre-game analysis and trade positioning pipeline
- [ ] Live in-game autonomous trading reacting to score/state changes
- [ ] Configurable budget split between sports and general trading
- [ ] Sports-specific LLM prompts incorporating game context and stats
- [ ] Support for all Polymarket sports (NFL, NBA, MLB, NHL, CFB, CBB, soccer, esports, tennis)

### Out of Scope

- Mobile app or web UI — CLI/autonomous operation only
- Manual trade confirmation for live games — fully autonomous
- Custom odds modeling — use external odds data and LLM reasoning
- Social/sentiment analysis for sports — use structured stats data
- Backtesting framework — forward-looking execution only

## Context

- **Existing system**: Layered agent-based architecture with Application (Trader/Executor), Connector (Gamma/Chroma/News), Data Models, and Utility layers
- **Sports websocket**: `wss://sports-api.polymarket.com/ws` — no auth, streams live game state for all active sports events (scores, periods, possession, game status)
- **Current sports handling**: `TRADE_EXCLUDE_SPORTS` env var and `canonicalize_category()` function currently filter OUT sports markets — this needs to be inverted for sports mode
- **Tech stack**: Python 3.9, LangChain, OpenAI, Chroma, py-clob-client, FastAPI
- **Live data fields from WS**: gameId, leagueAbbreviation, slug, homeTeam/awayTeam, status, score, period, live, ended, elapsed

## Constraints

- **Tech stack**: Python 3.9, must integrate with existing LangChain/OpenAI pipeline
- **API compatibility**: Must use Polymarket CLOB API for execution (same as general pipeline)
- **Budget**: Sports and general trading share the same USDC wallet, configurable split
- **Latency**: Live in-game trades need to react within seconds of game state changes
- **Architecture**: Sports pipeline must coexist with general pipeline without interference

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Separate pipeline (not mode toggle) | Sports requires fundamentally different data flow (websocket vs polling) and timing (continuous vs periodic) | — Pending |
| Dedicated sports data API for stats | LLM knowledge alone insufficient for current season stats and real-time odds | — Pending |
| Full autonomous live trading | User wants speed advantage over manual traders during games | — Pending |
| All sports from v1 | Polymarket WS already streams all sports; no reason to limit | — Pending |
| Configurable budget split | Flexibility to adjust risk between sports and general trading | — Pending |

---
*Last updated: 2026-03-03 after initialization*
