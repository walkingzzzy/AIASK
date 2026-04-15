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

try:
    from .strategy_llm_provider import StrategyLLMRequestError as _PublicStrategyLLMRequestError
except Exception:  # pragma: no cover - circular import fallback
    _PublicStrategyLLMRequestError = None


if _PublicStrategyLLMRequestError is None:
    class StrategyLLMRequestError(RuntimeError):
        def __init__(self, message: str, *, metrics: Optional[dict[str, Any]] = None):
            super().__init__(message)
            self.metrics = dict(metrics or {})
else:
    StrategyLLMRequestError = _PublicStrategyLLMRequestError


class StrategyLLMProviderCompatibilityError(ValueError):
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
    stage_retry_count: int = 1
    stage_retry_backoff_sec: float = 1.5
    initial_compact_level: int = 0
    recent_timeout_minimal_streak: int = 1
    recent_timeout_cooldown_sec: float = 600.0
    recent_overload_minimal_streak: int = 1
    recent_overload_cooldown_sec: float = 90.0
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
        recent_overload_minimal_streak = max(1, min(8, int(os.getenv("STRATEGY_LLM_RECENT_OVERLOAD_MINIMAL_STREAK", "1") or 1)))
        recent_overload_cooldown_sec = max(0.0, float(os.getenv("STRATEGY_LLM_RECENT_OVERLOAD_COOLDOWN_SEC", "90") or 90))
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
            stage_retry_count=max(0, int(os.getenv("STRATEGY_LLM_STAGE_RETRY_COUNT", "1") or 1)),
            stage_retry_backoff_sec=max(
                0.0,
                float(
                    os.getenv(
                        "STRATEGY_LLM_STAGE_RETRY_BACKOFF_SEC",
                        os.getenv("STRATEGY_LLM_RETRY_BACKOFF_SEC", "1.5"),
                    )
                    or 1.5
                ),
            ),
            initial_compact_level=initial_compact_level,
            recent_timeout_minimal_streak=recent_timeout_minimal_streak,
            recent_timeout_cooldown_sec=recent_timeout_cooldown_sec,
            recent_overload_minimal_streak=recent_overload_minimal_streak,
            recent_overload_cooldown_sec=recent_overload_cooldown_sec,
            max_concurrency=max(1, min(16, int(os.getenv("STRATEGY_LLM_MAX_CONCURRENCY", "3") or 3))),
            strict=str(os.getenv("STRATEGY_LLM_STRICT_MODE", "")).strip().lower() in {"1", "true", "yes", "on"},
        )


class _StrategyLLMProviderRuntimeMixin:
        @staticmethod
        def _runtime_client_is_customized(client: Any) -> bool:
            if client is None:
                return False
            if not isinstance(client, httpx.AsyncClient):
                return True
            client_dict = getattr(client, "__dict__", {}) or {}
            return "post" in client_dict or "stream" in client_dict

        async def _ensure_runtime_async_state(self) -> None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            loop_id = id(loop)
            if getattr(self, "_runtime_loop_id", None) == loop_id:
                return
            client = getattr(self, "_client", None)
            client_is_customized = self._runtime_client_is_customized(client)
            if client is not None and not client_is_customized:
                try:
                    await client.aclose()
                except Exception:
                    pass
            self._request_semaphore = asyncio.Semaphore(max(1, int(self.config.max_concurrency or 1)))
            if client is None or not client_is_customized:
                self._client = httpx.AsyncClient(follow_redirects=True, http2=False)
            self._runtime_loop_id = loop_id

        def _timeout_for_attempt(self, attempt: int, total_attempts: int) -> float:
            base = max(float(self.config.timeout_sec or 0), 5.0)
            if total_attempts <= 1:
                return base
            if total_attempts == 2:
                schedule = [
                    min(base, max(12.0, round(base * 0.6, 4))),
                    base,
                ]
            else:
                schedule = [
                    min(base, max(12.0, round(base * 0.5, 4))),
                    min(base, max(20.0, round(base * 0.75, 4))),
                    base,
                ]
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
            minimum_limit = 2 if requested_limit >= 2 else 1
            return max(minimum_limit, requested_limit - base_reduction - max(0, attempt - 1))

        @staticmethod
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

        @staticmethod
        def _is_timeout_like_error(exc: Exception) -> bool:
            return isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError))

        @staticmethod
        def _is_connectivity_error(exc: Exception) -> bool:
            return isinstance(exc, httpx.ConnectError)

        @staticmethod
        def _status_code_from_error(exc: Exception) -> Optional[int]:
            try:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                return int(status_code) if status_code is not None else None
            except Exception:
                return None

        @staticmethod
        def _is_overload_status_code(status_code: Optional[int]) -> bool:
            return int(status_code or 0) in {429, 502, 503, 504, 529}

        def _is_overload_like_error(self, exc: Exception) -> bool:
            return self._is_overload_status_code(self._status_code_from_error(exc))

        def _failure_type(self, exc: Exception) -> str:
            status_code = self._status_code_from_error(exc)
            return f"HTTP{status_code}" if status_code else exc.__class__.__name__

        @staticmethod
        def _retry_after_seconds(exc: Exception) -> Optional[float]:
            response = getattr(exc, "response", None)
            headers = getattr(response, "headers", None)
            if headers is None:
                return None
            raw = headers.get("Retry-After") or headers.get("retry-after")
            if raw in (None, ""):
                return None
            try:
                return max(0.0, float(raw))
            except Exception:
                return None

        def _retry_backoff_delay(self, attempt: int, exc: Exception, *, base_delay: float, max_delay: float = 15.0) -> float:
            retry_after = self._retry_after_seconds(exc)
            if retry_after is not None:
                return min(max(retry_after, base_delay), max_delay)
            multiplier = 2.0 if self._is_overload_like_error(exc) else (1.5 if self._is_timeout_like_error(exc) else 1.0)
            delay = max(0.0, float(base_delay or 0.0)) * max(1.0, multiplier * (2 ** max(int(attempt) - 1, 0)))
            return min(delay, max_delay)

        def _should_retry_request_error(self, exc: Exception) -> bool:
            return self._is_timeout_like_error(exc) or self._is_overload_like_error(exc)

        def _active_compatibility_failure(self) -> Optional[dict[str, Any]]:
            now = time.monotonic()
            cooldown_until = float(getattr(self, "_compatibility_cooldown_until", 0.0) or 0.0)
            metrics = dict(getattr(self, "_last_compatibility_failure_metrics", {}) or {})
            if not metrics:
                return None
            if cooldown_until > 0 and cooldown_until <= now:
                self._compatibility_cooldown_until = 0.0
                self._last_compatibility_failure_metrics = {}
                return None
            if cooldown_until > 0:
                metrics["compatibility_cooldown_sec"] = round(max(cooldown_until - now, 0.0), 4)
            return metrics

        def _active_connectivity_failure(self) -> Optional[dict[str, Any]]:
            now = time.monotonic()
            cooldown_until = float(getattr(self, "_recent_connectivity_cooldown_until", 0.0) or 0.0)
            minimal_streak = max(1, int(getattr(self.config, "recent_connectivity_minimal_streak", 1) or 1))
            streak = int(getattr(self, "_recent_connectivity_streak", 0) or 0)
            if cooldown_until > 0 and cooldown_until <= now:
                self._recent_connectivity_streak = 0
                self._recent_connectivity_cooldown_until = 0.0
                return None
            if streak < minimal_streak or cooldown_until <= 0:
                return None
            return {
                "cooldown_reason": "recent_connectivity",
                "recent_connectivity_streak": streak,
                "recent_connectivity_cooldown_sec": round(max(cooldown_until - now, 0.0), 4),
                "last_error_type": self._last_failure_type or "ConnectError",
                "last_error_status_code": self._last_failure_status_code,
            }

        def _response_structure_metrics(
            self,
            payload: Any,
            *,
            response: Optional[httpx.Response],
        ) -> dict[str, Any]:
            body = dict(payload or {}) if isinstance(payload, dict) else {}
            choices = list(body.get("choices") or [])
            first_choice = dict(choices[0] or {}) if choices else {}
            message = dict(first_choice.get("message") or {})
            usage = dict(body.get("usage") or {})
            try:
                raw_preview = json.dumps(body, ensure_ascii=False, default=str)[:400]
            except Exception:
                raw_preview = str(body)[:400]
            return {
                "response_content_type": str((getattr(response, "headers", {}) or {}).get("content-type") or ""),
                "response_keys": sorted(str(key) for key in list(body.keys())[:20]),
                "choice_keys": sorted(str(key) for key in list(first_choice.keys())[:20]),
                "message_keys": sorted(str(key) for key in list(message.keys())[:20]),
                "finish_reason": first_choice.get("finish_reason"),
                "completion_tokens": usage.get("completion_tokens"),
                "raw_response_preview": raw_preview,
            }

        @staticmethod
        def _is_empty_200_compatibility_metrics(metrics: Optional[dict[str, Any]]) -> bool:
            payload = dict(metrics or {})
            error_text = str(payload.get("last_error") or "").strip().lower()
            return bool(payload.get("empty_200_response")) or "missing extractable content" in error_text

        @staticmethod
        def _has_direct_json_payload(payload: Any) -> bool:
            if isinstance(payload, list):
                return True
            if not isinstance(payload, dict):
                return False
            return "choices" not in payload and "output" not in payload

        @classmethod
        def _append_text_fragments(cls, fragments: list[str], value: Any) -> None:
            if value is None:
                return
            if isinstance(value, str):
                fragments.append(value)
                return
            if isinstance(value, list):
                for item in value:
                    cls._append_text_fragments(fragments, item)
                return
            if isinstance(value, dict):
                if isinstance(value.get("text"), str):
                    fragments.append(str(value.get("text") or ""))
                elif "text" in value:
                    cls._append_text_fragments(fragments, value.get("text"))
                if isinstance(value.get("delta"), str):
                    fragments.append(str(value.get("delta") or ""))
                elif "delta" in value:
                    cls._append_text_fragments(fragments, value.get("delta"))
                if "content" in value:
                    cls._append_text_fragments(fragments, value.get("content"))
                if "output_text" in value:
                    cls._append_text_fragments(fragments, value.get("output_text"))

        @classmethod
        def _extract_stream_event_text(cls, payload: Any, *, event_name: str = "") -> str:
            fragments: list[str] = []
            if not isinstance(payload, dict):
                return ""

            for choice in list(payload.get("choices") or []):
                if not isinstance(choice, dict):
                    continue
                cls._append_text_fragments(fragments, choice.get("delta"))
                cls._append_text_fragments(fragments, choice.get("message"))

            payload_type = str(payload.get("type") or event_name or "").strip().lower()
            if payload_type.endswith("output_text.delta"):
                cls._append_text_fragments(fragments, payload.get("delta"))
            if payload_type.endswith("output_text.done"):
                cls._append_text_fragments(fragments, payload.get("text"))

            cls._append_text_fragments(fragments, payload.get("item"))
            cls._append_text_fragments(fragments, payload.get("response"))
            return "".join(fragments)

        @staticmethod
        def _parse_sse_events(raw_text: str) -> list[dict[str, Any]]:
            events: list[dict[str, Any]] = []
            current_event: Optional[str] = None
            current_data_lines: list[str] = []

            def _flush() -> None:
                nonlocal current_event, current_data_lines
                if current_event is None and not current_data_lines:
                    return
                data_raw = "\n".join(current_data_lines).strip()
                record: dict[str, Any] = {
                    "event": current_event,
                    "data_raw": data_raw,
                }
                if data_raw == "[DONE]":
                    record["done"] = True
                elif data_raw:
                    try:
                        record["payload"] = json.loads(data_raw)
                    except Exception:
                        record["payload"] = None
                events.append(record)
                current_event = None
                current_data_lines = []

            for raw_line in str(raw_text or "").splitlines():
                line = raw_line.rstrip("\r")
                if not line.strip():
                    _flush()
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    current_event = line[len("event:") :].strip() or None
                    continue
                if line.startswith("data:"):
                    current_data_lines.append(line[len("data:") :].strip())
                    continue
            _flush()
            return events

        def _should_retry_with_stream(self, exc: StrategyLLMProviderCompatibilityError) -> bool:
            metrics = dict(getattr(exc, "metrics", {}) or {})
            content_type = str(metrics.get("response_content_type") or "").strip().lower()
            error_text = self._error_text(exc).lower()
            if "missing extractable content" in error_text:
                return True
            if "text/event-stream" not in content_type:
                return False
            return False

        def _should_retry_without_response_format(
            self,
            exc: StrategyLLMProviderCompatibilityError,
            *,
            request_payload: Optional[dict[str, Any]],
        ) -> bool:
            if not isinstance(request_payload, dict):
                return False
            if "response_format" not in request_payload:
                return False
            metrics = dict(getattr(exc, "metrics", {}) or {})
            content_type = str(metrics.get("response_content_type") or "").strip().lower()
            if "application/json" not in content_type:
                return False
            return self._is_empty_200_compatibility_metrics(
                {
                    **metrics,
                    "last_error": metrics.get("last_error") or self._error_text(exc),
                }
            )

        async def _stream_parse_response_payload(
            self,
            *,
            headers: dict[str, Any],
            request_payload: dict[str, Any],
            request_kind: str,
            timeout: httpx.Timeout,
        ) -> tuple[Any, Any, str]:
            await self._ensure_runtime_async_state()
            stream_method = getattr(self._client, "stream", None)
            if not callable(stream_method):
                self._raise_compatibility_error(
                    f"{request_kind}: stream fallback unavailable for event-stream compatibility replay",
                    response=None,
                    payload=None,
                    empty_200_response=True,
                    extra_metrics={
                        "response_content_type": "text/event-stream",
                        "stream_fallback_unavailable": True,
                    },
                )

            stream_payload = dict(request_payload or {})
            stream_payload["stream"] = True
            raw_chunks: list[str] = []
            async with self._client.stream(
                "POST",
                self._endpoint(),
                headers={**headers, "Accept": "text/event-stream, application/json"},
                json=stream_payload,
                timeout=timeout,
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_text():
                    if chunk:
                        raw_chunks.append(str(chunk))
            raw_text = "".join(raw_chunks)
            events = self._parse_sse_events(raw_text)
            content_parts: list[str] = []
            last_payload: dict[str, Any] = {}
            for event in events:
                payload = event.get("payload")
                if isinstance(payload, dict):
                    last_payload = payload
                    text = self._extract_stream_event_text(payload, event_name=str(event.get("event") or ""))
                    if text:
                        content_parts.append(text)
            content = "".join(content_parts)
            if not str(content or "").strip():
                self._raise_missing_content_error(
                    request_kind=f"{request_kind}: stream replay",
                    payload=last_payload or None,
                    response=response,
                )
            parsed_text = self._extract_json_text(content)
            if not str(parsed_text or "").strip():
                self._raise_compatibility_error(
                    f"{request_kind}: stream replay content missing JSON payload",
                    response=response,
                    payload=last_payload or None,
                    raw_text_preview=raw_text,
                    content_preview=content,
                )
            try:
                parsed = json.loads(parsed_text)
            except Exception as exc:
                self._raise_compatibility_error(
                    f"{request_kind}: stream replay content is not valid JSON ({self._error_text(exc)})",
                    response=response,
                    payload=last_payload or None,
                    raw_text_preview=raw_text,
                    content_preview=content,
                )

            synthetic_body = {
                "id": last_payload.get("id") if isinstance(last_payload, dict) else None,
                "object": last_payload.get("object") if isinstance(last_payload, dict) else None,
                "model": last_payload.get("model") if isinstance(last_payload, dict) else None,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": content,
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": last_payload.get("usage") if isinstance(last_payload, dict) else None,
                "compatibility_mode": "chat_stream_replay",
            }
            return parsed, synthetic_body, content

        def _parse_response_payload(
            self,
            response: httpx.Response,
            *,
            request_kind: str,
        ) -> tuple[Any, Any, str]:
            try:
                raw_text = str(getattr(response, "text", "") or "")
            except Exception:
                raw_text = ""
            try:
                body = response.json()
            except Exception as exc:
                empty_200_response = int(getattr(response, "status_code", 0) or 0) == 200 and not raw_text.strip()
                self._raise_compatibility_error(
                    f"{request_kind}: response body is not valid JSON ({self._error_text(exc)})",
                    response=response,
                    payload={},
                    raw_text_preview=raw_text,
                    empty_200_response=empty_200_response,
                )
            if self._has_direct_json_payload(body):
                return body, body, ""
            content = self._extract_content(body if isinstance(body, dict) else {})
            if not str(content or "").strip():
                self._raise_missing_content_error(
                    request_kind=request_kind,
                    payload=body,
                    response=response,
                )
            parsed_text = self._extract_json_text(content)
            if not str(parsed_text or "").strip():
                self._raise_compatibility_error(
                    f"{request_kind}: response content missing JSON payload",
                    response=response,
                    payload=body,
                    raw_text_preview=raw_text,
                    content_preview=content,
                )
            try:
                parsed = json.loads(parsed_text)
            except Exception as exc:
                self._raise_compatibility_error(
                    f"{request_kind}: response content is not valid JSON ({self._error_text(exc)})",
                    response=response,
                    payload=body,
                    raw_text_preview=raw_text,
                    content_preview=content,
                )
            return parsed, body, content

        async def _request_and_parse_payload(
            self,
            *,
            headers: dict[str, Any],
            request_payload: dict[str, Any],
            request_kind: str,
            timeout: httpx.Timeout,
            allow_response_format_replay: bool = True,
        ) -> tuple[Any, Any, str, str]:
            await self._ensure_runtime_async_state()
            response = await self._client.post(
                self._endpoint(),
                headers=headers,
                json=request_payload,
                timeout=timeout,
            )
            response.raise_for_status()
            try:
                parsed, body, content = self._parse_response_payload(
                    response,
                    request_kind=request_kind,
                )
                return parsed, body, content, "direct"
            except StrategyLLMProviderCompatibilityError as exc:
                if self._should_retry_with_stream(exc):
                    try:
                        parsed, body, content = await self._stream_parse_response_payload(
                            headers=headers,
                            request_payload=request_payload,
                            request_kind=request_kind,
                            timeout=timeout,
                        )
                        return parsed, body, content, "chat_stream_replay"
                    except StrategyLLMProviderCompatibilityError:
                        pass
                if allow_response_format_replay and self._should_retry_without_response_format(
                    exc,
                    request_payload=request_payload,
                ):
                    replay_payload = dict(request_payload or {})
                    replay_payload.pop("response_format", None)
                    parsed, body, content, inner_mode = await self._request_and_parse_payload(
                        headers=headers,
                        request_payload=replay_payload,
                        request_kind=f"{request_kind}: no-response-format replay",
                        timeout=timeout,
                        allow_response_format_replay=False,
                    )
                    replay_mode = (
                        "chat_no_response_format_replay"
                        if inner_mode == "direct"
                        else f"chat_no_response_format_{inner_mode}"
                    )
                    if isinstance(body, dict):
                        body = {
                            **body,
                            "compatibility_mode": replay_mode,
                        }
                    return parsed, body, content, replay_mode
                raise

        def _append_recent_request_outcome(
            self,
            *,
            status: str,
            compatibility_failed: bool = False,
            empty_200_response: bool = False,
        ) -> None:
            from collections import deque

            outcomes = getattr(self, "_recent_request_outcomes", None)
            if not isinstance(outcomes, deque):
                outcomes = deque(maxlen=12)
                self._recent_request_outcomes = outcomes
            outcomes.append(
                {
                    "status": str(status or "").strip().lower() or "unknown",
                    "compatibility_failed": bool(compatibility_failed),
                    "empty_200_response": bool(empty_200_response),
                }
            )

        def get_health_snapshot(self) -> dict[str, Any]:
            active_compatibility = self._active_compatibility_failure()
            outcomes = list(getattr(self, "_recent_request_outcomes", []) or [])
            recent_request_count = len(outcomes)
            compatibility_failure_count = sum(
                1 for item in outcomes if bool(dict(item or {}).get("compatibility_failed"))
            )
            effective_response_count = sum(
                1 for item in outcomes if str(dict(item or {}).get("status") or "").strip().lower() == "succeeded"
            )
            empty_200_response_count = sum(
                1 for item in outcomes if bool(dict(item or {}).get("empty_200_response"))
            )
            compatibility_failure_ratio = (
                round(compatibility_failure_count / recent_request_count, 4) if recent_request_count else 0.0
            )
            effective_response_ratio = (
                round(effective_response_count / recent_request_count, 4) if recent_request_count else 0.0
            )
            scheduler_should_disable = False
            scheduler_skip_reason = None
            connectivity_failure = self._active_connectivity_failure()
            if connectivity_failure is not None:
                scheduler_should_disable = True
                scheduler_skip_reason = "connectivity_cooldown_active"
            elif active_compatibility is not None:
                scheduler_should_disable = True
                scheduler_skip_reason = "compatibility_cooldown_active"
            elif recent_request_count >= 2 and compatibility_failure_ratio >= 0.5:
                scheduler_should_disable = True
                scheduler_skip_reason = "compatibility_failure_ratio_high"
            elif empty_200_response_count > 0 and effective_response_ratio < 0.34:
                scheduler_should_disable = True
                scheduler_skip_reason = "empty_200_false_success_detected"
            if scheduler_should_disable:
                health_status = "blocked"
            elif recent_request_count <= 0 and active_compatibility is None and not self._last_failure_type:
                health_status = "unknown"
            elif compatibility_failure_count > 0 or effective_response_ratio < 1.0:
                health_status = "degraded"
            else:
                health_status = "healthy"
            return {
                "health_status": health_status,
                "recent_request_count": recent_request_count,
                "compatibility_failure_count": compatibility_failure_count,
                "effective_response_count": effective_response_count,
                "empty_200_response_count": empty_200_response_count,
                "compatibility_failure_ratio": compatibility_failure_ratio,
                "effective_response_ratio": effective_response_ratio,
                "connectivity_cooldown_active": connectivity_failure is not None,
                "connectivity_cooldown_sec": (
                    connectivity_failure.get("recent_connectivity_cooldown_sec") if connectivity_failure else 0.0
                ),
                "recent_connectivity_streak": (
                    connectivity_failure.get("recent_connectivity_streak")
                    if connectivity_failure
                    else int(getattr(self, "_recent_connectivity_streak", 0) or 0)
                ),
                "compatibility_cooldown_active": active_compatibility is not None,
                "compatibility_cooldown_sec": (
                    active_compatibility.get("compatibility_cooldown_sec") if active_compatibility else 0.0
                ),
                "scheduler_should_disable": scheduler_should_disable,
                "scheduler_skip_reason": scheduler_skip_reason,
                "last_error_type": self._last_failure_type,
                "last_error_status_code": self._last_failure_status_code,
            }

        def _raise_compatibility_error(
            self,
            message: str,
            *,
            response: Optional[httpx.Response],
            payload: Any = None,
            raw_text_preview: str = "",
            content_preview: str = "",
            empty_200_response: bool = False,
            extra_metrics: Optional[dict[str, Any]] = None,
        ) -> None:
            metrics = self._response_structure_metrics(payload, response=response)
            if raw_text_preview:
                metrics["raw_text_preview"] = str(raw_text_preview)[:400]
            if content_preview:
                metrics["content_preview"] = str(content_preview)[:400]
            if extra_metrics:
                metrics.update(dict(extra_metrics or {}))
            raise StrategyLLMProviderCompatibilityError(
                message,
                metrics={
                    "status": "compatibility_failed",
                    "last_error_type": "ProviderCompatibilityError",
                    "last_error_status_code": getattr(response, "status_code", None),
                    "empty_200_response": bool(empty_200_response),
                    **metrics,
                },
            )

        def _raise_missing_content_error(
            self,
            *,
            request_kind: str,
            payload: Any,
            response: Optional[httpx.Response],
        ) -> None:
            metrics = self._response_structure_metrics(payload, response=response)
            content_type = str(metrics.get("response_content_type") or "unknown")
            choice_keys = metrics.get("choice_keys") or []
            message_keys = metrics.get("message_keys") or []
            self._raise_compatibility_error(
                f"{request_kind}: response missing extractable content "
                f"(content-type={content_type}, choice_keys={choice_keys}, message_keys={message_keys})",
                response=response,
                payload=payload,
                empty_200_response=True,
            )

        def _recent_failure_degrade_state(self) -> tuple[int, Optional[str]]:
            initial_level = max(0, min(int(self.config.initial_compact_level or 0), 2))
            now = time.monotonic()
            if self._recent_timeout_cooldown_until > 0 and self._recent_timeout_cooldown_until <= now:
                self._recent_timeout_streak = 0
                self._recent_timeout_cooldown_until = 0.0
            if getattr(self, "_recent_overload_cooldown_until", 0.0) > 0 and self._recent_overload_cooldown_until <= now:
                self._recent_overload_streak = 0
                self._recent_overload_cooldown_until = 0.0
            if self._recent_timeout_streak >= max(1, int(self.config.recent_timeout_minimal_streak or 1)) and self._recent_timeout_cooldown_until > now:
                return max(initial_level, 2), 'recent_timeout'
            if getattr(self, "_recent_overload_streak", 0) >= max(1, int(getattr(self.config, "recent_overload_minimal_streak", 1) or 1)) and getattr(self, "_recent_overload_cooldown_until", 0.0) > now:
                return max(initial_level, 2), 'recent_overload'
            return initial_level, None

        def _record_request_failure(self, exc: Exception) -> None:
            self._last_failure_type = self._failure_type(exc)
            self._last_failure_status_code = self._status_code_from_error(exc)
            self._append_recent_request_outcome(status="failed")
            if self._is_connectivity_error(exc):
                self._recent_connectivity_streak = int(getattr(self, "_recent_connectivity_streak", 0) or 0) + 1
                self._recent_connectivity_cooldown_until = time.monotonic() + max(
                    0.0,
                    float(getattr(self.config, "recent_connectivity_cooldown_sec", 600.0) or 0.0),
                )
                self._recent_timeout_streak += 1
                self._recent_timeout_cooldown_until = time.monotonic() + max(0.0, float(self.config.recent_timeout_cooldown_sec or 0.0))
            elif self._is_timeout_like_error(exc):
                self._recent_timeout_streak += 1
                self._recent_timeout_cooldown_until = time.monotonic() + max(0.0, float(self.config.recent_timeout_cooldown_sec or 0.0))
            elif self._is_overload_like_error(exc):
                self._recent_overload_streak = int(getattr(self, "_recent_overload_streak", 0) or 0) + 1
                retry_after = self._retry_after_seconds(exc)
                cooldown_sec = max(
                    float(getattr(self.config, "recent_overload_cooldown_sec", 90.0) or 0.0),
                    float(retry_after or 0.0),
                )
                self._recent_overload_cooldown_until = time.monotonic() + max(0.0, cooldown_sec)

        def _record_compatibility_failure(self, exc: Exception) -> None:
            metrics = dict(getattr(exc, "metrics", {}) or {})
            self._last_failure_type = str(metrics.get("last_error_type") or exc.__class__.__name__)
            self._last_failure_status_code = self._status_code_from_error(exc)
            empty_200_response = self._is_empty_200_compatibility_metrics(
                {
                    **metrics,
                    "last_error": metrics.get("last_error") or self._error_text(exc),
                    "empty_200_response": metrics.get("empty_200_response"),
                }
            )
            self._last_compatibility_failure_metrics = {
                "status": "compatibility_failed",
                "last_error_type": self._last_failure_type,
                "last_error": self._error_text(exc),
                "empty_200_response": empty_200_response,
                **metrics,
            }
            self._append_recent_request_outcome(
                status="compatibility_failed",
                compatibility_failed=True,
                empty_200_response=empty_200_response,
            )
            cooldown_sec = max(0.0, float(getattr(self.config, "compatibility_cooldown_sec", 300.0) or 300.0))
            self._compatibility_cooldown_until = time.monotonic() + cooldown_sec if cooldown_sec > 0 else 0.0

        def _record_request_success(self) -> None:
            self._recent_timeout_streak = 0
            self._recent_timeout_cooldown_until = 0.0
            self._recent_connectivity_streak = 0
            self._recent_connectivity_cooldown_until = 0.0
            self._recent_overload_streak = 0
            self._recent_overload_cooldown_until = 0.0
            self._last_failure_type = None
            self._last_failure_status_code = None
            self._compatibility_cooldown_until = 0.0
            self._last_compatibility_failure_metrics = {}
            self._append_recent_request_outcome(status="succeeded")

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
            await self._ensure_runtime_async_state()

            started_at = time.perf_counter()
            compatibility_metrics = self._active_compatibility_failure()
            if compatibility_metrics is not None:
                raise StrategyLLMRequestError(
                    "external llm request skipped during compatibility cooldown",
                    metrics={
                        "endpoint": self._endpoint(),
                        "provider": self.config.provider,
                        "model": self.config.model,
                        "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                        **compatibility_metrics,
                        "status": "compatibility_skip",
                    },
                )
            connectivity_metrics = self._active_connectivity_failure()
            if connectivity_metrics is not None:
                raise StrategyLLMRequestError(
                    "external llm request skipped during connectivity cooldown",
                    metrics={
                        "endpoint": self._endpoint(),
                        "provider": self.config.provider,
                        "model": self.config.model,
                        "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                        **connectivity_metrics,
                        "status": "cooldown_skip",
                    },
                )
            requested_limit = self._normalize_limit(limit)
            market_summary = self._summarize_market_frame(market_frame)
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            last_exc: Optional[Exception] = None
            attempts = max(1, int(self.config.retry_count or 0) + 1)
            attempt_reports: list[dict[str, Any]] = []
            initial_compact_level, degrade_reason = self._recent_failure_degrade_state()
            initial_prompt_profile = self._prompt_profile_name(initial_compact_level)
            effective_attempts = 1 if degrade_reason in {'recent_timeout', 'recent_overload'} else attempts
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
                if degrade_reason in {'recent_timeout', 'recent_overload'} and attempt == 1:
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
                        data, body, content, compatibility_mode = await self._request_and_parse_payload(
                            headers=headers,
                            request_payload=payload,
                            request_kind="generate_candidates",
                            timeout=self._request_timeout(request_timeout_sec),
                        )
                    raw_candidates = data.get("candidates") if isinstance(data, dict) else None
                    if not isinstance(raw_candidates, list):
                        raise ValueError("external llm response missing candidates")
                    analysis = self._normalize_analysis(data.get("analysis") if isinstance(data, dict) else {})
                    candidates = []
                    for item in raw_candidates:
                        normalized_candidate = self._normalize_candidate_payload(
                            item,
                            research_task=research_task,
                            allow_legacy_contract_defaults=True,
                        )
                        if normalized_candidate is not None:
                            candidates.append(normalized_candidate)
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
                        "non_executable_candidate_count": max(0, len(raw_candidates) - len(candidates)),
                        "analysis_present": bool(analysis),
                        "analysis_keys": sorted(list(analysis.keys())),
                        "compatibility_mode": compatibility_mode,
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
                            "non_executable_candidate_count": max(0, len(raw_candidates) - len(candidates)),
                            "analysis_present": bool(analysis),
                            "compatibility_mode": compatibility_mode,
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
                        "raw_candidates": [dict(item or {}) for item in raw_candidates],
                        "raw_response": body,
                        "content": content,
                        "analysis": analysis,
                        "research_context": compact_research_context,
                        "research_task": dict(research_task or {}),
                        "candidates": selected_candidates,
                        "compatibility_mode": compatibility_mode,
                        "request_metrics": request_metrics,
                    }
                except StrategyLLMProviderCompatibilityError as exc:
                    last_exc = exc
                    attempt_reports.append({
                        "attempt": attempt,
                        "status": "compatibility_failed",
                        "request_limit": request_limit,
                        "timeout_sec": request_timeout_sec,
                        "prompt_profile": prompt_profile,
                        "prompt_chars": len(system_prompt) + len(user_prompt),
                        "max_tokens": max_tokens,
                        "degrade_reason": degrade_reason,
                        "initial_prompt_profile": initial_prompt_profile,
                        "elapsed_seconds": round(time.perf_counter() - request_started_at, 4),
                        "error_type": str(dict(getattr(exc, "metrics", {}) or {}).get("last_error_type") or "ProviderCompatibilityError"),
                        "error": self._error_text(exc),
                        "status_code": self._status_code_from_error(exc),
                        **dict(getattr(exc, "metrics", {}) or {}),
                    })
                    break
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
                        "error_type": self._failure_type(exc),
                        "error": self._error_text(exc),
                        "status_code": self._status_code_from_error(exc),
                        "retry_after_sec": self._retry_after_seconds(exc),
                    })
                    if attempt >= attempts or not self._should_retry_request_error(exc):
                        break
                    await asyncio.sleep(
                        self._retry_backoff_delay(
                            attempt,
                            exc,
                            base_delay=float(self.config.retry_backoff_sec or 0.0),
                        )
                    )

            if last_exc is not None:
                if isinstance(last_exc, StrategyLLMProviderCompatibilityError):
                    self._record_compatibility_failure(last_exc)
                else:
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
                "recent_overload_streak": int(getattr(self, "_recent_overload_streak", 0) or 0),
                "recent_overload_cooldown_sec": round(max(getattr(self, "_recent_overload_cooldown_until", 0.0) - time.monotonic(), 0.0), 4),
                "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                "attempt_count": len(attempt_reports),
                "attempts": attempt_reports,
                "last_error_type": self._failure_type(last_exc) if last_exc else "RuntimeError",
                "last_error_status_code": self._status_code_from_error(last_exc) if last_exc else None,
                "last_error": self._error_text(last_exc or RuntimeError("external llm request failed")),
            }
            if isinstance(last_exc, StrategyLLMProviderCompatibilityError):
                metrics.update(dict(getattr(last_exc, "metrics", {}) or {}))
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
            await self._ensure_runtime_async_state()

            started_at = time.perf_counter()
            stage_timeout = float(timeout_sec or 10.0)
            compatibility_metrics = self._active_compatibility_failure()
            if compatibility_metrics is not None:
                raise StrategyLLMRequestError(
                    f"call_stage({stage_id}) skipped during compatibility cooldown",
                    metrics={
                        "stage_id": stage_id,
                        "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                        **compatibility_metrics,
                        "status": "compatibility_skip",
                    },
                )
            connectivity_metrics = self._active_connectivity_failure()
            if connectivity_metrics is not None:
                raise StrategyLLMRequestError(
                    f"call_stage({stage_id}) skipped during connectivity cooldown",
                    metrics={
                        "stage_id": stage_id,
                        "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                        **connectivity_metrics,
                        "status": "cooldown_skip",
                    },
                )
            _compact_level, degrade_reason = self._recent_failure_degrade_state()
            if degrade_reason in {'recent_timeout', 'recent_overload'}:
                is_overload = degrade_reason == 'recent_overload'
                raise StrategyLLMRequestError(
                    f"call_stage({stage_id}) skipped during {'overload' if is_overload else 'timeout'} cooldown",
                    metrics={
                        "stage_id": stage_id,
                        "status": "cooldown_skip",
                        "cooldown_reason": degrade_reason,
                        "last_error_type": "RecentOverloadCooldown" if is_overload else "RecentTimeoutCooldown",
                        "recent_timeout_streak": self._recent_timeout_streak,
                        "recent_timeout_cooldown_sec": round(
                            max(self._recent_timeout_cooldown_until - time.monotonic(), 0.0),
                            4,
                        ),
                        "recent_overload_streak": int(getattr(self, "_recent_overload_streak", 0) or 0),
                        "recent_overload_cooldown_sec": round(
                            max(getattr(self, "_recent_overload_cooldown_until", 0.0) - time.monotonic(), 0.0),
                            4,
                        ),
                        "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                    },
                )
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
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
            attempts = max(1, int(getattr(self.config, "stage_retry_count", 1) or 0) + 1)
            attempt_reports: list[dict[str, Any]] = []

            client = self._client
            for attempt in range(1, attempts + 1):
                request_started_at = time.perf_counter()
                try:
                    async with self._request_semaphore:
                        data, _body, _content, _compatibility_mode = await self._request_and_parse_payload(
                            headers=headers,
                            request_payload=payload,
                            request_kind=f"call_stage({stage_id})",
                            timeout=self._request_timeout(stage_timeout),
                        )
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
                except StrategyLLMProviderCompatibilityError as exc:
                    last_exc = exc
                    attempt_reports.append({
                        "attempt": attempt,
                        "status": "compatibility_failed",
                        "elapsed_seconds": round(time.perf_counter() - request_started_at, 4),
                        "error_type": str(dict(getattr(exc, "metrics", {}) or {}).get("last_error_type") or "ProviderCompatibilityError"),
                        "error": self._error_text(exc),
                        "status_code": self._status_code_from_error(exc),
                        **dict(getattr(exc, "metrics", {}) or {}),
                    })
                    break
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
                        "elapsed_seconds": round(time.perf_counter() - request_started_at, 4),
                        "error_type": self._failure_type(exc),
                        "error": self._error_text(exc),
                        "status_code": self._status_code_from_error(exc),
                        "retry_after_sec": self._retry_after_seconds(exc),
                    })
                    if attempt >= attempts or not self._should_retry_request_error(exc):
                        break
                    await asyncio.sleep(
                        self._retry_backoff_delay(
                            attempt,
                            exc,
                            base_delay=float(getattr(self.config, "stage_retry_backoff_sec", self.config.retry_backoff_sec) or 0.0),
                        )
                    )

            if last_exc is not None:
                if isinstance(last_exc, StrategyLLMProviderCompatibilityError):
                    self._record_compatibility_failure(last_exc)
                else:
                    self._record_request_failure(last_exc)
            raise StrategyLLMRequestError(
                f"call_stage({stage_id}) failed after {len(attempt_reports)} attempts: {self._error_text(last_exc or RuntimeError('unknown'))}",
                metrics={
                    "stage_id": stage_id,
                    "status": "failed",
                    "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                    "attempt_count": len(attempt_reports),
                    "attempts": attempt_reports,
                    "last_error_type": (self._failure_type(last_exc) if last_exc else "RuntimeError"),
                    "last_error_status_code": self._status_code_from_error(last_exc) if last_exc else None,
                    "last_error": self._error_text(last_exc or RuntimeError("unknown")),
                    "recent_timeout_streak": self._recent_timeout_streak,
                    "recent_timeout_cooldown_sec": round(max(self._recent_timeout_cooldown_until - time.monotonic(), 0.0), 4),
                    "recent_overload_streak": int(getattr(self, "_recent_overload_streak", 0) or 0),
                    "recent_overload_cooldown_sec": round(max(getattr(self, "_recent_overload_cooldown_until", 0.0) - time.monotonic(), 0.0), 4),
                    **(dict(getattr(last_exc, "metrics", {}) or {}) if isinstance(last_exc, StrategyLLMProviderCompatibilityError) else {}),
                },
            ) from last_exc
