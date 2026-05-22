

# ── P3-1: 凯利公式仓位管理 ─────────────────────────────────────


def _kelly_position_sizing(
    hit_rate: float,
    avg_win: float,
    avg_loss: float,
    capital: float,
    entry_price: float,
    fraction: float = 0.5,
    max_position_pct: float = 0.30,
) -> dict:
    """用分数凯利公式计算最优仓位。

    f* = (b*p - q) / b，其中 b = avg_win / avg_loss, p = 胜率, q = 1-p。
    实战使用 fraction (默认 ½ Kelly) 降低波动风险。
    """
    if avg_loss <= 0 or hit_rate <= 0 or entry_price <= 0:
        return {"kelly_raw": 0, "kelly_adjusted": 0, "kelly_shares": 0,
                "method": "数据不足", "applicable": False}

    b = avg_win / avg_loss
    q = 1 - hit_rate
    kelly_pct = (b * hit_rate - q) / b

    if kelly_pct <= 0:
        return {"kelly_raw": round(kelly_pct, 4), "kelly_adjusted": 0,
                "kelly_shares": 0, "method": "Kelly 为负，不建议建仓",
                "applicable": False}

    adj_pct = min(kelly_pct * fraction, max_position_pct)
    amount = capital * adj_pct
    shares = (math.floor(amount / entry_price) // 100) * 100

    return {
        "kelly_raw": round(kelly_pct, 4),
        "kelly_adjusted": round(adj_pct, 4),
        "kelly_shares": shares,
        "method": f"{fraction:.0%} Kelly",
        "win_loss_ratio": round(b, 2),
        "note": f"基于胜率{hit_rate:.0%}、盈亏比{b:.2f}计算",
        "applicable": True,
    }


# ── P3-2: 多维度市场状态检测 ───────────────────────────────────


def _detect_regime_advanced(
    closes: list[float], volumes: list[float],
) -> dict:
    """三维分类矩阵: 动量×波动率×量能。

    输出 6 种细粒度状态替代原始的"偏多/偏空/震荡"。
    """
    if len(closes) < 30 or len(volumes) < 20:
        return {"regime": "unknown", "momentum": 0, "volatility": 0,
                "volume_trend": 0, "label": "数据不足"}

    # 维度1: 动量 — 30 日收益率
    ret_30 = (closes[-1] - closes[-30]) / closes[-30] * 100

    # 维度2: 波动率 — 20 日年化波动率
    daily_ret = np.diff(closes[-21:]) / np.array(closes[-21:-1])
    vol_ann = float(np.std(daily_ret) * np.sqrt(250) * 100)

    # 维度3: 量能趋势 — 5 日均量 vs 20 日均量
    avg_vol_5 = float(np.mean(volumes[-5:]))
    avg_vol_20 = float(np.mean(volumes[-20:]))
    vol_trend = ((avg_vol_5 - avg_vol_20) / avg_vol_20 * 100) if avg_vol_20 > 0 else 0

    # 分类
    is_volatile = vol_ann > 30
    if ret_30 > 5:
        regime = "bull_volatile" if is_volatile else "bull_calm"
    elif ret_30 < -5:
        regime = "bear_volatile" if is_volatile else "bear_calm"
    else:
        regime = "range_volatile" if is_volatile else "range_calm"

    # 量能标签
    if vol_trend > 30:
        volume_label = "放量"
    elif vol_trend < -30:
        volume_label = "缩量"
    else:
        volume_label = "正常"

    _REGIME_LABELS = {
        "bull_calm": "温和上涨",
        "bull_volatile": "剧烈上涨",
        "bear_calm": "温和下跌",
        "bear_volatile": "剧烈下跌",
        "range_calm": "低波震荡",
        "range_volatile": "高波震荡",
    }

    return {
        "regime": regime,
        "label": _REGIME_LABELS.get(regime, regime),
        "momentum_30d": round(ret_30, 2),
        "volatility_ann": round(vol_ann, 2),
        "volume_trend": round(vol_trend, 2),
        "volume_label": volume_label,
    }


def _regime_adjusted_params(regime: str) -> dict:
    """根据市场状态调整策略参数。"""
    defaults = {"max_position_pct": 0.30, "atr_multiplier": 2.0, "risk_per_trade": 0.02}
    adjustments = {
        "bull_calm":     {"max_position_pct": 0.30, "atr_multiplier": 2.0, "risk_per_trade": 0.02},
        "bull_volatile": {"max_position_pct": 0.20, "atr_multiplier": 2.5, "risk_per_trade": 0.015},
        "bear_calm":     {"max_position_pct": 0.15, "atr_multiplier": 1.5, "risk_per_trade": 0.01},
        "bear_volatile": {"max_position_pct": 0.10, "atr_multiplier": 3.0, "risk_per_trade": 0.01},
        "range_calm":    {"max_position_pct": 0.25, "atr_multiplier": 2.0, "risk_per_trade": 0.02},
        "range_volatile":{"max_position_pct": 0.20, "atr_multiplier": 2.5, "risk_per_trade": 0.015},
    }
    return adjustments.get(regime, defaults)


# ── P3-3: 滚动窗口验证（WFA Lite）─────────────────────────────


def _rolling_window_validation(
    closes: list[float], signal: str, klines: list[dict], window_size: int = 50,
) -> dict | None:
    """将数据分为多个窗口，验证信号在不同时期的稳定性。"""
    try:
        from ..services.data_pipeline.condition_stats import compute_signal_hit_rate

        n = len(klines)
        if n < window_size * 2:
            return None

        window_results = []
        for start in range(0, n - window_size + 1, window_size):
            end = start + window_size
            window_klines = klines[start:end]
            if len(window_klines) < 30:
                continue
            report = compute_signal_hit_rate(window_klines, signal=signal, forward_days=[10])
            r10 = report.get("forward_returns", {}).get("10d", {})
            if r10.get("samples", 0) >= 3 and r10.get("hit_rate") is not None:
                window_results.append(float(r10["hit_rate"]))

        if len(window_results) < 2:
            return None

        stability = round(1.0 - float(np.std(window_results)), 3)
        mean_hr = round(float(np.mean(window_results)), 3)

        if stability >= 0.85:
            verdict = "非常稳定"
        elif stability >= 0.70:
            verdict = "稳定"
        elif stability >= 0.55:
            verdict = "一般"
        else:
            verdict = "不稳定（过拟合风险）"

        return {
            "windows": len(window_results),
            "hit_rates": [round(r, 3) for r in window_results],
            "stability": stability,
            "mean_hit_rate": mean_hr,
            "verdict": verdict,
        }
    except Exception as e:
        logger.debug("滚动窗口验证失败: %s", e)
    return None


# ── P3-4: 信号衰减检测 ────────────────────────────────────────


def _detect_signal_decay(
    klines: list[dict], signal: str, recent_window: int = 60,
) -> dict | None:
    """对比近期 vs 全样本的信号命中率，检测信号是否衰减。"""
    try:
        from ..services.data_pipeline.condition_stats import compute_signal_hit_rate

        if len(klines) < recent_window + 30:
            return None

        full_report = compute_signal_hit_rate(klines, signal=signal, forward_days=[10])
        recent_report = compute_signal_hit_rate(klines[-recent_window:], signal=signal, forward_days=[10])

        full_r10 = full_report.get("forward_returns", {}).get("10d", {})
        recent_r10 = recent_report.get("forward_returns", {}).get("10d", {})

        full_hr = full_r10.get("hit_rate")
        recent_hr = recent_r10.get("hit_rate")
        full_samples = full_r10.get("samples", 0)
        recent_samples = recent_r10.get("samples", 0)

        if full_hr is None or full_hr <= 0 or full_samples < 5:
            return None

        decay_ratio = round(recent_hr / full_hr, 3) if recent_hr is not None else 0

        warning = None
        if decay_ratio < 0.5:
            warning = f"信号严重衰减：近{recent_window}日命中率仅为历史的{decay_ratio:.0%}，建议降低仓位或切换信号"
        elif decay_ratio < 0.7:
            warning = f"信号有所衰减：近{recent_window}日命中率下降{(1 - decay_ratio):.0%}，需谨慎"

        return {
            "full_sample_hr": full_hr,
            "full_sample_n": full_samples,
            "recent_hr": recent_hr,
            "recent_n": recent_samples,
            "decay_ratio": decay_ratio,
            "warning": warning,
        }
    except Exception as e:
        logger.debug("信号衰减检测失败: %s", e)
    return None


# ── P3-5: A 股交易成本建模 ────────────────────────────────────


def _calc_trading_costs(
    entry_price: float,
    exit_price: float,
    shares: int,
    atr_14: float = 0,
) -> dict:
    """计算 A 股单次完整交易（买入+卖出）的全部成本。"""
    if shares <= 0 or entry_price <= 0:
        return {"total_cost": 0, "cost_pct": 0, "gross_pnl": 0, "net_pnl": 0}

    slippage_rate = max(_MIN_SLIPPAGE_RATE, (atr_14 * 0.1 / entry_price) if atr_14 > 0 and entry_price > 0 else _MIN_SLIPPAGE_RATE)

    buy_amount = entry_price * shares
    sell_amount = exit_price * shares

    buy_commission = buy_amount * _COMMISSION_RATE
    buy_transfer = buy_amount * _TRANSFER_FEE_RATE
    buy_slippage = buy_amount * slippage_rate

    sell_commission = sell_amount * _COMMISSION_RATE
    sell_stamp_tax = sell_amount * _STAMP_TAX_RATE
    sell_transfer = sell_amount * _TRANSFER_FEE_RATE
    sell_slippage = sell_amount * slippage_rate

    total_cost = (buy_commission + buy_transfer + buy_slippage
                  + sell_commission + sell_stamp_tax + sell_transfer + sell_slippage)

    gross_pnl = (exit_price - entry_price) * shares
    net_pnl = gross_pnl - total_cost

    return {
        "total_cost": round(total_cost, 2),
        "cost_pct": round(total_cost / buy_amount * 100, 3) if buy_amount > 0 else 0,
        "gross_pnl": round(gross_pnl, 2),
        "net_pnl": round(net_pnl, 2),
        "breakdown": {
            "buy_cost": round(buy_commission + buy_transfer + buy_slippage, 2),
            "sell_cost": round(sell_commission + sell_stamp_tax + sell_transfer + sell_slippage, 2),
            "slippage_rate": round(slippage_rate * 100, 3),
        },
    }


async def _cross_validate_signal(code: str, capital: float) -> dict | None:
    """交叉验证: 调用 should_i_buy 获取独立判断。"""
    try:
        from ._decision_buy import should_i_buy

        result = await should_i_buy(code=code, investment_style="balanced")
        if isinstance(result, dict) and result.get("success"):
            d = result.get("data", {})
            return {
                "recommendation": d.get("recommendation"),
                "buy_probability": d.get("decision_probability", {}).get("buy_probability"),
                "score": d.get("score"),
                "confidence": d.get("confidence"),
            }
    except Exception as e:
        logger.debug("交叉验证失败: %s", e)
    return None


async def _get_realtime_price(code: str) -> float | None:
    """安全获取实时价格用于价格校准。"""
    try:
        from ...services.market_data_access import FALLBACK_DB_ONLY, get_quote_snapshot_response
        rt = await get_quote_snapshot_response(code, fallback_mode=FALLBACK_DB_ONLY)
        if isinstance(rt, dict) and rt.get("success"):
            p = float(rt.get("data", {}).get("price", 0))
            return p if p > 0 else None
    except Exception:
        return None
