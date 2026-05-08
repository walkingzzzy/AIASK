"""策略说明书自动生成 (Gap 8, P4).

非阻断性功能：为 promotion review 生成人类可读的策略说明文档。
LLM 不可用时返回 fallback 模板，不影响策略提交流程。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 策略类型中文映射
_STRATEGY_TYPE_LABELS: Dict[str, str] = {
    "momentum": "动量策略",
    "ma_cross": "均线交叉策略",
    "rsi": "RSI策略",
    "value_factor": "价值因子策略",
    "quality_factor": "质量因子策略",
    "growth_factor": "成长因子策略",
    "multi_factor": "多因子策略",
    "macro_timing": "宏观择时策略",
    "volatility_breakout": "波动率突破策略",
    "event_structure_breakout": "事件结构突破策略",
    "gap_fill": "缺口回补策略",
    "mean_reversion_short": "均值回归策略",
    "sector_rotation": "板块轮动策略",
    "north_capital_track": "北向资金跟踪策略",
    "margin_divergence": "融资融券背离策略",
}

STRATEGY_DOC_SYSTEM_PROMPT = """你是一位专业的量化策略分析师。请根据提供的策略信息，生成一份简洁的中文策略说明书。
只输出以下四个部分，每个部分 2-3 句话，使用中文：

1. 策略原理：策略的核心逻辑和信号生成方式
2. 适用市场环境：在什么样的市场条件下表现最好
3. 主要风险：策略面临的关键风险
4. 关键参数说明：最重要的参数及其含义"""

STRATEGY_DOC_USER_PROMPT_TEMPLATE = """策略名称：{name}
策略类型：{strategy_type_label} ({strategy_type})
标的池：{target_symbols}
核心参数：{params}
回测指标：{backtest_metrics}
信号统计：{signal_quality}"""


def _string(value: Any) -> str:
    return str(value or "").strip()


def _format_backtest_metrics(metrics: Optional[dict]) -> str:
    if not metrics:
        return "暂无回测数据"
    m = dict(metrics)
    parts = []
    for key, label in [
        ("sharpe_ratio", "Sharpe"),
        ("max_drawdown", "最大回撤"),
        ("win_rate", "胜率"),
        ("total_return", "总收益"),
        ("trade_count", "交易次数"),
    ]:
        val = m.get(key)
        if val is not None:
            if key in ("max_drawdown", "win_rate", "total_return"):
                parts.append(f"{label}: {float(val):.1%}")
            elif key == "sharpe_ratio":
                parts.append(f"{label}: {float(val):.2f}")
            else:
                parts.append(f"{label}: {val}")
    return "; ".join(parts) if parts else "暂无回测数据"


def _format_signal_quality(signal_stats: Optional[dict]) -> str:
    if not signal_stats:
        return "暂无信号统计"
    s = dict(signal_stats)
    parts = []
    hit_rates = s.get("hit_rate", {})
    if hit_rates:
        hr_5d = hit_rates.get(5) or hit_rates.get("5")
        if hr_5d is not None:
            parts.append(f"5日命中率: {float(hr_5d):.1%}")
    skill = s.get("skill_lcb", {})
    if skill:
        sk_5d = skill.get(5) or skill.get("5")
        if sk_5d is not None:
            parts.append(f"5日Skill LCB: {float(sk_5d):.3f}")
    total = s.get("total_signals")
    if total is not None:
        parts.append(f"总信号数: {total}")
    return "; ".join(parts) if parts else "暂无信号统计"


def build_fallback_document(strategy: dict, backtest_metrics: Optional[dict] = None, signal_quality: Optional[dict] = None) -> dict:
    """生成模板化的策略说明书（LLM 不可用时的降级方案）."""
    strategy_type = _string(strategy.get("strategy_type")).lower()
    type_label = _STRATEGY_TYPE_LABELS.get(strategy_type, strategy_type or "通用策略")
    name = _string(strategy.get("name")) or f"{type_label}-{str(strategy.get('id') or 'unknown')[:8]}"
    target_symbols = strategy.get("target_symbols") or strategy.get("params", {}).get("target_symbols") or []
    if isinstance(target_symbols, list):
        symbols_str = ", ".join(_string(s) for s in target_symbols[:10])
        if len(target_symbols) > 10:
            symbols_str += f" 等{len(target_symbols)}只"
    else:
        symbols_str = _string(target_symbols)

    return {
        "strategy_id": _string(strategy.get("id")),
        "document_kind": "promotion_review_brief",
        "language": "zh-CN",
        "llm_generated": False,
        "fallback_used": True,
        "sections": {
            "principle": f"{name}是一只{type_label}，通过量化模型对{symbols_str or '全市场'}进行分析，生成交易信号。",
            "market_regime": f"该策略适用于常规市场环境，建议在持仓周期内持续观察信号表现。",
            "risk_boundaries": "主要风险包括市场系统性风险、策略模型失效风险及流动性风险。",
            "key_parameters": f"策略类型: {type_label}; 标的范围: {symbols_str or '全市场'}。",
        },
        "backtest_summary": _format_backtest_metrics(backtest_metrics),
        "signal_summary": _format_signal_quality(signal_quality),
    }


async def generate_strategy_document(
    llm_client: Optional[Any],
    strategy: dict,
    *,
    backtest_metrics: Optional[dict] = None,
    signal_quality: Optional[dict] = None,
) -> dict:
    """生成策略说明书（优先 LLM，不可用时 fallback）.

    此函数不抛出异常 — LLM 失败时自动降级。
    """
    # 如果 LLM 客户端不可用，直接返回 fallback
    if llm_client is None:
        return build_fallback_document(strategy, backtest_metrics, signal_quality)

    strategy_type = _string(strategy.get("strategy_type")).lower()
    type_label = _STRATEGY_TYPE_LABELS.get(strategy_type, strategy_type or "通用策略")
    name = _string(strategy.get("name")) or f"{type_label}-{str(strategy.get('id') or 'unknown')[:8]}"

    target_symbols = strategy.get("target_symbols") or strategy.get("params", {}).get("target_symbols") or []
    if isinstance(target_symbols, list):
        symbols_str = ", ".join(_string(s) for s in target_symbols[:10])
    else:
        symbols_str = _string(target_symbols)

    params = strategy.get("params", {})
    # 简化参数展示（截断过长值）
    params_brief = {
        k: (str(v)[:80] if not isinstance(v, (int, float, bool)) else v)
        for k, v in dict(params).items()
    }

    user_prompt = STRATEGY_DOC_USER_PROMPT_TEMPLATE.format(
        name=name,
        strategy_type_label=type_label,
        strategy_type=strategy_type,
        target_symbols=symbols_str or "全市场",
        params=str(params_brief)[:500],
        backtest_metrics=_format_backtest_metrics(backtest_metrics),
        signal_quality=_format_signal_quality(signal_quality),
    )

    try:
        response = await llm_client.chat(
            messages=[
                {"role": "system", "content": STRATEGY_DOC_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=600,
        )
        content = _string(response.get("content") or response.get("text") or "")
        if not content:
            raise ValueError("empty LLM response")

        # 解析四个部分
        sections = _parse_doc_sections(content)
        return {
            "strategy_id": _string(strategy.get("id")),
            "document_kind": "promotion_review_brief",
            "language": "zh-CN",
            "llm_generated": True,
            "fallback_used": False,
            "sections": sections,
            "backtest_summary": _format_backtest_metrics(backtest_metrics),
            "signal_summary": _format_signal_quality(signal_quality),
        }

    except Exception as exc:
        logger.debug("Strategy doc LLM generation failed, using fallback: %s", exc)
        return build_fallback_document(strategy, backtest_metrics, signal_quality)


def _parse_doc_sections(text: str) -> dict:
    """解析 LLM 输出为四个部分."""
    sections = {
        "principle": "",
        "market_regime": "",
        "risk_boundaries": "",
        "key_parameters": "",
    }
    current_key = None
    key_markers = {
        "策略原理": "principle",
        "适用市场环境": "market_regime",
        "主要风险": "risk_boundaries",
        "关键参数": "key_parameters",
    }

    for line in text.split("\n"):
        line_stripped = line.strip()
        if not line_stripped:
            continue

        matched = False
        for marker, key in key_markers.items():
            if marker in line_stripped:
                current_key = key
                content = line_stripped.replace(marker, "").strip().lstrip(":：").strip()
                if content:
                    sections[current_key] = content
                matched = True
                break

        if not matched and current_key:
            if sections[current_key]:
                sections[current_key] += "\n" + line_stripped
            else:
                sections[current_key] = line_stripped

    # 如果解析失败，把全文放入 principle
    if not any(sections.values()):
        sections["principle"] = text.strip()[:500]

    return sections
