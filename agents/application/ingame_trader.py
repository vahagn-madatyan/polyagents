"""InGameTrader — autonomous in-game trading engine.

Coordinates: score-change detection -> event classification (minor/major) ->
fast-path (cache + live price divergence) or slow-path (LLM re-analysis in daemon thread) ->
per-game cooldown debounce -> exposure cap -> budget gate -> dry-run/live trade execution.

Does NOT import Executor, Chroma, or Gamma to avoid the heavy dependency chain.
"""

from __future__ import annotations

import os
import threading
import time
from typing import TYPE_CHECKING, Optional

from agents.utils.objects import SportGameState, SportsMarketTag

if TYPE_CHECKING:
    from agents.application.budget import BudgetCoordinator
    from agents.application.pregame_cache import PregameCache
    from agents.application.sports_executor import SportsExecutor
    from agents.connectors.sports_data import SportsDataConnector
    from agents.polymarket.polymarket import Polymarket


# ---------------------------------------------------------------------------
# Inline env helpers (same pattern as sports_trader.py / budget.py)
# ---------------------------------------------------------------------------


def _env_float(key: str, default: float) -> float:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Sport-specific near-resolution heuristics
# ---------------------------------------------------------------------------

# Periods that indicate end-of-game proximity, keyed by league prefix
_FINAL_PERIODS: dict[str, set[str]] = {
    "nfl": {"Q4", "OT"},
    "nba": {"Q4", "OT", "OT1", "OT2"},
    "mlb": {},  # innings vary — use elapsed heuristic only
    "nhl": {"P3", "OT"},
    "cfb": {"Q4", "OT"},
    "cbb": {"2H", "OT"},
    "soccer": {"2H", "ET"},
    "cs2": {},  # best-of series — check score
    "tennis": {},  # set-based — no simple period heuristic
}

# Default fallback for unknown leagues
_DEFAULT_FINAL_PERIODS: set[str] = {"OT", "Q4", "P3", "2H", "ET"}

# Default in-game trade amount (fraction of sport cap) for fast-path
_INGAME_SIZE_FRACTION = 0.05


class InGameTrader:
    """Autonomous in-game trading engine.

    Flow per tick:
      1. Diff current_states against _prev_game_states snapshot
      2. For each changed game: classify event (major or minor)
      3. Check cooldown + in-flight guards
      4. Minor -> fast-path (cache probability vs live Polymarket price)
      5. Major -> slow-path (LLM re-analysis in daemon thread)
      6. Game ended -> add to _ended_games and cancel blackout-window orders

    All state is in-memory. Lost on restart — acceptable per CONTEXT.md.
    """

    def __init__(
        self,
        budget_coordinator: "BudgetCoordinator",
        data_connector: "SportsDataConnector",
        executor: "SportsExecutor",
        cache: "PregameCache",
        dry_run: bool,
        polymarket: Optional["Polymarket"] = None,
        wallet_balance: float = 0.0,
    ) -> None:
        self._budget = budget_coordinator
        self._data_connector = data_connector
        self._executor = executor
        self._cache = cache
        self.dry_run = dry_run
        self._polymarket = polymarket
        self._wallet_balance = wallet_balance

        # Read configuration from environment
        self.cooldown_seconds: int = _env_int("SPORTS_INGAME_COOLDOWN_SECONDS", 30)
        self.min_confidence_gap: float = _env_float(
            "SPORTS_INGAME_MIN_CONFIDENCE_GAP", 0.15
        )
        self.blackout_minutes: int = _env_int("SPORTS_BLACKOUT_MINUTES", 2)
        self.max_game_exposure_usd: float = _env_float(
            "SPORTS_MAX_GAME_EXPOSURE_USD", 50.0
        )

        # Per-game state tracking
        self._prev_game_states: dict[int, SportGameState] = {}
        self._last_processed: dict[int, float] = {}
        self._slow_path_in_flight: set[int] = set()
        self._order_log: dict[int, list[dict]] = {}
        self._game_exposure: dict[int, float] = {}
        self._ended_games: set[int] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tick(
        self,
        current_states: dict[int, SportGameState],
        slug_table: dict[str, list[SportsMarketTag]],
    ) -> None:
        """Main entry point — called each loop iteration (~1s cadence).

        Diffs current_states against _prev_game_states snapshot. For each game:
        - First time seen: store as baseline
        - Game ended: handle_game_ended()
        - Score changed: classify -> fast-path or slow-path
        - No change: skip
        """
        for game_id, current in current_states.items():
            # Skip games already marked as ended
            if game_id in self._ended_games:
                self._prev_game_states[game_id] = current
                continue

            prev = self._prev_game_states.get(game_id)

            if prev is None:
                # First time seeing this game — store as baseline, no event
                self._prev_game_states[game_id] = current
                print(
                    f"[ingame_trader] event=baseline_stored game_id={game_id} "
                    f"score_raw={current.score_raw}"
                )
                continue

            # Check for game ended
            if current.ended and not prev.ended:
                print(
                    f"[ingame_trader] event=game_ended game_id={game_id} "
                    f"score_raw={current.score_raw}"
                )
                self._prev_game_states[game_id] = current
                self.handle_game_ended(game_id)
                continue

            # Check for score change
            if current.score_raw != prev.score_raw:
                tags = slug_table.get(current.slug)
                if tags is None:
                    print(
                        f"[ingame_trader] event=no_market_tag game_id={game_id} "
                        f"slug={current.slug} score_raw={current.score_raw}"
                    )
                    self._prev_game_states[game_id] = current
                    continue
                market_tag = tags[0]

                self._handle_score_change(game_id, prev, current, market_tag)
                self._prev_game_states[game_id] = current
            else:
                # No change — update state reference but take no action
                self._prev_game_states[game_id] = current

    def handle_period_transition(
        self,
        msg: dict,
        slug_table: dict[str, list[SportsMarketTag]],
    ) -> None:
        """Handle period_transition queue message from SportsWSConnector.

        Routes to slow-path as a major event (period transitions are significant
        state changes regardless of score).
        """
        game_id = msg.get("game_id")
        if game_id is None:
            print(f"[ingame_trader] event=period_transition_no_game_id msg={msg}")
            return

        state = msg.get("state")
        if state is None:
            print(
                f"[ingame_trader] event=period_transition_no_state_in_msg game_id={game_id}"
            )
            return

        tags = slug_table.get(state.slug)
        if tags is None:
            print(
                f"[ingame_trader] event=period_transition_no_market_tag game_id={game_id} "
                f"slug={state.slug}"
            )
            return
        market_tag = tags[0]

        if not self._should_process(game_id):
            print(
                f"[ingame_trader] event=period_transition_skipped game_id={game_id} "
                f"reason=cooldown_or_in_flight"
            )
            return

        current = self._prev_game_states.get(game_id)
        if current is None:
            print(f"[ingame_trader] event=period_transition_no_state game_id={game_id}")
            return

        print(
            f"[ingame_trader] event=period_transition game_id={game_id} "
            f"period={msg.get('period')}"
        )
        self._mark_processed(game_id)
        self._spawn_slow_path(game_id, current, market_tag)

    def handle_game_ended(self, game_id: int) -> None:
        """Mark game as ended and cancel orders within the blackout window.

        Called when current.ended transitions True or explicitly from external code.
        """
        self._ended_games.add(game_id)
        print(
            f"[ingame_trader] event=handle_game_ended game_id={game_id} "
            f"cancelling_blackout_orders=true"
        )
        self._cancel_blackout_orders(game_id)

    # ------------------------------------------------------------------
    # Internal routing
    # ------------------------------------------------------------------

    def _handle_score_change(
        self,
        game_id: int,
        prev: SportGameState,
        current: SportGameState,
        market_tag: SportsMarketTag,
    ) -> None:
        """Classify score change and route to fast or slow path."""
        if not self._should_process(game_id):
            print(
                f"[ingame_trader] event=score_change_skipped game_id={game_id} "
                f"reason=cooldown_or_in_flight"
            )
            return

        event_type = self._classify_score_change(prev, current)
        print(
            f"[ingame_trader] event=score_change game_id={game_id} "
            f"event_type={event_type} "
            f"prev={prev.score_raw} curr={current.score_raw}"
        )

        if event_type == "major":
            self._mark_processed(game_id)
            self._spawn_slow_path(game_id, current, market_tag)
        else:
            self._fast_path(game_id, current, market_tag)

    def _spawn_slow_path(
        self,
        game_id: int,
        current: SportGameState,
        market_tag: SportsMarketTag,
    ) -> None:
        """Spawn daemon thread for slow-path LLM analysis."""
        t = threading.Thread(
            target=self._run_slow_path,
            args=(game_id, current, market_tag),
            daemon=True,
            name=f"ingame-slow-{game_id}",
        )
        t.start()

    # ------------------------------------------------------------------
    # Fast path
    # ------------------------------------------------------------------

    def _fast_path(
        self,
        game_id: int,
        current: SportGameState,
        market_tag: SportsMarketTag,
    ) -> None:
        """Fast-path: read PregameCache probability vs live Polymarket price.

        No LLM calls. Trades when divergence exceeds min_confidence_gap.
        """
        # Guard: ended games
        if game_id in self._ended_games:
            print(
                f"[ingame_trader] event=fast_path_skip game_id={game_id} reason=game_ended"
            )
            return

        # Guard: proactive near-resolution blackout
        if self._is_near_resolution(current):
            print(
                f"[ingame_trader] event=fast_path_skip game_id={game_id} "
                f"reason=near_resolution"
            )
            self._mark_processed(game_id)
            return

        # Step 1: read cache
        cache_entry = self._cache.get(game_id)
        if cache_entry is None:
            print(
                f"[ingame_trader] event=fast_path_skip game_id={game_id} "
                f"reason=no_cache_entry"
            )
            self._mark_processed(game_id)
            return

        llm_prob = float(cache_entry.get("llm_home_win_prob", 0.0))

        # Step 2: fetch live Polymarket price
        try:
            live_price = self._polymarket.get_orderbook_price(market_tag.token_id_yes)
        except Exception as exc:
            print(
                f"[ingame_trader] event=fast_path_skip game_id={game_id} "
                f"reason=price_fetch_error error={exc}"
            )
            self._mark_processed(game_id)
            return

        # Step 3: compute divergence
        divergence = abs(llm_prob - live_price)
        if divergence < self.min_confidence_gap:
            print(
                f"[ingame_trader] event=fast_path_skip game_id={game_id} "
                f"reason=low_divergence divergence={divergence:.4f} "
                f"threshold={self.min_confidence_gap:.4f}"
            )
            self._mark_processed(game_id)
            return

        # Step 4: determine outcome
        if llm_prob > live_price:
            outcome = "Yes"
            token_id = market_tag.token_id_yes
        else:
            outcome = "No"
            token_id = market_tag.token_id_no

        # Step 5: compute trade amount (fixed fraction of sport-level cap)
        trade_amount = _INGAME_SIZE_FRACTION * self.max_game_exposure_usd

        # Step 6: exposure cap
        if not self._check_exposure(game_id, trade_amount):
            print(
                f"[ingame_trader] event=fast_path_skip game_id={game_id} "
                f"reason=exposure_cap trade_amount={trade_amount:.2f}"
            )
            self._mark_processed(game_id)
            return

        # Step 7: budget gate
        if not self._budget.can_spend_sports(trade_amount, self._wallet_balance):
            print(
                f"[ingame_trader] event=fast_path_skip game_id={game_id} "
                f"reason=budget_exhausted trade_amount={trade_amount:.2f}"
            )
            self._mark_processed(game_id)
            return

        # Step 8: execute (or dry-run)
        self._mark_processed(game_id)
        self._execute_ingame_trade(game_id, token_id, outcome, trade_amount, market_tag)

    # ------------------------------------------------------------------
    # Slow path
    # ------------------------------------------------------------------

    def _run_slow_path(
        self,
        game_id: int,
        current: SportGameState,
        market_tag: SportsMarketTag,
    ) -> None:
        """Full LLM analysis for major events. Runs in daemon thread.

        Flow:
          1. Mark game_id as in-flight
          2. Fetch game context
          3. Run SportsExecutor.analyze_game()
          4. Update PregameCache with new analysis
          5. Apply confidence gap gate
          6. Apply exposure cap
          7. Apply budget gate
          8. Execute or dry-run trade
          9. Remove from in-flight (in finally block)
        """
        self._slow_path_in_flight.add(game_id)
        self._mark_processed(game_id)
        try:
            # Guard: ended games
            if game_id in self._ended_games:
                print(
                    f"[ingame_trader] event=slow_path_skip game_id={game_id} "
                    f"reason=game_ended"
                )
                return

            # Guard: proactive near-resolution blackout
            if self._is_near_resolution(current):
                print(
                    f"[ingame_trader] event=slow_path_skip game_id={game_id} "
                    f"reason=near_resolution"
                )
                return

            # Step 1: fetch game context
            game_context = self._data_connector.get_game_context(current)

            # Step 2: LLM analysis
            candidate = self._executor.analyze_game(current, market_tag, game_context)

            if candidate is None:
                print(
                    f"[ingame_trader] event=slow_path_skip game_id={game_id} "
                    f"reason=executor_returned_none"
                )
                return

            # Step 3: update PregameCache with fresh analysis
            probs = {
                p["outcome"]: p["likelihood"]
                for p in candidate.probabilities
                if isinstance(p, dict)
            }
            llm_home_win_prob = probs.get("Yes", 0.0)
            llm_away_win_prob = probs.get("No", 0.0)

            cache_entry = {
                "game_id": game_id,
                "league": current.league,
                "home_team": current.home_team,
                "away_team": current.away_team,
                "llm_home_win_prob": llm_home_win_prob,
                "llm_away_win_prob": llm_away_win_prob,
                "confidence_gap": candidate.confidence_gap,
                "selected_outcome": candidate.suggested_outcome,
                "selected_side": candidate.parsed_side,
                "size_fraction": candidate.parsed_size_fraction or 0.0,
                "rationale": candidate.rationale,
                "risk_factors": candidate.risk_factors,
                "counter_case": candidate.counter_case,
                "polymarket_price_at_analysis": (
                    candidate.outcome_prices[0] if candidate.outcome_prices else 0.0
                ),
                "trade_attempted": False,
                "trade_error": None,
            }
            self._cache.set(game_id, cache_entry)

            # Step 4: confidence gap gate
            if candidate.confidence_gap < self.min_confidence_gap:
                print(
                    f"[ingame_trader] event=slow_path_skip game_id={game_id} "
                    f"reason=low_confidence confidence_gap={candidate.confidence_gap:.4f} "
                    f"threshold={self.min_confidence_gap:.4f}"
                )
                return

            # Step 5: determine outcome and token
            outcome = candidate.suggested_outcome or "Yes"
            token_id = (
                market_tag.token_id_yes if outcome == "Yes" else market_tag.token_id_no
            )

            # Step 6: compute trade amount
            size_fraction = candidate.parsed_size_fraction or _INGAME_SIZE_FRACTION
            trade_amount = size_fraction * self.max_game_exposure_usd

            # Step 7: exposure cap
            if not self._check_exposure(game_id, trade_amount):
                print(
                    f"[ingame_trader] event=slow_path_skip game_id={game_id} "
                    f"reason=exposure_cap trade_amount={trade_amount:.2f}"
                )
                return

            # Step 8: budget gate
            if not self._budget.can_spend_sports(trade_amount, self._wallet_balance):
                print(
                    f"[ingame_trader] event=slow_path_skip game_id={game_id} "
                    f"reason=budget_exhausted trade_amount={trade_amount:.2f}"
                )
                return

            # Step 9: execute or dry-run
            self._execute_ingame_trade(
                game_id, token_id, outcome, trade_amount, market_tag
            )

        except Exception as exc:
            print(
                f"[ingame_trader] event=slow_path_error game_id={game_id} error={exc}"
            )
        finally:
            self._slow_path_in_flight.discard(game_id)

    # ------------------------------------------------------------------
    # Trade execution
    # ------------------------------------------------------------------

    def _execute_ingame_trade(
        self,
        game_id: int,
        token_id: str,
        outcome: str,
        amount: float,
        market_tag: SportsMarketTag,
    ) -> None:
        """Execute in-game trade via CLOB (or log in dry-run mode).

        Records the order in _order_log and updates _game_exposure on success.
        """
        if self.dry_run:
            print(
                f"[ingame_trader] dry_run game_id={game_id} "
                f"would_trade outcome={outcome} token_id={token_id} amount={amount:.2f}"
            )
            return

        try:
            order_id = self._polymarket.execute_market_order_for_token(
                token_id=token_id, amount=amount
            )
            self._log_order(game_id, order_id, market_tag.market_id)
            self._record_exposure(game_id, amount)
            self._budget.record_sports_trade(amount, market_tag.league)
            print(
                f"[ingame_trader] event=ingame_trade_placed game_id={game_id} "
                f"outcome={outcome} order_id={order_id} amount={amount:.2f}"
            )
        except Exception as exc:
            print(
                f"[ingame_trader] event=ingame_trade_error game_id={game_id} error={exc}"
            )

    # ------------------------------------------------------------------
    # Guards and checks
    # ------------------------------------------------------------------

    def _should_process(self, game_id: int) -> bool:
        """Return True when game is eligible for processing.

        Checks:
        - Not in _ended_games
        - Not in cooldown
        - Not in slow-path in-flight
        """
        if game_id in self._ended_games:
            return False
        if self._is_in_cooldown(game_id):
            return False
        if game_id in self._slow_path_in_flight:
            return False
        return True

    def _is_in_cooldown(self, game_id: int) -> bool:
        """Return True if game is within cooldown window."""
        last = self._last_processed.get(game_id)
        if last is None:
            return False
        return (time.time() - last) < self.cooldown_seconds

    def _mark_processed(self, game_id: int) -> None:
        """Record current time as last-processed timestamp for game."""
        self._last_processed[game_id] = time.time()

    def _check_exposure(self, game_id: int, amount: float) -> bool:
        """Return True if adding amount stays within per-game exposure cap."""
        current = self._game_exposure.get(game_id, 0.0)
        return (current + amount) <= self.max_game_exposure_usd

    def _record_exposure(self, game_id: int, amount: float) -> None:
        """Add amount to running per-game exposure total."""
        self._game_exposure[game_id] = self._game_exposure.get(game_id, 0.0) + amount

    def _log_order(self, game_id: int, order_id: str, market_id: str) -> None:
        """Record placed order in _order_log (in-memory only)."""
        if game_id not in self._order_log:
            self._order_log[game_id] = []
        self._order_log[game_id].append(
            {
                "order_id": order_id,
                "timestamp": time.time(),
                "market_id": market_id,
            }
        )

    # ------------------------------------------------------------------
    # Event classification
    # ------------------------------------------------------------------

    def _classify_score_change(
        self, prev: SportGameState, current: SportGameState
    ) -> str:
        """Classify score change as 'major' or 'minor'.

        Major triggers:
        - Lead change (different team leading after)
        - Tied-to-leading or leading-to-tied
        - Overtime/Extra-time period detected

        Minor: all other score changes (same team leading, slightly more)
        """
        # Overtime / extra-time period check (takes priority)
        period_upper = (current.period or "").upper()
        if any(ot in period_upper for ot in ("OT", "OVERTIME", "ET")):
            return "major"

        # Score comparison — treat None as 0
        prev_home = prev.home_score if prev.home_score is not None else 0
        prev_away = prev.away_score if prev.away_score is not None else 0
        curr_home = current.home_score if current.home_score is not None else 0
        curr_away = current.away_score if current.away_score is not None else 0

        def leader(home, away) -> str:
            """Return 'home', 'away', or 'tied'."""
            if home > away:
                return "home"
            if away > home:
                return "away"
            return "tied"

        prev_leader = leader(prev_home, prev_away)
        curr_leader = leader(curr_home, curr_away)

        if prev_leader != curr_leader:
            # Lead changed, tied->leading, or leading->tied
            return "major"

        return "minor"

    # ------------------------------------------------------------------
    # Game-ended safeguards
    # ------------------------------------------------------------------

    def _cancel_blackout_orders(self, game_id: int) -> None:
        """Cancel CLOB orders placed within the blackout window.

        FOK orders may already be filled — wrap each cancel in try/except.
        """
        orders = self._order_log.get(game_id, [])
        if not orders:
            return

        blackout_cutoff = time.time() - (self.blackout_minutes * 60)

        for order in orders:
            order_ts = order.get("timestamp", 0)
            if order_ts < blackout_cutoff:
                # Order older than blackout window — skip
                continue
            order_id = order.get("order_id")
            if not order_id:
                continue
            try:
                self._polymarket.client.cancel(order_id)
                print(
                    f"[ingame_trader] event=blackout_cancel game_id={game_id} "
                    f"order_id={order_id}"
                )
            except Exception as exc:
                print(
                    f"[ingame_trader] event=blackout_cancel_error game_id={game_id} "
                    f"order_id={order_id} error={exc}"
                )

    def _is_near_resolution(self, state: SportGameState) -> bool:
        """Proactive blackout heuristic — return True when game is near end.

        Sport-specific checks. Logs a warning when uncertain.
        Resolution heuristic is intentionally conservative to avoid missed blackouts.
        """
        league = (state.league or "").lower()
        period = (state.period or "").upper()
        elapsed = (state.elapsed or "").upper()

        # Explicit ended flag always triggers
        if state.ended:
            return True

        # Check OT periods (near resolution for most sports)
        period_upper = period.upper()

        # NFL/CFB Q4 with late elapsed time
        if league in ("nfl", "cfb") and period_upper == "Q4":
            # If elapsed looks like it's in the final 2 minutes
            if elapsed and ":" in elapsed:
                try:
                    parts = elapsed.split(":")
                    minutes = int(parts[0])
                    if minutes <= 2:
                        return True
                except (ValueError, IndexError):
                    pass

        # NBA Q4 with <2 min remaining
        if league == "nba" and period_upper == "Q4":
            if elapsed and ":" in elapsed:
                try:
                    parts = elapsed.split(":")
                    minutes = int(parts[0])
                    if minutes <= 2:
                        return True
                except (ValueError, IndexError):
                    pass

        # Soccer: any time after the 85th minute in second half
        if league == "soccer" and period_upper == "2H":
            if elapsed:
                try:
                    elapsed_min = int(elapsed.split(":")[0])
                    if elapsed_min >= 85:
                        return True
                except (ValueError, IndexError):
                    pass

        # Generic OT double-OT near resolution
        if "OT" in period_upper and period_upper not in ("OT", "OT1"):
            # Deep overtime — cautiously flag as near resolution
            print(
                f"[ingame_trader] warn=near_resolution_uncertain game_id={state.game_id} "
                f"period={state.period}"
            )
            return True

        return False
