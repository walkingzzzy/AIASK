

# ── 场景生成 ──────────────────────────────────────────────────────


def _estimate_scenario_probabilities(
    closes: list[float],
    current_price: float,
    supports: list[dict],
    resistances: list[dict],
    atr_14: float,
) -> dict[str, float]:
    """P1: 用历史数据估算场景概率，替代硬编码常数。"""
    if len(closes) < 60:
        return {"pullback": 0.40, "breakout": 0.25, "deep_pullback": 0.20}

    # 统计历史上价格触及支撑/阻力后的表现
    n = len(closes)
    pullback_count = 0
    breakout_count = 0
    deep_drop_count = 0
    total_windows = 0

    sup_price = supports[0]["price"] if supports else current_price * 0.97
    res_price = resistances[0]["price"] if resistances else current_price * 1.03
    deep_sup = supports[1]["price"] if len(supports) >= 2 else current_price * 0.95

    for i in range(max(60, n - 120), n - 5):
        c = closes[i]
        future_5d = closes[i + 1: i + 6]
        if not future_5d:
            continue
        total_windows += 1
        future_max = max(future_5d)
        future_min = min(future_5d)

        dist_to_sup = (c - sup_price) / c if c > 0 else 0.1
        dist_to_res = (res_price - c) / c if c > 0 else 0.1

        if dist_to_sup < 0.03 and future_max > c:
            pullback_count += 1
        if future_max > res_price and dist_to_res < 0.08:
            breakout_count += 1
        if future_min < deep_sup:
            deep_drop_count += 1

    if total_windows > 0:
        p_pull = round(max(0.15, min(0.60, pullback_count / total_windows)), 2)
        p_break = round(max(0.10, min(0.45, breakout_count / total_windows)), 2)
        p_deep = round(max(0.05, min(0.35, deep_drop_count / total_windows)), 2)
    else:
        p_pull, p_break, p_deep = 0.40, 0.25, 0.20

    # ATR 适应：高波动时降低突破概率（假突破多），提升深度回调概率
    atr_pct = atr_14 / current_price if current_price > 0 else 0.03
    if atr_pct > 0.05:
        p_break = round(p_break * 0.8, 2)
        p_deep = round(min(0.35, p_deep * 1.2), 2)

    return {"pullback": p_pull, "breakout": p_break, "deep_pullback": p_deep}


async def _build_scenario_with_stop(
    code: str,
    entry_price: float,
    capital: float,
    risk_per_trade: float,
    atr_14: float,
    klines: list[dict] | None,
    levels: list[dict] | None,
    max_position_pct: float = 0.30,
    hit_rate_detail: dict | None = None,
) -> tuple[dict, dict, dict, dict | None]:
    """P0+P3: 统一止损/止盈/仓位计算 + 凯利公式辅助仓位建议。"""
    stop_result = await compute_stop_levels(
        code, entry_price, capital=capital, risk_per_trade=risk_per_trade,
        klines=klines, levels=levels,
    )
    sl_data = stop_result.get("data", {}) if stop_result.get("success") else {}
    sl_info = sl_data.get("stop_loss", {})
    tp_info = sl_data.get("take_profit", {})
    pos_info = sl_data.get("position_sizing", {})

    stop_price = sl_info.get("recommended", round(entry_price - atr_14 * 2, 2))
    risk_per_share = abs(entry_price - stop_price)
    if risk_per_share < 0.01:
        risk_per_share = atr_14 * 2

    shares = pos_info.get("max_shares", 0)
    if not shares and capital > 0 and risk_per_share > 0:
        risk_budget = capital * risk_per_trade
        shares = min(
            (math.floor(risk_budget / risk_per_share) // 100) * 100,
            (math.floor(capital * max_position_pct / entry_price) // 100) * 100,
        )

    method = sl_info.get("method", f"ATR(14)×2 = {round(atr_14 * 2, 2)}")

    # P3-1: 凯利公式辅助仓位
    kelly = None
    if hit_rate_detail:
        hp = hit_rate_detail.get("by_holding_period", {}).get("10d", {})
        hr = hp.get("hit_rate")
        avg_return = hp.get("avg_return")
        if hr is not None and avg_return is not None and hr > 0:
            avg_win = abs(avg_return) if avg_return > 0 else abs(avg_return) * 1.5
            avg_loss = risk_per_share / entry_price if entry_price > 0 else 0.03
            kelly = _kelly_position_sizing(hr, avg_win, avg_loss, capital, entry_price, 0.5, max_position_pct)
            if kelly.get("applicable") and kelly["kelly_shares"] > 0:
                shares = min(shares, kelly["kelly_shares"])

    return (
        {"price": stop_price, "method": method, "risk_per_share": risk_per_share},
        {"tp_2x": tp_info.get("tp_2x"), "tp_3x": tp_info.get("tp_3x")},
        {"shares": shares, "position_pct": pos_info.get("position_pct", round(shares * entry_price / capital * 100, 2) if shares and capital else 0)},
        kelly,
    )


async def _build_scenarios(
    code: str,
    current_price: float,
    levels: list[dict],
    capital: float,
    risk_per_trade: float,
    direction: str,
    atr_14: float,
    klines: list[dict] | None = None,
    closes: list[float] | None = None,
    hit_rate_detail: dict | None = None,
) -> list[dict]:
    """P0+P1+P3: 场景化入场方案 — 统一止损 + 数据驱动概率 + 凯利仓位 + 交易成本。"""
    scenarios = []

    supports = sorted(
        [lv for lv in levels if lv["type"] == "support" and lv["price"] < current_price],
        key=lambda x: x["price"],
        reverse=True,
    )
    resistances = sorted(
        [lv for lv in levels if lv["type"] == "resistance" and lv["price"] > current_price],
        key=lambda x: x["price"],
    )

    # P1: 数据驱动概率
    probs = _estimate_scenario_probabilities(
        closes or [], current_price, supports, resistances, atr_14,
    )

    # ── 场景 A: 回调至最近支撑位买入 ──
    if supports and direction in ("wait_pullback", "watch", "buy"):
        target_support = supports[0]
        entry = target_support["price"]

        sl, tp, pos, kelly = await _build_scenario_with_stop(
            code, entry, capital, risk_per_trade, atr_14, klines, levels, 0.30,
            hit_rate_detail=hit_rate_detail,
        )
        risk_per_share = sl["risk_per_share"]
        shares = pos["shares"]

        tp1 = resistances[0]["price"] if resistances else (tp["tp_2x"] or round(entry * 1.10, 2))
        tp2 = resistances[1]["price"] if len(resistances) > 1 else (tp["tp_3x"] or round(entry * 1.15, 2))
        rr1 = round(max(0, (tp1 - entry) / risk_per_share), 2) if risk_per_share > 0 else 0
        rr2 = round(max(0, (tp2 - entry) / risk_per_share), 2) if risk_per_share > 0 else 0

        # P3-5: 交易成本
        costs_tp1 = _calc_trading_costs(entry, tp1, shares, atr_14)
        costs_sl = _calc_trading_costs(entry, sl["price"], shares, atr_14)

        scenario = {
            "id": "A",
            "name": "回调买入（推荐）",
            "probability": probs["pullback"],
            "probability_source": "历史统计",
            "condition": f"价格回调至 {entry} 附近 ({', '.join(target_support.get('sources', [])[:3])})",
            "entry": {"price": entry, "shares": shares, "amount": round(shares * entry, 2) if shares else 0, "position_pct": pos["position_pct"]},
            "stop_loss": {"price": sl["price"], "method": sl["method"], "max_loss": round(shares * risk_per_share, 2) if shares else 0, "max_loss_pct": round(shares * risk_per_share / capital * 100, 2) if shares and capital else 0},
            "take_profit": [
                {"price": tp1, "action": "减仓 50%", "reason": "阻力位", "rr_ratio": rr1},
                {"price": tp2, "action": "清仓", "reason": "上方阻力位", "rr_ratio": rr2},
            ],
            "if_wrong": target_support.get("breach_action", f"跌破 {sl['price']} 止损离场"),
            "trading_costs": {
                "tp1_net_pnl": costs_tp1["net_pnl"], "tp1_cost": costs_tp1["total_cost"],
                "sl_net_pnl": costs_sl["net_pnl"], "sl_cost": costs_sl["total_cost"],
                "roundtrip_cost_pct": costs_tp1["cost_pct"],
            },
        }
        if kelly:
            scenario["kelly_sizing"] = kelly
        scenarios.append(scenario)

    # ── 场景 B: 强势突破最近阻力位 ──
    if resistances and direction in ("wait_pullback", "watch", "buy"):
        target_res = resistances[0]
        entry = round(target_res["price"] + atr_14 * 0.1, 2)

        sl, tp, pos, kelly = await _build_scenario_with_stop(
            code, entry, capital, risk_per_trade, atr_14, klines, levels, 0.25,
            hit_rate_detail=hit_rate_detail,
        )
        risk_per_share = sl["risk_per_share"]
        shares = pos["shares"]

        tp1 = resistances[1]["price"] if len(resistances) > 1 else (tp["tp_2x"] or round(entry * 1.08, 2))
        tp2 = tp["tp_3x"] or round(entry * 1.15, 2)
        rr1 = round(max(0, (tp1 - entry) / risk_per_share), 2) if risk_per_share > 0 else 0
        rr2 = round(max(0, (tp2 - entry) / risk_per_share), 2) if risk_per_share > 0 else 0

        costs_tp1 = _calc_trading_costs(entry, tp1, shares, atr_14)
        costs_sl = _calc_trading_costs(entry, sl["price"], shares, atr_14)

        scenario = {
            "id": "B",
            "name": "强势突破追涨",
            "probability": probs["breakout"],
            "probability_source": "历史统计",
            "condition": f"放量突破 {target_res['price']}（{target_res.get('confirmation', '需放量确认')}）",
            "entry": {"price": entry, "shares": shares, "amount": round(shares * entry, 2) if shares else 0, "position_pct": pos["position_pct"]},
            "stop_loss": {"price": sl["price"], "method": sl["method"], "max_loss": round(shares * risk_per_share, 2) if shares else 0, "max_loss_pct": round(shares * risk_per_share / capital * 100, 2) if shares and capital else 0},
            "take_profit": [
                {"price": tp1, "action": "减仓 50%", "reason": "上方阻力位", "rr_ratio": rr1},
                {"price": tp2, "action": "清仓", "reason": "趋势目标位", "rr_ratio": rr2},
            ],
            "if_wrong": target_res.get("breach_action", f"跌回 {sl['price']} 下方止损"),
            "trading_costs": {
                "tp1_net_pnl": costs_tp1["net_pnl"], "tp1_cost": costs_tp1["total_cost"],
                "sl_net_pnl": costs_sl["net_pnl"], "sl_cost": costs_sl["total_cost"],
                "roundtrip_cost_pct": costs_tp1["cost_pct"],
            },
        }
        if kelly:
            scenario["kelly_sizing"] = kelly
        scenarios.append(scenario)

    # ── 场景 C: 深度回调至更低支撑 ──
    if len(supports) >= 2 and direction in ("wait_pullback", "watch", "buy", "avoid"):
        deep_support = supports[1]
        entry = deep_support["price"]

        sl, tp, pos, kelly = await _build_scenario_with_stop(
            code, entry, capital, risk_per_trade, atr_14, klines, levels, 0.20,
            hit_rate_detail=hit_rate_detail,
        )
        risk_per_share = sl["risk_per_share"]
        shares = pos["shares"]

        tp1 = supports[0]["price"] if supports else (tp["tp_2x"] or round(entry * 1.08, 2))
        tp2_price = resistances[0]["price"] if resistances else round(current_price * 1.05, 2)
        rr1 = round(max(0, (tp1 - entry) / risk_per_share), 2) if risk_per_share > 0 else 0
        rr2 = round(max(0, (tp2_price - entry) / risk_per_share), 2) if risk_per_share > 0 else 0

        costs_tp1 = _calc_trading_costs(entry, tp1, shares, atr_14)
        costs_sl = _calc_trading_costs(entry, sl["price"], shares, atr_14)

        scenario = {
            "id": "C",
            "name": "深度回调抄底",
            "probability": probs["deep_pullback"],
            "probability_source": "历史统计",
            "condition": f"跌至 {entry} 附近且缩量企稳 ({', '.join(deep_support.get('sources', [])[:2])})",
            "entry": {"price": entry, "shares": shares, "amount": round(shares * entry, 2) if shares else 0, "position_pct": pos["position_pct"]},
            "stop_loss": {"price": sl["price"], "method": sl["method"], "max_loss": round(shares * risk_per_share, 2) if shares else 0, "max_loss_pct": round(shares * risk_per_share / capital * 100, 2) if shares and capital else 0},
            "take_profit": [
                {"price": tp1, "action": "减仓 50%", "reason": "反弹至上方支撑", "rr_ratio": rr1},
                {"price": tp2_price, "action": "清仓", "reason": "反弹至首个阻力位", "rr_ratio": rr2},
            ],
            "if_wrong": deep_support.get("breach_action", f"跌破 {sl['price']} 止损离场"),
            "trading_costs": {
                "tp1_net_pnl": costs_tp1["net_pnl"], "tp1_cost": costs_tp1["total_cost"],
                "sl_net_pnl": costs_sl["net_pnl"], "sl_cost": costs_sl["total_cost"],
                "roundtrip_cost_pct": costs_tp1["cost_pct"],
            },
        }
        if kelly:
            scenario["kelly_sizing"] = kelly
        scenarios.append(scenario)

    return scenarios


# ── 主入口 ────────────────────────────────────────────────────────


async def _get_fund_flow_safe(code: str) -> dict | None:
    """安全获取资金流数据。"""
    try:
        import asyncio
        from .fund_flow import get_stock_fund_flow
        result = await asyncio.to_thread(get_stock_fund_flow, code)
        if isinstance(result, dict) and result.get("success"):
            return result.get("data")
    except Exception:
        pass
    return None


def _normalize_price(price: float, factor: float) -> float:
    """将复权价转换为实际市场价格。"""
    return round(price * factor, 2)


def _normalize_output(result: dict, factor: float) -> dict:
    """对整个输出结构中的绝对价格字段应用归一化因子，并重算仓位。"""
    if abs(factor - 1.0) < 0.005:
        return result

    cap = result.get("position_management", {}).get("_capital", 0)
    risk_pct = result.get("position_management", {}).get("max_loss_per_trade_pct", 2.0) / 100
    max_pos_pct = result.get("position_management", {}).get("max_position_pct", 30) / 100

    result["current_price"] = _normalize_price(result["current_price"], factor)

    for lv in result.get("key_levels", []):
        old_price = lv["price"]
        lv["price"] = _normalize_price(old_price, factor)
        for field in ("confirmation", "breach_action"):
            if field in lv and isinstance(lv[field], str):
                lv[field] = _replace_prices_in_text(lv[field], factor)

    for sc in result.get("scenarios", []):
        entry = sc.get("entry", {})
        sl = sc.get("stop_loss", {})

        if "price" in entry:
            entry["price"] = _normalize_price(entry["price"], factor)
        if "price" in sl:
            sl["price"] = _normalize_price(sl["price"], factor)

        e_price = entry.get("price", 0)
        s_price = sl.get("price", 0)
        risk_per_share = abs(e_price - s_price) if e_price and s_price else 0

        if cap > 0 and e_price > 0 and risk_per_share > 0:
            risk_budget = cap * risk_pct
            by_risk = math.floor(risk_budget / risk_per_share)
            by_cap = math.floor(cap * max_pos_pct / e_price)
            shares = min(by_risk, by_cap)
            shares = (shares // 100) * 100
            entry["shares"] = shares
            entry["amount"] = round(shares * e_price, 2)
            entry["position_pct"] = round(entry["amount"] / cap * 100, 2)
            sl["max_loss"] = round(shares * risk_per_share, 2)
            sl["max_loss_pct"] = round(sl["max_loss"] / cap * 100, 2)

        for tp in sc.get("take_profit", []):
            if "price" in tp:
                tp["price"] = _normalize_price(tp["price"], factor)
                if risk_per_share > 0 and e_price > 0:
                    tp["rr_ratio"] = round(abs(tp["price"] - e_price) / risk_per_share, 2)

        if "if_wrong" in sc and isinstance(sc["if_wrong"], str):
            sc["if_wrong"] = _replace_prices_in_text(sc["if_wrong"], factor)
        if "condition" in sc and isinstance(sc["condition"], str):
            sc["condition"] = _replace_prices_in_text(sc["condition"], factor)

    snap = result.get("indicators_snapshot", {})
    for f in ("ma20", "ma60", "atr_14"):
        if snap.get(f) is not None:
            snap[f] = _normalize_price(snap[f], factor)

    return result


def _replace_prices_in_text(text: str, factor: float) -> str:
    """替换文本中出现的价格数字（>10 的浮点数）为归一化后的值。"""
    import re
    def _repl(m):
        val = float(m.group(0))
        if val > 10:
            return f"{val * factor:.2f}"
        return m.group(0)
    return re.sub(r'\d+\.\d+', _repl, text)


def _select_signal_name(rsi_value: float, macd_hist: list) -> str:
    """根据当前指标状态选择最匹配的历史信号名。"""
    valid_hist = [h for h in (macd_hist or []) if h is not None]
    macd_positive = valid_hist[-1] > 0 if valid_hist else False

    if rsi_value < _RSI_OVERSOLD and macd_positive:
        return "rsi_oversold_and_macd_golden"
    if rsi_value < _RSI_OVERSOLD:
        return "rsi_oversold"
    if macd_positive:
        return "ma_bullish_alignment"
    return "ma_bearish_alignment"


async def _get_historical_hit_rate(
    code: str, rsi_value: float, macd_hist: list,
) -> float | None:
    """尝试获取当前信号组合的 10 日历史胜率。"""
    try:
        from ..services.data_pipeline.condition_stats import compute_signal_hit_rate

        db = get_db()
        klines = await db.get_klines(code, limit=500)
        if not klines or len(klines) < 60:
            return None

        signal = _select_signal_name(rsi_value, macd_hist)
        report = compute_signal_hit_rate(klines, signal=signal, forward_days=[5, 10, 20])
        r10 = report.get("forward_returns", {}).get("10d", {})
        if r10.get("reliable") and r10.get("hit_rate") is not None:
            return float(r10["hit_rate"])
    except Exception as e:
        logger.debug("历史胜率获取失败: %s", e)
    return None


async def _get_hit_rate_detail(
    code: str, rsi_value: float, macd_hist: list,
) -> dict | None:
    """P1: 深化信号命中率 — 分持有期、平均收益、regime 分层。"""
    try:
        from ..services.data_pipeline.condition_stats import compute_signal_hit_rate

        db = get_db()
        klines = await db.get_klines(code, limit=500)
        if not klines or len(klines) < 60:
            return None

        signal = _select_signal_name(rsi_value, macd_hist)
        report = compute_signal_hit_rate(klines, signal=signal, forward_days=[5, 10, 20])

        detail = {
            "signal": signal,
            "sample_count": report.get("sample_count", 0),
            "by_holding_period": {},
            "by_regime": {},
        }

        for fd_key, stats in report.get("forward_returns", {}).items():
            detail["by_holding_period"][fd_key] = {
                "hit_rate": stats.get("hit_rate"),
                "avg_return": stats.get("avg_return"),
                "samples": stats.get("samples", 0),
                "reliable": stats.get("reliable", False),
            }

        for regime, buckets in report.get("by_regime", {}).items():
            regime_summary = {}
            for fd_key, stats in buckets.items():
                regime_summary[fd_key] = {
                    "hit_rate": stats.get("hit_rate"),
                    "avg_return": stats.get("avg_return"),
                    "samples": stats.get("samples", 0),
                }
            detail["by_regime"][regime] = regime_summary

        return detail if detail["sample_count"] > 0 else None
    except Exception as e:
        logger.debug("命中率详情获取失败: %s", e)
    return None


# ── P2: 量化增强辅助函数 ──────────────────────────────────────────


async def _get_similar_patterns(code: str, klines: list[dict]) -> dict | None:
    """P2: 调用相似形态分析，获取历史相似走势后的收益分布。"""
    try:
        from .quant import _build_similar_pattern_report
        report = _build_similar_pattern_report(klines, window_days=20, top_n=5, forward_days=[5, 10, 20])
        if report.get("matches"):
            agg = report.get("aggregate_prediction", {})
            return {
                "match_count": len(report["matches"]),
                "avg_correlation": round(np.mean([m.get("correlation", 0) for m in report["matches"]]), 3),
                "forward_prediction": {
                    k: {"avg_return": round(v.get("mean_return", 0) * 100, 2), "positive_pct": round(v.get("positive_pct", 0) * 100, 1)}
                    for k, v in agg.items()
                },
            }
    except Exception as e:
        logger.debug("相似形态分析失败: %s", e)
    return None


async def _get_factor_snapshot(code: str, closes: list[float]) -> dict | None:
    """P2: 计算动量/波动率因子的分位数，提供量化信号强度依据。"""
    try:
        if len(closes) < 60:
            return None

        # 动量因子: 20日收益率
        mom_20 = (closes[-1] - closes[-20]) / closes[-20] * 100 if closes[-20] > 0 else 0
        # 60日收益率
        mom_60 = (closes[-1] - closes[-60]) / closes[-60] * 100 if closes[-60] > 0 else 0

        # 波动率: 20日收益率标准差
        returns_20 = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(len(closes) - 20, len(closes)) if closes[i - 1] > 0]
        vol_20 = float(np.std(returns_20) * 100) if returns_20 else 0

        # 计算动量因子在历史中的分位数
        hist_mom = []
        for i in range(60, len(closes)):
            m = (closes[i] - closes[i - 20]) / closes[i - 20] * 100 if closes[i - 20] > 0 else 0
            hist_mom.append(m)
        mom_pct = round(sum(1 for m in hist_mom if m < mom_20) / len(hist_mom) * 100, 1) if hist_mom else 50

        hist_vol = []
        for i in range(40, len(closes)):
            r = [(closes[j] - closes[j - 1]) / closes[j - 1] for j in range(i - 19, i + 1) if closes[j - 1] > 0]
            if r:
                hist_vol.append(float(np.std(r) * 100))
        vol_pct = round(sum(1 for v in hist_vol if v < vol_20) / len(hist_vol) * 100, 1) if hist_vol else 50

        return {
            "momentum_20d": round(mom_20, 2),
            "momentum_60d": round(mom_60, 2),
            "momentum_percentile": mom_pct,
            "volatility_20d": round(vol_20, 2),
            "volatility_percentile": vol_pct,
            "momentum_signal": "强势" if mom_pct > 80 else "偏强" if mom_pct > 60 else "中性" if mom_pct > 40 else "偏弱" if mom_pct > 20 else "弱势",
            "volatility_signal": "高波动" if vol_pct > 80 else "中高" if vol_pct > 60 else "正常" if vol_pct > 40 else "偏低" if vol_pct > 20 else "低波动",
        }
    except Exception as e:
        logger.debug("因子快照获取失败: %s", e)
    return None


def _compute_var(closes: list[float], capital: float, position_pct: float = 0.30) -> dict | None:
    """P2: 计算 VaR 和极端场景损失估算。"""
    try:
        if len(closes) < 60:
            return None

        returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes)) if closes[i - 1] > 0]
        if len(returns) < 30:
            return None

        arr = np.array(returns)
        position_value = capital * position_pct

        var_95 = round(float(np.percentile(arr, 5)) * position_value, 2)
        var_99 = round(float(np.percentile(arr, 1)) * position_value, 2)
        max_daily_loss = round(float(np.min(arr)) * position_value, 2)

        # 连续下跌极端场景: 最近 250 天内最大 5 日回撤
        max_5d_drawdown = 0
        for i in range(4, len(closes)):
            dd = (closes[i] - max(closes[max(0, i - 4): i + 1])) / max(closes[max(0, i - 4): i + 1])
            if dd < max_5d_drawdown:
                max_5d_drawdown = dd

        return {
            "daily_var_95": abs(var_95),
            "daily_var_99": abs(var_99),
            "worst_daily_loss": abs(max_daily_loss),
            "max_5d_drawdown_pct": round(abs(max_5d_drawdown) * 100, 2),
            "extreme_scenario_loss": round(abs(max_5d_drawdown) * position_value, 2),
            "position_value": round(position_value, 2),
        }
    except Exception as e:
        logger.debug("VaR 计算失败: %s", e)
    return None
