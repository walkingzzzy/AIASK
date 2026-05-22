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

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

def _get_pipeline_constants():
    from strategy_factory import PIPELINE_STAGE_TIMEOUT_SEC, PIPELINE_STAGE_TIMEOUTS
    return PIPELINE_STAGE_TIMEOUT_SEC, PIPELINE_STAGE_TIMEOUTS

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


def _normalize_hint_text(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "").replace("_", "")


def _extract_named_market_hints(snapshot: dict[str, Any]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()

    def add(value: Any):
        text = str(value or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        names.append(text)

    for item in list(snapshot.get("hot_sectors") or snapshot.get("sectors") or [])[:12]:
        if isinstance(item, dict):
            for key in ("group", "name", "sector", "theme"):
                add(item.get(key))
        else:
            add(item)
    for item in list(snapshot.get("dragon_tiger") or [])[:10]:
        if isinstance(item, dict):
            add(item.get("name"))
            add(item.get("industry"))
    return names


def _match_theme_candidates(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    hint_names = _extract_named_market_hints(snapshot)
    for hint in hint_names:
        normalized_hint = _normalize_hint_text(hint)
        if not normalized_hint:
            continue
        for theme in EXTENDED_THEME_LIBRARY:
            aliases = [str(alias or "").strip() for alias in list(theme.get("aliases") or []) if str(alias or "").strip()]
            alias_tokens = [theme.get("name"), theme.get("theme_code"), *aliases]
            normalized_tokens = [_normalize_hint_text(token) for token in alias_tokens if _normalize_hint_text(token)]
            if not any(
                normalized_hint in token or token in normalized_hint
                for token in normalized_tokens
            ):
                continue
            theme_code = str(theme.get("theme_code") or "").strip()
            if not theme_code or theme_code in seen_codes:
                break
            seen_codes.add(theme_code)
            candidates.append(
                {
                    "source_hint": hint,
                    "theme_code": theme_code,
                    "theme_name": theme.get("name"),
                    "aliases": aliases[:4],
                    "parent": theme.get("parent"),
                }
            )
            break
    return candidates

logger = logging.getLogger(__name__)


def _stage_output_list_counts(output: Any) -> dict[str, int]:
    if not isinstance(output, dict):
        return {}
    counts: dict[str, int] = {}
    for key, value in output.items():
        if isinstance(value, list):
            counts[str(key)] = len(value)
    return counts


def _stage_validation_failure_reason(stage_id: str, output: Any) -> str:
    if not isinstance(output, dict):
        return "output_not_object"
    counts = _stage_output_list_counts(output)
    if stage_id == "market_confirmation" and "confirmations" in output and counts.get("confirmations", 0) <= 0:
        return "empty_confirmations"
    if stage_id == "strategy_generation" and "candidates" in output and counts.get("candidates", 0) <= 0:
        return "empty_candidates"
    if stage_id == "event_recognition" and "events" in output and counts.get("events", 0) <= 0:
        return "empty_events"
    if stage_id == "theme_propagation" and "themes" in output and counts.get("themes", 0) <= 0:
        return "empty_themes"
    if stage_id == "exposure_mapping" and "exposures" in output and counts.get("exposures", 0) <= 0:
        return "empty_exposures"
    return "schema_validation_failed"


def _stage_result_fallback_reason(stage_result: StageResult) -> str:
    metrics = dict(stage_result.llm_error_metrics or {})
    if metrics.get("validation_failure_reason"):
        return str(metrics.get("validation_failure_reason"))
    if metrics.get("status"):
        return str(metrics.get("status"))
    if stage_result.llm_error_type:
        return str(stage_result.llm_error_type)
    if stage_result.error:
        return str(stage_result.error)
    if stage_result.used_fallback and not stage_result.llm_attempted:
        return "local_fallback_preferred_or_skip"
    return "fallback"


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
        fallback_stage_ids = [sid for sid, sr in self.stages.items() if sr.used_fallback]
        invalid_output_stage_ids = [
            sid
            for sid, sr in self.stages.items()
            if dict(sr.llm_error_metrics or {}).get("status") == "invalid_output"
        ]
        stage_fallback_reasons = {
            sid: _stage_result_fallback_reason(sr)
            for sid, sr in self.stages.items()
            if sr.used_fallback
        }
        return {
            "pipeline_elapsed_sec": round(self.elapsed_sec, 4),
            "stage_count": len(self.stages),
            "candidate_count": len(self.candidates),
            "error": self.error,
            "fallback_stage_count": len(fallback_stage_ids),
            "fallback_stage_ids": fallback_stage_ids,
            "invalid_output_stage_ids": invalid_output_stage_ids,
            "stage_fallback_reasons": stage_fallback_reasons,
            "stages": {
                sid: {
                    "used_fallback": sr.used_fallback,
                    "llm_attempted": sr.llm_attempted,
                    "elapsed_sec": round(sr.elapsed_sec, 4),
                    "prompt_chars": sr.prompt_chars,
                    "response_chars": sr.response_chars,
                    "error": sr.error,
                    "llm_error": sr.llm_error,
                    "llm_error_type": sr.llm_error_type,
                    "llm_error_metrics": dict(sr.llm_error_metrics or {}),
                    "fallback_reason": stage_fallback_reasons.get(sid),
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
        """两阶段并行编排。

        Phase-1（并行）：event_recognition + theme_propagation + exposure_mapping
          三路同时从初始 snapshot 出发，互不依赖，节省约 2 个 LLM 往返延迟。
          theme_propagation / exposure_mapping 的 fallback 已增强，可在无上游
          输出时从 snapshot 热门板块推断，保证输出非空。

        Phase-2（串行）：market_confirmation → strategy_generation
          依赖 Phase-1 合并后的上下文，必须顺序执行。
        """
        snapshot = snapshot or {}
        pipeline_started = time.perf_counter()
        result = PipelineResult()
        PIPELINE_STAGE_TIMEOUT_SEC, PIPELINE_STAGE_TIMEOUTS = _get_pipeline_constants()

        stage_input = self._build_initial_input(snapshot, research_task)
        skip_llm = False

        # ── Phase 1：三路并行 ────────────────────────────────────────────────
        PARALLEL_STAGES = ["event_recognition", "theme_propagation", "exposure_mapping"]
        parallel_results: list[Any] = await asyncio.gather(
            *[
                self.run_stage(
                    db=db,
                    stage_id=sid,
                    input_data=stage_input,
                    snapshot=snapshot,
                    stage_def=self.registry.get(sid),
                    skip_llm=skip_llm,
                )
                for sid in PARALLEL_STAGES
            ],
            return_exceptions=True,
        )

        timeout_hit = False
        parallel_llm_failures = 0
        fatal_error: Optional[str] = None

        for sid, sr in zip(PARALLEL_STAGES, parallel_results):
            if isinstance(sr, BaseException):
                logger.warning("Pipeline stage %s raised exception: %s", sid, sr)
                from .strategy_stages import StageResult as _SR
                sr = _SR(stage_id=sid, output={}, used_fallback=True, error=str(sr))
            result.stages[sid] = sr
            if sr.error and not sr.output:
                fatal_error = f"stage {sid} failed: {sr.error}"
                break
            if not skip_llm and sr.used_fallback:
                parallel_llm_failures += 1
                _limit = PIPELINE_STAGE_TIMEOUTS.get(sid, PIPELINE_STAGE_TIMEOUT_SEC)
                if sr.elapsed_sec >= _limit * 0.8:
                    timeout_hit = True
            stage_input = {**stage_input, **sr.output}

        if fatal_error:
            result.error = fatal_error
            result.candidates = list(stage_input.get("candidates") or [])
            result.elapsed_sec = time.perf_counter() - pipeline_started
            return result

        if timeout_hit or parallel_llm_failures >= 2:
            skip_llm = True
            logger.info(
                "Pipeline Phase-1: %d LLM failure(s), timeout_hit=%s → skip_llm for Phase-2",
                parallel_llm_failures, timeout_hit,
            )

        # ── Phase 2：串行（依赖 Phase-1 合并上下文）────────────────────────
        consecutive_llm_failures = 0
        for stage_id in ["market_confirmation", "strategy_generation"]:
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
                    if not stage_def.prefer_fallback:
                        consecutive_llm_failures += 1
                    _stage_limit = PIPELINE_STAGE_TIMEOUTS.get(stage_id, PIPELINE_STAGE_TIMEOUT_SEC)
                    if stage_result.elapsed_sec >= _stage_limit * 0.8:
                        logger.info(
                            "Stage %s took %.1fs (LLM timeout), skipping LLM for remaining stages",
                            stage_id, stage_result.elapsed_sec,
                        )
                        skip_llm = True
                    elif consecutive_llm_failures >= 2:
                        logger.info(
                            "LLM failed %d consecutive stages in Phase-2, skipping LLM",
                            consecutive_llm_failures,
                        )
                        skip_llm = True
                else:
                    consecutive_llm_failures = 0

            if stage_result.error and not stage_result.output:
                result.error = f"stage {stage_id} failed: {stage_result.error}"
                break

            stage_input = {**stage_input, **stage_result.output}

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
        prepared_input = dict(input_data or {})
        prompt_chars = 0
        llm_error = None
        llm_error_type = None
        llm_error_metrics: dict[str, Any] = {}

        if stage_def.prefer_fallback:
            logger.info("Stage %s using local fallback (prefer_fallback)", stage_id)
            return await self._call_fallback_stage(
                stage_def,
                db,
                input_data,
                snapshot,
                started,
                llm_attempted=False,
                prompt_chars=prompt_chars,
                llm_error=llm_error,
                llm_error_type=llm_error_type,
                llm_error_metrics=llm_error_metrics,
            )

        # 1) 尝试 LLM 调用（跳过条件：skip_llm 标记或 provider 不可用）
        if not skip_llm and self.provider.is_enabled():
            llm_attempted = True
            prepared_input = self._prepare_stage_input(stage_id, input_data)
            # PR-AI4: 向量检索注入 — 为 strategy_generation 阶段注入真实基本面数据
            if stage_id == "strategy_generation" and db is not None:
                prepared_input = await self._enrich_with_stock_profiles(
                    db, prepared_input
                )
            # PR-AI2: Look-ahead Bias 防护 — 注入时间约束
            _snapshot_date = str(
                (input_data.get("market_snapshot") or {}).get("date")
                or (snapshot or {}).get("date")
                or (snapshot or {}).get("snapshot_date")
                or ""
            ).strip()
            _lookahead_guard = ""
            if _snapshot_date:
                _lookahead_guard = (
                    f"重要约束：当前业务时点={_snapshot_date}。"
                    f"你只能引用早于或等于{_snapshot_date}的事件和数据，"
                    f"严禁引用此日期之后的任何信息。\n\n"
                )
            _effective_system_prompt = _lookahead_guard + stage_def.system_prompt
            prompt_chars = len(_effective_system_prompt) + len(json.dumps(prepared_input, ensure_ascii=False, default=str))
            pipeline_stage_timeout_sec, pipeline_stage_timeouts = _get_pipeline_constants()
            try:
                output = await self.provider.call_stage(
                    stage_id=stage_def.stage_id,
                    input_data=prepared_input,
                    system_prompt=_effective_system_prompt,
                    max_tokens=stage_def.max_tokens,
                    temperature=stage_def.temperature,
                    timeout_sec=pipeline_stage_timeouts.get(stage_def.stage_id, pipeline_stage_timeout_sec),
                )
                if validate_stage_output(stage_id, output):
                    elapsed = time.perf_counter() - started
                    return StageResult(
                        stage_id=stage_id,
                        output=output,
                        used_fallback=False,
                        llm_attempted=True,
                        prompt_chars=prompt_chars,
                        response_chars=len(json.dumps(output, ensure_ascii=False, default=str)),
                        elapsed_sec=elapsed,
                    )
                else:
                    llm_error = f"llm output failed validation for {stage_id}"
                    llm_error_type = "ValidationError"
                    validation_failure_reason = _stage_validation_failure_reason(stage_id, output)
                    llm_error_metrics = {
                        "stage_id": stage_id,
                        "status": "invalid_output",
                        "validation_failure_reason": validation_failure_reason,
                        "output_keys": list(output.keys()) if isinstance(output, dict) else [],
                        "output_list_counts": _stage_output_list_counts(output),
                        "output_sample": json.dumps(output, ensure_ascii=False, default=str)[:200],
                    }
                    logger.warning(
                        "Stage %s LLM output failed validation, falling back. "
                        "reason=%s, output keys=%s, sample=%.200s",
                        stage_id,
                        validation_failure_reason,
                        list(output.keys()) if isinstance(output, dict) else [],
                        json.dumps(output, ensure_ascii=False, default=str)[:200],
                    )
            except StrategyLLMRequestError as exc:
                llm_error = str(exc)
                llm_error_metrics = dict(getattr(exc, "metrics", {}) or {})
                llm_error_type = str(llm_error_metrics.get("last_error_type") or exc.__class__.__name__)
                if llm_error_metrics.get("status") == "cooldown_skip" and llm_error_type == exc.__class__.__name__:
                    llm_error_type = (
                        "RecentOverloadCooldown"
                        if llm_error_metrics.get("cooldown_reason") == "recent_overload"
                        else "RecentTimeoutCooldown"
                    )
                log_fn = logger.info if llm_error_metrics.get("status") == "cooldown_skip" else logger.warning
                log_fn("Stage %s LLM call failed: %s, falling back", stage_id, exc)
            except Exception as exc:
                llm_error = str(exc)
                llm_error_metrics = dict(getattr(exc, "metrics", {}) or {})
                llm_error_type = str(llm_error_metrics.get("last_error_type") or exc.__class__.__name__)
                if llm_error_metrics.get("status") == "cooldown_skip" and llm_error_type == exc.__class__.__name__:
                    llm_error_type = (
                        "RecentOverloadCooldown"
                        if llm_error_metrics.get("cooldown_reason") == "recent_overload"
                        else "RecentTimeoutCooldown"
                    )
                llm_error_metrics = {
                    "stage_id": stage_id,
                    "status": llm_error_metrics.get("status") or "failed",
                    "last_error_type": llm_error_type,
                    **llm_error_metrics,
                }
                log_fn = logger.info if llm_error_metrics.get("status") == "cooldown_skip" else logger.warning
                log_fn("Stage %s LLM call failed: %s, falling back", stage_id, exc)
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
            prompt_chars=prompt_chars,
            llm_error=llm_error,
            llm_error_type=llm_error_type,
            llm_error_metrics=llm_error_metrics,
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
        _timeout_sec, _timeouts = _get_pipeline_constants()
        stage_timeout = _timeouts.get(stage_def.stage_id, _timeout_sec)
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
        prompt_chars: int = 0,
        llm_error: Optional[str] = None,
        llm_error_type: Optional[str] = None,
        llm_error_metrics: Optional[dict[str, Any]] = None,
    ) -> StageResult:
        """执行 fallback 函数。"""
        if stage_def.fallback_fn is None:
            return StageResult(
                stage_id=stage_def.stage_id,
                output={},
                used_fallback=True,
                llm_attempted=llm_attempted,
                prompt_chars=prompt_chars,
                elapsed_sec=time.perf_counter() - started,
                error=f"no fallback for stage {stage_def.stage_id}",
                llm_error=llm_error,
                llm_error_type=llm_error_type,
                llm_error_metrics=dict(llm_error_metrics or {}),
            )
        try:
            output = await stage_def.fallback_fn(db, input_data, snapshot)
            elapsed = time.perf_counter() - started
            valid = validate_stage_output(stage_def.stage_id, output)
            fallback_metrics = dict(llm_error_metrics or {})
            if not valid:
                fallback_metrics.update(
                    {
                        "fallback_validation_failure_reason": _stage_validation_failure_reason(
                            stage_def.stage_id,
                            output,
                        ),
                        "fallback_output_keys": list(output.keys()) if isinstance(output, dict) else [],
                        "fallback_output_list_counts": _stage_output_list_counts(output),
                    }
                )
            return StageResult(
                stage_id=stage_def.stage_id,
                output=output if valid else {},
                used_fallback=True,
                llm_attempted=llm_attempted,
                prompt_chars=prompt_chars,
                elapsed_sec=elapsed,
                error=None if valid else f"fallback output failed validation for {stage_def.stage_id}",
                llm_error=llm_error,
                llm_error_type=llm_error_type,
                llm_error_metrics=fallback_metrics,
            )
        except Exception as exc:
            logger.error("Stage %s fallback failed: %s", stage_def.stage_id, exc)
            return StageResult(
                stage_id=stage_def.stage_id,
                output={},
                used_fallback=True,
                llm_attempted=llm_attempted,
                prompt_chars=prompt_chars,
                elapsed_sec=time.perf_counter() - started,
                error=f"fallback failed: {exc}",
                llm_error=llm_error,
                llm_error_type=llm_error_type,
                llm_error_metrics=dict(llm_error_metrics or {}),
            )

    @staticmethod
    async def _enrich_with_stock_profiles(
        db: Any,
        prepared_input: dict[str, Any],
    ) -> dict[str, Any]:
        """PR-AI4: 从 stock_profile_embeddings 取真实基本面数据注入 LLM 输入。

        让 LLM 看到目标股票的真实 PE/PB/ROE/营收增速/动量/波动率，
        而不是凭训练记忆编造。
        """
        # 收集所有 target_symbols
        target_symbols: list[str] = []
        for source in (
            prepared_input.get("exposures") or [],
            prepared_input.get("confirmations") or [],
        ):
            for item in list(source or []):
                if isinstance(item, dict):
                    syms = item.get("target_symbols") or []
                    if isinstance(syms, list):
                        target_symbols.extend(str(s).strip() for s in syms if str(s).strip())
                    sym = str(item.get("symbol") or "").strip()
                    if sym:
                        target_symbols.append(sym)
        research_task = dict(prepared_input.get("research_task") or {})
        for s in list(research_task.get("target_symbols") or []):
            code = str(s).strip()
            if code:
                target_symbols.append(code)
        # 去重保序
        seen: set[str] = set()
        unique_symbols: list[str] = []
        for s in target_symbols:
            if s not in seen:
                seen.add(s)
                unique_symbols.append(s)
        if not unique_symbols:
            return prepared_input

        list_vector_profiles = getattr(db, "list_vector_profiles", None)
        if not callable(list_vector_profiles):
            return prepared_input

        stock_fundamentals: list[dict[str, Any]] = []
        for code in unique_symbols[:6]:
            try:
                rows = await list_vector_profiles(
                    collection_name="stock_profile_embeddings",
                    stock_code=code,
                    profile_type="fundamental",
                    limit=1,
                )
                if rows:
                    import json as _json
                    meta = _json.loads(rows[0].get("metadata") or "{}")
                    raw = dict(meta.get("raw_features") or {})
                    stock_fundamentals.append({
                        "code": code,
                        "name": meta.get("stock_name") or "",
                        "industry": meta.get("industry") or "",
                        "pe": round(float(raw.get("pe_ratio") or 0), 2),
                        "pb": round(float(raw.get("pb_ratio") or 0), 2),
                        "roe": round(float(raw.get("roe") or 0), 4),
                        "revenue_growth": round(float(raw.get("revenue_growth") or 0), 4),
                        "profit_growth": round(float(raw.get("profit_growth") or 0), 4),
                        "momentum_20d": round(float(raw.get("momentum_20d") or 0), 4),
                        "volatility_20d": round(float(raw.get("volatility_20d") or 0), 4),
                    })
            except Exception:
                continue

        if stock_fundamentals:
            prepared_input["stock_fundamentals"] = stock_fundamentals
        return prepared_input

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
            {
                "theme_code": t["theme_code"],
                "name": t["name"],
                "aliases": list(t.get("aliases") or [])[:6],
                "parent": t.get("parent"),
            }
            for t in EXTENDED_THEME_LIBRARY
        ]
        matched_theme_candidates = _match_theme_candidates(snapshot)

        initial: dict[str, Any] = {
            "market_snapshot": market_snapshot,
            "theme_library": theme_directory,
        }
        if matched_theme_candidates:
            initial["matched_theme_candidates"] = matched_theme_candidates[:8]
        event_detection_hints = {
            "hot_sector_names": _extract_named_market_hints(snapshot)[:8],
            "north_fund_bias": (
                "inflow"
                if float((((market_snapshot.get("north_fund") or {}).get("net_inflow") or 0) or 0)) > 0
                else "neutral_or_outflow"
            ) if market_snapshot.get("north_fund") else None,
        }
        if any(value for value in event_detection_hints.values()):
            initial["event_detection_hints"] = event_detection_hints

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
                for k in (
                    "task_id",
                    "task_key",
                    "task_source",
                    "theme_code",
                    "direction",
                    "opportunity_type",
                    "target_symbols",
                    "strategy_preferences",
                    "preferred_strategy_types",
                    "allowed_strategy_types",
                    "target_symbol_policy",
                    "universe_expansion_policy",
                    "preference_strength",
                    "preference_reason",
                    "validation_focus",
                    "factor_name",
                    "candidate_family",
                    "candidate_name",
                    "rationale",
                    "expected_regime",
                    "validation_score",
                    "template_generation_profile",
                    "generation_limit",
                )
                if k in research_task
            }

        return initial

    @staticmethod
    def _prepare_stage_input(stage_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """按阶段压缩输入，降低 LLM 延迟和超时概率。"""
        if stage_id == "event_recognition":
            prepared: dict[str, Any] = {}

            market_snapshot = dict(input_data.get("market_snapshot") or {})
            if market_snapshot:
                prepared["market_snapshot"] = {
                    key: market_snapshot.get(key)
                    for key in (
                        "date",
                        "fear_greed",
                        "fear_greed_index",
                        "sentiment",
                        "sectors",
                        "north_fund",
                        "dragon_tiger_summary",
                    )
                    if key in market_snapshot
                }
                if isinstance(prepared["market_snapshot"].get("sectors"), list):
                    compact_sectors: list[str] = []
                    for item in prepared["market_snapshot"]["sectors"][:6]:
                        if isinstance(item, dict):
                            compact_sectors.append(str(item.get("group") or item.get("name") or "").strip())
                        else:
                            compact_sectors.append(str(item).strip())
                    prepared["market_snapshot"]["sectors"] = [item for item in compact_sectors if item]
                if isinstance(prepared["market_snapshot"].get("north_fund"), dict):
                    prepared["market_snapshot"]["north_fund"] = {
                        key: prepared["market_snapshot"]["north_fund"].get(key)
                        for key in ("net_inflow", "net_3d")
                        if prepared["market_snapshot"]["north_fund"].get(key) is not None
                    }
                if isinstance(prepared["market_snapshot"].get("dragon_tiger_summary"), list):
                    prepared["market_snapshot"]["dragon_tiger_summary"] = [
                        str(item.get("name") or item.get("code") or "").strip()
                        for item in prepared["market_snapshot"]["dragon_tiger_summary"][:4]
                        if isinstance(item, dict)
                    ]
                    prepared["market_snapshot"]["dragon_tiger_summary"] = [
                        item for item in prepared["market_snapshot"]["dragon_tiger_summary"] if item
                    ]

            hints = dict(input_data.get("event_detection_hints") or {})
            if hints:
                prepared["event_detection_hints"] = hints

            matched_theme_candidates = list(input_data.get("matched_theme_candidates") or [])
            if matched_theme_candidates:
                prepared["matched_theme_candidates"] = matched_theme_candidates[:6]

            research_task = dict(input_data.get("research_task") or {})
            if research_task:
                prepared["research_task"] = {
                    key: research_task.get(key)
                    for key in (
                        "task_id",
                        "task_key",
                        "task_source",
                        "theme_code",
                        "direction",
                        "opportunity_type",
                        "target_symbols",
                        "preferred_strategy_types",
                        "allowed_strategy_types",
                        "preference_reason",
                        "validation_focus",
                        "factor_name",
                        "candidate_family",
                        "candidate_name",
                        "expected_regime",
                        "validation_score",
                        "template_generation_profile",
                    )
                    if key in research_task
                }

            theme_library = list(input_data.get("theme_library") or [])
            prioritized_codes = [
                str(item.get("theme_code") or "").strip()
                for item in matched_theme_candidates[:6]
                if str(item.get("theme_code") or "").strip()
            ]
            selected_theme_library: list[dict[str, Any]] = []
            seen_theme_codes: set[str] = set()
            for code in prioritized_codes:
                for item in theme_library:
                    item_code = str((item or {}).get("theme_code") or "").strip()
                    if item_code != code or item_code in seen_theme_codes:
                        continue
                    seen_theme_codes.add(item_code)
                    selected_theme_library.append(item)
                    break
            if not prioritized_codes:
                for item in theme_library:
                    item_code = str((item or {}).get("theme_code") or "").strip()
                    if not item_code or item_code in seen_theme_codes:
                        continue
                    seen_theme_codes.add(item_code)
                    selected_theme_library.append(item)
                    if len(selected_theme_library) >= 4:
                        break
            if selected_theme_library:
                prepared["theme_library"] = selected_theme_library[:6]
            return prepared

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
                    "task_id",
                    "task_key",
                    "task_source",
                    "theme_code",
                    "direction",
                    "target_symbols",
                    "strategy_preferences",
                    "preferred_strategy_types",
                    "allowed_strategy_types",
                    "target_symbol_policy",
                    "universe_expansion_policy",
                    "preference_strength",
                    "preference_reason",
                    "validation_focus",
                    "opportunity_type",
                    "factor_name",
                    "candidate_family",
                    "candidate_name",
                    "rationale",
                    "expected_regime",
                    "validation_score",
                    "template_generation_profile",
                    "generation_limit",
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
