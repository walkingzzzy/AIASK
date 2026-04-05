"""多阶段 AI 策略生成 Pipeline 端到端测试。

覆盖:
1. Stage 定义与注册表完整性
2. 各阶段 validator 正确判定
3. 各阶段 fallback 在无 LLM 时正常产出
4. Pipeline 端到端全流程（纯 fallback 路径）
5. Pipeline provenance 追踪完整
6. Pipeline candidates → StrategySpec 转换
7. PIPELINE_MODE 开关路由验证
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from akshare_mcp.services.strategy_stages import (
    EXTENDED_THEME_LIBRARY,
    STAGE_ORDER,
    StageDefinition,
    StageResult,
    _fallback_exposure_mapping,
    _fallback_strategy_generation,
    _validate_event_recognition,
    _validate_theme_propagation,
    _validate_exposure_mapping,
    _validate_market_confirmation,
    _validate_strategy_generation,
    get_stage_registry,
    validate_stage_output,
)
from akshare_mcp.services.strategy_pipeline import (
    MultiStageStrategyPipeline,
    PipelineResult,
    get_strategy_pipeline,
)
from akshare_mcp.services.strategy_factory.constants import (
    PIPELINE_MODE,
    PIPELINE_STAGE_MAX_TOKENS,
    PIPELINE_STAGE_TEMPERATURE,
    PIPELINE_STAGE_TIMEOUT_SEC,
)


# ---------------------------------------------------------------------------
# Helpers: mock db
# ---------------------------------------------------------------------------

class _MockDB:
    """极简 mock DB，支持 fallback 函数中需要的方法。"""

    async def get_klines(self, code: str, limit: int = 100) -> list[dict]:
        """返回简单的模拟 K 线数据。"""
        base = 10.0
        klines = []
        for i in range(limit):
            close = base + i * 0.05
            klines.append({
                "date": f"2026-01-{i+1:02d}",
                "open": close - 0.02,
                "close": close,
                "high": close + 0.03,
                "low": close - 0.04,
                "volume": 100000 + i * 1000,
            })
        return klines

    async def list_stock_universe(self, limit: int = 200, offset: int = 0) -> list[dict]:
        """返回模拟的股票池。"""
        return [
            {"code": "600519", "name": "贵州茅台", "industry": "白酒", "sector": "消费"},
            {"code": "000858", "name": "五粮液", "industry": "白酒", "sector": "消费"},
            {"code": "601318", "name": "中国平安", "industry": "保险", "sector": "金融"},
            {"code": "600036", "name": "招商银行", "industry": "银行", "sector": "金融"},
            {"code": "002415", "name": "海康威视", "industry": "安防", "sector": "科技"},
            {"code": "300750", "name": "宁德时代", "industry": "锂电池", "sector": "新能源"},
            {"code": "601012", "name": "隆基绿能", "industry": "光伏", "sector": "新能源"},
            {"code": "600276", "name": "恒瑞医药", "industry": "创新药", "sector": "医药"},
            {"code": "000001", "name": "平安银行", "industry": "银行", "sector": "金融"},
            {"code": "600585", "name": "海螺水泥", "industry": "建材", "sector": "基建"},
        ]


MOCK_SNAPSHOT = {
    "fear_greed": {"score": 55, "label": "neutral"},
    "date": "2026-03-10",
    "sentiment": "neutral",
    "hot_sectors": [
        {"group": "白酒", "change_pct": 2.5},
        {"group": "半导体", "change_pct": 1.8},
        {"group": "新能源", "change_pct": 1.2},
    ],
    "north_fund": {"net_inflow": 50000000},
    "dragon_tiger": [
        {"code": "600519", "name": "贵州茅台", "direction": "buy"},
    ],
}


# ===========================================================================
# Test 1: Stage 定义与注册表完整性
# ===========================================================================

class TestStageRegistry:
    def test_stage_order_has_5_stages(self):
        assert len(STAGE_ORDER) == 5
        assert STAGE_ORDER == [
            "event_recognition",
            "theme_propagation",
            "exposure_mapping",
            "market_confirmation",
            "strategy_generation",
        ]

    def test_registry_contains_all_stages(self):
        registry = get_stage_registry()
        for stage_id in STAGE_ORDER:
            assert stage_id in registry, f"Missing stage: {stage_id}"
            stage_def = registry[stage_id]
            assert isinstance(stage_def, StageDefinition)
            assert stage_def.stage_id == stage_id

    def test_each_stage_has_dedicated_prompt(self):
        registry = get_stage_registry()
        prompts = set()
        for stage_id in STAGE_ORDER:
            prompt = registry[stage_id].system_prompt
            assert prompt, f"Stage {stage_id} has empty prompt"
            assert len(prompt) > 50, f"Stage {stage_id} prompt too short ({len(prompt)} chars)"
            assert prompt not in prompts, f"Stage {stage_id} prompt duplicates another stage"
            prompts.add(prompt)

    def test_strategy_generation_prompt_tightens_snapshot_family_tasks(self):
        registry = get_stage_registry()
        prompt = registry["strategy_generation"].system_prompt

        assert "不得同时输出 momentum 和 ma_cross" in prompt
        assert "allowed_strategy_types" in prompt
        assert "lookback>=20" in prompt

    def test_each_stage_has_fallback(self):
        registry = get_stage_registry()
        for stage_id in STAGE_ORDER:
            assert registry[stage_id].fallback_fn is not None, f"Stage {stage_id} missing fallback_fn"
            assert callable(registry[stage_id].fallback_fn)

    def test_each_stage_has_required_output_keys(self):
        expected_keys = {
            "event_recognition": ["events"],
            "theme_propagation": ["themes"],
            "exposure_mapping": ["exposures"],
            "market_confirmation": ["confirmations"],
            "strategy_generation": ["candidates"],
        }
        registry = get_stage_registry()
        for stage_id, keys in expected_keys.items():
            assert registry[stage_id].required_output_keys == keys

    def test_each_stage_uses_constants_config(self):
        registry = get_stage_registry()
        for stage_id in STAGE_ORDER:
            stage = registry[stage_id]
            assert stage.max_tokens == PIPELINE_STAGE_MAX_TOKENS.get(stage_id, 500)
            assert stage.temperature == PIPELINE_STAGE_TEMPERATURE.get(stage_id, 0.2)

    def test_extended_theme_library_has_20_themes(self):
        assert len(EXTENDED_THEME_LIBRARY) == 20
        codes = [t["theme_code"] for t in EXTENDED_THEME_LIBRARY]
        assert len(set(codes)) == 20, "Duplicate theme_codes detected"
        for t in EXTENDED_THEME_LIBRARY:
            assert "name" in t
            assert "aliases" in t
            assert isinstance(t["aliases"], list) and len(t["aliases"]) > 0


# ===========================================================================
# Test 2: 各阶段 validator
# ===========================================================================

class TestStageValidators:
    def test_event_recognition_valid(self):
        assert _validate_event_recognition({
            "events": [{"theme_code": "chip_domestic", "event_type": "sector_rotation"}]
        })

    def test_event_recognition_invalid_empty(self):
        assert not _validate_event_recognition({"events": []})
        assert not _validate_event_recognition({})

    def test_event_recognition_invalid_missing_keys(self):
        assert not _validate_event_recognition({"events": [{"theme_code": "x"}]})  # no event_type

    def test_theme_propagation_valid(self):
        assert _validate_theme_propagation({
            "themes": [{"theme_code": "chip_domestic", "direction": "bullish"}]
        })

    def test_theme_propagation_invalid(self):
        assert not _validate_theme_propagation({"themes": []})
        assert not _validate_theme_propagation({"themes": [{}]})

    def test_exposure_mapping_valid(self):
        assert _validate_exposure_mapping({
            "exposures": [{"theme_code": "chip_domestic", "target_symbols": ["002415"]}]
        })

    def test_exposure_mapping_invalid(self):
        assert not _validate_exposure_mapping({"exposures": [{"theme_code": "x"}]})

    def test_market_confirmation_valid(self):
        assert _validate_market_confirmation({
            "confirmations": [{"symbol": "002415", "confirmed": True}]
        })

    def test_market_confirmation_invalid(self):
        assert not _validate_market_confirmation({"confirmations": [{"symbol": "x"}]})  # no confirmed
        assert not _validate_market_confirmation({"confirmations": [{"confirmed": True}]})  # no symbol

    def test_strategy_generation_valid(self):
        assert _validate_strategy_generation({
            "candidates": [{
                "name": "test",
                "dsl": {
                    "entry": {"any": [{"op": "gt"}]},
                    "exit": {"any": [{"op": "lt"}]},
                },
            }]
        })

    def test_strategy_generation_invalid(self):
        assert not _validate_strategy_generation({"candidates": [{"name": "test", "dsl": {}}]})
        assert not _validate_strategy_generation({"candidates": [{"name": "test"}]})

    def test_validate_stage_output_dispatches(self):
        """validate_stage_output 应按 stage_id 分发到正确的 validator。"""
        good_event = {"events": [{"theme_code": "x", "event_type": "y"}]}
        assert validate_stage_output("event_recognition", good_event) is True
        assert validate_stage_output("event_recognition", {"events": []}) is False
        assert validate_stage_output("unknown_stage", {}) is True  # 未知 stage 默认通过


# ===========================================================================
# Test 3: 各阶段 fallback 函数
# ===========================================================================

class TestStageFallbacks:
    """测试每个阶段的 fallback 函数在无 LLM 环境下能正常产出。"""

    @pytest.fixture
    def db(self):
        return _MockDB()

    @pytest.mark.asyncio
    async def test_fallback_event_recognition(self, db):
        registry = get_stage_registry()
        fn = registry["event_recognition"].fallback_fn
        output = await fn(db, {"market_snapshot": {}, "theme_library": []}, MOCK_SNAPSHOT)
        assert "events" in output
        assert isinstance(output["events"], list)

    @pytest.mark.asyncio
    async def test_fallback_theme_propagation(self, db):
        registry = get_stage_registry()
        fn = registry["theme_propagation"].fallback_fn
        input_data = {
            "events": [
                {"event_id": "e1", "theme_code": "chip_domestic", "event_type": "sector_rotation"},
                {"event_id": "e2", "theme_code": "liquor_consumption", "event_type": "flow"},
            ]
        }
        output = await fn(db, input_data, {})
        assert "themes" in output
        themes = output["themes"]
        assert len(themes) == 2
        assert themes[0]["theme_code"] == "chip_domestic"
        assert themes[1]["theme_code"] == "liquor_consumption"
        # 每个 theme 应有传导链、方向、置信度
        for th in themes:
            assert "propagation_chain" in th
            assert "direction" in th
            assert "confidence" in th

    @pytest.mark.asyncio
    async def test_fallback_exposure_mapping(self, db):
        registry = get_stage_registry()
        fn = registry["exposure_mapping"].fallback_fn
        input_data = {
            "themes": [
                {"theme_code": "liquor_consumption", "theme_name": "消费龙头"},
            ]
        }
        output = await fn(db, input_data, {})
        assert "exposures" in output
        exposures = output["exposures"]
        # 白酒 alias 应匹配到 600519、000858
        assert len(exposures) >= 1
        symbols = exposures[0].get("target_symbols", [])
        assert "600519" in symbols or "000858" in symbols

    @pytest.mark.asyncio
    async def test_fallback_market_confirmation(self, db):
        registry = get_stage_registry()
        fn = registry["market_confirmation"].fallback_fn
        input_data = {
            "exposures": [
                {"theme_code": "liquor_consumption", "target_symbols": ["600519", "000858"]},
            ]
        }
        output = await fn(db, input_data, {})
        assert "confirmations" in output
        confs = output["confirmations"]
        assert len(confs) == 2
        for c in confs:
            assert "symbol" in c
            assert "confirmed" in c
            assert "signal_strength" in c

    @pytest.mark.asyncio
    async def test_fallback_market_confirmation_fetches_symbols_concurrently(self):
        registry = get_stage_registry()
        fn = registry["market_confirmation"].fallback_fn
        state = {"in_flight": 0, "max_in_flight": 0}

        async def _get_klines(_code: str, limit: int = 30):
            state["in_flight"] += 1
            state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
            await asyncio.sleep(0.01)
            state["in_flight"] -= 1
            return [
                {
                    "date": f"2026-01-{idx+1:02d}",
                    "open": 10.0 + idx * 0.1,
                    "close": 10.1 + idx * 0.1,
                    "high": 10.2 + idx * 0.1,
                    "low": 9.9 + idx * 0.1,
                    "volume": 100000 + idx * 1000,
                }
                for idx in range(limit)
            ]

        output = await fn(
            SimpleNamespace(get_klines=_get_klines),
            {
                "exposures": [
                    {
                        "theme_code": "chip_domestic",
                        "target_symbols": ["600519", "000858", "601318", "600036"],
                    }
                ]
            },
            MOCK_SNAPSHOT,
        )

        assert len(output["confirmations"]) == 4
        assert state["max_in_flight"] >= 2

    @pytest.mark.asyncio
    async def test_fallback_strategy_generation(self, db):
        registry = get_stage_registry()
        fn = registry["strategy_generation"].fallback_fn
        input_data = {
            "confirmations": [
                {"theme_code": "liquor_consumption", "symbol": "600519", "confirmed": True},
                {"theme_code": "liquor_consumption", "symbol": "000858", "confirmed": True},
            ]
        }
        output = await fn(db, input_data, {})
        assert "candidates" in output
        candidates = output["candidates"]
        assert len(candidates) >= 1
        for cand in candidates:
            assert "name" in cand
            assert "strategy_type" in cand
            assert "params" in cand
            assert "dsl" in cand
            dsl = cand["dsl"]
            assert "entry" in dsl
            assert "exit" in dsl
            assert "target_symbols" in cand

    @pytest.mark.asyncio
    async def test_fallback_strategy_generation_expands_growth_and_flow_families(self, db):
        result = await _fallback_strategy_generation(
            db,
            input_data={
                "confirmations": [
                    {"theme_code": "chip_domestic", "symbol": "002415", "confirmed": True},
                    {"theme_code": "chip_domestic", "symbol": "300750", "confirmed": True},
                ]
            },
            snapshot={
                **MOCK_SNAPSHOT,
                "fear_greed": {"score": 64, "label": "greed"},
                "north_fund": {"net_inflow": 180000000},
            },
        )

        strategy_types = {item["strategy_type"] for item in result["candidates"]}
        assert "volatility_breakout" in strategy_types
        assert "north_capital_track" in strategy_types

    @pytest.mark.asyncio
    async def test_fallback_strategy_generation_expands_defensive_and_repair_families(self, db):
        result = await _fallback_strategy_generation(
            db,
            input_data={
                "confirmations": [
                    {"theme_code": "high_dividend_banks", "symbol": "600036", "confirmed": True},
                    {"theme_code": "high_dividend_banks", "symbol": "000001", "confirmed": True},
                ]
            },
            snapshot={
                **MOCK_SNAPSHOT,
                "fear_greed": {"score": 36, "label": "fear"},
                "north_fund": {"net_inflow": 80000000},
            },
        )

        strategy_types = {item["strategy_type"] for item in result["candidates"]}
        assert "mean_reversion_short" in strategy_types
        assert "gap_fill" in strategy_types

    @pytest.mark.asyncio
    async def test_fallback_strategy_generation_expands_rotation_and_divergence_families(self, db):
        result = await _fallback_strategy_generation(
            db,
            input_data={
                "confirmations": [
                    {"theme_code": "infrastructure", "symbol": "600585", "confirmed": True},
                    {"theme_code": "infrastructure", "symbol": "601012", "confirmed": True},
                ]
            },
            snapshot={
                **MOCK_SNAPSHOT,
                "fear_greed": {"score": 40, "label": "fear"},
                "hot_sectors": [
                    {"group": "基建", "change_pct": 1.8},
                    {"group": "有色", "change_pct": 1.5},
                    {"group": "航运", "change_pct": 1.3},
                ],
            },
        )

        strategy_types = {item["strategy_type"] for item in result["candidates"]}
        assert "sector_rotation" in strategy_types
        assert "margin_divergence" in strategy_types

    @pytest.mark.asyncio
    async def test_fallback_strategy_generation_tightens_snapshot_family_breakout_task(self, db):
        result = await _fallback_strategy_generation(
            db,
            input_data={
                "confirmations": [
                    {"theme_code": "chip_domestic", "symbol": "002415", "confirmed": True},
                    {"theme_code": "chip_domestic", "symbol": "300750", "confirmed": True},
                ],
                "research_task": {
                    "task_source": "snapshot",
                    "opportunity_type": "candidate_family_activation",
                    "candidate_family": "momentum",
                    "validation_focus": "candidate_target_only",
                    "allowed_strategy_types": ["volatility_breakout", "ma_cross", "sector_rotation"],
                    "template_generation_profile": "conservative_breakout",
                },
            },
            snapshot={
                **MOCK_SNAPSHOT,
                "fear_greed": {"score": 64, "label": "greed"},
                "north_fund": {"net_inflow": 180000000},
            },
        )

        candidates = list(result["candidates"])
        assert len(candidates) == 1
        assert candidates[0]["strategy_type"] == "volatility_breakout"
        assert candidates[0]["research_task"]["template_generation_profile"] == "conservative_breakout"

    @pytest.mark.asyncio
    async def test_fallback_strategy_generation_tightens_snapshot_family_mean_reversion_task(self, db):
        result = await _fallback_strategy_generation(
            db,
            input_data={
                "confirmations": [
                    {"theme_code": "high_dividend_banks", "symbol": "600036", "confirmed": True},
                    {"theme_code": "high_dividend_banks", "symbol": "000001", "confirmed": True},
                ],
                "research_task": {
                    "task_source": "snapshot",
                    "opportunity_type": "candidate_factor_activation",
                    "candidate_family": "close_location",
                    "validation_focus": "candidate_target_only",
                    "allowed_strategy_types": ["rsi", "gap_fill", "ma_cross"],
                    "template_generation_profile": "conservative_mean_reversion",
                },
            },
            snapshot={
                **MOCK_SNAPSHOT,
                "fear_greed": {"score": 42, "label": "fear"},
            },
        )

        candidates = list(result["candidates"])
        assert len(candidates) == 1
        assert candidates[0]["strategy_type"] == "rsi"
        assert candidates[0]["research_task"]["candidate_family"] == "close_location"


# ===========================================================================
# Test 4: Pipeline 端到端全流程（纯 fallback 路径）
# ===========================================================================

class TestPipelineEndToEnd:
    """LLM 不可用时，Pipeline 纯走 fallback 仍然能跑通 5 个阶段。"""

    @pytest.fixture
    def db(self):
        return _MockDB()

    @pytest.fixture
    def pipeline(self):
        """LLM disabled 的 pipeline。"""
        mock_provider = MagicMock()
        mock_provider.is_enabled.return_value = False
        return MultiStageStrategyPipeline(provider=mock_provider)

    @pytest.mark.asyncio
    async def test_full_pipeline_fallback_produces_candidates(self, db, pipeline):
        result = await pipeline.run_pipeline(db=db, snapshot=MOCK_SNAPSHOT)

        assert type(result).__name__ == "PipelineResult"
        assert hasattr(result, "stages")
        assert hasattr(result, "candidates")
        assert result.error is None, f"Pipeline error: {result.error}"
        assert result.elapsed_sec > 0

        # 所有 5 个阶段应被执行
        assert len(result.stages) == 5
        for stage_id in STAGE_ORDER:
            assert stage_id in result.stages
            sr = result.stages[stage_id]
            assert sr.used_fallback is True, f"Stage {stage_id} should use fallback"
            assert sr.error is None, f"Stage {stage_id} error: {sr.error}"

        # 最终应有候选策略
        assert len(result.candidates) > 0
        for cand in result.candidates:
            assert "name" in cand
            assert "dsl" in cand

    @pytest.mark.asyncio
    async def test_pipeline_chain_data_passes_between_stages(self, db, pipeline):
        """验证每阶段的 output 确实传递给下一阶段。"""
        result = await pipeline.run_pipeline(db=db, snapshot=MOCK_SNAPSHOT)

        # Stage 1 应输出 events
        s1 = result.stages["event_recognition"]
        assert "events" in s1.output

        # Stage 2 应输出 themes
        s2 = result.stages["theme_propagation"]
        assert "themes" in s2.output

        # Stage 3 应输出 exposures
        s3 = result.stages["exposure_mapping"]
        assert "exposures" in s3.output

        # Stage 4 应输出 confirmations
        s4 = result.stages["market_confirmation"]
        assert "confirmations" in s4.output

        # Stage 5 应输出 candidates
        s5 = result.stages["strategy_generation"]
        assert "candidates" in s5.output

    @pytest.mark.asyncio
    async def test_exposure_mapping_fallback_bootstraps_from_snapshot_when_parallel_input_has_no_themes(self, db):
        result = await _fallback_exposure_mapping(
            db,
            input_data={},
            snapshot=MOCK_SNAPSHOT,
        )

        assert "exposures" in result
        assert len(result["exposures"]) > 0
        assert any(item.get("target_symbols") for item in result["exposures"])


# ===========================================================================
# Test 5: Provenance 追踪
# ===========================================================================

class TestProvenance:
    @pytest.fixture
    def db(self):
        return _MockDB()

    @pytest.fixture
    def pipeline(self):
        mock_provider = MagicMock()
        mock_provider.is_enabled.return_value = False
        return MultiStageStrategyPipeline(provider=mock_provider)

    @pytest.mark.asyncio
    async def test_provenance_structure(self, db, pipeline):
        result = await pipeline.run_pipeline(db=db, snapshot=MOCK_SNAPSHOT)
        prov = result.provenance

        assert "pipeline_elapsed_sec" in prov
        assert prov["pipeline_elapsed_sec"] > 0
        assert prov["stage_count"] == 5
        assert prov["candidate_count"] > 0
        assert prov["error"] is None

        stages_prov = prov["stages"]
        for stage_id in STAGE_ORDER:
            assert stage_id in stages_prov
            sp = stages_prov[stage_id]
            assert sp["used_fallback"] is True
            assert sp["elapsed_sec"] >= 0
            assert sp["error"] is None
            assert "llm_error" in sp
            assert "llm_error_type" in sp

    @pytest.mark.asyncio
    async def test_provenance_is_json_serializable(self, db, pipeline):
        result = await pipeline.run_pipeline(db=db, snapshot=MOCK_SNAPSHOT)
        serialized = json.dumps(result.provenance, ensure_ascii=False, default=str)
        assert len(serialized) > 10
        parsed = json.loads(serialized)
        assert parsed["stage_count"] == 5


# ===========================================================================
# Test 6: Pipeline candidates → StrategySpec 转换
# ===========================================================================

class TestCandidateToSpec:
    def test_pipeline_candidate_to_spec_success(self):
        from akshare_mcp.services.strategy_generators import LLMProxyStrategyGenerator

        candidate = {
            "name": "消费龙头_趋势跟踪",
            "strategy_type": "ma_cross",
            "target_symbols": ["600519", "000858"],
            "dsl": {
                "version": "1.0",
                "timeframe": "daily",
                "entry": {
                    "any": [{"op": "cross_above",
                             "left": {"indicator": "sma", "field": "close", "window": 5},
                             "right": {"indicator": "sma", "field": "close", "window": 20}}],
                },
                "exit": {
                    "any": [{"op": "cross_below",
                             "left": {"indicator": "sma", "field": "close", "window": 5},
                             "right": {"indicator": "sma", "field": "close", "window": 20}}],
                },
                "metadata": {"target_symbols": ["600519", "000858"]},
            },
            "tags": ["ai_staged", "ma_cross"],
        }

        spec = LLMProxyStrategyGenerator._pipeline_candidate_to_spec(
            candidate, provenance={"pipeline_elapsed_sec": 1.0, "stage_count": 5}
        )

        assert spec is not None
        assert spec.name == "消费龙头_趋势跟踪"
        assert "pipeline_staged" in spec.tags
        assert spec.metadata.get("generator_type") == "pipeline_staged"
        assert "600519" in spec.metadata.get("target_symbols", [])

    def test_pipeline_candidate_to_spec_keeps_template_params_for_native_family(self):
        from akshare_mcp.services.strategy_generators import LLMProxyStrategyGenerator

        candidate = {
            "name": "芯片半导体_波动突破",
            "strategy_type": "volatility_breakout",
            "target_symbols": ["002415", "300750"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["002415", "300750"]},
            "params": {"lookback": 20, "threshold": 0.025},
            "dsl": {
                "version": "1.0",
                "timeframe": "daily",
                "entry": {
                    "all": [
                        {"op": "gt", "left": {"indicator": "roc", "field": "close", "window": 20}, "right": {"value": 0.025}},
                        {"op": "gt", "left": {"indicator": "stddev", "field": "close", "window": 20}, "right": {"value": 0.018}},
                    ],
                },
                "exit": {
                    "any": [
                        {"op": "lt", "left": {"indicator": "roc", "field": "close", "window": 10}, "right": {"value": -0.015}},
                    ],
                },
                "metadata": {"target_symbols": ["002415", "300750"]},
            },
            "tags": ["ai_staged", "chip_domestic", "volatility_breakout"],
        }

        spec = LLMProxyStrategyGenerator._pipeline_candidate_to_spec(
            candidate, provenance={"pipeline_elapsed_sec": 0.8, "stage_count": 5}
        )

        assert spec is not None
        assert spec.strategy_type == "volatility_breakout"
        assert spec.params["lookback"] == 20
        assert spec.params["threshold"] == 0.025
        assert spec.metadata["stock_pool"]["symbols"] == ["002415", "300750"]

        submit_candidate = spec.to_candidate("strategy_factory:pipeline_staged", "exp_pipeline_1")
        assert submit_candidate["name"] == "芯片半导体_波动突破"
        assert submit_candidate["target_symbols"] == ["002415", "300750"]
        assert submit_candidate["params"]["target_symbols"] == ["002415", "300750"]
        assert submit_candidate["params"]["stock_pool"]["symbols"] == ["002415", "300750"]
        assert submit_candidate["pipeline_provenance"]["stage_count"] == 5

    def test_pipeline_candidate_to_spec_drops_snapshot_family_momentum(self):
        from akshare_mcp.services.strategy_generators import LLMProxyStrategyGenerator

        candidate = {
            "name": "snapshot_momentum_candidate",
            "strategy_type": "momentum",
            "target_symbols": ["002415", "300750"],
            "params": {"lookback": 12, "threshold": 0.018},
            "dsl": {
                "version": "1.0",
                "timeframe": "daily",
                "entry": {"any": [{"op": "gt", "left": {"indicator": "roc", "field": "close", "window": 12}, "right": {"value": 0.018}}]},
                "exit": {"any": [{"op": "lt", "left": {"indicator": "roc", "field": "close", "window": 8}, "right": {"value": -0.02}}]},
            },
            "research_task": {
                "task_source": "snapshot",
                "opportunity_type": "candidate_family_activation",
                "candidate_family": "momentum",
                "validation_focus": "candidate_target_only",
                "template_generation_profile": "conservative_breakout",
                "allowed_strategy_types": ["volatility_breakout", "ma_cross", "sector_rotation"],
            },
        }

        spec = LLMProxyStrategyGenerator._pipeline_candidate_to_spec(
            candidate, provenance={"pipeline_elapsed_sec": 0.6, "stage_count": 5}
        )

        assert spec is None

    def test_pipeline_candidate_to_spec_retunes_snapshot_family_ma_cross(self):
        from akshare_mcp.services.strategy_generators import LLMProxyStrategyGenerator

        candidate = {
            "name": "snapshot_ma_cross_candidate",
            "strategy_type": "ma_cross",
            "target_symbols": ["002415", "300750"],
            "params": {"short_period": 6, "long_period": 24},
            "stock_pool": {"selection_mode": "explicit", "symbols": ["002415", "300750"]},
            "dsl": {
                "version": "1.0",
                "timeframe": "daily",
                "entry": {
                    "any": [{
                        "op": "cross_above",
                        "left": {"indicator": "sma", "field": "close", "window": 6},
                        "right": {"indicator": "sma", "field": "close", "window": 24},
                    }],
                },
                "exit": {
                    "any": [{
                        "op": "cross_below",
                        "left": {"indicator": "sma", "field": "close", "window": 6},
                        "right": {"indicator": "sma", "field": "close", "window": 24},
                    }],
                },
            },
            "research_task": {
                "task_source": "snapshot",
                "opportunity_type": "candidate_factor_activation",
                "candidate_family": "ma_cross",
                "validation_focus": "candidate_target_only",
                "template_generation_profile": "conservative_breakout",
                "allowed_strategy_types": ["volatility_breakout", "ma_cross", "sector_rotation"],
            },
        }

        spec = LLMProxyStrategyGenerator._pipeline_candidate_to_spec(
            candidate, provenance={"pipeline_elapsed_sec": 0.6, "stage_count": 5}
        )

        assert spec is not None
        assert spec.strategy_type == "ma_cross"
        assert spec.params["short_period"] >= 12
        assert spec.params["long_period"] >= 48
        assert "snapshot_family_conservative" in spec.tags

    def test_pipeline_candidate_to_spec_none_for_bad_input(self):
        from akshare_mcp.services.strategy_generators import LLMProxyStrategyGenerator

        assert LLMProxyStrategyGenerator._pipeline_candidate_to_spec(None, {}) is None
        assert LLMProxyStrategyGenerator._pipeline_candidate_to_spec({}, {}) is None  # empty dict lacks required fields


# ===========================================================================
# Test 7: PIPELINE_MODE 路由
# ===========================================================================

class TestPipelineModeRouting:
    @pytest.fixture
    def db(self):
        return _MockDB()

    @pytest.mark.asyncio
    async def test_staged_mode_calls_pipeline(self, db):
        """PIPELINE_MODE=staged 应该走 pipeline 路径。"""
        from akshare_mcp.services.strategy_generators import LLMProxyStrategyGenerator

        gen = LLMProxyStrategyGenerator()

        mock_pipeline_result = PipelineResult(
            candidates=[{
                "name": "test_pipeline_strategy",
                "strategy_type": "ma_cross",
                "target_symbols": ["600519"],
                "dsl": {
                    "version": "1.0",
                    "timeframe": "daily",
                    "entry": {"any": [{"op": "cross_above",
                                       "left": {"indicator": "sma", "field": "close", "window": 5},
                                       "right": {"indicator": "sma", "field": "close", "window": 20}}]},
                    "exit": {"any": [{"op": "cross_below",
                                      "left": {"indicator": "sma", "field": "close", "window": 5},
                                      "right": {"indicator": "sma", "field": "close", "window": 20}}]},
                    "metadata": {"target_symbols": ["600519"]},
                },
                "tags": ["ai_staged"],
            }],
            elapsed_sec=0.5,
        )
        mock_pipeline_result.stages = {sid: StageResult(stage_id=sid, output={}) for sid in STAGE_ORDER}

        with patch("akshare_mcp.services.strategy_generators.PIPELINE_MODE", "staged"), \
             patch("akshare_mcp.services.strategy_generators.get_strategy_pipeline") as mock_get_pipe:
            mock_pipe = AsyncMock()
            mock_pipe.run_pipeline.return_value = mock_pipeline_result
            mock_get_pipe.return_value = mock_pipe

            # provider 需要 is_enabled() == True 才会走 staged 路径
            gen.external_provider = MagicMock()
            gen.external_provider.is_enabled.return_value = True

            specs = await gen.generate(db, limit=3, snapshot=MOCK_SNAPSHOT)

            mock_pipe.run_pipeline.assert_awaited_once()
            assert len(specs) >= 1
            assert specs[0].metadata.get("generator_type") == "pipeline_staged"

    @pytest.mark.asyncio
    async def test_staged_mode_preserves_llm_error_when_fallback_succeeds(self, db):
        """staged pipeline fallback 成功时，仍应保留原始 LLM 错误。"""
        from akshare_mcp.services.strategy_generators import LLMProxyStrategyGenerator

        gen = LLMProxyStrategyGenerator()

        mock_pipeline_result = PipelineResult(
            candidates=[{
                "name": "test_pipeline_strategy",
                "strategy_type": "ma_cross",
                "target_symbols": ["600519"],
                "dsl": {
                    "version": "1.0",
                    "timeframe": "daily",
                    "entry": {"any": [{"op": "cross_above",
                                       "left": {"indicator": "sma", "field": "close", "window": 5},
                                       "right": {"indicator": "sma", "field": "close", "window": 20}}]},
                    "exit": {"any": [{"op": "cross_below",
                                      "left": {"indicator": "sma", "field": "close", "window": 5},
                                      "right": {"indicator": "sma", "field": "close", "window": 20}}]},
                    "metadata": {"target_symbols": ["600519"]},
                },
                "tags": ["ai_staged"],
            }],
            elapsed_sec=0.5,
        )
        mock_pipeline_result.stages = {
            "event_recognition": StageResult(
                stage_id="event_recognition",
                output={"events": [{"theme_code": "chip_domestic", "event_type": "policy"}]},
                used_fallback=True,
                llm_attempted=True,
                prompt_chars=120,
                elapsed_sec=8.2,
                llm_error="call_stage(event_recognition) failed after 1 attempts: ReadTimeout",
                llm_error_type="ReadTimeout",
                llm_error_metrics={"last_error_type": "ReadTimeout"},
            ),
        }

        with patch("akshare_mcp.services.strategy_generators.PIPELINE_MODE", "staged"), \
             patch("akshare_mcp.services.strategy_generators.get_strategy_pipeline") as mock_get_pipe:
            mock_pipe = AsyncMock()
            mock_pipe.run_pipeline.return_value = mock_pipeline_result
            mock_get_pipe.return_value = mock_pipe

            gen.external_provider = MagicMock()
            gen.external_provider.is_enabled.return_value = True
            gen.external_provider.config = MagicMock(provider="openai_compatible", model="test-model")

            specs = await gen.generate(db, limit=1, snapshot=MOCK_SNAPSHOT)
            report = gen.get_last_report()

            assert len(specs) == 1
            assert report["external_provider"]["status"] == "fallback_only"
            assert report["external_provider"]["last_error_type"] == "ReadTimeout"
            assert "ReadTimeout" in report["external_provider"]["last_error"]
            assert report["external_provider"]["requests"][0]["error_type"] == "ReadTimeout"
            assert "ReadTimeout" in report["pipeline_provenance"]["stages"]["event_recognition"]["llm_error"]

    @pytest.mark.asyncio
    async def test_monolithic_mode_skips_pipeline(self, db):
        """PIPELINE_MODE=monolithic 不应走 pipeline 路径。"""
        from akshare_mcp.services.strategy_generators import LLMProxyStrategyGenerator

        gen = LLMProxyStrategyGenerator()

        with patch("akshare_mcp.services.strategy_generators.PIPELINE_MODE", "monolithic"), \
             patch("akshare_mcp.services.strategy_generators.get_strategy_pipeline") as mock_get_pipe:
            mock_pipe = AsyncMock()
            mock_get_pipe.return_value = mock_pipe

            gen.external_provider = MagicMock()
            gen.external_provider.is_enabled.return_value = True
            gen.external_provider.config = MagicMock(strict=False)
            gen.external_provider.generate_candidates = AsyncMock(return_value={
                "candidates": [], "analysis": {}, "request_metrics": {},
            })

            # 需要 frame 才能走到 monolithic provider 调用
            with patch.object(gen, "_build_market_frame", new_callable=AsyncMock, return_value=None):
                specs = await gen.generate(db, limit=1, snapshot=MOCK_SNAPSHOT)

            # pipeline 不应被调用
            mock_pipe.run_pipeline.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pipeline_timeout_skips_monolithic_external_provider(self, db):
        """staged pipeline 超时后，本轮不应继续触发 monolithic 外部 LLM。"""
        from akshare_mcp.services.strategy_generators import LLMProxyStrategyGenerator

        gen = LLMProxyStrategyGenerator()

        async def _slow_pipeline(*args, **kwargs):
            await asyncio.sleep(0.05)
            return PipelineResult(candidates=[], elapsed_sec=0.05)

        with patch("akshare_mcp.services.strategy_generators.PIPELINE_MODE", "staged"), \
             patch("akshare_mcp.services.strategy_generators.get_strategy_pipeline") as mock_get_pipe, \
             patch.object(LLMProxyStrategyGenerator, "_pipeline_run_timeout_sec", return_value=0.01):
            mock_pipe = AsyncMock()
            mock_pipe.run_pipeline.side_effect = _slow_pipeline
            mock_get_pipe.return_value = mock_pipe

            gen.external_provider = MagicMock()
            gen.external_provider.is_enabled.return_value = True
            gen.external_provider.config = MagicMock(strict=False, provider="openai_compatible", model="test-model")
            gen.external_provider.generate_candidates = AsyncMock(return_value={"candidates": [], "analysis": {}, "request_metrics": {}})

            with patch.object(gen, "_build_market_frame", new_callable=AsyncMock, return_value=None):
                specs = await gen.generate(db, limit=1, snapshot=MOCK_SNAPSHOT)

            assert len(specs) >= 1
            gen.external_provider.generate_candidates.assert_not_awaited()
            report = gen.get_last_report()
            assert report["external_provider"]["status"] == "skipped_after_pipeline_timeout"
            assert report["pipeline_staged_fallback_reason"] == "pipeline_timeout"

    def test_pipeline_run_timeout_defaults_to_stage_budget(self):
        """未显式配置总预算时，应按 stage timeout 汇总并附加缓冲。"""
        from akshare_mcp.services.strategy_generators import LLMProxyStrategyGenerator

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STRATEGY_LLM_PIPELINE_RUN_TIMEOUT_SEC", None)
            with patch("akshare_mcp.services.strategy_generators._sf", return_value={
                "PIPELINE_STAGE_TIMEOUT_SEC": 10.0,
                "PIPELINE_STAGE_TIMEOUTS": {
                    "event_recognition": 8.0,
                    "theme_propagation": 10.0,
                    "exposure_mapping": 10.0,
                    "market_confirmation": 10.0,
                    "strategy_generation": 12.0,
                },
            }):
                assert LLMProxyStrategyGenerator._pipeline_run_timeout_sec() == pytest.approx(60.0)

    def test_pipeline_run_timeout_prefers_explicit_env(self, monkeypatch):
        from akshare_mcp.services.strategy_generators import LLMProxyStrategyGenerator

        monkeypatch.setenv("STRATEGY_LLM_PIPELINE_RUN_TIMEOUT_SEC", "33")
        assert LLMProxyStrategyGenerator._pipeline_run_timeout_sec() == pytest.approx(33.0)

    def test_pipeline_run_timeout_scales_with_large_stage_budget(self):
        from akshare_mcp.services.strategy_generators import LLMProxyStrategyGenerator

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STRATEGY_LLM_PIPELINE_RUN_TIMEOUT_SEC", None)
            with patch("akshare_mcp.services.strategy_generators._sf", return_value={
                "PIPELINE_STAGE_TIMEOUT_SEC": 60.0,
                "PIPELINE_STAGE_TIMEOUTS": {
                    "event_recognition": 60.0,
                    "theme_propagation": 60.0,
                    "exposure_mapping": 60.0,
                    "market_confirmation": 60.0,
                    "strategy_generation": 60.0,
                },
            }):
                assert LLMProxyStrategyGenerator._pipeline_run_timeout_sec() == pytest.approx(360.0)


# ===========================================================================
# Test 8: 单阶段 LLM 调用路径（mock LLM 返回）
# ===========================================================================

class TestSingleStageLLMPath:
    @pytest.fixture
    def db(self):
        return _MockDB()

    @pytest.mark.asyncio
    async def test_stage_uses_llm_when_available(self, db):
        """当 LLM 可用且返回合法输出时，不走 fallback。"""
        mock_provider = MagicMock()
        mock_provider.is_enabled.return_value = True

        llm_output = {
            "events": [{"event_id": "llm_1", "theme_code": "chip_domestic", "event_type": "policy"}]
        }
        mock_provider.call_stage = AsyncMock(return_value=llm_output)

        pipeline = MultiStageStrategyPipeline(provider=mock_provider)
        stage_result = await pipeline.run_stage(
            db=db,
            stage_id="event_recognition",
            input_data={"market_snapshot": {}, "theme_library": []},
        )

        assert stage_result.used_fallback is False
        assert stage_result.output == llm_output
        assert stage_result.error is None
        mock_provider.call_stage.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stage_falls_back_on_invalid_llm_output(self, db):
        """LLM 返回不合法输出时，自动 fallback 到本地规则。"""
        mock_provider = MagicMock()
        mock_provider.is_enabled.return_value = True
        mock_provider.call_stage = AsyncMock(return_value={"events": []})  # invalid: empty list

        pipeline = MultiStageStrategyPipeline(provider=mock_provider)
        stage_result = await pipeline.run_stage(
            db=db,
            stage_id="event_recognition",
            input_data={"market_snapshot": {}, "theme_library": []},
            snapshot=MOCK_SNAPSHOT,
        )

        assert stage_result.used_fallback is True
        mock_provider.call_stage.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stage_falls_back_on_llm_exception(self, db):
        """LLM 调用抛异常时，自动 fallback。"""
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMRequestError

        mock_provider = MagicMock()
        mock_provider.is_enabled.return_value = True
        mock_provider.call_stage = AsyncMock(
            side_effect=StrategyLLMRequestError(
                "timeout",
                metrics={"last_error_type": "ReadTimeout", "elapsed_seconds": 8.0},
            )
        )

        pipeline = MultiStageStrategyPipeline(provider=mock_provider)
        stage_result = await pipeline.run_stage(
            db=db,
            stage_id="event_recognition",
            input_data={"market_snapshot": {}, "theme_library": []},
            snapshot=MOCK_SNAPSHOT,
        )

        assert stage_result.used_fallback is True
        assert stage_result.llm_error == "timeout"
        assert stage_result.llm_error_type == "ReadTimeout"
        assert stage_result.prompt_chars > 0
        assert stage_result.llm_error_metrics["elapsed_seconds"] == 8.0

    @pytest.mark.asyncio
    async def test_stage_skips_external_llm_during_recent_timeout_cooldown(self, db):
        """最近超时处于冷却窗口时，应直接 fallback 而不是再次发起外部请求。"""
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMProvider

        provider = StrategyLLMProvider(
            StrategyLLMConfig(
                enabled=True,
                base_url="https://example.com/v1",
                api_key="test-key",
                model="test-model",
            )
        )
        provider._recent_timeout_streak = 1
        provider._recent_timeout_cooldown_until = time.monotonic() + 60.0
        provider._client.post = AsyncMock(side_effect=AssertionError("external request should be skipped during cooldown"))

        pipeline = MultiStageStrategyPipeline(provider=provider)
        stage_result = await pipeline.run_stage(
            db=db,
            stage_id="event_recognition",
            input_data={"market_snapshot": {}, "theme_library": []},
            snapshot=MOCK_SNAPSHOT,
        )

        assert stage_result.used_fallback is True
        assert stage_result.llm_error_type == "RecentTimeoutCooldown"
        assert stage_result.llm_error_metrics["status"] == "cooldown_skip"
        provider._client.post.assert_not_awaited()
        await provider.close()

    @pytest.mark.asyncio
    async def test_stage_skips_external_llm_during_recent_overload_cooldown(self, db):
        """最近过载处于冷却窗口时，应直接 fallback 并避免继续轰炸外部 LLM。"""
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMProvider

        provider = StrategyLLMProvider(
            StrategyLLMConfig(
                enabled=True,
                base_url="https://example.com/v1",
                api_key="test-key",
                model="test-model",
            )
        )
        provider._recent_overload_streak = 1
        provider._recent_overload_cooldown_until = time.monotonic() + 60.0
        provider._client.post = AsyncMock(side_effect=AssertionError("external request should be skipped during overload cooldown"))

        pipeline = MultiStageStrategyPipeline(provider=provider)
        stage_result = await pipeline.run_stage(
            db=db,
            stage_id="event_recognition",
            input_data={"market_snapshot": {}, "theme_library": []},
            snapshot=MOCK_SNAPSHOT,
        )

        assert stage_result.used_fallback is True
        assert stage_result.llm_error_type == "RecentOverloadCooldown"
        assert stage_result.llm_error_metrics["status"] == "cooldown_skip"
        assert stage_result.llm_error_metrics["cooldown_reason"] == "recent_overload"
        provider._client.post.assert_not_awaited()
        await provider.close()

def test_strategy_llm_prompt_disallows_market_fallback_for_strict_event_targets():
    from akshare_mcp.services.strategy_llm_provider import StrategyLLMProvider

    provider = StrategyLLMProvider.__new__(StrategyLLMProvider)

    system_prompt, user_prompt = provider._build_prompt(
        snapshot={"date": "2026-04-03"},
        market_summary={"market_regime": {"risk_on": 0.6}},
        research_context={"candidate_universe_symbols": ["600519", "000858"]},
        parent_strategies=[],
        history_summary=[],
        limit=1,
        research_task={
            "task_source": "event_driven",
            "event_id": "evt_1",
            "theme_code": "baijiu",
            "target_symbols": ["600519"],
            "same_theme_symbols": ["000858"],
        },
    )

    payload = json.loads(user_prompt)

    assert "不允许退回 candidate_universe" in system_prompt
    assert "same_theme_symbols" in system_prompt
    assert payload["output_contract"]["target_symbol_rule"] == "strict_intersection_with_research_task"


def test_strategy_llm_prompt_tightens_snapshot_target_pool_contract():
    from akshare_mcp.services.strategy_llm_provider import StrategyLLMProvider

    provider = StrategyLLMProvider.__new__(StrategyLLMProvider)

    system_prompt, user_prompt = provider._build_prompt(
        snapshot={"date": "2026-04-03"},
        market_summary={"market_regime": {"risk_on": 0.6}},
        research_context={"candidate_universe_symbols": ["603855", "603279", "002833", "601766"]},
        parent_strategies=[],
        history_summary=[],
        limit=2,
        research_task={
            "task_source": "snapshot",
            "task_id": "task_pipeline_rsi_prompt",
            "allowed_strategy_types": ["rsi"],
            "target_symbols": ["603855", "603279", "002833", "601766", "600528", "600582", "600894", "920599"],
        },
    )

    payload = json.loads(user_prompt)
    contract = payload["output_contract"]["target_alignment_contract"]

    assert "不得扩展到 candidate_universe 或全市场" in system_prompt
    assert contract["min_target_overlap_count"] == 4
    assert contract["max_target_symbols"] == 4
    assert contract["disallow_market_fallback"] is True


def test_strategy_llm_normalize_rejects_low_alignment_snapshot_candidate():
    from akshare_mcp.services.strategy_llm_provider import StrategyLLMProvider

    provider = StrategyLLMProvider.__new__(StrategyLLMProvider)

    normalized = provider._normalize_candidate_payload(
        {
            "name": "fragile_rsi_snapshot",
            "strategy_type": "rsi",
            "generator_type": "pipeline_staged",
            "tags": ["pipeline_staged", "generator_pipeline_staged"],
            "target_symbols": ["603855", "603279", "002833"],
            "dsl": {
                "version": "1.0",
                "timeframe": "daily",
                "entry": {
                    "any": [{
                        "op": "lt",
                        "left": {"indicator": "rsi", "field": "close", "window": 14},
                        "right": {"value": 30},
                    }],
                },
                "exit": {
                    "any": [{
                        "op": "gt",
                        "left": {"indicator": "rsi", "field": "close", "window": 14},
                        "right": {"value": 60},
                    }],
                },
                "metadata": {},
            },
        },
        research_task={
            "task_source": "snapshot",
            "allowed_strategy_types": ["rsi"],
            "target_symbols": ["603855", "603279", "002833", "601766", "600528", "600582", "600894", "920599"],
        },
    )

    assert normalized is None


# ===========================================================================
# Test 9: Pipeline 初始输入构建
# ===========================================================================

class TestBuildInitialInput:
    def test_builds_market_snapshot(self):
        pipeline = MultiStageStrategyPipeline.__new__(MultiStageStrategyPipeline)
        initial = pipeline._build_initial_input(MOCK_SNAPSHOT)

        ms = initial["market_snapshot"]
        assert ms["fear_greed"]["score"] == 55
        assert ms["date"] == "2026-03-10"
        assert len(ms["sectors"]) == 3
        assert ms["north_fund"]["net_inflow"] == 50000000

    def test_includes_theme_directory(self):
        pipeline = MultiStageStrategyPipeline.__new__(MultiStageStrategyPipeline)
        initial = pipeline._build_initial_input({})

        assert "theme_library" in initial

    def test_build_initial_input_adds_theme_hints(self):
        pipeline = MultiStageStrategyPipeline.__new__(MultiStageStrategyPipeline)
        initial = pipeline._build_initial_input(MOCK_SNAPSHOT)

        assert initial["theme_library"][0]["aliases"]
        matched = list(initial.get("matched_theme_candidates") or [])
        matched_codes = {item["theme_code"] for item in matched}
        assert "chip_domestic" in matched_codes
        assert "liquor_consumption" in matched_codes
        hints = dict(initial.get("event_detection_hints") or {})
        assert "hot_sector_names" in hints
        assert "半导体" in list(hints.get("hot_sector_names") or [])

    def test_prepare_event_recognition_input_prioritizes_hints(self):
        pipeline = MultiStageStrategyPipeline.__new__(MultiStageStrategyPipeline)
        initial = pipeline._build_initial_input(MOCK_SNAPSHOT)

        prepared = pipeline._prepare_stage_input("event_recognition", initial)

        assert "matched_theme_candidates" in prepared
        assert len(prepared["matched_theme_candidates"]) <= 6
        assert len(prepared["theme_library"]) <= 12
        assert prepared["theme_library"][0]["theme_code"] in {
            item["theme_code"] for item in prepared["matched_theme_candidates"]
        }
        assert len(initial["theme_library"]) == 20
        for entry in initial["theme_library"]:
            assert "theme_code" in entry
            assert "name" in entry

    def test_includes_research_task(self):
        pipeline = MultiStageStrategyPipeline.__new__(MultiStageStrategyPipeline)
        task = {"task_key": "abc", "theme_code": "chip_domestic", "direction": "bullish"}
        initial = pipeline._build_initial_input({}, research_task=task)

        assert "research_task" in initial
        assert initial["research_task"]["task_key"] == "abc"
        assert initial["research_task"]["theme_code"] == "chip_domestic"

    def test_includes_extended_snapshot_research_task_context(self):
        pipeline = MultiStageStrategyPipeline.__new__(MultiStageStrategyPipeline)
        task = {
            "task_key": "snapshot_family_1",
            "task_source": "snapshot",
            "opportunity_type": "candidate_family_activation",
            "candidate_family": "close_location",
            "factor_name": "close_location",
            "candidate_name": "close_location_watch",
            "preference_reason": "governed_family:close_location",
            "rationale": "围绕 close_location target pool 收紧生成。",
            "expected_regime": ["trend"],
            "validation_score": 79.0,
            "template_generation_profile": "conservative_mean_reversion",
            "allowed_strategy_types": ["rsi", "gap_fill", "ma_cross"],
        }
        initial = pipeline._build_initial_input({}, research_task=task)
        prepared = pipeline._prepare_stage_input("strategy_generation", initial)

        assert initial["research_task"]["candidate_family"] == "close_location"
        assert initial["research_task"]["template_generation_profile"] == "conservative_mean_reversion"
        assert prepared["research_task"]["allowed_strategy_types"] == ["rsi", "gap_fill", "ma_cross"]
        assert prepared["research_task"]["candidate_name"] == "close_location_watch"


# ===========================================================================
# Test 10: Constants 配置一致性
# ===========================================================================

class TestConstants:
    def test_pipeline_mode_default(self):
        # 可能被环境变量覆盖，但应该是合法值
        assert PIPELINE_MODE in ("staged", "monolithic")

    def test_timeout_is_reasonable(self):
        assert 1.0 <= PIPELINE_STAGE_TIMEOUT_SEC <= 60.0

    def test_max_tokens_all_stages(self):
        for stage_id in STAGE_ORDER:
            assert stage_id in PIPELINE_STAGE_MAX_TOKENS
            assert 100 <= PIPELINE_STAGE_MAX_TOKENS[stage_id] <= 2000

    def test_temperature_all_stages(self):
        for stage_id in STAGE_ORDER:
            assert stage_id in PIPELINE_STAGE_TEMPERATURE
            assert 0.0 <= PIPELINE_STAGE_TEMPERATURE[stage_id] <= 1.0
