from pathlib import Path

from akshare_mcp.scenario_artifact_audit import audit_scenario_artifacts
from akshare_mcp.tool_registry import build_tool_registry


def test_scenario_artifact_audit_should_accept_legacy_subset_with_current_baseline():
    package_root = Path(__file__).resolve().parents[1]
    runtime_count = len(build_tool_registry())
    payload = audit_scenario_artifacts(
        report_path=package_root / "tests/real_world_scenarios/MCP_TOOL_TEST_RESULTS.md",
        readme_path=package_root / "tests/real_world_scenarios/README.md",
        evaluation_path=package_root / "tests/real_world_scenarios/EVALUATION_REPORT.md",
        expected_tool_count=runtime_count,
        runtime_tool_count=runtime_count,
    )

    assert payload["status"] in ("pass", "warn")
    assert payload["legacy_subset"] is True
    assert payload["scenario_count"] == 12
    assert payload["runtime_tool_count"] == runtime_count
    assert len(payload["report"]["baseline_counts"]) >= 1
    assert payload["report"]["step_summary"]["total_steps"] == 85
    if payload["report"]["baseline_counts"] != [runtime_count]:
        assert payload["status"] == "warn", "status should be 'warn' when legacy baseline differs from runtime"
