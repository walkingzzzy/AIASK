from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from strategy_factory.api import facade
from strategy_factory.application import runtime


REPO_ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN_SOURCE_TOKENS = (
    "get_legacy_strategy_factory_scheduler",
    "get_legacy_strategy_factory_package",
    "legacy_bridge",
)


def test_runtime_package_returns_local_view_only(monkeypatch):
    runtime._build_local_runtime_view.cache_clear()
    monkeypatch.setattr(
        runtime,
        "_build_local_runtime_view",
        lambda: SimpleNamespace(sample_symbol="local", get_strategy_factory_scheduler=lambda: "local"),
    )

    package = runtime.get_strategy_factory_package()
    assert package.sample_symbol == "local"
    assert package.get_strategy_factory_scheduler() == "local"


def test_runtime_legacy_package_accessor_is_removed():
    assert not hasattr(runtime, "get_legacy_strategy_factory_package")


def test_facade_default_scheduler_stays_local(monkeypatch):
    monkeypatch.setattr(
        facade,
        "_runtime_get_strategy_factory_package",
        lambda: SimpleNamespace(get_strategy_factory_scheduler=lambda: "local"),
    )

    assert facade.get_strategy_factory_scheduler() == "local"


def test_facade_legacy_scheduler_accessor_is_removed():
    assert not hasattr(facade, "get_legacy_strategy_factory_scheduler")


def test_facade_rejects_removed_prefer_legacy_kwarg():
    with pytest.raises(TypeError, match="legacy scheduler access is no longer available"):
        facade.get_strategy_factory_scheduler(prefer_legacy=True)


def test_legacy_runtime_tokens_are_removed_from_strategy_factory_source():
    source_root = REPO_ROOT / "packages/strategy-factory/src"
    for token in FORBIDDEN_SOURCE_TOKENS:
        actual_paths: list[str] = []
        for path in source_root.rglob("*.py"):
            relative_path = path.relative_to(REPO_ROOT).as_posix()
            source = path.read_text(encoding="utf-8", errors="ignore")
            if token in source:
                actual_paths.append(relative_path)
        assert not actual_paths, f"{token} still exists in source: {sorted(actual_paths)}"
