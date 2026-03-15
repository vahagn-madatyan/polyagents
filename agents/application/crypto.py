import asyncio
import logging
import os
from typing import Dict, List, Optional

from agents.application.market_filter import (
    SYMBOL_MAP,
    CryptoMarketInfo,
    extract_crypto_price_target,
    is_crypto_price_market,
    parse_market_expiry_seconds,
)
from agents.application.prompts import Prompter

logger = logging.getLogger(__name__)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class CryptoStrategy:
    def __init__(
        self,
        symbols: list[str],
        min_edge: float = 0.05,
    ) -> None:
        from agents.application.executor import Executor as Agent
        from agents.application.trade import Trader

        self.trader = Trader()
        self.agent = Agent()
        self.prompter = Prompter()
        self.symbols = [s.upper() for s in symbols]
        self.min_edge = min_edge
        self._cached_markets: Optional[list] = None
        self._markets_fetched_cycle = 0
        self._markets_refresh_cycles = 10

    async def run_cycle(self, runner, cycle: int) -> None:
        budget = runner.budget
        ws = runner.ws

        if not budget.can_spend(self.trader.min_order_amount_usdc):
            logger.info("[crypto] budget_exhausted")
            runner.stop()
            return

        # Refresh crypto markets periodically
        if (
            self._cached_markets is None
            or (cycle - self._markets_fetched_cycle) >= self._markets_refresh_cycles
        ):
            all_events = await asyncio.to_thread(
                self.trader.polymarket.get_all_tradeable_events
            )
            all_markets_raw = await asyncio.to_thread(
                self.agent.map_filtered_events_to_markets, all_events
            )
            # Filter for crypto price markets only
            self._cached_markets = self._filter_crypto_price_markets(all_markets_raw)
            self._markets_fetched_cycle = cycle
            logger.info("[crypto] cached_crypto_markets=%d", len(self._cached_markets))

        crypto_markets = self._cached_markets
        if not crypto_markets:
            logger.info("[crypto] no_crypto_markets_found")
            return

        # Evaluate each market with live price data
        for market_info, market_data in crypto_markets:
            if not budget.can_spend(self.trader.min_order_amount_usdc):
                break

            if budget.is_on_cooldown(market_data["market_id"], cooldown_seconds=300):
                continue

            # Get live price
            live_price = ws.get_price(market_info.ws_key_binance)
            if live_price is None:
                continue

            # Calculate momentum
            momentum_1m = ws.get_momentum(market_info.ws_key_binance, window_secs=60)
            momentum_5m = ws.get_momentum(market_info.ws_key_binance, window_secs=300)
            momentum_15m = ws.get_momentum(market_info.ws_key_binance, window_secs=900)

            # Time remaining
            time_remaining = parse_market_expiry_seconds(market_data.get("end", ""))
            hours_remaining = (time_remaining or 0) / 3600.0
            if hours_remaining <= 0:
                continue

            # Get market prices
            yes_price = _safe_float(market_data.get("yes_price", 0.5))
            no_price = _safe_float(market_data.get("no_price", 0.5))

            # LLM analysis
            prompt = self.prompter.crypto_price_analyst(
                symbol=market_info.symbol,
                current_price=live_price,
                target_price=market_info.target_price,
                direction=market_info.direction,
                momentum_1m=momentum_1m,
                momentum_5m=momentum_5m,
                momentum_15m=momentum_15m,
                time_remaining_hours=hours_remaining,
                market_yes_price=yes_price,
                market_no_price=no_price,
            )

            try:
                response = await asyncio.to_thread(
                    self.agent._invoke_llm,
                    prompt,
                    "crypto_price_analysis",
                )
                trade_json = self.agent._parse_json_object(response)
            except Exception as err:
                logger.error(
                    "[crypto] llm_error market_id=%s error=%s",
                    market_data.get("market_id"),
                    err,
                )
                continue

            # Check edge
            probs = trade_json.get("probabilities", [])
            selected_outcome = trade_json.get("selected_outcome", "")
            side = str(trade_json.get("side", "BUY")).upper()

            model_prob = 0.5
            for p in probs:
                if p.get("outcome") == selected_outcome:
                    model_prob = _safe_float(p.get("likelihood", 0.5))
                    break

            implied_prob = yes_price if selected_outcome == "Yes" else no_price
            edge = abs(model_prob - implied_prob)

            if edge < self.min_edge:
                logger.info(
                    "[crypto] skipped_low_edge market_id=%s edge=%.4f min=%.4f",
                    market_data.get("market_id"),
                    edge,
                    self.min_edge,
                )
                continue

            # Determine allocation
            alloc = min(budget.remaining() * 0.10, budget.remaining())
            alloc = max(alloc, self.trader.min_order_amount_usdc)
            if not budget.can_spend(alloc):
                continue

            # Execute or dry run
            market_id = market_data.get("market_id", 0)
            if self.trader.execute_trades:
                try:
                    token_map = self.trader.polymarket.resolve_token_for_outcome(
                        outcomes=market_data.get("outcomes", []),
                        token_ids=market_data.get("token_ids", []),
                        selected_outcome=selected_outcome,
                        side=side,
                    )
                    await asyncio.to_thread(
                        self.trader.polymarket.execute_market_order_for_token,
                        token_map["token_id"],
                        alloc,
                    )
                    budget.record_trade(alloc, market_id, selected_outcome)
                    logger.info(
                        "[crypto] executed market_id=%d amount=%.2f outcome=%s edge=%.4f",
                        market_id,
                        alloc,
                        selected_outcome,
                        edge,
                    )
                except Exception as err:
                    logger.error(
                        "[crypto] execution_failed market_id=%d error=%s",
                        market_id,
                        err,
                    )
            else:
                budget.record_trade(alloc, market_id, selected_outcome)
                logger.info(
                    "[crypto] dry_run market_id=%d amount=%.2f outcome=%s edge=%.4f",
                    market_id,
                    alloc,
                    selected_outcome,
                    edge,
                )

        logger.info(
            "[crypto] cycle=%d complete remaining=%.2f", cycle, budget.remaining()
        )

    def _filter_crypto_price_markets(self, markets_raw) -> list:
        """Filter SimpleMarket list for crypto price markets and extract info."""
        results = []
        for market in markets_raw:
            if isinstance(market, dict):
                question = market.get("question", "")
                data = market
            else:
                question = getattr(market, "question", "")
                data = {
                    "market_id": getattr(market, "id", 0),
                    "question": question,
                    "end": getattr(market, "end", ""),
                    "outcomes": self.agent._parse_literal_list(
                        getattr(market, "outcomes", "[]")
                    ),
                    "token_ids": self.agent._parse_literal_list(
                        getattr(market, "clob_token_ids", "[]")
                    ),
                    "yes_price": 0.5,
                    "no_price": 0.5,
                }
                prices = self.agent._parse_literal_list(
                    getattr(market, "outcome_prices", "[]")
                )
                if len(prices) >= 2:
                    data["yes_price"] = _safe_float(prices[0], 0.5)
                    data["no_price"] = _safe_float(prices[1], 0.5)

            if not is_crypto_price_market(question):
                continue

            info = extract_crypto_price_target(question)
            if info is None:
                continue

            if info.symbol not in self.symbols:
                continue

            results.append((info, data))

        logger.info(
            "[crypto] found %d crypto price markets for symbols %s",
            len(results),
            self.symbols,
        )
        return results


def start_crypto(
    interval: int = 30,
    session_budget: float = 100.0,
    symbols: str = "BTC,ETH,SOL,XRP",
    min_edge: float = 0.05,
) -> None:
    from agents.application.runner import run_strategy

    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    strategy = CryptoStrategy(
        symbols=symbol_list,
        min_edge=min_edge,
    )
    run_strategy(
        strategy_fn=strategy.run_cycle,
        session_budget=session_budget,
        interval_seconds=interval,
        connect_rtds=True,
    )
