# Testing Patterns

**Analysis Date:** 2026-03-03

## Test Framework

**Runner:**
- pytest (v8.3.2) - primary test framework
- unittest - secondary, used in some test files for traditional unittest.TestCase structure
- Config: No pytest.ini or pyproject.toml configuration file detected
- Pytest runs with default discovery and configuration

**Assertion Library:**
- `unittest.TestCase` assertion methods: `assertEqual()`, `assertTrue()`, `assertFalse()`, `assertGreaterEqual()`, etc.
- `pytest` assertions: `assert` statements (pytest style)

**Run Commands:**
```bash
python -m pytest tests/
python -m pytest tests/ -v
python -m pytest tests/ --tb=short
python -m unittest discover tests/
python tests/test_file.py
```

## Test File Organization

**Location:**
- Co-located in `tests/` directory separate from source code
- Tests grouped by functionality, not mirroring source structure
- Files: `tests/test_trade_selection.py`, `tests/test_news_connector.py`, `tests/test_event_url_trader.py`, `tests/test.py`

**Naming:**
- Files: `test_*.py` pattern
- Classes: `TestXxx` pattern for unittest.TestCase subclasses, or no class for pytest functions
- Functions: `test_` prefix

**Structure:**
```
tests/
├── test_trade_selection.py       # Executor-related trade selection tests
├── test_news_connector.py        # News API integration tests
├── test_event_url_trader.py      # Trader URL parsing and event resolution tests
└── test.py                       # Basic sanity tests
```

## Test Structure - unittest Pattern

**Suite Organization (from `test_trade_selection.py`):**
```python
import unittest
from agents.application.executor import (
    Executor,
    allocate_confidence_weighted,
    canonicalize_category,
    select_soft_quota_candidates,
)
from agents.utils.objects import CandidateTrade, SimpleEvent

class TestTradeSelection(unittest.TestCase):
    def test_category_canonicalization_precedence(self) -> None:
        self.assertEqual(canonicalize_category("Politics", "", "", ""), "politics")
        # ...

if __name__ == "__main__":
    unittest.main()
```

**Patterns:**
- Setup: Implicit initialization in test methods, no setUp/tearDown used
- Assertions: `self.assertEqual()`, `self.assertAlmostEqual()`, `self.assertGreaterEqual()`
- Cleanup: No explicit teardown observed; tests are stateless

## Test Structure - pytest Pattern

**Suite Organization (from `test_news_connector.py`):**
```python
from unittest.mock import MagicMock
from agents.connectors.news import News

def _article(url: str, title: str, published_at: str) -> dict:
    """Helper to create test article data"""
    return {...}

def test_top_headlines_hit_skips_fallback() -> None:
    news, api_mock = _news_with_mocked_api()
    api_mock.get_top_headlines.return_value = {"articles": [...]}

    articles, used_fallback = news.get_articles_for_cli_keywords("iran")

    assert used_fallback is False
    assert len(articles) == 2
```

**Patterns:**
- Plain functions with `test_` prefix (no test class needed)
- Helper functions prefixed with underscore: `_article()`, `_news_with_mocked_api()`, `_candidate()`
- Direct `assert` statements for assertions
- Fixture-like helpers return test doubles (mocks, stubs)

## Mocking

**Framework:** `unittest.mock` module

**Patterns from `test_event_url_trader.py`:**
```python
# Create class without __init__ to bypass initialization
trader = Trader.__new__(Trader)

# Stub classes for dependencies
class GammaStub:
    def get_events(self, querystring_params=None):
        return [...]
    def get_all_events(self):
        return [...]

class PolyStub:
    def map_api_to_event(self, event):
        return {...}

# Inject stubs as attributes
trader.gamma = GammaStub()
trader.polymarket = PolyStub()
```

**Patterns from `test_trade_selection.py`:**
```python
class DummyLogger:
    def info(self, *args, **kwargs) -> None:
        return None

class DummyGamma:
    market_fetch_concurrency = 4
    def __init__(self) -> None:
        self.requested_market_ids = []
    def get_markets_by_ids(self, market_ids):
        self.requested_market_ids = list(market_ids)
        return [...]

# Set on executor instance
executor = Executor.__new__(Executor)
executor.logger = DummyLogger()
executor.gamma = DummyGamma()
```

**Patterns from `test_news_connector.py`:**
```python
from unittest.mock import MagicMock

def _news_with_mocked_api() -> tuple[News, MagicMock]:
    news = News()
    api_mock = MagicMock()
    news.API = api_mock
    return news, api_mock

# Use MagicMock for external APIs
api_mock.get_top_headlines.return_value = {"articles": [...]}
api_mock.get_everything.side_effect = [...]

# Verify calls
api_mock.get_everything.assert_not_called()
assert api_mock.get_everything.call_args.kwargs["sort_by"] == "relevancy"
```

**What to Mock:**
- External API clients (NewsApiClient via MagicMock)
- Dependency classes that would require complex initialization
- Heavy dependencies (Gamma API client, Polymarket client)
- Database or file system operations

**What NOT to Mock:**
- Pydantic models and data objects (CandidateTrade, SimpleEvent)
- Pure utility functions
- Logic you want to test end-to-end
- Small helper stubs can be created for specific test scenarios

## Fixtures and Factories

**Test Data - Helper Functions:**
```python
def _candidate(market_id: int, category: str, gap: float) -> CandidateTrade:
    """Factory for creating test CandidateTrade instances"""
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
```

**Test Data - Inline Dictionaries:**
```python
def _article(url: str, title: str, published_at: str) -> dict:
    return {
        "source": {"id": None, "name": "Example"},
        "author": "Reporter",
        "title": title,
        "description": f"{title} description",
        "url": url,
        "urlToImage": None,
        "publishedAt": published_at,
        "content": f"{title} content",
    }
```

**Location:**
- Helper functions defined within test modules, not in separate fixtures module
- Prefixed with underscore to indicate they're test utilities
- Can be reused across multiple test functions in same file

## Coverage

**Requirements:** Not enforced (no coverage config file detected)

**View Coverage:**
```bash
python -m pytest tests/ --cov=agents --cov-report=html
python -m pytest tests/ --cov=agents --cov-report=term-missing
```

## Test Types

**Unit Tests:**
- Scope: Individual functions and methods in isolation
- Approach: Mock all external dependencies (APIs, files, complex objects)
- Examples: `test_category_canonicalization_precedence()`, `test_confidence_weighted_allocator_*()` in `test_trade_selection.py`
- Most tests follow this pattern

**Integration Tests:**
- Scope: Multiple components working together
- Approach: Mock external systems (APIs) but test actual code integration
- Examples: `test_build_trade_candidates_passes_supplemental_context_by_market_id()` (tests Executor with stubs)
- `test_relevance_mode_filters_and_ranks_by_body_matches()` (tests News with mocked API)

**E2E Tests:**
- Framework: Not implemented (no end-to-end test framework detected)
- Would require: Real API keys, real blockchain, real trading infrastructure
- Approach: Manual testing or staging environment validation

## Common Patterns

**Parameterized Testing:**
```python
@pytest.mark.parametrize(
    "event_url,expected_slug",
    [
        ("https://polymarket.com/event/english-premier-league-winner", "english-premier-league-winner"),
        ("https://polymarket.com/event/english-premier-league-winner?tid=123", "english-premier-league-winner"),
        ("english-premier-league-winner", "english-premier-league-winner"),
    ],
)
def test_extract_event_slug_from_url_success(event_url: str, expected_slug: str) -> None:
    trader = _trader_without_init()
    assert trader._extract_event_slug_from_url(event_url) == expected_slug
```

**Exception Testing:**
```python
def test_extract_event_slug_from_url_invalid_raises() -> None:
    trader = _trader_without_init()
    with pytest.raises(ValueError):
        trader._extract_event_slug_from_url("https://polymarket.com/markets")
```

**Asserting Function Calls on Mocks:**
```python
# Verify exact call arguments
for call in api_mock.get_everything.call_args_list:
    assert call.kwargs["language"] == "en"
    assert "country" not in call.kwargs
    assert call.kwargs["sort_by"] == "publishedAt"

# Verify not called
api_mock.get_top_headlines.assert_not_called()

# Access last call
kwargs = api_mock.get_everything.call_args.kwargs
```

**Testing with Side Effects:**
```python
# Sequential return values for repeated calls
api_mock.get_top_headlines.side_effect = [{"articles": []}, {"articles": []}]

# Exception on call
class DummyMapper:
    def map_api_to_market(self, market_data):
        raise AssertionError("method should not be called")
```

**Testing State Changes:**
```python
def test_apply_minimum_order_constraints_reallocates_after_pruning() -> None:
    # ... setup candidates ...

    adjusted = trader._apply_minimum_order_constraints(candidates, usdc_balance=10.0)

    # Verify modified state
    executable = [c for c in adjusted if c.execution_status != "SKIPPED_BELOW_MIN_ORDER"]
    skipped = [c for c in adjusted if c.execution_status == "SKIPPED_BELOW_MIN_ORDER"]

    assert len(executable) == 3
    assert len(skipped) == 2
    for candidate in executable:
        assert candidate.allocation_amount_usdc >= 1.0
```

**Creating Objects Without Initialization:**
```python
# Bypass __init__ to inject mocks for dependencies
executor = Executor.__new__(Executor)
executor.logger = DummyLogger()
executor.gamma = DummyGamma()
executor.polymarket_mapper = DummyMapper()
executor._passes_market_quality_filters = lambda market_payload: True
```

## Assertion Patterns

**Numeric Comparisons:**
```python
# Approximate float equality (within 6 decimal places)
self.assertAlmostEqual(total, 300.0, places=6)

# Range assertions
self.assertGreaterEqual(candidate.allocation_amount_usdc, 20.0)
self.assertLessEqual(candidate.allocation_amount_usdc, 100.0)
```

**Collection Assertions:**
```python
# Length and membership
self.assertEqual(len(selected), 5)
self.assertEqual({candidate.category_bucket for candidate in selected}, {"crypto"})

# Ordering
assert [a.url for a in articles] == ["https://example.com/two", "https://example.com/one"]
```

**Boolean Assertions:**
```python
assert used_fallback is False
assert used_fallback is True
self.assertTrue("FOO".isupper())
self.assertFalse("Foo".isupper())
```

---

*Testing analysis: 2026-03-03*
