

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_research_plane_detail(data: dict[str, Any]) -> dict[str, Any]:
    raw = dict(data or {})
    research_plane = dict(raw.get("research_plane") or {})
    if research_plane:
        return research_plane
    snapshot = dict(raw.get("snapshot") or {})
    stages = dict(raw.get("stages") or {})
    factor_stage = dict(stages.get("factor_research") or {})
    autonomy_stage = dict(stages.get("autonomy") or {})
    factor_research = dict(raw.get("factor_research") or snapshot.get("factor_research") or {})
    if factor_stage.get("research_artifact") and not factor_research.get("research_artifact"):
        factor_research = {
            **factor_research,
            "research_artifact": dict(factor_stage.get("research_artifact") or {}),
        }
    experiments_payload = dict(raw.get("experiments") or {})
    experiments = list(experiments_payload.get("items") or raw.get("experiment_records") or [])
    return build_research_plane_artifact(
        factor_research=factor_research,
        readiness=dict(raw.get("readiness") or {}),
        autonomy_stage=autonomy_stage,
        candidates=list(raw.get("candidates") or []),
        experiments=experiments,
    )


def _normalize_governance_plane_detail(data: dict[str, Any]) -> dict[str, Any]:
    raw = dict(data or {})
    governance_plane = dict(raw.get("governance_plane") or {})
    if governance_plane:
        return governance_plane

    stages = dict(raw.get("stages") or {})
    quality_gate_report = dict(
        raw.get("quality_gate")
        or raw.get("gate_report")
        or stages.get("quality_gate")
        or {}
    )
    backtest_report = dict(
        raw.get("backtest_report")
        or stages.get("backtest")
        or {}
    )
    dedup_report = dict(
        raw.get("dedup_report")
        or stages.get("deduplicate")
        or {}
    )
    submit_result = dict(
        raw.get("submit_result")
        or stages.get("submit")
        or {}
    )
    return build_governance_plane_artifact(
        candidates=list(raw.get("candidates") or []),
        quality_gate_report=quality_gate_report,
        backtest_report=backtest_report,
        dedup_report=dedup_report,
        submit_result=submit_result,
    )

def normalize_run_result_to_detail(data: dict[str, Any]) -> FactoryRunDetailDTO:
    """Convert a raw cycle-runner result dict to a stable detail DTO."""
    return FactoryRunDetailDTO.from_dict(data)


def normalize_run_result_to_summary(data: dict[str, Any]) -> FactoryRunSummaryDTO:
    """Convert a raw cycle-runner result dict to a stable summary DTO."""
    return FactoryRunSummaryDTO.from_dict(data)


__all__ = [
    "FactoryRunDetailDTO",
    "FactoryRunSummaryDTO",
    "FactoryStatusDTO",
    "StageResultDTO",
    "normalize_run_result_to_detail",
    "normalize_run_result_to_summary",
]
