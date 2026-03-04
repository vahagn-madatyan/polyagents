import asyncio
import logging
import os
from typing import Optional

from agents.application.budget import SessionBudgetManager
from agents.connectors.websocket import WebSocketManager

logger = logging.getLogger(__name__)


class ContinuousStrategy:
    def __init__(
        self,
        include_news: bool = False,
        exclude_sports: bool = False,
        news_limit: int = 5,
        news_days: int = 7,
        news_relevance: bool = True,
        cooldown_seconds: int = 300,
        volatility_threshold: float = 0.05,
        events_refresh_cycles: int = 5,
    ) -> None:
        from agents.application.trade import Trader

        self.trader = Trader()
        self.include_news = include_news
        self.exclude_sports = exclude_sports
        self.news_limit = news_limit
        self.news_days = news_days
        self.news_relevance = news_relevance
        self.cooldown_seconds = cooldown_seconds
        self.volatility_threshold = volatility_threshold
        self.events_refresh_cycles = events_refresh_cycles
        self._cached_events = None
        self._events_fetched_cycle = 0

    async def run_cycle(self, runner, cycle: int) -> None:
        budget = runner.budget
        ws = runner.ws

        if not budget.can_spend(self.trader.min_order_amount_usdc):
            logger.info(
                "[continuous] budget_exhausted remaining=%.2f", budget.remaining()
            )
            runner.stop()
            return

        # Refresh events periodically
        if (
            self._cached_events is None
            or (cycle - self._events_fetched_cycle) >= self.events_refresh_cycles
        ):
            logger.info("[continuous] refreshing_events cycle=%d", cycle)
            self._cached_events = await asyncio.to_thread(
                self.trader.polymarket.get_all_tradeable_events
            )
            self._events_fetched_cycle = cycle
            logger.info("[continuous] cached_events=%d", len(self._cached_events or []))

        events = self._cached_events
        if not events:
            logger.info("[continuous] no_events_found")
            return

        # Filter events with RAG
        filtered_events = await asyncio.to_thread(
            self.trader.agent.filter_events_with_rag, events
        )
        if not filtered_events:
            logger.info("[continuous] no_events_after_filter")
            return

        # Map to markets
        markets = await asyncio.to_thread(
            self.trader.agent.map_filtered_events_to_markets, filtered_events
        )
        if not markets:
            logger.info("[continuous] no_markets_found")
            return

        # Filter markets with RAG
        filtered_markets = await asyncio.to_thread(
            self.trader.agent.filter_markets, markets
        )
        if not filtered_markets:
            logger.info("[continuous] no_markets_after_filter")
            return

        # Exclude sports if configured
        if self.exclude_sports:
            filtered_markets = self.trader._exclude_sports_markets(filtered_markets)
            if not filtered_markets:
                return

        # Filter out markets on cooldown
        filtered_markets = self._filter_cooldown_markets(filtered_markets, budget)

        # Prioritize volatile markets (those with big WebSocket price swings)
        filtered_markets = self._prioritize_volatile_markets(filtered_markets, ws)

        if not filtered_markets:
            logger.info("[continuous] no_markets_after_cooldown_and_volatility_filter")
            return

        # Build news context if enabled
        context_by_market_id = None
        if self.include_news:
            context_by_market_id = await asyncio.to_thread(
                self.trader._build_news_context_by_market_id,
                filtered_markets,
                self.news_limit,
                self.news_days,
                self.news_relevance,
            )

        # Build candidates via LLM
        candidates_payload = await asyncio.to_thread(
            self.trader.agent.build_trade_candidates,
            filtered_markets,
            context_by_market_id,
        )

        selected = candidates_payload.get("selected_candidates", [])
        if not selected:
            logger.info("[continuous] no_candidates_selected")
            return

        # Allocate from session budget (not full wallet)
        remaining = budget.remaining()
        self.trader.agent.allocate_selected_candidates(selected, remaining)

        # Execute trades
        for candidate in selected:
            if candidate.allocation_amount_usdc <= 0:
                continue
            if not budget.can_spend(candidate.allocation_amount_usdc):
                candidate.execution_status = "SKIPPED_BUDGET_EXHAUSTED"
                continue

            if self.trader.execute_trades:
                try:
                    token_map = self.trader.polymarket.resolve_token_for_outcome(
                        outcomes=candidate.outcomes,
                        token_ids=candidate.token_ids,
                        selected_outcome=candidate.suggested_outcome,
                        side=candidate.parsed_side,
                    )
                    response = await asyncio.to_thread(
                        self.trader.polymarket.execute_market_order_for_token,
                        token_map["token_id"],
                        candidate.allocation_amount_usdc,
                    )
                    candidate.execution_status = "EXECUTED"
                    candidate.execution_response = response
                    budget.record_trade(
                        amount=candidate.allocation_amount_usdc,
                        market_id=candidate.market_id,
                        outcome=candidate.suggested_outcome,
                    )
                    logger.info(
                        "[continuous] executed market_id=%d amount=%.2f outcome=%s",
                        candidate.market_id,
                        candidate.allocation_amount_usdc,
                        candidate.suggested_outcome,
                    )
                except Exception as err:
                    candidate.execution_status = "FAILED"
                    candidate.execution_response = str(err)
                    logger.error(
                        "[continuous] execution_failed market_id=%d error=%s",
                        candidate.market_id,
                        err,
                    )
            else:
                candidate.execution_status = "DRY_RUN"
                budget.record_trade(
                    amount=candidate.allocation_amount_usdc,
                    market_id=candidate.market_id,
                    outcome=candidate.suggested_outcome,
                )

        # Print cycle summary
        mode = "DRY_RUN" if not self.trader.execute_trades else "LIVE"
        self.trader._print_trade_summary_table(selected, mode=f"{mode}_C{cycle}")

    def _filter_cooldown_markets(self, markets, budget: SessionBudgetManager):
        result = []
        for market_obj in markets:
            market_doc = (
                market_obj[0] if isinstance(market_obj, (list, tuple)) else None
            )
            metadata = getattr(market_doc, "metadata", {}) or {}
            try:
                market_id = int(metadata.get("id", 0))
            except (TypeError, ValueError):
                market_id = 0
            if not budget.is_on_cooldown(market_id, self.cooldown_seconds):
                result.append(market_obj)
        return result

    def _prioritize_volatile_markets(self, markets, ws: WebSocketManager):
        """Move markets with high orderbook price volatility to the front."""
        # For now, return as-is. Volatility detection requires subscribed orderbooks.
        # Future: track price_change events and reorder by magnitude.
        return markets


def start_continuous(
    interval: int = 30,
    session_budget: float = 100.0,
    cooldown: int = 300,
    include_news: bool = False,
    exclude_sports: bool = False,
    news_limit: int = 5,
    news_days: int = 7,
    news_relevance: bool = True,
    volatility_threshold: float = 0.05,
) -> None:
    from agents.application.runner import run_strategy

    strategy = ContinuousStrategy(
        include_news=include_news,
        exclude_sports=exclude_sports,
        news_limit=news_limit,
        news_days=news_days,
        news_relevance=news_relevance,
        cooldown_seconds=cooldown,
        volatility_threshold=volatility_threshold,
    )
    run_strategy(
        strategy_fn=strategy.run_cycle,
        session_budget=session_budget,
        interval_seconds=interval,
        connect_rtds=False,  # continuous mode doesn't need RTDS
    )
