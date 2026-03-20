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

from strategy_factory import PIPELINE_STAGE_TIMEOUT_SEC, PIPELINE_STAGE_TIMEOUTS

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
                    "llm_attempted": sr.llm_attempted,
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
                    if stage_def.prefer_fallback:
                        consecutive_llm_failures = 0
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
        llm_attempted = False

        if stage_def.prefer_fallback:
            logger.info("Stage %s using local fallback (prefer_fallback)", stage_id)
            return await self._call_fallback_stage(stage_def, db, input_data, snapshot, started, llm_attempted=False)

        # 1) 尝试 LLM 调用（跳过条件：skip_llm 标记或 provider 不可用）
        if not skip_llm and self.provider.is_enabled():
            llm_attempted = True
            prepared_input = self._prepare_stage_input(stage_id, input_data)
            try:
                output = await self.provider.call_stage(
                    stage_id=stage_def.stage_id,
                    input_data=prepared_input,
                    system_prompt=stage_def.system_prompt,
                    max_tokens=stage_def.max_tokens,
                    temperature=stage_def.temperature,
                    timeout_sec=PIPELINE_STAGE_TIMEOUTS.get(stage_def.stage_id, PIPELINE_STAGE_TIMEOUT_SEC),
                )
                if validate_stage_output(stage_id, output):
                    elapsed = time.perf_counter() - started
                    return StageResult(
                        stage_id=stage_id,
                        output=output,
                        used_fallback=False,
                        llm_attempted=True,
                        prompt_chars=len(stage_def.system_prompt) + len(json.dumps(prepared_input, ensure_ascii=False, default=str)),
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
        return await self._call_fallback_stage(
            stage_def,
            db,
            input_data,
            snapshot,
            started,
            llm_attempted=llm_attempted,
        )

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
        prepared_input = self._prepare_stage_input(stage_def.stage_id, input_data)
        return await self.provider.call_stage(
            stage_id=stage_def.stage_id,
            input_data=prepared_input,
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
        *,
        llm_attempted: bool,
    ) -> StageResult:
        """执行 fallback 函数。"""
        if stage_def.fallback_fn is None:
            return StageResult(
                stage_id=stage_def.stage_id,
                output={},
                used_fallback=True,
                llm_attempted=llm_attempted,
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
                llm_attempted=llm_attempted,
                elapsed_sec=elapsed,
                error=None if valid else f"fallback output failed validation for {stage_def.stage_id}",
            )
        except Exception as exc:
            logger.error("Stage %s fallback failed: %s", stage_def.stage_id, exc)
            return StageResult(
                stage_id=stage_def.stage_id,
                output={},
                used_fallback=True,
                llm_attempted=llm_attempted,
                elapsed_sec=time.perf_counter() - started,
                error=f"fallback failed: {exc}",
            )

    @staticmethod
    def _build_initial_input(
        snapshot: dict[str, Any],
        research_task: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """构建 Stage 1 (event_recognition) 的输入。"""
        market_snapshot: dict[str, Any] = {}
        snapshot_date = snapshot.get("date") or snapshot.get("snapshot_date")
        if snapshot_date is not None:
            market_snapshot["date"] = snapshot_date

        fear_greed = snapshot.get("fear_greed")
        if fear_greed is None:
            fear_greed = snapshot.get("fear_greed_index")
        if fear_greed is not None:
            market_snapshot["fear_greed"] = fear_greed
            market_snapshot["fear_greed_index"] = snapshot.get("fear_greed_index", fear_greed)

        sentiment = snapshot.get("sentiment") or snapshot.get("fg_level")
        if sentiment is not None:
            market_snapshot["sentiment"] = sentiment

        sector_data = snapshot.get("hot_sectors") or snapshot.get("sectors") or []
        if isinstance(sector_data, list):
            market_snapshot["sectors"] = sector_data[:20]

        north_fund = snapshot.get("north_fund")
        if not north_fund and snapshot.get("north_fund_3d_net") is not None:
            north_fund = {"net_3d": snapshot.get("north_fund_3d_net")}
        if not north_fund:
            north_fund = snapshot.get("capital_flow") or {}
        if north_fund:
            market_snapshot["north_fund"] = north_fund

        dragon_tiger = snapshot.get("dragon_tiger") or []
        if isinstance(dragon_tiger, list):
            market_snapshot["dragon_tiger_summary"] = dragon_tiger[:10]

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

        if research_task:
            initial["research_task"] = {
                k: research_task[k]
                for k in ("task_key", "theme_code", "direction", "target_symbols", "strategy_preferences")
                if k in research_task
            }

        return initial

    @staticmethod
    def _prepare_stage_input(stage_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """按阶段压缩输入，降低 LLM 延迟和超时概率。"""
        if stage_id != "strategy_generation":
            return input_data

        prepared: dict[str, Any] = {}

        market_snapshot = dict(input_data.get("market_snapshot") or {})
        if market_snapshot:
            prepared["market_snapshot"] = {
                key: market_snapshot.get(key)
                for key in ("date", "fear_greed", "sentiment", "north_fund")
                if key in market_snapshot
            }

        research_task = dict(input_data.get("research_task") or {})
        if research_task:
            prepared["research_task"] = {
                key: research_task.get(key)
                for key in (
                    "task_key",
                    "task_source",
                    "theme_code",
                    "direction",
                    "target_symbols",
                    "strategy_preferences",
                    "opportunity_type",
                    "horizon",
                )
                if key in research_task
            }

        themes = list(input_data.get("themes") or [])
        if themes:
            prepared["themes"] = [
                {
                    "theme_code": item.get("theme_code"),
                    "theme_name": item.get("theme_name"),
                    "direction": item.get("direction"),
                    "confidence": item.get("confidence"),
                }
                for item in themes[:3]
            ]

        exposures = list(input_data.get("exposures") or [])
        if exposures:
            prepared["exposures"] = [
                {
                    "theme_code": item.get("theme_code"),
                    "target_symbols": list(item.get("target_symbols") or [])[:6],
                    "sector": item.get("sector"),
                    "exposure_type": item.get("exposure_type"),
                    "weight": item.get("weight"),
                }
                for item in exposures[:4]
            ]

        confirmations = list(input_data.get("confirmations") or [])
        if confirmations:
            prepared["confirmations"] = [
                {
                    "theme_code": item.get("theme_code"),
                    "symbol": item.get("symbol"),
                    "confirmed": item.get("confirmed"),
                    "signal_strength": item.get("signal_strength"),
                    "entry_timing": item.get("entry_timing"),
                    "risk_level": item.get("risk_level"),
                }
                for item in confirmations[:8]
            ]

        return prepared or input_data


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_pipeline: Optional[MultiStageStrategyPipeline] = None


def get_strategy_pipeline() -> MultiStageStrategyPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = MultiStageStrategyPipeline()
    return _pipeline
