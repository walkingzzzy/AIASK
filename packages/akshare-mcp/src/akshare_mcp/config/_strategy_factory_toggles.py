"""Strategy Factory release toggles — akshare-mcp side mirror.

与 packages/strategy-factory/.../_runtime_toggles.py 保持同步。
任何修改都需要双侧同时改。

关联:策略工厂到孵化工厂过渡-开发方案-2026-05-26.md (P1)
"""

from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = str(raw).strip().lower()
    return value in {"1", "true", "yes", "on"}


def paper_intake_enabled() -> bool:
    return _env_bool("INCUBATION_FACTORY_PAPER_INTAKE_ENABLED", default=False)


def paper_intake_batch_limit() -> int:
    raw = os.getenv("INCUBATION_FACTORY_PAPER_INTAKE_BATCH_LIMIT", "50")
    try:
        value = int(str(raw).strip())
    except Exception:
        value = 50
    return max(1, min(value, 500))


def recompile_remediation_enabled() -> bool:
    """P0-b/P1: 孵化工厂每轮对 observe 池趋势策略重编译补 compiled_dsl + 测量
    instrument_profile,并把满足 formal readiness 的样本升级到 formal_incubation。
    默认 OFF,行为与改造前一致。"""
    return _env_bool("INCUBATION_FACTORY_RECOMPILE_REMEDIATION_ENABLED", default=False)


def recompile_remediation_batch_limit() -> int:
    raw = os.getenv("INCUBATION_FACTORY_RECOMPILE_REMEDIATION_BATCH_LIMIT", "200")
    try:
        value = int(str(raw).strip())
    except Exception:
        value = 200
    return max(1, min(value, 1000))


def diagnostic_intake_enabled() -> bool:
    return _env_bool("INCUBATION_FACTORY_DIAGNOSTIC_INTAKE_ENABLED", default=False)


def diagnostic_intake_batch_limit() -> int:
    raw = os.getenv("INCUBATION_FACTORY_DIAGNOSTIC_BATCH_LIMIT", "5")
    try:
        value = int(str(raw).strip())
    except Exception:
        value = 5
    return max(1, min(value, 50))


def gate3_record_only_intake_enabled() -> bool:
    return _env_bool("INCUBATION_FACTORY_GATE3_RECORD_ONLY_INTAKE_ENABLED", default=False)


def gate3_record_only_intake_batch_limit() -> int:
    raw = os.getenv("INCUBATION_FACTORY_GATE3_RECORD_ONLY_BATCH_LIMIT", "100")
    try:
        value = int(str(raw).strip())
    except Exception:
        value = 100
    return max(1, min(value, 500))


def gate3_record_only_intake_min_grade() -> str:
    grade = str(os.getenv("INCUBATION_FACTORY_GATE3_RECORD_ONLY_MIN_GRADE", "C") or "").strip().upper()
    return grade if grade in {"D", "C", "B", "A", "S", "SS", "SSS"} else "C"


__all__ = [
    "paper_intake_enabled",
    "paper_intake_batch_limit",
    "diagnostic_intake_enabled",
    "diagnostic_intake_batch_limit",
    "gate3_record_only_intake_enabled",
    "gate3_record_only_intake_batch_limit",
    "gate3_record_only_intake_min_grade",
]
