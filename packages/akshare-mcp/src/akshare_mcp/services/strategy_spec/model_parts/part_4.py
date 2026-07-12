    for field_name in ("legacy_semantic_contract", "contradiction_count", "proxy_dependency_score"):
        if candidate_params.get(field_name) not in (None, "", [], {}):
            candidate_payload[field_name] = candidate_params.get(field_name)
    strategy_explanation = build_strategy_explanation(
        candidate_payload,
        source=source,
    )
    if strategy_explanation:
        candidate_payload["strategy_explanation"] = strategy_explanation
        candidate_params["strategy_explanation"] = strategy_explanation
    return candidate_payload
