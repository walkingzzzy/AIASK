

async def _fallback_exposure_mapping(db: Any, input_data: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """使用 opportunity.py 的规则扫描做板块→成分股映射。"""
    themes = list(input_data.get("themes") or [])
    if not themes:
        # Phase-1 并行时 exposure_mapping 拿不到 theme_propagation 输出，
        # 需要直接从 snapshot 的热门板块自举主题线索。
        for name in _snapshot_sector_names(snapshot, input_data)[:6]:
            matched_code = _match_sector_to_theme(name)
            theme_info = _THEME_LOOKUP.get(matched_code, {})
            themes.append({
                "theme_code": matched_code or f"snapshot_sector_{name}",
                "theme_name": theme_info.get("name", name) or name,
                "sector_hint": name,
            })

    # 尝试从 DB 加载股票池并按主题关键词匹配
    from strategy_factory import _call_optional_async
    universe = await _call_optional_async(db, "list_stock_universe", limit=200, offset=0, default=[])

    normalized_universe = [
        {
            "code": str((row or {}).get("code") or "").strip(),
            "text": " ".join(
                [
                    str((row or {}).get("name") or "").lower(),
                    str((row or {}).get("industry") or "").lower(),
                    str((row or {}).get("sector") or "").lower(),
                ]
            ),
        }
        for row in list(universe or [])
    ]

    def _map_theme(th: dict[str, Any]) -> Optional[dict[str, Any]]:
        theme_code = str(th.get("theme_code") or "").strip()
        theme_info = _THEME_LOOKUP.get(theme_code, {})
        sector_hint = str(th.get("sector_hint") or th.get("theme_name") or "").strip()
        aliases = [
            str(alias or "").strip().lower()
            for alias in list(theme_info.get("aliases") or [])
            if str(alias or "").strip()
        ]
        if sector_hint:
            aliases.extend(
                [
                    sector_hint.lower(),
                    sector_hint.replace("板块", "").strip().lower(),
                ]
            )
        aliases = list(dict.fromkeys([alias for alias in aliases if alias]))
        if not aliases:
            return None
        matched_symbols: list[str] = []
        for row in normalized_universe:
            text = str(row.get("text") or "")
            if any(alias in text for alias in aliases):
                code = str(row.get("code") or "").strip()
                if code:
                    matched_symbols.append(code)
            if len(matched_symbols) >= 6:
                break
        if matched_symbols:
            return {
                "theme_code": theme_code,
                "target_symbols": matched_symbols,
                "sector": theme_info.get("name", sector_hint or theme_code),
                "exposure_type": "direct_beneficiary",
                "weight": 0.5,
            }
        return None
    exposures = [
        item
        for item in await asyncio.gather(*[asyncio.to_thread(_map_theme, th) for th in themes])
        if item
    ]
    return {"exposures": exposures}


async def _fallback_market_confirmation(db: Any, input_data: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """使用技术面扫描逻辑做确认。"""
    from strategy_factory import _call_optional_async

    exposures = list(input_data.get("exposures") or [])
    symbol_jobs: list[tuple[str, str]] = []
    for exp in exposures:
        theme_code = str(exp.get("theme_code") or "").strip()
        for symbol in list(exp.get("target_symbols") or [])[:4]:
            symbol_jobs.append((theme_code, symbol))

    async def _load_symbol_klines(symbol: str) -> list[dict[str, Any]]:
        try:
            return list(await _call_optional_async(db, "get_klines", symbol, limit=30, default=[]))
        except TypeError:
            return list(await _call_optional_async(db, "get_klines", symbol, default=[]))

    kline_payloads = await asyncio.gather(
        *[_load_symbol_klines(symbol) for _theme_code, symbol in symbol_jobs],
        return_exceptions=True,
    )

    confirmations: list[dict[str, Any]] = []
    for (theme_code, symbol), kline_payload in zip(symbol_jobs, kline_payloads):
        if isinstance(kline_payload, Exception):
            klines = []
        else:
            klines = list(kline_payload or [])
        confirmed = False
        signal_strength = "weak"
        if len(klines) >= 5:
            closes = [float(k.get("close") or 0) for k in klines if k.get("close") is not None]
            if len(closes) >= 5:
                ma5 = sum(closes[-5:]) / 5
                ma20 = sum(closes[-20:]) / max(len(closes[-20:]), 1) if len(closes) >= 20 else sum(closes) / len(closes)
                last_close = closes[-1]
                # 简单确认: 价格在均线上方且短均线>长均线
                if last_close > ma20 and ma5 > ma20:
                    confirmed = True
                    signal_strength = "moderate"
                if last_close > ma5 > ma20:
                    signal_strength = "strong"
        confirmations.append({
            "theme_code": theme_code,
            "symbol": symbol,
            "confirmed": confirmed,
            "signal_strength": signal_strength,
            "entry_timing": "immediate" if confirmed else "avoid",
            "risk_level": "medium",
        })
    return {"confirmations": confirmations}


def _is_defensive_theme(theme_code: str) -> bool:
    """判断主题是否属于防御/价值类（适合均值回归而非趋势跟踪）。"""
    theme_info = _THEME_LOOKUP.get(theme_code, {})
    parent = theme_info.get("parent", "")
    if parent in ("defensive",):
        return True
    if theme_code in ("high_dividend_banks", "insurance_pension"):
        return True
    return False


def _fear_greed_score(snapshot: dict[str, Any]) -> int:
    raw = snapshot.get("fear_greed_index")
    if raw is None:
        raw = dict(snapshot.get("fear_greed") or {}).get("score")
    try:
        return int(float(raw or 50))
    except (TypeError, ValueError):
        return 50


def _north_fund_inflow(snapshot: dict[str, Any]) -> float:
    north_fund = dict(snapshot.get("north_fund") or {})
    for key in ("net_inflow", "net_inflow_amount", "amount", "inflow"):
        value = north_fund.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _theme_parent(theme_code: str) -> str:
    return str(_THEME_LOOKUP.get(theme_code, {}).get("parent") or "").strip()


def _is_growth_theme(theme_code: str) -> bool:
    parent = _theme_parent(theme_code)
    if parent in {"technology", "new_energy", "defense"}:
        return True
    return theme_code in {
        "chip_domestic",
        "new_energy_vehicle",
        "photovoltaic_wind",
        "telecom_5g",
        "software_saas",
        "robotics_automation",
        "data_center_cloud",
    }


def _is_rotation_theme(theme_code: str) -> bool:
    parent = _theme_parent(theme_code)
    if parent in {"commodities", "policy", "infrastructure", "global_trade", "real_estate"}:
        return True
    return theme_code in {
        "upstream_oil_gas",
        "shipping_trade",
        "real_estate_chain",
        "rare_earth_metals",
        "infrastructure",
        "carbon_neutral",
    }


def _is_flow_preferred_theme(theme_code: str) -> bool:
    parent = _theme_parent(theme_code)
    if parent in {"consumer", "defensive", "technology", "new_energy"}:
        return True
    return theme_code in {
        "liquor_consumption",
        "high_dividend_banks",
        "insurance_pension",
        "chip_domestic",
        "software_saas",
        "data_center_cloud",
    }


def _theme_hot_sector_strength(theme_code: str, snapshot: dict[str, Any], input_data: Optional[dict[str, Any]] = None) -> float:
    theme_info = _THEME_LOOKUP.get(theme_code, {})
    aliases = {
        str(alias or "").strip().lower()
        for alias in list(theme_info.get("aliases") or [])
        if str(alias or "").strip()
    }
    aliases.add(str(theme_info.get("name") or theme_code).strip().lower())
    max_change = 0.0
    for sector_item in list((snapshot.get("hot_sectors") or (input_data or {}).get("market_snapshot", {}).get("sectors")) or []):
        name = _sector_item_name(sector_item).lower()
        if not name:
            continue
        if not any(alias and (alias in name or name in alias) for alias in aliases):
            continue
        try:
            max_change = max(max_change, abs(float((sector_item or {}).get("change_pct") or 0.0)))
        except (AttributeError, TypeError, ValueError):
            max_change = max(max_change, 0.0)
    return max_change


def _collapsed_hint_text(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
    )


def _snapshot_strategy_generation_profile(research_task: Optional[dict[str, Any]]) -> dict[str, Any]:
    task = dict(research_task or {})
    task_source = str(task.get("task_source") or "").strip().lower()
    opportunity_type = str(task.get("opportunity_type") or "").strip().lower()
    validation_focus = str(task.get("validation_focus") or "").strip().lower()
    allowed_strategy_types = [
        str(item).strip()
        for item in list(task.get("allowed_strategy_types") or [])
        if str(item).strip()
    ]
    template_profile = str(task.get("template_generation_profile") or "").strip().lower()
    hint_blob = " ".join(
        str(item or "")
        for item in (
            task.get("candidate_family"),
            task.get("factor_name"),
            task.get("candidate_name"),
            task.get("preference_reason"),
            task.get("rationale"),
        )
        if str(item or "").strip()
    )
    collapsed = _collapsed_hint_text(hint_blob)
    conservative_snapshot_task = (
        task_source == "snapshot"
        and (
            opportunity_type in {"candidate_family_activation", "candidate_factor_activation", "factor_acceleration"}
            or validation_focus == "candidate_target_only"
            or template_profile.startswith("conservative_")
        )
    )
    mean_reversion_tokens = (
        "closelocation",
        "intradayresilience",
        "trendefficiency",
        "pullback",
        "quality",
        "stability",
        "quiet",
        "resilience",
        "repair",
        "reversion",
        "defensive",
        "rsi",
    )
    flow_tokens = (
        "capitalflow",
        "northcapital",
        "northbound",
        "fundflow",
        "liquidity",
        "turnover",
    )
    rotation_tokens = (
        "rotation",
        "sector",
        "cycle",
        "divergence",
        "breadth",
    )
    breakout_tokens = (
        "momentum",
        "macross",
        "cross",
        "trend",
        "breakout",
        "gapcontinuation",
        "expansion",
        "acceleration",
        "volatility",
    )
    if not template_profile:
        if any(token in collapsed for token in mean_reversion_tokens):
            template_profile = "conservative_mean_reversion"
        elif any(token in collapsed for token in flow_tokens):
            template_profile = "conservative_flow"
        elif any(token in collapsed for token in rotation_tokens):
            template_profile = "conservative_rotation"
        elif any(token in collapsed for token in breakout_tokens):
            template_profile = "conservative_breakout"
        elif conservative_snapshot_task:
            template_profile = "conservative_trend"

    disable_momentum = (
        conservative_snapshot_task
        and (
            "momentum" not in allowed_strategy_types
            or template_profile in {
                "conservative_mean_reversion",
                "conservative_flow",
                "conservative_rotation",
                "conservative_trend",
                "conservative_breakout",
            }
        )
    )
    candidate_cap = 4
    if conservative_snapshot_task:
        candidate_cap = 1 if opportunity_type in {"candidate_family_activation", "candidate_factor_activation"} else 2

    return {
        "task_source": task_source,
        "opportunity_type": opportunity_type,
        "validation_focus": validation_focus,
        "allowed_strategy_types": allowed_strategy_types,
        "template_generation_profile": template_profile,
        "conservative_snapshot_task": conservative_snapshot_task,
        "disable_momentum": disable_momentum,
        "candidate_cap": candidate_cap,
    }


def _filter_templates_by_allowed_types(
    templates: list[dict[str, Any]],
    allowed_strategy_types: list[str],
) -> list[dict[str, Any]]:
    allowed = {
        str(item).strip()
        for item in list(allowed_strategy_types or [])
        if str(item).strip()
    }
    if not allowed:
        return list(templates)
    return [
        item
        for item in templates
        if str((item or {}).get("strategy_type") or "").strip() in allowed
    ]


def _build_template_candidate(
    *,
    theme_name: str,
    theme_code: str,
    family: str,
    title_suffix: str,
    symbols: list[str],
    stock_pool: dict[str, Any],
    params: dict[str, Any],
    entry: dict[str, Any],
    exit_rule: dict[str, Any],
    tags: list[str],
    description: str,
) -> dict[str, Any]:
    metadata = {"target_symbols": list(symbols), "stock_pool": dict(stock_pool)}
    return {
        "name": f"{theme_name}_{title_suffix}",
        "strategy_type": family,
        "target_symbols": list(symbols),
        "params": dict(params),
        "stock_pool": dict(stock_pool),
        "description": description,
        "dsl": {
            "version": "1.0",
            "timeframe": "daily",
            "entry": entry,
            "exit": exit_rule,
            "metadata": metadata,
        },
        "tags": ["ai_staged", theme_code, family, *tags],
    }


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for candidate in candidates:
        strategy_type = str(candidate.get("strategy_type") or "").strip()
        target_symbols = tuple(str(symbol).strip() for symbol in list(candidate.get("target_symbols") or []))
        if not strategy_type or not target_symbols:
            continue
        key = (strategy_type, target_symbols)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped
