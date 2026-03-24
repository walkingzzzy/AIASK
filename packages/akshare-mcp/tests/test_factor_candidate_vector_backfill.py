import pytest


class _FactorVectorDb:
    def __init__(self):
        self.saved_profiles = []

    async def list_vector_profiles(self, **kwargs):
        entity_id = kwargs.get("entity_id")
        return [row for row in self.saved_profiles if row.get("entity_id") == entity_id][: kwargs.get("limit", 1)]

    async def save_vector_profile(self, payload):
        self.saved_profiles.append(dict(payload))
        return dict(payload)


@pytest.mark.asyncio
async def test_backfill_factor_candidate_vectors_saves_profiles(monkeypatch):
    from akshare_mcp.services import factor_candidate_vector_backfill as mod

    async def _fake_list_records(**kwargs):
        assert kwargs["status"] == "success"
        return [
            {
                "artifact_id": "mem_001",
                "status": "success",
                "codes": ["600519"],
                "tags": ["success", "family:momentum"],
                "candidate": {
                    "name": "mom_a",
                    "family": "momentum",
                    "hypothesis": "强动量带来超额收益",
                    "expression_dsl": "momentum_20d",
                    "inputs": ["close"],
                    "expected_holding_period": 10,
                    "expected_regime": ["trend"],
                },
                "rating": {"grade": "A", "recommendation": "promote"},
            },
            {
                "artifact_id": "mem_002",
                "status": "success",
                "codes": ["000001"],
                "tags": ["success", "family:value"],
                "candidate": {
                    "name": "value_a",
                    "family": "value",
                    "hypothesis": "低估值修复",
                    "expression_dsl": "pb_ratio",
                    "inputs": ["close"],
                    "expected_holding_period": 20,
                    "expected_regime": ["reversion"],
                },
                "rating": {"grade": "B", "recommendation": "review"},
            },
        ]

    monkeypatch.setattr(mod, "list_factor_candidate_records_async", _fake_list_records)

    db = _FactorVectorDb()
    result = await mod.backfill_factor_candidate_vectors(
        db,
        limit=20,
        status="success",
        dry_run=False,
    )

    assert result["candidate_records"] == 2
    assert result["saved_profiles"] == 2
    assert [row["entity_id"] for row in db.saved_profiles] == ["mem_001", "mem_002"]
    assert all(row["collection_name"] == "factor_candidate_embeddings" for row in db.saved_profiles)
    assert all(row["profile_type"] == "memory" for row in db.saved_profiles)
