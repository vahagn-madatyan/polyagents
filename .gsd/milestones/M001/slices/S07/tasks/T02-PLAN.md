# T02: 07-code-quality-and-state-persistence 02

**Slice:** S07 — **Milestone:** M001

## Description

Persist InGameTrader's _order_log and _ended_games to JSON files so trade history and game-end state survive process restarts.

Purpose: Currently both are in-memory only (lost on restart). Following the PregameCache pattern (JSON + filelock), we add atomic writes on every update and reload on startup. This ensures no trade data or game state is lost during normal restarts or crashes.

Output: Updated `ingame_trader.py` with persistence hooks, `tests/test_ingame_persistence.py` covering round-trip, missing file, and corrupt file scenarios.

## Must-Haves

- [ ] "_order_log is written to a JSON file on every update and reloaded on startup so no trade history is lost on restart"
- [ ] "_ended_games is written to a JSON file on every update and reloaded on startup so no game-end state is lost on restart"
- [ ] "Missing persistence files on startup result in empty state (no crash)"
- [ ] "Corrupt persistence files on startup produce a warning log and fresh state (no crash)"
- [ ] "Integer game_id keys round-trip correctly through JSON serialization (int -> str -> int)"

## Files

- `agents/application/ingame_trader.py`
- `tests/test_ingame_persistence.py`
