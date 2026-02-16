import math

import pytest

import akshare_mcp.tools.managers.quant_manager as qm


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _FakeDB:
    async def get_klines(self, code, limit=240):
        bars = max(120, int(limit))
        rows = []
        for i in range(bars):
            px = 10.0 + 0.02 * i + 0.8 * math.sin(i / 8.0)
            rows.append(
                {
                    "date": f"2025-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
                    "close": round(px, 4),
                    "volume": 100000 + (i % 15) * 5000,
                    "amount": round(px * (100000 + (i % 15) * 5000), 2),
                }
            )
        # mimic DB behavior: newest first
        return list(reversed(rows))

    async def get_financials(self, code, limit=1):
        return [
            {
                "pe_ratio": 15.0,
                "pb_ratio": 2.0,
                "roe": 0.16,
                "debt_ratio": 0.45,
                "gross_margin": 0.35,
                "roa": 0.08,
            }
        ]


def _patch_alt_sources(monkeypatch):
    monkeypatch.setattr(
        qm,
        "get_stock_news",
        lambda stock_code, limit=20: {
            "success": True,
            "data": [
                {"title": "利好 上调评级"},
                {"title": "buy upgrade outlook"},
                {"title": "风险 提示"},
            ],
        },
    )
    monkeypatch.setattr(
        qm,
        "get_stock_notices",
        lambda start_date, end_date, stock_code="": {
            "success": True,
            "data": {"events": [{"title": "重大突破"}, {"title": "增持计划"}]},
        },
    )
    monkeypatch.setattr(
        qm,
        "get_research_reports",
        lambda symbol="", limit=10: {"success": True, "data": [{"title": "上调目标价"}]},
    )
    monkeypatch.setattr(
        qm,
        "get_stock_fund_flow",
        lambda stock_code: {
            "success": True,
            "data": {
                "mainNetInflow": 350000000.0,
                "largeNetInflow": 220000000.0,
                "superLargeNetInflow": 90000000.0,
                "smallNetInflow": -80000000.0,
            },
        },
    )
    monkeypatch.setattr(
        qm,
        "get_north_fund",
        lambda days=30: {
            "success": True,
            "data": [{"date": f"2026-01-{i:02d}", "total": 150000000.0 + i * 10000000.0} for i in range(1, 8)],
        },
    )


def _patch_artifact_store(monkeypatch):
    store = {}

    def _register(payload):
        store[payload["artifact_id"]] = payload
        return payload

    async def _get_one(artifact_id):
        return store.get(artifact_id)

    async def _list_all(limit=20):
        items = list(store.values())
        return items[-int(limit):]

    monkeypatch.setattr(qm, "register_artifact", _register)
    monkeypatch.setattr(qm, "get_artifact_async", _get_one)
    monkeypatch.setattr(qm, "list_artifacts_async", _list_all)
    return store


@pytest.mark.asyncio
async def test_p2_alternative_factors_action(monkeypatch):
    mcp = _DummyMCP()
    qm.register_quant_manager(mcp)
    monkeypatch.setattr(qm, "get_db", lambda: _FakeDB())
    _patch_alt_sources(monkeypatch)

    result = await mcp.quant_manager(action="alternative_factors", code="600519", lookback_days=30, limit=10)
    assert result["success"] is True
    rows = result["data"]["rows"]
    assert len(rows) == 1
    factors = rows[0]["factors"]
    assert "sentiment" in factors
    assert "event" in factors
    assert "capital_flow" in factors
    assert "alternative_composite" in factors


@pytest.mark.asyncio
async def test_p2_automl_discovery_and_feature_store(monkeypatch):
    mcp = _DummyMCP()
    qm.register_quant_manager(mcp)
    monkeypatch.setattr(qm, "get_db", lambda: _FakeDB())
    _patch_alt_sources(monkeypatch)
    store = _patch_artifact_store(monkeypatch)
    async def _fake_oos(**kwargs):
        return {"success": True, "data": {"summary": {"oos_ic_mean": 0.03}}}

    monkeypatch.setattr(qm, "run_factor_oos_validation", _fake_oos)

    auto = await mcp.quant_manager(
        action="automl_discovery",
        kwargs={
            "codes": ["600519", "000858"],
            "horizon_days": 8,
            "lookback_bars": 180,
            "top_k_features": 5,
            "persist_artifact": True,
            "run_anchor_oos": True,
        },
    )
    assert auto["success"] is True
    auto_data = auto["data"]
    assert auto_data["dataset_stats"]["sample_count"] >= 80
    assert len(auto_data["selected_features"]) >= 2
    assert auto_data["artifact_id"] in store

    snapshot = await mcp.quant_manager(
        action="feature_store",
        kwargs={"op": "snapshot", "codes": ["600519", "000858"]},
    )
    assert snapshot["success"] is True
    snapshot_id = snapshot["data"]["artifact_id"]
    assert snapshot_id in store

    listed = await mcp.quant_manager(action="feature_store", kwargs={"op": "list", "limit": 20})
    assert listed["success"] is True
    assert listed["data"]["count"] >= 1

    get_one = await mcp.quant_manager(action="feature_store", kwargs={"op": "get", "artifact_id": snapshot_id})
    assert get_one["success"] is True
    assert get_one["data"]["artifact"]["artifact_id"] == snapshot_id

    replay = await mcp.quant_manager(action="replay_experiment", kwargs={"artifact_id": auto_data["artifact_id"]})
    assert replay["success"] is True
    assert "metric_delta" in replay["data"]
    assert "test_ic" in replay["data"]["metric_delta"]
