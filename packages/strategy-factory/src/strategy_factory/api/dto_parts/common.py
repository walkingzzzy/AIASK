
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..application.governance_plane_contract import build_governance_plane_artifact
from ..application.research_plane_contract import build_research_plane_artifact
from ..application.run_models import FactoryRunStatus, StageStatus, normalize_run_status, normalize_stage_status


# ---------------------------------------------------------------------------
# Stage DTO
# ---------------------------------------------------------------------------

@dataclass
class StageResultDTO:
    """DTO for a single stage within a factory run."""

    stage: str
    status: str
    ok: bool
    hard_failure: bool
    degraded: bool
    skip_reason: Optional[str]
    warning_count: int
    blocker_count: int
    persistence_failure_count: int

    @classmethod
    def from_dict(cls, stage: str, data: Any) -> "StageResultDTO":
        d = dict(data) if isinstance(data, dict) else {}
        status_enum = normalize_stage_status(d.get("status"))
        return cls(
            stage=stage,
            status=status_enum.value,
            ok=bool(d.get("ok", True)),
            hard_failure=bool(d.get("hard_failure")),
            degraded=bool(d.get("degraded")),
            skip_reason=d.get("skip_reason"),
            warning_count=int(d.get("warning_count") or 0),
            blocker_count=int(d.get("blocker_count") or 0),
            persistence_failure_count=int(d.get("persistence_failure_count") or 0),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "stage": self.stage,
            "status": self.status,
            "ok": self.ok,
            "hard_failure": self.hard_failure,
            "degraded": self.degraded,
            "warning_count": self.warning_count,
            "blocker_count": self.blocker_count,
            "persistence_failure_count": self.persistence_failure_count,
        }
        if self.skip_reason:
            result["skip_reason"] = self.skip_reason
        return result
