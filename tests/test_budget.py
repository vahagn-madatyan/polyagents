import time

from agents.application.budget import SessionBudgetManager, TradeRecord


class TestSessionBudgetManager:
    def test_initial_state(self):
        mgr = SessionBudgetManager(total_budget=100.0)
        assert mgr.total_budget == 100.0
        assert mgr.spent == 0.0
        assert mgr.remaining() == 100.0
        assert mgr.trades == []

    def test_can_spend_within_budget(self):
        mgr = SessionBudgetManager(total_budget=100.0)
        assert mgr.can_spend(50.0) is True
        assert mgr.can_spend(100.0) is True
        assert mgr.can_spend(100.01) is False

    def test_record_trade_updates_spent(self):
        mgr = SessionBudgetManager(total_budget=100.0)
        mgr.record_trade(amount=25.0, market_id=123, outcome="Yes")
        assert mgr.spent == 25.0
        assert mgr.remaining() == 75.0
        assert len(mgr.trades) == 1
        assert mgr.trades[0].amount == 25.0
        assert mgr.trades[0].market_id == 123

    def test_can_spend_after_spending(self):
        mgr = SessionBudgetManager(total_budget=100.0)
        mgr.record_trade(amount=90.0, market_id=1, outcome="Yes")
        assert mgr.can_spend(10.0) is True
        assert mgr.can_spend(10.01) is False

    def test_budget_exhausted(self):
        mgr = SessionBudgetManager(total_budget=50.0)
        mgr.record_trade(amount=50.0, market_id=1, outcome="Yes")
        assert mgr.remaining() == 0.0
        assert mgr.can_spend(0.01) is False
        assert mgr.is_exhausted() is True

    def test_summary_output(self):
        mgr = SessionBudgetManager(total_budget=100.0)
        mgr.record_trade(amount=25.0, market_id=1, outcome="Yes")
        mgr.record_trade(amount=10.0, market_id=2, outcome="No")
        summary = mgr.summary()
        assert "100.00" in summary
        assert "35.00" in summary
        assert "65.00" in summary
        assert "2 trades" in summary

    def test_cooldown_tracking(self):
        mgr = SessionBudgetManager(total_budget=100.0)
        mgr.record_trade(amount=10.0, market_id=42, outcome="Yes")
        assert mgr.is_on_cooldown(42, cooldown_seconds=300) is True
        assert mgr.is_on_cooldown(99, cooldown_seconds=300) is False

    def test_zero_budget(self):
        mgr = SessionBudgetManager(total_budget=0.0)
        assert mgr.is_exhausted() is True
        assert mgr.can_spend(0.01) is False
