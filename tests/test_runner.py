import asyncio

import pytest

from agents.application.runner import AsyncRunner
from agents.application.budget import SessionBudgetManager
from agents.connectors.websocket import WebSocketManager


class TestAsyncRunner:
    def test_creation(self):
        runner = AsyncRunner(
            session_budget=100.0,
            interval_seconds=30,
        )
        assert isinstance(runner.budget, SessionBudgetManager)
        assert isinstance(runner.ws, WebSocketManager)
        assert runner.interval_seconds == 30
        assert runner.budget.total_budget == 100.0

    def test_should_continue_fresh(self):
        runner = AsyncRunner(session_budget=100.0, interval_seconds=30)
        assert runner.should_continue() is True

    def test_should_continue_exhausted(self):
        runner = AsyncRunner(session_budget=10.0, interval_seconds=30)
        runner.budget.record_trade(10.0, market_id=1, outcome="Yes")
        assert runner.should_continue() is False

    def test_should_continue_stopped(self):
        runner = AsyncRunner(session_budget=100.0, interval_seconds=30)
        runner.stop()
        assert runner.should_continue() is False

    def test_cycle_count(self):
        runner = AsyncRunner(session_budget=100.0, interval_seconds=30)
        assert runner.cycle_count == 0
        runner.cycle_count += 1
        assert runner.cycle_count == 1
