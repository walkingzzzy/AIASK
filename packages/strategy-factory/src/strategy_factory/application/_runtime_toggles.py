"""Strategy Factory runtime feature toggles.

所有改变 admission/grade 行为的修改都通过环境变量包裹,允许观察期后视效果决定
固化或回滚。命名空间统一以 STRATEGY_FACTORY_ / INCUBATION_FACTORY_ 前缀,集中
在此文件维护。

关联方案: 策略工厂到孵化工厂过渡-开发方案-2026-05-26.md (DEV-V1)
关联架构: 策略工厂到孵化工厂过渡架构方案-2026-05-26.md (V4-network §15.2 / §16.2)
"""

from __future__ import annotations

import os
from typing import FrozenSet


def _env_bool(name: str, default: bool) -> bool:
    """解析 1/true/yes/on (大小写不敏感) 为 True,其它为 False。

    未设置 env 时使用 default。default=False 是安全默认。
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    value = str(raw).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _env_set(name: str, default: str = "") -> FrozenSet[str]:
    """解析逗号分隔的字符串为 frozenset,自动 strip 空白与小写化。"""
    raw = os.getenv(name, default)
    value = str(raw or "").strip().lower()
    if not value:
        return frozenset()
    return frozenset(item.strip() for item in value.split(",") if item.strip())


# === DEV-V1 P0: 允许 D 级 + Gate passed 候选走 observe lane ===
# 默认 False 保持现有行为;灰度期间手动 export STRATEGY_FACTORY_OBSERVE_D_GRADE_ENABLED=1
# 验收期 14 天,验收通过后再修改默认值或固化删除 toggle。
def observe_d_grade_enabled() -> bool:
    return _env_bool("STRATEGY_FACTORY_OBSERVE_D_GRADE_ENABLED", default=False)


# === DEV-V1 P3: 扩展 _TRADE_AWARE_VALIDATION_GRADE_FAMILIES 集合 ===
# 默认空集保持现有行为;灰度期间手动 export STRATEGY_FACTORY_TRADE_AWARE_EXTRA_FAMILIES=...
# 推荐渐进灰度顺序:
#   Week N+0: ""
#   Week N+1: "volatility_breakout"                    # 占 48% 候选,优先
#   Week N+2: "volatility_breakout,value_factor"
#   Week N+3: "volatility_breakout,value_factor,sector_rotation"
#   Week N+4: 全集 (volatility_breakout,value_factor,sector_rotation,
#                   macro_timing,growth_factor,north_capital_track,event_structure_breakout)
# 短周期反转型 (rsi/mean_reversion_short/gap_fill/margin_divergence) 不建议扩展。
def trade_aware_extra_families() -> FrozenSet[str]:
    return _env_set("STRATEGY_FACTORY_TRADE_AWARE_EXTRA_FAMILIES", default="")


# === DEV-V1 P1: 孵化工厂消费 paper observation 候选 ===
# 默认 False;P0 灰度产生 paper account 后再开启,否则空管道。
def paper_intake_enabled() -> bool:
    return _env_bool("INCUBATION_FACTORY_PAPER_INTAKE_ENABLED", default=False)


# === DEV-V1 P1 配套:单批 paper observation 的 batch limit ===
def paper_intake_batch_limit() -> int:
    raw = os.getenv("INCUBATION_FACTORY_PAPER_INTAKE_BATCH_LIMIT", "50")
    try:
        value = int(str(raw).strip())
    except Exception:
        value = 50
    return max(1, min(value, 500))


# === DEV-V2: Gate-3 failed but diagnostically useful candidates ===
def diagnostic_observation_enabled() -> bool:
    return _env_bool("STRATEGY_FACTORY_DIAGNOSTIC_OBSERVATION_ENABLED", default=False)


def diagnostic_observation_batch_limit() -> int:
    raw = os.getenv("STRATEGY_FACTORY_DIAGNOSTIC_OBSERVATION_BATCH_LIMIT", "5")
    try:
        value = int(str(raw).strip())
    except Exception:
        value = 5
    return max(1, min(value, 50))


def diagnostic_observation_ttl_days() -> int:
    raw = os.getenv("STRATEGY_FACTORY_DIAGNOSTIC_OBSERVATION_TTL_DAYS", "7")
    try:
        value = int(str(raw).strip())
    except Exception:
        value = 7
    return max(1, min(value, 30))


__all__ = [
    "observe_d_grade_enabled",
    "trade_aware_extra_families",
    "paper_intake_enabled",
    "paper_intake_batch_limit",
    "diagnostic_observation_enabled",
    "diagnostic_observation_batch_limit",
    "diagnostic_observation_ttl_days",
]
