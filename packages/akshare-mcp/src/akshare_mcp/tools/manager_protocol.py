"""Shared manager argument normalization and response metadata helpers."""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Iterable, Optional

from ..utils import fail, normalize_code, ok

DEFAULT_CODE_KEYS = ("code", "Code", "stock_code", "symbol", "ticker")
DEFAULT_LIST_KEYS = {
    "codes": ("Codes",),
}


def _merge_json_like_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return dict(payload)
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload or "{}")
        except Exception:
            return {}
        if isinstance(parsed, dict):
            return dict(parsed)
    return {}


def normalize_manager_kwargs(
    kwargs: Optional[dict[str, Any]],
    *,
    field_aliases: Optional[dict[str, Iterable[str]]] = None,
) -> dict[str, Any]:
    normalized = dict(kwargs or {})

    for key in ("params", "kwargs"):
        normalized.update(_merge_json_like_payload(normalized.get(key)))

    aliases = dict(DEFAULT_LIST_KEYS)
    if field_aliases:
        aliases.update({k: tuple(v) for k, v in field_aliases.items()})

    for canonical, candidates in aliases.items():
        if normalized.get(canonical) not in (None, "", []):
            continue
        for alias in candidates:
            value = normalized.get(alias)
            if value not in (None, "", []):
                normalized[canonical] = value
                break

    if "code" not in normalized or normalized.get("code") in (None, ""):
        for alias in DEFAULT_CODE_KEYS:
            value = normalized.get(alias)
            if value not in (None, ""):
                normalized["code"] = value
                break

    return normalized


def normalize_manager_payload(
    *,
    params: Any = None,
    kwargs: Any = None,
    code: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Unified entry point for Manager parameter normalization.

    Merge priority (later wins): kwargs → params → extra → explicit code.

    Accepts BFF legacy calls (kwargs as JSON string) and new structured
    MCP calls (params as dict) transparently.
    """
    merged: dict[str, Any] = {}

    # 1. merge kwargs (legacy compat: may be JSON string or dict)
    merged.update(_merge_json_like_payload(kwargs))

    # 2. merge params (structured MCP input)
    merged.update(_merge_json_like_payload(params))

    # 3. merge explicit extra fields
    if extra and isinstance(extra, dict):
        merged.update(extra)

    # 4. resolve code from explicit param or merged payload
    if code and isinstance(code, str) and code.strip():
        merged["code"] = code.strip()
    elif "code" not in merged or merged.get("code") in (None, ""):
        for alias in DEFAULT_CODE_KEYS:
            value = merged.get(alias)
            if value not in (None, ""):
                merged["code"] = value
                break

    # 5. apply standard alias resolution
    for canonical, candidates in DEFAULT_LIST_KEYS.items():
        if merged.get(canonical) not in (None, "", []):
            continue
        for alias in candidates:
            value = merged.get(alias)
            if value not in (None, "", []):
                merged[canonical] = value
                break

    return merged


def normalize_manager_code(
    code: Optional[str],
    kwargs: dict[str, Any],
    *,
    normalize: bool = False,
) -> tuple[Optional[str], dict[str, Any]]:
    merged = dict(kwargs or {})
    resolved = code or merged.get("code")
    if isinstance(resolved, str):
        resolved = resolved.strip() or None
    if resolved and normalize:
        resolved = normalize_code(resolved)
    merged["code"] = resolved
    return resolved, merged


def extract_common_meta(kwargs: Optional[dict[str, Any]], *, defaults: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    merged = dict(defaults or {})
    source = dict(kwargs or {})
    for key in ("as_of", "adjust", "price_source_policy", "explain", "strict_mode"):
        if key in source:
            merged[key] = source.get(key)
    return merged


def build_manager_meta(
    *,
    tool_name: str,
    action: str,
    started_at: float,
    source_chain: Optional[Iterable[str]] = None,
    data_timestamp: Optional[str] = None,
    tool_version: str = "v1.1",
    cached: bool = False,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    meta = {
        "trace_id": f"{tool_name}:{action}:{int(time.time() * 1000)}",
        "tool_version": tool_version,
        "data_timestamp": data_timestamp or datetime.now().strftime("%Y-%m-%d"),
        "source_chain": [str(item).strip() for item in list(source_chain or [tool_name]) if str(item).strip()],
        "cached": bool(cached),
        "latency_ms": int((time.perf_counter() - started_at) * 1000),
    }
    if extra:
        meta.update(extra)
    return meta


def ok_with_meta(
    data: Any,
    *,
    tool_name: str,
    action: str,
    started_at: float,
    source_chain: Optional[Iterable[str]] = None,
    data_timestamp: Optional[str] = None,
    tool_version: str = "v1.1",
    cached: bool = False,
    extra_meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    response = ok(data, cached=cached)
    response["meta"] = build_manager_meta(
        tool_name=tool_name,
        action=action,
        started_at=started_at,
        source_chain=source_chain,
        data_timestamp=data_timestamp,
        tool_version=tool_version,
        cached=cached,
        extra=extra_meta,
    )
    return response


def fail_with_meta(
    error: Any,
    *,
    tool_name: str,
    action: str,
    started_at: float,
    source_chain: Optional[Iterable[str]] = None,
    data_timestamp: Optional[str] = None,
    tool_version: str = "v1.1",
    cached: bool = False,
    extra_meta: Optional[dict[str, Any]] = None,
    error_code: Optional[str] = None,
) -> dict[str, Any]:
    response = fail(error, error_code=error_code)
    response["meta"] = build_manager_meta(
        tool_name=tool_name,
        action=action,
        started_at=started_at,
        source_chain=source_chain,
        data_timestamp=data_timestamp,
        tool_version=tool_version,
        cached=cached,
        extra=extra_meta,
    )
    return response


# T07: Standard error code constants
ERR_PARAM = "PARAM_ERROR"
ERR_NOT_FOUND = "NOT_FOUND"
ERR_AUTH = "AUTH_ERROR"
ERR_UPSTREAM = "UPSTREAM_ERROR"
ERR_INTERNAL = "INTERNAL_ERROR"
