from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_script_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "scripts" / "audit_sync_factor_context_data.py"
    spec = importlib.util.spec_from_file_location("audit_sync_factor_context_data_test_mod", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeDb:
    def __init__(self, snapshot=None, task_runs=None, latest_factory_run=None, factory_runs=None):
        self._snapshot = snapshot
        self._task_runs = list(task_runs or [])
        self._latest_factory_run = latest_factory_run
        self._factory_runs = list(factory_runs or [])

    async def get_daily_snapshot(self):
        return self._snapshot

    async def list_strategy_task_runs(self, **kwargs):
        del kwargs
        return list(self._task_runs)

    async def get_latest_strategy_factory_run(self):
        return self._latest_factory_run

    async def list_strategy_factory_runs(self, limit=20):
        del limit
        return list(self._factory_runs)


@pytest.mark.asyncio
async def test_resolve_scope_codes_merges_active_pool_representative_and_factory_targets(monkeypatch):
    mod = _load_script_module()
    monkeypatch.setattr(mod, "REPRESENTATIVE_STOCKS", ["600519", "601318", "000001"])

    async def _fake_get_factor_candidate_record_async(artifact_id):
        mapping = {
            "cand_1": {"artifact_id": "cand_1", "codes": ["300750", "000858"]},
            "cand_2": {"artifact_id": "cand_2", "codes": ["002415"]},
        }
        return mapping.get(artifact_id)

    monkeypatch.setattr(mod, "get_factor_candidate_record_async", _fake_get_factor_candidate_record_async)

    db = _FakeDb(
        snapshot={
            "date": "2026-03-23",
            "factor_research": {
                "active_candidate_pool": {
                    "top_candidates": [
                        {"artifact_id": "cand_1"},
                        {"artifact_id": "cand_2"},
                    ]
                }
            },
        },
        task_runs=[
            {
                "task_key": "task_1",
                "started_at": datetime(2026, 3, 23, 10, 0, 0),
                "payload": {
                    "research_task": {"target_symbols": ["601012", "000001"]},
                    "event_context": {"target_symbols": ["300750"]},
                },
            },
            {
                "task_key": "task_2",
                "started_at": datetime(2026, 3, 22, 10, 0, 0),
                "payload": {
                    "research_task": {"target_symbols": ["688981"]},
                },
            },
        ],
    )
    args = SimpleNamespace(
        codes="600036",
        scope_sources="explicit,representative,active_pool,factory_targets",
        active_pool_limit=10,
        task_run_limit=20,
    )

    codes, summary = await mod._resolve_scope_codes(db, args)

    assert codes == ["600036", "600519", "601318", "000001", "300750", "000858", "002415", "601012"]
    assert summary["active_pool"]["artifact_ids"] == ["cand_1", "cand_2"]
    assert summary["factory_targets"]["task_keys"] == ["task_1"]
    assert summary["resolved_count"] == 8


@pytest.mark.asyncio
async def test_resolve_scope_codes_falls_back_to_default_codes_when_sources_empty(monkeypatch):
    mod = _load_script_module()
    monkeypatch.setattr(mod, "DEFAULT_CODES", ["600519", "000858"])
    monkeypatch.setattr(mod, "REPRESENTATIVE_STOCKS", [])

    async def _fake_get_factor_candidate_record_async(artifact_id):
        del artifact_id
        return None

    monkeypatch.setattr(mod, "get_factor_candidate_record_async", _fake_get_factor_candidate_record_async)

    db = _FakeDb(snapshot={"date": "2026-03-23", "factor_research": {"active_candidate_pool": {"top_candidates": []}}}, task_runs=[])
    args = SimpleNamespace(
        codes="",
        scope_sources="active_pool,factory_targets",
        active_pool_limit=10,
        task_run_limit=20,
    )

    codes, summary = await mod._resolve_scope_codes(db, args)

    assert codes == ["600519", "000858"]
    assert summary["factory_targets"]["matched_runs"] == 0
    assert summary["active_pool"]["codes"] == []


@pytest.mark.asyncio
async def test_resolve_scope_codes_prefers_latest_factory_run_active_pool(monkeypatch):
    mod = _load_script_module()
    monkeypatch.setattr(mod, "REPRESENTATIVE_STOCKS", ["600519"])

    async def _fake_get_factor_candidate_record_async(artifact_id):
        del artifact_id
        return None

    async def _fake_get_artifact_async(artifact_id):
        mapping = {
            "factor_validation_001": {
                "artifact_id": "factor_validation_001",
                "strategy": "quant_factor_candidate_validation",
                "payload": {"codes": ["300750", "000858"]},
            },
            "factor_validation_002": {
                "artifact_id": "factor_validation_002",
                "strategy": "quant_factor_candidate_validation",
                "payload": {
                    "coverage": {
                        "per_code_stats": [{"code": "601012"}],
                    }
                },
            },
        }
        return mapping.get(artifact_id)

    monkeypatch.setattr(mod, "get_factor_candidate_record_async", _fake_get_factor_candidate_record_async)
    monkeypatch.setattr(mod, "get_artifact_async", _fake_get_artifact_async)

    db = _FakeDb(
        snapshot={
            "date": "2026-03-22",
            "factor_research": {},
        },
        latest_factory_run={
            "run_id": "factory_run_001",
            "started_at": datetime(2026, 3, 23, 9, 30, 0),
            "snapshot_summary": {
                "date": "2026-03-23",
                "factor_research": {
                    "summary": {
                        "factor_source_mode": "governed_candidate_pool",
                    },
                    "active_candidate_pool": {
                        "count": 2,
                        "top_candidates": [
                            {"artifact_id": "factor_validation_001", "name": "cand_a"},
                        ],
                    },
                },
            },
            "summary": {
                "autonomy_task_briefs": [
                    {"source_candidate_artifact_id": "factor_validation_002"},
                ]
            },
        },
    )
    args = SimpleNamespace(
        codes="",
        scope_sources="active_pool",
        active_pool_limit=10,
        factory_run_limit=5,
        task_run_limit=20,
    )

    codes, summary = await mod._resolve_scope_codes(db, args)

    assert codes == ["300750", "000858", "601012"]
    assert summary["active_pool"]["source"] == "factory_run"
    assert summary["active_pool"]["run_id"] == "factory_run_001"
    assert summary["active_pool"]["snapshot_date"] == "2026-03-23"
    assert summary["active_pool"]["artifact_ids"] == ["factor_validation_001", "factor_validation_002"]
    assert summary["active_pool"]["factor_source_mode"] == "governed_candidate_pool"


@pytest.mark.asyncio
async def test_resolve_scope_codes_filters_non_market_registry_codes(monkeypatch):
    mod = _load_script_module()
    monkeypatch.setattr(mod, "REPRESENTATIVE_STOCKS", [])

    async def _fake_get_factor_candidate_record_async(artifact_id):
        del artifact_id
        return None

    async def _fake_get_artifact_async(artifact_id):
        if artifact_id != "factor_validation_registry_case":
            return None
        return {
            "artifact_id": artifact_id,
            "strategy": "quant_factor_candidate_validation",
            "payload": {
                "codes": ["RG001", "RG002", "600519", "000858"],
            },
        }

    monkeypatch.setattr(mod, "get_factor_candidate_record_async", _fake_get_factor_candidate_record_async)
    monkeypatch.setattr(mod, "get_artifact_async", _fake_get_artifact_async)

    db = _FakeDb(
        latest_factory_run={
            "run_id": "factory_run_registry_case",
            "started_at": datetime(2026, 3, 23, 9, 30, 0),
            "snapshot_summary": {
                "date": "2026-03-23",
                "factor_research": {
                    "summary": {"factor_source_mode": "governed_candidate_pool"},
                    "active_candidate_pool": {
                        "count": 1,
                        "top_candidates": [{"artifact_id": "factor_validation_registry_case"}],
                    },
                },
            },
            "summary": {},
        }
    )
    args = SimpleNamespace(
        codes="RG003,600036",
        scope_sources="explicit,active_pool",
        active_pool_limit=10,
        factory_run_limit=5,
        task_run_limit=20,
    )

    codes, summary = await mod._resolve_scope_codes(db, args)

    assert codes == ["600036", "600519", "000858"]
    assert summary["active_pool"]["codes"] == ["600519", "000858"]
