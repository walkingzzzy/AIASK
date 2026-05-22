

# ---------------------------------------------------------------------------
# Factory run detail DTO
# ---------------------------------------------------------------------------

@dataclass
class FactoryRunDetailDTO:
    """DTO for a complete factory run detail, including per-stage breakdown."""

    summary: FactoryRunSummaryDTO
    stages: list[StageResultDTO] = field(default_factory=list)
    snapshot_summary: dict[str, Any] = field(default_factory=dict)
    quality_gate: dict[str, Any] = field(default_factory=dict)
    research_summary: dict[str, Any] = field(default_factory=dict)
    research_plane: dict[str, Any] = field(default_factory=dict)
    research_artifact: dict[str, Any] = field(default_factory=dict)
    task_artifact: dict[str, Any] = field(default_factory=dict)
    candidate_artifact: dict[str, Any] = field(default_factory=dict)
    evidence_artifact: dict[str, Any] = field(default_factory=dict)
    governance_plane: dict[str, Any] = field(default_factory=dict)
    gate_artifact: dict[str, Any] = field(default_factory=dict)
    gate_artifact_v2: dict[str, Any] = field(default_factory=dict)
    dedup_artifact: dict[str, Any] = field(default_factory=dict)
    submission_artifact: dict[str, Any] = field(default_factory=dict)
    governance_evidence_artifact: dict[str, Any] = field(default_factory=dict)
    gate_a: dict[str, Any] = field(default_factory=dict)
    gate_b: dict[str, Any] = field(default_factory=dict)
    gate_c: dict[str, Any] = field(default_factory=dict)
    protocol_versions: dict[str, Any] = field(default_factory=dict)
    prediction_trace_summary: dict[str, Any] = field(default_factory=dict)
    feedback_summary: dict[str, Any] = field(default_factory=dict)
    incubation_summary: dict[str, Any] = field(default_factory=dict)
    live_ready_summary: dict[str, Any] = field(default_factory=dict)
    artifact_refs: list[dict[str, Any]] = field(default_factory=list)
    parity_result: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FactoryRunDetailDTO":
        d = dict(data or {})
        summary_dto = FactoryRunSummaryDTO.from_dict(d)
        raw_summary = dict(d.get("summary") or {})
        raw_stages = dict(d.get("stages") or {})
        stage_payloads = {
            name: payload
            for name, payload in raw_stages.items()
            if isinstance(payload, dict)
        }
        research_plane = _normalize_research_plane_detail(d)
        governance_plane = _normalize_governance_plane_detail(d)
        stages = [
            StageResultDTO.from_dict(name, payload)
            for name, payload in stage_payloads.items()
        ]
        return cls(
            summary=summary_dto,
            stages=stages,
            snapshot_summary=dict(d.get("snapshot_summary") or {}),
            quality_gate=dict(d.get("quality_gate") or d.get("gate_report") or {}),
            research_summary=dict(raw_summary.get("research_summary") or {}),
            research_plane=research_plane,
            research_artifact=dict(research_plane.get("research_artifact") or {}),
            task_artifact=dict(research_plane.get("task_artifact") or {}),
            candidate_artifact=dict(research_plane.get("candidate_artifact") or {}),
            evidence_artifact=dict(research_plane.get("evidence_artifact") or {}),
            governance_plane=governance_plane,
            gate_artifact=dict(governance_plane.get("gate_artifact") or {}),
            gate_artifact_v2=dict(governance_plane.get("gate_artifact_v2") or {}),
            dedup_artifact=dict(governance_plane.get("dedup_artifact") or {}),
            submission_artifact=dict(governance_plane.get("submission_artifact") or {}),
            governance_evidence_artifact=dict(governance_plane.get("evidence_artifact") or {}),
            gate_a=dict(governance_plane.get("gate_a") or {}),
            gate_b=dict(governance_plane.get("gate_b") or {}),
            gate_c=dict(governance_plane.get("gate_c") or {}),
            protocol_versions=dict(governance_plane.get("protocol_versions") or {}),
            prediction_trace_summary=dict(governance_plane.get("prediction_trace_summary") or {}),
            feedback_summary=dict(raw_summary.get("feedback_summary") or {}),
            incubation_summary=dict(raw_summary.get("incubation_summary") or {}),
            live_ready_summary=dict(raw_summary.get("live_ready_summary") or {}),
            artifact_refs=[
                dict(item or {})
                for item in list(d.get("artifact_refs") or summary_dto.artifact_refs or [])
                if isinstance(item, dict)
            ],
            parity_result=dict(d.get("parity_result") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.summary.to_dict(),
            "stages": {s.stage: s.to_dict() for s in self.stages},
            "snapshot_summary": self.snapshot_summary,
            "quality_gate": self.quality_gate,
            "research_summary": self.research_summary,
            "research_plane": self.research_plane,
            "research_artifact": self.research_artifact,
            "task_artifact": self.task_artifact,
            "candidate_artifact": self.candidate_artifact,
            "evidence_artifact": self.evidence_artifact,
            "governance_plane": self.governance_plane,
            "gate_artifact": self.gate_artifact,
            "gate_artifact_v2": self.gate_artifact_v2,
            "dedup_artifact": self.dedup_artifact,
            "submission_artifact": self.submission_artifact,
            "governance_evidence_artifact": self.governance_evidence_artifact,
            "gate_a": self.gate_a,
            "gate_b": self.gate_b,
            "gate_c": self.gate_c,
            "protocol_versions": self.protocol_versions,
            "prediction_trace_summary": self.prediction_trace_summary,
            "feedback_summary": self.feedback_summary,
            "incubation_summary": self.incubation_summary,
            "live_ready_summary": self.live_ready_summary,
            "artifact_refs": list(self.artifact_refs),
            "parity_result": dict(self.parity_result),
        }

    def get_stage(self, name: str) -> Optional[StageResultDTO]:
        for s in self.stages:
            if s.stage == name:
                return s
        return None

    def failed_stages(self) -> list[str]:
        return [s.stage for s in self.stages if s.status == StageStatus.FAILED.value]

    def partial_stages(self) -> list[str]:
        return [s.stage for s in self.stages if s.status == StageStatus.PARTIAL.value]
