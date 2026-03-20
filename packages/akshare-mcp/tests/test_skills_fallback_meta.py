import platform

import pytest

import akshare_mcp.tools.skills as skills_mod


RUNTIME_TOOL_COUNT = 171 if platform.system() == "Windows" else 134


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


def test_load_skills_without_registry_uses_fallback(monkeypatch):
    monkeypatch.setattr(skills_mod, "_list_skill_roots", lambda: [])
    assert skills_mod._load_skills() == skills_mod._FALLBACK_SKILLS


def test_list_skills_exposes_status_and_schema(monkeypatch):
    monkeypatch.setattr(
        skills_mod,
        "_load_skill_coverage_audit",
        lambda: {
            "generated_at": "2026-03-13T00:00:00+00:00",
            "tool_count": RUNTIME_TOOL_COUNT,
            "skills_count": 20,
            "coverage": {"covered_count": RUNTIME_TOOL_COUNT, "coverage_pct": 100.0, "missing_count": 0},
            "executors": {"registered_skill_count": 20, "executable_skill_count": 4, "executor_coverage_pct": 20.0},
        },
    )
    monkeypatch.setattr(
        skills_mod,
        "_load_skills",
        lambda: [
            {
                "id": "akshare-market",
                "name": "Market",
                "category": "market",
                "description": "x",
                "path": "/tmp/akshare-market/SKILL.md",
            },
            {
                "id": "custom-demo",
                "name": "Custom Demo",
                "category": "demo",
                "description": "x",
                "path": "/tmp/custom-demo/SKILL.md",
            },
            {
                "id": "legacy-skill",
                "name": "Legacy Skill",
                "category": "demo",
                "description": "x",
                "path": "/tmp/legacy-skill/SKILL.md",
                "deprecated": True,
            },
        ],
    )
    monkeypatch.setattr(skills_mod, "_SKILL_EXECUTORS", {"akshare-market": lambda _params: {"status": "ok"}})

    mcp = _DummyMCP()
    skills_mod.register(mcp)

    result = mcp.list_skills()

    assert result["success"] is True
    data = result["data"]
    skill_map = {item["id"]: item for item in data["skills"]}

    assert skill_map["akshare-market"]["status"] == "executable"
    assert skill_map["akshare-market"]["execution_mode"] == "orchestrated"
    assert skill_map["akshare-market"]["executable"] is True
    assert skill_map["akshare-market"]["input_schema"]["type"] == "object"
    assert "smoke_test" in skill_map["akshare-market"]["supported_tasks"]

    assert skill_map["custom-demo"]["status"] == "registered"
    assert skill_map["custom-demo"]["execution_mode"] == "no_handler"
    assert skill_map["custom-demo"]["executable"] is False

    assert skill_map["legacy-skill"]["status"] == "deprecated"
    assert skill_map["legacy-skill"]["execution_mode"] == "deprecated"
    assert skill_map["legacy-skill"]["deprecated"] is True

    registry_summary = data["registry_summary"]
    assert registry_summary["total_count"] == 3
    assert registry_summary["executable_count"] == 1
    assert registry_summary["registered_only_count"] == 1
    assert registry_summary["deprecated_count"] == 1
    assert registry_summary["executor_coverage_ratio"] == pytest.approx(1 / 3, rel=1e-4)
    assert registry_summary["executable_skill_ids"] == ["akshare-market"]
    assert registry_summary["available_handlers"] == ["akshare-market"]
    assert registry_summary["tool_reference_coverage"] == {
        "covered_count": RUNTIME_TOOL_COUNT,
        "coverage_pct": 100.0,
        "missing_count": 0,
        "tool_count": RUNTIME_TOOL_COUNT,
        "skills_count": 20,
        "generated_at": "2026-03-13T00:00:00+00:00",
    }
    assert registry_summary["executor_audit"] == {
        "registered_skill_count": 20,
        "executable_skill_count": 4,
        "executor_coverage_pct": 20.0,
    }
    assert registry_summary["execution_gap"] == [
        {
            "id": "custom-demo",
            "name": "Custom Demo",
            "status": "registered",
            "execution_mode": "no_handler",
        }
    ]


def test_search_skills_keeps_registry_summary(monkeypatch):
    monkeypatch.setattr(skills_mod, "_load_skill_coverage_audit", lambda: None)
    monkeypatch.setattr(
        skills_mod,
        "_load_skills",
        lambda: [
            {
                "id": "akshare-market",
                "name": "Market",
                "category": "market",
                "description": "x",
                "path": "/tmp/akshare-market/SKILL.md",
            },
            {
                "id": "custom-demo",
                "name": "Custom Demo",
                "category": "demo",
                "description": "x",
                "path": "/tmp/custom-demo/SKILL.md",
            },
        ],
    )
    monkeypatch.setattr(skills_mod, "_SKILL_EXECUTORS", {"akshare-market": lambda _params: {"status": "ok"}})

    mcp = _DummyMCP()
    skills_mod.register(mcp)

    result = mcp.search_skills("custom")

    assert result["success"] is True
    data = result["data"]
    assert data["count"] == 1
    assert data["skills"][0]["id"] == "custom-demo"
    assert data["registry_summary"]["total_count"] == 2
    assert data["registry_summary"]["executable_count"] == 1
    assert data["registry_summary"]["registered_only_count"] == 1


def test_repo_local_skill_registry_is_fully_executable(monkeypatch):
    repo_root = skills_mod._find_repo_skills_root()
    assert repo_root is not None

    monkeypatch.setattr(skills_mod, "_list_skill_roots", lambda: [repo_root])
    monkeypatch.setattr(skills_mod, "_load_skill_coverage_audit", lambda: None)

    skills = skills_mod._enrich_skills(skills_mod._load_skills())
    summary = skills_mod._build_skill_registry_summary(skills)

    assert len(skills) == 20
    assert all(skill["executable"] for skill in skills)
    assert summary["total_count"] == 20
    assert summary["executable_count"] == 20
    assert summary["registered_only_count"] == 0
    assert summary["executor_coverage_ratio"] == 1.0
    assert summary["execution_gap"] == []


@pytest.mark.asyncio
async def test_run_skill_no_handler_returns_stable_not_executable_error(monkeypatch):
    monkeypatch.setattr(
        skills_mod,
        "_load_skills",
        lambda: [{"id": "custom-demo", "name": "Custom Demo", "category": "demo", "description": "x", "path": ""}],
    )
    monkeypatch.setattr(skills_mod, "_SKILL_EXECUTORS", {})

    mcp = _DummyMCP()
    skills_mod.register(mcp)

    result = await mcp.run_skill("custom-demo", {"task": "demo"})

    assert result["success"] is False
    assert result["data"] is None
    assert result["error_code"] == "SKILL_NOT_EXECUTABLE"
    assert result["detail"]["skill"]["status"] == "registered"
    assert result["backend_requested"] == "skill_executor"
    assert result["backend_used"] == "registry_only"
    assert result["fallback_used"] is True
    assert result["fallback_reason"] == ["skills_registry_unavailable", "handler_not_implemented"]
    assert isinstance(result["latency_ms"], int)
    assert result["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_run_skill_deprecated_returns_stable_error(monkeypatch):
    monkeypatch.setattr(
        skills_mod,
        "_load_skills",
        lambda: [
            {
                "id": "legacy-skill",
                "name": "Legacy Skill",
                "category": "demo",
                "description": "x",
                "path": "/tmp/legacy-skill/SKILL.md",
                "deprecated": True,
            }
        ],
    )
    monkeypatch.setattr(skills_mod, "_SKILL_EXECUTORS", {"legacy-skill": lambda _params: {"status": "ignored"}})

    mcp = _DummyMCP()
    skills_mod.register(mcp)

    result = await mcp.run_skill("legacy-skill", {"task": "demo"})

    assert result["success"] is False
    assert result["error_code"] == "SKILL_DEPRECATED"
    assert result["detail"]["skill"]["status"] == "deprecated"
    assert result["backend_requested"] == "skill_executor"
    assert result["backend_used"] == "registry_only"
    assert result["fallback_used"] is True
    assert result["fallback_reason"] == ["skill_deprecated"]


@pytest.mark.asyncio
async def test_run_skill_executor_exception_keeps_fail_contract_and_meta(monkeypatch):
    def _boom(_params):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        skills_mod,
        "_load_skills",
        lambda: [{"id": "akshare-market", "name": "Market", "category": "market", "description": "x", "path": ""}],
    )
    monkeypatch.setattr(skills_mod, "_SKILL_EXECUTORS", {"akshare-market": _boom})

    mcp = _DummyMCP()
    skills_mod.register(mcp)

    result = await mcp.run_skill("akshare-market", {"task": "smoke_test"})

    assert result["success"] is False
    assert result["data"] is None
    assert "RuntimeError: boom" in result["error"]
    assert result["error_code"] == "SKILL_EXECUTION_FAILED"
    assert result["backend_requested"] == "skill_executor"
    assert result["backend_used"] == "none"
    assert result["fallback_used"] is True
    assert result["fallback_reason"] == ["skills_registry_unavailable", "executor_exception:RuntimeError"]
    assert isinstance(result["latency_ms"], int)
    assert result["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_run_skill_newly_executable_policy_skill_succeeds(monkeypatch):
    monkeypatch.setattr(
        skills_mod,
        "_load_skill_coverage_audit",
        lambda: None,
    )
    monkeypatch.setattr(
        skills_mod,
        "_load_skills",
        lambda: [
            {
                "id": "akshare-ips-discipline",
                "name": "IPS",
                "category": "discipline",
                "description": "x",
                "path": "/tmp/akshare-ips-discipline/SKILL.md",
            }
        ],
    )

    mcp = _DummyMCP()
    skills_mod.register(mcp)

    result = await mcp.run_skill("akshare-ips-discipline", {"task": "draft_ips", "goal": "Retire with guardrails"})

    assert result["success"] is True
    assert result["data"]["backend_requested"] == "skill_executor"
    assert result["data"]["backend_used"] == "built_in_orchestrator"
    assert result["data"]["execution"]["status"] == "completed"
    assert result["data"]["execution"]["summary"]["ips_draft"]["goal"] == "Retire with guardrails"
