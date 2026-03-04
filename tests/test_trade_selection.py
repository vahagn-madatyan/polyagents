import unittest

from agents.application.executor import (
    Executor,
    allocate_confidence_weighted,
    canonicalize_category,
    select_soft_quota_candidates,
)
from agents.utils.objects import CandidateTrade, SimpleEvent


def _candidate(market_id: int, category: str, gap: float) -> CandidateTrade:
    return CandidateTrade(
        market_id=market_id,
        question=f"Market {market_id}",
        category_bucket=category,
        outcomes=["Yes", "No"],
        outcome_prices=[0.5, 0.5],
        token_ids=[str(market_id * 2), str(market_id * 2 + 1)],
        probabilities=[
            {"outcome": "Yes", "likelihood": 0.5 + gap / 2.0},
            {"outcome": "No", "likelihood": 0.5 - gap / 2.0},
        ],
        suggested_outcome="Yes",
        parsed_side="BUY",
        confidence_gap=gap,
        rag_score=float(market_id),
    )


class TestTradeSelection(unittest.TestCase):
    def test_category_canonicalization_precedence(self) -> None:
        self.assertEqual(canonicalize_category("Politics", "", "", ""), "politics")
        self.assertEqual(canonicalize_category("", "nba,playoffs", "", ""), "sports")
        self.assertEqual(
            canonicalize_category("", "", "Will Ethereum hit 5k?", "crypto market"),
            "crypto",
        )
        self.assertEqual(
            canonicalize_category("", "", "Will it rain?", "weather"), "other"
        )

    def test_soft_quota_selects_diverse_categories_when_available(self) -> None:
        candidates = [
            _candidate(1, "crypto", 0.30),
            _candidate(2, "crypto", 0.25),
            _candidate(3, "sports", 0.20),
            _candidate(4, "politics", 0.18),
            _candidate(5, "other", 0.15),
        ]

        selected = select_soft_quota_candidates(
            candidates, target_count=5, min_categories=3
        )

        self.assertEqual(len(selected), 5)
        self.assertEqual(
            len({candidate.category_bucket for candidate in selected[:3]}), 3
        )

    def test_soft_quota_degrades_gracefully_with_limited_categories(self) -> None:
        candidates = [
            _candidate(idx, "crypto", 0.2 - idx * 0.01) for idx in range(1, 5)
        ]

        selected = select_soft_quota_candidates(
            candidates, target_count=5, min_categories=3
        )

        self.assertEqual(len(selected), 4)
        self.assertEqual(
            {candidate.category_bucket for candidate in selected}, {"crypto"}
        )

    def test_confidence_weighted_allocator_respects_budget_and_caps(self) -> None:
        candidates = [
            _candidate(1, "crypto", 0.30),
            _candidate(2, "sports", 0.22),
            _candidate(3, "politics", 0.18),
            _candidate(4, "other", 0.14),
            _candidate(5, "crypto", 0.10),
        ]

        allocated = allocate_confidence_weighted(
            candidates=candidates,
            usdc_balance=1000.0,
            total_budget_fraction=0.30,
            min_per_market_fraction=0.02,
            max_per_market_fraction=0.10,
        )

        total = sum(candidate.allocation_amount_usdc for candidate in allocated)
        self.assertAlmostEqual(total, 300.0, places=6)
        for candidate in allocated:
            self.assertGreaterEqual(candidate.allocation_amount_usdc, 20.0)
            self.assertLessEqual(candidate.allocation_amount_usdc, 100.0)

    def test_confidence_weighted_allocator_handles_zero_gaps(self) -> None:
        candidates = [_candidate(idx, "other", 0.0) for idx in range(1, 6)]

        allocated = allocate_confidence_weighted(
            candidates=candidates,
            usdc_balance=1000.0,
            total_budget_fraction=0.30,
            min_per_market_fraction=0.02,
            max_per_market_fraction=0.10,
        )

        expected = 60.0
        for candidate in allocated:
            self.assertAlmostEqual(candidate.allocation_amount_usdc, expected, places=6)

    def test_trade_parser_json_and_fallback_paths(self) -> None:
        executor = Executor.__new__(Executor)

        json_trade = (
            '{"probabilities":[{"outcome":"Yes","likelihood":0.62},'
            '{"outcome":"No","likelihood":0.38}],"selected_outcome":"Yes",'
            '"side":"BUY","price":0.61,"size_fraction":0.05,'
            '"rationale":"Momentum favors Yes.",'
            '"risk_factors":["headline shock"],"counter_case":"Volatility spikes."}'
        )

        parsed_json = executor._parse_trade_decision(
            superforecast_content="",
            trade_content=json_trade,
            outcomes=["Yes", "No"],
            outcome_prices=[0.50, 0.50],
        )

        self.assertEqual(parsed_json["selected_outcome"], "Yes")
        self.assertEqual(parsed_json["parsed_side"], "BUY")
        self.assertAlmostEqual(parsed_json["parsed_price"], 0.61, places=9)
        self.assertEqual(parsed_json["risk_factors"], ["headline shock"])

        malformed_trade = "price:0.54, size:0.07, side:BUY"
        superforecast = (
            "I believe Test has a likelihood `0.54` for outcome of `Yes`. "
            "I believe Test has a likelihood `0.46` for outcome of `No`."
        )

        parsed_fallback = executor._parse_trade_decision(
            superforecast_content=superforecast,
            trade_content=malformed_trade,
            outcomes=["Yes", "No"],
            outcome_prices=[0.54, 0.46],
        )

        self.assertEqual(parsed_fallback["selected_outcome"], "Yes")
        self.assertEqual(parsed_fallback["parsed_side"], "BUY")
        self.assertAlmostEqual(parsed_fallback["parsed_price"], 0.54, places=9)
        self.assertEqual(len(parsed_fallback["probabilities"]), 2)

    def test_map_filtered_events_to_markets_supports_simple_event_entries(self) -> None:
        class DummyLogger:
            def info(self, *args, **kwargs) -> None:
                return None

        class DummyGamma:
            market_fetch_concurrency = 4

            def __init__(self) -> None:
                self.requested_market_ids = []

            def get_markets_by_ids(self, market_ids):
                self.requested_market_ids = list(market_ids)
                return [{"id": "111"}, {"id": "222"}]

        class DummyMapper:
            def map_api_to_market(self, market_data):
                return {
                    "id": int(market_data["id"]),
                    "question": f"Question {market_data['id']}",
                    "end": "",
                    "description": "Description",
                    "active": True,
                    "funded": True,
                    "rewardsMinSize": 0.0,
                    "rewardsMaxSpread": 0.0,
                    "volume": 100000.0,
                    "volume24hr": 50000.0,
                    "volume_clob": 100000.0,
                    "volume24hr_clob": 50000.0,
                    "liquidity": 90000.0,
                    "liquidity_clob": 90000.0,
                    "spread": 0.01,
                    "outcomes": "['Yes','No']",
                    "outcome_prices": "[0.55,0.45]",
                    "clob_token_ids": "['1','2']",
                    "category": "sports",
                    "tags": "premier league",
                    "event_id": "10",
                    "event_title": "Premier League Winner",
                    "event_slug": "english-premier-league-winner",
                }

        executor = Executor.__new__(Executor)
        executor.logger = DummyLogger()
        executor.gamma = DummyGamma()
        executor.polymarket_mapper = DummyMapper()
        executor._passes_market_quality_filters = lambda market_payload: True

        event = SimpleEvent(
            id=10,
            ticker="",
            slug="english-premier-league-winner",
            title="Premier League Winner",
            description="",
            end="",
            active=True,
            closed=False,
            archived=False,
            restricted=False,
            new=False,
            featured=False,
            markets="111,222",
        )

        mapped_markets = executor.map_filtered_events_to_markets([event])

        self.assertEqual(executor.gamma.requested_market_ids, ["111", "222"])
        self.assertEqual(len(mapped_markets), 2)
        self.assertEqual(mapped_markets[0]["id"], 111)
        self.assertEqual(mapped_markets[1]["id"], 222)

    def test_build_trade_candidates_passes_supplemental_context_by_market_id(
        self,
    ) -> None:
        class DummyLogger:
            def info(self, *args, **kwargs) -> None:
                return None

            def warning(self, *args, **kwargs) -> None:
                return None

        class DummyMarketDoc:
            metadata = {"id": "321", "question": "Will Team A win?"}

        captured_context = {"value": ""}
        market_obj = (DummyMarketDoc(), 0.01)

        executor = Executor.__new__(Executor)
        executor.logger = DummyLogger()
        executor._dedupe_market_docs = lambda markets: [market_obj]

        def fake_source_best_trade(market_object, supplemental_context=""):
            captured_context["value"] = supplemental_context
            return _candidate(321, "sports", 0.24)

        executor.source_best_trade = fake_source_best_trade
        executor._candidate_has_tradeable_entry_price = lambda candidate: True
        executor.select_trade_candidates = lambda candidates: candidates

        payload = executor.build_trade_candidates(
            [market_obj],
            supplemental_context_by_market_id={321: "Market-specific news context"},
        )

        self.assertEqual(captured_context["value"], "Market-specific news context")
        self.assertEqual(len(payload["selected_candidates"]), 1)
        self.assertEqual(payload["selected_candidates"][0].market_id, 321)


if __name__ == "__main__":
    unittest.main()
