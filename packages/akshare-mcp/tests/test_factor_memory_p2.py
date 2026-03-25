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


def _register_validation_artifact(
    artifact_id: str,
    codes: list[str],
    *,
    name: str,
    recommendation: str,
    total_score: float,
    lookahead_risk: str = "low",
    multiple_testing_risk: str = "low",
    source_generation_artifact_id: str | None = None,
    wf_stability: float = 0.72,
    kf_stability: float = 0.68,
    wf_degradation: float = 0.03,
    kf_degradation: float = 0.04,
):
    from akshare_mcp.services import register_artifact

    register_artifact(
        {
            "artifact_id": artifact_id,
            "strategy": "quant_factor_candidate_validation",
            "strategy_version": "p2.v1",
            "code": ",".join(codes),
            "payload": {
                "artifact_id": artifact_id,
                "action": "validate_factor_candidate",
                "codes": list(codes),
                "candidate": _build_candidate("momentum_20d", name=name),
                "metrics": {"rank_ic_mean": 0.11, "rank_ic_ir": 0.72, "sample_dates": 36},
                "candidate_resolution": {
                    "artifact_id": source_generation_artifact_id,
                },
                "factor_validation_report": {
                    "oos": {
                        "available": True,
                        "walk_forward": {
                            "stability_ratio": wf_stability,
                            "degradation": wf_degradation,
                            "oos_rank_ic_mean": 0.08,
                            "oos_rank_ic_ir": 0.61,
                        },
                        "purged_kfold": {
                            "stability_ratio": kf_stability,
                            "degradation": kf_degradation,
                            "oos_rank_ic_mean": 0.07,
                            "oos_rank_ic_ir": 0.55,
                        },
                    }
                },
                "rating": {
                    "grade": "A" if recommendation == "promote" else "B",
                    "recommendation": recommendation,
                    "total_score": total_score,
                },
                "lookahead_audit": {
                    "available": True,
                    "risk_level": lookahead_risk,
                },
                "multiple_testing": {
                    "available": True,
                    "risk_level": multiple_testing_risk,
                },
                "warnings": [
                    *(["lookahead_audit_failed"] if lookahead_risk == "high" else []),
                    *(["multiple_testing_failed"] if multiple_testing_risk == "high" else []),
                ],
                "stage": "validated",
            },
        }
    )


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
async def test_quant_manager_factor_candidate_registry_active_pool_blocks_high_risk_candidates(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    import akshare_mcp.services.artifact_registry as _ar_mod

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())
    monkeypatch.setattr(_ar_mod, "_get_db", lambda: None)

    registry_codes = ["991111", "991112", "991113", "991114"]
    _register_validation_artifact(
        "factor_validation_registry_governed_safe",
        registry_codes,
        name="governed_safe",
        recommendation="promote",
        total_score=92.0,
        lookahead_risk="low",
        multiple_testing_risk="low",
    )
    _register_validation_artifact(
        "factor_validation_registry_governed_lookahead_high",
        registry_codes,
        name="governed_lookahead_high",
        recommendation="promote",
        total_score=95.0,
        lookahead_risk="high",
        multiple_testing_risk="low",
    )
    _register_validation_artifact(
        "factor_validation_registry_governed_multiple_high",
        registry_codes,
        name="governed_multiple_high",
        recommendation="review",
        total_score=89.0,
        lookahead_risk="low",
        multiple_testing_risk="high",
    )

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    registry_summary = await mcp.quant_manager(
        action="factor_candidate_registry",
        kwargs={"op": "summary", "codes": registry_codes, "limit": 20, "market_codes_only": True},
    )

    assert registry_summary["success"] is True
    summary = registry_summary["data"]["summary"]
    assert summary["count"] >= 3
    assert summary["lookahead_risk_counts"]["high"] >= 1
    assert summary["multiple_testing_risk_counts"]["high"] >= 1
    assert summary["blocked_count"] >= 2
    assert summary["governed_active_count"] >= 1

    active_pool = await mcp.quant_manager(
        action="factor_candidate_registry",
        kwargs={"op": "active_pool", "codes": registry_codes, "limit": 20, "market_codes_only": True},
    )

    assert active_pool["success"] is True
    pool = active_pool["data"]["active_pool"]
    top_artifact_ids = [str(item.get("artifact_id") or "") for item in pool["top_candidates"]]
    assert "factor_validation_registry_governed_safe" in top_artifact_ids
    assert "factor_validation_registry_governed_lookahead_high" not in top_artifact_ids
    assert "factor_validation_registry_governed_multiple_high" not in top_artifact_ids
    assert pool["count"] == 1
    assert pool["excluded_count"] >= 2
    assert pool["exclusion_reason_counts"]["lookahead_risk_high"] >= 1
    assert pool["exclusion_reason_counts"]["multiple_testing_risk_high"] >= 1

    excluded = {str(item.get("artifact_id") or ""): item for item in pool["excluded_candidates"]}
    assert "lookahead_risk_high" in excluded["factor_validation_registry_governed_lookahead_high"]["reasons"]
    assert "multiple_testing_risk_high" in excluded["factor_validation_registry_governed_multiple_high"]["reasons"]


@pytest.mark.asyncio
async def test_quant_manager_model_registry_and_champion_challenger_review(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    import akshare_mcp.services.artifact_registry as _ar_mod

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())
    monkeypatch.setattr(_ar_mod, "_get_db", lambda: None)

    registry_codes = ["301901", "301902", "301903", "301904"]
    _register_validation_artifact(
        "factor_validation_registry_cc_champion",
        registry_codes,
        name="cc_champion",
        recommendation="promote",
        total_score=94.0,
        lookahead_risk="low",
        multiple_testing_risk="low",
    )
    _register_validation_artifact(
        "factor_validation_registry_cc_challenger",
        registry_codes,
        name="cc_challenger",
        recommendation="review",
        total_score=88.0,
        lookahead_risk="low",
        multiple_testing_risk="low",
    )

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    review = await mcp.quant_manager(
        action="champion_challenger",
        kwargs={
            "op": "review",
            "codes": registry_codes,
            "limit": 20,
            "persist_artifact": False,
            "update_registry": True,
            "market_codes_only": True,
        },
    )

    assert review["success"] is True
    data = review["data"]
    assert data["champion"]["artifact_id"] == "factor_validation_registry_cc_champion"
    assert data["challengers"][0]["artifact_id"] == "factor_validation_registry_cc_challenger"
    assert data["registered_models"][0]["deployment_stage"] == "champion"
    assert data["registered_models"][1]["deployment_stage"] == "challenger"

    registry_list = await mcp.quant_manager(
        action="model_registry",
        kwargs={"op": "list", "family": "momentum", "limit": 20},
    )
    assert registry_list["success"] is True
    items = registry_list["data"]["items"]
    assert len(items) >= 2
    assert any(item["deployment_stage"] == "champion" for item in items)
    assert any(item["deployment_stage"] == "challenger" for item in items)

    registry_summary = await mcp.quant_manager(
        action="model_registry",
        kwargs={"op": "summary", "family": "momentum", "limit": 20},
    )
    assert registry_summary["success"] is True
    summary = registry_summary["data"]["summary"]
    assert summary["champion_count"] >= 1
    assert summary["challenger_count"] >= 1


@pytest.mark.asyncio
async def test_quant_manager_model_registry_lifecycle_scan_and_retrain_plan(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    import akshare_mcp.services.artifact_registry as _ar_mod
    from akshare_mcp.services import register_artifact

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())
    monkeypatch.setattr(_ar_mod, "_get_db", lambda: None)

    registry_codes = ["302101", "302102", "302103", "302104"]
    generation_artifact_id = "factor_llm_episode_lifecycle_case"
    register_artifact(
        {
            "artifact_id": generation_artifact_id,
            "strategy": "quant_llm_factor_mining",
            "strategy_version": "p0.v1",
            "code": ",".join(registry_codes),
            "payload": {
                "artifact_id": generation_artifact_id,
                "action": "llm_factor_mining",
                "codes": list(registry_codes),
                "candidate_count": 1,
                "candidates": [_build_candidate("momentum_20d", name="lifecycle_model")],
            },
        }
    )
    _register_validation_artifact(
        "factor_validation_registry_lifecycle_champion",
        registry_codes,
        name="lifecycle_champion",
        recommendation="promote",
        total_score=84.0,
        source_generation_artifact_id=generation_artifact_id,
        wf_stability=0.18,
        kf_stability=0.24,
        wf_degradation=0.17,
        kf_degradation=0.15,
    )
    _register_validation_artifact(
        "factor_validation_registry_lifecycle_challenger",
        registry_codes,
        name="lifecycle_challenger",
        recommendation="review",
        total_score=83.2,
        source_generation_artifact_id=generation_artifact_id,
        wf_stability=0.42,
        kf_stability=0.39,
        wf_degradation=0.05,
        kf_degradation=0.04,
    )
    register_artifact(
        {
            "artifact_id": "factor_episode_lifecycle_replay",
            "strategy": "quant_factor_episode_replay",
            "strategy_version": "p2.v2",
            "code": ",".join(registry_codes),
            "payload": {
                "artifact_id": "factor_episode_lifecycle_replay",
                "action": "replay_factor_episode",
                "source_artifact_id": generation_artifact_id,
                "codes": list(registry_codes),
                "episode_summary": {
                    "validated_count": 0,
                    "failed_count": 3,
                },
            },
        }
    )

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    review = await mcp.quant_manager(
        action="champion_challenger",
        kwargs={
            "op": "review",
            "codes": registry_codes,
            "limit": 20,
            "persist_artifact": True,
            "update_registry": True,
            "market_codes_only": True,
        },
    )
    assert review["success"] is True
    assert review["data"]["review_status"] == "tight_race"

    lifecycle = await mcp.quant_manager(
        action="model_registry",
        kwargs={
            "op": "lifecycle_scan",
            "family": "momentum",
            "limit": 20,
            "persist_artifact": False,
            "stability_floor": 0.35,
            "degradation_ceiling": 0.08,
            "tight_race_gap": 5.0,
            "replay_success_floor": 0.6,
        },
    )
    assert lifecycle["success"] is True
    scan_items = lifecycle["data"]["items"]
    champion_item = next(item for item in scan_items if item["deployment_stage"] == "champion")
    assert "high_degradation" in champion_item["flags"]
    assert "low_stability" in champion_item["flags"]
    assert "challenger_pressure" in champion_item["flags"]
    assert "replay_decay" in champion_item["flags"]
    assert champion_item["recommended_action"] == "schedule_retrain"
    assert lifecycle["data"]["summary"]["retrain_recommended_count"] >= 1

    retrain_plan = await mcp.quant_manager(
        action="model_registry",
        kwargs={
            "op": "schedule_retrain",
            "artifact_id": champion_item["artifact_id"],
            "family": "momentum",
            "only_flagged": True,
        },
    )
    assert retrain_plan["success"] is True
    plan = retrain_plan["data"]["plan"]
    assert plan["target_model_count"] >= 1
    assert generation_artifact_id in plan["target_generation_artifact_ids"]
    assert "high_degradation" in plan["reason_codes"]
    assert plan["next_action"] == "replay_factor_episode"

    retrain_list = await mcp.quant_manager(
        action="model_registry",
        kwargs={"op": "retrain_list", "family": "momentum", "limit": 20},
    )
    assert retrain_list["success"] is True
    assert retrain_list["data"]["count"] >= 1

    retrain_summary = await mcp.quant_manager(
        action="model_registry",
        kwargs={"op": "retrain_summary", "family": "momentum", "limit": 20},
    )
    assert retrain_summary["success"] is True
    assert retrain_summary["data"]["summary"]["count"] >= 1


@pytest.mark.asyncio
async def test_quant_manager_execute_retrain_and_retrain_status(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    import akshare_mcp.services.artifact_registry as _ar_mod
    from akshare_mcp.services import register_artifact

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())
    monkeypatch.setattr(_ar_mod, "_get_db", lambda: None)

    registry_codes = ["303101", "303102", "303103", "303104"]
    generation_artifact_id = "factor_llm_episode_retrain_execute_case"
    register_artifact(
        {
            "artifact_id": generation_artifact_id,
            "strategy": "quant_llm_factor_mining",
            "strategy_version": "p0.v1",
            "code": ",".join(registry_codes),
            "payload": {
                "artifact_id": generation_artifact_id,
                "action": "llm_factor_mining",
                "codes": list(registry_codes),
                "candidate_count": 2,
                "candidates": [
                    _build_candidate("momentum_20d", name="retrain_good"),
                    _build_candidate("foobar(close)", name="retrain_bad"),
                ],
            },
        }
    )
    _register_validation_artifact(
        "factor_validation_registry_retrain_execute_champion",
        registry_codes,
        name="retrain_execute_champion",
        recommendation="promote",
        total_score=91.0,
        source_generation_artifact_id=generation_artifact_id,
    )
    _register_validation_artifact(
        "factor_validation_registry_retrain_execute_challenger",
        registry_codes,
        name="retrain_execute_challenger",
        recommendation="review",
        total_score=86.0,
        source_generation_artifact_id=generation_artifact_id,
    )

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    review = await mcp.quant_manager(
        action="champion_challenger",
        kwargs={
            "op": "review",
            "codes": registry_codes,
            "limit": 20,
            "persist_artifact": False,
            "update_registry": True,
            "market_codes_only": True,
        },
    )
    assert review["success"] is True

    registry_list = await mcp.quant_manager(
        action="model_registry",
        kwargs={
            "op": "list",
            "deployment_stage": "champion",
            "family": "momentum",
            "limit": 20,
        },
    )
    assert registry_list["success"] is True
    champion_item = next(
        item
        for item in registry_list["data"]["items"]
        if item["deployment_stage"] == "champion"
        and item["source_generation_artifact_id"] == generation_artifact_id
    )

    retrain_plan = await mcp.quant_manager(
        action="model_registry",
        kwargs={
            "op": "schedule_retrain",
            "artifact_id": champion_item["artifact_id"],
            "family": "momentum",
            "only_flagged": False,
            "codes": registry_codes,
        },
    )
    assert retrain_plan["success"] is True
    plan_id = retrain_plan["data"]["artifact_id"]

    retrain_execute = await mcp.quant_manager(
        action="model_registry",
        kwargs={
            "op": "execute_retrain",
            "artifact_id": plan_id,
            "codes": registry_codes,
            "lookback_bars": 180,
            "horizon_days": 10,
            "max_dates": 40,
            "write_memory": False,
            "update_registry": True,
        },
    )
    assert retrain_execute["success"] is True
    run = retrain_execute["data"]["run"]
    plan = retrain_execute["data"]["plan"]
    assert run["status"] == "completed"
    assert run["plan_id"] == plan_id
    assert run["execution_summary"]["target_model_count"] == 1
    assert run["execution_summary"]["replay_run_count"] == 1
    assert run["execution_summary"]["validation_run_count"] == 1
    assert run["execution_summary"]["registry_update_count"] == 1
    assert plan["last_run_artifact_id"] == run["artifact_id"]
    assert plan["last_run_status"] == "completed"
    assert plan["run_count"] == 1

    status_by_plan = await mcp.quant_manager(
        action="model_registry",
        kwargs={"op": "retrain_status", "artifact_id": plan_id},
    )
    assert status_by_plan["success"] is True
    assert status_by_plan["data"]["latest_run"]["artifact_id"] == run["artifact_id"]
    assert status_by_plan["data"]["run_summary"]["count"] >= 1

    status_by_run = await mcp.quant_manager(
        action="model_registry",
        kwargs={"op": "retrain_status", "artifact_id": run["artifact_id"]},
    )
    assert status_by_run["success"] is True
    assert status_by_run["data"]["run"]["artifact_id"] == run["artifact_id"]
    assert status_by_run["data"]["plan"]["last_run_artifact_id"] == run["artifact_id"]


@pytest.mark.asyncio
async def test_quant_manager_replay_factor_episode_revalidates_candidate_batch(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    import akshare_mcp.services.artifact_registry as _ar_mod
    from akshare_mcp.services import register_artifact

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())
    monkeypatch.setattr(_ar_mod, "_get_db", lambda: None)

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
