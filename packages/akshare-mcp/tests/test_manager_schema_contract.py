"""T03: Manager schema contract tests.

Verify that all Manager tools have properly structured MCP schemas:
- 'required' fields must NOT contain 'kwargs' or 'extra_kwargs'
- All managers must accept 'action' as the first required parameter
- 'params' and 'kwargs' must be optional (not required)
"""

import importlib
import inspect
import json
import re
from pathlib import Path
from typing import get_type_hints

import pytest

MANAGERS_DIR = Path(__file__).resolve().parent.parent / "src" / "akshare_mcp" / "tools" / "managers"


def _discover_manager_files():
    """Find all *_manager.py files."""
    return sorted(MANAGERS_DIR.glob("*_manager.py"))


def _extract_manager_function_name(filepath: Path) -> str | None:
    """Extract the async def xxx_manager name from file."""
    content = filepath.read_text(encoding="utf-8")
    # Find the registered tool function (inside register_xxx_manager)
    match = re.search(r"async def (\w+_manager)\(", content)
    return match.group(1) if match else None


def _extract_manager_signature(filepath: Path) -> str | None:
    """Extract the function signature line."""
    content = filepath.read_text(encoding="utf-8")
    # Find lines with async def xxx_manager(
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("async def ") and "_manager(" in stripped:
            return stripped
    return None


@pytest.fixture
def manager_files():
    return _discover_manager_files()


class TestManagerSchemaContract:
    """Ensure all manager signatures produce valid MCP schemas."""

    def test_all_managers_discovered(self, manager_files):
        """Sanity check: we should have at least 25 manager files."""
        assert len(manager_files) >= 25, f"Expected at least 25 managers, found {len(manager_files)}"

    @pytest.mark.parametrize("filepath", _discover_manager_files(), ids=lambda p: p.stem)
    def test_no_star_kwargs_in_signature(self, filepath):
        """No manager should use **kwargs in its MCP tool signature."""
        content = filepath.read_text(encoding="utf-8")
        # Find the @mcp.tool() decorated function signature
        in_tool_decorator = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("@mcp.tool"):
                in_tool_decorator = True
                continue
            if in_tool_decorator and stripped.startswith("async def "):
                assert "**kwargs" not in stripped, (
                    f"{filepath.name}: MCP tool signature still uses **kwargs: {stripped}"
                )
                assert "**extra_kwargs" not in stripped, (
                    f"{filepath.name}: MCP tool signature still uses **extra_kwargs: {stripped}"
                )
                in_tool_decorator = False

    @pytest.mark.parametrize("filepath", _discover_manager_files(), ids=lambda p: p.stem)
    def test_action_is_first_param(self, filepath):
        """Every manager must have 'action: str' as first parameter."""
        sig = _extract_manager_signature(filepath)
        if sig is None:
            pytest.skip(f"No manager function found in {filepath.name}")
        # After 'def xxx_manager(', the first param should be 'action'
        match = re.search(r"_manager\((.+)", sig)
        if match:
            first_params = match.group(1)
            assert first_params.startswith("action:") or first_params.startswith("action :"), (
                f"{filepath.name}: first parameter should be 'action', got: {first_params[:50]}"
            )

    @pytest.mark.parametrize("filepath", _discover_manager_files(), ids=lambda p: p.stem)
    def test_kwargs_is_optional(self, filepath):
        """If 'kwargs' exists in signature, it must have a default value (not required)."""
        sig = _extract_manager_signature(filepath)
        if sig is None:
            pytest.skip(f"No manager function found in {filepath.name}")
        # Check that kwargs has a default: kwargs: Any = None or kwargs: str = '{}'
        if "kwargs" in sig and "**kwargs" not in sig:
            # Should have '= None' or '= "{}"' or similar default
            # Extract the kwargs parameter
            kwargs_match = re.search(r"kwargs\s*:\s*\w+[^,)]*", sig)
            if kwargs_match:
                param_text = kwargs_match.group(0)
                assert "=" in param_text, (
                    f"{filepath.name}: 'kwargs' parameter must have a default value: {param_text}"
                )

    @pytest.mark.parametrize("filepath", _discover_manager_files(), ids=lambda p: p.stem)
    def test_has_normalize_manager_payload(self, filepath):
        """All migrated managers should use normalize_manager_payload."""
        content = filepath.read_text(encoding="utf-8")
        # strategy_manager and quant_manager may use older normalize patterns
        if filepath.stem in ("strategy_manager", "quant_manager"):
            pytest.skip(f"{filepath.stem} uses pre-existing structured protocol")
        assert "normalize_manager_payload" in content, (
            f"{filepath.name}: should import and use normalize_manager_payload"
        )
