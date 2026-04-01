from datetime import date, timedelta

import pytest


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _ValidationDB:
    _GROWTH = {
        "000001": 1.0010,
        "000002": 1.0020,
        "000003": 1.0030,
        "000004": 1.0040,
    }

    async def get_klines(self, code, limit=220):
        growth = float(self._GROWTH.get(code, 1.0015))
        start = date(2025, 1, 1)
        close = 10.0
        rows = []
        for idx in range(max(240, int(limit))):
            prev_close = close
            close = prev_close * growth
            volume = 100000 + idx * 1000 + int(code[-1]) * 100
            rows.append(
                {
                    "date": str(start + timedelta(days=idx)),
                    "open": round(prev_close, 6),
                    "high": round(close * 1.01, 6),
                    "low": round(prev_close * 0.99, 6),
                    "close": round(close, 6),
                    "volume": volume,
                    "amount": round(volume * close, 2),
                }
            )
        return rows[-int(limit):]


def _build_candidate(expression="momentum_20d"):
    return {
        "name": "trend_factor_v1",
        "hypothesis": "更强的中期动量对应更高的未来收益。",
        "family": "momentum",
        "inputs": ["close"],
        "expression_dsl": expression,
        "expected_holding_period": 10,
        "expected_regime": ["trend"],
        "complexity_hint": "low",
        "novelty_rationale": "以最小 DSL 验证因子编译与横截面验证闭环。",
    }


def test_compile_factor_candidate_accepts_supported_expression():
    from akshare_mcp.services.factor_candidate_compiler import compile_factor_candidate

    compiled = compile_factor_candidate(_build_candidate("zscore(momentum_20d, 20)"))

    assert compiled["valid"] is True
    assert "momentum_20d" in compiled["referenced_fields"]
    assert "zscore" in compiled["function_calls"]


def test_compile_factor_candidate_rejects_unsupported_function():
    from akshare_mcp.services.factor_candidate_compiler import compile_factor_candidate

    compiled = compile_factor_candidate(_build_candidate("foobar(close)"))

    assert compiled["valid"] is False
    assert compiled["unsupported_functions"] == ["foobar"]


@pytest.mark.asyncio
async def test_validate_factor_candidate_pipeline_produces_metrics():
    from akshare_mcp.services.factor_validation_pipeline import validate_factor_candidate_pipeline

    result = await validate_factor_candidate_pipeline(
        _ValidationDB(),
        _build_candidate("momentum_20d"),
        codes=["000001", "000002", "000003", "000004"],
        lookback_bars=200,
        horizon_days=5,
        max_dates=40,
    )

    assert result["success"] is True
    assert result["metrics"]["sample_dates"] >= 10
    assert result["metrics"]["rank_ic_mean"] > 0.8
    assert result["coverage"]["processed_codes"] == 4
    assert result["lookahead_audit"]["available"] is True
    assert result["lookahead_audit"]["risk_level"] == "low"
    assert result["lookahead_audit"]["tail_check"]["passed"] is True
    assert result["multiple_testing"]["available"] is True
    assert "deflated_sharpe" in result["multiple_testing"]
    assert "pbo" in result["multiple_testing"]
    assert result["oos_validation"]["available"] is True
    assert result["robustness"]["available"] is True
    assert result["similarity"]["available"] is True
    assert result["cost_capacity"]["available"] is True
    assert result["factor_validation_report"]["rating"]["grade"] in {"A", "B"}
    assert result["rating"]["governance"]["admission_blocked"] is False
    assert result["rating"]["governance"]["registry_stage"] == "governed"
    assert result["rating"]["component_scores"]["governance"] > 0.0


@pytest.mark.asyncio
async def test_quant_manager_validate_factor_candidate_from_artifact(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    from akshare_mcp.services import register_artifact

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())

    artifact_id = "test_factor_llm_seed_artifact"
    register_artifact(
        {
            "artifact_id": artifact_id,
            "strategy": "quant_llm_factor_mining",
            "strategy_version": "p0.v1",
            "code": "000001,000002,000003,000004",
            "payload": {
                "artifact_id": artifact_id,
                "action": "llm_factor_mining",
                "codes": ["000001", "000002", "000003", "000004"],
                "candidates": [_build_candidate("momentum_20d")],
            },
        }
    )

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    result = await mcp.quant_manager(
        action="validate_factor_candidate",
        kwargs={
            "artifact_id": artifact_id,
            "candidate_index": 0,
            "lookback_bars": 200,
            "horizon_days": 5,
            "max_dates": 40,
            "persist_artifact": False,
        },
    )

    assert result["success"] is True
    assert result["data"]["candidate_resolution"]["resolved_from"] == "artifact_candidate"
    assert result["data"]["metrics"]["rank_ic_mean"] > 0.8
    assert result["data"]["coverage"]["processed_codes"] == 4
    assert result["data"]["multiple_testing"]["available"] is True
    assert result["data"]["factor_validation_report"]["oos"]["available"] is True
    assert result["data"]["factor_validation_report"]["multiple_testing"]["available"] is True
    assert result["data"]["factor_validation_report"]["robustness"]["available"] is True
    assert result["data"]["rating"]["grade"] in {"A", "B"}
    assert result["data"]["governance"]["admission_blocked"] is False
    assert result["data"]["registry_stage"] == "governed"
    assert result["data"]["lineage"]["source_generation_artifact_id"] == artifact_id
    assert result["data"]["lineage"]["source_validation_artifact_id"] == result["data"]["artifact_id"]


@pytest.mark.asyncio
async def test_validate_factor_candidate_pipeline_flags_suspicious_future_literal():
    from akshare_mcp.services.factor_validation_pipeline import validate_factor_candidate_pipeline

    result = await validate_factor_candidate_pipeline(
        _ValidationDB(),
        _build_candidate("delay(close, -1)"),
        codes=["000001", "000002", "000003", "000004"],
        lookback_bars=180,
        horizon_days=5,
        max_dates=30,
    )

    assert result["success"] is True
    assert result["lookahead_audit"]["available"] is True
    assert result["lookahead_audit"]["risk_level"] == "high"
    assert "negative_delay_or_delta_literal" in result["lookahead_audit"]["candidate_expression"]["suspicious_tokens"]
    assert "lookahead_audit_failed" in result["warnings"]
    assert result["rating"]["governance"]["admission_blocked"] is True
    assert "lookahead_risk_high" in result["rating"]["governance"]["admission_block_reasons"]


def test_validation_rating_blocks_admission_when_multiple_testing_is_unavailable():
    from akshare_mcp.services.factor_validation_pipeline import _build_validation_rating

    rating = _build_validation_rating(
        {"rank_ic_mean": 0.12},
        {
            "available": True,
            "rating": {"total_score": 80.0},
            "walk_forward": {"stability_ratio": 0.61, "degradation": 0.04},
            "purged_kfold": {"stability_ratio": 0.58, "degradation": 0.05},
        },
        {"available": True, "robustness_score": 0.72},
        {"available": True, "top_similar_basis": [{"correlation": 0.21}]},
        {"available": True, "estimated_cost_rate": 0.0015, "execution_score": 0.82},
        {"available": True, "risk_level": "low"},
        {"available": False, "reason": "insufficient_panel_shape"},
    )

    assert rating["grade"] in {"A", "B", "C"}
    assert rating["governance"]["admission_blocked"] is True
    assert rating["governance"]["registry_stage"] == "validated"
    assert "multiple_testing_unavailable" in rating["governance"]["admission_block_reasons"]
    assert rating["governance"]["governance_recommendation"] == "watch"
