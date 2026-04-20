

async def handle_factor_candidate_registry(
    *,
    kw: dict[str, Any],
    ok: Callable[..., dict],
    fail: Callable[..., dict],
    filter_market_codes: Callable[[Any], list[str]],
) -> dict:
    op = str(kw.get("op", "list") or "list").strip().lower()

    if op in {"list", "ls"}:
        codes = _as_code_list(kw.get("codes"))
        market_codes_only = bool(kw.get("market_codes_only", False))
        include_synthetic = bool(kw.get("include_synthetic", False))
        family = str(kw.get("family") or "").strip() or None
        grade = str(kw.get("grade") or "").strip() or None
        recommendation = str(kw.get("recommendation") or "").strip() or None
        min_score = kw.get("min_score")
        min_score = None if min_score in {None, ""} else _safe_float(min_score, 0.0)
        only_active = bool(kw.get("only_active", False))
        limit = max(1, min(int(kw.get("limit", 20) or 20), 100))
        items = await _list_factor_candidate_registry_items(
            limit=limit,
            codes=codes or None,
            family=family,
            grade=grade,
            recommendation=recommendation,
            min_score=min_score,
            only_active=only_active,
            market_codes_only=market_codes_only,
            include_synthetic=include_synthetic,
            filter_market_codes=filter_market_codes,
        )
        return ok(
            {"op": "list", "count": len(items), "items": items, "summary": _summarize_factor_candidate_registry(items)},
            source_chain=["services.artifact_registry", "quant_manager.validate_factor_candidate"],
        )

    if op in {"summary", "stats"}:
        codes = _as_code_list(kw.get("codes"))
        market_codes_only = bool(kw.get("market_codes_only", False))
        include_synthetic = bool(kw.get("include_synthetic", False))
        family = str(kw.get("family") or "").strip() or None
        grade = str(kw.get("grade") or "").strip() or None
        recommendation = str(kw.get("recommendation") or "").strip() or None
        min_score = kw.get("min_score")
        min_score = None if min_score in {None, ""} else _safe_float(min_score, 0.0)
        only_active = bool(kw.get("only_active", False))
        limit = max(1, min(int(kw.get("limit", 200) or 200), 500))
        items = await _list_factor_candidate_registry_items(
            limit=limit,
            codes=codes or None,
            family=family,
            grade=grade,
            recommendation=recommendation,
            min_score=min_score,
            only_active=only_active,
            market_codes_only=market_codes_only,
            include_synthetic=include_synthetic,
            filter_market_codes=filter_market_codes,
        )
        return ok(
            {"op": "summary", "summary": _summarize_factor_candidate_registry(items)},
            source_chain=["services.artifact_registry", "quant_manager.validate_factor_candidate"],
        )

    if op in {"active_pool", "pool"}:
        codes = _as_code_list(kw.get("codes"))
        market_codes_only = bool(kw.get("market_codes_only", False))
        include_synthetic = bool(kw.get("include_synthetic", False))
        family = str(kw.get("family") or "").strip() or None
        min_score = kw.get("min_score")
        min_score = None if min_score in {None, ""} else _safe_float(min_score, 0.0)
        limit = max(1, min(int(kw.get("limit", 200) or 200), 500))
        items = await _list_factor_candidate_registry_items(
            limit=limit,
            codes=codes or None,
            family=family,
            recommendation=None,
            min_score=min_score,
            only_active=False,
            market_codes_only=market_codes_only,
            include_synthetic=include_synthetic,
            filter_market_codes=filter_market_codes,
        )
        return ok(
            {
                "op": "active_pool",
                "summary": _summarize_factor_candidate_registry(items),
                "active_pool": _build_active_candidate_pool(items),
            },
            source_chain=["services.artifact_registry", "quant_manager.validate_factor_candidate"],
        )

    if op in {"get", "detail"}:
        artifact_id = str(kw.get("artifact_id") or "").strip()
        if not artifact_id:
            return fail("factor_candidate_registry get 需要 artifact_id")
        artifact = await get_artifact_async(artifact_id)
        if not artifact:
            return fail(f"artifact not found: {artifact_id}")
        if str(artifact.get("strategy") or "").strip().lower() != "quant_factor_candidate_validation":
            return fail(f"artifact {artifact_id} is not quant_factor_candidate_validation")
        payload = _payload_from_artifact_row(artifact)
        return ok(
            {"op": "get", "item": _normalize_registry_item(artifact, payload), "artifact": artifact},
            source_chain=["services.artifact_registry", "quant_manager.validate_factor_candidate"],
        )

    return fail("Unknown factor_candidate_registry op. Supported: list|get|summary|active_pool")
