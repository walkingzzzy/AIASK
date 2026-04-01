"""外部 AI 策略生成 provider。"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx
import pandas as pd
from strategy_factory.domain.targets import _apply_target_symbol_policy, _normalize_research_task_contract

from ..env_loader import load_mcp_env


class StrategyLLMRequestError(RuntimeError):
    def __init__(self, message: str, *, metrics: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.metrics = dict(metrics or {})


@dataclass
class StrategyLLMConfig:
    enabled: bool = False
    provider: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout_sec: float = 30.0
    connect_timeout_sec: float = 8.0
    write_timeout_sec: float = 10.0
    pool_timeout_sec: float = 5.0
    temperature: float = 0.3
    max_tokens: int = 900
    retry_count: int = 2
    retry_backoff_sec: float = 1.0
    initial_compact_level: int = 0
    recent_timeout_minimal_streak: int = 1
    recent_timeout_cooldown_sec: float = 600.0
    max_concurrency: int = 3
    strict: bool = False

    @classmethod
    def from_env(cls) -> "StrategyLLMConfig":
        load_mcp_env(override=False, only_prefixes=('STRATEGY_LLM_',))
        enabled = str(os.getenv("STRATEGY_LLM_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"}
        timeout_sec = float(os.getenv("STRATEGY_LLM_TIMEOUT_SEC", "30") or 30)
        initial_compact_level = max(0, min(2, int(os.getenv("STRATEGY_LLM_INITIAL_COMPACT_LEVEL", "0") or 0)))
        recent_timeout_minimal_streak = max(1, min(8, int(os.getenv("STRATEGY_LLM_RECENT_TIMEOUT_MINIMAL_STREAK", "1") or 1)))
        recent_timeout_cooldown_sec = max(0.0, float(os.getenv("STRATEGY_LLM_RECENT_TIMEOUT_COOLDOWN_SEC", "600") or 600))
        return cls(
            enabled=enabled,
            provider=str(os.getenv("STRATEGY_LLM_PROVIDER", "openai_compatible") or "openai_compatible"),
            base_url=str(os.getenv("STRATEGY_LLM_BASE_URL", "") or "").strip(),
            api_key=str(os.getenv("STRATEGY_LLM_API_KEY", "") or "").strip(),
            model=str(os.getenv("STRATEGY_LLM_MODEL", "") or "").strip(),
            timeout_sec=timeout_sec,
            connect_timeout_sec=float(os.getenv("STRATEGY_LLM_CONNECT_TIMEOUT_SEC", str(min(timeout_sec, 8.0))) or min(timeout_sec, 8.0)),
            write_timeout_sec=float(os.getenv("STRATEGY_LLM_WRITE_TIMEOUT_SEC", str(min(timeout_sec, 10.0))) or min(timeout_sec, 10.0)),
            pool_timeout_sec=float(os.getenv("STRATEGY_LLM_POOL_TIMEOUT_SEC", str(min(timeout_sec, 5.0))) or min(timeout_sec, 5.0)),
            temperature=float(os.getenv("STRATEGY_LLM_TEMPERATURE", "0.3") or 0.3),
            max_tokens=max(128, int(os.getenv("STRATEGY_LLM_MAX_TOKENS", "900") or 900)),
            retry_count=max(0, int(os.getenv("STRATEGY_LLM_RETRY_COUNT", "2") or 2)),
            retry_backoff_sec=max(0.0, float(os.getenv("STRATEGY_LLM_RETRY_BACKOFF_SEC", "1.0") or 1.0)),
            initial_compact_level=initial_compact_level,
            recent_timeout_minimal_streak=recent_timeout_minimal_streak,
            recent_timeout_cooldown_sec=recent_timeout_cooldown_sec,
            max_concurrency=max(1, min(8, int(os.getenv("STRATEGY_LLM_MAX_CONCURRENCY", "3") or 3))),
            strict=str(os.getenv("STRATEGY_LLM_STRICT_MODE", "")).strip().lower() in {"1", "true", "yes", "on"},
        )


class _StrategyLLMProviderRuntimeMixin:
        def _timeout_for_attempt(self, attempt: int, total_attempts: int) -> float:
            base = max(float(self.config.timeout_sec or 0), 5.0)
            if total_attempts <= 1:
                return min(base, 25.0)
            schedule = [min(base, 12.0), min(base, 20.0), min(base, 30.0)]
            timeout_sec = schedule[min(max(attempt - 1, 0), len(schedule) - 1)]
            return max(5.0, timeout_sec)

        def _request_timeout(self, request_timeout_sec: float) -> httpx.Timeout:
            connect_timeout = max(1.0, min(float(self.config.connect_timeout_sec or request_timeout_sec), request_timeout_sec))
            write_timeout = max(1.0, min(float(self.config.write_timeout_sec or request_timeout_sec), request_timeout_sec))
            pool_timeout = max(1.0, min(float(self.config.pool_timeout_sec or request_timeout_sec), request_timeout_sec))
            return httpx.Timeout(connect=connect_timeout, read=request_timeout_sec, write=write_timeout, pool=pool_timeout)

        def _request_limit_for_attempt(self, limit: int, attempt: int, *, initial_compact_level: int = 0) -> int:
            requested_limit = self._normalize_limit(limit)
            base_reduction = 1 if initial_compact_level >= 1 and requested_limit > 1 else 0
            return max(1, requested_limit - base_reduction - max(0, attempt - 1))

        def _compact_level_for_attempt(attempt: int, total_attempts: int) -> int:
            index = max(int(attempt or 1) - 1, 0)
            if int(total_attempts or 1) <= 1:
                return 0
            if index == 0:
                return 0
            return 2

        def _max_tokens_for_attempt(self, request_limit: int, compact_level: int) -> int:
            base = max(128, int(self.config.max_tokens or 900))
            analysis_budget = 260 if compact_level <= 0 else (160 if compact_level == 1 else 96)
            candidate_budget = max(1, int(request_limit or 1)) * (220 if compact_level <= 0 else (170 if compact_level == 1 else 140))
            return max(128, min(base, analysis_budget + candidate_budget))

        def _is_timeout_like_error(exc: Exception) -> bool:
            return isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError))

        def _recent_timeout_degrade_state(self) -> tuple[int, Optional[str]]:
            initial_level = max(0, min(int(self.config.initial_compact_level or 0), 2))
            now = time.monotonic()
            if self._recent_timeout_cooldown_until > 0 and self._recent_timeout_cooldown_until <= now:
                self._recent_timeout_streak = 0
                self._recent_timeout_cooldown_until = 0.0
            if self._recent_timeout_streak >= max(1, int(self.config.recent_timeout_minimal_streak or 1)) and self._recent_timeout_cooldown_until > now:
                return max(initial_level, 2), 'recent_timeout'
            return initial_level, None

        def _record_request_failure(self, exc: Exception) -> None:
            self._last_failure_type = exc.__class__.__name__
            if self._is_timeout_like_error(exc):
                self._recent_timeout_streak += 1
                self._recent_timeout_cooldown_until = time.monotonic() + max(0.0, float(self.config.recent_timeout_cooldown_sec or 0.0))

        def _record_request_success(self) -> None:
            self._recent_timeout_streak = 0
            self._recent_timeout_cooldown_until = 0.0
            self._last_failure_type = None

        async def generate_candidates(
            self,
            *,
            snapshot: Optional[dict[str, Any]] = None,
            market_frame: Optional[pd.DataFrame] = None,
            research_context: Optional[dict[str, Any]] = None,
            parent_strategies: Optional[list[dict[str, Any]]] = None,
            history_summary: Optional[list[dict[str, Any]]] = None,
            research_task: Optional[dict[str, Any]] = None,
            limit: int = 3,
        ) -> Optional[dict[str, Any]]:
            if not self.is_enabled():
                return None

            started_at = time.perf_counter()
            requested_limit = self._normalize_limit(limit)
            market_summary = self._summarize_market_frame(market_frame)
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            last_exc: Optional[Exception] = None
            attempts = max(1, int(self.config.retry_count or 0) + 1)
            attempt_reports: list[dict[str, Any]] = []
            initial_compact_level, degrade_reason = self._recent_timeout_degrade_state()
            initial_prompt_profile = self._prompt_profile_name(initial_compact_level)
            effective_attempts = 1 if degrade_reason == 'recent_timeout' else attempts
            client = self._client
            for attempt in range(1, effective_attempts + 1):
                compact_level = max(initial_compact_level, self._compact_level_for_attempt(attempt, effective_attempts))
                request_limit = self._request_limit_for_attempt(requested_limit, attempt, initial_compact_level=initial_compact_level)
                compact_research_context = self._compact_research_context(research_context, compact_level=compact_level)
                system_prompt, user_prompt = self._build_prompt(
                    snapshot or {},
                    market_summary,
                    compact_research_context,
                    list(parent_strategies or []),
                    list(history_summary or []),
                    request_limit,
                    research_task=research_task,
                    compact_level=compact_level,
                )
                prompt_profile = self._prompt_profile_name(compact_level)
                request_timeout_sec = self._timeout_for_attempt(attempt, effective_attempts)
                if degrade_reason == 'recent_timeout' and attempt == 1:
                    request_timeout_sec = max(request_timeout_sec, min(float(self.config.timeout_sec or request_timeout_sec), 15.0))
                max_tokens = self._max_tokens_for_attempt(request_limit, compact_level)
                payload = {
                    "model": self.config.model,
                    "temperature": self.config.temperature,
                    "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"},
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                }
                request_started_at = time.perf_counter()
                try:
                    async with self._request_semaphore:
                        response = await client.post(
                            self._endpoint(),
                            headers=headers,
                            json=payload,
                            timeout=self._request_timeout(request_timeout_sec),
                        )
                    response.raise_for_status()
                    body = response.json()
                    content = self._extract_content(body)
                    json_text = self._extract_json_text(content)
                    data = json.loads(json_text)
                    raw_candidates = data.get("candidates") if isinstance(data, dict) else None
                    if not isinstance(raw_candidates, list):
                        raise ValueError("external llm response missing candidates")
                    analysis = self._normalize_analysis(data.get("analysis") if isinstance(data, dict) else {})
                    candidates = []
                    for item in raw_candidates:
                        normalized_candidate = self._normalize_candidate_payload(item, research_task=research_task)
                        if normalized_candidate is not None:
                            candidates.append(normalized_candidate)
                    if not candidates:
                        raise ValueError("external llm response missing executable candidates")
                    selected_candidates = candidates[:requested_limit]
                    self._record_request_success()
                    request_metrics = {
                        "status": "succeeded",
                        "endpoint": self._endpoint(),
                        "provider": self.config.provider,
                        "model": self.config.model,
                        "requested_limit": requested_limit,
                        "attempt_count": attempt,
                        "prompt_profile": prompt_profile,
                        "initial_prompt_profile": initial_prompt_profile,
                        "degrade_reason": degrade_reason,
                        "recent_timeout_streak": self._recent_timeout_streak,
                        "prompt_chars": len(system_prompt) + len(user_prompt),
                        "max_tokens": max_tokens,
                        "response_chars": len(content),
                        "raw_candidate_count": len(raw_candidates),
                        "returned_candidate_count": len(candidates),
                        "selected_candidate_count": len(selected_candidates),
                        "analysis_present": bool(analysis),
                        "analysis_keys": sorted(list(analysis.keys())),
                        "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                        "attempts": [*attempt_reports, {
                            "attempt": attempt,
                            "status": "succeeded",
                            "request_limit": request_limit,
                            "timeout_sec": request_timeout_sec,
                            "prompt_profile": prompt_profile,
                            "prompt_chars": len(system_prompt) + len(user_prompt),
                            "max_tokens": max_tokens,
                            "elapsed_seconds": round(time.perf_counter() - request_started_at, 4),
                            "raw_candidate_count": len(raw_candidates),
                            "returned_candidate_count": len(candidates),
                            "analysis_present": bool(analysis),
                        }],
                    }
                    return {
                        "provider": self.config.provider,
                        "model": self.config.model,
                        "prompt": {
                            "system": system_prompt,
                            "user": user_prompt,
                            "profile": prompt_profile,
                        },
                        "raw_response": body,
                        "content": content,
                        "analysis": analysis,
                        "research_context": compact_research_context,
                        "research_task": dict(research_task or {}),
                        "candidates": selected_candidates,
                        "request_metrics": request_metrics,
                    }
                except (
                    httpx.TimeoutException,
                    httpx.ConnectError,
                    httpx.ReadError,
                    httpx.RemoteProtocolError,
                    httpx.HTTPStatusError,
                    json.JSONDecodeError,
                    ValueError,
                ) as exc:
                    last_exc = exc
                    attempt_reports.append({
                        "attempt": attempt,
                        "status": "failed",
                        "request_limit": request_limit,
                        "timeout_sec": request_timeout_sec,
                        "prompt_profile": prompt_profile,
                        "prompt_chars": len(system_prompt) + len(user_prompt),
                        "max_tokens": max_tokens,
                        "degrade_reason": degrade_reason,
                        "initial_prompt_profile": initial_prompt_profile,
                        "elapsed_seconds": round(time.perf_counter() - request_started_at, 4),
                        "error_type": exc.__class__.__name__,
                        "error": self._error_text(exc),
                        "status_code": getattr(getattr(exc, "response", None), "status_code", None),
                    })
                    if attempt >= attempts:
                        break
                    await asyncio.sleep(self.config.retry_backoff_sec * attempt)

            if last_exc is not None:
                self._record_request_failure(last_exc)
            metrics = {
                "status": "failed",
                "endpoint": self._endpoint(),
                "provider": self.config.provider,
                "model": self.config.model,
                "requested_limit": requested_limit,
                "initial_prompt_profile": initial_prompt_profile,
                "degrade_reason": degrade_reason,
                "recent_timeout_streak": self._recent_timeout_streak,
                "recent_timeout_cooldown_sec": round(max(self._recent_timeout_cooldown_until - time.monotonic(), 0.0), 4),
                "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                "attempt_count": len(attempt_reports),
                "attempts": attempt_reports,
                "last_error_type": last_exc.__class__.__name__ if last_exc else "RuntimeError",
                "last_error": self._error_text(last_exc or RuntimeError("external llm request failed")),
            }
            raise StrategyLLMRequestError(
                f"external llm request failed after {len(attempt_reports)} attempts: {metrics['last_error_type']}",
                metrics=metrics,
            ) from last_exc

        async def call_stage(
            self,
            *,
            stage_id: str,
            input_data: dict[str, Any],
            system_prompt: str,
            max_tokens: int = 500,
            temperature: float = 0.2,
            timeout_sec: Optional[float] = None,
        ) -> dict[str, Any]:
            """Execute a single pipeline stage via the external LLM.

            This reuses the existing HTTP infrastructure (retry, timeout
            degradation, cooldown tracking) but with a much simpler prompt
            structure: a short system prompt + JSON-serialised input data.

            Returns the parsed JSON dict from the LLM response.
            Raises ``StrategyLLMRequestError`` on failure.
            """
            if not self.is_enabled():
                raise StrategyLLMRequestError(
                    f"call_stage({stage_id}): LLM provider not enabled",
                    metrics={"stage_id": stage_id, "status": "disabled"},
                )

            started_at = time.perf_counter()
            stage_timeout = float(timeout_sec or 10.0)
            _compact_level, degrade_reason = self._recent_timeout_degrade_state()
            if degrade_reason == 'recent_timeout':
                raise StrategyLLMRequestError(
                    f"call_stage({stage_id}) skipped during timeout cooldown",
                    metrics={
                        "stage_id": stage_id,
                        "status": "cooldown_skip",
                        "last_error_type": "RecentTimeoutCooldown",
                        "recent_timeout_streak": self._recent_timeout_streak,
                        "recent_timeout_cooldown_sec": round(
                            max(self._recent_timeout_cooldown_until - time.monotonic(), 0.0),
                            4,
                        ),
                        "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                    },
                )
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            user_prompt = json.dumps(input_data, ensure_ascii=False, default=str, separators=(",", ":"))
            payload = {
                "model": self.config.model,
                "temperature": temperature,
                "max_tokens": max(128, max_tokens),
                "response_format": {"type": "json_object"},
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }

            last_exc: Optional[Exception] = None
            attempts = 1  # single attempt per stage — fail fast and fallback

            client = self._client
            for attempt in range(1, attempts + 1):
                request_started_at = time.perf_counter()
                try:
                    async with self._request_semaphore:
                        response = await client.post(
                            self._endpoint(),
                            headers=headers,
                            json=payload,
                            timeout=self._request_timeout(stage_timeout),
                        )
                    response.raise_for_status()
                    body = response.json()
                    content = self._extract_content(body)
                    json_text = self._extract_json_text(content)
                    data = json.loads(json_text)
                    if isinstance(data, list):
                        # LLM 返回了裸数组 — 根据 stage_id 包装成 dict
                        _STAGE_LIST_KEY = {
                            "event_recognition": "events",
                            "theme_propagation": "themes",
                            "exposure_mapping": "exposures",
                            "market_confirmation": "confirmations",
                            "strategy_generation": "candidates",
                        }
                        wrap_key = _STAGE_LIST_KEY.get(stage_id, "results")
                        data = {wrap_key: data}
                    if not isinstance(data, dict):
                        raise ValueError(f"call_stage({stage_id}): expected JSON object, got {type(data).__name__}")
                    self._record_request_success()
                    return data
                except (
                    httpx.TimeoutException,
                    httpx.ConnectError,
                    httpx.ReadError,
                    httpx.RemoteProtocolError,
                    httpx.HTTPStatusError,
                    json.JSONDecodeError,
                    ValueError,
                ) as exc:
                    last_exc = exc
                    if attempt >= attempts:
                        break
                    await asyncio.sleep(min(self.config.retry_backoff_sec * attempt, 3.0))

            if last_exc is not None:
                self._record_request_failure(last_exc)
            raise StrategyLLMRequestError(
                f"call_stage({stage_id}) failed after {attempts} attempts: {self._error_text(last_exc or RuntimeError('unknown'))}",
                metrics={
                    "stage_id": stage_id,
                    "status": "failed",
                    "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                    "last_error_type": (last_exc.__class__.__name__ if last_exc else "RuntimeError"),
                },
            ) from last_exc
