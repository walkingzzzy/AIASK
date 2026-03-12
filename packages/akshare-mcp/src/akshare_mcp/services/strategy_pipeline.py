"""多阶段 AI 策略生成 — Pipeline 编排器。

``MultiStageStrategyPipeline`` 按顺序执行 5 个 Stage：
  event_recognition → theme_propagation → exposure_mapping
  → market_confirmation → strategy_generation

每阶段:
1. 尝试通过 ``StrategyLLMProvider.call_stage()`` 调用外部 LLM
2. 如果 LLM 失败或输出不合法，自动 fallback 到本地规则引擎
3. 验证输出 → 作为下一阶段的输入
4. 记录完整 provenance（prompt / response / 耗时 / 是否 fallback）
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .strategy_stages import (
    EXTENDED_THEME_LIBRARY,
    STAGE_ORDER,
    StageDefinition,
    StageResult,
    get_stage_registry,
    validate_stage_output,
)
from .strategy_llm_provider import (
    StrategyLLMProvider,
    StrategyLLMRequestError,
    get_strategy_llm_provider,
)
from .strategy_factory.constants import PIPELINE_STAGE_TIMEOUT_SEC, PIPELINE_STAGE_TIMEOUTS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------


@dataclass
class PipelineResult:
    """完整 pipeline 执行结果。"""

    stages: dict[str, StageResult] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    elapsed_sec: float = 0.0
    error: Optional[str] = None

    @property
    def provenance(self) -> dict[str, Any]:
        """返回可序列化的 provenance 摘要。"""
        return {
            "pipeline_elapsed_sec": round(self.elapsed_sec, 4),
            "stage_count": len(self.stages),
            "candidate_count": len(self.candidates),
            "error": self.error,
            "stages": {
                sid: {
                    "used_fallback": sr.used_fallback,
                    "elapsed_sec": round(sr.elapsed_sec, 4),
                    "prompt_chars": sr.prompt_chars,
                    "response_chars": sr.response_chars,
                    "error": sr.error,
                }
                for sid, sr in self.stages.items()
            },
        }


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------


class MultiStageStrategyPipeline:
    """链式执行 5 个 Stage 的编排器。"""

    def __init__(self, provider: Optional[StrategyLLMProvider] = None):
        self.provider = provider or get_strategy_llm_provider()
        self.registry = get_stage_registry()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_pipeline(
        self,
        db: Any,
        snapshot: Optional[dict[str, Any]] = None,
        research_task: Optional[dict[str, Any]] = None,
    ) -> PipelineResult:
        """完整 5 阶段编排。"""
        snapshot = snapshot or {}
        pipeline_started = time.perf_counter()
        result = PipelineResult()

        # 构建 Stage 1 的初始输入
        stage_input = self._build_initial_input(snapshot, research_task)

        # 跟踪 LLM 失败状态：超时或连续验证失败后，后续阶段直接走 fallback
        skip_llm = False
        consecutive_llm_failures = 0

        for stage_id in STAGE_ORDER:
            stage_def = self.registry.get(stage_id)
            if stage_def is None:
                logger.error("Pipeline stage %s not found in registry", stage_id)
                continue

            stage_result = await self.run_stage(
                db=db,
                stage_id=stage_id,
                input_data=stage_input,
                snapshot=snapshot,
                stage_def=stage_def,
                skip_llm=skip_llm,
            )
            result.stages[stage_id] = stage_result

            if not skip_llm:
                if stage_result.used_fallback:
                    consecutive_llm_failures += 1
                    # 超时检测：耗时接近超时阈值 → 立即跳过
                    _stage_limit = PIPELINE_STAGE_TIMEOUTS.get(stage_id, PIPELINE_STAGE_TIMEOUT_SEC)
                    if stage_result.elapsed_sec >= _stage_limit * 0.8:
                        logger.info(
                            "Stage %s took %.1fs (LLM timeout), skipping LLM for remaining stages",
                            stage_id, stage_result.elapsed_sec,
                        )
                        skip_llm = True
                    # 连续失败检测：连续 2 次 LLM 输出无效 → 跳过
                    elif consecutive_llm_failures >= 2:
                        logger.info(
                            "LLM failed %d consecutive stages, skipping LLM for remaining stages",
                            consecutive_llm_failures,
                        )
                        skip_llm = True
                else:
                    consecutive_llm_failures = 0  # LLM 成功则重置计数

            if stage_result.error and not stage_result.output:
                # 严重失败 — 中断 pipeline
                result.error = f"stage {stage_id} failed: {stage_result.error}"
                break

            # 链式传递: 当前 output 合并到下一阶段的 input
            stage_input = {**stage_input, **stage_result.output}

        # 从最终 stage_input 中提取 candidates
        result.candidates = list(stage_input.get("candidates") or [])
        result.elapsed_sec = time.perf_counter() - pipeline_started
        return result

    async def run_stage(
        self,
        db: Any,
        stage_id: str,
        input_data: dict[str, Any],
        snapshot: Optional[dict[str, Any]] = None,
        stage_def: Optional[StageDefinition] = None,
        skip_llm: bool = False,
    ) -> StageResult:
        """执行单个 Stage（支持外部按需调用）。"""
        snapshot = snapshot or {}
        if stage_def is None:
            stage_def = self.registry.get(stage_id)
        if stage_def is None:
            return StageResult(
                stage_id=stage_id,
                output={},
                error=f"stage {stage_id} not registered",
            )

        started = time.perf_counter()

        # 1) 尝试 LLM 调用（跳过条件：skip_llm 标记或 provider 不可用）
        if not skip_llm and self.provider.is_enabled():
            try:
                output = await self._call_llm_stage(stage_def, input_data)
                if validate_stage_output(stage_id, output):
                    elapsed = time.perf_counter() - started
                    return StageResult(
                        stage_id=stage_id,
                        output=output,
                        used_fallback=False,
                        prompt_chars=len(stage_def.system_prompt) + len(json.dumps(input_data, ensure_ascii=False, default=str)),
                        response_chars=len(json.dumps(output, ensure_ascii=False, default=str)),
                        elapsed_sec=elapsed,
                    )
                else:
                    logger.warning(
                        "Stage %s LLM output failed validation, falling back. "
                        "Output keys: %s, sample: %.200s",
                        stage_id,
                        list(output.keys()),
                        json.dumps(output, ensure_ascii=False, default=str)[:200],
                    )
            except (StrategyLLMRequestError, Exception) as exc:
                logger.warning("Stage %s LLM call failed: %s, falling back", stage_id, exc)
        elif skip_llm:
            logger.info("Stage %s skipping LLM (prior stage timed out)", stage_id)

        # 2) Fallback 到本地规则引擎
        return await self._call_fallback_stage(stage_def, db, input_data, snapshot, started)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call_llm_stage(
        self,
        stage_def: StageDefinition,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """调用 LLM provider 执行单阶段。"""
        stage_timeout = PIPELINE_STAGE_TIMEOUTS.get(stage_def.stage_id, PIPELINE_STAGE_TIMEOUT_SEC)
        return await self.provider.call_stage(
            stage_id=stage_def.stage_id,
            input_data=input_data,
            system_prompt=stage_def.system_prompt,
            max_tokens=stage_def.max_tokens,
            temperature=stage_def.temperature,
            timeout_sec=stage_timeout,
        )

    async def _call_fallback_stage(
        self,
        stage_def: StageDefinition,
        db: Any,
        input_data: dict[str, Any],
        snapshot: dict[str, Any],
        started: float,
    ) -> StageResult:
        """执行 fallback 函数。"""
        if stage_def.fallback_fn is None:
            return StageResult(
                stage_id=stage_def.stage_id,
                output={},
                used_fallback=True,
                elapsed_sec=time.perf_counter() - started,
                error=f"no fallback for stage {stage_def.stage_id}",
            )
        try:
            output = await stage_def.fallback_fn(db, input_data, snapshot)
            elapsed = time.perf_counter() - started
            valid = validate_stage_output(stage_def.stage_id, output)
            return StageResult(
                stage_id=stage_def.stage_id,
                output=output if valid else {},
                used_fallback=True,
                elapsed_sec=elapsed,
                error=None if valid else f"fallback output failed validation for {stage_def.stage_id}",
            )
        except Exception as exc:
            logger.error("Stage %s fallback failed: %s", stage_def.stage_id, exc)
            return StageResult(
                stage_id=stage_def.stage_id,
                output={},
                used_fallback=True,
                elapsed_sec=time.perf_counter() - started,
                error=f"fallback failed: {exc}",
            )

    @staticmethod
    def _build_initial_input(
        snapshot: dict[str, Any],
        research_task: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """构建 Stage 1 (event_recognition) 的输入。"""
        # 市场快照摘要
        market_snapshot: dict[str, Any] = {}
        for key in ("fear_greed", "date", "sentiment"):
            if key in snapshot:
                market_snapshot[key] = snapshot[key]

        # 板块涨跌
        sector_data = snapshot.get("hot_sectors") or snapshot.get("sectors") or []
        if isinstance(sector_data, list):
            market_snapshot["sectors"] = sector_data[:20]

        # 北向资金
        north_fund = snapshot.get("north_fund") or snapshot.get("capital_flow") or {}
        if north_fund:
            market_snapshot["north_fund"] = north_fund

        # 龙虎榜摘要
        dragon_tiger = snapshot.get("dragon_tiger") or []
        if isinstance(dragon_tiger, list):
            market_snapshot["dragon_tiger_summary"] = dragon_tiger[:10]

        # 主题库目录（仅 code + name，节省 token）
        theme_directory = [
            {"theme_code": t["theme_code"], "name": t["name"]}
            for t in EXTENDED_THEME_LIBRARY
        ]

        initial: dict[str, Any] = {
            "market_snapshot": market_snapshot,
            "theme_library": theme_directory,
        }

        factor_research = dict(snapshot.get("factor_research") or {})
        if factor_research:
            initial["factor_research"] = {
                "active_factors": list(factor_research.get("active_factors") or [])[:3],
                "top_factor_names": list(((factor_research.get("summary") or {}).get("top_factor_names") or []))[:3],
                "preferred_strategy_types": list(factor_research.get("preferred_strategy_types") or [])[:4],
                "degraded": bool(factor_research.get("degraded")),
            }

        # 传递 research_task 上下文（如有）
        if research_task:
            initial["research_task"] = {
                k: research_task[k]
                for k in ("task_key", "theme_code", "direction", "target_symbols", "strategy_preferences")
                if k in research_task
            }

        return initial


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_pipeline: Optional[MultiStageStrategyPipeline] = None


def get_strategy_pipeline() -> MultiStageStrategyPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = MultiStageStrategyPipeline()
    return _pipeline
