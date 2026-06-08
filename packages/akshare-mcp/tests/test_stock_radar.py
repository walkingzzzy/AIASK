from __future__ import annotations

import asyncio
import json
from datetime import date

from aiask_quant_core.storage.sqlite import SQLiteAdapter

from akshare_mcp.services.stock_radar import (
    enhance_radar_event_with_llm,
    extract_radar_event,
    _confirmation_factors,
    push_stock_radar_digest,
    run_stock_radar,
    score_radar_candidate,
)


def test_stock_radar_rule_extraction_detects_contract() -> None:
    extraction = extract_radar_event(
        {
            "doc_uid": "cninfo:1",
            "title": "Company signs AI compute cooperation contract",
            "summary": "The company signed a 5亿元 AI compute service contract.",
            "stock_code": "600000",
            "source_tier": "tier_a",
        }
    )

    assert extraction is not None
    payload = extraction.as_dict()
    assert payload["event_type"] == "ai_compute_cooperation"
    assert payload["direction"] == "positive"
    assert payload["amount_text"]
    assert payload["source_doc_uids"] == ["cninfo:1"]


def test_stock_radar_score_applies_risk_penalty() -> None:
    positive = score_radar_candidate(
        extraction={"importance_score": 0.9, "direction": "positive"},
        source_tier="tier_a",
        confirmations={"sector_heat": {"score": 0.5}},
    )
    risky = score_radar_candidate(
        extraction={"importance_score": 0.9, "direction": "negative", "risk_flags": ["investigation"]},
        source_tier="tier_a",
        confirmations={"sector_heat": {"score": 0.5}},
    )

    assert positive["radar_score"] > risky["radar_score"]
    assert risky["component_scores"]["risk_penalty"] >= 18


def _patch_degraded_confirmations(monkeypatch) -> None:
    import akshare_mcp.services.stock_radar as radar_mod

    async def fake_confirmations(_db, symbol, extraction):
        return {
            "fund_flow": {"status": "degraded", "confirmed": False, "reason": "test"},
            "north_fund": {"status": "degraded", "confirmed": False, "reason": "test"},
            "dragon_tiger": {"status": "degraded", "confirmed": False, "reason": "test", "alias_policy": "alias_mapping_only"},
            "sector_heat": {"status": "degraded", "score": 0.0, "themes": list(extraction.get("themes") or []), "reason": "test"},
            "late_session_volume": {"status": "disabled", "confirmed": False, "reason": "test"},
            "symbol": symbol,
        }

    monkeypatch.setattr(radar_mod, "_confirmation_factors", fake_confirmations)


def test_stock_radar_run_uses_existing_market_documents_with_degraded_fallbacks(tmp_path, monkeypatch) -> None:
    import akshare_mcp.services.stock_radar as radar_mod

    async def fake_ingest(*args, **kwargs):
        return {"totals": {"saved_docs": 0}, "fetched": {}, "errors": [], "quality_flags": []}

    monkeypatch.setattr(radar_mod, "run_market_text_source_ingest", fake_ingest)
    _patch_degraded_confirmations(monkeypatch)
    db = SQLiteAdapter(path=tmp_path / "stock_radar_run.sqlite3")

    async def _run() -> None:
        try:
            await db.initialize()
            await db.save_market_documents(
                "600000",
                "notice",
                [
                    {
                        "doc_uid": "cninfo:radar:1",
                        "title": "Company signs AI compute cooperation contract",
                        "summary": "Official disclosure says the company signed a major AI compute contract.",
                        "content": "Official disclosure says the company signed a major AI compute contract.",
                        "published_at": date.today().isoformat(),
                        "source": "cninfo",
                        "provider": "cninfo",
                        "source_tier": "tier_a",
                        "url": "https://static.cninfo.com.cn/finalpage/mock.pdf",
                    }
                ],
                embed=False,
            )
            result = await run_stock_radar(
                db,
                mode="dry_run",
                days=3,
                limit=10,
                allow_network=False,
                ingest_market_text=True,
            )

            assert result["success"] is True
            data = result["data"]
            assert data["candidate_count"] == 1
            assert data["candidates"][0]["event_type"] == "ai_compute_cooperation"
            assert "network_disabled" in data["degraded_flags"]
            assert "llm_unavailable_rules_only" in data["degraded_flags"]
            assert data["candidates"][0]["confirmations"]["late_session_volume"]["status"] == "disabled"
            assert data["candidates"][0]["extraction"]["llm_status"] == "unavailable"
            assert data["candidates"][0]["extraction"]["score"]["component_scores"]["risk_penalty"] >= 8
            async with db.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT metadata FROM market_documents WHERE doc_uid = $1",
                    "cninfo:radar:1",
                )
            metadata = json.loads(row["metadata"])
            assert metadata["radar_pdf_parse"]["status"] == "degraded"
            assert metadata["radar_pdf_parse"]["reason"] == "network_disabled"

            push = await push_stock_radar_digest(
                db,
                {
                    "run_id": data["run"]["run_id"],
                    "channels": ["wecom"],
                    "dry_run": False,
                },
            )
            assert push["success"] is False
            assert push["error_code"] == "STOCK_RADAR_PUSH_REQUIRES_HIGH_CONFIDENCE"
            assert push["data"]["push_logs"][0]["status"] == "blocked"
        finally:
            await db.close()

    asyncio.run(_run())


def test_stock_radar_pdf_parse_success_feeds_llm_and_persists_metadata(tmp_path, monkeypatch) -> None:
    import akshare_mcp.services.stock_radar as radar_mod

    async def fake_ingest(*args, **kwargs):
        return {"totals": {}, "fetched": {}, "errors": [], "quality_flags": []}

    monkeypatch.setattr(radar_mod, "run_market_text_source_ingest", fake_ingest)
    monkeypatch.setattr(
        radar_mod,
        "_download_pdf_file",
        lambda url: {"local_pdf_path": str(tmp_path / "mock.pdf"), "checksum": "abc123", "bytes": 1234},
    )
    monkeypatch.setattr(
        radar_mod,
        "_extract_pdf_text_from_file",
        lambda path: {
            "status": "ok",
            "parser": "pymupdf",
            "text": "PDF says the company signed a 5亿元 AI compute cooperation contract with CloudCo.",
            "pages": 1,
            "text_density": 92,
        },
    )
    _patch_degraded_confirmations(monkeypatch)

    class FakeProvider:
        def is_enabled(self):
            return True

        async def call_stage(self, **kwargs):
            assert "PDF says" in kwargs["input_data"]["pdf_text"]
            return {
                "event": {
                    "event_type": "ai_compute_cooperation",
                    "direction": "positive",
                    "importance_score": 0.95,
                    "sentiment_score": 0.8,
                    "themes": ["AI", "算力"],
                    "amount_text": "5亿元",
                    "counterparties": ["CloudCo"],
                    "risk_flags": [],
                    "summary": "AI compute cooperation contract",
                    "confidence": 0.86,
                    "source_doc_uids": ["cninfo:radar:llm"],
                }
            }

    monkeypatch.setattr("akshare_mcp.services.strategy_llm_provider.get_strategy_llm_provider", lambda: FakeProvider())
    db = SQLiteAdapter(path=tmp_path / "stock_radar_pdf.sqlite3")

    async def _run() -> None:
        try:
            await db.initialize()
            await db.save_market_documents(
                "600000",
                "notice",
                [
                    {
                        "doc_uid": "cninfo:radar:llm",
                        "title": "Company signs AI compute cooperation contract",
                        "summary": "Official disclosure has details in PDF.",
                        "content": "Official disclosure has details in PDF.",
                        "published_at": date.today().isoformat(),
                        "source": "cninfo",
                        "provider": "cninfo",
                        "source_tier": "tier_a",
                        "url": "https://static.cninfo.com.cn/finalpage/mock.pdf",
                    }
                ],
                embed=False,
            )
            result = await run_stock_radar(
                db,
                mode="dry_run",
                days=3,
                limit=5,
                allow_network=True,
                ingest_market_text=True,
            )

            assert result["success"] is True
            candidate = result["data"]["candidates"][0]
            assert candidate["extraction"]["llm_status"] == "ok"
            assert candidate["extraction"]["status"] == "verified"
            assert candidate["extraction"]["confidence"] == 0.86
            assert candidate["extraction"]["score"]["component_scores"]["risk_penalty"] == 0
            async with db.acquire() as conn:
                row = await conn.fetchrow("SELECT metadata FROM market_documents WHERE doc_uid = $1", "cninfo:radar:llm")
            metadata = json.loads(row["metadata"])
            assert metadata["radar_pdf_parse"]["status"] == "ok"
            assert metadata["radar_pdf_parse"]["local_pdf_path"]
            assert "text" not in metadata["radar_pdf_parse"]
        finally:
            await db.close()

    asyncio.run(_run())


def test_stock_radar_llm_failure_keeps_rule_fallback(monkeypatch) -> None:
    class FailingProvider:
        def is_enabled(self):
            return True

        async def call_stage(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr("akshare_mcp.services.strategy_llm_provider.get_strategy_llm_provider", lambda: FailingProvider())
    fallback = extract_radar_event(
        {
            "doc_uid": "cninfo:fail",
            "title": "Company signs AI compute cooperation contract",
            "summary": "Official disclosure says AI compute contract.",
            "stock_code": "600000",
        }
    )
    assert fallback is not None

    extraction, meta = asyncio.run(enhance_radar_event_with_llm({"doc_uid": "cninfo:fail"}, fallback))

    assert extraction["event_type"] == "ai_compute_cooperation"
    assert extraction["status"] == "provisional"
    assert extraction["llm_status"] == "failed"
    assert meta["status"] == "failed"


def test_stock_radar_confirmation_factors_use_existing_fund_tools(monkeypatch) -> None:
    import akshare_mcp.tools.fund_flow as fund_flow_tools

    monkeypatch.setattr(
        fund_flow_tools,
        "get_stock_fund_flow",
        lambda **kwargs: {"success": True, "data": {"code": "600000", "mainNetInflow": 12_000_000, "source": "db.stock_fund_flow"}},
    )
    monkeypatch.setattr(
        fund_flow_tools,
        "get_north_fund",
        lambda **kwargs: {"success": True, "data": {"items": [{"total": 1.2}, {"total": 0.8}, {"total": -0.2}], "source": "db"}},
    )
    monkeypatch.setattr(
        fund_flow_tools,
        "get_dragon_tiger",
        lambda **kwargs: {"success": True, "data": [{"code": "600000", "netAmount": 5_000_000}]},
    )
    monkeypatch.setattr(
        fund_flow_tools,
        "get_sector_fund_flow",
        lambda **kwargs: {"success": True, "data": [{"name": "AI", "mainNetInflow": 9_000_000, "changePercent": 0.03}]},
    )
    monkeypatch.setattr(
        fund_flow_tools,
        "get_concept_fund_flow",
        lambda **kwargs: {"success": True, "data": [{"name": "算力", "mainNetInflow": 8_000_000, "changePercent": 0.02}]},
    )

    class NoMinuteDb:
        class _Conn:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def fetchval(self, *args, **kwargs):
                return None

        def acquire(self):
            return self._Conn()

    confirmations = asyncio.run(
        _confirmation_factors(
            NoMinuteDb(),
            "600000",
            {"direction": "positive", "themes": ["AI", "算力"]},
        )
    )

    assert confirmations["fund_flow"]["confirmed"] is True
    assert confirmations["north_fund"]["confirmed"] is True
    assert confirmations["dragon_tiger"]["confirmed"] is True
    assert confirmations["sector_heat"]["score"] > 0
    assert confirmations["late_session_volume"]["status"] == "disabled"
