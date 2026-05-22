
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationInfo, field_validator

from akshare_mcp.env_loader import load_mcp_env


class FactorLLMRequestError(RuntimeError):
    """因子研究模型请求异常。"""

    def __init__(self, message: str, *, metrics: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.metrics = dict(metrics or {})


class FactorLLMProviderCompatibilityError(ValueError):
    """Provider 返回 200 但结构不兼容时的显式异常。"""

    def __init__(self, message: str, *, metrics: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.metrics = dict(metrics or {})


@dataclass
class FactorLLMConfig:
    enabled: bool = False
    provider: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout_sec: float = 45.0
    connect_timeout_sec: float = 8.0
    write_timeout_sec: float = 10.0
    pool_timeout_sec: float = 5.0
    temperature: float = 0.2
    max_tokens: int = 1800
    retry_count: int = 2
    retry_backoff_sec: float = 1.0
    compatibility_cooldown_sec: float = 300.0
    smoke_check_enabled: bool = True
    smoke_check_ttl_sec: float = 300.0
    max_concurrency: int = 3
    strict: bool = False

    @classmethod
    def from_env(cls) -> "FactorLLMConfig":
        load_mcp_env(override=False, only_prefixes=("FACTOR_LLM_", "STRATEGY_LLM_"))

        def _env_text(name: str, *, fallback: str = "", default: str = "") -> str:
            raw = str(os.getenv(name, "") or "").strip()
            if raw:
                return raw
            if fallback:
                fallback_raw = str(os.getenv(fallback, "") or "").strip()
                if fallback_raw:
                    return fallback_raw
            return str(default or "").strip()

        def _env_bool(name: str, *, fallback: str = "", default: bool = False) -> bool:
            raw = str(os.getenv(name, "") or "").strip()
            if not raw and fallback:
                raw = str(os.getenv(fallback, "") or "").strip()
            if not raw:
                return bool(default)
            return raw.lower() in {"1", "true", "yes", "on"}

        def _env_float(name: str, *, fallback: str = "", default: float) -> float:
            raw = str(os.getenv(name, "") or "").strip()
            if not raw and fallback:
                raw = str(os.getenv(fallback, "") or "").strip()
            if not raw:
                return float(default)
            try:
                return float(raw)
            except Exception:
                return float(default)

        def _env_int(name: str, *, fallback: str = "", default: int) -> int:
            raw = str(os.getenv(name, "") or "").strip()
            if not raw and fallback:
                raw = str(os.getenv(fallback, "") or "").strip()
            if not raw:
                return int(default)
            try:
                return int(raw)
            except Exception:
                return int(default)

        enabled = _env_bool("FACTOR_LLM_ENABLED", fallback="STRATEGY_LLM_ENABLED", default=False)
        timeout_sec = _env_float("FACTOR_LLM_TIMEOUT_SEC", fallback="STRATEGY_LLM_TIMEOUT_SEC", default=45.0)
        return cls(
            enabled=enabled,
            provider=_env_text("FACTOR_LLM_PROVIDER", fallback="STRATEGY_LLM_PROVIDER", default="openai_compatible"),
            base_url=_env_text("FACTOR_LLM_BASE_URL", fallback="STRATEGY_LLM_BASE_URL"),
            api_key=_env_text("FACTOR_LLM_API_KEY", fallback="STRATEGY_LLM_API_KEY"),
            model=_env_text("FACTOR_LLM_MODEL", fallback="STRATEGY_LLM_MODEL"),
            timeout_sec=timeout_sec,
            connect_timeout_sec=_env_float(
                "FACTOR_LLM_CONNECT_TIMEOUT_SEC",
                fallback="STRATEGY_LLM_CONNECT_TIMEOUT_SEC",
                default=min(timeout_sec, 8.0),
            ),
            write_timeout_sec=_env_float(
                "FACTOR_LLM_WRITE_TIMEOUT_SEC",
                fallback="STRATEGY_LLM_WRITE_TIMEOUT_SEC",
                default=min(timeout_sec, 10.0),
            ),
            pool_timeout_sec=_env_float(
                "FACTOR_LLM_POOL_TIMEOUT_SEC",
                fallback="STRATEGY_LLM_POOL_TIMEOUT_SEC",
                default=min(timeout_sec, 5.0),
            ),
            temperature=_env_float("FACTOR_LLM_TEMPERATURE", fallback="STRATEGY_LLM_TEMPERATURE", default=0.2),
            max_tokens=max(256, _env_int("FACTOR_LLM_MAX_TOKENS", fallback="STRATEGY_LLM_MAX_TOKENS", default=1800)),
            retry_count=max(0, _env_int("FACTOR_LLM_RETRY_COUNT", fallback="STRATEGY_LLM_RETRY_COUNT", default=2)),
            retry_backoff_sec=max(
                0.0,
                _env_float("FACTOR_LLM_RETRY_BACKOFF_SEC", fallback="STRATEGY_LLM_RETRY_BACKOFF_SEC", default=1.0),
            ),
            compatibility_cooldown_sec=max(
                0.0,
                _env_float(
                    "FACTOR_LLM_COMPATIBILITY_COOLDOWN_SEC",
                    fallback="STRATEGY_LLM_COMPATIBILITY_COOLDOWN_SEC",
                    default=300.0,
                ),
            ),
            smoke_check_enabled=_env_bool(
                "FACTOR_LLM_SMOKE_CHECK_ENABLED",
                fallback="STRATEGY_LLM_SMOKE_CHECK_ENABLED",
                default=True,
            ),
            smoke_check_ttl_sec=max(
                0.0,
                _env_float(
                    "FACTOR_LLM_SMOKE_CHECK_TTL_SEC",
                    fallback="STRATEGY_LLM_SMOKE_CHECK_TTL_SEC",
                    default=300.0,
                ),
            ),
            max_concurrency=max(
                1,
                min(8, _env_int("FACTOR_LLM_MAX_CONCURRENCY", fallback="STRATEGY_LLM_MAX_CONCURRENCY", default=3)),
            ),
            strict=_env_bool("FACTOR_LLM_STRICT_MODE", fallback="STRATEGY_LLM_STRICT_MODE", default=False),
        )


class FactorCandidateModel(BaseModel):
    """结构化候选因子。"""

    model_config = ConfigDict(extra="allow")

    name: str = Field(..., min_length=2, max_length=80)
    hypothesis: str = Field(..., min_length=4, max_length=400)
    family: str = Field(default="custom", min_length=2, max_length=40)
    inputs: list[str] = Field(default_factory=list, min_length=1, max_length=24)
    expression_dsl: str = Field(..., min_length=3, max_length=600)
    expected_holding_period: int = Field(default=10, ge=1, le=252)
    expected_regime: list[str] = Field(default_factory=list, max_length=12)
    complexity_hint: str = Field(default="medium", min_length=1, max_length=20)
    novelty_rationale: str = Field(default="", max_length=400)
    generation_trace: dict[str, Any] = Field(default_factory=dict)
    source_model: str = Field(default="", max_length=120)

    @field_validator("name", "family", "hypothesis", "expression_dsl", "novelty_rationale", mode="before")
    @classmethod
    def _normalize_text(cls, value: Any, info: ValidationInfo) -> str:
        text = " ".join(str(value or "").strip().split())
        max_lengths = {
            "name": 80,
            "family": 40,
            "hypothesis": 400,
            "expression_dsl": 600,
            "novelty_rationale": 400,
        }
        max_length = max_lengths.get(str(info.field_name or ""))
        if max_length and len(text) > max_length:
            return text[:max_length].rstrip()
        return text

    @field_validator("inputs", "expected_regime", mode="before")
    @classmethod
    def _normalize_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            parts = [item.strip() for item in re.split(r"[,;\n|]+", value) if item.strip()]
            return parts
        if isinstance(value, (list, tuple, set)):
            return [" ".join(str(item or "").strip().split()) for item in value if str(item or "").strip()]
        return [" ".join(str(value).strip().split())] if str(value).strip() else []

    @field_validator("complexity_hint", mode="before")
    @classmethod
    def _normalize_complexity(cls, value: Any) -> str:
        text = str(value or "medium").strip().lower()
        if text not in {"low", "medium", "high"}:
            return "medium"
        return text

    @field_validator("expected_holding_period", mode="before")
    @classmethod
    def _normalize_expected_holding_period(cls, value: Any) -> int:
        if value is None:
            return 10
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value or "").strip().lower()
        if not text:
            return 10
        numbers = [int(item) for item in re.findall(r"\d+", text)]
        if not numbers:
            return 10
        if len(numbers) >= 2 and any(token in text for token in ("-", "to", "~", "–", "—")):
            return int(round((numbers[0] + numbers[1]) / 2))
        return int(numbers[0])


class FactorGenerationEnvelope(BaseModel):
    """候选因子生成返回结构。"""

    model_config = ConfigDict(extra="allow")

    candidates: list[FactorCandidateModel] = Field(default_factory=list, min_length=1, max_length=32)
    analysis: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("warnings", mode="before")
    @classmethod
    def _normalize_warnings(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []


_FACTOR_GENERATION_ADAPTER = TypeAdapter(FactorGenerationEnvelope)
_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "factor_candidate.schema.json"


def get_factor_candidate_schema_path() -> str:
    """返回候选因子 schema 路径。"""

    return str(_SCHEMA_PATH)


def load_factor_candidate_schema() -> dict[str, Any]:
    """读取候选因子 schema 文件。"""

    with _SCHEMA_PATH.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def factor_candidate_runtime_schema() -> dict[str, Any]:
    """返回运行时 pydantic schema。"""

    return FactorGenerationEnvelope.model_json_schema()


def validate_factor_generation_payload(
    payload: Any,
    *,
    model: str = "",
    provider: str = "",
) -> dict[str, Any]:
    """校验模型返回的候选因子结构。"""

    normalized = payload
    if isinstance(payload, list):
        normalized = {"candidates": payload}
    elif isinstance(payload, dict) and "candidates" not in payload:
        if payload.get("name") and payload.get("expression_dsl"):
            normalized = {"candidates": [payload]}
        else:
            normalized = {"candidates": payload.get("items") or []}

    envelope = _FACTOR_GENERATION_ADAPTER.validate_python(normalized)
    data = envelope.model_dump(mode="json")
    for candidate in data.get("candidates", []):
        trace = dict(candidate.get("generation_trace") or {})
        if provider and not trace.get("provider"):
            trace["provider"] = provider
        if model and not candidate.get("source_model"):
            candidate["source_model"] = model
        if model and not trace.get("model"):
            trace["model"] = model
        candidate["generation_trace"] = trace
    return data
