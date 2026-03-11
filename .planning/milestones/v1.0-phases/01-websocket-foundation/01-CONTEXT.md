# Phase 1: WebSocket Foundation - Context

**Gathered:** 2026-03-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Reliable `SportGameState` stream from Polymarket's sports websocket with reconnect, freeze detection, and normalization across all 9 supported sports (NFL, NBA, MLB, NHL, CFB, CBB, soccer, esports, tennis). Period transition detection and edge-case game status handling included. No trading logic — this phase delivers the data foundation.

</domain>

<decisions>
## Implementation Decisions

### Game State Model
- Common base fields (score, period, elapsed, live, ended, status) plus optional sport-specific extras (possession for NFL/CFB, innings for MLB, sets for tennis)
- Single `SportGameState` Pydantic model with optional sport-specific fields — NOT per-sport subclasses
- Scores stored as raw string from WS AND parsed integers (home_score, away_score) — enables delta computation and debugging
- Primary key: `gameId` from WS; secondary lookup by `slug` (league-team1-team2-date)
- Track `last_updated` timestamp on every state change — needed for watchdog and downstream latency measurement

### Watchdog Behavior
- On silent freeze: force reconnect AND mark all active game states as stale until refreshed by new WS data
- Freeze timeout: configurable via `SPORTS_WS_FREEZE_TIMEOUT_SECONDS` env var — default 5 minutes (well before the known ~18min server-side freeze)
- Reconnect strategy: exponential backoff with jitter (1s, 2s, 4s, 8s... up to configurable max) — prevents thundering herd

### Logging & Observability
- Configurable via `SPORTS_WS_LOG_LEVEL` env var with levels: `all` (every message), `changes` (score/period changes only), `minimal` (connect/disconnect only)
- Default to `changes` — balance between observability and noise
- Follow existing `print(f"[sports_ws] key=value")` pattern for machine-parseable output

### State Lifecycle
- Ended game state kept in memory for configurable TTL via `SPORTS_WS_ENDED_GAME_TTL_MINUTES` — needed for post-game settlement windows
- Purge automatically after TTL expires
- All game state cleared on pipeline restart

### Claude's Discretion
- Exact thread management for WS daemon thread
- Internal queue implementation details (size, blocking behavior)
- Pydantic field validators and normalization logic
- Heartbeat (ping/pong) implementation specifics

</decisions>

<specifics>
## Specific Ideas

- Research flagged a known Polymarket WS silent freeze bug (GitHub issue #26 on `Polymarket/real-time-data-client`) — watchdog must detect data gaps even when ping/pong is healthy
- WS sends `ping` every 5 seconds, client must `pong` within 10 seconds or gets disconnected
- Sport-specific status values vary (NFL has quarters, MLB has innings/half, soccer has halves, tennis has sets) — normalization must handle all without losing sport context

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `canonicalize_category()` in `agents/application/executor.py`: already identifies sports markets — can inform the sport-specific field mapping
- `_env_bool()`, `_env_int()`, `_env_float()` helpers: use for all new env var parsing
- Pydantic pattern in `agents/utils/objects.py`: follow existing `SimpleMarket`/`SimpleEvent` style for `SportGameState`

### Established Patterns
- Connectors in `agents/connectors/`: new WS connector goes in `agents/connectors/sports_ws.py`
- Logging: `print(f"[tag] key=value")` for structured output, `logging.getLogger()` for important state transitions
- Environment config: load in `__init__`, provide sensible defaults

### Integration Points
- `agents/utils/objects.py`: add `SportGameState` Pydantic model here
- `agents/connectors/sports_ws.py`: new file for WS connector class
- `.env.example`: add new env vars (SPORTS_WS_FREEZE_TIMEOUT_SECONDS, SPORTS_WS_LOG_LEVEL, SPORTS_WS_ENDED_GAME_TTL_MINUTES)
- Both `websocket-client==1.8.0` and `websockets==12.0` already in requirements.txt

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-websocket-foundation*
*Context gathered: 2026-03-03*
