#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
PACKAGE_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[3]
SRC_ROOT = PACKAGE_ROOT / "src"
REPORT_DIR = REPO_ROOT / "reports/tool_healthcheck"
DOC_MATRIX_PATH = REPO_ROOT / "docs/171工具全量对话式深度测试任务.md"
SCENARIO_REPORT_PATH = PACKAGE_ROOT / "tests/real_world_scenarios/MCP_TOOL_TEST_RESULTS.md"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from akshare_mcp.scenario_artifact_audit import audit_scenario_artifacts
from akshare_mcp.tool_registry import build_tool_registry


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _tail(text: str, *, lines: int = 30, chars: int = 3000) -> str:
    trimmed = "\n".join((text or "").strip().splitlines()[-lines:])
    return trimmed if len(trimmed) <= chars else trimmed[-chars:]


def _matrix_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(
        1
        for line in _read_text(path).splitlines()
        if line.startswith("| ") and "`" in line and line.split("|", 2)[1].strip().isdigit()
    )


def _build_command_plan(mode: str) -> list[dict[str, Any]]:
    quick = [
        {
            "name": "tool_registry_export",
            "cmd": [sys.executable, "scripts/export_tool_registry.py"],
            "timeout": 300,
        },
        {
            "name": "scenario_artifact_audit",
            "cmd": [sys.executable, "scripts/audit_real_world_scenarios.py"],
            "timeout": 300,
        },
        {
            "name": "tool_registry_meta",
            "cmd": [sys.executable, "-m", "pytest", "tests/test_tool_registry_meta.py", "-q"],
            "timeout": 300,
        },
        {
            "name": "scenario_artifact_meta",
            "cmd": [sys.executable, "-m", "pytest", "tests/test_scenario_artifact_audit.py", "-q"],
            "timeout": 300,
        },
        {
            "name": "tool_quality_meta",
            "cmd": [sys.executable, "-m", "pytest", "tests/test_tool_quality_meta.py", "-q"],
            "timeout": 300,
        },
        {
            "name": "p0_regressions",
            "cmd": [sys.executable, "-m", "pytest", "tests/test_p0_regressions.py", "-q"],
            "timeout": 600,
        },
    ]
    full = quick + [
        {
            "name": "mcp_functional_smoke",
            "cmd": [sys.executable, "tests/test_mcp_functional.py"],
            "timeout": 900,
        },
        {
            "name": "data_quality_core",
            "cmd": [sys.executable, "tests/data-quality/run_core_tests.py"],
            "timeout": 1200,
        },
    ]
    return {"quick": quick, "full": full}[mode]


def _run_stage(plan: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{SRC_ROOT}{os.pathsep}{pythonpath}" if pythonpath else str(SRC_ROOT)

    try:
        proc = subprocess.run(
            plan["cmd"],
            cwd=PACKAGE_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=int(plan["timeout"]),
            check=False,
        )
        return {
            "name": plan["name"],
            "command": " ".join(plan["cmd"]),
            "status": "pass" if proc.returncode == 0 else "fail",
            "exit_code": proc.returncode,
            "duration_seconds": round(time.perf_counter() - started, 2),
            "stdout_tail": _tail(proc.stdout),
            "stderr_tail": _tail(proc.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": plan["name"],
            "command": " ".join(plan["cmd"]),
            "status": "fail",
            "exit_code": None,
            "duration_seconds": round(time.perf_counter() - started, 2),
            "stdout_tail": _tail(exc.stdout or ""),
            "stderr_tail": _tail(exc.stderr or ""),
            "error": f"timeout>{plan['timeout']}s",
        }


def _render_markdown(summary: dict[str, Any]) -> str:
    matrix_label = (
        str(summary["matrix_tool_count"])
        if summary["matrix_tool_count"] > 0
        else "runtime fallback"
    )
    lines = [
        "# AKShare MCP Release Gate",
        "",
        f"- 运行时间: {summary['executed_at']}",
        f"- 模式: `{summary['mode']}`",
        f"- 总体状态: **{summary['status'].upper()}**",
        f"- runtime tool count: `{summary['runtime_tool_count']}`",
        f"- expected tool baseline: `{matrix_label}`",
        f"- scenario baseline: `{summary['scenario_baseline_counts']}`",
        "",
        "## Stage Results",
        "",
        "| Stage | Status | Duration | Command |",
        "|-------|--------|----------|---------|",
    ]
    for stage in summary["stages"]:
        lines.append(
            f"| {stage['name']} | {stage['status'].upper()} | {float(stage['duration_seconds']):.2f}s | `{stage['command']}` |"
        )

    if summary["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in summary["warnings"])

    lines.extend(["", "## Outputs", ""])
    lines.append(f"- latest json: `{summary['latest_json']}`")
    lines.append(f"- latest markdown: `{summary['latest_markdown']}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the AKShare MCP release gate.")
    parser.add_argument("--mode", choices=("quick", "full"), default="full")
    parser.add_argument("--output-dir", default=str(REPORT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    plans = _build_command_plan(args.mode)
    stages = [_run_stage(plan) for plan in plans]
    runtime_tool_count = len(build_tool_registry())
    matrix_tool_count = _matrix_count(DOC_MATRIX_PATH)
    expected_tool_count = matrix_tool_count or runtime_tool_count
    scenario_payload = audit_scenario_artifacts(
        report_path=SCENARIO_REPORT_PATH,
        readme_path=PACKAGE_ROOT / "tests/real_world_scenarios/README.md",
        evaluation_path=PACKAGE_ROOT / "tests/real_world_scenarios/EVALUATION_REPORT.md",
        expected_tool_count=expected_tool_count,
        runtime_tool_count=runtime_tool_count,
    )
    scenario_baseline_counts = scenario_payload.get("report", {}).get("baseline_counts", [])

    warnings: list[str] = []
    if matrix_tool_count and runtime_tool_count != matrix_tool_count:
        warnings.append(f"runtime tool count {runtime_tool_count} != doc matrix count {matrix_tool_count}")
    if scenario_baseline_counts and any(count != runtime_tool_count for count in scenario_baseline_counts):
        warnings.append(
            f"scenario baseline stale: {scenario_baseline_counts} vs runtime {runtime_tool_count}"
        )
    if scenario_payload.get("status") == "fail":
        warnings.append("scenario artifact audit failed")

    overall_status = "pass" if all(stage["status"] == "pass" for stage in stages) and not warnings else "fail"
    payload = {
        "executed_at": _now_iso(),
        "mode": args.mode,
        "status": overall_status,
        "runtime_tool_count": runtime_tool_count,
        "matrix_tool_count": expected_tool_count,
        "scenario_baseline_counts": scenario_baseline_counts,
        "scenario_audit_status": scenario_payload.get("status"),
        "warnings": warnings,
        "stages": stages,
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"release_gate_{timestamp}.json"
    md_path = output_dir / f"release_gate_{timestamp}.md"
    latest_json = output_dir / "release_gate_latest.json"
    latest_md = output_dir / "release_gate_latest.md"

    payload["latest_json"] = str(latest_json)
    payload["latest_markdown"] = str(latest_md)

    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    md_text = _render_markdown(payload)
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")

    print(json.dumps({"status": overall_status, "latest_json": str(latest_json), "latest_markdown": str(latest_md)}, ensure_ascii=False, indent=2))
    return 0 if overall_status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
