"""
Unit tests for agents/sports.py — sports pipeline entry point and dry-run mode.
All external dependencies are mocked to prevent actual WS connections or API calls.
"""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestDryRunResolution:
    def test_sports_execute_trades_overrides_master_false(self, monkeypatch):
        """SPORTS_EXECUTE_TRADES=false => dry_run=True regardless of EXECUTE_TRADES."""
        monkeypatch.setenv("SPORTS_EXECUTE_TRADES", "false")
        monkeypatch.setenv("EXECUTE_TRADES", "true")
        from agents.sports import _resolve_dry_run

        assert _resolve_dry_run() is True

    def test_sports_execute_trades_overrides_master_true(self, monkeypatch):
        """SPORTS_EXECUTE_TRADES=true => dry_run=False."""
        monkeypatch.setenv("SPORTS_EXECUTE_TRADES", "true")
        monkeypatch.setenv("EXECUTE_TRADES", "false")
        from agents.sports import _resolve_dry_run

        assert _resolve_dry_run() is False

    def test_falls_back_to_execute_trades_when_not_set(self, monkeypatch):
        """When SPORTS_EXECUTE_TRADES absent, falls back to EXECUTE_TRADES."""
        monkeypatch.delenv("SPORTS_EXECUTE_TRADES", raising=False)
        monkeypatch.setenv("EXECUTE_TRADES", "true")
        from agents.sports import _resolve_dry_run

        assert _resolve_dry_run() is False

    def test_dry_run_when_both_absent(self, monkeypatch):
        """When neither flag is set, defaults to dry-run (safe default)."""
        monkeypatch.delenv("SPORTS_EXECUTE_TRADES", raising=False)
        monkeypatch.delenv("EXECUTE_TRADES", raising=False)
        from agents.sports import _resolve_dry_run

        assert _resolve_dry_run() is True


def _make_ws_mock():
    """Create a WS connector mock with expected interface."""
    mock = MagicMock()
    mock.get_all_game_states.return_value = {}
    mock.get_message_queue.return_value = MagicMock()
    mock.get_message_queue.return_value.get_nowait.side_effect = Exception("empty")
    return mock


def _make_gamma_mock():
    mock = MagicMock()
    mock.build_slug_table.return_value = ({}, [])
    return mock


class TestMainInitialization:
    @patch("agents.sports.time.sleep", side_effect=KeyboardInterrupt)
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_main_initializes_all_components(
        self, MockBudget, MockWS, MockGamma, MockData, mock_sleep, monkeypatch
    ):
        """main() must initialize BudgetCoordinator, GammaMarketClient, SportsDataConnector, SportsWSConnector."""
        monkeypatch.setenv("SPORTS_EXECUTE_TRADES", "false")
        monkeypatch.setenv("SPORTS_INITIAL_WALLET_USD", "1000.0")
        MockWS.return_value = _make_ws_mock()
        MockGamma.return_value = _make_gamma_mock()

        import agents.sports as sports_mod

        try:
            sports_mod.main()
        except KeyboardInterrupt:
            pass

        MockBudget.assert_called_once()
        MockWS.assert_called_once()
        MockGamma.assert_called_once()
        MockData.assert_called_once()

    @patch("agents.sports.time.sleep", side_effect=KeyboardInterrupt)
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_main_builds_initial_slug_table(
        self, MockBudget, MockWS, MockGamma, MockData, mock_sleep, monkeypatch
    ):
        """main() must call build_slug_table with game states from WS connector."""
        monkeypatch.setenv("SPORTS_EXECUTE_TRADES", "false")
        monkeypatch.setenv("SPORTS_INITIAL_WALLET_USD", "1000.0")
        ws_mock = _make_ws_mock()
        ws_mock.get_all_game_states.return_value = {"game1": MagicMock()}
        MockWS.return_value = ws_mock
        gamma_mock = _make_gamma_mock()
        MockGamma.return_value = gamma_mock

        import agents.sports as sports_mod

        try:
            sports_mod.main()
        except KeyboardInterrupt:
            pass

        gamma_mock.build_slug_table.assert_called_once()

    @patch("agents.sports.time.sleep", side_effect=KeyboardInterrupt)
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_main_dry_run_false_when_sports_flag_true(
        self, MockBudget, MockWS, MockGamma, MockData, mock_sleep, monkeypatch, capsys
    ):
        """main() respects SPORTS_EXECUTE_TRADES=true => not dry_run."""
        monkeypatch.setenv("SPORTS_EXECUTE_TRADES", "true")
        monkeypatch.setenv("SPORTS_INITIAL_WALLET_USD", "1000.0")
        MockWS.return_value = _make_ws_mock()
        MockGamma.return_value = _make_gamma_mock()

        import agents.sports as sports_mod

        try:
            sports_mod.main()
        except KeyboardInterrupt:
            pass

        captured = capsys.readouterr()
        assert "dry_run=False" in captured.out

    @patch("agents.sports.time.sleep", side_effect=KeyboardInterrupt)
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_main_dry_run_true_when_sports_flag_false(
        self, MockBudget, MockWS, MockGamma, MockData, mock_sleep, monkeypatch, capsys
    ):
        """main() respects SPORTS_EXECUTE_TRADES=false => dry_run=True."""
        monkeypatch.setenv("SPORTS_EXECUTE_TRADES", "false")
        monkeypatch.setenv("SPORTS_INITIAL_WALLET_USD", "1000.0")
        MockWS.return_value = _make_ws_mock()
        MockGamma.return_value = _make_gamma_mock()

        import agents.sports as sports_mod

        try:
            sports_mod.main()
        except KeyboardInterrupt:
            pass

        captured = capsys.readouterr()
        assert "dry_run=True" in captured.out

    @patch("agents.sports.time.sleep", side_effect=KeyboardInterrupt)
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_main_falls_back_to_master_execute_flag(
        self, MockBudget, MockWS, MockGamma, MockData, mock_sleep, monkeypatch, capsys
    ):
        """When SPORTS_EXECUTE_TRADES absent, falls back to EXECUTE_TRADES."""
        monkeypatch.delenv("SPORTS_EXECUTE_TRADES", raising=False)
        monkeypatch.setenv("EXECUTE_TRADES", "false")
        monkeypatch.setenv("SPORTS_INITIAL_WALLET_USD", "1000.0")
        MockWS.return_value = _make_ws_mock()
        MockGamma.return_value = _make_gamma_mock()

        import agents.sports as sports_mod

        try:
            sports_mod.main()
        except KeyboardInterrupt:
            pass

        captured = capsys.readouterr()
        assert "dry_run=True" in captured.out


class TestMainIdle:
    @patch("agents.sports.time.sleep", side_effect=KeyboardInterrupt)
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_main_does_not_crash_with_no_active_games(
        self, MockBudget, MockWS, MockGamma, MockData, mock_sleep, monkeypatch
    ):
        """main() runs idle loop without crashing when no games are active."""
        monkeypatch.setenv("SPORTS_EXECUTE_TRADES", "false")
        monkeypatch.setenv("SPORTS_INITIAL_WALLET_USD", "1000.0")
        ws_mock = _make_ws_mock()
        ws_mock.get_all_game_states.return_value = {}
        MockWS.return_value = ws_mock
        MockGamma.return_value = _make_gamma_mock()

        import agents.sports as sports_mod

        # main() handles KeyboardInterrupt internally and exits cleanly — no exception raised
        sports_mod.main()


class TestCleanShutdown:
    @patch("agents.sports.time.sleep", side_effect=KeyboardInterrupt)
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_keyboard_interrupt_calls_connector_stop(
        self, MockBudget, MockWS, MockGamma, MockData, mock_sleep, monkeypatch
    ):
        """main() calls connector.stop() on KeyboardInterrupt for clean shutdown."""
        monkeypatch.setenv("SPORTS_EXECUTE_TRADES", "false")
        monkeypatch.setenv("SPORTS_INITIAL_WALLET_USD", "1000.0")
        ws_mock = _make_ws_mock()
        MockWS.return_value = ws_mock
        MockGamma.return_value = _make_gamma_mock()

        import agents.sports as sports_mod

        try:
            sports_mod.main()
        except KeyboardInterrupt:
            pass

        ws_mock.stop.assert_called_once()


class TestModuleEntryPoint:
    def test_sports_module_is_importable(self):
        """agents.sports can be imported without error."""
        import agents.sports as sports_mod

        assert hasattr(sports_mod, "main")
        assert callable(sports_mod.main)

    def test_sports_module_has_main_block(self):
        """agents/sports.py contains if __name__ == '__main__' block."""
        import inspect

        import agents.sports as sports_mod

        source = inspect.getsource(sports_mod)
        assert '__name__ == "__main__"' in source or "__name__ == '__main__'" in source
