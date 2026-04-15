#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SERVER_TOOL_TUPLE_PATTERN = re.compile(r"_(?:core|heavy)_tool_names\s*=\s*\((?P<body>.*?)\)", re.S)
MODULE_NAME_PATTERN = re.compile(r'"([A-Za-z0-9_]+)"')
SERVER_REGISTER_PATTERN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\.register\(app\)", re.M)
DECORATOR_TOOL_PATTERN = re.compile(
    r"@[A-Za-z_][A-Za-z0-9_\.]*\.tool(?:\([^\n]*\))?\s*\n\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
    re.M,
)
CALL_TOOL_PATTERN = re.compile(
    r"[A-Za-z_][A-Za-z0-9_\.]*\.tool\s*\(\s*\)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
    re.M,
)
CODE_SPAN_PATTERN = re.compile(r"`([^`]+)`")
SPAN_HEAD_PATTERN = re.compile(r"^\s*([a-z][a-z0-9_]*)(?:\s*\(|\s*$)")


@dataclass
class SkillCoverage:
    skill: str
    file: str
    referenced_tools: list[str]
    refs_unknown: list[str]

    def to_dict(self) -> dict:
        return {
            "skill": self.skill,
            "file": self.file,
            "referenced_tools": self.referenced_tools,
            "refs_unknown": self.refs_unknown,
        }


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _looks_like_tool_name(name: str) -> bool:
    if not name or "_" not in name:
        return False
    return name.endswith("_manager") or name.startswith(
        (
            "get_",
            "list_",
            "search_",
            "calculate_",
            "analyze_",
            "create_",
            "delete_",
            "update_",
            "remove_",
            "add_",
            "run_",
            "check_",
            "clear_",
            "sync_",
            "send_",
            "push_",
            "parse_",
            "optimize_",
            "validate_",
            "should_",
        )
    )


def _discover_server_modules(server_text: str) -> list[str]:
    module_names: set[str] = set()

    for match in SERVER_TOOL_TUPLE_PATTERN.finditer(server_text):
        module_names.update(MODULE_NAME_PATTERN.findall(match.group("body")))

    module_names.update(SERVER_REGISTER_PATTERN.findall(server_text))
    module_names.discard("app")

    return sorted(module_names)


def discover_runtime_tools(server_file: Path, tools_dir: Path) -> tuple[list[str], list[Path]]:
    server_text = _load_text(server_file)
    module_names = _discover_server_modules(server_text)
    if not module_names:
        raise RuntimeError(f"Cannot find registered tool modules in {server_file}")
    candidate_files: list[Path] = []

    for module in module_names:
        module_file = tools_dir / f"{module}.py"
        if module_file.exists():
            candidate_files.append(module_file)
        module_dir = tools_dir / module
        if module_dir.is_dir():
            candidate_files.extend(sorted(module_dir.rglob("*.py")))

    candidate_files.append(server_file)
    unique_files = sorted(set(candidate_files))

    tool_names: set[str] = set()
    for path in unique_files:
        text = _load_text(path)
        tool_names.update(DECORATOR_TOOL_PATTERN.findall(text))
        tool_names.update(CALL_TOOL_PATTERN.findall(text))

    if not tool_names:
        raise RuntimeError("No tools discovered. Check parser patterns.")

    return sorted(tool_names), unique_files


def parse_skill_markdown(skill_name: str, skill_file: Path, all_tools: set[str]) -> SkillCoverage:
    text = _load_text(skill_file)
    referenced: set[str] = set()
    unknown: set[str] = set()

    for span in CODE_SPAN_PATTERN.findall(text):
        match = SPAN_HEAD_PATTERN.match(span.strip())
        if not match:
            continue
        name = match.group(1)
        if "_" not in name:
            continue
        if name in all_tools:
            referenced.add(name)
        # 只把可能是工具名的未知引用记录下来（避免把参数名当工具）
        elif _looks_like_tool_name(name):
            unknown.add(name)

    return SkillCoverage(
        skill=skill_name,
        file=str(skill_file.as_posix()),
        referenced_tools=sorted(referenced),
        refs_unknown=sorted(unknown),
    )


def collect_skill_coverages(skills_dir: Path, all_tools: set[str]) -> list[SkillCoverage]:
    coverage_items: list[SkillCoverage] = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name.startswith("_") or skill_dir.name.startswith("."):
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        coverage_items.append(parse_skill_markdown(skill_dir.name, skill_file, all_tools))
    return coverage_items


def discover_skill_executors(skills_tool_file: Path) -> dict:
    if not skills_tool_file.is_file():
        return {
            "skill_tool_file": str(skills_tool_file.as_posix()),
            "executable_skill_ids": [],
            "executor_count": 0,
        }

    text = _load_text(skills_tool_file)
    try:
        tree = ast.parse(text, filename=str(skills_tool_file))
    except SyntaxError:
        return {
            "skill_tool_file": str(skills_tool_file.as_posix()),
            "executable_skill_ids": [],
            "executor_count": 0,
            "parse_error": "syntax_error",
        }

    executable_skill_ids: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_SKILL_EXECUTORS" and isinstance(node.value, ast.Dict):
                    for key_node in node.value.keys:
                        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                            executable_skill_ids.add(key_node.value)
                    break
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == "_SKILL_EXECUTORS" and isinstance(node.value, ast.Dict):
                for key_node in node.value.keys:
                    if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                        executable_skill_ids.add(key_node.value)

    return {
        "skill_tool_file": str(skills_tool_file.as_posix()),
        "executable_skill_ids": sorted(executable_skill_ids),
        "executor_count": len(executable_skill_ids),
    }


def detect_module_name_collisions(package_root: Path) -> list[dict]:
    """Detect file-package collisions like market.py + market/__init__.py in the same package dir."""
    if not package_root.is_dir():
        return []

    collisions: list[dict] = []
    package_dirs = [d for d in package_root.rglob("*") if d.is_dir() and (d / "__init__.py").exists()]
    package_dirs.insert(0, package_root)

    for pkg_dir in sorted(set(package_dirs)):
        py_files = {
            p.stem: p
            for p in pkg_dir.glob("*.py")
            if p.name != "__init__.py"
        }
        sub_packages = {
            d.name: d
            for d in pkg_dir.iterdir()
            if d.is_dir() and (d / "__init__.py").exists()
        }

        for name in sorted(set(py_files) & set(sub_packages)):
            collisions.append(
                {
                    "package_dir": str(pkg_dir.as_posix()),
                    "name": name,
                    "module_file": str(py_files[name].as_posix()),
                    "package_init": str((sub_packages[name] / "__init__.py").as_posix()),
                }
            )

    return collisions


def compute_report(
    repo_root: Path,
    all_tools: list[str],
    tool_source_files: list[Path],
    skill_coverages: list[SkillCoverage],
    module_name_collisions: list[dict],
    skill_executor_audit: dict,
) -> dict:
    all_tools_set = set(all_tools)
    union_covered = sorted(
        {
            tool
            for item in skill_coverages
            for tool in item.referenced_tools
            if tool in all_tools_set
        }
    )
    missing_tools = sorted(all_tools_set - set(union_covered))

    manager_tools = sorted([tool for tool in all_tools if tool.endswith("_manager")])
    covered_manager = sorted(set(union_covered) & set(manager_tools))

    unknown_refs = [
        {"skill": item.skill, "refs_unknown": item.refs_unknown}
        for item in skill_coverages
        if item.refs_unknown
    ]

    tool_count = len(all_tools)
    covered_count = len(union_covered)
    manager_total = len(manager_tools)
    registry_skill_ids = sorted(item.skill for item in skill_coverages)
    executable_skill_ids = sorted(
        set(skill_executor_audit.get("executable_skill_ids") or []) & set(registry_skill_ids)
    )
    unregistered_executor_ids = sorted(
        set(skill_executor_audit.get("executable_skill_ids") or []) - set(registry_skill_ids)
    )
    registered_only_skill_ids = sorted(set(registry_skill_ids) - set(executable_skill_ids))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo_root": str(repo_root.as_posix()),
        "tool_source_files": [str(path.as_posix()) for path in tool_source_files],
        "tool_count": tool_count,
        "skills_count": len(skill_coverages),
        "coverage": {
            "covered_count": covered_count,
            "coverage_pct": round((covered_count * 100.0 / tool_count), 2) if tool_count else 0.0,
            "missing_count": len(missing_tools),
        },
        "executors": {
            "registered_skill_count": len(registry_skill_ids),
            "executable_skill_count": len(executable_skill_ids),
            "executor_coverage_pct": round((len(executable_skill_ids) * 100.0 / len(registry_skill_ids)), 2)
            if registry_skill_ids
            else 0.0,
            "registered_only_count": len(registered_only_skill_ids),
            "registered_only_skill_ids": registered_only_skill_ids,
            "executable_skill_ids": executable_skill_ids,
            "unregistered_executor_ids": unregistered_executor_ids,
            "executor_count": int(skill_executor_audit.get("executor_count") or len(executable_skill_ids)),
            "skill_tool_file": skill_executor_audit.get("skill_tool_file"),
        },
        "manager": {
            "total_count": manager_total,
            "covered_count": len(covered_manager),
            "coverage_pct": round((len(covered_manager) * 100.0 / manager_total), 2)
            if manager_total
            else 0.0,
        },
        "all_tools": all_tools,
        "skills": [item.to_dict() for item in skill_coverages],
        "union_covered_tools": union_covered,
        "missing_tools": missing_tools,
        "manager_tools": manager_tools,
        "covered_manager_by_skills": covered_manager,
        "unknown_tool_refs": unknown_refs,
        "module_name_collisions": module_name_collisions,
        "module_name_collisions_count": len(module_name_collisions),
    }


def evaluate_thresholds(report: dict, baseline: dict) -> tuple[bool, list[str]]:
    thresholds = baseline.get("thresholds", {})
    violations: list[str] = []

    min_total = thresholds.get("min_total_coverage_pct")
    if min_total is not None and report["coverage"]["coverage_pct"] < float(min_total):
        violations.append(
            f"total coverage {report['coverage']['coverage_pct']}% < min_total_coverage_pct {min_total}%"
        )

    min_manager_count = thresholds.get("min_manager_coverage_count")
    if min_manager_count is not None and report["manager"]["covered_count"] < int(min_manager_count):
        violations.append(
            "manager covered "
            f"{report['manager']['covered_count']} < min_manager_coverage_count {min_manager_count}"
        )

    max_unknown = thresholds.get("max_unknown_tool_refs")
    unknown_total = sum(len(item["refs_unknown"]) for item in report["unknown_tool_refs"])
    if max_unknown is not None and unknown_total > int(max_unknown):
        violations.append(f"unknown tool refs {unknown_total} > max_unknown_tool_refs {max_unknown}")

    max_module_collisions = thresholds.get("max_module_name_collisions")
    collision_count = int(report.get("module_name_collisions_count", 0))
    if max_module_collisions is not None and collision_count > int(max_module_collisions):
        violations.append(
            f"module name collisions {collision_count} > max_module_name_collisions {max_module_collisions}"
        )

    return len(violations) == 0, violations


def write_outputs(report: dict, output_json: Path, output_gap: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    output_gap.parent.mkdir(parents=True, exist_ok=True)
    output_gap.write_text("\n".join(report["missing_tools"]) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit project skills coverage against runtime MCP tools."
    )
    parser.add_argument(
        "--server-file",
        default="packages/akshare-mcp/src/akshare_mcp/server.py",
        help="Path to akshare_mcp server.py",
    )
    parser.add_argument(
        "--tools-dir",
        default="packages/akshare-mcp/src/akshare_mcp/tools",
        help="Path to akshare_mcp tools directory",
    )
    parser.add_argument(
        "--skills-dir",
        default=".codex/skills",
        help="Path to project skills directory",
    )
    parser.add_argument(
        "--package-root",
        default="packages/akshare-mcp/src/akshare_mcp",
        help="Path to Python package root used for module collision checks",
    )
    parser.add_argument(
        "--output-json",
        default="skill_tool_coverage_runtime.json",
        help="Output JSON report path",
    )
    parser.add_argument(
        "--output-gap",
        default="skill_tool_gap_list.txt",
        help="Output missing tools list path",
    )
    parser.add_argument(
        "--baseline",
        default=".codex/skills/_meta/coverage_baseline.json",
        help="Threshold baseline JSON path",
    )
    parser.add_argument(
        "--check-thresholds",
        action="store_true",
        help="Check against baseline thresholds and return non-zero on violations",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()

    server_file = (repo_root / args.server_file).resolve()
    tools_dir = (repo_root / args.tools_dir).resolve()
    skills_dir = (repo_root / args.skills_dir).resolve()
    package_root = (repo_root / args.package_root).resolve()
    output_json = (repo_root / args.output_json).resolve()
    output_gap = (repo_root / args.output_gap).resolve()
    baseline_file = (repo_root / args.baseline).resolve()

    if not server_file.exists():
        print(f"[ERROR] server file not found: {server_file}", file=sys.stderr)
        return 2
    if not tools_dir.is_dir():
        print(f"[ERROR] tools dir not found: {tools_dir}", file=sys.stderr)
        return 2
    if not skills_dir.is_dir():
        print(f"[ERROR] skills dir not found: {skills_dir}", file=sys.stderr)
        return 2

    all_tools, tool_source_files = discover_runtime_tools(server_file, tools_dir)
    skill_coverages = collect_skill_coverages(skills_dir, set(all_tools))
    module_name_collisions = detect_module_name_collisions(package_root)
    skill_executor_audit = discover_skill_executors((tools_dir / "skills.py").resolve())
    report = compute_report(
        repo_root, all_tools, tool_source_files, skill_coverages, module_name_collisions, skill_executor_audit
    )

    threshold_result = {"enabled": False, "baseline": str(baseline_file.as_posix())}
    exit_code = 0

    if args.check_thresholds:
        threshold_result["enabled"] = True
        if not baseline_file.exists():
            threshold_result["passed"] = False
            threshold_result["violations"] = [f"baseline not found: {baseline_file.as_posix()}"]
            exit_code = 3
        else:
            baseline = json.loads(_load_text(baseline_file))
            passed, violations = evaluate_thresholds(report, baseline)
            threshold_result["passed"] = passed
            threshold_result["violations"] = violations
            threshold_result["thresholds"] = baseline.get("thresholds", {})
            if not passed:
                exit_code = 4

    report["threshold_check"] = threshold_result
    write_outputs(report, output_json, output_gap)

    print(
        "[OK] tools={tool_count} skills={skills_count} covered={covered} "
        "coverage={coverage}% executable_skills={exec_cov}/{skill_count} "
        "executor_coverage={exec_pct}% missing={missing} "
        "manager={mgr_cov}/{mgr_total} collisions={collisions}".format(
            tool_count=report["tool_count"],
            skills_count=report["skills_count"],
            covered=report["coverage"]["covered_count"],
            coverage=report["coverage"]["coverage_pct"],
            exec_cov=report["executors"]["executable_skill_count"],
            skill_count=report["executors"]["registered_skill_count"],
            exec_pct=report["executors"]["executor_coverage_pct"],
            missing=report["coverage"]["missing_count"],
            mgr_cov=report["manager"]["covered_count"],
            mgr_total=report["manager"]["total_count"],
            collisions=report["module_name_collisions_count"],
        )
    )

    if report["unknown_tool_refs"]:
        for item in report["unknown_tool_refs"]:
            print(
                f"[WARN] unknown refs in {item['skill']}: {', '.join(item['refs_unknown'])}",
                file=sys.stderr,
            )

    if report.get("module_name_collisions"):
        for item in report["module_name_collisions"]:
            print(
                "[WARN] module collision: {name} -> {module_file} | {package_init}".format(
                    name=item["name"],
                    module_file=item["module_file"],
                    package_init=item["package_init"],
                ),
                file=sys.stderr,
            )

    if args.check_thresholds and exit_code != 0:
        for violation in threshold_result.get("violations", []):
            print(f"[ERROR] {violation}", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
