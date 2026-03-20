#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
PACKAGE_ROOT = SCRIPT_PATH.parents[1]
SRC_ROOT = PACKAGE_ROOT / "src"
REPO_ROOT = SCRIPT_PATH.parents[3]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports/real_world_scenarios"
REPORT_PATH = PACKAGE_ROOT / "tests/real_world_scenarios/MCP_TOOL_TEST_RESULTS.md"
README_PATH = PACKAGE_ROOT / "tests/real_world_scenarios/README.md"
EVALUATION_PATH = PACKAGE_ROOT / "tests/real_world_scenarios/EVALUATION_REPORT.md"
DOC_MATRIX_PATH = REPO_ROOT / "docs/171工具全量对话式深度测试任务.md"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from akshare_mcp.scenario_artifact_audit import audit_scenario_artifacts
from akshare_mcp.tool_registry import build_tool_registry


def _matrix_count(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="ignore")
    return sum(
        1
        for line in text.splitlines()
        if line.startswith("| ") and "`" in line and re.match(r"^\|\s*\d+\s*\|", line)
    )


def _render_markdown(payload: dict) -> str:
    report = payload["report"]
    step_summary = report.get("step_summary") or {}
    lines = [
        "# Real World Scenario Artifact Audit",
        "",
        f"- 运行时间: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- 总体状态: **{payload['status'].upper()}**",
        f"- legacy subset: `{payload['legacy_subset']}`",
        f"- 场景数量: `{payload['scenario_count']}`",
        f"- runtime tool count: `{payload['runtime_tool_count']}`",
        f"- expected tool count: `{payload['expected_tool_count']}`",
        "",
        "## 历史产物",
        "",
        f"- 结果报告: `{report['path']}`",
        f"- 报告基线工具数: `{report['baseline_counts']}`",
        f"- README: `{payload['readme']['path']}`",
        f"- 评估报告: `{payload['evaluation']['path']}`",
        "",
    ]
    if step_summary:
        lines.extend(
            [
                "## 历史执行摘要",
                "",
                f"- total_steps: `{step_summary['total_steps']}`",
                f"- passed_steps: `{step_summary['passed_steps']}`",
                f"- partial_steps: `{step_summary['partial_steps']}`",
                f"- failed_steps: `{step_summary['failed_steps']}`",
                "",
            ]
        )
    if payload["warnings"]:
        lines.extend(["## 警告", ""])
        lines.extend(f"- {warning}" for warning in payload["warnings"])
        lines.append("")
    lines.extend(["## 建议", ""])
    lines.extend(f"- {item}" for item in payload["recommended_actions"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit legacy real-world scenario artifacts.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    runtime_tool_count = len(build_tool_registry())
    expected_tool_count = _matrix_count(DOC_MATRIX_PATH) or runtime_tool_count
    payload = audit_scenario_artifacts(
        report_path=REPORT_PATH,
        readme_path=README_PATH,
        evaluation_path=EVALUATION_PATH,
        expected_tool_count=expected_tool_count,
        runtime_tool_count=runtime_tool_count,
    )
    payload["generated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"scenario_artifact_audit_{timestamp}.json"
    md_path = output_dir / f"scenario_artifact_audit_{timestamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"

    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    md_text = _render_markdown(payload)

    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")

    print(
        json.dumps(
            {
                "status": payload["status"],
                "outputs": {
                    "json": str(json_path),
                    "markdown": str(md_path),
                    "latest_json": str(latest_json),
                    "latest_markdown": str(latest_md),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if payload["status"] != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
