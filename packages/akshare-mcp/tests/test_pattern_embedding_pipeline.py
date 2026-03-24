from __future__ import annotations

import pytest

from akshare_mcp.services.pattern_embedding_pipeline import backfill_kline_pattern_vectors


class _PatternDb:
    def __init__(self):
        self.saved_collections: list[dict] = []
        self.saved_windows: list[dict] = []
        self.saved_profiles: list[dict] = []
        self.ensured_indexes: list[dict] = []

    async def list_stock_universe(self, limit=200, **_kwargs):
        return [
            {"code": "600519", "name": "贵州茅台", "industry": "白酒"},
            {"code": "000001", "name": "平安银行", "industry": "银行"},
        ][:limit]

    async def get_klines(self, code, limit=0):
        base = 100.0 if code == "600519" else 10.0
        return [
            {
                "date": f"2026-03-{day:02d}",
                "code": code,
                "open": base + day - 0.5,
                "high": base + day + 0.8,
                "low": base + day - 0.8,
                "close": base + day,
                "volume": 1000 + day,
            }
            for day in range(1, max(limit, 40) + 1)
        ]

    async def save_vector_collection(self, payload: dict):
        self.saved_collections.append(dict(payload))
        return payload

    async def save_kline_pattern_window(self, payload: dict):
        self.saved_windows.append(dict(payload))
        return payload

    async def save_vector_profile(self, payload: dict):
        self.saved_profiles.append(dict(payload))
        return payload

    async def ensure_vector_profile_pgvector_index(self, **kwargs):
        self.ensured_indexes.append(dict(kwargs))
        return "idx_test"

    def get_vector_backend(self):
        return "pgvector"


@pytest.mark.asyncio
async def test_backfill_kline_pattern_vectors_saves_windows_and_profiles():
    db = _PatternDb()

    result = await backfill_kline_pattern_vectors(
        db,
        code_limit=2,
        window_size=5,
        lookback_days=20,
        max_windows_per_code=2,
        step_days=3,
    )

    assert result["processed_codes"] == 2
    assert result["candidate_windows"] == 4
    assert result["saved_windows"] == 4
    assert result["saved_profiles"] == 4
    assert db.saved_collections[0]["collection_name"] == "kline_pattern_embeddings"
    assert db.saved_windows[0]["window_size"] == 5
    assert db.saved_profiles[0]["entity_type"] == "kline_pattern_window"
    assert db.saved_profiles[0]["profile_type"] == "returns|daily||5"
    assert db.ensured_indexes[0]["collection_name"] == "kline_pattern_embeddings"
