"""Unit tests for PolymarketEvent Pydantic model in agents/utils/objects.py.

Verifies that the PolymarketEvent model (which uses forward references via
`from __future__ import annotations`) parses correctly with markets=None
and with nested Market objects.
"""

from agents.utils.objects import Market, PolymarketEvent


class TestPolymarketEvent:
    def test_creates_with_markets_none(self):
        event = PolymarketEvent(id="12345")
        assert event.id == "12345"
        assert event.markets is None

    def test_creates_with_market_objects(self):
        market = Market(id=1)
        event = PolymarketEvent(id="12345", markets=[market])
        assert event.markets is not None
        assert len(event.markets) == 1
        assert event.markets[0].id == 1

    def test_markets_field_is_optional(self):
        event = PolymarketEvent(id="99")
        assert event.markets is None

    def test_creates_with_multiple_markets(self):
        markets = [Market(id=1), Market(id=2), Market(id=3)]
        event = PolymarketEvent(id="abc", title="Test Event", markets=markets)
        assert event.title == "Test Event"
        assert len(event.markets) == 3
        assert event.markets[2].id == 3

    def test_stale_todo_comment_is_removed(self):
        """Ensure the stale TODO comment no longer exists in objects.py source."""
        import os

        module_path = os.path.join(
            os.path.dirname(__file__), "..", "agents", "utils", "objects.py"
        )
        module_path = os.path.abspath(module_path)
        with open(module_path, "r") as f:
            source = f.read()
        assert (
            "TODO: double check this works as intended" not in source
        ), "Stale TODO comment should have been removed from objects.py"
