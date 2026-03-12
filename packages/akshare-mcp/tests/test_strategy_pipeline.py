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
import time
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from akshare_mcp.services.strategy_stages import (
    EXTENDED_THEME_LIBRARY,
    STAGE_ORDER,
    StageDefinition,
    StageResult,
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
            assert "dsl" in cand
            dsl = cand["dsl"]
            assert "entry" in dsl
            assert "exit" in dsl
            assert "target_symbols" in cand


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

        assert isinstance(result, PipelineResult)
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
        mock_provider.call_stage = AsyncMock(side_effect=StrategyLLMRequestError("timeout"))

        pipeline = MultiStageStrategyPipeline(provider=mock_provider)
        stage_result = await pipeline.run_stage(
            db=db,
            stage_id="event_recognition",
            input_data={"market_snapshot": {}, "theme_library": []},
            snapshot=MOCK_SNAPSHOT,
        )

        assert stage_result.used_fallback is True


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
