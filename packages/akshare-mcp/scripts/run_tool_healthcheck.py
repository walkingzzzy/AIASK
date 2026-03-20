#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import re
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
DOC_MATRIX_PATH = REPO_ROOT / "docs/171工具全量对话式深度测试任务.md"
SCENARIO_ARTIFACT_PATH = PACKAGE_ROOT / "tests/real_world_scenarios/MCP_TOOL_TEST_RESULTS.md"
DATA_QUALITY_ARTIFACT_PATH = PACKAGE_ROOT / "tests/data-quality/DATA_QUALITY_REPORT_CORE.md"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports/tool_healthcheck"
REGISTRY_OUTPUT_DIR = REPO_ROOT / "reports/tool_registry"
SCENARIO_AUDIT_OUTPUT_DIR = REPO_ROOT / "reports/real_world_scenarios"
DEFAULT_EXPECTED_TOOL_COUNT = 171 if platform.system() == "Windows" else 134

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from akshare_mcp.scenario_artifact_audit import audit_scenario_artifacts
from akshare_mcp.tool_registry import build_tool_registry, summarize_tool_registry


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _tail_text(text: str, *, max_lines: int = 40, max_chars: int = 4000) -> str:
    trimmed = "\n".join(text.strip().splitlines()[-max_lines:])
    if len(trimmed) <= max_chars:
        return trimmed
    return trimmed[-max_chars:]


def _parse_coverage_matrix(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "count": 0,
            "tools": [],
            "tool_names": [],
            "missing": True,
        }

    rows: list[dict[str, Any]] = []
    in_matrix = False
    for raw_line in _read_text(path).splitlines():
        line = raw_line.rstrip()
        if re.match(r"^##\s+\d+\s+工具全覆盖矩阵$", line.strip()):
            in_matrix = True
            continue
        if not in_matrix:
            continue
        if line.startswith("## ") and "覆盖率统计" in line:
            break
        match = re.match(r"^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|$", line)
        if not match:
            continue
        rows.append(
            {
                "index": int(match.group(1)),
                "name": match.group(2).strip(),
                "coverage_task": match.group(3).strip(),
            }
        )

    return {
        "path": str(path),
        "count": len(rows),
        "tools": rows,
        "tool_names": [row["name"] for row in rows],
    }


def _inspect_manual_artifact(path: Path, *, expected_count: int) -> dict[str, Any]:
    result = {
        "path": str(path),
        "exists": path.exists(),
        "reported_counts": [],
        "warning": None,
        "modified_at": None,
    }
    if not path.exists():
        result["warning"] = "artifact_missing"
        return result

    stat = path.stat()
    result["modified_at"] = datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds")
    text = _read_text(path)

    counts: list[int] = []
    for pattern in (
        r"available_tools[^\n]*count\s*=\s*(\d+)",
        r"(?:\*\*)?工具总数(?:\*\*)?[:：]\s*\*\*(\d+)\*\*",
    ):
        counts.extend(int(item) for item in re.findall(pattern, text))

    result["reported_counts"] = sorted(set(counts))
    if result["reported_counts"] and any(count != expected_count for count in result["reported_counts"]):
        result["warning"] = "artifact_stale_count"
    return result


def _build_command_plan(mode: str) -> list[dict[str, Any]]:
    quick = [
        {
            "name": "tool_registry_export",
            "cmd": [sys.executable, "scripts/export_tool_registry.py", "--output-dir", str(REGISTRY_OUTPUT_DIR)],
            "timeout": 300,
        },
        {
            "name": "scenario_artifact_audit",
            "cmd": [sys.executable, "scripts/audit_real_world_scenarios.py", "--output-dir", str(SCENARIO_AUDIT_OUTPUT_DIR)],
            "timeout": 300,
        },
        {
            "name": "scenario_artifact_meta",
            "cmd": [sys.executable, "-m", "pytest", "tests/test_scenario_artifact_audit.py", "-q"],
            "timeout": 300,
        },
        {
            "name": "tool_registry_meta",
            "cmd": [sys.executable, "-m", "pytest", "tests/test_tool_registry_meta.py", "-q"],
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
    extended = quick + [
        {
            "name": "limit_up_data_quality",
            "cmd": [sys.executable, "tests/data-quality/test_04_tushare_limit_up.py"],
            "timeout": 180,
        },
        {
            "name": "block_trades_data_quality",
            "cmd": [sys.executable, "tests/data-quality/test_05_tushare_block_trades.py"],
            "timeout": 180,
        },
    ]
    full = extended + [
        {
            "name": "mcp_functional_smoke",
            "cmd": [sys.executable, "tests/test_mcp_functional.py"],
            "timeout": 900,
        },
        {
            "name": "data_quality_core",
            "cmd": [sys.executable, "tests/data-quality/run_core_tests.py"],
            "timeout": 1800,
        },
    ]
    plans = {"quick": quick, "extended": extended, "full": full}
    return plans[mode]


def _run_command(plan: dict[str, Any]) -> dict[str, Any]:
    start = time.perf_counter()
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
        duration = round(time.perf_counter() - start, 2)
        return {
            "name": plan["name"],
            "command": " ".join(plan["cmd"]),
            "timeout": int(plan["timeout"]),
            "status": "pass" if proc.returncode == 0 else "fail",
            "exit_code": proc.returncode,
            "duration_seconds": duration,
            "stdout_tail": _tail_text(proc.stdout),
            "stderr_tail": _tail_text(proc.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        duration = round(time.perf_counter() - start, 2)
        return {
            "name": plan["name"],
            "command": " ".join(plan["cmd"]),
            "timeout": int(plan["timeout"]),
            "status": "fail",
            "exit_code": None,
            "duration_seconds": duration,
            "stdout_tail": _tail_text(exc.stdout or ""),
            "stderr_tail": _tail_text(exc.stderr or ""),
            "error": f"timeout>{plan['timeout']}s",
        }


def _render_markdown(summary: dict[str, Any]) -> str:
    registry = summary["registry"]
    stage_rows = []
    for stage in summary["stages"]:
        stage_rows.append(
            "| {name} | {status} | {duration:.2f}s | `{command}` |".format(
                name=stage["name"],
                status=stage["status"].upper(),
                duration=float(stage["duration_seconds"]),
                command=stage["command"],
            )
        )

    warnings = list(summary["warnings"])
    if summary["scenario_artifact"].get("warning"):
        warnings.append(
            "场景测试结果文档存在基线漂移: "
            f"{summary['scenario_artifact'].get('reported_counts') or ['missing']} vs runtime {registry['runtime_count']}"
        )

    lines = [
        "# AKShare MCP Tool Healthcheck",
        "",
        f"- 运行时间: {summary['executed_at']}",
        f"- 模式: `{summary['mode']}`",
        f"- 总体状态: **{summary['status'].upper()}**",
        "",
        "## 注册表核验",
        "",
        "| 指标 | 数值 |",
        "|------|------|",
        f"| runtime tool count | {registry['runtime_count']} |",
        f"| doc matrix count | {registry['matrix_count']} |",
        f"| expected count | {registry['expected_count']} |",
        f"| missing in runtime | {len(registry['missing_in_runtime'])} |",
        f"| extra in runtime | {len(registry['extra_in_runtime'])} |",
        "",
    ]

    if registry["missing_in_runtime"]:
        lines.extend(
            [
                "### 运行时缺失工具",
                "",
                ", ".join(f"`{name}`" for name in registry["missing_in_runtime"]),
                "",
            ]
        )
    if registry["extra_in_runtime"]:
        lines.extend(
            [
                "### 运行时新增工具",
                "",
                ", ".join(f"`{name}`" for name in registry["extra_in_runtime"]),
                "",
            ]
        )

    lines.extend(
        [
            "## 阶段结果",
            "",
            "| Stage | Status | Duration | Command |",
            "|-------|--------|----------|---------|",
            *stage_rows,
            "",
            "## 人工产物检查",
            "",
            f"- 场景报告: `{summary['scenario_artifact']['path']}`",
            f"- 场景报告计数: `{summary['scenario_artifact']['reported_counts']}`",
        f"- 场景产物审计: `{summary['scenario_audit_artifact']['path']}`",
        f"- 数据质量报告: `{summary['data_quality_artifact']['path']}`",
        f"- Tool registry 导出: `{summary['tool_registry_artifact']['path']}`",
            "",
        ]
    )

    if warnings:
        lines.extend(["## 警告", ""])
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")

    lines.extend(
        [
            "## 建议",
            "",
            "- quick 模式可用于 CI 的结构化回归守卫。",
            "- extended/full 模式用于本地或专机，补充真实数据质量验证。",
            "- 若历史人工文档中的工具计数继续停留在旧值，应在重新跑人工回归后更新报告。",
            "",
        ]
    )
    return "\n".join(lines)


def _write_outputs(output_dir: Path, summary: dict[str, Any]) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"healthcheck_{timestamp}.json"
    md_path = output_dir / f"healthcheck_{timestamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"

    markdown = _render_markdown(summary)
    payload = json.dumps(summary, ensure_ascii=False, indent=2)

    json_path.write_text(payload, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    latest_json.write_text(payload, encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")
    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "latest_json": str(latest_json),
        "latest_markdown": str(latest_md),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AKShare MCP tool healthcheck pipeline.")
    parser.add_argument("--mode", choices=["quick", "extended", "full"], default="quick")
    parser.add_argument("--expected-tools", type=int, default=DEFAULT_EXPECTED_TOOL_COUNT)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    runtime_rows = build_tool_registry()
    runtime_summary = summarize_tool_registry(runtime_rows)
    runtime_tools = [row["name"] for row in runtime_rows]
    matrix = _parse_coverage_matrix(DOC_MATRIX_PATH)
    matrix_tool_names = matrix["tool_names"] or runtime_tools
    matrix_count = int(matrix["count"] or len(matrix_tool_names))

    runtime_set = set(runtime_tools)
    matrix_set = set(matrix_tool_names)
    registry = {
        "runtime_count": len(runtime_tools),
        "matrix_count": matrix_count,
        "expected_count": int(args.expected_tools),
        "missing_in_runtime": sorted(matrix_set - runtime_set),
        "extra_in_runtime": sorted(runtime_set - matrix_set),
        "decorated_tool_count": runtime_summary["decorated_tool_count"],
        "missing_implementation_path_count": runtime_summary["missing_implementation_path_count"],
        "missing_docstring_count": runtime_summary["missing_docstring_count"],
    }

    stages = [_run_command(plan) for plan in _build_command_plan(args.mode)]
    warnings: list[str] = []
    if registry["runtime_count"] != registry["expected_count"]:
        warnings.append(
            f"runtime tool count mismatch: expected {registry['expected_count']}, got {registry['runtime_count']}"
        )
    if not matrix.get("missing") and registry["matrix_count"] != registry["expected_count"]:
        warnings.append(
            f"doc matrix count mismatch: expected {registry['expected_count']}, got {registry['matrix_count']}"
        )
    if matrix.get("missing"):
        warnings.append("coverage matrix doc missing; using runtime registry as baseline")
    if registry["missing_implementation_path_count"] > 0:
        warnings.append(
            f"tool registry has {registry['missing_implementation_path_count']} tool(s) without resolved implementation path"
        )

    has_registry_drift = bool(registry["missing_in_runtime"] or registry["extra_in_runtime"])
    has_stage_failure = any(stage["status"] != "pass" for stage in stages)
    status = "pass"
    if has_registry_drift or has_stage_failure:
        status = "fail"
    elif warnings:
        status = "warn"

    scenario_audit_summary = audit_scenario_artifacts(
        report_path=SCENARIO_ARTIFACT_PATH,
        readme_path=PACKAGE_ROOT / "tests/real_world_scenarios/README.md",
        evaluation_path=PACKAGE_ROOT / "tests/real_world_scenarios/EVALUATION_REPORT.md",
        expected_tool_count=int(args.expected_tools),
        runtime_tool_count=registry["runtime_count"],
    )
    warnings.extend(item for item in scenario_audit_summary.get("warnings", []) if item not in warnings)

    if status != "fail" and warnings:
        status = "warn"

    summary = {
        "executed_at": _iso_now(),
        "mode": args.mode,
        "status": status,
        "registry": registry,
        "scenario_artifact": _inspect_manual_artifact(
            SCENARIO_ARTIFACT_PATH,
            expected_count=int(args.expected_tools),
        ),
        "scenario_audit_artifact": {
            "path": str(SCENARIO_AUDIT_OUTPUT_DIR / "latest.json"),
            "summary": scenario_audit_summary,
        },
        "data_quality_artifact": _inspect_manual_artifact(
            DATA_QUALITY_ARTIFACT_PATH,
            expected_count=int(args.expected_tools),
        ),
        "tool_registry_artifact": {
            "path": str(REGISTRY_OUTPUT_DIR / "latest.json"),
            "summary": runtime_summary,
        },
        "stages": stages,
        "warnings": warnings,
    }
    outputs = _write_outputs(Path(args.output_dir), summary)

    print(json.dumps({"status": status, "outputs": outputs}, ensure_ascii=False, indent=2))
    return 1 if status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
