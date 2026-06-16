from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "factories"))

from _quality_session_report import _extract_issue_flags  # noqa: E402


def test_quality_session_flags_split_infra_contract_and_true_quality_failures() -> None:
    flags, notes = _extract_issue_flags(
        {
            "status": "partial",
            "summary": {
                "pipeline_fallback_counts": {"cooldown_skip": 1},
                "submission_lane_counts": {"observe_incubation": 1},
                "submitted": 1,
                "gate_3_passed": 1,
            },
        },
        [
            {
                "admission_block_reasons": [
                    "execution_readiness_tier:missing_executable_contract",
                    "profit_factor 1.2 < 1.8",
                ],
                "quality_report_execution_readiness_tier": "missing_executable_contract",
            }
        ],
    )

    assert "infra_degraded" in flags
    assert "formal_contract_blocked" in flags
    assert "true_quality_blocked" in flags
    assert notes


def test_quality_session_does_not_label_formal_contract_ready_sample_as_contract_blocked() -> None:
    flags, _notes = _extract_issue_flags(
        {
            "status": "success",
            "summary": {
                "submission_lane_counts": {"formal_incubation": 1},
                "submitted": 1,
                "gate_3_passed": 1,
            },
        },
        [
            {
                "admission_block_reasons": ["profit_factor 1.2 < 1.8"],
                "quality_report_execution_readiness_tier": "formal_runtime_ready",
            }
        ],
    )

    assert "formal_contract_blocked" not in flags
    assert "true_quality_blocked" in flags
