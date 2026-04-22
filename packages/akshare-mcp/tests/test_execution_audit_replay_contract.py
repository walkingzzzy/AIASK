from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_script_module(module_name: str, script_name: str):
    script_path = REPO_ROOT / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_acceptance_script_rejects_blocker_taxonomy_drift():
    acceptance_mod = _load_script_module(
        "strategy_execution_audit_acceptance_test",
        "strategy-execution-audit-acceptance.py",
    )

    with pytest.raises(ValueError, match="contract mismatch"):
        acceptance_mod._normalize_detail_dimension(
            top_level_values=["insufficient_samples"],
            blocker_details=[{"blocker": "promotion_hard_gate_pending"}],
            detail_key="blocker",
            field_name="blockers",
            strategy_id="strategy-gap",
        )


def test_replay_loader_selects_sample_gap_rows_from_acceptance_report(tmp_path: Path):
    replay_mod = _load_script_module(
        "strategy_incubation_history_replay_test",
        "strategy-incubation-history-replay.py",
    )
    report_path = tmp_path / "execution_audit_acceptance.json"
    report_path.write_text(
        json.dumps(
            {
                "report_type": "execution_audit_acceptance",
                "schema_version": "execution_audit_acceptance.v2",
                "strategy_results": [
                    {
                        "strategy_id": "strategy-gap",
                        "has_sample_gap": True,
                        "blockers": ["promotion_hard_gate_pending"],
                        "gap_categories": ["sample_gap"],
                        "blocker_details": [
                            {
                                "blocker": "promotion_hard_gate_pending",
                                "category": "sample_gap",
                            }
                        ],
                    },
                    {
                        "strategy_id": "strategy-metrics",
                        "has_sample_gap": False,
                        "blockers": ["failed_metrics"],
                        "gap_categories": ["performance_gap"],
                        "blocker_details": [
                            {
                                "blocker": "failed_metrics",
                                "category": "performance_gap",
                            }
                        ],
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    assert replay_mod._load_strategy_ids_from_acceptance_report(
        report_path,
        sample_gap_only=True,
    ) == ["strategy-gap"]


def test_replay_acceptance_summary_recognizes_bootstrap_ready_as_sample_gap():
    replay_mod = _load_script_module(
        "strategy_incubation_history_replay_summary_test",
        "strategy-incubation-history-replay.py",
    )

    summary = replay_mod._summarize_acceptance(
        {
            "status": "needs_attention",
            "acceptance_matrix": {"overall_ready": False},
            "blockers": ["promotion_hard_gate_pending"],
            "gap_categories": ["sample_gap"],
            "trade_audit_summary": {
                "execution_audit_gate_status": "bootstrap_ready",
                "realized_trade_count": 5,
            },
        }
    )

    assert summary["overall_ready"] is False
    assert summary["has_sample_gap"] is True
    assert summary["execution_audit_gate_status"] == "bootstrap_ready"
    assert summary["realized_trade_count"] == 5
    assert summary["blockers"] == ["promotion_hard_gate_pending"]
