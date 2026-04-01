from ._test_factor_memory_p2_support import *


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


@pytest.mark.asyncio
async def test_factor_research_memory_recall_uses_db_dense_vector(monkeypatch):
    from akshare_mcp.services.factor_research_memory import FactorResearchMemoryService

    service = FactorResearchMemoryService(embedding_service=_DisabledEmbeddingService())
    scope_codes = ["TMP2DB"]
    success_record = await service.record_validation_outcome(
        candidate=_build_candidate("momentum_20d", name="db_dense_success"),
        validation={"rating": {"grade": "A", "recommendation": "promote"}, "metrics": {"rank_ic_mean": 0.12}},
        codes=scope_codes,
    )
    await service.record_validation_outcome(
        candidate=_build_candidate("pb_ratio", name="db_dense_other"),
        validation={"rating": {"grade": "B", "recommendation": "review"}, "metrics": {"rank_ic_mean": 0.05}},
        codes=scope_codes,
    )

    class _DenseDb:
        async def search_vector_profiles_by_embedding(self, **kwargs):
            assert kwargs["collection_name"] == "factor_candidate_embeddings"
            assert kwargs["profile_type"] == "memory"
            return [
                {
                    "entity_id": success_record["artifact_id"],
                    "similarity": 0.97,
                }
            ]

    monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: _DenseDb())
    matches = await service.recall_similar_candidates(
        candidate=_build_candidate("momentum_20d", name="db_dense_query"),
        codes=scope_codes,
        limit=2,
    )

    assert matches[0]["artifact_id"] == success_record["artifact_id"]
    assert matches[0]["vector_similarity"] == 0.97
    assert matches[0]["embedding_similarity"] >= 0.97


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
async def test_registered_quant_manager_accepts_params_only_for_memory_stats(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod

    class _MemoryStatsService:
        async def summarize_memory_records(self, limit=200, codes=None, status=None, family=None):
            return {
                "total_records": 1,
                "status_counts": {"success": 1},
                "family_counts": {"momentum": 1},
            }

    monkeypatch.setattr(quant_mod, "get_db", lambda: object())
    monkeypatch.setattr(quant_mod, "get_factor_research_memory_service", lambda: _MemoryStatsService())

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    result = await mcp.quant_manager(
        action="factor_research_memory",
        params={"op": "stats", "limit": 5},
    )

    assert result["success"] is True
    assert result["data"]["op"] == "stats"
    assert result["data"]["stats"]["total_records"] == 1


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

__all__ = [name for name in globals() if name.startswith("test_")]
