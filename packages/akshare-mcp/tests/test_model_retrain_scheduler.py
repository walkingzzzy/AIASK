from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from akshare_mcp.services import get_artifact_async, register_artifact
from akshare_mcp.services.model_retrain_scheduler import ModelRetrainScheduler


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


def _register_retrain_plan(plan_id: str) -> None:
    created_at = (datetime.now().astimezone() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    register_artifact(
        {
            "artifact_id": plan_id,
            "strategy": "quant_model_retrain_plan",
            "strategy_version": "p2.v2",
            "code": "600519,000001,000858",
            "payload": {
                "plan_id": plan_id,
                "status": "planned",
                "priority": "high",
                "family": "momentum",
                "codes": ["600519", "000001", "000858"],
                "target_model_count": 1,
                "target_models": [
                    {
                        "artifact_id": "model_registry_seed_001",
                        "model_key": "momentum_seed_001",
                        "codes": ["600519", "000001", "000858"],
                    }
                ],
                "execution_mode": "scheduled",
                "schedule_hint": "daily",
                "created_at": created_at,
                "scheduler_status": "pending",
                "run_count": 0,
                "failure_count": 0,
            },
        }
    )


@pytest.mark.asyncio
async def test_model_retrain_scheduler_executes_due_plan_and_updates_governance(monkeypatch):
    import akshare_mcp.services.artifact_registry as artifact_mod

    monkeypatch.setattr(artifact_mod, "_get_db", lambda: None)
    _register_retrain_plan("quant_retrain_plan_scheduler_case")

    async def _fake_executor(plan_id: str, plan_payload: dict, reason: str):
        assert plan_id == "quant_retrain_plan_scheduler_case"
        assert reason == "manual_test"
        return {
            "success": True,
            "data": {
                "plan": {
                    **plan_payload,
                    "status": "completed",
                    "last_run_status": "completed",
                    "last_run_artifact_id": "quant_retrain_run_scheduler_case",
                    "run_count": int(plan_payload.get("run_count", 0) or 0) + 1,
                },
                "run": {
                    "artifact_id": "quant_retrain_run_scheduler_case",
                    "status": "completed",
                },
            },
        }

    scheduler = ModelRetrainScheduler(
        poll_interval_sec=60,
        lease_ttl_sec=300,
        max_plans_per_run=1,
        executor=_fake_executor,
    )
    result = await scheduler.run_once(reason="manual_test")

    assert result["executed_count"] == 1
    artifact = await get_artifact_async("quant_retrain_plan_scheduler_case")
    assert artifact is not None
    payload = artifact["payload"]
    assert payload["status"] == "completed"
    assert payload["scheduler_status"] == "idle"
    assert payload["last_run_artifact_id"] == "quant_retrain_run_scheduler_case"
    assert payload["lease_owner"] is None
    assert payload["failure_count"] == 0
    assert payload["next_run_at"]


@pytest.mark.asyncio
async def test_quant_manager_model_registry_retrain_scheduler_ops(monkeypatch):
    import akshare_mcp.services.model_retrain_scheduler as scheduler_mod
    import akshare_mcp.tools.managers.quant_manager as quant_mod

    class _StubScheduler:
        def status(self):
            return {
                "scheduler": "model_retrain_scheduler",
                "running": False,
                "instance_id": "stub-scheduler",
                "poll_interval_sec": 60,
                "lease_ttl_sec": 300,
                "max_plans_per_run": 1,
                "last_scan_at": None,
                "last_result": None,
            }

        async def run_once(self, *, reason: str = "manual", force: bool = False):
            return {
                "scheduler": "model_retrain_scheduler",
                "reason": reason,
                "forced": force,
                "executed_count": 1,
            }

    monkeypatch.setattr(scheduler_mod, "get_model_retrain_scheduler", lambda: _StubScheduler())

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    status_resp = await mcp.quant_manager(action="model_registry", kwargs={"op": "retrain_scheduler_status"})
    assert status_resp["success"] is True
    assert status_resp["data"]["scheduler"] == "model_retrain_scheduler"
    assert status_resp["data"]["instance_id"] == "stub-scheduler"

    run_resp = await mcp.quant_manager(
        action="model_registry",
        kwargs={"op": "retrain_scheduler_run_now", "reason": "manual_trigger", "force": True},
    )
    assert run_resp["success"] is True
    assert run_resp["data"]["reason"] == "manual_trigger"
    assert run_resp["data"]["forced"] is True
    assert run_resp["data"]["executed_count"] == 1
