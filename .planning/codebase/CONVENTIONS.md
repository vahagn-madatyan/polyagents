# Coding Conventions

**Analysis Date:** 2026-03-03

## Naming Patterns

**Files:**
- Lowercase with underscores: `news.py`, `executor.py`, `polymarket.py`
- Classes grouped in modules by functional domain: `agents/connectors/`, `agents/polymarket/`, `agents/application/`
- Test files prefixed with `test_`: `test_trade_selection.py`, `test_news_connector.py`

**Classes:**
- PascalCase: `Trader`, `Executor`, `PolymarketEvent`, `SimpleMarket`, `CandidateTrade`
- Descriptive names indicating purpose: `Prompter`, `GammaMarketClient`, `PolymarketRAG`
- Private/internal marker with underscore prefix: methods like `_truncate()`, `_format_probabilities()`, `_resolve_event_by_slug()`

**Functions/Methods:**
- snake_case: `parse_camel_case()`, `get_articles_for_cli_keywords()`, `map_filtered_events_to_markets()`
- Prefixed with underscore for private/internal methods: `_apply_minimum_order_constraints()`, `_extract_event_slug_from_url()`
- Action verbs for clarity: `get_`, `build_`, `filter_`, `extract_`, `resolve_`, `apply_`, `execute_`

**Variables:**
- snake_case: `event_slug`, `market_id`, `usdc_balance`, `confidence_gap`, `filtered_markets`
- Type-specific suffixes when helpful: `_count`, `_amount`, `_usdc`, `_response`, `_by_market_id` (for dicts)
- Temporary/working variables: `working`, `used_fallback`, `captured_context`

**Constants:**
- UPPER_CASE: `UPPER`, `LOWER` (example from parse_camel_case utility)
- Often defined in environment or configuration sections

**Types:**
- Use PascalCase for data models: `SimpleMarket`, `CandidateTrade`, `SimpleEvent`, `Article`
- Type hints use `typing` module: `List[str]`, `Dict[str, int]`, `Optional[bool]`

## Code Style

**Formatting:**
- Tool: Black (v24.4.2)
- Line length: 88 characters (Black default)
- Configuration: `.pre-commit-config.yaml` with Black hook
- Run with: `black` via pre-commit

**Linting:**
- Black is the primary style enforcer
- Pre-commit hooks enforce formatting before commits
- No separate linting configuration files (eslint, flake8, mypy config) detected

**Indentation:**
- 4 spaces per indentation level
- Consistent across all Python files

## Import Organization

**Order:**
1. Standard library imports (ast, json, logging, math, os, re, etc.)
2. Third-party library imports (typing, dotenv, langchain, pydantic, etc.)
3. Local/relative imports from agents package

**Example from `executor.py`:**
```python
import ast
import json
import logging
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agents.application.prompts import Prompter
from agents.connectors.chroma import PolymarketRAG as Chroma
from agents.polymarket.gamma import GammaMarketClient as Gamma
from agents.polymarket.polymarket import Polymarket
from agents.utils.objects import CandidateTrade, SimpleEvent, SimpleMarket
```

**Path Aliases:**
- Import aliases for clarity: `PolymarketRAG as Chroma`, `GammaMarketClient as Gamma`
- Absolute imports only (no relative `from . import` patterns observed)

## Error Handling

**Patterns:**
- Try-except blocks for specific exception types: `except (TypeError, ValueError):`
- Catch multiple specific exceptions rather than bare `except Exception:`
- Return `None` or default values on errors rather than raising in many cases
- Print error messages with context tags like `[cleanup]`, `[event]`, `[execution]`, `[news]`

**Examples from `trade.py`:**
```python
try:
    min_order_amount = float(os.getenv("TRADE_MIN_ORDER_AMOUNT_USDC", "1.0"))
except (TypeError, ValueError):
    min_order_amount = 1.0

try:
    shutil.rmtree(path)
except FileNotFoundError:
    continue
except Exception as err:
    print(f"[cleanup] unable_to_remove path={path} error={err}")
```

**Validation Functions:**
- Utility functions for env parsing: `_env_bool()`, `_env_int()`, `_env_float()`, `_safe_float()`
- Explicit conversion with sensible defaults rather than silent failures

## Logging

**Framework:** Mixed - Python `logging` module + `print()` statements

**Logger Setup (in `executor.py`):**
```python
import logging
self.logger = logging.getLogger(self.__class__.__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
```

**Patterns - Print Statements:**
- Used extensively for user-facing messages and detailed traces
- Format: `print(f"[component] key=value key=value message")`
- Bracket tags indicate component: `[cleanup]`, `[rationale]`, `[execution]`, `[news]`, `[portfolio]`, `[markets]`, `[event]`, `[run]`
- Machine-parseable format with key=value pairs for observability

**Patterns - Logger:**
- Used in `Executor` and `GammaMarketClient` for structured logging
- Formatted with context: `logger.info("[trade_cfg] candidate_count=%s...", value)`
- Used for important config and state transitions, not verbose traces

**When to Use:**
- Print: User-facing output, progress reporting, structured event logs
- Logger: Configuration validation, important transitions, warnings/errors

## Comments

**When to Comment:**
- Docstrings on public methods and classes
- Inline comments for non-obvious logic or business rules
- Comments on complex algorithms (e.g., the event slug extraction logic in `_extract_event_slug_from_url()`)

**JSDoc/TSDoc:**
- Not used (Python codebase uses docstrings)
- Type hints via `typing` module annotations preferred over docstring types

**Examples from `trade.py`:**
```python
def one_best_trade(self, include_news: Optional[bool] = None, ...) -> None:
    """
    one_best_trade runs the autonomous trading pipeline end-to-end.
    """

# Inline comment explaining fallback logic
if direct_matches:
    # Prefer active/open/non-archived, but still return a slug match if only closed/archived exists.
    preferred = sorted(...)
```

## Function Design

**Size:**
- Methods range from 5-50 lines typically
- Longer methods used for complex business logic with clear sections: `one_best_trade()` is ~170 lines with numbered steps
- Private helper methods extract reusable functionality

**Parameters:**
- Use type hints for all parameters: `def get_articles_for_cli_keywords(self, keywords: str, limit: int = 10, ...)`
- Optional parameters with defaults at end: `Optional[bool] = None`
- Keyword arguments preferred for optional config: `def build_trade_candidates(self, filtered_markets, supplemental_context_by_market_id=None)`

**Return Values:**
- Explicit type hints: `-> None`, `-> str`, `-> List[CandidateTrade]`
- Tuples for multiple returns: `-> tuple[list[Article], bool]`
- Return `None` for void methods or early exits
- Return empty collections `[]` or `{}` rather than `None` for collection types

**Example from `executor.py`:**
```python
def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")
```

## Module Design

**Exports:**
- No `__init__.py` barrel files observed with `from X import *`
- Direct imports from modules: `from agents.application.trade import Trader`
- All top-level functions and classes are importable by design

**Barrel Files:**
- Not used in this codebase
- Each module handles its own exports explicitly

## Pydantic Models

**Pattern:**
- Used for data objects requiring validation: `SimpleMarket`, `CandidateTrade`, `Article`, `SimpleEvent`
- Location: `agents/utils/objects.py`
- Fields with type hints and optional defaults: `active: bool`, `volume: Optional[float] = 0.0`
- `from __future__ import annotations` for forward references

**Example from `objects.py`:**
```python
from pydantic import BaseModel, Field

class SimpleMarket(BaseModel):
    id: int
    question: str
    end: str
    description: str
    active: bool
    funded: bool
    volume: Optional[float] = 0.0
```

## Environment Configuration

**Pattern:**
- Load from `.env` file via `python-dotenv`
- Parsed with helper functions in code: `_env_bool()`, `_env_int()`, `_env_float()`
- Sensible defaults in code rather than required in `.env`
- Configuration often collected at class `__init__` time

**Example from `trade.py`:**
```python
def __init__(self):
    self.execute_trades = (
        str(os.getenv("EXECUTE_TRADES", "false")).strip().lower()
        in ("1", "true", "yes", "on")
    )
    self.min_order_amount_usdc = max(0.0, float(os.getenv("TRADE_MIN_ORDER_AMOUNT_USDC", "1.0")))
```

---

*Convention analysis: 2026-03-03*
