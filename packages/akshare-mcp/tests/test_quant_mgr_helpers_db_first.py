from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from akshare_mcp.tools.managers import quant_mgr_helpers as helpers_mod


class _AltFactorDb:
    def __init__(self):
        self.get_north_fund_history = AsyncMock(
            return_value=[
                {"trade_date": date(2026, 3, 20), "north_money": 2.2e9, "source": "north_fund_flow"},
                {"trade_date": date(2026, 3, 19), "north_money": 2.0e9, "source": "north_fund_flow"},
                {"trade_date": date(2026, 3, 18), "north_money": 1.9e9, "source": "north_fund_flow"},
                {"trade_date": date(2026, 3, 17), "north_money": 1.8e9, "source": "north_fund_flow"},
                {"trade_date": date(2026, 3, 16), "north_money": 1.7e9, "source": "north_fund_flow"},
            ]
        )


class _AcquireContext:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DbFirstConn:
    async def fetch(self, query, *params):
        if "FROM vector_documents" in query:
            code = params[0]
            doc_types = set(params[1])
            if "news" in doc_types:
                return [{"id": 1, "doc_type": "news", "content": f"{code} 利好 新闻", "date": "2026-03-20"}]
            if "notice" in doc_types or "announcement" in doc_types:
                return [{"id": 2, "doc_type": "notice", "content": f"{code} 公告 进展", "date": "2026-03-19"}]
            if "research" in doc_types or "report" in doc_types:
                return []
        if "FROM research_reports" in query:
            code = params[0]
            return [
                {
                    "code": code,
                    "title": f"{code} upgrade",
                    "rating": "buy",
                    "target_price": 11.0,
                    "institution": "DB Broker",
                    "analyst": "Analyst B",
                    "publish_date": "2026-03-18",
                    "summary": "数据库研报",
                    "pdf_url": "",
                }
            ]
        return []

    async def fetchrow(self, query, *params):
        if "FROM stock_fund_flow" in query:
            code = params[0]
            return {
                "code": code,
                "trade_date": "2026-03-20",
                "main_net_inflow": 5e8,
                "large_net_inflow": 2e8,
                "super_large_net_inflow": 1e8,
                "small_net_inflow": 1e8,
            }
        return None


class _DbFirstAltFactorDb(_AltFactorDb):
    def __init__(self):
        super().__init__()
        self._conn = _DbFirstConn()

    def acquire(self):
        return _AcquireContext(self._conn)


@pytest.mark.asyncio
async def test_compute_alternative_factors_prefers_db_north_history(monkeypatch):
    db = _AltFactorDb()
    monkeypatch.setattr(
        helpers_mod,
        "get_stock_news",
        lambda code, limit=5: {"success": True, "data": [{"title": f"{code} 利好"}]},
    )
    monkeypatch.setattr(
        helpers_mod,
        "get_stock_notices",
        lambda start_date, end_date, stock_code: {"success": True, "data": [{"title": f"{stock_code} 公告"}]},
    )
    monkeypatch.setattr(
        helpers_mod,
        "get_research_reports",
        lambda code, limit=5: {"success": True, "data": [{"title": f"{code} upgrade"}]},
    )
    monkeypatch.setattr(
        helpers_mod,
        "get_stock_fund_flow",
        lambda code: {
            "success": True,
            "data": {
                "mainNetInflow": 5e8,
                "largeNetInflow": 2e8,
                "superLargeNetInflow": 1e8,
                "smallNetInflow": 1e8,
            },
        },
    )
    monkeypatch.setattr(
        helpers_mod,
        "get_north_fund",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("north fallback should not run")),
    )

    factors, source_chain = await helpers_mod._compute_alternative_factors_for_code(
        db=db,
        code="600519",
        lookback_days=10,
        limit=5,
    )

    assert "db.get_north_fund_history" in source_chain
    assert factors["capital_flow"]["north_flow_score_raw"] > 0.0
    assert factors["alternative_composite"]["score_raw"] > -1.0
    db.get_north_fund_history.assert_awaited_once()


@pytest.mark.asyncio
async def test_compute_alternative_factors_prefers_db_text_and_flow_context(monkeypatch):
    db = _DbFirstAltFactorDb()
    monkeypatch.setattr(
        helpers_mod,
        "get_stock_news",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("stock news fallback should not run")),
    )
    monkeypatch.setattr(
        helpers_mod,
        "get_stock_notices",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("stock notices fallback should not run")),
    )
    monkeypatch.setattr(
        helpers_mod,
        "get_research_reports",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("research fallback should not run")),
    )
    monkeypatch.setattr(
        helpers_mod,
        "get_stock_fund_flow",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fund flow fallback should not run")),
    )
    monkeypatch.setattr(
        helpers_mod,
        "get_north_fund",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("north fallback should not run")),
    )

    factors, source_chain = await helpers_mod._compute_alternative_factors_for_code(
        db=db,
        code="600519",
        lookback_days=10,
        limit=5,
    )

    assert "db.vector_documents.news" in source_chain
    assert "db.vector_documents.notice" in source_chain
    assert "db.research_reports" in source_chain
    assert "db.stock_fund_flow" in source_chain
    assert factors["sentiment"]["headline_count"] >= 3
    assert factors["capital_flow"]["score_raw"] > 0.0
