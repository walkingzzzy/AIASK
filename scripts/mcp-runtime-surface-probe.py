#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
AKSHARE_SRC = REPO_ROOT / "packages" / "akshare-mcp" / "src"
STRATEGY_FACTORY_SRC = REPO_ROOT / "packages" / "strategy-factory" / "src"

for candidate in (AKSHARE_SRC, STRATEGY_FACTORY_SRC):
    text = str(candidate)
    if text not in sys.path:
        sys.path.insert(0, text)

from akshare_mcp.server import mcp  # noqa: E402
from akshare_mcp.storage import get_db  # noqa: E402


DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "aiask_e2e"
LOCAL_SKILLS_ROOT = REPO_ROOT / ".codex" / "skills"
SKILL_COVERAGE_PATH = REPO_ROOT / "skill_tool_coverage_runtime.json"
SKILL_GAP_LIST_PATH = REPO_ROOT / "skill_tool_gap_list.txt"


PROMPT_CASES: dict[str, dict[str, Any]] = {
    "factor-mining": {"codes": "600519,000001", "candidate_count": 2, "focus": "smoke_test"},
    "stock-analysis": {"code": "600519", "focus": "估值与决策", "include_financials": True, "include_decision": True},
    "prediction-diagnosis": {
        "probabilities": "0.12,0.74,0.61,0.35",
        "labels": "0,1,1,0",
        "method": "raw",
        "focus": "校准质量",
    },
    "factor-registry-review": {"codes": "600519,000001", "focus": "候选治理"},
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe MCP resources, prompts and local skills.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def _safe_json_load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _sample_text(value: Any, limit: int = 320) -> str:
    if isinstance(value, (dict, list)):
      text = json.dumps(value, ensure_ascii=False, default=str)
    else:
      text = str(value)
    return text if len(text) <= limit else f"{text[:limit]}..."


def _message_preview(messages: list[Any]) -> list[str]:
    preview: list[str] = []
    for message in messages[:4]:
        content = getattr(message, "content", "")
        preview.append(_sample_text(content, 180))
    return preview


async def _call_tool(name: str, args: dict[str, Any]) -> tuple[bool, Any]:
    tool = mcp._tool_manager._tools.get(name)
    if not tool:
        return False, {"error": f"tool_not_found:{name}"}
    try:
        result = await tool.run(args)
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception:
                result = {"success": True, "data": result}
        return True, result
    except Exception as exc:
        return False, {"error": f"{type(exc).__name__}: {exc}"}


async def _resolve_strategy_id() -> str | None:
    for action, params in (
        ("list", {"limit": 1}),
        ("rank", {"limit": 1}),
        ("ranking", {"limit": 1}),
    ):
        ok, result = await _call_tool("strategy_manager", {"action": action, "params": params})
        if not ok:
            continue
        payload = result.get("data") if isinstance(result, dict) and "data" in result else result
        candidates = []
        if isinstance(payload, dict):
            for key in ("items", "strategies", "rows", "data", "list"):
                value = payload.get(key)
                if isinstance(value, list):
                    candidates = value
                    break
        elif isinstance(payload, list):
            candidates = payload
        for candidate in candidates:
            if isinstance(candidate, dict):
                strategy_id = candidate.get("id") or candidate.get("strategy_id")
                if strategy_id is not None:
                    return str(strategy_id)
    return None


async def _probe_resources() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for resource in mcp._resource_manager.list_resources():
        started = time.perf_counter()
        try:
            content = await resource.read()
            parsed = json.loads(content) if isinstance(content, str) and content.strip().startswith(("{", "[")) else content
            results.append(
                {
                    "uri": str(resource.uri),
                    "title": resource.title,
                    "ok": True,
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                    "preview": _sample_text(parsed),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "uri": str(resource.uri),
                    "title": resource.title,
                    "ok": False,
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return results


async def _probe_prompts() -> list[dict[str, Any]]:
    strategy_id = await _resolve_strategy_id()
    prompt_cases = dict(PROMPT_CASES)
    prompt_cases["strategy-review"] = {
        "strategy_id": strategy_id or "missing-strategy",
        "focus": "晋级前检查",
        "include_projection": True,
    }
    prompt_cases["strategy-promotion-review"] = {
        "strategy_id": strategy_id or "missing-strategy",
        "focus": "promotion smoke",
    }

    results: list[dict[str, Any]] = []
    for prompt in mcp._prompt_manager.list_prompts():
        args = prompt_cases.get(prompt.name, {})
        started = time.perf_counter()
        try:
            messages = await mcp._prompt_manager.render_prompt(prompt.name, args)
            results.append(
                {
                    "name": prompt.name,
                    "ok": True,
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                    "message_count": len(messages),
                    "preview": _message_preview(messages),
                    "used_args": args,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "name": prompt.name,
                    "ok": False,
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                    "error": f"{type(exc).__name__}: {exc}",
                    "used_args": args,
                }
            )
    return results


async def _probe_local_skills() -> list[dict[str, Any]]:
    local_skill_ids = sorted(path.parent.name for path in LOCAL_SKILLS_ROOT.glob("*/SKILL.md"))
    ok, registry_payload = await _call_tool("list_skills", {})
    registry = registry_payload.get("data") if ok and isinstance(registry_payload, dict) else {}
    registry_items = {
        str(item.get("id")): item
        for item in list(registry.get("skills") or [])
        if isinstance(item, dict) and item.get("id")
    }

    results: list[dict[str, Any]] = []
    for skill_id in local_skill_ids:
        started = time.perf_counter()
        registered = registry_items.get(skill_id) or {}
        ok_call, result = await _call_tool("run_skill", {"skill_id": skill_id, "params": {"task": "smoke_test"}})
        payload = result.get("data") if ok_call and isinstance(result, dict) and "data" in result else result
        success = bool(ok_call and isinstance(result, dict) and result.get("success") is True)
        entry = {
            "skill_id": skill_id,
            "registered": bool(registered),
            "registry_status": registered.get("status"),
            "executable": registered.get("executable"),
            "ok": success,
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }
        if success:
            entry["preview"] = _sample_text(payload)
        else:
            entry["error"] = _sample_text(payload)
        results.append(entry)
    return results


async def main() -> int:
    args = _parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    resources = await _probe_resources()
    prompts = await _probe_prompts()
    skills = await _probe_local_skills()

    coverage_audit = _safe_json_load(SKILL_COVERAGE_PATH, {})
    gap_list = [
        line.strip()
        for line in SKILL_GAP_LIST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ] if SKILL_GAP_LIST_PATH.exists() else []

    summary = {
        "resource_count": len(resources),
        "resource_passed": sum(1 for item in resources if item["ok"]),
        "prompt_count": len(prompts),
        "prompt_passed": sum(1 for item in prompts if item["ok"]),
        "local_skill_count": len(skills),
        "local_skill_passed": sum(1 for item in skills if item["ok"]),
        "avg_latency_ms": round(
            (
                sum(item["latency_ms"] for item in resources)
                + sum(item["latency_ms"] for item in prompts)
                + sum(item["latency_ms"] for item in skills)
            )
            / max(len(resources) + len(prompts) + len(skills), 1),
            2,
        ),
        "mapping_gap_count": len(gap_list),
    }

    report = {
        "executed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": summary,
        "resources": resources,
        "prompts": prompts,
        "local_skills": skills,
        "skill_tool_coverage_audit": coverage_audit,
        "skill_tool_gap_list": gap_list,
    }

    json_path = output_dir / "mcp-runtime-surface-probe.json"
    md_path = output_dir / "mcp-runtime-surface-probe.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_lines = [
        "# MCP Runtime Surface Probe",
        "",
        f"- 执行时间: {report['executed_at']}",
        f"- Resources: {summary['resource_passed']} / {summary['resource_count']}",
        f"- Prompts: {summary['prompt_passed']} / {summary['prompt_count']}",
        f"- 本地 Skills: {summary['local_skill_passed']} / {summary['local_skill_count']}",
        f"- 平均延迟: {summary['avg_latency_ms']} ms",
        f"- Skills 与 Tools 映射缺口: {summary['mapping_gap_count']}",
        "",
        "## 失败项",
        "",
    ]
    failed_items = [
        *[f"resource {item['uri']}: {item['error']}" for item in resources if not item["ok"]],
        *[f"prompt {item['name']}: {item['error']}" for item in prompts if not item["ok"]],
        *[f"skill {item['skill_id']}: {item['error']}" for item in skills if not item["ok"]],
    ]
    md_lines.extend([f"- {item}" for item in failed_items] or ["- 无"])
    md_lines.extend(["", "## 映射缺口", ""])
    md_lines.extend([f"- {item}" for item in gap_list] or ["- 无"])
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "summary": summary}, ensure_ascii=False, indent=2))

    try:
        maybe_close = get_db().close()
        if inspect.isawaitable(maybe_close):
            await maybe_close
    except Exception:
        pass

    total_failures = (
        (summary["resource_count"] - summary["resource_passed"])
        + (summary["prompt_count"] - summary["prompt_passed"])
        + (summary["local_skill_count"] - summary["local_skill_passed"])
    )
    return 0 if total_failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
