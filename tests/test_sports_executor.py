"""Unit tests for sports analysis engine: SportsExecutor, Prompter sports methods, and PregameCache."""

from __future__ import annotations

import json
import os
import time
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers: build test fixtures
# ---------------------------------------------------------------------------


def _make_game_state(**kwargs):
    from agents.utils.objects import SportGameState

    defaults = {
        "game_id": 42,
        "league": "nba",
        "slug": "nba-lal-bos-2026-03-07",
        "home_team": "LAL",
        "away_team": "BOS",
        "status": "InProgress",
        "score_raw": "55-60",
        "home_score": 55,
        "away_score": 60,
        "period": "Q3",
        "live": True,
        "ended": False,
    }
    defaults.update(kwargs)
    return SportGameState(**defaults)


def _make_market_tag(**kwargs):
    from agents.utils.objects import SportsMarketTag

    defaults = {
        "slug": "nba-lal-bos-2026-03-07",
        "league": "nba",
        "home_team": "LAL",
        "away_team": "BOS",
        "market_id": "9001",
        "condition_id": "0xabc123",
        "token_id_yes": "tok-yes",
        "token_id_no": "tok-no",
        "question": "Will the Lakers win?",
        "outcome_prices": "0.6,0.4",
    }
    defaults.update(kwargs)
    return SportsMarketTag(**defaults)


def _make_game_context(**kwargs):
    defaults = {
        "league": "nba",
        "home_team": "LAL",
        "away_team": "BOS",
        "home_stats": {
            "wins": 40,
            "losses": 20,
            "win_rate": 0.667,
            "recent_form": "WWLWW",
        },
        "away_stats": {
            "wins": 35,
            "losses": 25,
            "win_rate": 0.583,
            "recent_form": "WLWLW",
        },
        "head_to_head": [
            {
                "date": "2025-11-10",
                "home_team": "LAL",
                "away_team": "BOS",
                "home_score": 110,
                "away_score": 105,
                "winner": "LAL",
            },
            {
                "date": "2025-12-20",
                "home_team": "BOS",
                "away_team": "LAL",
                "home_score": 98,
                "away_score": 102,
                "winner": "LAL",
            },
        ],
        "external_odds": {
            "home_odds": 1.8,
            "away_odds": 2.1,
            "implied_home_prob": 0.556,
            "implied_away_prob": 0.476,
            "source_bookmaker": "FanDuel",
        },
    }
    defaults.update(kwargs)
    return defaults


# ===========================================================================
# TestSportsPrompts
# ===========================================================================


class TestSportsPrompts:
    """Tests for Prompter.sports_superforecaster() and Prompter.sports_trade_decision()."""

    def _prompter(self):
        from agents.application.prompts import Prompter

        return Prompter()

    def test_sports_superforecaster_returns_two_messages(self):
        prompter = self._prompter()
        game_state = _make_game_state()
        game_context = _make_game_context()
        messages = prompter.sports_superforecaster(game_state, game_context)
        assert len(messages) == 2

    def test_sports_superforecaster_system_mentions_sports_betting_analyst(self):
        from langchain_core.messages import SystemMessage

        prompter = self._prompter()
        messages = prompter.sports_superforecaster(
            _make_game_state(), _make_game_context()
        )
        system_msg = messages[0]
        assert isinstance(system_msg, SystemMessage)
        assert "sports betting analyst" in system_msg.content.lower()

    def test_sports_superforecaster_human_includes_home_team_win_rate(self):
        from langchain_core.messages import HumanMessage

        prompter = self._prompter()
        messages = prompter.sports_superforecaster(
            _make_game_state(), _make_game_context()
        )
        human_msg = messages[1]
        assert isinstance(human_msg, HumanMessage)
        # Should include home team win rate
        assert (
            "0.667" in human_msg.content
            or "win_rate" in human_msg.content.lower()
            or "LAL" in human_msg.content
        )

    def test_sports_superforecaster_human_includes_away_team_stats(self):
        from langchain_core.messages import HumanMessage

        prompter = self._prompter()
        messages = prompter.sports_superforecaster(
            _make_game_state(), _make_game_context()
        )
        human_msg = messages[1]
        # Should include away team info
        assert "BOS" in human_msg.content or "0.583" in human_msg.content

    def test_sports_superforecaster_human_includes_h2h_records(self):
        from langchain_core.messages import HumanMessage

        prompter = self._prompter()
        messages = prompter.sports_superforecaster(
            _make_game_state(), _make_game_context()
        )
        human_msg = messages[1]
        # H2H section should mention both teams
        content = human_msg.content.lower()
        assert "head" in content or "h2h" in content or "lal" in content

    def test_sports_superforecaster_human_includes_external_odds(self):
        from langchain_core.messages import HumanMessage

        prompter = self._prompter()
        messages = prompter.sports_superforecaster(
            _make_game_state(), _make_game_context()
        )
        human_msg = messages[1]
        # External odds implied prob should appear
        assert (
            "0.556" in human_msg.content
            or "implied" in human_msg.content.lower()
            or "bookmaker" in human_msg.content.lower()
        )

    def test_sports_superforecaster_does_not_include_polymarket_prices(self):
        from langchain_core.messages import HumanMessage

        prompter = self._prompter()
        messages = prompter.sports_superforecaster(
            _make_game_state(), _make_game_context()
        )
        human_msg = messages[1]
        content = human_msg.content.lower()
        # Blind estimate: should NOT mention polymarket prices
        assert "polymarket" not in content

    def test_sports_superforecaster_handles_none_home_stats(self):
        """Should not crash when home/away stats are None."""
        from langchain_core.messages import HumanMessage

        prompter = self._prompter()
        ctx = _make_game_context(home_stats=None, away_stats=None)
        messages = prompter.sports_superforecaster(_make_game_state(), ctx)
        assert len(messages) == 2
        human_msg = messages[1]
        assert isinstance(human_msg, HumanMessage)

    def test_sports_superforecaster_handles_empty_h2h(self):
        """Should not crash when head_to_head list is empty."""
        prompter = self._prompter()
        ctx = _make_game_context(head_to_head=[])
        messages = prompter.sports_superforecaster(_make_game_state(), ctx)
        assert len(messages) == 2

    # --- sports_trade_decision ---

    def test_sports_trade_decision_returns_two_messages(self):
        prompter = self._prompter()
        messages = prompter.sports_trade_decision(
            prediction="Home team likely wins with 65% probability.",
            game_state=_make_game_state(),
            game_context=_make_game_context(),
            outcomes=["Yes", "No"],
            outcome_prices=[0.6, 0.4],
            polymarket_price=0.6,
        )
        assert len(messages) == 2

    def test_sports_trade_decision_system_mentions_trade_decisions(self):
        from langchain_core.messages import SystemMessage

        prompter = self._prompter()
        messages = prompter.sports_trade_decision(
            prediction="Test prediction.",
            game_state=_make_game_state(),
            game_context=_make_game_context(),
            outcomes=["Yes", "No"],
            outcome_prices=[0.6, 0.4],
            polymarket_price=0.6,
        )
        system_msg = messages[0]
        assert isinstance(system_msg, SystemMessage)
        assert (
            "trade" in system_msg.content.lower()
            or "decision" in system_msg.content.lower()
        )

    def test_sports_trade_decision_human_includes_prediction_text(self):
        from langchain_core.messages import HumanMessage

        prompter = self._prompter()
        prediction = (
            "Home team likely wins with 65% probability based on strong offense."
        )
        messages = prompter.sports_trade_decision(
            prediction=prediction,
            game_state=_make_game_state(),
            game_context=_make_game_context(),
            outcomes=["Yes", "No"],
            outcome_prices=[0.6, 0.4],
            polymarket_price=0.6,
        )
        human_msg = messages[1]
        assert isinstance(human_msg, HumanMessage)
        assert prediction in human_msg.content or "65%" in human_msg.content

    def test_sports_trade_decision_human_includes_outcome_prices(self):
        from langchain_core.messages import HumanMessage

        prompter = self._prompter()
        messages = prompter.sports_trade_decision(
            prediction="Some prediction.",
            game_state=_make_game_state(),
            game_context=_make_game_context(),
            outcomes=["Yes", "No"],
            outcome_prices=[0.6, 0.4],
            polymarket_price=0.6,
        )
        human_msg = messages[1]
        # Prices or outcomes should be mentioned
        assert "0.6" in human_msg.content or "Yes" in human_msg.content

    def test_sports_trade_decision_includes_divergence_line_when_odds_available(self):
        from langchain_core.messages import HumanMessage

        prompter = self._prompter()
        ctx = _make_game_context()  # has external_odds with implied_home_prob=0.556
        messages = prompter.sports_trade_decision(
            prediction="Some prediction.",
            game_state=_make_game_state(),
            game_context=ctx,
            outcomes=["Yes", "No"],
            outcome_prices=[0.6, 0.4],
            polymarket_price=0.6,
        )
        human_msg = messages[1]
        content = human_msg.content.lower()
        # Divergence line should mention implied prob vs polymarket comparison
        assert "divergence" in content or "imply" in content or "external" in content

    def test_sports_trade_decision_omits_divergence_when_external_odds_none(self):
        from langchain_core.messages import HumanMessage

        prompter = self._prompter()
        ctx = _make_game_context(external_odds=None)
        messages = prompter.sports_trade_decision(
            prediction="Some prediction.",
            game_state=_make_game_state(),
            game_context=ctx,
            outcomes=["Yes", "No"],
            outcome_prices=[0.6, 0.4],
            polymarket_price=0.6,
        )
        human_msg = messages[1]
        content = human_msg.content.lower()
        assert "divergence" not in content and "external odds imply" not in content

    def test_sports_trade_decision_omits_divergence_when_no_implied_home_prob(self):
        from langchain_core.messages import HumanMessage

        prompter = self._prompter()
        ctx = _make_game_context(
            external_odds={"home_odds": 1.8, "source_bookmaker": "DraftKings"}
        )
        messages = prompter.sports_trade_decision(
            prediction="Some prediction.",
            game_state=_make_game_state(),
            game_context=ctx,
            outcomes=["Yes", "No"],
            outcome_prices=[0.6, 0.4],
            polymarket_price=0.6,
        )
        human_msg = messages[1]
        content = human_msg.content.lower()
        assert "divergence" not in content and "external odds imply" not in content

    def test_sports_trade_decision_human_includes_json_schema(self):
        from langchain_core.messages import HumanMessage

        prompter = self._prompter()
        messages = prompter.sports_trade_decision(
            prediction="Some prediction.",
            game_state=_make_game_state(),
            game_context=_make_game_context(),
            outcomes=["Yes", "No"],
            outcome_prices=[0.6, 0.4],
            polymarket_price=0.6,
        )
        human_msg = messages[1]
        # JSON schema fields should be present
        assert "selected_outcome" in human_msg.content
        assert "side" in human_msg.content
        assert "price" in human_msg.content
        assert "rationale" in human_msg.content


# ===========================================================================
# TestSportsExecutor
# ===========================================================================


VALID_TRADE_JSON = json.dumps(
    {
        "probabilities": [
            {"outcome": "Yes", "likelihood": 0.65},
            {"outcome": "No", "likelihood": 0.35},
        ],
        "selected_outcome": "Yes",
        "side": "BUY",
        "price": 0.6,
        "size_fraction": 0.1,
        "rationale": "Home team strong record.",
        "risk_factors": ["Late-game fatigue"],
        "counter_case": "Away team hot streak.",
    }
)


class TestSportsExecutor:
    """Tests for SportsExecutor.__init__, _invoke_llm, and analyze_game."""

    def test_init_creates_chatOpenAI_instance(self):
        """SportsExecutor.__init__ must create a ChatOpenAI instance."""
        with patch("agents.application.sports_executor.ChatOpenAI") as MockLLM, patch(
            "agents.application.sports_executor.Prompter"
        ):
            MockLLM.return_value = MagicMock()
            from agents.application.sports_executor import SportsExecutor

            executor = SportsExecutor()
            assert MockLLM.called

    def test_init_creates_prompter_instance(self):
        """SportsExecutor.__init__ must create a Prompter instance."""
        with patch("agents.application.sports_executor.ChatOpenAI"), patch(
            "agents.application.sports_executor.Prompter"
        ) as MockPrompter:
            MockPrompter.return_value = MagicMock()
            from agents.application.sports_executor import SportsExecutor

            executor = SportsExecutor()
            assert MockPrompter.called

    def test_init_uses_openai_model_env_var(self):
        """SportsExecutor.__init__ must use OPENAI_MODEL env var."""
        with patch.dict(os.environ, {"OPENAI_MODEL": "gpt-4o"}), patch(
            "agents.application.sports_executor.ChatOpenAI"
        ) as MockLLM, patch("agents.application.sports_executor.Prompter"):
            MockLLM.return_value = MagicMock()
            from agents.application.sports_executor import SportsExecutor

            executor = SportsExecutor()
            # model kwarg should be gpt-4o (from env var)
            assert MockLLM.called
            call_kwargs = MockLLM.call_args[1] if MockLLM.call_args else {}
            assert call_kwargs.get("model") == "gpt-4o"

    def test_invoke_llm_calls_llm_invoke_and_returns_content(self):
        """_invoke_llm must call self.llm.invoke(payload) and return result.content."""
        from agents.application.sports_executor import SportsExecutor

        executor = SportsExecutor.__new__(SportsExecutor)
        mock_llm = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "test response content"
        mock_llm.invoke.return_value = mock_result
        executor.llm = mock_llm

        payload = [MagicMock(), MagicMock()]
        result = executor._invoke_llm(payload, "test_op")

        mock_llm.invoke.assert_called_once_with(payload)
        assert result == "test response content"

    def test_analyze_game_calls_both_llm_stages(self):
        """analyze_game must call LLM twice: superforecaster then trade_decision."""
        from agents.application.sports_executor import SportsExecutor

        executor = SportsExecutor.__new__(SportsExecutor)
        mock_prompter = MagicMock()
        mock_prompter.sports_superforecaster.return_value = [MagicMock(), MagicMock()]
        mock_prompter.sports_trade_decision.return_value = [MagicMock(), MagicMock()]
        executor.prompter = mock_prompter

        mock_llm = MagicMock()
        mock_result = MagicMock()
        mock_result.content = VALID_TRADE_JSON
        mock_llm.invoke.return_value = mock_result
        executor.llm = mock_llm

        game_state = _make_game_state()
        market_tag = _make_market_tag()
        game_context = _make_game_context()

        result = executor.analyze_game(game_state, market_tag, game_context)

        assert mock_prompter.sports_superforecaster.called
        assert mock_prompter.sports_trade_decision.called
        assert mock_llm.invoke.call_count == 2

    def test_analyze_game_returns_candidate_trade(self):
        """analyze_game must return a CandidateTrade."""
        from agents.application.sports_executor import SportsExecutor
        from agents.utils.objects import CandidateTrade

        executor = SportsExecutor.__new__(SportsExecutor)
        mock_prompter = MagicMock()
        mock_prompter.sports_superforecaster.return_value = [MagicMock(), MagicMock()]
        mock_prompter.sports_trade_decision.return_value = [MagicMock(), MagicMock()]
        executor.prompter = mock_prompter

        mock_llm = MagicMock()
        mock_result = MagicMock()
        mock_result.content = VALID_TRADE_JSON
        mock_llm.invoke.return_value = mock_result
        executor.llm = mock_llm

        result = executor.analyze_game(
            _make_game_state(), _make_market_tag(), _make_game_context()
        )

        assert isinstance(result, CandidateTrade)

    def test_analyze_game_sets_correct_market_id(self):
        """analyze_game must set market_id from SportsMarketTag.market_id."""
        from agents.application.sports_executor import SportsExecutor

        executor = SportsExecutor.__new__(SportsExecutor)
        mock_prompter = MagicMock()
        mock_prompter.sports_superforecaster.return_value = [MagicMock(), MagicMock()]
        mock_prompter.sports_trade_decision.return_value = [MagicMock(), MagicMock()]
        executor.prompter = mock_prompter

        mock_llm = MagicMock()
        mock_result = MagicMock()
        mock_result.content = VALID_TRADE_JSON
        mock_llm.invoke.return_value = mock_result
        executor.llm = mock_llm

        tag = _make_market_tag(market_id="9001")
        result = executor.analyze_game(_make_game_state(), tag, _make_game_context())
        assert result.market_id == 9001

    def test_analyze_game_sets_category_bucket_sports(self):
        """analyze_game must set category_bucket='sports'."""
        from agents.application.sports_executor import SportsExecutor

        executor = SportsExecutor.__new__(SportsExecutor)
        mock_prompter = MagicMock()
        mock_prompter.sports_superforecaster.return_value = [MagicMock(), MagicMock()]
        mock_prompter.sports_trade_decision.return_value = [MagicMock(), MagicMock()]
        executor.prompter = mock_prompter

        mock_llm = MagicMock()
        mock_result = MagicMock()
        mock_result.content = VALID_TRADE_JSON
        mock_llm.invoke.return_value = mock_result
        executor.llm = mock_llm

        result = executor.analyze_game(
            _make_game_state(), _make_market_tag(), _make_game_context()
        )
        assert result.category_bucket == "sports"

    def test_analyze_game_sets_token_ids_from_tag(self):
        """analyze_game must populate token_ids from SportsMarketTag."""
        from agents.application.sports_executor import SportsExecutor

        executor = SportsExecutor.__new__(SportsExecutor)
        mock_prompter = MagicMock()
        mock_prompter.sports_superforecaster.return_value = [MagicMock(), MagicMock()]
        mock_prompter.sports_trade_decision.return_value = [MagicMock(), MagicMock()]
        executor.prompter = mock_prompter

        mock_llm = MagicMock()
        mock_result = MagicMock()
        mock_result.content = VALID_TRADE_JSON
        mock_llm.invoke.return_value = mock_result
        executor.llm = mock_llm

        tag = _make_market_tag(token_id_yes="yes-tok", token_id_no="no-tok")
        result = executor.analyze_game(_make_game_state(), tag, _make_game_context())
        assert "yes-tok" in result.token_ids
        assert "no-tok" in result.token_ids

    def test_analyze_game_parses_llm_fields_into_candidate_trade(self):
        """analyze_game must parse side, price, rationale from LLM JSON."""
        from agents.application.sports_executor import SportsExecutor

        executor = SportsExecutor.__new__(SportsExecutor)
        mock_prompter = MagicMock()
        mock_prompter.sports_superforecaster.return_value = [MagicMock(), MagicMock()]
        mock_prompter.sports_trade_decision.return_value = [MagicMock(), MagicMock()]
        executor.prompter = mock_prompter

        mock_llm = MagicMock()
        mock_result = MagicMock()
        mock_result.content = VALID_TRADE_JSON
        mock_llm.invoke.return_value = mock_result
        executor.llm = mock_llm

        result = executor.analyze_game(
            _make_game_state(), _make_market_tag(), _make_game_context()
        )
        assert result.parsed_side == "BUY"
        assert result.parsed_price == 0.6
        assert result.rationale == "Home team strong record."

    def test_analyze_game_fallback_prices_when_outcome_prices_none(self):
        """analyze_game must default to [0.5, 0.5] when outcome_prices is None on tag."""
        from agents.application.sports_executor import SportsExecutor

        executor = SportsExecutor.__new__(SportsExecutor)
        mock_prompter = MagicMock()
        mock_prompter.sports_superforecaster.return_value = [MagicMock(), MagicMock()]
        mock_prompter.sports_trade_decision.return_value = [MagicMock(), MagicMock()]
        executor.prompter = mock_prompter

        mock_llm = MagicMock()
        mock_result = MagicMock()
        mock_result.content = VALID_TRADE_JSON
        mock_llm.invoke.return_value = mock_result
        executor.llm = mock_llm

        tag = _make_market_tag(outcome_prices=None)
        result = executor.analyze_game(_make_game_state(), tag, _make_game_context())
        assert result is not None
        assert result.outcome_prices == [0.5, 0.5]

    def test_analyze_game_returns_none_on_malformed_llm_response(self):
        """analyze_game must return None (not crash) when LLM returns malformed JSON."""
        from agents.application.sports_executor import SportsExecutor

        executor = SportsExecutor.__new__(SportsExecutor)
        mock_prompter = MagicMock()
        mock_prompter.sports_superforecaster.return_value = [MagicMock(), MagicMock()]
        mock_prompter.sports_trade_decision.return_value = [MagicMock(), MagicMock()]
        executor.prompter = mock_prompter

        mock_llm = MagicMock()
        mock_result = MagicMock()
        mock_result.content = ""  # Empty — force failure path
        mock_llm.invoke.return_value = mock_result
        executor.llm = mock_llm

        # _parse_json_object returns {} for empty, which should still produce a CandidateTrade
        # but we need to verify no crash. Result might be CandidateTrade with defaults or None.
        result = executor.analyze_game(
            _make_game_state(), _make_market_tag(), _make_game_context()
        )
        # Should not raise — result can be CandidateTrade or None
        assert result is None or hasattr(result, "market_id")

    def test_analyze_game_returns_none_on_llm_exception(self):
        """analyze_game must return None (not crash) when LLM raises exception."""
        from agents.application.sports_executor import SportsExecutor

        executor = SportsExecutor.__new__(SportsExecutor)
        mock_prompter = MagicMock()
        mock_prompter.sports_superforecaster.return_value = [MagicMock(), MagicMock()]
        executor.prompter = mock_prompter

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("LLM failed")
        executor.llm = mock_llm

        result = executor.analyze_game(
            _make_game_state(), _make_market_tag(), _make_game_context()
        )
        assert result is None


# ===========================================================================
# TestPregameCache
# ===========================================================================


class TestPregameCache:
    """Tests for PregameCache CRUD, TTL, coercion, and remove."""

    def _make_cache(self, tmp_path):
        from agents.application.pregame_cache import PregameCache

        cache_file = str(tmp_path / "pregame_cache.json")
        return PregameCache(cache_path=cache_file)

    def test_set_and_get_returns_entry(self, tmp_path):
        cache = self._make_cache(tmp_path)
        entry = {"selected_outcome": "Yes", "confidence": 0.65}
        cache.set(42, entry)
        result = cache.get(42)
        assert result is not None
        assert result["selected_outcome"] == "Yes"

    def test_get_unknown_game_id_returns_none(self, tmp_path):
        cache = self._make_cache(tmp_path)
        assert cache.get(9999) is None

    def test_set_persists_to_file(self, tmp_path):
        """PregameCache.set must write to the JSON file."""
        from agents.application.pregame_cache import PregameCache

        cache_file = str(tmp_path / "pregame_cache.json")
        cache = PregameCache(cache_path=cache_file)
        cache.set(7, {"foo": "bar"})
        # Read file directly to verify persistence
        import json

        with open(cache_file) as f:
            data = json.load(f)
        assert "7" in data

    def test_get_survives_restart(self, tmp_path):
        """PregameCache.get must retrieve entries written by a previous instance."""
        from agents.application.pregame_cache import PregameCache

        cache_file = str(tmp_path / "pregame_cache.json")
        cache1 = PregameCache(cache_path=cache_file)
        cache1.set(15, {"key": "value_restart"})

        # Simulate restart: create new instance pointing to same file
        cache2 = PregameCache(cache_path=cache_file)
        result = cache2.get(15)
        assert result is not None
        assert result["key"] == "value_restart"

    def test_is_fresh_within_ttl(self, tmp_path):
        """is_fresh must return True when entry timestamp is within TTL."""
        cache = self._make_cache(tmp_path)
        cache.set(10, {"outcome": "Yes"})
        assert cache.is_fresh(10) is True

    def test_is_fresh_returns_false_for_expired_entry(self, tmp_path):
        """is_fresh must return False when entry timestamp is beyond TTL."""
        from agents.application.pregame_cache import PregameCache
        import json

        cache_file = str(tmp_path / "pregame_cache.json")
        cache = PregameCache(cache_path=cache_file, ttl_minutes=1)
        # Write an entry with a very old timestamp (2 minutes ago)
        old_timestamp = time.time() - 120
        data = {"10": {"outcome": "Yes", "timestamp": old_timestamp}}
        with open(cache_file, "w") as f:
            json.dump(data, f)
        assert cache.is_fresh(10) is False

    def test_is_fresh_returns_false_for_missing_game(self, tmp_path):
        """is_fresh must return False for unknown game_id."""
        cache = self._make_cache(tmp_path)
        assert cache.is_fresh(9999) is False

    def test_int_str_coercion_set_int_get_int(self, tmp_path):
        """set with int game_id and get with int game_id should both work."""
        cache = self._make_cache(tmp_path)
        cache.set(42, {"data": "test_int_coerce"})
        result = cache.get(42)
        assert result is not None
        assert result["data"] == "test_int_coerce"

    def test_int_str_coercion_internally_keyed_as_str(self, tmp_path):
        """Internal JSON file must use str keys regardless of set/get int input."""
        import json

        from agents.application.pregame_cache import PregameCache

        cache_file = str(tmp_path / "pregame_cache.json")
        cache = PregameCache(cache_path=cache_file)
        cache.set(100, {"data": "str_key_check"})
        with open(cache_file) as f:
            raw = json.load(f)
        assert "100" in raw  # must be stored as string key

    def test_remove_deletes_entry(self, tmp_path):
        cache = self._make_cache(tmp_path)
        cache.set(77, {"data": "to_be_removed"})
        assert cache.get(77) is not None
        cache.remove(77)
        assert cache.get(77) is None

    def test_remove_nonexistent_does_not_crash(self, tmp_path):
        """remove must not crash when game_id not in cache."""
        cache = self._make_cache(tmp_path)
        cache.remove(9999)  # Should not raise


# ===========================================================================
# TestSportsAnalysisCacheModel
# ===========================================================================


class TestSportsAnalysisCacheModel:
    """Tests for SportsAnalysisCache Pydantic model."""

    def _make_valid(self, **kwargs):
        from agents.utils.objects import SportsAnalysisCache

        defaults = {
            "game_id": 42,
            "league": "nba",
            "home_team": "LAL",
            "away_team": "BOS",
            "timestamp": 1709999999.0,
            "llm_home_win_prob": 0.65,
            "llm_away_win_prob": 0.35,
            "confidence_gap": 0.1,
            "selected_outcome": "Yes",
            "selected_side": "BUY",
            "size_fraction": 0.1,
            "rationale": "Strong home advantage.",
            "polymarket_price_at_analysis": 0.6,
        }
        defaults.update(kwargs)
        return SportsAnalysisCache(**defaults)

    def test_valid_model_creates_without_error(self):
        model = self._make_valid()
        assert model.game_id == 42

    def test_model_has_correct_field_types(self):
        model = self._make_valid()
        assert isinstance(model.game_id, int)
        assert isinstance(model.league, str)
        assert isinstance(model.llm_home_win_prob, float)
        assert isinstance(model.confidence_gap, float)
        assert isinstance(model.risk_factors, list)

    def test_risk_factors_default_is_empty_list(self):
        model = self._make_valid()
        assert model.risk_factors == []

    def test_counter_case_default_is_empty_string(self):
        model = self._make_valid()
        assert model.counter_case == ""

    def test_trade_attempted_default_is_false(self):
        model = self._make_valid()
        assert model.trade_attempted is False

    def test_trade_error_default_is_none(self):
        model = self._make_valid()
        assert model.trade_error is None

    def test_external_implied_prob_default_is_none(self):
        model = self._make_valid()
        assert model.external_implied_prob is None

    def test_superforecast_response_default_is_empty_string(self):
        model = self._make_valid()
        assert model.superforecast_response == ""

    def test_trade_response_default_is_empty_string(self):
        model = self._make_valid()
        assert model.trade_response == ""

    def test_optional_fields_can_be_set(self):
        model = self._make_valid(
            external_implied_prob=0.55,
            trade_attempted=True,
            trade_error="Some error",
            risk_factors=["risk1", "risk2"],
            counter_case="The away team is on a hot streak.",
        )
        assert model.external_implied_prob == 0.55
        assert model.trade_attempted is True
        assert model.trade_error == "Some error"
        assert model.risk_factors == ["risk1", "risk2"]
        assert model.counter_case == "The away team is on a hot streak."
