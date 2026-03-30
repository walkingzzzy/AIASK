"""T03: Manager help contract tests.

Verify that every Manager tool supports a basic `action="help"` call
that returns structured help information.

These tests import only the protocol layer and do static analysis,
avoiding database/network dependencies.
"""

import re
from pathlib import Path

import pytest

MANAGERS_DIR = Path(__file__).resolve().parent.parent / "src" / "akshare_mcp" / "tools" / "managers"


def _discover_manager_files():
    """Find all *_manager.py files."""
    return sorted(MANAGERS_DIR.glob("*_manager.py"))


def _has_help_action(content: str) -> bool:
    """Check if the file handles action == 'help'."""
    return bool(
        re.search(r"""action\s*==\s*['"]help['"]""", content)
        or re.search(r"""['"]help['"]\s*:""", content)
    )


def _has_supported_actions_dict(content: str) -> bool:
    """Check if the file defines SUPPORTED_ACTIONS or similar help dict."""
    return bool(
        "supported_actions" in content.lower()
        or "SUPPORTED_ACTIONS" in content
    )


class TestManagerHelpContract:
    """Verify every manager handles action='help' properly."""

    @pytest.mark.parametrize("filepath", _discover_manager_files(), ids=lambda p: p.stem)
    def test_has_help_action_handler(self, filepath):
        """Every manager should handle action='help'."""
        content = filepath.read_text(encoding="utf-8")
        assert _has_help_action(content), (
            f"{filepath.name}: missing action='help' handler"
        )

    @pytest.mark.parametrize("filepath", _discover_manager_files(), ids=lambda p: p.stem)
    def test_has_supported_actions_documentation(self, filepath):
        """Every manager should document supported_actions in help response."""
        content = filepath.read_text(encoding="utf-8")
        assert _has_supported_actions_dict(content), (
            f"{filepath.name}: missing supported_actions documentation in help"
        )

    @pytest.mark.parametrize("filepath", _discover_manager_files(), ids=lambda p: p.stem)
    def test_docstring_present(self, filepath):
        """Every manager tool function should have a docstring."""
        content = filepath.read_text(encoding="utf-8")
        # Find @mcp.tool() followed by async def, then a docstring
        # Must handle multi-line function signatures (e.g. quant_manager)
        in_tool = False
        in_def = False
        found_closing_paren = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("@mcp.tool"):
                in_tool = True
                in_def = False
                found_closing_paren = False
                continue
            if in_tool and not in_def and stripped.startswith("async def "):
                in_def = True
                # Check if this is a single-line def (ends with ):)
                if stripped.endswith("):") or stripped.endswith(") -> dict:"):
                    found_closing_paren = True
                continue
            if in_tool and in_def and not found_closing_paren:
                # Still in multi-line signature, wait for closing ):
                if stripped.endswith("):") or stripped.endswith(") -> dict:"):
                    found_closing_paren = True
                continue
            if in_tool and in_def and found_closing_paren:
                # Next non-empty line after def should be docstring
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    in_tool = False  # found it
                    break
                elif stripped:
                    pytest.fail(
                        f"{filepath.name}: MCP tool function missing docstring after signature"
                    )
                    break

