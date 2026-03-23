from datetime import date, timedelta
from types import SimpleNamespace

import pytest


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _DisabledEmbeddingService:
    config = SimpleNamespace(provider="disabled", model="")

    def is_enabled(self):
        return False

    async def embed_text(self, text):
        raise RuntimeError("embedding disabled")


class _PromptDB:
    async def get_klines(self, code, limit=180):
        return [
            {"date": "2026-03-17", "open": 10.0, "high": 10.5, "low": 9.9, "close": 10.2, "volume": 1000, "amount": 2000.0},
            {"date": "2026-03-18", "open": 10.2, "high": 10.6, "low": 10.0, "close": 10.4, "volume": 1100, "amount": 2100.0},
            {"date": "2026-03-19", "open": 10.4, "high": 10.8, "low": 10.3, "close": 10.7, "volume": 1400, "amount": 2600.0},
            {"date": "2026-03-20", "open": 10.7, "high": 11.0, "low": 10.6, "close": 10.9, "volume": 1500, "amount": 2800.0},
            {"date": "2026-03-21", "open": 10.9, "high": 11.2, "low": 10.8, "close": 11.1, "volume": 1700, "amount": 3000.0},
        ] * 30

    async def get_financials(self, code, limit=4):
        return [
            {
                "roe": 18.2,
                "roa": 9.1,
                "gross_margin": 42.0,
                "debt_ratio": 0.31,
                "revenue_growth": 12.5,
                "profit_growth": 15.6,
            }
        ]


class _ValidationDB:
    async def get_klines(self, code, limit=220):
        rows = []
        close = 10.0
        start = date(2025, 1, 1)
        for idx in range(max(240, int(limit))):
            close *= 1.002 + (int(str(code)[-1]) * 0.0001)
            volume = 100000 + idx * 1000
            rows.append(
                {
                    "date": str(start + timedelta(days=idx)),
                    "open": round(close * 0.998, 6),
                    "high": round(close * 1.01, 6),
                    "low": round(close * 0.99, 6),
                    "close": round(close, 6),
                    "volume": volume,
                    "amount": round(close * volume, 2),
                }
            )
        return rows[-int(limit):]


def _build_candidate(expression="momentum_20d", name="trend_factor_v2"):
    return {
        "name": name,
        "hypothesis": "更强的中期动量对应更高的未来收益。",
        "family": "momentum",
        "inputs": ["close"],
        "expression_dsl": expression,
        "expected_holding_period": 10,
        "expected_regime": ["trend"],
        "complexity_hint": "low",
        "novelty_rationale": "P2 memory integration test candidate.",
    }


@pytest.mark.asyncio
async def test_factor_research_memory_records_and_recalls_without_embedding():
    from akshare_mcp.services.factor_research_memory import FactorResearchMemoryService

    service = FactorResearchMemoryService(embedding_service=_DisabledEmbeddingService())
    success_record = await service.record_validation_outcome(
        candidate=_build_candidate("momentum_20d", name="memory_success"),
        validation={"rating": {"grade": "A", "recommendation": "promote"}, "metrics": {"rank_ic_mean": 0.12}},
        codes=["TM001"],
    )
    await service.record_validation_outcome(
        candidate=_build_candidate("volatility_20d", name="memory_fail"),
        validation={"rating": {"grade": "D", "recommendation": "reject"}, "metrics": {"rank_ic_mean": -0.02}},
        codes=["TM001"],
    )

    matches = await service.recall_similar_candidates(
        candidate=_build_candidate("momentum_20d", name="memory_query"),
        codes=["TM001"],
        limit=2,
    )

    assert matches[0]["artifact_id"] == success_record["artifact_id"]
    assert matches[0]["similarity"] >= matches[-1]["similarity"]

    context = await service.build_prompt_memory_context(codes=["TM001"], limit=4)
    assert context["available"] is True
    assert len(context["success_examples"]) >= 1
    assert len(context["failure_examples"]) >= 1


@pytest.mark.asyncio
async def test_factor_research_memory_persists_similarity_edges_and_stats():
    from akshare_mcp.services.factor_research_memory import FactorResearchMemoryService

    service = FactorResearchMemoryService(embedding_service=_DisabledEmbeddingService())
    scope_codes = ["TMP2EDGE"]
    seed = await service.record_validation_outcome(
        candidate=_build_candidate("momentum_20d", name="edge_seed"),
        validation={"rating": {"grade": "A", "recommendation": "promote"}, "metrics": {"rank_ic_mean": 0.11}},
        codes=scope_codes,
    )
    duplicate = await service.record_validation_outcome(
        candidate=_build_candidate("momentum_20d", name="edge_duplicate"),
        validation={
            "rating": {"grade": "B", "recommendation": "review"},
            "metrics": {"rank_ic_mean": 0.05},
            "robustness": {"available": True, "grade": "weak", "robustness_score": 0.25},
        },
        codes=scope_codes,
    )

    assert duplicate["similarity_edges"][0]["artifact_id"] == seed["artifact_id"]
    assert duplicate["similarity_edges"][0]["edge_type"] == "duplicate"
    assert "duplicate" in duplicate["tags"]
    assert "unstable" in duplicate["tags"]

    stats = await service.summarize_memory_records(codes=scope_codes, limit=10)
    assert stats["total_records"] >= 2
    assert stats["duplicate_like_count"] >= 1
    assert stats["unstable_count"] >= 1


def test_factor_research_memory_duplicate_policy_blocks_candidates():
    from akshare_mcp.services.factor_research_memory import FactorResearchMemoryService

    service = FactorResearchMemoryService(embedding_service=_DisabledEmbeddingService())
    policy = service.apply_duplicate_policy(
        [
            {
                "name": "dup_factor",
                "duplicate_block_recommended": True,
                "generation_trace": {"memory_similarity": {"similarity": 0.991, "top_status": "success", "edge_type": "duplicate"}},
            },
            {
                "name": "failed_pattern_factor",
                "generation_trace": {"memory_similarity": {"similarity": 0.95, "top_status": "fail", "edge_type": "failure_pattern"}},
            },
            {
                "name": "fresh_factor",
                "generation_trace": {"memory_similarity": {"similarity": 0.28, "top_status": "review", "edge_type": "semantic_neighbor"}},
            },
        ],
        dedup_mode="block",
    )

    assert policy["summary"]["blocked_count"] == 2
    assert len(policy["kept_candidates"]) == 1
    assert policy["kept_candidates"][0]["name"] == "fresh_factor"


@pytest.mark.asyncio
async def test_factor_prompt_builder_accepts_memory_context(monkeypatch):
    import akshare_mcp.services.factor_prompt_builder as prompt_mod

    async def _fake_alt(db, code, lookback_days=30, limit=6):
        return ({"alternative_composite": {"score_raw": 0.2}}, ["tools.news.*"])

    monkeypatch.setattr(prompt_mod, "_compute_alternative_factors_for_code", _fake_alt)
    monkeypatch.setattr(prompt_mod, "get_stock_news", lambda code, limit=6: {"success": True, "data": [{"title": f"{code} 新闻"}]})
    monkeypatch.setattr(prompt_mod, "get_stock_notices", lambda start_date, end_date, stock_code: {"success": True, "data": [{"title": f"{stock_code} 公告"}]})
    monkeypatch.setattr(prompt_mod, "get_research_reports", lambda code, limit=6: {"success": True, "data": [{"title": f"{code} 研报"}]})
    monkeypatch.setattr(prompt_mod, "get_stock_fund_flow", lambda code: {"success": True, "data": {"mainNetInflow": 1000}})

    prompt = await prompt_mod.build_factor_mining_prompt(
        db=_PromptDB(),
        codes=["600519"],
        candidate_count=2,
        memory_context={"available": True, "success_examples": [{"name": "old_factor"}], "failure_examples": []},
    )

    assert prompt.request_payload["memory_context"]["available"] is True
    assert prompt.context_summary["memory_context"]["available"] is True
    assert "memory_context" in prompt.user_prompt


@pytest.mark.asyncio
async def test_quant_manager_integrates_memory_context_and_memory_write(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    from akshare_mcp.services.factor_prompt_builder import FactorMiningPrompt

    class _DisabledProvider:
        config = SimpleNamespace(provider="openai_compatible", model="")

        def is_enabled(self):
            return False

    class _FakeMemoryService:
        async def build_prompt_memory_context(self, **kwargs):
            return {"available": True, "success_examples": [{"name": "old_success"}], "failure_examples": []}

        async def annotate_generated_candidates(self, candidates, **kwargs):
            out = []
            for item in list(candidates or []):
                row = dict(item)
                row["duplicate_risk"] = "high"
                out.append(row)
            return {"candidates": out, "warnings": ["memory_dedup_applied"]}

        async def record_validation_outcome(self, **kwargs):
            return {"artifact_id": "factor_memory_test_record", "status": "success"}

        async def list_memory_records(self, **kwargs):
            return [{"artifact_id": "factor_memory_test_record", "status": "success"}]

        async def get_memory_record(self, artifact_id):
            return {"artifact_id": artifact_id, "status": "success"}

        async def recall_similar_candidates(self, **kwargs):
            return [{"artifact_id": "factor_memory_test_record", "status": "success", "similarity": 0.97}]

        async def summarize_memory_records(self, **kwargs):
            return {"total_records": 1, "status_counts": {"success": 1}}

        def apply_duplicate_policy(self, candidates, **kwargs):
            return {
                "mode": kwargs.get("dedup_mode", "penalty"),
                "kept_candidates": list(candidates or []),
                "blocked_candidates": [],
                "summary": {
                    "input_count": len(list(candidates or [])),
                    "kept_count": len(list(candidates or [])),
                    "blocked_count": 0,
                    "blocked_ratio": 0.0,
                },
                "warnings": [],
            }

    async def _fake_prompt_builder(db, codes, **kwargs):
        return FactorMiningPrompt(
            system_prompt="system",
            user_prompt="user",
            context_summary={"codes": list(codes), "rows": [], "memory_context": kwargs.get("memory_context")},
            request_payload={"codes": list(codes), "memory_context": kwargs.get("memory_context")},
            source_chain=["services.factor_prompt_builder"],
            schema_path="/tmp/factor_candidate.schema.json",
        )

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())
    monkeypatch.setattr(quant_mod, "get_factor_llm_provider", lambda: _DisabledProvider())
    monkeypatch.setattr(quant_mod, "build_factor_mining_prompt", _fake_prompt_builder)
    monkeypatch.setattr(quant_mod, "get_factor_research_memory_service", lambda: _FakeMemoryService())

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    mining = await mcp.quant_manager(
        action="llm_factor_mining",
        code="600519",
        kwargs={"candidate_count": 2, "persist_artifact": False},
    )

    assert mining["success"] is True
    assert mining["data"]["memory_context"]["available"] is True
    assert mining["data"]["candidates"][0]["duplicate_risk"] == "high"

    validation = await mcp.quant_manager(
        action="validate_factor_candidate",
        kwargs={
            "candidate": _build_candidate("momentum_20d", name="memory_validate"),
            "codes": ["000001", "000002", "000003", "000004"],
            "persist_artifact": False,
        },
    )

    assert validation["success"] is True
    assert validation["data"]["memory_record"]["artifact_id"] == "factor_memory_test_record"

    memory_list = await mcp.quant_manager(
        action="factor_research_memory",
        kwargs={"op": "list", "limit": 5},
    )
    assert memory_list["success"] is True
    assert memory_list["data"]["op"] == "list"

    memory_stats = await mcp.quant_manager(
        action="factor_research_memory",
        kwargs={"op": "stats", "limit": 5},
    )
    assert memory_stats["success"] is True
    assert memory_stats["data"]["op"] == "stats"


@pytest.mark.asyncio
async def test_quant_manager_blocks_high_similarity_candidates_when_requested(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    from akshare_mcp.services.factor_prompt_builder import FactorMiningPrompt
    from akshare_mcp.services.factor_research_memory import FactorResearchMemoryService

    class _BlockingProvider:
        config = SimpleNamespace(provider="openai_compatible", model="factor-test-model")

        def is_enabled(self):
            return True

        async def generate_candidates(self, prompt, candidate_count=2):
            return {
                "provider": "openai_compatible",
                "model": "factor-test-model",
                "candidate_count": 2,
                "candidates": [
                    _build_candidate("momentum_20d", name="dup_factor"),
                    _build_candidate("volatility_20d", name="fresh_factor"),
                ],
                "analysis": {"mode": "test"},
                "warnings": [],
            }

    class _BlockingMemoryService:
        async def build_prompt_memory_context(self, **kwargs):
            return {"available": True, "success_examples": [], "failure_examples": []}

        async def annotate_generated_candidates(self, candidates, **kwargs):
            rows = []
            for item in list(candidates or []):
                row = dict(item)
                if row.get("name") == "dup_factor":
                    row["duplicate_risk"] = "high"
                    row["duplicate_block_recommended"] = True
                    row["duplicate_reason"] = "与历史失败候选模式高度相似"
                    row["generation_trace"] = {
                        "memory_similarity": {
                            "similarity": 0.991,
                            "top_status": "fail",
                            "edge_type": "failure_pattern",
                        }
                    }
                else:
                    row["duplicate_risk"] = "low"
                    row["duplicate_block_recommended"] = False
                    row["generation_trace"] = {
                        "memory_similarity": {
                            "similarity": 0.21,
                            "top_status": "review",
                            "edge_type": "semantic_neighbor",
                        }
                    }
                rows.append(row)
            return {"candidates": rows, "warnings": []}

        def apply_duplicate_policy(self, candidates, **kwargs):
            service = FactorResearchMemoryService(embedding_service=_DisabledEmbeddingService())
            return service.apply_duplicate_policy(candidates, **kwargs)

    async def _fake_prompt_builder(db, codes, **kwargs):
        return FactorMiningPrompt(
            system_prompt="system",
            user_prompt="user",
            context_summary={"codes": list(codes), "rows": [], "memory_context": kwargs.get("memory_context")},
            request_payload={"codes": list(codes), "memory_context": kwargs.get("memory_context")},
            source_chain=["services.factor_prompt_builder"],
            schema_path="/tmp/factor_candidate.schema.json",
        )

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())
    monkeypatch.setattr(quant_mod, "get_factor_llm_provider", lambda: _BlockingProvider())
    monkeypatch.setattr(quant_mod, "build_factor_mining_prompt", _fake_prompt_builder)
    monkeypatch.setattr(quant_mod, "get_factor_research_memory_service", lambda: _BlockingMemoryService())

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    mining = await mcp.quant_manager(
        action="llm_factor_mining",
        code="600519",
        kwargs={"candidate_count": 2, "persist_artifact": False, "dedup_mode": "block"},
    )

    assert mining["success"] is True
    assert mining["data"]["candidate_count"] == 1
    assert mining["data"]["candidates"][0]["name"] == "fresh_factor"
    assert mining["data"]["blocked_candidates"][0]["name"] == "dup_factor"


@pytest.mark.asyncio
async def test_quant_manager_factor_candidate_registry_lists_validated_candidates(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod

    registry_codes = ["RG001", "RG002", "RG003", "RG004"]
    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    validation = await mcp.quant_manager(
        action="validate_factor_candidate",
        kwargs={
            "candidate": _build_candidate("momentum_20d", name="registry_factor"),
            "codes": registry_codes,
            "output_artifact_id": "factor_validation_registry_case",
            "write_memory": False,
        },
    )

    assert validation["success"] is True

    registry_list = await mcp.quant_manager(
        action="factor_candidate_registry",
        kwargs={"op": "list", "codes": registry_codes, "limit": 10},
    )

    assert registry_list["success"] is True
    assert registry_list["data"]["count"] >= 1
    assert any(item["artifact_id"] == "factor_validation_registry_case" for item in registry_list["data"]["items"])

    registry_summary = await mcp.quant_manager(
        action="factor_candidate_registry",
        kwargs={"op": "summary", "codes": registry_codes, "limit": 20},
    )
    assert registry_summary["success"] is True
    assert registry_summary["data"]["summary"]["count"] >= 1

    active_pool = await mcp.quant_manager(
        action="factor_candidate_registry",
        kwargs={"op": "active_pool", "codes": registry_codes, "limit": 20},
    )
    assert active_pool["success"] is True
    assert active_pool["data"]["active_pool"]["count"] >= 1
    assert any(item["family"] == "momentum" for item in active_pool["data"]["active_pool"]["family_summary"])


@pytest.mark.asyncio
async def test_quant_manager_factor_candidate_registry_active_pool_can_filter_non_market_codes(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    invalid_validation = await mcp.quant_manager(
        action="validate_factor_candidate",
        kwargs={
            "candidate": _build_candidate("momentum_20d", name="registry_invalid_market_code"),
            "codes": ["RG001", "RG002", "RG003", "RG004"],
            "output_artifact_id": "factor_validation_registry_non_market_only",
            "write_memory": False,
        },
    )
    assert invalid_validation["success"] is True

    valid_validation = await mcp.quant_manager(
        action="validate_factor_candidate",
        kwargs={
            "candidate": _build_candidate("momentum_20d", name="registry_valid_market_code"),
            "codes": ["600519", "000858", "000333", "601318"],
            "output_artifact_id": "factor_validation_registry_market_only",
            "write_memory": False,
        },
    )
    assert valid_validation["success"] is True

    active_pool = await mcp.quant_manager(
        action="factor_candidate_registry",
        kwargs={"op": "active_pool", "market_codes_only": True, "limit": 50},
    )

    assert active_pool["success"] is True
    top_artifact_ids = [str(item.get("artifact_id") or "") for item in active_pool["data"]["active_pool"]["top_candidates"]]
    assert "factor_validation_registry_non_market_only" not in top_artifact_ids
    assert "factor_validation_registry_market_only" in top_artifact_ids


@pytest.mark.asyncio
async def test_quant_manager_replay_factor_episode_revalidates_candidate_batch(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    from akshare_mcp.services import register_artifact

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())

    source_artifact_id = "factor_llm_episode_case"
    register_artifact(
        {
            "artifact_id": source_artifact_id,
            "strategy": "quant_llm_factor_mining",
            "strategy_version": "p0.v1",
            "code": "RG001,RG002,RG003,RG004",
            "payload": {
                "artifact_id": source_artifact_id,
                "action": "llm_factor_mining",
                "codes": ["RG001", "RG002", "RG003", "RG004"],
                "generation_mode": "llm_provider",
                "provider": "openai_compatible",
                "model": "test-model",
                "candidate_count": 2,
                "candidates": [
                    _build_candidate("momentum_20d", name="episode_good"),
                    _build_candidate("foobar(close)", name="episode_bad"),
                ],
                "params": {"lookback_bars": 200},
            },
        }
    )

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    replay = await mcp.quant_manager(
        action="replay_factor_episode",
        kwargs={
            "artifact_id": source_artifact_id,
            "write_memory": False,
            "codes": ["RG001", "RG002", "RG003", "RG004"],
        },
    )

    assert replay["success"] is True
    assert replay["data"]["episode_summary"]["replayed_candidate_count"] == 2
    assert replay["data"]["episode_summary"]["validated_count"] == 1
    assert replay["data"]["episode_summary"]["failed_count"] == 1
    assert any(item["status"] == "validated" for item in replay["data"]["outcomes"])
    assert any(item["status"] == "failed" for item in replay["data"]["outcomes"])

    replay_list = await mcp.quant_manager(
        action="replay_factor_episode",
        kwargs={"op": "list", "source_artifact_id": source_artifact_id, "limit": 10},
    )
    assert replay_list["success"] is True
    assert replay_list["data"]["count"] >= 1

    replay_get = await mcp.quant_manager(
        action="replay_factor_episode",
        kwargs={"op": "get", "artifact_id": replay["data"]["artifact_id"]},
    )
    assert replay_get["success"] is True
    assert replay_get["data"]["item"]["source_artifact_id"] == source_artifact_id

    replay_summary = await mcp.quant_manager(
        action="replay_factor_episode",
        kwargs={"op": "summary", "source_artifact_id": source_artifact_id, "limit": 10},
    )
    assert replay_summary["success"] is True
    assert replay_summary["data"]["summary"]["count"] >= 1
