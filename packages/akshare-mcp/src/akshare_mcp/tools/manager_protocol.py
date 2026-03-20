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
) -> dict[str, Any]:
    response = fail(error)
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
