"""P2: Mock AI must never light production_ready (L4)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from aiask_agent.financial_readiness import financial_system_readiness
from aiask_agent.model_client import MockModelClient
from aiask_agent.runtime import AgentRuntime
from aiask_agent.session_store import AgentSessionStore


def test_mock_provider_blocks_production_ready(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_MODEL_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    runtime = AgentRuntime(
        model_client=MockModelClient(),
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
    )

    async def fake_call_tool(name: str, params: dict | None = None) -> dict[str, Any]:
        if name == "agent_memory_search":
            return {"success": True, "data": {"items": []}}
        if name in {"agent_factory_status", "agent_factory_runs", "agent_strategy_review_snapshot"}:
            return {"success": True, "data": {"runtime_enabled": True, "runs": [], "items": []}}
        if name == "agent_factory_formal_diagnostics":
            return {
                "success": True,
                "data": {
                    "ok": True,
                    "formal_count": 5,
                    "observe_count": 10,
                    "signal_id_coverage": 1.0,
                    "orders_total": 20,
                    "orders_with_signal_id": 20,
                    "trades_total": 20,
                    "signals_total": 30,
                    "hard_gate_histogram": {"passed": 5, "missing": 0, "bootstrap_pending": 0,
                                            "failed_metrics": 0, "insufficient_samples": 0,
                                            "bootstrap_ready": 0, "unknown": 0},
                    "exit_funnel": {
                        "open_positions": 0, "with_exit_signal": 0, "with_exit_order": 0,
                        "closed": 10, "exit_order_conversion": 1.0,
                    },
                    "top_blockers": [],
                    "evidence_gaps": [],
                    "next_actions": [],
                },
            }
        return {"success": True, "data": {}}

    monkeypatch.setattr(runtime.tool_registry, "call_tool", fake_call_tool)

    import aiask_agent.adapters.quant as quant_adapter

    monkeypatch.setattr(
        quant_adapter,
        "database_status",
        lambda: {"configured": True, "writable": True, "path": str(tmp_path / "db.sqlite3")},
    )

    result = asyncio.run(
        financial_system_readiness(
            runtime,
            full_mode_enabled=True,
            control_token_configured=True,
            ai_status={"provider": "mock", "configured": True, "mock": True, "model": "mock"},
        )
    )
    assert result["production_ready"] is False
    action_ids = [str(a.get("action_id") or "") for a in result.get("next_actions") or []]
    assert "replace_mock_model" in action_ids
    assert result.get("factory_diagnostics", {}).get("formal_count") == 5
