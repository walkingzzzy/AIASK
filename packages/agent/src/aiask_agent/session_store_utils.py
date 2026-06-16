from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any


SECRET_KEY_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "broker_token",
    "cookie",
    "credential",
    "password",
    "refresh_token",
    "secret",
    "token",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=max(0, int(days or 0)))).isoformat()


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _bounded_text(value: Any, *, limit: int = 2000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...<truncated {len(text) - limit} chars>"


def _is_secret_key(key: str) -> bool:
    lowered = str(key or "").strip().lower()
    return any(marker in lowered for marker in SECRET_KEY_MARKERS)


def _clean_optional(value: Any, *, limit: int = 500) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:limit]


def _int_or_none(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _side_effect_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()[:200] or None
    if isinstance(value, dict):
        for key in ("level", "side_effect", "type"):
            if value.get(key):
                return str(value.get(key)).strip()[:200]
        return _dumps(sanitize_for_audit(value))[:500]
    return str(value).strip()[:200] or None


def sanitize_for_audit(value: Any, *, max_depth: int = 4, max_items: int = 40, max_text: int = 2000) -> Any:
    """Return a bounded, secret-redacted copy that is safe for local audit rows."""
    if max_depth <= 0:
        if isinstance(value, (dict, list, tuple)):
            return {"truncated": True, "type": value.__class__.__name__}
        return _bounded_text(value, limit=max_text) if isinstance(value, str) else value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _bounded_text(value, limit=max_text)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                result["_truncated_items"] = max(0, len(value) - max_items)
                break
            text_key = str(key)
            if _is_secret_key(text_key):
                result[text_key] = "[redacted]"
            else:
                result[text_key] = sanitize_for_audit(item, max_depth=max_depth - 1, max_items=max_items, max_text=max_text)
        return result
    if isinstance(value, (list, tuple)):
        items = [
            sanitize_for_audit(item, max_depth=max_depth - 1, max_items=max_items, max_text=max_text)
            for item in list(value)[:max_items]
        ]
        if len(value) > max_items:
            items.append({"_truncated_items": len(value) - max_items})
        return items
    return _bounded_text(value, limit=max_text)


def _metadata_archived(metadata: dict[str, Any] | None) -> bool:
    value = dict(metadata or {}).get("archived")
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "archived"}
    return bool(value)
