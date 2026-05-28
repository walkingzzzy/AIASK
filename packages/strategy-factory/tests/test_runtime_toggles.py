"""Runtime toggle env-var parsing tests (DEV-V1 TG)."""

import pytest

from strategy_factory.application import _runtime_toggles as toggles


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Each test starts from a clean env."""
    for key in (
        "STRATEGY_FACTORY_OBSERVE_D_GRADE_ENABLED",
        "STRATEGY_FACTORY_TRADE_AWARE_EXTRA_FAMILIES",
        "INCUBATION_FACTORY_PAPER_INTAKE_ENABLED",
        "INCUBATION_FACTORY_PAPER_INTAKE_BATCH_LIMIT",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1", True),
        ("true", True),
        ("True", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("", False),
        ("garbage", False),
    ],
)
def test_observe_d_grade_enabled_parsing(monkeypatch, value, expected):
    monkeypatch.setenv("STRATEGY_FACTORY_OBSERVE_D_GRADE_ENABLED", value)
    assert toggles.observe_d_grade_enabled() is expected


def test_observe_d_grade_default_false_when_unset():
    """安全默认 — 未设置时不解封 D 级,保持现有行为。"""
    assert toggles.observe_d_grade_enabled() is False


def test_trade_aware_extra_families_empty():
    assert toggles.trade_aware_extra_families() == frozenset()


def test_trade_aware_extra_families_single(monkeypatch):
    monkeypatch.setenv("STRATEGY_FACTORY_TRADE_AWARE_EXTRA_FAMILIES", "volatility_breakout")
    assert toggles.trade_aware_extra_families() == frozenset({"volatility_breakout"})


def test_trade_aware_extra_families_multiple_csv(monkeypatch):
    monkeypatch.setenv(
        "STRATEGY_FACTORY_TRADE_AWARE_EXTRA_FAMILIES",
        "volatility_breakout,value_factor,sector_rotation",
    )
    assert toggles.trade_aware_extra_families() == frozenset(
        {"volatility_breakout", "value_factor", "sector_rotation"}
    )


def test_trade_aware_extra_families_strips_whitespace(monkeypatch):
    monkeypatch.setenv(
        "STRATEGY_FACTORY_TRADE_AWARE_EXTRA_FAMILIES",
        " volatility_breakout , value_factor ,, ",
    )
    assert toggles.trade_aware_extra_families() == frozenset(
        {"volatility_breakout", "value_factor"}
    )


def test_trade_aware_extra_families_lowercases(monkeypatch):
    """env 值大小写不敏感,统一转 lower 比对。"""
    monkeypatch.setenv("STRATEGY_FACTORY_TRADE_AWARE_EXTRA_FAMILIES", "Volatility_Breakout,VALUE_FACTOR")
    assert toggles.trade_aware_extra_families() == frozenset(
        {"volatility_breakout", "value_factor"}
    )


def test_paper_intake_enabled_default_false():
    assert toggles.paper_intake_enabled() is False


def test_paper_intake_enabled_via_env(monkeypatch):
    monkeypatch.setenv("INCUBATION_FACTORY_PAPER_INTAKE_ENABLED", "1")
    assert toggles.paper_intake_enabled() is True


def test_paper_intake_batch_limit_default():
    assert toggles.paper_intake_batch_limit() == 50


@pytest.mark.parametrize(
    "value,expected",
    [
        ("10", 10),
        ("100", 100),
        ("0", 1),  # 下限 1
        ("-5", 1),
        ("999", 500),  # 上限 500
        ("garbage", 50),  # 解析失败回退默认值
        ("", 50),
    ],
)
def test_paper_intake_batch_limit_bounds(monkeypatch, value, expected):
    monkeypatch.setenv("INCUBATION_FACTORY_PAPER_INTAKE_BATCH_LIMIT", value)
    assert toggles.paper_intake_batch_limit() == expected


def test_runtime_change_takes_effect(monkeypatch):
    """toggle 改变后立即生效,不依赖 module-level 缓存。"""
    assert toggles.observe_d_grade_enabled() is False
    monkeypatch.setenv("STRATEGY_FACTORY_OBSERVE_D_GRADE_ENABLED", "1")
    assert toggles.observe_d_grade_enabled() is True
    monkeypatch.delenv("STRATEGY_FACTORY_OBSERVE_D_GRADE_ENABLED")
    assert toggles.observe_d_grade_enabled() is False
