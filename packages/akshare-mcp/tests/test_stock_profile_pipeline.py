import pytest


class _StockProfileDb:
    def __init__(self):
        self.saved_profiles = []

    async def get_stock_info(self, code):
        return {
            "code": code,
            "name": "贵州茅台" if code == "600519" else "平安银行",
            "industry": "白酒",
            "pe_ratio": 20.0 if code == "600519" else 18.0,
            "pb_ratio": 5.0 if code == "600519" else 4.2,
            "market_cap": 2.1e12 if code == "600519" else 1.6e12,
        }

    async def get_financials(self, code, limit=1):
        del code, limit
        return [
            {
                "roe": 18.0,
                "debt_ratio": 0.35,
                "revenue_growth": 0.12,
                "profit_growth": 0.15,
            }
        ]

    async def get_klines(self, code, limit=90):
        base = 10.0 if code == "600519" else 8.0
        return [
            {
                "close": base + idx * 0.1,
                "volume": 1000 + idx * 10,
            }
            for idx in range(max(limit, 30))
        ]

    async def list_stock_universe(self, *, limit=200, offset=0, min_market_cap=None, industry=None, market=None):
        del offset, min_market_cap, industry, market
        return [
            {"code": "600519", "name": "贵州茅台", "industry": "白酒"},
            {"code": "000001", "name": "平安银行", "industry": "白酒"},
        ][:limit]

    async def list_vector_profiles(self, **kwargs):
        entity_id = kwargs.get("entity_id")
        return [row for row in self.saved_profiles if row.get("entity_id") == entity_id][: kwargs.get("limit", 1)]

    async def save_vector_profile(self, payload):
        self.saved_profiles.append(dict(payload))
        return dict(payload)


@pytest.mark.asyncio
async def test_backfill_stock_profile_vectors_saves_profiles():
    from akshare_mcp.services.stock_profile_pipeline import backfill_stock_profile_vectors

    db = _StockProfileDb()
    result = await backfill_stock_profile_vectors(
        db,
        stock_codes=["600519"],
        profile_types=["fundamental", "both"],
        dry_run=False,
    )

    assert result["processed_codes"] == 1
    assert result["saved_profiles"] == 2
    assert [row["entity_id"] for row in db.saved_profiles] == ["600519|fundamental", "600519|both"]
    assert all(row["collection_name"] == "stock_profile_embeddings" for row in db.saved_profiles)
    assert all(len(row["embedding"]) == 11 for row in db.saved_profiles)


@pytest.mark.asyncio
async def test_build_stock_profile_payload_contains_feature_metadata():
    from akshare_mcp.services.stock_profile_pipeline import build_stock_profile_payload

    db = _StockProfileDb()
    payload = await build_stock_profile_payload(db, "600519", profile_type="technical")

    assert payload is not None
    assert payload["entity_id"] == "600519|technical"
    assert payload["profile_type"] == "technical"
    assert len(payload["embedding"]) == 11
    assert payload["metadata"]["raw_features"]["momentum_20d"] > 0
    assert payload["metadata"]["stock_name"] == "贵州茅台"
