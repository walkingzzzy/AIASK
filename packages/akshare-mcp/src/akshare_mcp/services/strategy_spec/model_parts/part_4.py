    for field_name in ("legacy_semantic_contract", "contradiction_count", "proxy_dependency_score"):
        if candidate_params.get(field_name) not in (None, "", [], {}):
            candidate_payload[field_name] = candidate_params.get(field_name)
    return candidate_payload
