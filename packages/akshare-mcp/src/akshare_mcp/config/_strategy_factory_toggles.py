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


def diagnostic_intake_enabled() -> bool:
    return _env_bool("INCUBATION_FACTORY_DIAGNOSTIC_INTAKE_ENABLED", default=False)


def diagnostic_intake_batch_limit() -> int:
    raw = os.getenv("INCUBATION_FACTORY_DIAGNOSTIC_BATCH_LIMIT", "5")
    try:
        value = int(str(raw).strip())
    except Exception:
        value = 5
    return max(1, min(value, 50))


__all__ = [
    "paper_intake_enabled",
    "paper_intake_batch_limit",
    "diagnostic_intake_enabled",
    "diagnostic_intake_batch_limit",
]
