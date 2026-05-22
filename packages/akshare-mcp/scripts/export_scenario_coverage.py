#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
PACKAGE_ROOT = SCRIPT_PATH.parents[1]
SRC_ROOT = PACKAGE_ROOT / "src"
REPO_ROOT = SCRIPT_PATH.parents[3]
DOC_MATRIX_PATH = REPO_ROOT / "docs/171工具全量对话式深度测试任务.md"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports/real_world_scenarios"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from akshare_mcp.scenario_coverage_matrix import merge_runtime_with_coverage, parse_coverage_matrix
from akshare_mcp.tool_registry import build_tool_registry


def _render_markdown(payload: dict) -> str:
    summary = payload["summary"]
    tools = payload["tools"]
    lines = [
        "# Scenario Coverage Matrix",
        "",
        f"- 导出时间: {payload['generated_at']}",
        f"- runtime tool count: **{summary['runtime_tool_count']}**",
        f"- coverage matrix count: **{summary['coverage_matrix_count']}**",
        f"- uncovered runtime tools: **{summary['uncovered_runtime_count']}**",
        f"- missing in runtime: **{summary['missing_in_runtime_count']}**",
        f"- multi-task tools: **{summary['multi_task_tool_count']}**",
        "",
        "| # | Tool | Category | Coverage Tasks | Runtime |",
        "|---|------|----------|----------------|---------|",
    ]
    for row in tools:
        coverage_index = row.get("coverage_index") or "-"
        coverage_text = row.get("coverage_task_text") or "-"
        category = row.get("category") or "-"
        runtime_status = "yes" if row.get("runtime_registered") else "no"
        lines.append(
            f"| {coverage_index} | `{row['name']}` | `{category}` | {coverage_text} | {runtime_status} |"
        )

    if payload["uncovered_runtime"]:
        lines.extend(["", "## Uncovered Runtime Tools", ""])
        lines.extend(f"- `{name}`" for name in payload["uncovered_runtime"])
    if payload["missing_in_runtime"]:
        lines.extend(["", "## Missing In Runtime", ""])
        lines.extend(f"- `{name}`" for name in payload["missing_in_runtime"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the 171-tool scenario coverage matrix.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    runtime_rows = build_tool_registry()
    coverage_rows = parse_coverage_matrix(DOC_MATRIX_PATH)
    merged = merge_runtime_with_coverage(runtime_rows, coverage_rows)
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        **merged,
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"scenario_coverage_{timestamp}.json"
    md_path = output_dir / f"scenario_coverage_{timestamp}.md"
    latest_json = output_dir / "scenario_coverage_latest.json"
    latest_md = output_dir / "scenario_coverage_latest.md"

    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    md_text = _render_markdown(payload)
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")

    print(
        json.dumps(
            {
                "summary": payload["summary"],
                "latest_json": str(latest_json),
                "latest_markdown": str(latest_md),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if summary_ok(payload["summary"]) else 1


def summary_ok(summary: dict) -> bool:
    return (
        int(summary.get("runtime_tool_count", 0)) == int(summary.get("coverage_matrix_count", -1))
        and int(summary.get("missing_in_runtime_count", 0)) == 0
        and int(summary.get("uncovered_runtime_count", 0)) == 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
