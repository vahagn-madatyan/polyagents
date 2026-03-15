import asyncio
import logging
import os
from typing import Optional

from agents.application.market_filter import (
    SYMBOL_MAP,
    extract_crypto_price_target,
    is_5min_btc_market,
    parse_market_expiry_seconds,
)

logger = logging.getLogger(__name__)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def compute_model_probability(
    current_price: float,
    target_price: float,
    direction: str,
    momentum_1m: float,
    momentum_5m: float,
    time_remaining_secs: float,
) -> float:
    """
    Pure algorithmic probability estimate for whether BTC will be
    above/below target within the time window.

    Factors:
    - Distance from target as % of price
    - Momentum (1m and 5m weighted)
    - Time remaining (more time = more uncertainty)
    """
    if target_price == 0:
        return 0.5

    # Distance factor: how far current price is from target
    distance_pct = (current_price - target_price) / target_price

    # For "above" direction: positive distance = favorable
    # For "below" direction: negative distance = favorable
    if direction == "below":
        distance_pct = -distance_pct

    # Momentum factor (weighted: 5m momentum matters more for 5-min markets)
    momentum_signal = momentum_1m * 0.4 + momentum_5m * 0.6
    if direction == "below":
        momentum_signal = -momentum_signal

    # Time decay: less time remaining = distance matters more
    time_factor = max(0.1, min(1.0, time_remaining_secs / 600.0))

    # Combine signals into a raw score
    # distance_pct of 0.01 (1%) is significant for 5-min window
    distance_score = distance_pct * 50  # scale so 1% = 0.5 score units
    momentum_score = momentum_signal * 200  # scale so 0.5% momentum = 1 score unit

    raw_score = 0.5 + distance_score * (1.0 / time_factor) + momentum_score

    # Clamp to [0.01, 0.99]
    return max(0.01, min(0.99, raw_score))


class BtcArbitrageStrategy:
    def __init__(
        self,
        max_per_trade: float = 5.0,
        min_edge: float = 0.10,
        price_feed_tolerance: float = 0.001,
    ) -> None:
        from agents.application.executor import Executor as Agent
        from agents.application.trade import Trader

        self.trader = Trader()
        self.agent = Agent()
        self.max_per_trade = max_per_trade
        self.min_edge = min_edge
        self.price_feed_tolerance = price_feed_tolerance
        self._cached_markets: Optional[list] = None
        self._markets_fetched_cycle = 0
        self._markets_refresh_cycles = 3  # refresh more frequently for 5-min markets

    async def run_cycle(self, runner, cycle: int) -> None:
        budget = runner.budget
        ws = runner.ws

        if not budget.can_spend(self.trader.min_order_amount_usdc):
            logger.info("[arb] budget_exhausted")
            runner.stop()
            return

        # Validate dual price feeds
        valid, avg_price = ws.validate_dual_feed(
            SYMBOL_MAP["BTC"]["binance"],
            SYMBOL_MAP["BTC"]["chainlink"],
            tolerance=self.price_feed_tolerance,
        )
        if not valid:
            binance_price = ws.get_price(SYMBOL_MAP["BTC"]["binance"])
            chainlink_price = ws.get_price(SYMBOL_MAP["BTC"]["chainlink"])
            logger.warning(
                "[arb] dual_feed_invalid binance=%s chainlink=%s tolerance=%s",
                binance_price,
                chainlink_price,
                self.price_feed_tolerance,
            )
            return

        current_btc_price = avg_price

        # Refresh 5-min BTC markets
        if (
            self._cached_markets is None
            or (cycle - self._markets_fetched_cycle) >= self._markets_refresh_cycles
        ):
            all_events = await asyncio.to_thread(
                self.trader.polymarket.get_all_tradeable_events
            )
            all_markets = await asyncio.to_thread(
                self.agent.map_filtered_events_to_markets, all_events
            )
            self._cached_markets = self._filter_5min_btc_markets(all_markets)
            self._markets_fetched_cycle = cycle
            logger.info("[arb] cached_5min_markets=%d", len(self._cached_markets))

        markets_5min = self._cached_markets
        if not markets_5min:
            logger.info("[arb] no_5min_btc_markets")
            return

        trades_this_cycle = 0
        for market_info, market_data in markets_5min:
            if not budget.can_spend(self.trader.min_order_amount_usdc):
                break

            market_id = market_data.get("market_id", 0)
            if budget.is_on_cooldown(market_id, cooldown_seconds=300):
                continue

            # Time remaining
            time_remaining = parse_market_expiry_seconds(market_data.get("end", ""))
            if time_remaining is None or time_remaining <= 0:
                continue
            if time_remaining > 600:  # skip if more than 10 minutes out
                continue

            # Momentum
            momentum_1m = ws.get_momentum(SYMBOL_MAP["BTC"]["binance"], window_secs=60)
            momentum_5m = ws.get_momentum(SYMBOL_MAP["BTC"]["binance"], window_secs=300)

            # Model probability
            model_prob = compute_model_probability(
                current_price=current_btc_price,
                target_price=market_info.target_price,
                direction=market_info.direction,
                momentum_1m=momentum_1m,
                momentum_5m=momentum_5m,
                time_remaining_secs=time_remaining,
            )

            # Market implied probability
            yes_price = _safe_float(market_data.get("yes_price", 0.5))
            no_price = _safe_float(market_data.get("no_price", 0.5))

            # Determine trade direction
            if model_prob > yes_price + self.min_edge:
                selected_outcome = "Yes"
                side = "BUY"
                edge = model_prob - yes_price
            elif (1 - model_prob) > no_price + self.min_edge:
                selected_outcome = "No"
                side = "BUY"
                edge = (1 - model_prob) - no_price
            else:
                continue  # no edge

            alloc = min(self.max_per_trade, budget.remaining())
            if alloc < self.trader.min_order_amount_usdc:
                continue

            logger.info(
                "[arb] signal market_id=%d target=%.0f current=%.0f model_prob=%.4f "
                "implied_yes=%.4f edge=%.4f outcome=%s time_left=%.0fs",
                market_id,
                market_info.target_price,
                current_btc_price,
                model_prob,
                yes_price,
                edge,
                selected_outcome,
                time_remaining,
            )

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
                    trades_this_cycle += 1
                    logger.info(
                        "[arb] executed market_id=%d amount=%.2f", market_id, alloc
                    )
                except Exception as err:
                    logger.error(
                        "[arb] execution_failed market_id=%d error=%s", market_id, err
                    )
            else:
                budget.record_trade(alloc, market_id, selected_outcome)
                trades_this_cycle += 1
                logger.info(
                    "[arb] dry_run market_id=%d amount=%.2f edge=%.4f",
                    market_id,
                    alloc,
                    edge,
                )

        logger.info(
            "[arb] cycle=%d trades=%d remaining=%.2f btc=%.0f",
            cycle,
            trades_this_cycle,
            budget.remaining(),
            current_btc_price,
        )

    def _filter_5min_btc_markets(self, markets_raw) -> list:
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

            if not is_5min_btc_market(question):
                continue

            info = extract_crypto_price_target(question)
            if info is None:
                continue

            results.append((info, data))

        return results


def start_btc_arbitrage(
    session_budget: float = 50.0,
    max_per_trade: float = 5.0,
    min_edge: float = 0.10,
    price_feed_tolerance: float = 0.001,
) -> None:
    from agents.application.runner import run_strategy

    strategy = BtcArbitrageStrategy(
        max_per_trade=max_per_trade,
        min_edge=min_edge,
        price_feed_tolerance=price_feed_tolerance,
    )
    run_strategy(
        strategy_fn=strategy.run_cycle,
        session_budget=session_budget,
        interval_seconds=15,  # faster interval for 5-min markets
        connect_rtds=True,
    )
