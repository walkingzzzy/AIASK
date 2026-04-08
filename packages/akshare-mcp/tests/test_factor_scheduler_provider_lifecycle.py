import json
from unittest.mock import MagicMock

import pytest


class _RecoveringProvider:
    def __init__(self):
        self.rebuilt = False

    def status(self):
        if not self.rebuilt:
            return {
                "enabled": True,
                "configured": True,
                "ready": False,
                "client_closed": False,
                "health_status": "degraded",
                "rebuild_recommended": True,
                "rebuild_count": 0,
                "consecutive_failures": 1,
                "last_error_type": "RuntimeError",
                "last_error": "provider temporarily unavailable",
            }
        return {
            "enabled": True,
            "configured": True,
            "ready": True,
            "client_closed": False,
            "health_status": "ready",
            "rebuild_recommended": False,
            "rebuild_count": 1,
            "consecutive_failures": 0,
            "last_error_type": "RuntimeError",
            "last_error": "provider temporarily unavailable",
        }

    async def rebuild_client(self, *, reason: str = "manual"):
        self.rebuilt = True
        return {"status": "rebuilt", "reason": reason}

    def is_enabled(self):
        return True


class _StickyDegradedProvider:
    def __init__(self):
        self.rebuilt = False

    def status(self):
        return {
            "enabled": True,
            "configured": True,
            "ready": False,
            "client_closed": False,
            "health_status": "degraded",
            "rebuild_recommended": not self.rebuilt,
            "rebuild_count": 1 if self.rebuilt else 0,
            "consecutive_failures": 2,
            "last_error_type": "RuntimeError",
            "last_error": "provider still unavailable",
        }

    async def rebuild_client(self, *, reason: str = "manual"):
        self.rebuilt = True
        return {"status": "rebuilt", "reason": reason}

    def is_enabled(self):
        return True


class _ReadySmokeProvider:
    def __init__(self):
        self.smoke_calls = 0

    def status(self):
        return {
            "enabled": True,
            "configured": True,
            "ready": True,
            "client_closed": False,
            "health_status": "ready",
            "rebuild_recommended": False,
            "rebuild_count": 0,
            "consecutive_failures": 0,
            "last_error_type": None,
            "last_error": None,
        }

    async def smoke_check(self):
        self.smoke_calls += 1
        return {"status": "passed"}

    def is_enabled(self):
        return True


def test_factor_scheduler_resolves_validation_codes_with_representative_sample(monkeypatch):
    from akshare_mcp.services.factor_scheduler import FactorScheduler

    monkeypatch.delenv("FACTOR_SCHEDULER_VALIDATION_MAX_CODES", raising=False)
    universe = [f"{idx:06d}" for idx in range(1, 61)]
    scheduler = FactorScheduler(universe=universe, factors=["reversal"], batch_size=10)

    resolved = scheduler._resolve_validation_codes({"codes": universe})

    assert len(resolved) == 24
    assert resolved[0] == universe[0]
    assert resolved[-1] == universe[-1]
    assert resolved != universe[:24]

    resolved_indices = [universe.index(code) for code in resolved]
    assert resolved_indices == sorted(resolved_indices)
    assert max(b - a for a, b in zip(resolved_indices, resolved_indices[1:])) <= 4


def test_factor_scheduler_validation_code_limit_can_be_overridden(monkeypatch):
    from akshare_mcp.services.factor_scheduler import FactorScheduler

    monkeypatch.setenv("FACTOR_SCHEDULER_VALIDATION_MAX_CODES", "12")
    universe = [f"{idx:06d}" for idx in range(1, 41)]
    scheduler = FactorScheduler(universe=universe, factors=["reversal"], batch_size=10)

    resolved = scheduler._resolve_validation_codes({"codes": universe})

    assert len(resolved) == 12
    assert resolved[0] == universe[0]
    assert resolved[-1] == universe[-1]


@pytest.mark.asyncio
async def test_factor_scheduler_blocks_local_fallback_by_default_when_provider_stays_unready(monkeypatch):
    from akshare_mcp.services.factor_scheduler import FactorScheduler
    from akshare_mcp.tools.managers import quant_manager as quant_manager_module

    monkeypatch.setenv("FACTOR_LLM_ENABLED", "1")
    monkeypatch.setenv("FACTOR_SCHEDULER_LLM_MINING", "1")
    monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: MagicMock())

    fake_provider = _StickyDegradedProvider()
    monkeypatch.setattr(
        "akshare_mcp.services.factor_llm_provider.get_factor_llm_provider",
        lambda: fake_provider,
    )

    llm_calls = []

    async def _fake_quant_manager(*, action, code=None, **kwargs):
        del code
        payload = json.loads(kwargs["kwargs"])
        if action == "batch_compute_factors":
            return {
                "success": True,
                "data": {
                    "computed_count": len(payload.get("codes") or []),
                    "error_count": 0,
                },
            }
        if action == "llm_factor_mining":
            llm_calls.append(payload)
            raise AssertionError("llm_factor_mining should be blocked when provider remains unready")
        raise AssertionError(f"unexpected action: {action}")

    monkeypatch.setattr(quant_manager_module, "quant_manager", _fake_quant_manager)

    scheduler = FactorScheduler(
        universe=["000001", "000002", "000333", "600519"],
        factors=["reversal"],
        batch_size=2,
    )

    result = await scheduler.run_once()
    status = scheduler.status()

    assert llm_calls == []
    assert result["status"] == "partial"
    assert result["llm_provider"]["health_status"] == "degraded"
    assert result["llm_provider_preflight"]["action"] == "rebuild_client"
    assert result["summary"]["llm_provider_health_status"] == "degraded"
    assert result["summary"]["llm_provider_rebuild_count"] == 1
    assert result["summary"]["llm_fallback_used"] is False
    assert result["summary"]["llm_allow_local_rule_fallback"] is False
    assert result["summary"]["llm_provider_gate_status"] == "blocked"
    assert result["summary"]["llm_provider_gate_reason"] == "provider_not_ready_after_preflight"
    assert result["stages"]["llm_factor_mining"]["generation_mode"] == "provider_blocked"
    assert result["stages"]["llm_factor_mining"]["allow_local_rule_fallback"] is False
    assert result["stages"]["llm_factor_mining"]["provider_preflight_action"] == "rebuild_client"


@pytest.mark.asyncio
async def test_factor_scheduler_run_once_loads_factor_env_from_file(monkeypatch, tmp_path):
    from akshare_mcp.services.factor_scheduler import FactorScheduler
    from akshare_mcp.tools.managers import quant_manager as quant_manager_module

    env_path = tmp_path / "factor.env"
    env_path.write_text(
        "\n".join(
            [
                "FACTOR_LLM_ENABLED=1",
                "FACTOR_SCHEDULER_LLM_MINING=1",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AKSHARE_MCP_ENV", str(env_path))
    monkeypatch.delenv("FACTOR_LLM_ENABLED", raising=False)
    monkeypatch.delenv("FACTOR_SCHEDULER_LLM_MINING", raising=False)
    monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: MagicMock())

    fake_provider = _ReadySmokeProvider()
    monkeypatch.setattr(
        "akshare_mcp.services.factor_llm_provider.get_factor_llm_provider",
        lambda: fake_provider,
    )

    llm_payloads = []

    async def _fake_quant_manager(*, action, code=None, **kwargs):
        del code
        payload = json.loads(kwargs["kwargs"])
        if action == "batch_compute_factors":
            return {
                "success": True,
                "data": {
                    "computed_count": len(payload.get("codes") or []),
                    "error_count": 0,
                },
            }
        if action == "llm_factor_mining":
            llm_payloads.append(payload)
            return {
                "success": True,
                "data": {
                    "codes": list(payload.get("codes") or []),
                    "candidate_count": 1,
                    "candidates": [
                        {
                            "name": "env_loaded_factor",
                            "family": "momentum",
                        }
                    ],
                    "generation_mode": "llm_provider",
                    "fallback_used": False,
                    "fallback_reason": None,
                },
            }
        if action == "validate_factor_candidate":
            return {
                "success": True,
                "data": {"artifact_id": payload["output_artifact_id"]},
            }
        if action == "factor_candidate_registry" and payload.get("op") == "summary":
            return {
                "success": True,
                "data": {
                    "summary": {
                        "count": 1,
                        "governed_active_count": 1,
                        "blocked_active_count": 0,
                    }
                },
            }
        if action == "factor_candidate_registry" and payload.get("op") == "active_pool":
            return {
                "success": True,
                "data": {
                    "active_pool": {
                        "count": 1,
                        "strict_count": 1,
                        "provisional_count": 0,
                    }
                },
            }
        raise AssertionError(f"unexpected action: {action}")

    monkeypatch.setattr(quant_manager_module, "quant_manager", _fake_quant_manager)

    scheduler = FactorScheduler(
        universe=["000001", "000002", "000333", "600519"],
        factors=["reversal"],
        batch_size=2,
    )

    result = await scheduler.run_once()

    assert result["status"] == "success"
    assert len(llm_payloads) == 1
    assert fake_provider.smoke_calls == 1
    assert result["summary"]["llm_provider_gate_status"] == "ready"
    assert result["summary"]["llm_provider_enabled"] is True


@pytest.mark.asyncio
async def test_factor_scheduler_can_opt_into_local_fallback_override(monkeypatch):
    from akshare_mcp.services.factor_scheduler import FactorScheduler
    from akshare_mcp.tools.managers import quant_manager as quant_manager_module

    monkeypatch.setenv("FACTOR_LLM_ENABLED", "1")
    monkeypatch.setenv("FACTOR_SCHEDULER_LLM_MINING", "1")
    monkeypatch.setenv("FACTOR_SCHEDULER_ALLOW_LOCAL_RULE_FALLBACK", "1")
    monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: MagicMock())

    fake_provider = _StickyDegradedProvider()
    monkeypatch.setattr(
        "akshare_mcp.services.factor_llm_provider.get_factor_llm_provider",
        lambda: fake_provider,
    )

    llm_payloads = []

    async def _fake_quant_manager(*, action, code=None, **kwargs):
        del code
        payload = json.loads(kwargs["kwargs"])
        if action == "batch_compute_factors":
            return {
                "success": True,
                "data": {
                    "computed_count": len(payload.get("codes") or []),
                    "error_count": 0,
                },
            }
        if action == "llm_factor_mining":
            llm_payloads.append(payload)
            assert payload["allow_fallback"] is True
            return {
                "success": True,
                "data": {
                    "codes": ["000001", "000002", "000333", "600519"],
                    "candidate_count": 1,
                    "candidates": [{"name": "fallback_factor", "family": "momentum"}],
                    "generation_mode": "local_rule_fallback",
                    "fallback_used": True,
                    "fallback_reason": "provider entered local fallback",
                },
            }
        if action == "validate_factor_candidate":
            return {
                "success": True,
                "data": {"artifact_id": payload["output_artifact_id"]},
            }
        if action == "factor_candidate_registry" and payload.get("op") == "summary":
            return {
                "success": True,
                "data": {
                    "summary": {
                        "count": 1,
                        "governed_active_count": 1,
                        "blocked_active_count": 0,
                    }
                },
            }
        if action == "factor_candidate_registry" and payload.get("op") == "active_pool":
            return {
                "success": True,
                "data": {"active_pool": {"count": 1}},
            }
        raise AssertionError(f"unexpected action: {action}")

    monkeypatch.setattr(quant_manager_module, "quant_manager", _fake_quant_manager)

    scheduler = FactorScheduler(
        universe=["000001", "000002", "000333", "600519"],
        factors=["reversal"],
        batch_size=2,
    )

    result = await scheduler.run_once()

    assert len(llm_payloads) == 1
    assert result["status"] == "success"
    assert result["summary"]["llm_fallback_used"] is True
    assert result["summary"]["llm_allow_local_rule_fallback"] is True
    assert result["summary"]["llm_provider_gate_status"] == "fallback_override"
    assert result["summary"]["llm_provider_gate_reason"] == "scheduler_local_rule_fallback_override"
    assert result["stages"]["llm_factor_mining"]["provider_preflight_action"] == "rebuild_client"
