"""Unit tests for agents/utils/env.py shared environment variable helpers.

Tests verify:
- _env_bool default behavior (key missing)
- _env_bool truthy values: "1", "true", "yes", "on" (case-insensitive, whitespace-trimmed)
- _env_bool falsy values: "0", "false", "no", "off", any other string
- _env_int default behavior (key missing)
- _env_int valid integer parsing
- _env_int graceful fallback on non-numeric strings (no crash)
- _env_float default behavior (key missing)
- _env_float valid float parsing
- _env_float graceful fallback on non-numeric strings (no crash)
- agents/utils/env.py imports ONLY os (no heavy deps)
"""

import ast
import importlib
import os
import sys
from unittest.mock import patch

import pytest

from agents.utils.env import _env_bool, _env_float, _env_int


# ---------------------------------------------------------------------------
# _env_bool tests
# ---------------------------------------------------------------------------


class TestEnvBool:
    def test_returns_false_default_when_key_not_set(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TEST_BOOL_MISSING", None)
            assert _env_bool("TEST_BOOL_MISSING", False) is False

    def test_returns_true_default_when_key_not_set(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TEST_BOOL_MISSING", None)
            assert _env_bool("TEST_BOOL_MISSING", True) is True

    def test_true_for_value_1(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "1")
        assert _env_bool("TEST_BOOL", False) is True

    def test_true_for_value_true_lowercase(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "true")
        assert _env_bool("TEST_BOOL", False) is True

    def test_true_for_value_true_uppercase(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "TRUE")
        assert _env_bool("TEST_BOOL", False) is True

    def test_true_for_value_yes(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "yes")
        assert _env_bool("TEST_BOOL", False) is True

    def test_true_for_value_YES_uppercase(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "YES")
        assert _env_bool("TEST_BOOL", False) is True

    def test_true_for_value_on(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "on")
        assert _env_bool("TEST_BOOL", False) is True

    def test_true_for_value_on_uppercase(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "ON")
        assert _env_bool("TEST_BOOL", False) is True

    def test_true_with_leading_whitespace(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "  true  ")
        assert _env_bool("TEST_BOOL", False) is True

    def test_false_for_value_0(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "0")
        assert _env_bool("TEST_BOOL", True) is False

    def test_false_for_value_false_lowercase(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "false")
        assert _env_bool("TEST_BOOL", True) is False

    def test_false_for_value_no(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "no")
        assert _env_bool("TEST_BOOL", True) is False

    def test_false_for_value_off(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "off")
        assert _env_bool("TEST_BOOL", True) is False

    def test_false_for_arbitrary_string(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "anything_else")
        assert _env_bool("TEST_BOOL", True) is False


# ---------------------------------------------------------------------------
# _env_int tests
# ---------------------------------------------------------------------------


class TestEnvInt:
    def test_returns_default_when_key_not_set(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TEST_INT_MISSING", None)
            assert _env_int("TEST_INT_MISSING", 42) == 42

    def test_returns_zero_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TEST_INT_MISSING", None)
            assert _env_int("TEST_INT_MISSING", 0) == 0

    def test_parses_valid_integer(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "100")
        assert _env_int("TEST_INT", 0) == 100

    def test_parses_negative_integer(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "-5")
        assert _env_int("TEST_INT", 0) == -5

    def test_returns_default_for_non_numeric_string(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "not_a_number")
        assert _env_int("TEST_INT", 42) == 42

    def test_returns_default_for_float_string(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "3.14")
        assert _env_int("TEST_INT", 42) == 42

    def test_returns_default_for_empty_string(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "")
        assert _env_int("TEST_INT", 42) == 42


# ---------------------------------------------------------------------------
# _env_float tests
# ---------------------------------------------------------------------------


class TestEnvFloat:
    def test_returns_default_when_key_not_set(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TEST_FLOAT_MISSING", None)
            assert _env_float("TEST_FLOAT_MISSING", 3.14) == pytest.approx(3.14)

    def test_returns_zero_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TEST_FLOAT_MISSING", None)
            assert _env_float("TEST_FLOAT_MISSING", 0.0) == pytest.approx(0.0)

    def test_parses_valid_float(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT", "2.718")
        assert _env_float("TEST_FLOAT", 0.0) == pytest.approx(2.718)

    def test_parses_integer_as_float(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT", "5")
        assert _env_float("TEST_FLOAT", 0.0) == pytest.approx(5.0)

    def test_parses_negative_float(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT", "-1.5")
        assert _env_float("TEST_FLOAT", 0.0) == pytest.approx(-1.5)

    def test_returns_default_for_non_numeric_string(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT", "not_a_number")
        assert _env_float("TEST_FLOAT", 3.14) == pytest.approx(3.14)

    def test_returns_default_for_empty_string(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT", "")
        assert _env_float("TEST_FLOAT", 3.14) == pytest.approx(3.14)


# ---------------------------------------------------------------------------
# Import purity test — agents/utils/env.py must only import os
# ---------------------------------------------------------------------------


class TestEnvModuleImportPurity:
    def test_env_module_only_imports_os(self):
        """Parse agents/utils/env.py source and assert the only import is 'os'."""
        module_path = os.path.join(
            os.path.dirname(__file__), "..", "agents", "utils", "env.py"
        )
        module_path = os.path.abspath(module_path)
        with open(module_path, "r") as f:
            source = f.read()

        tree = ast.parse(source)
        imported_names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                module_name = (node.module or "").split(".")[0]
                imported_names.append(module_name)

        # Remove duplicates
        imported_names = list(set(imported_names))

        forbidden = [name for name in imported_names if name not in ("os", "")]
        assert forbidden == [], (
            f"agents/utils/env.py must only import 'os', "
            f"but found additional imports: {forbidden}"
        )
