

def _build_trend_templates(
    theme_name: str,
    theme_code: str,
    symbols: list[str],
    stock_pool: dict[str, Any],
    *,
    include_breakout: bool = False,
    conservative: bool = False,
    disable_momentum: bool = False,
    prefer_breakout_first: bool = False,
) -> list[dict[str, Any]]:
    """趋势跟踪模板，兼顾传统趋势与高波动成长场景。"""
    short_window = 12 if conservative else 6
    long_window = 48 if conservative else 24
    ma_entry = {
        "any": [{
            "op": "cross_above",
            "left": {"indicator": "sma", "field": "close", "window": short_window},
            "right": {"indicator": "sma", "field": "close", "window": long_window},
        }],
    }
    ma_exit = {
        "any": [{
            "op": "cross_below",
            "left": {"indicator": "sma", "field": "close", "window": short_window},
            "right": {"indicator": "sma", "field": "close", "window": long_window},
        }],
    }
    ma_tags = ["trend", "ma_cross"]
    ma_description = f"{theme_name}主线以均线趋势跟踪为主，适合景气延续与抱团强化阶段。"
    if conservative:
        ma_entry = {
            "all": [
                {
                    "op": "cross_above",
                    "left": {"indicator": "sma", "field": "close", "window": short_window},
                    "right": {"indicator": "sma", "field": "close", "window": long_window},
                },
                {
                    "op": "gt",
                    "left": {"field": "close"},
                    "right": {"indicator": "sma", "field": "close", "window": 20},
                },
                {
                    "op": "gt",
                    "left": {"indicator": "roc", "field": "close", "window": 20},
                    "right": {"value": 0.01},
                },
                {
                    "op": "gt",
                    "left": {"indicator": "volume_ratio", "field": "volume", "window": 20},
                    "right": {"value": 1.0},
                },
            ],
        }
        ma_exit = {
            "any": [
                {
                    "op": "cross_below",
                    "left": {"indicator": "sma", "field": "close", "window": short_window},
                    "right": {"indicator": "sma", "field": "close", "window": long_window},
                },
                {
                    "op": "lt",
                    "left": {"field": "close"},
                    "right": {"indicator": "sma", "field": "close", "window": 20},
                },
                {
                    "op": "lt",
                    "left": {"indicator": "roc", "field": "close", "window": 10},
                    "right": {"value": -0.012},
                },
            ],
        }
        ma_tags = ["trend", "ma_cross", "conservative"]
        ma_description = f"{theme_name}在定向 target pool 下改用长周期均线和量价确认，优先保证信号稳定性而不是追求高频触发。"

    templates = [
        _build_template_candidate(
            theme_name=theme_name,
            theme_code=theme_code,
            family="ma_cross",
            title_suffix="趋势跟踪",
            symbols=symbols,
            stock_pool=stock_pool,
            params={"short_period": short_window, "long_period": long_window},
            entry=ma_entry,
            exit_rule=ma_exit,
            tags=ma_tags,
            description=ma_description,
        ),
    ]
    if not disable_momentum:
        momentum_lookback = 24 if conservative else 12
        momentum_threshold = 0.03 if conservative else 0.018
        momentum_entry = {
            "all": [
                {"op": "gt", "left": {"indicator": "roc", "field": "close", "window": momentum_lookback}, "right": {"value": momentum_threshold}},
                {"op": "gt", "left": {"indicator": "volume_ratio", "field": "volume", "window": 20}, "right": {"value": 1.15 if conservative else 1.1}},
            ],
        }
        momentum_exit = {
            "any": [
                {"op": "lt", "left": {"indicator": "roc", "field": "close", "window": 12 if conservative else 8}, "right": {"value": -0.01 if conservative else -0.02}},
                {"op": "gt", "left": {"indicator": "rsi", "field": "close", "window": 14}, "right": {"value": 76 if conservative else 78}},
            ],
        }
        momentum_tags = ["trend", "momentum"]
        momentum_description = f"{theme_name}热点扩散阶段更适合用短中周期动量确认主升浪。"
        if conservative:
            momentum_entry = {
                "all": [
                    {"op": "gt", "left": {"indicator": "roc", "field": "close", "window": momentum_lookback}, "right": {"value": momentum_threshold}},
                    {
                        "op": "gt",
                        "left": {"field": "close"},
                        "right": {"indicator": "sma", "field": "close", "window": 40},
                    },
                    {
                        "op": "gt",
                        "left": {"indicator": "sma", "field": "close", "window": 12},
                        "right": {"indicator": "sma", "field": "close", "window": 48},
                    },
                    {"op": "gt", "left": {"indicator": "volume_ratio", "field": "volume", "window": 20}, "right": {"value": 1.15}},
                ],
            }
            momentum_tags = ["trend", "momentum", "conservative"]
            momentum_description = f"{theme_name}仅在强趋势已确认时才允许动量突破，优先过滤掉高换手、低持续性的追涨信号。"
        templates.append(
            _build_template_candidate(
                theme_name=theme_name,
                theme_code=theme_code,
                family="momentum",
                title_suffix="动量突破",
                symbols=symbols,
                stock_pool=stock_pool,
                params={"lookback": momentum_lookback, "threshold": momentum_threshold},
                entry=momentum_entry,
                exit_rule=momentum_exit,
                tags=momentum_tags,
                description=momentum_description,
            )
        )
    if include_breakout:
        breakout_candidate = _build_template_candidate(
            theme_name=theme_name,
            theme_code=theme_code,
            family="volatility_breakout",
            title_suffix="波动突破",
            symbols=symbols,
            stock_pool=stock_pool,
            params={"lookback": 30 if conservative else 20, "threshold": 0.03 if conservative else 0.025},
            entry={
                "all": [
                    {"op": "gt", "left": {"indicator": "roc", "field": "close", "window": 30 if conservative else 20}, "right": {"value": 0.03 if conservative else 0.025}},
                    {"op": "gt", "left": {"indicator": "stddev", "field": "close", "window": 20}, "right": {"value": 0.02 if conservative else 0.018}},
                    {"op": "gt", "left": {"indicator": "volume_ratio", "field": "volume", "window": 20}, "right": {"value": 1.12 if conservative else 1.0}},
                ],
            },
            exit_rule={
                "any": [
                    {"op": "lt", "left": {"indicator": "roc", "field": "close", "window": 12 if conservative else 10}, "right": {"value": -0.012 if conservative else -0.015}},
                    {
                        "op": "cross_below",
                        "left": {"indicator": "sma", "field": "close", "window": 10 if conservative else 5},
                        "right": {"indicator": "sma", "field": "close", "window": 40 if conservative else 20},
                    },
                ],
            },
            tags=["trend", "breakout", "high_beta", *(['conservative'] if conservative else [])],
            description=(
                f"{theme_name}处于高弹性放量阶段时，优先用波动突破捕捉主升与加速段。"
                if not conservative
                else f"{theme_name}在定向 basket 下优先用更长确认窗口的波动突破，只保留趋势和量能都足够清晰的候选。"
            ),
        )
        if prefer_breakout_first:
            templates = [breakout_candidate, *templates]
        else:
            templates.append(breakout_candidate)
    return templates


def _build_mean_reversion_templates(
    theme_name: str,
    theme_code: str,
    symbols: list[str],
    stock_pool: dict[str, Any],
    *,
    include_gap_fill: bool = False,
) -> list[dict[str, Any]]:
    """均值回归模板，覆盖防御与错杀修复场景。"""
    templates = [
        _build_template_candidate(
            theme_name=theme_name,
            theme_code=theme_code,
            family="rsi",
            title_suffix="超卖回归",
            symbols=symbols,
            stock_pool=stock_pool,
            params={"rsi_period": 14, "oversold": 35, "overbought": 65},
            entry={
                "all": [
                    {"op": "lt", "left": {"indicator": "rsi", "field": "close", "window": 14}, "right": {"value": 35}},
                    {"op": "gt", "left": {"indicator": "volume_ratio", "field": "volume", "window": 20}, "right": {"value": 0.8}},
                ],
            },
            exit_rule={
                "any": [
                    {"op": "gt", "left": {"indicator": "rsi", "field": "close", "window": 14}, "right": {"value": 65}},
                ],
            },
            tags=["mean_reversion", "rsi"],
            description=f"{theme_name}偏低波防御属性，适合用经典 RSI 超卖回归吸收短线回撤。",
        ),
        _build_template_candidate(
            theme_name=theme_name,
            theme_code=theme_code,
            family="mean_reversion_short",
            title_suffix="短线回归",
            symbols=symbols,
            stock_pool=stock_pool,
            params={"rsi_period": 6, "oversold": 26, "overbought": 62},
            entry={
                "all": [
                    {"op": "lt", "left": {"indicator": "rsi", "field": "close", "window": 6}, "right": {"value": 26}},
                    {"op": "lt", "left": {"indicator": "zscore", "field": "close", "window": 20}, "right": {"value": -1.0}},
                ],
            },
            exit_rule={
                "any": [
                    {"op": "gt", "left": {"indicator": "rsi", "field": "close", "window": 6}, "right": {"value": 58}},
                    {"op": "gt", "left": {"indicator": "zscore", "field": "close", "window": 20}, "right": {"value": 0.8}},
                ],
            },
            tags=["mean_reversion", "short_horizon"],
            description=f"{theme_name}震荡期更容易出现短周期偏离修复，适合短线均值回归模板。",
        ),
    ]
    if include_gap_fill:
        templates.append(
            _build_template_candidate(
                theme_name=theme_name,
                theme_code=theme_code,
                family="gap_fill",
                title_suffix="跳空回补",
                symbols=symbols,
                stock_pool=stock_pool,
                params={"gap_threshold": 0.02, "rsi_period": 5, "oversold": 24, "overbought": 58},
                entry={
                    "all": [
                        {"op": "lt", "left": {"indicator": "rsi", "field": "close", "window": 5}, "right": {"value": 24}},
                        {"op": "lt", "left": {"indicator": "roc", "field": "close", "window": 2}, "right": {"value": -0.025}},
                    ],
                },
                exit_rule={
                    "any": [
                        {"op": "gt", "left": {"indicator": "rsi", "field": "close", "window": 5}, "right": {"value": 58}},
                        {"op": "gt", "left": {"indicator": "roc", "field": "close", "window": 3}, "right": {"value": 0.02}},
                    ],
                },
                tags=["mean_reversion", "event_repair"],
                description=f"{theme_name}若因情绪冲击出现快速错杀，更适合用跳空回补模板承接修复。",
            )
        )
    return templates


def _build_rotation_templates(
    theme_name: str,
    theme_code: str,
    symbols: list[str],
    stock_pool: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        _build_template_candidate(
            theme_name=theme_name,
            theme_code=theme_code,
            family="sector_rotation",
            title_suffix="行业轮动",
            symbols=symbols,
            stock_pool=stock_pool,
            params={"lookback": 20, "factor_weights": {"momentum": 0.45, "quality": 0.30, "value": 0.25}},
            entry={
                "all": [
                    {"op": "gt", "left": {"indicator": "roc", "field": "close", "window": 20}, "right": {"value": 0.015}},
                    {"op": "gt", "left": {"indicator": "zscore", "field": "close", "window": 20}, "right": {"value": -0.3}},
                ],
            },
            exit_rule={
                "any": [
                    {"op": "lt", "left": {"indicator": "roc", "field": "close", "window": 10}, "right": {"value": -0.015}},
                    {"op": "lt", "left": {"indicator": "zscore", "field": "close", "window": 20}, "right": {"value": -1.2}},
                ],
            },
            tags=["rotation", "macro"],
            description=f"{theme_name}更偏政策/商品/顺周期轮动，适合用行业轮动打分模板捕捉切换。",
        )
    ]


def _build_flow_templates(
    theme_name: str,
    theme_code: str,
    symbols: list[str],
    stock_pool: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        _build_template_candidate(
            theme_name=theme_name,
            theme_code=theme_code,
            family="north_capital_track",
            title_suffix="北向跟踪",
            symbols=symbols,
            stock_pool=stock_pool,
            params={"lookback": 15, "threshold": 0.015},
            entry={
                "all": [
                    {"op": "gt", "left": {"indicator": "roc", "field": "close", "window": 15}, "right": {"value": 0.015}},
                    {"op": "gt", "left": {"indicator": "volume_ratio", "field": "volume", "window": 15}, "right": {"value": 1.1}},
                ],
            },
            exit_rule={
                "any": [
                    {"op": "lt", "left": {"indicator": "roc", "field": "close", "window": 10}, "right": {"value": -0.012}},
                    {"op": "lt", "left": {"indicator": "volume_ratio", "field": "volume", "window": 10}, "right": {"value": 0.92}},
                ],
            },
            tags=["capital_flow", "north_fund"],
            description=f"{theme_name}受资金偏好驱动较强时，优先使用北向跟踪模板承接趋势与量能共振。",
        )
    ]


def _build_divergence_templates(
    theme_name: str,
    theme_code: str,
    symbols: list[str],
    stock_pool: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        _build_template_candidate(
            theme_name=theme_name,
            theme_code=theme_code,
            family="margin_divergence",
            title_suffix="融资背离",
            symbols=symbols,
            stock_pool=stock_pool,
            params={"fear_threshold": 40, "greed_threshold": 60, "lookback": 15},
            entry={
                "all": [
                    {"op": "lt", "left": {"indicator": "roc", "field": "close", "window": 5}, "right": {"value": 0.0}},
                    {"op": "gt", "left": {"indicator": "volume_ratio", "field": "volume", "window": 15}, "right": {"value": 0.95}},
                ],
            },
            exit_rule={
                "any": [
                    {"op": "gt", "left": {"indicator": "rsi", "field": "close", "window": 10}, "right": {"value": 68}},
                    {"op": "lt", "left": {"indicator": "roc", "field": "close", "window": 10}, "right": {"value": -0.02}},
                ],
            },
            tags=["capital_flow", "divergence"],
            description=f"{theme_name}在情绪分歧与量价背离阶段，更适合用融资背离模板捕捉修复回归。",
        )
    ]
