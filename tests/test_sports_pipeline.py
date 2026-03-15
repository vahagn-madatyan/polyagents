"""
Unit tests for agents/sports.py — sports pipeline entry point and dry-run mode.
All external dependencies are mocked to prevent actual WS connections or API calls.
"""

import os
import queue
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
    @patch("agents.sports.InGameTrader")
    @patch("agents.sports.SportsTrader")
    @patch("agents.sports.PregameCache")
    @patch("agents.sports.SportsExecutor")
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_main_initializes_all_components(
        self,
        MockBudget,
        MockWS,
        MockGamma,
        MockData,
        MockExecutor,
        MockCache,
        MockTrader,
        MockInGameTrader,
        mock_sleep,
        monkeypatch,
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
    @patch("agents.sports.InGameTrader")
    @patch("agents.sports.SportsTrader")
    @patch("agents.sports.PregameCache")
    @patch("agents.sports.SportsExecutor")
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_main_builds_initial_slug_table(
        self,
        MockBudget,
        MockWS,
        MockGamma,
        MockData,
        MockExecutor,
        MockCache,
        MockTrader,
        MockInGameTrader,
        mock_sleep,
        monkeypatch,
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
    @patch("agents.sports.InGameTrader")
    @patch("agents.sports.SportsTrader")
    @patch("agents.sports.PregameCache")
    @patch("agents.sports.SportsExecutor")
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_main_dry_run_false_when_sports_flag_true(
        self,
        MockBudget,
        MockWS,
        MockGamma,
        MockData,
        MockExecutor,
        MockCache,
        MockTrader,
        MockInGameTrader,
        mock_sleep,
        monkeypatch,
        capsys,
    ):
        """main() respects SPORTS_EXECUTE_TRADES=true => not dry_run."""
        monkeypatch.setenv("SPORTS_EXECUTE_TRADES", "true")
        monkeypatch.setenv("SPORTS_INITIAL_WALLET_USD", "1000.0")
        MockWS.return_value = _make_ws_mock()
        MockGamma.return_value = _make_gamma_mock()

        # Mock Polymarket for live mode
        mock_poly = MagicMock()
        mock_poly.get_usdc_balance.return_value = 1000.0

        import agents.sports as sports_mod

        with patch("agents.sports.SportsTrader") as MockTrader2, patch(
            "agents.sports.PregameCache"
        ) as MockCache2, patch("agents.sports.SportsExecutor") as MockExec2:
            with patch.dict(
                "sys.modules",
                {
                    "agents.polymarket.polymarket": MagicMock(
                        Polymarket=MagicMock(return_value=mock_poly)
                    )
                },
            ):
                try:
                    sports_mod.main()
                except (KeyboardInterrupt, Exception):
                    pass

        captured = capsys.readouterr()
        assert "dry_run=False" in captured.out

    @patch("agents.sports.time.sleep", side_effect=KeyboardInterrupt)
    @patch("agents.sports.InGameTrader")
    @patch("agents.sports.SportsTrader")
    @patch("agents.sports.PregameCache")
    @patch("agents.sports.SportsExecutor")
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_main_dry_run_true_when_sports_flag_false(
        self,
        MockBudget,
        MockWS,
        MockGamma,
        MockData,
        MockExecutor,
        MockCache,
        MockTrader,
        MockInGameTrader,
        mock_sleep,
        monkeypatch,
        capsys,
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
    @patch("agents.sports.InGameTrader")
    @patch("agents.sports.SportsTrader")
    @patch("agents.sports.PregameCache")
    @patch("agents.sports.SportsExecutor")
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_main_falls_back_to_master_execute_flag(
        self,
        MockBudget,
        MockWS,
        MockGamma,
        MockData,
        MockExecutor,
        MockCache,
        MockTrader,
        MockInGameTrader,
        mock_sleep,
        monkeypatch,
        capsys,
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
    @patch("agents.sports.InGameTrader")
    @patch("agents.sports.SportsTrader")
    @patch("agents.sports.PregameCache")
    @patch("agents.sports.SportsExecutor")
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_main_does_not_crash_with_no_active_games(
        self,
        MockBudget,
        MockWS,
        MockGamma,
        MockData,
        MockExecutor,
        MockCache,
        MockTrader,
        MockInGameTrader,
        mock_sleep,
        monkeypatch,
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
    @patch("agents.sports.InGameTrader")
    @patch("agents.sports.SportsTrader")
    @patch("agents.sports.PregameCache")
    @patch("agents.sports.SportsExecutor")
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_keyboard_interrupt_calls_connector_stop(
        self,
        MockBudget,
        MockWS,
        MockGamma,
        MockData,
        MockExecutor,
        MockCache,
        MockTrader,
        MockInGameTrader,
        mock_sleep,
        monkeypatch,
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


class TestPreGameWiring:
    """Tests for Phase 3 SportsTrader integration into the event loop."""

    @patch("agents.sports.time.sleep", side_effect=KeyboardInterrupt)
    @patch("agents.sports.InGameTrader")
    @patch("agents.sports.SportsTrader")
    @patch("agents.sports.PregameCache")
    @patch("agents.sports.SportsExecutor")
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_main_instantiates_sports_trader(
        self,
        MockBudget,
        MockWS,
        MockGamma,
        MockData,
        MockExecutor,
        MockCache,
        MockTrader,
        MockInGameTrader,
        mock_sleep,
        monkeypatch,
    ):
        """main() creates a SportsTrader instance after all Phase 3 components."""
        monkeypatch.setenv("SPORTS_EXECUTE_TRADES", "false")
        monkeypatch.setenv("SPORTS_INITIAL_WALLET_USD", "1000.0")
        MockWS.return_value = _make_ws_mock()
        MockGamma.return_value = _make_gamma_mock()

        import agents.sports as sports_mod

        try:
            sports_mod.main()
        except KeyboardInterrupt:
            pass

        MockTrader.assert_called_once()

    @patch("agents.sports.threading.Thread")
    @patch("agents.sports.time.sleep", side_effect=KeyboardInterrupt)
    @patch("agents.sports.InGameTrader")
    @patch("agents.sports.SportsTrader")
    @patch("agents.sports.PregameCache")
    @patch("agents.sports.SportsExecutor")
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_slug_table_triggers_pregame_analysis(
        self,
        MockBudget,
        MockWS,
        MockGamma,
        MockData,
        MockExecutor,
        MockCache,
        MockTrader,
        MockInGameTrader,
        mock_sleep,
        MockThread,
        monkeypatch,
    ):
        """When slug table maps a game, a pregame analysis thread is started."""
        monkeypatch.setenv("SPORTS_EXECUTE_TRADES", "false")
        monkeypatch.setenv("SPORTS_INITIAL_WALLET_USD", "1000.0")

        from agents.utils.objects import SportGameState, SportsMarketTag

        # Create a real game state + market tag so slug matching works
        gs = SportGameState(
            game_id=99,
            league="nba",
            slug="nba-lal-bos-2026-03-07",
            home_team="LAL",
            away_team="BOS",
            status="scheduled",
            score_raw="0-0",
            period="Pre",
            live=False,
            ended=False,
        )
        tag = SportsMarketTag(
            slug="nba-lal-bos-2026-03-07",
            league="nba",
            home_team="LAL",
            away_team="BOS",
            market_id="9001",
            condition_id="0xabc",
            token_id_yes="tok-yes",
            token_id_no="tok-no",
            question="Will the Lakers win?",
        )

        ws_mock = _make_ws_mock()
        ws_mock.get_all_game_states.return_value = {99: gs}
        MockWS.return_value = ws_mock

        gamma_mock = _make_gamma_mock()
        gamma_mock.build_slug_table.return_value = (
            {"nba-lal-bos-2026-03-07": [tag]},
            [],
        )
        MockGamma.return_value = gamma_mock

        # Trader mock: should_analyze returns True (cache stale)
        trader_instance = MagicMock()
        trader_instance.should_analyze.return_value = True
        MockTrader.return_value = trader_instance

        # Allow the ws thread to start but capture non-ws Thread calls
        started_threads = []

        def fake_thread(**kwargs):
            t = MagicMock()
            started_threads.append(kwargs)
            return t

        MockThread.side_effect = fake_thread

        import agents.sports as sports_mod

        try:
            sports_mod.main()
        except (KeyboardInterrupt, Exception):
            pass

        # At least one pregame thread should have been started
        pregame_threads = [
            t for t in started_threads if str(t.get("name", "")).startswith("pregame-")
        ]
        assert len(pregame_threads) >= 1

    @patch("agents.sports.time.sleep", side_effect=KeyboardInterrupt)
    @patch("agents.sports.InGameTrader")
    @patch("agents.sports.SportsTrader")
    @patch("agents.sports.PregameCache")
    @patch("agents.sports.SportsExecutor")
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_dry_run_uses_env_wallet_balance(
        self,
        MockBudget,
        MockWS,
        MockGamma,
        MockData,
        MockExecutor,
        MockCache,
        MockTrader,
        MockInGameTrader,
        mock_sleep,
        monkeypatch,
        capsys,
    ):
        """In dry-run mode, SPORTS_INITIAL_WALLET_USD env var is used instead of CLOB."""
        monkeypatch.setenv("SPORTS_EXECUTE_TRADES", "false")
        monkeypatch.setenv("SPORTS_INITIAL_WALLET_USD", "2500.0")
        MockWS.return_value = _make_ws_mock()
        MockGamma.return_value = _make_gamma_mock()

        import agents.sports as sports_mod

        try:
            sports_mod.main()
        except KeyboardInterrupt:
            pass

        captured = capsys.readouterr()
        assert "source=env" in captured.out
        assert "balance=2500.00" in captured.out

    @patch("agents.sports.time.sleep", side_effect=KeyboardInterrupt)
    @patch("agents.sports.InGameTrader")
    @patch("agents.sports.SportsTrader")
    @patch("agents.sports.PregameCache")
    @patch("agents.sports.SportsExecutor")
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_live_mode_fetches_clob_balance(
        self,
        MockBudget,
        MockWS,
        MockGamma,
        MockData,
        MockExecutor,
        MockCache,
        MockTrader,
        MockInGameTrader,
        mock_sleep,
        monkeypatch,
        capsys,
    ):
        """In live mode (SPORTS_EXECUTE_TRADES=true), Polymarket.get_usdc_balance() is called."""
        monkeypatch.setenv("SPORTS_EXECUTE_TRADES", "true")

        # Mock the lazy Polymarket import inside main()
        mock_poly_instance = MagicMock()
        mock_poly_instance.get_usdc_balance.return_value = 9999.0
        mock_poly_cls = MagicMock(return_value=mock_poly_instance)

        MockWS.return_value = _make_ws_mock()
        MockGamma.return_value = _make_gamma_mock()

        import agents.sports as sports_mod
        import sys

        # Patch the lazy import path used inside main()
        mock_poly_module = MagicMock()
        mock_poly_module.Polymarket = mock_poly_cls
        original = sys.modules.get("agents.polymarket.polymarket")
        sys.modules["agents.polymarket.polymarket"] = mock_poly_module
        try:
            sports_mod.main()
        except (KeyboardInterrupt, Exception):
            pass
        finally:
            if original is None:
                sys.modules.pop("agents.polymarket.polymarket", None)
            else:
                sys.modules["agents.polymarket.polymarket"] = original

        mock_poly_instance.get_usdc_balance.assert_called_once()
        captured = capsys.readouterr()
        assert "source=clob" in captured.out


class TestInGameTraderWiring:
    """Phase 4 integration tests: verify InGameTrader is wired into sports.py main()."""

    @patch("agents.sports.time.sleep", side_effect=KeyboardInterrupt)
    @patch("agents.sports.InGameTrader")
    @patch("agents.sports.SportsTrader")
    @patch("agents.sports.PregameCache")
    @patch("agents.sports.SportsExecutor")
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_ingame_trader_instantiated_with_shared_deps(
        self,
        MockBudget,
        MockWS,
        MockGamma,
        MockData,
        MockExecutor,
        MockCache,
        MockTrader,
        MockInGameTrader,
        mock_sleep,
        monkeypatch,
    ):
        """InGameTrader is constructed with the same shared dependencies as SportsTrader."""
        monkeypatch.setenv("EXECUTE_TRADES", "false")
        monkeypatch.delenv("SPORTS_EXECUTE_TRADES", raising=False)
        monkeypatch.setenv("SPORTS_INITIAL_WALLET_USD", "1000.0")

        ws_mock = _make_ws_mock()
        ws_mock.get_all_game_states.return_value = {1: MagicMock()}
        MockWS.return_value = ws_mock
        MockGamma.return_value = _make_gamma_mock()

        budget_instance = MagicMock()
        MockBudget.return_value = budget_instance

        data_instance = MagicMock()
        MockData.return_value = data_instance

        executor_instance = MagicMock()
        MockExecutor.return_value = executor_instance

        cache_instance = MagicMock()
        MockCache.return_value = cache_instance

        import agents.sports as sports_mod

        try:
            sports_mod.main()
        except KeyboardInterrupt:
            pass

        # InGameTrader must have been constructed
        MockInGameTrader.assert_called_once()
        call_kwargs = MockInGameTrader.call_args[1]

        # Verify shared dependency injection
        assert call_kwargs["budget_coordinator"] is budget_instance
        assert call_kwargs["data_connector"] is data_instance
        assert call_kwargs["executor"] is executor_instance
        assert call_kwargs["cache"] is cache_instance
        assert call_kwargs["dry_run"] is True  # EXECUTE_TRADES=false => dry_run=True
        assert call_kwargs["polymarket"] is None  # dry-run has no polymarket

    @patch("agents.sports.time.sleep", side_effect=KeyboardInterrupt)
    @patch("agents.sports.InGameTrader")
    @patch("agents.sports.SportsTrader")
    @patch("agents.sports.PregameCache")
    @patch("agents.sports.SportsExecutor")
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_ingame_trader_tick_called_in_loop(
        self,
        MockBudget,
        MockWS,
        MockGamma,
        MockData,
        MockExecutor,
        MockCache,
        MockTrader,
        MockInGameTrader,
        mock_sleep,
        monkeypatch,
    ):
        """ingame_trader.tick() is called in the main event loop with game_states_snapshot and slug_table."""
        monkeypatch.setenv("EXECUTE_TRADES", "false")
        monkeypatch.delenv("SPORTS_EXECUTE_TRADES", raising=False)
        monkeypatch.setenv("SPORTS_INITIAL_WALLET_USD", "1000.0")

        game_state_snapshot = {42: MagicMock()}
        ws_mock = _make_ws_mock()
        ws_mock.get_all_game_states.return_value = game_state_snapshot
        MockWS.return_value = ws_mock

        slug_table = {"nba-lal-bos": MagicMock()}
        gamma_mock = _make_gamma_mock()
        gamma_mock.build_slug_table.return_value = (slug_table, [])
        MockGamma.return_value = gamma_mock

        ingame_instance = MagicMock()
        MockInGameTrader.return_value = ingame_instance

        import agents.sports as sports_mod

        try:
            sports_mod.main()
        except KeyboardInterrupt:
            pass

        # tick() must have been called at least once in the loop
        assert ingame_instance.tick.called, "ingame_trader.tick() was not called"
        # Verify it was called with the game_states_snapshot and slug_table
        call_args = ingame_instance.tick.call_args
        assert call_args[0][0] == game_state_snapshot
        assert call_args[0][1] == slug_table

    @patch("agents.sports.time.sleep", side_effect=KeyboardInterrupt)
    @patch("agents.sports.InGameTrader")
    @patch("agents.sports.SportsTrader")
    @patch("agents.sports.PregameCache")
    @patch("agents.sports.SportsExecutor")
    @patch("agents.sports.SportsDataConnector")
    @patch("agents.sports.GammaMarketClient")
    @patch("agents.sports.SportsWSConnector")
    @patch("agents.sports.BudgetCoordinator")
    def test_period_transition_routed_to_ingame_trader(
        self,
        MockBudget,
        MockWS,
        MockGamma,
        MockData,
        MockExecutor,
        MockCache,
        MockTrader,
        MockInGameTrader,
        mock_sleep,
        monkeypatch,
    ):
        """period_transition messages from the queue are routed to ingame_trader.handle_period_transition()."""
        monkeypatch.setenv("EXECUTE_TRADES", "false")
        monkeypatch.delenv("SPORTS_EXECUTE_TRADES", raising=False)
        monkeypatch.setenv("SPORTS_INITIAL_WALLET_USD", "1000.0")

        # Build a real queue with one period_transition message
        msg = {
            "type": "period_transition",
            "game_id": 77,
            "state": {"score": "3-0"},
            "old_period": "Q1",
            "new_period": "Q2",
        }
        real_queue = queue.Queue()
        real_queue.put(msg)

        ws_mock = _make_ws_mock()
        # Return a non-empty game state so the wait loop exits without sleeping,
        # ensuring the main event loop runs at least one iteration to drain the queue.
        ws_mock.get_all_game_states.return_value = {77: MagicMock()}
        ws_mock.get_message_queue.return_value = real_queue
        MockWS.return_value = ws_mock

        slug_table = {"nba-lal-bos": MagicMock()}
        gamma_mock = _make_gamma_mock()
        gamma_mock.build_slug_table.return_value = (slug_table, [])
        MockGamma.return_value = gamma_mock

        ingame_instance = MagicMock()
        MockInGameTrader.return_value = ingame_instance

        import agents.sports as sports_mod

        try:
            sports_mod.main()
        except KeyboardInterrupt:
            pass

        # handle_period_transition() must have been called with the msg and slug_table
        assert (
            ingame_instance.handle_period_transition.called
        ), "ingame_trader.handle_period_transition() was not called"
        call_args = ingame_instance.handle_period_transition.call_args
        assert call_args[0][0] == msg
        assert call_args[0][1] == slug_table


class TestInGameTraderMarketLookup:
    """Integration tests: verify production-shaped slug_table results in successful market lookup."""

    def test_ingame_trader_market_lookup_succeeds_with_production_slug_table(
        self, monkeypatch
    ):
        """A production-shaped slug_table (dict[str, list[SportsMarketTag]]) causes
        InGameTrader.tick() to successfully resolve market_tag and enter the fast-path
        (cache.get() called), proving the lookup is NOT silently returning None.
        """
        import time

        from unittest.mock import MagicMock

        from agents.application.ingame_trader import InGameTrader
        from agents.utils.objects import SportsMarketTag, SportGameState

        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "0")
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")

        # Build a realistic SportsMarketTag
        tag = SportsMarketTag(
            slug="nba-lal-bos",
            league="nba",
            home_team="LAL",
            away_team="BOS",
            market_id="9001",
            condition_id="0xabc123def456",
            token_id_yes="tok-yes-001",
            token_id_no="tok-no-001",
            question="Will the Lakers win?",
            outcome_prices="0.6,0.4",
        )

        # Build production-shaped slug_table: keyed by slug string, value is list
        slug_table = {"nba-lal-bos": [tag]}

        # Build initial game state (baseline) — score 100-98, Lakers leading
        gs_initial = SportGameState(
            game_id=1,
            league="nba",
            slug="nba-lal-bos",
            home_team="LAL",
            away_team="BOS",
            status="InProgress",
            score_raw="100-98",
            home_score=100,
            away_score=98,
            period="Q4",
            live=True,
            ended=False,
        )

        # Build changed game state — score 102-98 (same leader, minor event -> fast-path)
        gs_changed = SportGameState(
            game_id=1,
            league="nba",
            slug="nba-lal-bos",
            home_team="LAL",
            away_team="BOS",
            status="InProgress",
            score_raw="102-98",
            home_score=102,
            away_score=98,
            period="Q4",
            live=True,
            ended=False,
        )

        # Wire up mocked dependencies
        budget = MagicMock()
        budget.can_spend_sports.return_value = True

        data_connector = MagicMock()
        data_connector.get_game_context.return_value = {
            "stats": {},
            "h2h": [],
            "odds": {},
        }

        executor = MagicMock()

        cache = MagicMock()
        cache.get.return_value = {
            "game_id": 1,
            "llm_home_win_prob": 0.70,
            "llm_away_win_prob": 0.30,
            "confidence_gap": 0.40,
            "selected_outcome": "Yes",
            "selected_side": "BUY",
            "timestamp": time.time(),
        }

        polymarket = MagicMock()
        polymarket.get_orderbook_price.return_value = 0.50  # divergence = 0.20 > 0.10

        # Instantiate a real InGameTrader (not mocked)
        trader = InGameTrader(
            budget_coordinator=budget,
            data_connector=data_connector,
            executor=executor,
            cache=cache,
            dry_run=True,
            polymarket=polymarket,
        )

        # First tick: establish baseline
        trader.tick({1: gs_initial}, slug_table)

        # cache.get() should NOT have been called yet (baseline only)
        cache.get.assert_not_called()

        # Second tick: score changed -> should resolve market_tag and enter fast-path
        trader.tick({1: gs_changed}, slug_table)

        # cache.get() MUST have been called — proves market_tag was NOT None (lookup succeeded)
        cache.get.assert_called_with(1)

    def test_ingame_trader_market_lookup_fails_silently_with_wrong_key_type(
        self, monkeypatch
    ):
        """Regression guard: if slug_table were keyed by int (old bug), cache.get() would
        never be called because market_tag lookup would return None. This test documents the
        expected behavior with correct slug-keyed slug_table vs confirms the old int-key
        behavior was the bug.
        """
        import time

        from unittest.mock import MagicMock

        from agents.application.ingame_trader import InGameTrader
        from agents.utils.objects import SportsMarketTag, SportGameState

        monkeypatch.setenv("SPORTS_INGAME_COOLDOWN_SECONDS", "0")
        monkeypatch.setenv("SPORTS_INGAME_MIN_CONFIDENCE_GAP", "0.10")

        tag = SportsMarketTag(
            slug="nba-lal-bos",
            league="nba",
            home_team="LAL",
            away_team="BOS",
            market_id="9001",
            condition_id="0xabc123",
            token_id_yes="tok-yes",
            token_id_no="tok-no",
            question="Will the Lakers win?",
        )

        # Miskeyed slug_table (old int-key bug pattern)
        slug_table_broken = {1: [tag]}  # wrong: game_id int as key, not slug string

        gs_initial = SportGameState(
            game_id=1,
            league="nba",
            slug="nba-lal-bos",
            home_team="LAL",
            away_team="BOS",
            status="InProgress",
            score_raw="100-98",
            home_score=100,
            away_score=98,
            period="Q4",
            live=True,
            ended=False,
        )
        gs_changed = SportGameState(
            game_id=1,
            league="nba",
            slug="nba-lal-bos",
            home_team="LAL",
            away_team="BOS",
            status="InProgress",
            score_raw="102-98",
            home_score=102,
            away_score=98,
            period="Q4",
            live=True,
            ended=False,
        )

        cache = MagicMock()
        cache.get.return_value = {"llm_home_win_prob": 0.70, "timestamp": time.time()}

        trader = InGameTrader(
            budget_coordinator=MagicMock(can_spend_sports=MagicMock(return_value=True)),
            data_connector=MagicMock(),
            executor=MagicMock(),
            cache=cache,
            dry_run=True,
            polymarket=MagicMock(get_orderbook_price=MagicMock(return_value=0.50)),
        )

        trader.tick({1: gs_initial}, slug_table_broken)
        trader.tick({1: gs_changed}, slug_table_broken)

        # With wrong int key, slug_table.get(current.slug) returns None -> cache.get NOT called
        cache.get.assert_not_called()
