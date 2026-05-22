

async def _fallback_strategy_generation(db: Any, input_data: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """使用 DSL 模板库生成策略，根据主题类型选择合适的策略模板。"""
    confirmations = list(input_data.get("confirmations") or [])
    confirmed = [c for c in confirmations if c.get("confirmed")]
    if not confirmed:
        confirmed = confirmations[:2]  # 至少生成一些候选

    # 按 theme_code 分组
    theme_symbols: dict[str, list[str]] = {}
    for conf in confirmed:
        tc = str(conf.get("theme_code") or "default").strip()
        sym = str(conf.get("symbol") or "").strip()
        if sym:
            theme_symbols.setdefault(tc, []).append(sym)

    candidates: list[dict[str, Any]] = []
    fear_greed = _fear_greed_score(snapshot)
    north_inflow = _north_fund_inflow(snapshot)
    hot_sector_count = len(_snapshot_sector_names(snapshot, input_data))
    generation_profile = _snapshot_strategy_generation_profile(input_data.get("research_task"))
    risk_on = fear_greed >= 58 or north_inflow > 0 or hot_sector_count >= 3
    risk_off = fear_greed <= 45 or str(snapshot.get("sentiment") or "").strip().lower() in {"fear", "risk_off", "weak"}
    for theme_code, symbols in theme_symbols.items():
        theme_info = _THEME_LOOKUP.get(theme_code, {})
        theme_name = theme_info.get("name", theme_code)
        stock_pool = {"selection_mode": "explicit", "symbols": list(symbols)}
        hot_strength = _theme_hot_sector_strength(theme_code, snapshot, input_data)
        include_breakout = _is_growth_theme(theme_code) and (risk_on or hot_strength >= 1.5)
        include_gap_fill = _is_defensive_theme(theme_code) or risk_off
        templates: list[dict[str, Any]] = []
        if generation_profile.get("conservative_snapshot_task"):
            template_profile = str(generation_profile.get("template_generation_profile") or "").strip().lower()
            if template_profile == "conservative_mean_reversion":
                templates.extend(
                    _build_mean_reversion_templates(
                        theme_name,
                        theme_code,
                        symbols,
                        stock_pool,
                        include_gap_fill=True,
                    )
                )
                if not risk_off:
                    templates.extend(_build_rotation_templates(theme_name, theme_code, symbols, stock_pool))
            elif template_profile == "conservative_flow":
                templates.extend(_build_flow_templates(theme_name, theme_code, symbols, stock_pool))
                templates.extend(_build_rotation_templates(theme_name, theme_code, symbols, stock_pool))
                templates.extend(
                    _build_trend_templates(
                        theme_name,
                        theme_code,
                        symbols,
                        stock_pool,
                        conservative=True,
                        disable_momentum=True,
                    )
                )
            elif template_profile == "conservative_rotation":
                templates.extend(_build_rotation_templates(theme_name, theme_code, symbols, stock_pool))
                templates.extend(_build_divergence_templates(theme_name, theme_code, symbols, stock_pool))
                if risk_on or hot_strength >= 1.0:
                    templates.extend(
                        _build_trend_templates(
                            theme_name,
                            theme_code,
                            symbols,
                            stock_pool,
                            conservative=True,
                            disable_momentum=True,
                        )
                    )
            elif template_profile == "conservative_breakout":
                templates.extend(
                    _build_trend_templates(
                        theme_name,
                        theme_code,
                        symbols,
                        stock_pool,
                        include_breakout=include_breakout or hot_strength >= 1.0,
                        conservative=True,
                        disable_momentum=True,
                        prefer_breakout_first=True,
                    )
                )
                if north_inflow > 0 and _is_flow_preferred_theme(theme_code):
                    templates.extend(_build_flow_templates(theme_name, theme_code, symbols, stock_pool))
            else:
                if risk_off or not _is_growth_theme(theme_code):
                    templates.extend(
                        _build_mean_reversion_templates(
                            theme_name,
                            theme_code,
                            symbols,
                            stock_pool,
                            include_gap_fill=include_gap_fill,
                        )
                    )
                templates.extend(_build_rotation_templates(theme_name, theme_code, symbols, stock_pool))
                templates.extend(
                    _build_trend_templates(
                        theme_name,
                        theme_code,
                        symbols,
                        stock_pool,
                        include_breakout=include_breakout and risk_on,
                        conservative=True,
                        disable_momentum=True,
                    )
                )
            templates = _filter_templates_by_allowed_types(
                templates,
                list(generation_profile.get("allowed_strategy_types") or []),
            )
            capped_templates = _dedupe_candidates(templates)[: int(generation_profile.get("candidate_cap") or 1)]
            for item in capped_templates:
                item["research_task"] = dict(input_data.get("research_task") or {})
            candidates.extend(capped_templates)
            continue
        if _is_defensive_theme(theme_code):
            templates.extend(
                _build_mean_reversion_templates(
                    theme_name,
                    theme_code,
                    symbols,
                    stock_pool,
                    include_gap_fill=include_gap_fill,
                )
            )
            logger.debug("Fallback: using mean-reversion templates for defensive theme '%s'", theme_code)
        elif _is_rotation_theme(theme_code):
            templates.extend(_build_rotation_templates(theme_name, theme_code, symbols, stock_pool))
            if risk_off:
                templates.extend(
                    _build_mean_reversion_templates(
                        theme_name,
                        theme_code,
                        symbols,
                        stock_pool,
                        include_gap_fill=True,
                    )
                )
            else:
                templates.extend(
                    _build_trend_templates(
                        theme_name,
                        theme_code,
                        symbols,
                        stock_pool,
                        include_breakout=include_breakout or hot_strength >= 1.0,
                    )
                )
        else:
            if risk_off and not _is_growth_theme(theme_code):
                templates.extend(
                    _build_mean_reversion_templates(
                        theme_name,
                        theme_code,
                        symbols,
                        stock_pool,
                        include_gap_fill=include_gap_fill,
                    )
                )
            templates.extend(
                _build_trend_templates(
                    theme_name,
                    theme_code,
                    symbols,
                    stock_pool,
                    include_breakout=include_breakout,
                )
            )

        if hot_sector_count >= 3 and _is_rotation_theme(theme_code):
            templates.extend(_build_rotation_templates(theme_name, theme_code, symbols, stock_pool))
        if north_inflow > 0 and _is_flow_preferred_theme(theme_code):
            templates.extend(_build_flow_templates(theme_name, theme_code, symbols, stock_pool))
        if risk_off and not _is_defensive_theme(theme_code):
            templates = _build_divergence_templates(theme_name, theme_code, symbols, stock_pool) + templates

        normal_templates = _dedupe_candidates(
            _filter_templates_by_allowed_types(
                templates,
                list(generation_profile.get("allowed_strategy_types") or []),
            )
        )[:4]
        for item in normal_templates:
            item["research_task"] = dict(input_data.get("research_task") or {})
        candidates.extend(normal_templates)

    return {"candidates": candidates[:6]}


def _match_sector_to_theme(sector_name: str) -> str:
    """将板块名称匹配到主题库中的 theme_code。"""
    sector_lower = sector_name.lower()
    for theme in EXTENDED_THEME_LIBRARY:
        for alias in list(theme.get("aliases") or []):
            if alias.lower() in sector_lower or sector_lower in alias.lower():
                return theme["theme_code"]
    return ""


# ---------------------------------------------------------------------------
# Stage Definitions — 注册表
# ---------------------------------------------------------------------------

def _build_stage_definitions() -> dict[str, StageDefinition]:
    """构建 5 个 Stage 的定义。"""
    from strategy_factory import (
        PIPELINE_STAGE_MAX_TOKENS,
        PIPELINE_STAGE_TEMPERATURE,
    )

    return {
        "event_recognition": StageDefinition(
            stage_id="event_recognition",
            system_prompt=_PROMPT_EVENT_RECOGNITION,
            max_tokens=PIPELINE_STAGE_MAX_TOKENS.get("event_recognition", 600),
            temperature=PIPELINE_STAGE_TEMPERATURE.get("event_recognition", 0.2),
            required_output_keys=["events"],
            fallback_fn=_fallback_event_recognition,
        ),
        "theme_propagation": StageDefinition(
            stage_id="theme_propagation",
            system_prompt=_PROMPT_THEME_PROPAGATION,
            max_tokens=PIPELINE_STAGE_MAX_TOKENS.get("theme_propagation", 400),
            temperature=PIPELINE_STAGE_TEMPERATURE.get("theme_propagation", 0.2),
            required_output_keys=["themes"],
            fallback_fn=_fallback_theme_propagation,
        ),
        "exposure_mapping": StageDefinition(
            stage_id="exposure_mapping",
            system_prompt=_PROMPT_EXPOSURE_MAPPING,
            max_tokens=PIPELINE_STAGE_MAX_TOKENS.get("exposure_mapping", 500),
            temperature=PIPELINE_STAGE_TEMPERATURE.get("exposure_mapping", 0.25),
            required_output_keys=["exposures"],
            fallback_fn=_fallback_exposure_mapping,
        ),
        "market_confirmation": StageDefinition(
            stage_id="market_confirmation",
            system_prompt=_PROMPT_MARKET_CONFIRMATION,
            max_tokens=PIPELINE_STAGE_MAX_TOKENS.get("market_confirmation", 500),
            temperature=PIPELINE_STAGE_TEMPERATURE.get("market_confirmation", 0.15),
            required_output_keys=["confirmations"],
            fallback_fn=_fallback_market_confirmation,
        ),
        "strategy_generation": StageDefinition(
            stage_id="strategy_generation",
            system_prompt=_PROMPT_STRATEGY_GENERATION,
            max_tokens=PIPELINE_STAGE_MAX_TOKENS.get("strategy_generation", 800),
            temperature=PIPELINE_STAGE_TEMPERATURE.get("strategy_generation", 0.3),
            required_output_keys=["candidates"],
            fallback_fn=_fallback_strategy_generation,
        ),
    }


# 惰性初始化的全局注册表
_stage_registry: Optional[dict[str, StageDefinition]] = None


def get_stage_registry() -> dict[str, StageDefinition]:
    global _stage_registry
    if _stage_registry is None:
        _stage_registry = _build_stage_definitions()
    return _stage_registry


def validate_stage_output(stage_id: str, output: dict[str, Any]) -> bool:
    """验证阶段输出是否合法。"""
    validator = _VALIDATORS.get(stage_id)
    if validator is None:
        return True
    try:
        return validator(output)
    except Exception:
        return False


# Pipeline 阶段执行顺序
STAGE_ORDER: list[str] = [
    "event_recognition",
    "theme_propagation",
    "exposure_mapping",
    "market_confirmation",
    "strategy_generation",
]
