"""
Unit tests for BudgetCoordinator — cross-process budget coordination with filelock.
"""

import json
import os
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from agents.application.budget import BudgetCoordinator


@pytest.fixture
def budget_env(tmp_path, monkeypatch):
    """Set env vars pointing lock and JSON file at tmp_path."""
    lock_path = str(tmp_path / "budget.lock")
    json_path = str(tmp_path / "budget.json")
    monkeypatch.setenv("SPORTS_BUDGET_FRACTION", "0.30")
    monkeypatch.setenv("SPORTS_MIN_WALLET_USD", "50.0")
    monkeypatch.setenv("SPORTS_BUDGET_LOCK_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("SPORTS_BUDGET_LOCK_PATH", lock_path)
    monkeypatch.setenv("SPORTS_BUDGET_FILE_PATH", json_path)
    # Clear any per-sport caps to test defaults
    monkeypatch.delenv("SPORTS_CAP_NFL", raising=False)
    monkeypatch.delenv("SPORTS_CAP_NBA", raising=False)
    monkeypatch.delenv("SPORTS_CAP_MLB", raising=False)
    monkeypatch.delenv("SPORTS_CAP_NHL", raising=False)
    return {"lock_path": lock_path, "json_path": json_path}


@pytest.fixture
def budget_env_with_caps(tmp_path, monkeypatch):
    """Env with per-sport caps configured."""
    lock_path = str(tmp_path / "budget.lock")
    json_path = str(tmp_path / "budget.json")
    monkeypatch.setenv("SPORTS_BUDGET_FRACTION", "0.30")
    monkeypatch.setenv("SPORTS_MIN_WALLET_USD", "50.0")
    monkeypatch.setenv("SPORTS_BUDGET_LOCK_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("SPORTS_BUDGET_LOCK_PATH", lock_path)
    monkeypatch.setenv("SPORTS_BUDGET_FILE_PATH", json_path)
    monkeypatch.setenv("SPORTS_CAP_NFL", "0.4")
    monkeypatch.setenv("SPORTS_CAP_NBA", "0.3")
    monkeypatch.setenv("SPORTS_CAP_MLB", "0.15")
    monkeypatch.setenv("SPORTS_CAP_NHL", "0.15")
    return {"lock_path": lock_path, "json_path": json_path}


class TestBudgetCoordinatorInit:
    def test_init_reads_sports_budget_fraction(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        assert bc.sports_budget == pytest.approx(300.0)

    def test_init_calculates_general_budget(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        assert bc.general_budget == pytest.approx(700.0)

    def test_init_reads_min_wallet(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        assert bc.min_wallet_usd == pytest.approx(50.0)

    def test_init_reads_lock_timeout(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        assert bc.lock_timeout == 5

    def test_init_with_zero_wallet(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=0.0)
        assert bc.sports_budget == pytest.approx(0.0)


class TestAllocateBudget:
    def test_allocate_budget_writes_json_file(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        result = bc.allocate_budget()
        json_path = budget_env["json_path"]
        assert os.path.exists(json_path)
        with open(json_path) as f:
            data = json.load(f)
        assert data["sports"] == pytest.approx(300.0)
        assert data["general"] == pytest.approx(700.0)

    def test_allocate_budget_returns_dict(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        result = bc.allocate_budget()
        assert isinstance(result, dict)
        assert "sports" in result
        assert "general" in result
        assert "wallet_balance" in result
        assert "timestamp" in result

    def test_allocate_budget_stores_wallet_balance(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        result = bc.allocate_budget()
        assert result["wallet_balance"] == pytest.approx(1000.0)


class TestGetBudgets:
    def test_get_sports_budget_after_allocate(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        bc.allocate_budget()
        assert bc.get_sports_budget() == pytest.approx(300.0)

    def test_get_general_budget_after_allocate(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        bc.allocate_budget()
        assert bc.get_general_budget() == pytest.approx(700.0)

    def test_get_budgets_sum_to_wallet(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        bc.allocate_budget()
        total = bc.get_sports_budget() + bc.get_general_budget()
        assert total == pytest.approx(1000.0)


class TestCanSpendSports:
    def test_can_spend_within_budget_and_wallet(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        bc.allocate_budget()
        assert bc.can_spend_sports(amount=50.0, wallet_balance=500.0) is True

    def test_cannot_spend_exceeds_sports_budget(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        bc.allocate_budget()
        assert bc.can_spend_sports(amount=400.0, wallet_balance=500.0) is False

    def test_cannot_spend_wallet_below_minimum(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        bc.allocate_budget()
        # wallet_balance=40 < SPORTS_MIN_WALLET_USD=50
        assert bc.can_spend_sports(amount=10.0, wallet_balance=40.0) is False

    def test_cannot_spend_exactly_at_minimum_wallet(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        bc.allocate_budget()
        # wallet_balance == SPORTS_MIN_WALLET_USD should be allowed
        assert bc.can_spend_sports(amount=10.0, wallet_balance=50.0) is True

    def test_cannot_spend_zero_amount(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        bc.allocate_budget()
        assert bc.can_spend_sports(amount=0.0, wallet_balance=500.0) is True


class TestPerSportCaps:
    def test_configured_league_cap(self, budget_env_with_caps):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        bc.allocate_budget()
        # NFL cap = 0.4 * sports_budget(300) = 120
        assert bc.get_sport_cap("NFL") == pytest.approx(120.0)

    def test_configured_league_cap_nba(self, budget_env_with_caps):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        bc.allocate_budget()
        # NBA cap = 0.3 * 300 = 90
        assert bc.get_sport_cap("NBA") == pytest.approx(90.0)

    def test_unconfigured_league_gets_equal_share(self, budget_env, monkeypatch):
        # No caps set — all leagues get equal share
        # With no specific leagues provided, unconfigured should share all sports budget equally
        bc = BudgetCoordinator(wallet_balance=1000.0)
        bc.allocate_budget()
        # No configured caps, so unknown league gets remainder/1 = all sports budget
        cap = bc.get_sport_cap("SOCCER")
        assert cap == pytest.approx(300.0)

    def test_caps_sum_does_not_exceed_sports_budget(self, budget_env_with_caps):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        bc.allocate_budget()
        total = (
            bc.get_sport_cap("NFL")
            + bc.get_sport_cap("NBA")
            + bc.get_sport_cap("MLB")
            + bc.get_sport_cap("NHL")
        )
        assert total <= bc.get_sports_budget() + 0.01  # small float tolerance

    def test_unconfigured_league_gets_remainder(self, budget_env, monkeypatch):
        """When NFL=0.4 is set, unconfigured gets 60% split equally."""
        monkeypatch.setenv("SPORTS_CAP_NFL", "0.4")
        bc = BudgetCoordinator(wallet_balance=1000.0)
        bc.allocate_budget()
        # NFL gets 120, remaining 60% = 180 goes to unconfigured
        unconfigured_cap = bc.get_sport_cap("NBA")
        assert unconfigured_cap == pytest.approx(180.0)


class TestRecordSportsTrade:
    def test_record_trade_decrements_sports_budget(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        bc.allocate_budget()
        bc.record_sports_trade(amount=50.0, league="NFL")
        assert bc.get_sports_budget() == pytest.approx(250.0)

    def test_record_multiple_trades(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        bc.allocate_budget()
        bc.record_sports_trade(amount=30.0, league="NFL")
        bc.record_sports_trade(amount=20.0, league="NBA")
        assert bc.get_sports_budget() == pytest.approx(250.0)

    def test_record_trade_updates_json_file(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        bc.allocate_budget()
        bc.record_sports_trade(amount=50.0, league="NFL")
        with open(budget_env["json_path"]) as f:
            data = json.load(f)
        assert data["sports"] == pytest.approx(250.0)


class TestConcurrentAccess:
    def test_two_instances_do_not_corrupt_shared_json(self, budget_env):
        """Two BudgetCoordinator instances writing to same file do not corrupt data."""
        bc1 = BudgetCoordinator(wallet_balance=1000.0)
        bc2 = BudgetCoordinator(wallet_balance=1000.0)
        bc1.allocate_budget()

        errors = []

        def trade_from_bc1():
            try:
                for _ in range(3):
                    bc1.record_sports_trade(amount=10.0, league="NFL")
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        def trade_from_bc2():
            try:
                for _ in range(3):
                    bc2.record_sports_trade(amount=10.0, league="NBA")
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=trade_from_bc1)
        t2 = threading.Thread(target=trade_from_bc2)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert errors == [], f"Errors during concurrent access: {errors}"

        # JSON must be valid after concurrent writes
        with open(budget_env["json_path"]) as f:
            data = json.load(f)
        assert isinstance(data["sports"], float)
        # 300 - 6 trades * 10 = 240
        assert data["sports"] == pytest.approx(240.0)


class TestWalletRefresh:
    def test_refresh_wallet_balance_updates_cached_balance(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        polymarket = MagicMock()
        polymarket.get_usdc_balance.return_value = 812.34

        balance = bc.refresh_wallet_balance(polymarket)

        assert balance == pytest.approx(812.34)
        assert bc.wallet_balance == pytest.approx(812.34)
        polymarket.get_usdc_balance.assert_called_once_with()

    def test_refresh_wallet_balance_uses_cooldown(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        polymarket = MagicMock()
        polymarket.get_usdc_balance.return_value = 777.0

        with patch(
            "agents.application.budget.time.time", side_effect=[100.0, 100.0, 110.0]
        ):
            first = bc.refresh_wallet_balance(polymarket)
            second = bc.refresh_wallet_balance(polymarket)

        assert first == pytest.approx(777.0)
        assert second == pytest.approx(777.0)
        assert polymarket.get_usdc_balance.call_count == 1

    def test_refresh_wallet_balance_refreshes_after_cooldown(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=1000.0)
        polymarket = MagicMock()
        polymarket.get_usdc_balance.side_effect = [777.0, 755.0]

        with patch(
            "agents.application.budget.time.time",
            side_effect=[100.0, 100.0, 131.0, 131.0],
        ):
            first = bc.refresh_wallet_balance(polymarket)
            second = bc.refresh_wallet_balance(polymarket)

        assert first == pytest.approx(777.0)
        assert second == pytest.approx(755.0)
        assert polymarket.get_usdc_balance.call_count == 2

    def test_refresh_wallet_balance_falls_back_on_api_error(self, budget_env, capsys):
        bc = BudgetCoordinator(wallet_balance=444.0)
        polymarket = MagicMock()
        polymarket.get_usdc_balance.side_effect = RuntimeError("boom")

        balance = bc.refresh_wallet_balance(polymarket)

        captured = capsys.readouterr()
        assert balance == pytest.approx(444.0)
        assert bc.wallet_balance == pytest.approx(444.0)
        assert "warn=wallet_refresh_failed" in captured.out

    def test_refresh_wallet_balance_skips_when_polymarket_missing(self, budget_env):
        bc = BudgetCoordinator(wallet_balance=555.0)

        balance = bc.refresh_wallet_balance(None)

        assert balance == pytest.approx(555.0)
