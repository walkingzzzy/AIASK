    """Allocate candidates into formal / observe / deferred incubation tracks."""

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    @staticmethod
    def _candidate_family(candidate: dict[str, Any]) -> str:
        payload = dict(candidate or {})
        research_task = dict(payload.get("research_task") or {})
        params = dict(payload.get("params") or {})
        candidate_provenance = dict(params.get("candidate_provenance") or {})
        return str(
            payload.get("candidate_family")
            or research_task.get("candidate_family")
            or params.get("candidate_family")
            or candidate_provenance.get("candidate_family")
            or payload.get("strategy_type")
            or "unknown"
        ).strip().lower() or "unknown"

    @staticmethod
    def _candidate_contract_value(candidate: dict[str, Any], key: str, default: Any = None) -> Any:
        payload = dict(candidate or {})
        params = dict(payload.get("params") or {})
        if key in payload:
            return payload.get(key)
        if key in params:
            return params.get(key)
        return default

    @classmethod
    def _is_formal_runtime_ready_candidate(cls, candidate: dict[str, Any]) -> bool:
        readiness_tier = str(
            cls._candidate_contract_value(candidate, "execution_readiness_tier") or ""
        ).strip().lower()
        trade_contract_status = str(
            cls._candidate_contract_value(candidate, "trade_prediction_contract_status") or ""
        ).strip().lower()
        semantic_runtime_match = cls._candidate_contract_value(
            candidate,
            "semantic_runtime_match",
        )
        proxy_runtime_used = bool(
            cls._candidate_contract_value(candidate, "proxy_runtime_used")
        )
        diagnostic_only = bool(
            cls._candidate_contract_value(candidate, "diagnostic_only")
        )
        observation_gap = bool(
            cls._candidate_contract_value(
                candidate,
                "trade_prediction_contract_observation_gap",
            )
        )
        execution_semantic_gap = bool(
            cls._candidate_contract_value(candidate, "execution_semantic_gap")
        )
        return (
            readiness_tier == "formal_runtime_ready"
            and trade_contract_status == "ready"
            and semantic_runtime_match is True
            and not proxy_runtime_used
            and not diagnostic_only
            and not observation_gap
            and not execution_semantic_gap
        )

    @staticmethod
    def _task_feedback_override(candidate: dict[str, Any]) -> dict[str, Any]:
        research_task = dict((candidate or {}).get("research_task") or {})
        if not research_task:
            return {}
        field_map = {
            "feedback_control_mode": "control_mode",
            "feedback_legacy_control_mode": "legacy_control_mode",
            "feedback_skill_control_mode": "skill_control_mode",
            "feedback_control_reasons": "control_reasons",
            "feedback_legacy_control_reasons": "legacy_control_reasons",
            "feedback_skill_control_reasons": "skill_control_reasons",
            "feedback_cooldown_active": "cooldown_active",
            "feedback_suppressed": "suppressed",
            "feedback_skill_cooldown_active": "skill_cooldown_active",
            "feedback_skill_suppressed": "skill_suppressed",
            "feedback_relaxed_throttle_active": "relaxed_throttle_active",
            "feedback_control_relaxed": "control_relaxed",
            "feedback_control_relaxed_mode": "control_relaxed_mode",
            "feedback_control_original_mode": "control_original_mode",
            "feedback_control_relax_reason": "control_relax_reason",
            "feedback_generation_limited": "generation_limited",
        }
        override: dict[str, Any] = {}
        for source_key, target_key in field_map.items():
            value = research_task.get(source_key)
            if value in (None, "", [], {}):
                continue
            override[target_key] = value
        return override

    @staticmethod
    def _resolve_budget_feedback_root(snapshot: dict[str, Any]) -> dict[str, Any]:
        factor_research = dict(snapshot.get("factor_research") or {})
        for payload in (
            factor_research.get("lifecycle_feedback_input"),
            factor_research.get("budget_feedback"),
            snapshot.get("family_gate_feedback"),
        ):
            if isinstance(payload, dict):
                feedback_root = dict(
                    normalize_feedback_input_contract(payload).get("feedback") or {}
                )
                if feedback_root:
                    return feedback_root
        return {}
