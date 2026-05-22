
from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

from ..services.technical_analysis import TechnicalAnalysis as _TA
from ..services import pattern_recognition
from ..storage import get_db
from ..utils import fail, ok

from .key_levels import compute_key_levels
from .stop_levels import compute_stop_levels

logger = logging.getLogger(__name__)


# ── P0: 统一阈值常量 ──────────────────────────────────────────────

_RSI_OVERSOLD = 30
_RSI_OVERBOUGHT = 70
_RSI_NEUTRAL_LOW = 40
_RSI_NEUTRAL_HIGH = 60

# ── P3-5: A 股交易成本参数 ───────────────────────────────────────
_COMMISSION_RATE = 0.00025   # 佣金 万2.5（双向）
_STAMP_TAX_RATE = 0.0005     # 印花税 0.05%（仅卖出）
_TRANSFER_FEE_RATE = 0.00001 # 过户费 0.001%（双向）
_MIN_SLIPPAGE_RATE = 0.001   # 最低滑点 0.1%

# ── 信号判定 ──────────────────────────────────────────────────────


def _judge_trend(
    closes: list[float],
    macd_data: dict,
    ma20: list[float],
    ma60: list[float],
) -> dict:
    """主信号: 趋势方向判定。

    P1 增强: 加入 DIF/DEA 金叉死叉 + 均线斜率判断，减少 neutral。
    """
    if not closes or len(closes) < 60:
        return {"direction": "neutral", "name": "数据不足", "detail": "K 线不足 60 根"}

    current = closes[-1]
    ma20_val = ma20[-1] if ma20 and ma20[-1] > 0 else 0
    ma60_val = ma60[-1] if ma60 and ma60[-1] > 0 else 0

    # MACD 柱线
    macd_hist = macd_data.get("histogram", [])
    valid_hist = [h for h in (macd_hist or []) if h is not None]
    macd_positive = valid_hist[-1] > 0 if valid_hist else False
    macd_rising = (
        len(valid_hist) >= 2 and valid_hist[-1] > valid_hist[-2]
    ) if valid_hist else False

    # P1: DIF/DEA 金叉死叉
    dif = [v for v in (macd_data.get("macd", []) or []) if v is not None]
    dea = [v for v in (macd_data.get("signal", []) or []) if v is not None]
    golden_cross = False
    death_cross = False
    if len(dif) >= 2 and len(dea) >= 2:
        golden_cross = dif[-2] < dea[-2] and dif[-1] >= dea[-1]
        death_cross = dif[-2] > dea[-2] and dif[-1] <= dea[-1]

    # P1: 均线斜率 (5日变化率)
    ma20_slope = 0.0
    if len(ma20) >= 5 and ma20[-5] and ma20[-5] > 0:
        ma20_slope = (ma20[-1] - ma20[-5]) / ma20[-5] * 100

    # 均线排列
    bullish_alignment = current > ma20_val > ma60_val > 0
    bearish_alignment = 0 < current < ma20_val and ma20_val < ma60_val

    # ── 强趋势 ──
    if bullish_alignment and macd_positive:
        return {
            "direction": "bullish",
            "name": "MACD 多头 + 均线多头排列",
            "detail": f"收盘 {current:.2f} > MA20 {ma20_val:.2f} > MA60 {ma60_val:.2f}，MACD 柱线为正",
        }
    if bearish_alignment and not macd_positive:
        return {
            "direction": "bearish",
            "name": "MACD 空头 + 均线空头排列",
            "detail": f"收盘 {current:.2f} < MA20 {ma20_val:.2f} < MA60 {ma60_val:.2f}，MACD 柱线为负",
        }

    # ── P1: DIF/DEA 交叉信号（可以在均线不完全排列时给出方向） ──
    if golden_cross:
        return {
            "direction": "bullish_weak",
            "name": "MACD 金叉",
            "detail": f"DIF 上穿 DEA，MACD 柱线{'为正' if macd_positive else '即将转正'}，均线斜率 {ma20_slope:+.2f}%",
        }
    if death_cross:
        return {
            "direction": "bearish_weak",
            "name": "MACD 死叉",
            "detail": f"DIF 下穿 DEA，MACD 柱线{'为负' if not macd_positive else '即将转负'}，均线斜率 {ma20_slope:+.2f}%",
        }

    # ── 弱趋势 ──
    if macd_positive and macd_rising:
        return {
            "direction": "bullish_weak",
            "name": "MACD 转多但均线未确认",
            "detail": f"MACD 柱线为正且上升，MA20 斜率 {ma20_slope:+.2f}%",
        }
    if not macd_positive and not macd_rising:
        return {
            "direction": "bearish_weak",
            "name": "MACD 偏空且动能下降",
            "detail": f"MACD 柱线为负且下降，MA20 斜率 {ma20_slope:+.2f}%",
        }

    # ── P1: 用均线斜率和价格位置进一步判断，减少 neutral ──
    if ma20_slope > 0.5 and current > ma20_val:
        return {
            "direction": "bullish_weak",
            "name": "均线上升趋势",
            "detail": f"MA20 斜率 {ma20_slope:+.2f}%，价格在均线上方",
        }
    if ma20_slope < -0.5 and current < ma20_val:
        return {
            "direction": "bearish_weak",
            "name": "均线下降趋势",
            "detail": f"MA20 斜率 {ma20_slope:+.2f}%，价格在均线下方",
        }

    return {
        "direction": "neutral",
        "name": "趋势不明确",
        "detail": f"MACD 与均线信号矛盾，MA20 斜率 {ma20_slope:+.2f}%，方向不清",
    }


def _judge_trigger(
    rsi_value: float,
    current_price: float,
    levels: list[dict],
    patterns: list[dict],
) -> dict:
    """触发信号: 入场时机判定。P0: 使用统一 RSI 阈值常量。"""
    near_support = None
    for lv in levels:
        if lv["type"] == "support" and lv.get("strength", 0) >= 2:
            dist = abs(current_price - lv["price"]) / current_price
            if dist < 0.03:
                near_support = lv
                break

    near_resistance = None
    for lv in levels:
        if lv["type"] == "resistance" and lv.get("strength", 0) >= 2:
            dist = abs(current_price - lv["price"]) / current_price
            if dist < 0.03:
                near_resistance = lv
                break

    bullish_pattern = None
    for p in (patterns or []):
        if p.get("bullish") in (True, "True", "true") and p.get("reliability") in ("high", "medium"):
            bullish_pattern = p
            break

    rsi_oversold = rsi_value < _RSI_OVERSOLD
    rsi_overbought = rsi_value > _RSI_OVERBOUGHT
    rsi_neutral_low = _RSI_OVERSOLD <= rsi_value < _RSI_NEUTRAL_LOW

    if near_support and rsi_oversold:
        return {
            "status": "triggered",
            "name": f"RSI 超卖({rsi_value:.0f}) + 接近支撑位 {near_support['price']}",
            "action": "可入场",
        }
    if near_support and bullish_pattern:
        return {
            "status": "triggered",
            "name": f"支撑位 {near_support['price']} + {bullish_pattern.get('name', '看涨形态')}",
            "action": "可入场",
        }
    if rsi_oversold and bullish_pattern:
        return {
            "status": "triggered",
            "name": f"RSI 超卖({rsi_value:.0f}) + {bullish_pattern.get('name', '看涨形态')}",
            "action": "可入场",
        }

    if rsi_overbought and near_resistance:
        return {
            "status": "exit_signal",
            "name": f"RSI 超买({rsi_value:.0f}) + 接近阻力位 {near_resistance['price']}",
            "action": "不宜追涨，等回调",
        }
    if rsi_overbought:
        return {
            "status": "wait",
            "name": f"RSI 超买({rsi_value:.0f})，短期过热",
            "action": f"等 RSI 回落至 {_RSI_NEUTRAL_HIGH} 以下再考虑",
        }

    if near_support:
        return {
            "status": "near_ready",
            "name": f"接近支撑位 {near_support['price']}，等确认信号",
            "action": "关注 K 线形态或放量企稳",
        }

    if rsi_neutral_low:
        return {
            "status": "near_ready",
            "name": f"RSI 中性偏低({rsi_value:.0f})，可关注",
            "action": "等价格触及支撑位再入场",
        }

    return {
        "status": "wait",
        "name": f"RSI {rsi_value:.0f}，无明确触发条件",
        "action": "观望",
    }


def _judge_confirmation(fund_flow: dict | None, avg_volume_20: float, latest_volume: float) -> dict:
    """确认信号: 资金流/成交量。"""
    main_inflow = 0
    if fund_flow:
        main_inflow = float(fund_flow.get("mainNetInflow", 0) or 0)

    volume_ratio = latest_volume / avg_volume_20 if avg_volume_20 > 0 else 1.0

    if main_inflow > 0 and volume_ratio > 1.3:
        return {
            "status": "confirmed",
            "name": f"主力净流入 {main_inflow / 1e4:+.0f} 万 + 放量 (量比 {volume_ratio:.1f})",
        }
    if main_inflow > 0:
        return {
            "status": "confirmed",
            "name": f"主力净流入 {main_inflow / 1e4:+.0f} 万",
        }
    if volume_ratio > 1.5:
        return {
            "status": "partial",
            "name": f"放量 (量比 {volume_ratio:.1f}) 但主力方向不明",
        }
    if main_inflow < 0:
        return {
            "status": "unconfirmed",
            "name": f"主力净流出 {main_inflow / 1e4:+.0f} 万，信号减弱",
        }
    return {
        "status": "neutral",
        "name": "资金面无明确方向",
    }


def _compute_confidence(
    trend: dict,
    trigger: dict,
    confirm: dict,
    *,
    data_staleness_days: int = 0,
    calibration_factor: float = 1.0,
    kline_count: int = 250,
    historical_hit_rate: float | None = None,
    cross_validation: dict | None = None,
    num_scenarios: int = 3,
    num_levels: int = 0,
    num_conflicts: int = 0,
    closes: list[float] | None = None,
    macd_hist: list | None = None,
    rsi_value: float = 50.0,
    fund_flow_direction: str = "neutral",
) -> tuple[float, dict]:
    """策略可信度 0.0-1.0: 衡量本次策略分析的可靠程度，与市场方向无关。

    四维度评分:
        data_quality   (25%): 数据新鲜度、价格校准、数据完整性
        signal_clarity (30%): 信号一致性、信号强度、冲突数量
        validation     (25%): 交叉验证、历史命中率
        completeness   (20%): 场景覆盖、风控完整、关键价位
    """
    # ═══════════════════════════════════════════════
    # 维度1: 数据质量 (25%)
    # ═══════════════════════════════════════════════
    if data_staleness_days <= 3:
        freshness = 1.0
    elif data_staleness_days <= 7:
        freshness = 0.90
    elif data_staleness_days <= 14:
        freshness = 0.70
    elif data_staleness_days <= 30:
        freshness = 0.50
    else:
        freshness = 0.30

    cal_dev = abs(calibration_factor - 1.0)
    if cal_dev < 0.01:
        calibration = 1.0
    elif cal_dev < 0.02:
        calibration = 0.90
    elif cal_dev < 0.05:
        calibration = 0.70
    else:
        calibration = 0.40

    if kline_count >= 200:
        data_completeness = 1.0
    elif kline_count >= 120:
        data_completeness = 0.85
    elif kline_count >= 60:
        data_completeness = 0.65
    else:
        data_completeness = 0.40

    dq_score = (freshness + calibration + data_completeness) / 3.0

    # ═══════════════════════════════════════════════
    # 维度2: 信号清晰度 (30%) — 不看方向，只看是否清晰一致
    # ═══════════════════════════════════════════════

    # 收集各子信号的方向: +1=看多, -1=看空, 0=中性
    signal_dirs: list[int] = []

    # MACD 方向
    valid_hist = [h for h in (macd_hist or []) if h is not None]
    if valid_hist:
        signal_dirs.append(1 if valid_hist[-1] > 0 else -1)

    # 均线方向 (通过 trend 结果推断)
    td = trend["direction"]
    if td in ("bullish", "bullish_weak"):
        signal_dirs.append(1)
    elif td in ("bearish", "bearish_weak"):
        signal_dirs.append(-1)
    else:
        signal_dirs.append(0)

    # RSI 方向
    if rsi_value > 55:
        signal_dirs.append(1)
    elif rsi_value < 45:
        signal_dirs.append(-1)
    else:
        signal_dirs.append(0)

    # 资金流方向
    if fund_flow_direction == "bullish":
        signal_dirs.append(1)
    elif fund_flow_direction == "bearish":
        signal_dirs.append(-1)
    else:
        signal_dirs.append(0)

    # 一致性: 计算非零信号中多数方向占比
    non_zero = [d for d in signal_dirs if d != 0]
    if non_zero:
        majority = max(
            sum(1 for d in non_zero if d > 0),
            sum(1 for d in non_zero if d < 0),
        )
        consistency = majority / len(non_zero)
    else:
        consistency = 0.5

    # 信号强度: 趋势越清晰(无论多空)，强度越高
    strength_map = {
        "bullish": 1.0, "bearish": 1.0,
        "bullish_weak": 0.75, "bearish_weak": 0.75,
        "neutral": 0.40,
    }
    trend_strength = strength_map.get(td, 0.40)

    trigger_strength_map = {
        "triggered": 1.0, "near_ready": 0.75,
        "wait": 0.50, "exit_signal": 0.80,
    }
    ts = trigger["status"]
    trig_strength = trigger_strength_map.get(ts, 0.50)

    signal_strength = (trend_strength + trig_strength) / 2.0

    # 冲突惩罚
    if num_conflicts == 0:
        conflict_free = 1.0
    elif num_conflicts == 1:
        conflict_free = 0.80
    elif num_conflicts == 2:
        conflict_free = 0.60
    else:
        conflict_free = 0.40

    sc_score = (consistency + signal_strength + conflict_free) / 3.0

    # ═══════════════════════════════════════════════
    # 维度3: 验证得分 (25%)
    # ═══════════════════════════════════════════════

    # 交叉验证一致性
    if cross_validation:
        cv_rec = cross_validation.get("recommendation", "")
        cv_dir = "buy" if cv_rec == "buy" else "sell" if cv_rec == "sell" else "hold"
        plan_dir = (
            "buy" if td in ("bullish", "bullish_weak")
            else "sell" if td in ("bearish", "bearish_weak")
            else "hold"
        )
        if cv_dir == plan_dir:
            cross_val_score = 1.0
        elif cv_dir == "hold" or plan_dir == "hold":
            cross_val_score = 0.75
        else:
            cross_val_score = 0.40
    else:
        cross_val_score = 0.50

    # 历史命中率
    if historical_hit_rate is not None:
        if historical_hit_rate >= 0.60:
            hit_rate_score = 1.0
        elif historical_hit_rate >= 0.50:
            hit_rate_score = 0.85
        elif historical_hit_rate >= 0.40:
            hit_rate_score = 0.70
        else:
            hit_rate_score = 0.50
    else:
        hit_rate_score = 0.50

    vd_score = (cross_val_score + hit_rate_score) / 2.0

    # P3: 信号稳定性和衰减度可在外部修正 vd_score（通过返回的 breakdown 触发）

    # ═══════════════════════════════════════════════
    # 维度4: 分析完整性 (20%)
    # ═══════════════════════════════════════════════
    scenario_score = 1.0 if num_scenarios >= 3 else (0.70 if num_scenarios >= 2 else 0.40)
    level_score = 1.0 if num_levels >= 4 else (0.70 if num_levels >= 2 else 0.40)
    cp_score = (scenario_score + level_score) / 2.0

    # ═══════════════════════════════════════════════
    # 加权合成
    # ═══════════════════════════════════════════════
    W_DQ, W_SC, W_VD, W_CP = 0.25, 0.30, 0.25, 0.20
    final = dq_score * W_DQ + sc_score * W_SC + vd_score * W_VD + cp_score * W_CP
    final = round(min(1.0, max(0.0, final)), 2)

    breakdown = {
        "data_quality": {
            "score": round(dq_score, 2),
            "freshness": freshness,
            "calibration": calibration,
            "completeness": data_completeness,
            "staleness_days": data_staleness_days,
        },
        "signal_clarity": {
            "score": round(sc_score, 2),
            "consistency": round(consistency, 2),
            "strength": round(signal_strength, 2),
            "conflict_free": conflict_free,
            "signal_directions": signal_dirs,
        },
        "validation": {
            "score": round(vd_score, 2),
            "cross_validation": round(cross_val_score, 2),
            "historical_hit_rate": historical_hit_rate,
            "hit_rate_score": hit_rate_score,
        },
        "completeness": {
            "score": round(cp_score, 2),
            "scenarios": scenario_score,
            "levels": level_score,
        },
        "weights": {"data_quality": W_DQ, "signal_clarity": W_SC, "validation": W_VD, "completeness": W_CP},
        "final": final,
    }

    return final, breakdown


def _determine_direction(trend: dict, trigger: dict, confidence: float) -> str:
    """最终方向判定。"""
    td = trend["direction"]
    ts = trigger["status"]

    if ts == "exit_signal":
        return "wait_pullback"
    if td in ("bullish", "bullish_weak") and ts == "triggered":
        return "buy"
    if td in ("bullish", "bullish_weak") and ts in ("wait",):
        return "wait_pullback"
    if td in ("bearish", "bearish_weak"):
        return "avoid"
    if ts == "near_ready":
        return "watch"
    return "wait"


def _determine_regime(closes: list[float]) -> str:
    """简单市场环境判定（向后兼容）。P3 新增 _detect_regime_advanced 提供细粒度。"""
    if len(closes) < 20:
        return "未知"
    ret_20 = (closes[-1] - closes[-20]) / closes[-20]
    if ret_20 > 0.05:
        return "偏多"
    if ret_20 < -0.05:
        return "偏空"
    return "震荡"
