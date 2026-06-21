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
from strategy_factory.api.semantic_contract import apply_target_symbol_policy, normalize_research_task_contract

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


class StrategyLLMResponseParseError(ValueError):
    """Non-empty provider response content could not be parsed as model JSON."""


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
    recent_timeout_minimal_streak: int = 3
    recent_timeout_cooldown_sec: float = 120.0
    recent_overload_minimal_streak: int = 3
    recent_overload_cooldown_sec: float = 120.0
    # P1-E: 兼容失败冷却也用 streak 门(默认连续3次才锁),避免单次兼容失败即长锁。
    compatibility_minimal_streak: int = 3
    compatibility_cooldown_sec: float = 120.0
    max_concurrency: int = 3
    strict: bool = False

    @classmethod
    def from_env(cls) -> "StrategyLLMConfig":
        load_mcp_env(override=False, only_prefixes=('STRATEGY_LLM_',))
        enabled = str(os.getenv("STRATEGY_LLM_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"}
        timeout_sec = float(os.getenv("STRATEGY_LLM_TIMEOUT_SEC", "30") or 30)
        initial_compact_level = max(0, min(2, int(os.getenv("STRATEGY_LLM_INITIAL_COMPACT_LEVEL", "0") or 0)))
        # 冷却默认值温和化(对齐 strategy_llm_provider.py:62-63 的意图)。
        # 历史 bug:本 runtime 门面用 timeout streak=1/cooldown=600 → 单次 ReadTimeout 立即锁 10 分钟,
        # cooldown 期内所有 pipeline stage 全 skip → event 空→theme 空(empty_themes)级联→no_executable_specs
        # 全退本地 fallback。实测一次 21:50 ReadTimeout 锁到 22:03。改为 streak=3(连续3次才冷却)+
        # cooldown=120s(数轮内自然恢复),avoid 单次抖动放大成长时间全链瘫痪。
        recent_timeout_minimal_streak = max(1, min(8, int(os.getenv("STRATEGY_LLM_RECENT_TIMEOUT_MINIMAL_STREAK", "3") or 3)))
        recent_timeout_cooldown_sec = max(0.0, float(os.getenv("STRATEGY_LLM_RECENT_TIMEOUT_COOLDOWN_SEC", "120") or 120))
        recent_overload_minimal_streak = max(1, min(8, int(os.getenv("STRATEGY_LLM_RECENT_OVERLOAD_MINIMAL_STREAK", "3") or 3)))
        recent_overload_cooldown_sec = max(0.0, float(os.getenv("STRATEGY_LLM_RECENT_OVERLOAD_COOLDOWN_SEC", "120") or 120))
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
            compatibility_minimal_streak=max(1, min(8, int(os.getenv("STRATEGY_LLM_COMPATIBILITY_MINIMAL_STREAK", "3") or 3))),
            compatibility_cooldown_sec=max(0.0, float(os.getenv("STRATEGY_LLM_COMPATIBILITY_COOLDOWN_SEC", "120") or 120)),
            max_concurrency=max(1, min(16, int(os.getenv("STRATEGY_LLM_MAX_CONCURRENCY", "3") or 3))),
            strict=str(os.getenv("STRATEGY_LLM_STRICT_MODE", "")).strip().lower() in {"1", "true", "yes", "on"},
        )

from akshare_mcp._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    '_strategy_llm_provider_runtime_parts',
    'class _StrategyLLMProviderRuntimeMixin:\n        @staticmethod\n',
    ['context.py', 'specs.py', 'runtime.py'],
    future_annotations=True,
)
