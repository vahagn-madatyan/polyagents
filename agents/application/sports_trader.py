"""SportsTrader — orchestrator for the pre-game sports trading pipeline.

Coordinates: data fetch -> LLM analysis (SportsExecutor) -> cache write ->
confidence gate -> budget gate -> dry-run/live trade execution.

Does NOT import Executor, Chroma, or Gamma to avoid the heavy dependency chain.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional

from agents.connectors.sports_ws import should_halt_trading
from agents.utils.env import _env_bool, _env_float, _env_int
from agents.utils.objects import CandidateTrade, SportGameState, SportsMarketTag

if TYPE_CHECKING:
    from agents.application.budget import BudgetCoordinator
    from agents.application.pregame_cache import PregameCache
    from agents.application.sports_executor import SportsExecutor
    from agents.connectors.sports_data import SportsDataConnector
    from agents.polymarket.polymarket import Polymarket


class SportsTrader:
    """Orchestrates the complete pre-game trading pipeline.

    Flow per game:
      1. Fetch game context (stats, H2H, odds) from SportsDataConnector
      2. Run two-stage LLM analysis via SportsExecutor.analyze_game()
      3. Write PregameCache entry (always, before trade attempt)
      4. Gate on minimum confidence gap (SPORTS_MIN_CONFIDENCE_GAP)
      5. Gate on budget (BudgetCoordinator.can_spend_sports())
      6. In dry-run: log the would-be trade; in live: execute CLOB order
    """

    def __init__(
        self,
        budget_coordinator: "BudgetCoordinator",
        data_connector: "SportsDataConnector",
        executor: "SportsExecutor",
        cache: "PregameCache",
        dry_run: bool,
        polymarket: Optional["Polymarket"] = None,
    ) -> None:
        self.budget_coordinator = budget_coordinator
        self.data_connector = data_connector
        self.executor = executor
        self.cache = cache
        self.dry_run = dry_run
        self.polymarket = polymarket

        # Read configuration
        self.min_confidence_gap: float = _env_float("SPORTS_MIN_CONFIDENCE_GAP", 0.10)

        # Track in-flight game analyses (prevents duplicate concurrent calls)
        self._in_flight: set[int] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_analyze(self, game_id: int) -> bool:
        """Return True when game should be re-analyzed (cache is stale or missing)."""
        return not self.cache.is_fresh(game_id)

    def run_pregame_analysis(
        self,
        game_id: int,
        game_state: SportGameState,
        market_tag: SportsMarketTag,
        wallet_balance: float,
    ) -> None:
        """Run the full pre-game analysis and trade pipeline for a single game.

        Skips:
          - Ended games
          - Games already being analyzed (in_flight guard)

        Always writes cache entry after successful LLM analysis, before trade gates.
        """
        # Guard: skip ended games
        if game_state.ended:
            print(
                f"[sports_trader] event=skip_ended game_id={game_id} "
                f"league={game_state.league}"
            )
            return

        # Phase 6: safety gate — skip analysis on halted game states
        if should_halt_trading(game_state):
            print(
                f"[sports_trader] event=trading_halted game_id={game_id} "
                f"status={game_state.status}"
            )
            return

        # Guard: prevent duplicate concurrent analysis of same game
        if game_id in self._in_flight:
            print(f"[sports_trader] event=skip_in_flight game_id={game_id}")
            return

        self._in_flight.add(game_id)
        try:
            self._analyze_and_trade(game_id, game_state, market_tag, wallet_balance)
        finally:
            self._in_flight.discard(game_id)

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _analyze_and_trade(
        self,
        game_id: int,
        game_state: SportGameState,
        market_tag: SportsMarketTag,
        wallet_balance: float,
    ) -> None:
        """Core pipeline: data fetch -> LLM -> cache -> gates -> execute."""
        # Step 1: fetch game context (stats, H2H, odds)
        game_context = self.data_connector.get_game_context(game_state)

        # Step 2: LLM analysis
        candidate: Optional[CandidateTrade] = self.executor.analyze_game(
            game_state, market_tag, game_context
        )

        if candidate is None:
            print(
                f"[sports_trader] event=analyze_failed game_id={game_id} "
                "reason=executor_returned_none"
            )
            return

        # Step 3: Build and write cache entry BEFORE trade gates
        # (ensures Phase 4 can read probability even if trade is skipped)
        cache_entry = self._build_cache_entry(
            game_id, game_state, candidate, market_tag
        )
        self.cache.set(game_id, cache_entry)

        # Step 4: Confidence gap gate
        if candidate.confidence_gap < self.min_confidence_gap:
            print(
                f"[sports_trader] event=skip_low_confidence game_id={game_id} "
                f"confidence_gap={candidate.confidence_gap:.4f} "
                f"threshold={self.min_confidence_gap:.4f}"
            )
            print(
                f"[sports_trader] event=pregame_complete game_id={game_id} "
                f"confidence_gap={candidate.confidence_gap:.4f} "
                f"traded=False amount=0.00"
            )
            return

        # Step 5: Compute trade amount
        sport_cap = self.budget_coordinator.get_sport_cap(game_state.league)
        size_fraction = candidate.parsed_size_fraction or 0.0
        trade_amount = size_fraction * sport_cap

        if trade_amount <= 0:
            print(
                f"[sports_trader] event=skip_zero_amount game_id={game_id} "
                f"size_fraction={size_fraction} cap={sport_cap}"
            )
            print(
                f"[sports_trader] event=pregame_complete game_id={game_id} "
                f"confidence_gap={candidate.confidence_gap:.4f} "
                f"traded=False amount=0.00"
            )
            return

        # Step 5b: Budget gate
        if not self.budget_coordinator.can_spend_sports(trade_amount, wallet_balance):
            print(
                f"[sports_trader] event=skip_budget_exhausted game_id={game_id} "
                f"trade_amount={trade_amount:.2f} wallet_balance={wallet_balance:.2f}"
            )
            print(
                f"[sports_trader] event=pregame_complete game_id={game_id} "
                f"confidence_gap={candidate.confidence_gap:.4f} "
                f"traded=False amount={trade_amount:.2f}"
            )
            return

        # Step 6: Dry-run gate
        if self.dry_run:
            print(
                f"[sports_trader] dry_run game_id={game_id} "
                f"would_trade outcome={candidate.suggested_outcome} "
                f"side={candidate.parsed_side} amount={trade_amount:.2f}"
            )
            print(
                f"[sports_trader] event=pregame_complete game_id={game_id} "
                f"confidence_gap={candidate.confidence_gap:.4f} "
                f"traded=False amount={trade_amount:.2f}"
            )
            return

        # Step 7: Live execution
        token_id = (
            market_tag.token_id_yes
            if candidate.suggested_outcome == "Yes"
            else market_tag.token_id_no
        )

        try:
            self.polymarket.execute_market_order_for_token(
                token_id=token_id, amount=trade_amount
            )
            self.budget_coordinator.record_sports_trade(trade_amount, game_state.league)
            print(
                f"[sports_trader] event=pregame_complete game_id={game_id} "
                f"confidence_gap={candidate.confidence_gap:.4f} "
                f"traded=True amount={trade_amount:.2f}"
            )
        except Exception as exc:
            error_msg = str(exc)
            print(
                f"[sports_trader] event=trade_error game_id={game_id} error={error_msg}"
            )
            # Update cache entry with trade_error so Phase 4 knows the trade failed
            cache_entry_with_error = dict(cache_entry)
            cache_entry_with_error["trade_error"] = error_msg
            self.cache.set(game_id, cache_entry_with_error)
            print(
                f"[sports_trader] event=pregame_complete game_id={game_id} "
                f"confidence_gap={candidate.confidence_gap:.4f} "
                f"traded=False amount={trade_amount:.2f}"
            )

    def _build_cache_entry(
        self,
        game_id: int,
        game_state: SportGameState,
        candidate: CandidateTrade,
        market_tag: SportsMarketTag,
    ) -> dict:
        """Build SportsAnalysisCache-compatible dict from CandidateTrade."""
        # Extract probabilities for home/away win
        probs = {
            p["outcome"]: p["likelihood"]
            for p in candidate.probabilities
            if isinstance(p, dict)
        }
        llm_home_win_prob = probs.get("Yes", 0.0)
        llm_away_win_prob = probs.get("No", 0.0)

        # Extract polymarket price at analysis time (first outcome price = Yes price)
        polymarket_price = (
            candidate.outcome_prices[0] if candidate.outcome_prices else 0.0
        )

        # Extract superforecast and trade responses from execution_response
        exec_resp = candidate.execution_response or {}
        superforecast_response = ""
        trade_response = ""
        if isinstance(exec_resp, dict):
            superforecast_response = str(exec_resp.get("superforecast_response", ""))
            trade_response = str(exec_resp.get("trade_recommendation", ""))

        return {
            "game_id": game_id,
            "league": game_state.league,
            "home_team": game_state.home_team,
            "away_team": game_state.away_team,
            "llm_home_win_prob": llm_home_win_prob,
            "llm_away_win_prob": llm_away_win_prob,
            "confidence_gap": candidate.confidence_gap,
            "selected_outcome": candidate.suggested_outcome,
            "selected_side": candidate.parsed_side,
            "size_fraction": candidate.parsed_size_fraction or 0.0,
            "rationale": candidate.rationale,
            "risk_factors": candidate.risk_factors,
            "counter_case": candidate.counter_case,
            "polymarket_price_at_analysis": polymarket_price,
            "superforecast_response": superforecast_response,
            "trade_response": trade_response,
            "trade_attempted": False,
            "trade_error": None,
        }
