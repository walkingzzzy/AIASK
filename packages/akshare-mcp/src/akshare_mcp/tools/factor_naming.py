"""统一 Factor 命名空间 resolver(诊断报告 §4.2.1 修复)。

P2-4.2.1 fix:quant_manager 内 4 个 action 命名规则不一致,导致 AI Agent
传 `momentum_20d` 在 factor_ic 接受、在 batch_compute_factors 拒绝、在
calculate_factor 又要求 `_ttm` 后缀。

本模块提供:
- ``resolve_factor_name(name, action)`` 一站式归一化,接受任意 alias / 后缀 / 大小写
- ``list_factor_aliases()`` 列出所有别名 → canonical 映射(供 list_factors 暴露)
- ``check_factor_supported(name)`` 严格校验,返回 (canonical, available, error_msg)
"""
from __future__ import annotations

from typing import Any

from .quant_definitions import SUPPORTED_FACTORS, _normalize_factor_name


# 跨 action 的统一别名扩展(诊断报告 §4.2.1 实测案例)
_CROSS_ACTION_ALIASES: dict[str, str] = {
    # mom_Nd vs momentum_Nd 双向
    "momentum_20d": "momentum",
    "mom_20d": "momentum",
    "momentum_30d": "mom_60d",  # fallback 到最近的预设
    # _ttm 后缀(calculate_factor 要求)兼容
    "roe_ttm": "roe",
    "pe_ttm": "pe_ratio",
    "pb_ttm": "pb_ratio",
    "ps_ttm": "ps_ratio",
    "eps_ttm": "eps",
    # 全大写/混合大小写 已通过 .lower() 处理
    # 别名:rsi_14 vs rsi
    "rsi_14": "rsi",
    "rsi_6": "rsi",  # 不同周期映射到同一 canonical
    "rsi_24": "rsi",
}


def resolve_factor_name(name: str, action: str | None = None) -> str:
    """统一的 factor name resolver。

    Args:
        name: 输入(可以是 canonical / alias / 大小写混合 / 后缀变体)
        action: 调用方 action(如 'factor_ic' / 'calculate_factor'),
                目前不影响解析逻辑,保留供未来 action-specific override

    Returns:
        canonical factor name(若无法识别,返回 normalized 输入,由调用方做存在性校验)
    """
    if not name:
        return ""
    raw = str(name).strip().lower()
    # 优先走 _CROSS_ACTION_ALIASES(本模块新增)
    if raw in _CROSS_ACTION_ALIASES:
        return _CROSS_ACTION_ALIASES[raw]
    # 再走 quant_definitions._normalize_factor_name(已有 50 个标准名 + 内部 aliases)
    return _normalize_factor_name(raw)


def list_factor_aliases() -> dict[str, list[str]]:
    """列出 canonical → list[alias] 完整映射。

    用于 list_factors 工具返回 alias-canonical 透明视图,
    AI Agent 可一次性看到 'momentum 接受哪些别名'。

    Returns:
        dict[str, list[str]]:
            { 'momentum': ['mom', 'mom_20d', 'momentum_20d'], 'rsi': ['rsi_14', ...], ... }
    """
    result: dict[str, list[str]] = {}
    # 1. 从 SUPPORTED_FACTORS.aliases 收集
    for canonical, meta in SUPPORTED_FACTORS.items():
        result.setdefault(canonical, [])
        for alias in meta.get("aliases", []) or []:
            ak = str(alias).strip().lower()
            if ak and ak not in result[canonical] and ak != canonical:
                result[canonical].append(ak)
    # 2. 从 _CROSS_ACTION_ALIASES 补充
    for alias, canonical in _CROSS_ACTION_ALIASES.items():
        if canonical not in result:
            result[canonical] = []
        if alias not in result[canonical]:
            result[canonical].append(alias)
    # 3. 排序,稳定输出
    for canonical in result:
        result[canonical].sort()
    return result


def check_factor_supported(name: str) -> tuple[str, bool, str | None]:
    """检查 factor 是否被支持。

    Returns:
        (canonical_name, is_supported, error_msg)
    """
    if not name:
        return "", False, "factor name is empty"
    canonical = resolve_factor_name(name)
    if canonical in SUPPORTED_FACTORS:
        return canonical, True, None
    aliases = list_factor_aliases()
    suggestions = []
    name_lower = str(name).strip().lower()
    for canon, alias_list in aliases.items():
        if name_lower in canon or any(name_lower in a for a in alias_list):
            suggestions.append(canon)
    if suggestions:
        msg = f"Unsupported factor '{name}'. Did you mean: {', '.join(suggestions[:3])}?"
    else:
        msg = (
            f"Unsupported factor '{name}'. Supported canonical: "
            f"{', '.join(sorted(SUPPORTED_FACTORS.keys())[:10])}, ... "
            f"(call list_factors for full list)"
        )
    return canonical, False, msg


# 向后兼容:重新导出 _normalize_factor_name
__all__ = [
    "resolve_factor_name",
    "list_factor_aliases",
    "check_factor_supported",
    "_normalize_factor_name",
]
