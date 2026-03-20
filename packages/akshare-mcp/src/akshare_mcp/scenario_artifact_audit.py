from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _extract_counts(text: str) -> list[int]:
    counts: list[int] = []
    for pattern in (
        r"available_tools[^\n]*count\s*=\s*(\d+)",
        r"(?:\*\*)?工具总数(?:\*\*)?[:：]\s*\*\*(\d+)\*\*",
    ):
        counts.extend(int(item) for item in re.findall(pattern, text))
    return sorted(set(counts))


def _extract_scenario_count(text: str) -> int | None:
    match = re.search(r"测试范围[:：]\s*`?scenario_01`?\s*~\s*`?scenario_(\d+)`?", text)
    if match:
        return int(match.group(1))
    match = re.search(r"评估范围[:：]\s*(\d+)个真实应用场景", text)
    if match:
        return int(match.group(1))
    match = re.search(r"#\s+MCP 工具对话式测试结果报告（(\d+)场景）", text)
    if match:
        return int(match.group(1))
    return None


def _extract_step_summary(text: str) -> dict[str, int] | None:
    match = re.search(
        r"\*\*总计\*\*[:：]\s*(\d+)\s*步[，,\s]+(\d+)\s*步通过[，,\s]+(\d+)\s*步部分通过[，,\s]+(\d+)\s*步失败",
        text,
    )
    if not match:
        return None
    return {
        "total_steps": int(match.group(1)),
        "passed_steps": int(match.group(2)),
        "partial_steps": int(match.group(3)),
        "failed_steps": int(match.group(4)),
    }


def audit_scenario_artifacts(
    *,
    report_path: Path,
    readme_path: Path,
    evaluation_path: Path | None = None,
    expected_tool_count: int,
    runtime_tool_count: int,
) -> dict[str, Any]:
    report_text = _read_text(report_path)
    readme_text = _read_text(readme_path)
    evaluation_text = _read_text(evaluation_path) if evaluation_path and evaluation_path.exists() else ""

    report_counts = _extract_counts(report_text)
    readme_counts = _extract_counts(readme_text)
    evaluation_counts = _extract_counts(evaluation_text)
    scenario_count = _extract_scenario_count(report_text) or _extract_scenario_count(readme_text)
    step_summary = _extract_step_summary(report_text)

    warnings: list[str] = []
    if report_counts and any(count != runtime_tool_count for count in report_counts):
        warnings.append(
            f"legacy scenario report baseline {report_counts} differs from runtime tool count {runtime_tool_count}"
        )
    if readme_counts and any(count != runtime_tool_count for count in readme_counts):
        warnings.append(
            f"scenario README baseline {readme_counts} differs from runtime tool count {runtime_tool_count}"
        )
    if expected_tool_count != runtime_tool_count:
        warnings.append(
            f"expected tool count {expected_tool_count} differs from runtime tool count {runtime_tool_count}"
        )

    status = "pass"
    if warnings:
        status = "warn"

    legacy_subset = bool(scenario_count and scenario_count < 20)
    return {
        "status": status,
        "legacy_subset": legacy_subset,
        "scenario_count": scenario_count,
        "runtime_tool_count": runtime_tool_count,
        "expected_tool_count": expected_tool_count,
        "report": {
            "path": str(report_path),
            "baseline_counts": report_counts,
            "step_summary": step_summary,
        },
        "readme": {
            "path": str(readme_path),
            "baseline_counts": readme_counts,
        },
        "evaluation": {
            "path": str(evaluation_path) if evaluation_path else None,
            "baseline_counts": evaluation_counts,
        },
        "warnings": warnings,
        "recommended_actions": [
            "Keep the 12-scenario report labeled as a legacy subset artifact.",
            "Use the runtime tool registry export as the current authoritative baseline.",
            "Re-run and refresh the legacy scenario report when a new manual dialog-based pass is available.",
        ],
    }
