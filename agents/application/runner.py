import asyncio
import logging
import signal
from typing import Callable, Coroutine, Optional

from agents.application.budget import SessionBudgetManager
from agents.connectors.websocket import WebSocketManager

logger = logging.getLogger(__name__)


class AsyncRunner:
    def __init__(
        self,
        session_budget: float,
        interval_seconds: int = 30,
        history_size: int = 300,
    ) -> None:
        self.budget = SessionBudgetManager(total_budget=session_budget)
        self.ws = WebSocketManager(history_size=history_size)
        self.interval_seconds = interval_seconds
        self.cycle_count = 0
        self._running = True

    def should_continue(self) -> bool:
        return self._running and not self.budget.is_exhausted()

    def stop(self) -> None:
        self._running = False

    async def run(
        self,
        strategy_fn: Callable[["AsyncRunner", int], Coroutine],
        market_token_ids: Optional[list[str]] = None,
        connect_rtds: bool = True,
    ) -> None:
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, self.stop)
        loop.add_signal_handler(signal.SIGTERM, self.stop)

        logger.info(
            "[runner] starting budget=%.2f interval=%ds",
            self.budget.total_budget,
            self.interval_seconds,
        )

        if connect_rtds or market_token_ids:
            await self.ws.start(market_token_ids=market_token_ids)
            # brief pause to let initial WS data arrive
            await asyncio.sleep(2)

        try:
            while self.should_continue():
                self.cycle_count += 1
                logger.info(
                    "[runner] cycle=%d remaining=%.2f",
                    self.cycle_count,
                    self.budget.remaining(),
                )
                try:
                    await strategy_fn(self, self.cycle_count)
                except Exception as err:
                    logger.error(
                        "[runner] cycle_error cycle=%d error=%s", self.cycle_count, err
                    )

                if self.should_continue():
                    await asyncio.sleep(self.interval_seconds)
        finally:
            await self.ws.stop()
            print()
            print("=" * 60)
            print("SESSION COMPLETE")
            print(self.budget.summary())
            print("=" * 60)


def run_strategy(
    strategy_fn: Callable[[AsyncRunner, int], Coroutine],
    session_budget: float,
    interval_seconds: int = 30,
    market_token_ids: Optional[list[str]] = None,
    connect_rtds: bool = True,
) -> None:
    """Synchronous entry point for CLI commands."""
    runner = AsyncRunner(
        session_budget=session_budget,
        interval_seconds=interval_seconds,
    )
    asyncio.run(
        runner.run(
            strategy_fn=strategy_fn,
            market_token_ids=market_token_ids,
            connect_rtds=connect_rtds,
        )
    )
