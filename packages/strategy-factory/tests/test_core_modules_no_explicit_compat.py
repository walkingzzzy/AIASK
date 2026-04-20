from __future__ import annotations

from pathlib import Path


CORE_MODULES = (
    "packages/strategy-factory/src/strategy_factory/application/factory_scheduler.py",
    "packages/strategy-factory/src/strategy_factory/application/_factory_scheduler_analysis.py",
    "packages/strategy-factory/src/strategy_factory/application/_factory_scheduler_runtime.py",
    "packages/strategy-factory/src/strategy_factory/application/_factory_scheduler_loop.py",
    "packages/strategy-factory/src/strategy_factory/application/submitter.py",
    "packages/strategy-factory/src/strategy_factory/application/_submitter_helpers.py",
    "packages/strategy-factory/src/strategy_factory/application/_submitter_policy.py",
    "packages/strategy-factory/src/strategy_factory/application/_submitter_actions.py",
    "packages/strategy-factory/src/strategy_factory/application/backtest_filter.py",
    "packages/strategy-factory/src/strategy_factory/application/quality_gates.py",
    "packages/strategy-factory/src/strategy_factory/application/deduplicator.py",
    "packages/strategy-factory/src/strategy_factory/application/elimination.py",
)


def test_core_migrated_modules_do_not_use_explicit_compat_bridge():
    repo_root = Path(__file__).resolve().parents[3]
    forbidden_tokens = ("get_compat_symbol", "call_compat_async", "get_compat_value")

    for relative_path in CORE_MODULES:
        source = (repo_root / relative_path).read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in source, f"{relative_path} still contains explicit compat bridge token: {token}"
