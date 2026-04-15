from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

import akshare_mcp.tools.skills as skills_mod
import akshare_mcp.tools.skills_strategy_workflows as strategy_skill_workflows
import akshare_mcp.tools.managers.strategy_manager as strategy_manager_mod
from akshare_mcp.tools.tool_catalog import get_tool_contract


ROOT = Path(__file__).resolve().parents[3]
AUDIT_SCRIPT = ROOT / "scripts" / "skill_coverage_audit.py"

_AUDIT_SPEC = importlib.util.spec_from_file_location("skill_coverage_audit_script", AUDIT_SCRIPT)
assert _AUDIT_SPEC is not None and _AUDIT_SPEC.loader is not None
skill_coverage_audit = importlib.util.module_from_spec(_AUDIT_SPEC)
sys.modules[_AUDIT_SPEC.name] = skill_coverage_audit
_AUDIT_SPEC.loader.exec_module(skill_coverage_audit)


class _DummyMCP:
    def tool(self, **_kwargs):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


def test_skill_coverage_audit_discovers_heavy_and_inline_tools():
    tools, _ = skill_coverage_audit.discover_runtime_tools(
        ROOT / "packages/akshare-mcp/src/akshare_mcp/server.py",
        ROOT / "packages/akshare-mcp/src/akshare_mcp/tools",
    )

    tool_set = set(tools)
    assert {"list_skills", "search_skills", "run_skill"} <= tool_set
    assert {"get_market_blocks", "get_block_stocks"} <= tool_set


@pytest.mark.asyncio
async def test_build_strategy_review_workflow_payload_builds_read_only_snapshot():
    calls: list[tuple[str, dict]] = []

    async def fake_manager(action: str, kwargs="{}", params=None):
        calls.append((action, dict(params or {})))
        return {"success": True, "data": {"action": action}}

    async def fake_resource(strategy_id: str):
        return {
            "found": True,
            "strategy_id": strategy_id,
            "summary": {
                "current_status": "listed",
                "open_risk_count": 2,
            },
        }

    payload = await strategy_skill_workflows.build_strategy_review_workflow_payload(
        "strat_demo",
        runtime_strategy_manager=fake_manager,
        build_strategy_review_payload=fake_resource,
    )

    assert payload["workflow"] == "strategy_review_workflow"
    assert payload["strategy_id"] == "strat_demo"
    assert payload["summary"]["current_status"] == "listed"
    assert payload["summary"]["open_risk_count"] == 2
    assert [step["step"] for step in payload["steps"]] == [
        "resource.strategy_review",
        "strategy_manager.review_report",
        "strategy_manager.factory_status",
        "strategy_manager.runtime_alerts",
    ]
    assert [action for action, _params in calls] == [
        "review_report",
        "factory_status",
        "runtime_alerts",
    ]


@pytest.mark.asyncio
async def test_exec_strategy_factory_strategy_review_reuses_shared_workflow(monkeypatch):
    calls: list[str] = []

    async def fake_workflow(*_args, **_kwargs):
        return {
            "workflow": "strategy_review_workflow",
            "strategy_id": "strat_demo",
            "steps": [],
            "summary": {
                "current_status": "listed",
                "open_risk_count": 1,
                "failed_steps": [],
            },
            "artifacts": {
                "strategy_review_resource": "resource://strategy/strat_demo/review",
            },
            "workflow_stage": {
                "completed_stages": [],
                "last_completed_stage": None,
                "recoverable": False,
                "resume_hint": None,
            },
        }

    async def fake_manager(action: str, kwargs="{}", params=None):
        calls.append(action)
        return {"success": True, "data": {"action": action, "params": dict(params or {})}}

    monkeypatch.setattr(strategy_skill_workflows, "build_strategy_review_workflow_payload", fake_workflow)

    result = await strategy_skill_workflows.exec_strategy_factory(
        {"task": "strategy_review", "strategy_id": "strat_demo", "limit": 3},
        runtime_strategy_manager=fake_manager,
    )

    assert result["status"] == "completed"
    assert [step["step"] for step in result["steps"]] == [
        "strategy_review_workflow.review",
        "strategy_manager.events",
    ]
    assert calls == ["events"]
    assert result["summary"]["strategy_id"] == "strat_demo"
    assert result["summary"]["current_status"] == "listed"
    assert result["summary"]["open_risk_count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("params", "expected_present", "expected_absent"),
    [
        (
            {"task": "submission_gate", "strategy_id": "strat_demo"},
            {"execution_audit_verification"},
            {"review_report_recheck", "submission_replay", "submit"},
        ),
        (
            {
                "task": "submission_gate",
                "strategy_id": "strat_demo",
                "trigger_review_report_recheck": True,
                "trigger_submission_replay": True,
                "trigger_submit": True,
            },
            {"review_report_recheck", "submission_replay", "submit", "execution_audit_verification"},
            set(),
        ),
        (
            {"task": "incubation_pipeline", "strategy_id": "strat_demo"},
            {
                "incubation_overview",
                "incubation_accounts",
                "incubation_metrics",
                "paper_account",
                "paper_orders",
                "paper_nav",
                "incubation_pipeline",
                "promotion_reviews",
            },
            {"incubation_sync_run", "incubation_pipeline_run", "promotion_review_run"},
        ),
        (
            {
                "task": "runtime_governance",
                "strategy_id": "strat_demo",
                "trigger_runtime_cycle": True,
            },
            {
                "runtime_cycle_status",
                "risk_events",
                "risk_snapshots",
                "runtime_alerts",
                "runtime_control",
                "runtime_cycle_run",
            },
            {"risk_scan_run", "risk_recovery", "runtime_control_set"},
        ),
        (
            {"task": "vector_governance", "strategy_id": "strat_demo"},
            {
                "vector_health",
                "vector_indexes",
                "vector_index_snapshots",
                "vector_profiles",
                "vector_ann_search",
            },
            {"vector_reconcile", "vector_rebuild", "vector_cleanup"},
        ),
        (
            {
                "task": "domain_projection",
                "strategy_id": "strat_demo",
                "trigger_domain_projection_rebuild": True,
            },
            {"domain_events", "domain_projection", "domain_projection_snapshot", "domain_projection_rebuild"},
            set(),
        ),
        (
            {"task": "ai_generation", "strategy_id": "strat_demo"},
            {"ai_experiments", "task_runs"},
            {"ai_generate"},
        ),
        (
            {
                "task": "ai_generation",
                "strategy_id": "strat_demo",
                "trigger_ai_generate": True,
            },
            {"ai_experiments", "task_runs", "ai_generate"},
            set(),
        ),
    ],
)
async def test_exec_strategy_factory_dispatches_new_tasks_with_explicit_stateful_triggers(
    params,
    expected_present,
    expected_absent,
):
    calls: list[str] = []

    async def fake_manager(action: str, kwargs="{}", params=None):
        calls.append(action)
        return {"success": True, "data": {"action": action, "params": dict(params or {})}}

    result = await strategy_skill_workflows.exec_strategy_factory(
        params,
        runtime_strategy_manager=fake_manager,
    )

    assert result["status"] == "completed"
    for action in expected_present:
        assert action in calls
    for action in expected_absent:
        assert action not in calls


@pytest.mark.asyncio
async def test_run_skill_strategy_factory_returns_stable_execution(monkeypatch):
    monkeypatch.setattr(skills_mod, "_load_skill_coverage_audit", lambda: None)
    monkeypatch.setattr(
        skills_mod,
        "_load_skills",
        lambda: [
            {
                "id": "akshare-strategy-factory",
                "name": "Strategy Factory",
                "category": "strategy",
                "description": "x",
                "path": "/tmp/akshare-strategy-factory/SKILL.md",
            }
        ],
    )
    monkeypatch.setattr(
        skills_mod,
        "_SKILL_EXECUTORS",
        {"akshare-strategy-factory": skills_mod._exec_strategy_factory},
    )

    async def fake_workflow(*_args, **_kwargs):
        return {
            "workflow": "strategy_review_workflow",
            "strategy_id": "strat_demo",
            "steps": [],
            "summary": {
                "current_status": "listed",
                "open_risk_count": 0,
                "failed_steps": [],
            },
            "artifacts": {
                "strategy_review_resource": "resource://strategy/strat_demo/review",
            },
            "workflow_stage": {
                "completed_stages": [],
                "last_completed_stage": None,
                "recoverable": False,
                "resume_hint": None,
            },
        }

    async def fake_manager(action: str, kwargs="{}", params=None):
        return {"success": True, "data": {"action": action, "params": dict(params or {})}}

    monkeypatch.setattr(strategy_skill_workflows, "build_strategy_review_workflow_payload", fake_workflow)
    monkeypatch.setattr(strategy_manager_mod, "strategy_manager", fake_manager)

    mcp = _DummyMCP()
    skills_mod.register(mcp)

    result = await mcp.run_skill(
        "akshare-strategy-factory",
        {"task": "strategy_review", "strategy_id": "strat_demo"},
    )

    assert result["success"] is True
    execution = result["data"]["execution"]
    assert execution["task"] == "strategy_review"
    assert execution["status"] == "completed"
    assert execution["summary"]["strategy_id"] == "strat_demo"
    assert execution["summary"]["current_status"] == "listed"


def test_strategy_manager_tool_contract_includes_strategy_factory_actions():
    contract = get_tool_contract("strategy_manager")
    assert contract is not None

    actions = set(contract["input_schema"]["properties"]["action"]["enum"])
    assert {
        "execution_audit_verification",
        "submission_replay",
        "factory_runs",
        "factory_run_detail",
        "task_runs",
        "incubation_pipeline",
        "promotion_review_run",
        "risk_snapshots",
        "runtime_alert_dispatch_run",
        "runtime_cycle_status",
        "vector_indexes",
        "vector_profiles",
        "domain_projection_snapshot",
        "ai_experiments",
    } <= actions
