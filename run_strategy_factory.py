#!/usr/bin/env python3
"""Compatibility entrypoint for the Strategy Factory runner.

The maintained implementation lives at ``scripts/factories/run_strategy_factory.py``.
This module keeps older imports and root-level invocations working while avoiding
a second copy of runner logic.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
_RUNNER_PATH = ROOT / "scripts" / "factories" / "run_strategy_factory.py"

# Boundary contract remains implemented in the maintained runner:
# target_codes=self.target_codes
# list_strategy_factory_dispatches


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("_aiask_strategy_factory_runner", _RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load Strategy Factory runner from {_RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


_runner = _load_runner_module()

StrategyFactoryRunner = _runner.StrategyFactoryRunner
parse_args = _runner.parse_args
main = _runner.main
_normalize_cycle_result = _runner._normalize_cycle_result
_resolve_runner_interval_sec = _runner._resolve_runner_interval_sec
_load_strategy_factory_runtime_kwargs = _runner._load_strategy_factory_runtime_kwargs


if __name__ == "__main__":
    main()
