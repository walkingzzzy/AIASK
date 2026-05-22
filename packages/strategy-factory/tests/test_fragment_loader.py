"""Tests for _fragment_loader safety checks."""

from __future__ import annotations

import os
import warnings

import pytest


def test_fragment_loader_no_redefinition_warnings_in_normal_mode():
    """In normal mode (check disabled), no warnings should be emitted."""
    # Ensure check is disabled
    os.environ.pop("STRATEGY_FACTORY_FRAGMENT_CHECK", None)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        from strategy_factory._fragment_loader import exec_fragments  # noqa: F401
        # No UserWarning about redefinitions
        redef_warnings = [x for x in w if "redefines" in str(x.message)]
        assert len(redef_warnings) == 0


def test_fragment_loader_detects_redefinition_when_enabled(tmp_path):
    """When STRATEGY_FACTORY_FRAGMENT_CHECK=1, redefinitions emit warnings."""
    os.environ["STRATEGY_FACTORY_FRAGMENT_CHECK"] = "1"
    try:
        # Reload the module to pick up the env change
        import importlib
        import strategy_factory._fragment_loader as fl
        importlib.reload(fl)

        # Create two fragments that define the same function
        parts_dir = tmp_path / "test_parts"
        parts_dir.mkdir()
        (parts_dir / "a.py").write_text("def my_func(): return 1\n")
        (parts_dir / "b.py").write_text("def my_func(): return 2\n")

        module_globals = {"__file__": str(tmp_path / "fake_module.py")}
        # Manually set up the parts dir to match
        fake_module = tmp_path / "fake_module.py"
        fake_module.write_text("")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            fl.exec_fragments(
                {"__file__": str(fake_module)},
                "test_parts",
                ["a.py", "b.py"],
            )
            redef_warnings = [x for x in w if "redefines" in str(x.message)]
            assert len(redef_warnings) == 1
            assert "my_func" in str(redef_warnings[0].message)
    finally:
        os.environ.pop("STRATEGY_FACTORY_FRAGMENT_CHECK", None)
        import importlib
        import strategy_factory._fragment_loader as fl
        importlib.reload(fl)
