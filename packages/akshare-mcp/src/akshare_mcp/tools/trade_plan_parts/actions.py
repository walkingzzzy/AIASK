

async def generate_plan(
    code: str,
    capital: float = 1_000_000,
    risk_per_trade: float = 0.02,
    style: str = "balanced",
) -> dict[str, Any]:
    """生成完整交易计划。"""
    from .db_freshness import ensure_fresh_klines, _calc_staleness

    klines, freshness_info = await ensure_fresh_klines(code, limit=250)

    if not klines or len(klines) < 60:
        return fail("K 线数据不足 60 根，无法生成交易计划")

    klines.sort(key=lambda k: k.get("date", ""))

    closes = [float(k.get("close", 0) or 0) for k in klines]
    highs = [float(k.get("high", 0) or 0) for k in klines]
    lows = [float(k.get("low", 0) or 0) for k in klines]
    volumes = [float(k.get("volume", 0) or 0) for k in klines]
    current_price = closes[-1]
    latest_volume = volumes[-1]
    avg_vol_20 = float(np.mean(volumes[-20:])) if len(volumes) >= 20 else float(np.mean(volumes))

    # ── Step 1: 关键价位 — 共享 klines 避免重复获取
    klines_for_levels = klines[-120:] if len(klines) > 120 else klines
    kl_result = await compute_key_levels(code, lookback_days=120, klines=klines_for_levels)
    levels = []
    if kl_result.get("success") and kl_result.get("data"):
        levels = kl_result["data"].get("levels", [])

    # ── Step 2: 技术指标
    ma20 = _TA.calculate_sma(closes, 20)
    ma60 = _TA.calculate_sma(closes, 60)
    macd_data = _TA.calculate_macd(closes)
    macd_hist = macd_data.get("histogram", [])
    rsi_data = _TA.calculate_rsi(closes)
    rsi_value = rsi_data.get("value", 50)
    atr_series = _TA.calculate_atr(highs, lows, closes, period=14)
    atr_14 = atr_series[-1] if atr_series and atr_series[-1] > 0 else 0

    # ── Step 3: K 线形态
    patterns = []
    try:
        patterns = pattern_recognition.detect_patterns(klines)
    except Exception:
        pass

    # ── Step 4: 资金流
    fund_flow = await _get_fund_flow_safe(code)

    # ── Step 5: 数据质量评估
    days_stale = freshness_info.get("staleness_days", _calc_staleness(klines))

    # ── Step 6: 信号融合 (核心) — P1: _judge_trend 使用完整 macd_data
    trend = _judge_trend(closes, macd_data, ma20, ma60)
    trigger = _judge_trigger(rsi_value, current_price, levels, patterns)
    confirm = _judge_confirmation(fund_flow, avg_vol_20, latest_volume)

    # P3-2: 多维度市场状态检测
    regime_detail = _detect_regime_advanced(closes, volumes)
    regime_params = _regime_adjusted_params(regime_detail["regime"])

    # P1: 深化历史验证 — 分持有期、平均收益、regime 分层
    hist_hit_rate = await _get_historical_hit_rate(code, rsi_value, macd_hist)
    hit_rate_detail = await _get_hit_rate_detail(code, rsi_value, macd_hist)

    # 冲突检测 (在 _compute_confidence 之前，因为冲突数量影响信号清晰度)
    conflicts = []
    if trend["direction"] in ("bullish", "bullish_weak") and rsi_value > _RSI_OVERBOUGHT:
        conflicts.append("趋势看多但 RSI 超买，短期过热，等回调更安全")
    if trend["direction"] in ("bearish", "bearish_weak") and trigger["status"] == "triggered":
        conflicts.append("趋势偏空但触发了看涨信号，可能是反弹而非反转，需谨慎")
    if confirm["status"] == "unconfirmed":
        conflicts.append("主力净流出，即使信号触发也需降低仓位")

    # 资金流方向
    fund_dir = "neutral"
    if confirm["status"] == "confirmed":
        fund_dir = "bullish"
    elif confirm["status"] == "unconfirmed":
        fund_dir = "bearish"

    # 交叉验证 (提前到这里，以便传入 _compute_confidence)
    cross_val = await _cross_validate_signal(code, capital)
    if cross_val:
        buy_prob = cross_val.get("buy_probability")
        if buy_prob is not None and buy_prob < 0.10 and trend["direction"] in ("bullish", "bullish_weak"):
            conflicts.append(
                f"交叉验证警告: should_i_buy 买入概率仅 {buy_prob:.1%}，"
                f"与当前趋势方向存在分歧"
            )

    confidence, confidence_breakdown = _compute_confidence(
        trend, trigger, confirm,
        data_staleness_days=days_stale,
        calibration_factor=1.0,
        kline_count=len(klines),
        historical_hit_rate=hist_hit_rate,
        cross_validation=cross_val,
        num_scenarios=3,
        num_levels=len(levels),
        num_conflicts=len(conflicts),
        closes=closes,
        macd_hist=macd_hist,
        rsi_value=rsi_value,
        fund_flow_direction=fund_dir,
    )
    direction = _determine_direction(trend, trigger, confidence)

    # 风格调整
    if style == "conservative" and direction == "buy":
        direction = "watch"
        confidence = round(confidence * 0.85, 2)
    elif style == "aggressive" and direction == "watch":
        direction = "buy"
        confidence = round(min(confidence * 1.1, 1.0), 2)

    # P3-2: 应用 regime 自适应参数
    effective_risk = regime_params.get("risk_per_trade", risk_per_trade)
    effective_max_pos = regime_params.get("max_position_pct", 0.30)

    # ── Step 6b: 场景化方案 — P0+P1+P3: 统一止损 + 数据驱动概率 + 凯利仓位 + 交易成本
    scenarios = await _build_scenarios(
        code, current_price, levels, capital, effective_risk, direction, atr_14,
        klines=klines_for_levels, closes=closes, hit_rate_detail=hit_rate_detail,
    )

    regime = _determine_regime(closes)

    stock_name = klines[-1].get("name", "") if klines else ""

    # ── P2: 量化增强分析（并行执行，不阻塞主流程）
    similar_patterns = await _get_similar_patterns(code, klines)
    factor_snapshot = await _get_factor_snapshot(code, closes)
    var_analysis = _compute_var(closes, capital, effective_max_pos)

    # ── P3-3: 滚动窗口验证 — 信号稳定性检测
    signal_name = _select_signal_name(rsi_value, macd_hist)
    signal_stability = _rolling_window_validation(closes, signal_name, klines)

    # ── P3-4: 信号衰减检测
    signal_decay = _detect_signal_decay(klines, signal_name)

    # ── 数据质量警告
    data_quality_warnings: list[str] = []
    if days_stale > 90:
        data_quality_warnings.append(
            f"K线数据严重过期（{days_stale}天），技术指标可能不反映当前市场状态"
        )
    elif days_stale > 30:
        data_quality_warnings.append(
            f"K线数据较旧（{days_stale}天），指标可信度降低"
        )
    elif days_stale > 7:
        data_quality_warnings.append(
            f"K线数据有延迟（{days_stale}天），建议关注最新行情"
        )

    if hist_hit_rate is not None and hist_hit_rate < 0.30:
        data_quality_warnings.append(
            f"当前信号组合的历史胜率较低({hist_hit_rate:.0%})，历史验证不充分"
        )
    elif hist_hit_rate is None:
        data_quality_warnings.append(
            "当前信号组合缺乏历史数据验证，置信度已折减"
        )

    # P3-3: 信号稳定性警告
    if signal_stability and signal_stability.get("stability", 1) < 0.55:
        data_quality_warnings.append(
            f"信号稳定性差（{signal_stability['stability']:.2f}），不同时期表现波动大，过拟合风险较高"
        )
        confidence = round(confidence * 0.90, 2)

    # P3-4: 信号衰减警告
    if signal_decay and signal_decay.get("warning"):
        data_quality_warnings.append(signal_decay["warning"])
        decay_ratio = signal_decay.get("decay_ratio", 1.0)
        if decay_ratio < 0.5:
            confidence = round(confidence * 0.85, 2)
        elif decay_ratio < 0.7:
            confidence = round(confidence * 0.92, 2)

    # 冲突检测中加入数据新鲜度冲突
    if days_stale > 30:
        conflicts.append(
            f"K线数据距今{days_stale}天，RSI/MACD等指标基于历史数据，仅供趋势参考"
        )

    result = {
        "code": code,
        "name": stock_name,
        "current_price": round(current_price, 2),
        "market_regime": regime,
        "regime_detail": regime_detail,
        "regime_adaptive_params": regime_params,
        "direction": direction,
        "confidence": confidence,
        "confidence_breakdown": confidence_breakdown,
        "data_quality": {
            "kline_last_date": klines[-1].get("date", "unknown") if klines else "unknown",
            "staleness_days": days_stale,
            "freshness": (
                "fresh" if days_stale <= 3
                else "acceptable" if days_stale <= 7
                else "stale" if days_stale <= 30
                else "severely_stale"
            ),
            "warnings": data_quality_warnings if data_quality_warnings else None,
        },
        "signal_summary": {
            "primary": {
                "name": trend["name"],
                "direction": trend["direction"],
                "detail": trend["detail"],
            },
            "trigger": {
                "name": trigger["name"],
                "status": trigger["status"],
                "action": trigger["action"],
            },
            "confirmation": {
                "name": confirm["name"],
                "status": confirm["status"],
            },
            "conflicts": conflicts if conflicts else None,
        },
        "cross_validation": cross_val,
        "scenarios": scenarios,
        "key_levels": levels[:8],
        "position_management": {
            "max_position_pct": round(effective_max_pos * 100, 1),
            "max_loss_per_trade_pct": round(effective_risk * 100, 2),
            "risk_budget_per_trade": round(capital * effective_risk, 2),
            "style": style,
            "regime_adjusted": regime_detail["regime"] != "unknown",
            "_capital": capital,
        },
        "indicators_snapshot": {
            "rsi": round(rsi_value, 1),
            "macd_histogram": round(float(macd_hist[-1]), 4) if macd_hist and macd_hist[-1] is not None else None,
            "ma20": round(ma20[-1], 2) if ma20 else None,
            "ma60": round(ma60[-1], 2) if ma60 else None,
            "atr_14": round(atr_14, 2),
            "atr_pct": round(atr_14 / current_price * 100, 2) if current_price > 0 else None,
            "volume_ratio": round(latest_volume / avg_vol_20, 2) if avg_vol_20 > 0 else None,
        },
        "hit_rate_detail": hit_rate_detail,
        "signal_stability": signal_stability,
        "signal_decay": signal_decay,
        "similar_patterns": similar_patterns,
        "factor_snapshot": factor_snapshot,
        "risk_analysis": var_analysis,
        "daily_checklist": [
            "开盘前: 检查隔夜消息面，确认计划是否需要调整",
            "盘中: 关注关键价位的量价配合",
            "尾盘: 记录当日高低价，若持仓则更新追踪止损位",
        ],
    }

    # ── Step 7: 价格归一化 — 用实时价校准复权偏移
    rt_price = await _get_realtime_price(code)
    price_factor = 1.0
    price_warning = None
    kline_date = klines[-1].get("date", "unknown") if klines else "unknown"

    if rt_price and current_price > 0:
        price_factor = rt_price / current_price
        if abs(price_factor - 1.0) > 0.02:
            result = _normalize_output(result, price_factor)
            price_warning = (
                f"K 线收盘价({current_price:.2f}, {kline_date})与实时价({rt_price:.2f})"
                f"偏差 {abs(price_factor - 1) * 100:.1f}%，已自动校准至实际价格"
            )

        # 用实际校准偏差重新计算 data_quality.calibration 子分
        cal_dev = abs(price_factor - 1.0)
        if cal_dev < 0.01:
            cal_sub = 1.0
        elif cal_dev < 0.02:
            cal_sub = 0.90
        elif cal_dev < 0.05:
            cal_sub = 0.70
        else:
            cal_sub = 0.40
        bd = result.get("confidence_breakdown", {})
        dq = bd.get("data_quality", {})
        old_cal = dq.get("calibration", 1.0)
        if abs(cal_sub - old_cal) > 0.01:
            dq["calibration"] = cal_sub
            new_dq_score = round((dq.get("freshness", 1.0) + cal_sub + dq.get("completeness", 1.0)) / 3.0, 2)
            dq["score"] = new_dq_score
            W = bd.get("weights", {})
            new_final = (
                new_dq_score * W.get("data_quality", 0.25)
                + bd.get("signal_clarity", {}).get("score", 0) * W.get("signal_clarity", 0.30)
                + bd.get("validation", {}).get("score", 0) * W.get("validation", 0.25)
                + bd.get("completeness", {}).get("score", 0) * W.get("completeness", 0.20)
            )
            new_final = round(min(1.0, max(0.0, new_final)), 2)
            bd["final"] = new_final
            result["confidence"] = new_final

    result["price_calibration"] = {
        "kline_close": round(current_price, 2),
        "realtime_price": round(rt_price, 2) if rt_price else None,
        "factor": round(price_factor, 4),
        "calibrated": abs(price_factor - 1.0) > 0.02,
        "warning": price_warning,
        "kline_date": kline_date,
    }

    result["position_management"].pop("_capital", None)

    return ok(result)


# ── MCP 注册 ──────────────────────────────────────────────────────


def register(mcp):
    """注册交易计划生成工具。"""

    @mcp.tool()
    async def generate_trade_plan(
        code: str,
        capital: float = 1_000_000,
        risk_per_trade: float = 0.02,
        style: str = "balanced",
    ):
        """生成完整交易计划（信号融合 + 场景化方案）

        一次调用完成多源信号融合，输出:
        - 方向判断 + 置信度
        - 3 个信号 (主信号/触发信号/确认信号) 的简洁结论
        - 场景化入场方案 (每个带条件/入场价/止损/止盈/若错则...)
        - 关键价位 (带突破/跌破操作建议)
        - 仓位管理参数

        Args:
            code: 股票代码
            capital: 可用资金 (元，默认 100 万)
            risk_per_trade: 单笔风险占比 (默认 0.02 即 2%)
            style: aggressive (激进) / balanced (均衡) / conservative (保守)
        """
        normalized_code, _, error = await resolve_existing_security_code_async(code=code)
        if error:
            return fail(error)
        return await generate_plan(
            normalized_code, capital=capital, risk_per_trade=risk_per_trade, style=style,
        )
