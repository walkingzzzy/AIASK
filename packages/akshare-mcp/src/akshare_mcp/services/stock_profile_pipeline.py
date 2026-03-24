"""Stock profile vector backfill pipeline for unified vector storage."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Optional


_PROFILE_TYPES = ("fundamental", "technical", "both")
_FEATURE_ORDER = (
    "pe_ratio",
    "pb_ratio",
    "market_cap_log10",
    "roe",
    "debt_ratio",
    "revenue_growth",
    "profit_growth",
    "momentum_20d",
    "trend_20d",
    "volatility_20d",
    "volume_ratio_20d",
)
_FEATURE_SET_BY_TYPE = {
    "fundamental": {
        "pe_ratio",
        "pb_ratio",
        "market_cap_log10",
        "roe",
        "debt_ratio",
        "revenue_growth",
        "profit_growth",
    },
    "technical": {
        "momentum_20d",
        "trend_20d",
        "volatility_20d",
        "volume_ratio_20d",
    },
    "both": set(_FEATURE_ORDER),
}


def _normalize_codes(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        items = raw
    else:
        items = str(raw).replace(";", ",").split(",")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        token = str(item or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _normalize_positive_int(value: Any, default: int, *, minimum: int = 1, maximum: int = 5000) -> int:
    try:
        resolved = int(default if value is None or value == "" else value)
    except (TypeError, ValueError):
        resolved = int(default)
    return max(minimum, min(resolved, maximum))


def _normalize_profile_types(raw: Any) -> list[str]:
    if raw is None:
        return list(_PROFILE_TYPES)
    resolved: list[str] = []
    seen: set[str] = set()
    for item in _normalize_codes(raw):
        token = str(item or "").strip().lower()
        if token not in _PROFILE_TYPES or token in seen:
            continue
        seen.add(token)
        resolved.append(token)
    return resolved or list(_PROFILE_TYPES)


def _normalize_ratio(value: Any) -> float:
    try:
        resolved = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if abs(resolved) > 1.5:
        return resolved / 100.0
    return resolved


def _normalize_vector(values: list[float]) -> list[float]:
    vector = [float(item) for item in list(values or [])]
    if not vector:
        return []
    norm = math.sqrt(sum(item * item for item in vector))
    if norm <= 0:
        return vector
    return [round(item / norm, 10) for item in vector]


def _clip_feature(value: float, *, scale: float) -> float:
    return round(math.tanh(float(value or 0.0) / max(float(scale or 1.0), 1e-6)), 8)


def _extract_fundamental_features(
    stock_info: dict[str, Any],
    financial_row: Optional[dict[str, Any]],
) -> dict[str, float]:
    financials = dict(financial_row or {})
    market_cap = float(stock_info.get("market_cap") or 0.0)
    return {
        "pe_ratio": float(stock_info.get("pe_ratio") or 0.0),
        "pb_ratio": float(stock_info.get("pb_ratio") or 0.0),
        "market_cap_log10": math.log10(max(market_cap, 1.0)) if market_cap > 0 else 0.0,
        "roe": float(financials.get("roe") or 0.0),
        "debt_ratio": _normalize_ratio(financials.get("debt_ratio")),
        "revenue_growth": _normalize_ratio(financials.get("revenue_growth")),
        "profit_growth": _normalize_ratio(financials.get("profit_growth")),
    }


def _extract_technical_features(klines: list[dict[str, Any]]) -> dict[str, float]:
    closes = [float(row.get("close") or 0.0) for row in list(klines or []) if row.get("close") is not None]
    volumes = [float(row.get("volume") or 0.0) for row in list(klines or []) if row.get("volume") is not None]
    if len(closes) < 20:
        return {}
    recent_closes = closes[-20:]
    returns = []
    for idx in range(1, len(recent_closes)):
        prev_close = float(recent_closes[idx - 1] or 0.0)
        close = float(recent_closes[idx] or 0.0)
        if prev_close <= 0:
            continue
        returns.append((close - prev_close) / prev_close)
    ma20 = sum(recent_closes) / len(recent_closes)
    avg_volume_20 = sum(volumes[-20:]) / max(len(volumes[-20:]), 1) if volumes else 0.0
    avg_volume_5 = sum(volumes[-5:]) / max(len(volumes[-5:]), 1) if volumes else 0.0
    return {
        "momentum_20d": ((recent_closes[-1] - recent_closes[0]) / recent_closes[0]) if recent_closes[0] > 0 else 0.0,
        "trend_20d": ((recent_closes[-1] - ma20) / ma20) if ma20 > 0 else 0.0,
        "volatility_20d": math.sqrt(sum(item * item for item in returns) / max(len(returns), 1)) if returns else 0.0,
        "volume_ratio_20d": (avg_volume_5 / avg_volume_20) if avg_volume_20 > 0 else 0.0,
    }


def build_stock_profile_features(
    stock_info: dict[str, Any],
    financial_row: Optional[dict[str, Any]] = None,
    klines: Optional[list[dict[str, Any]]] = None,
) -> dict[str, float]:
    return {
        **_extract_fundamental_features(stock_info, financial_row),
        **_extract_technical_features(list(klines or [])),
    }


def build_stock_profile_embedding(
    features: dict[str, float],
    *,
    profile_type: str,
) -> list[float]:
    normalized_type = str(profile_type or "both").strip().lower()
    allowed_features = _FEATURE_SET_BY_TYPE.get(normalized_type, _FEATURE_SET_BY_TYPE["both"])
    raw_vector: list[float] = []
    for feature_name in _FEATURE_ORDER:
        if feature_name not in allowed_features:
            raw_vector.append(0.0)
            continue
        value = float(features.get(feature_name) or 0.0)
        if feature_name == "pe_ratio":
            transformed = _clip_feature(math.log1p(max(value, 0.0)), scale=2.4)
        elif feature_name == "pb_ratio":
            transformed = _clip_feature(value, scale=5.0)
        elif feature_name == "market_cap_log10":
            transformed = _clip_feature(value - 9.0, scale=3.0)
        elif feature_name == "roe":
            transformed = _clip_feature(value, scale=25.0)
        elif feature_name == "debt_ratio":
            transformed = _clip_feature(value, scale=0.8)
        elif feature_name in {"revenue_growth", "profit_growth"}:
            transformed = _clip_feature(value, scale=0.4)
        elif feature_name == "momentum_20d":
            transformed = _clip_feature(value, scale=0.35)
        elif feature_name == "trend_20d":
            transformed = _clip_feature(value, scale=0.2)
        elif feature_name == "volatility_20d":
            transformed = _clip_feature(value, scale=0.08)
        elif feature_name == "volume_ratio_20d":
            transformed = _clip_feature(value - 1.0, scale=1.5)
        else:
            transformed = _clip_feature(value, scale=1.0)
        raw_vector.append(transformed)
    return _normalize_vector(raw_vector)


def build_stock_profile_summary(
    stock_info: dict[str, Any],
    features: dict[str, float],
    *,
    profile_type: str,
) -> str:
    name = stock_info.get("name") or stock_info.get("stock_name") or ""
    industry = stock_info.get("industry") or stock_info.get("sector") or ""
    return "\n".join(
        [
            "股票画像向量摘要",
            f"代码: {stock_info.get('code') or ''}",
            f"名称: {name}",
            f"行业: {industry}",
            f"画像类型: {profile_type}",
            f"PE: {float(features.get('pe_ratio') or 0.0):.4f}",
            f"PB: {float(features.get('pb_ratio') or 0.0):.4f}",
            f"市值log10: {float(features.get('market_cap_log10') or 0.0):.4f}",
            f"ROE: {float(features.get('roe') or 0.0):.4f}",
            f"资产负债率: {float(features.get('debt_ratio') or 0.0):.4f}",
            f"营收增速: {float(features.get('revenue_growth') or 0.0):.4f}",
            f"利润增速: {float(features.get('profit_growth') or 0.0):.4f}",
            f"20日动量: {float(features.get('momentum_20d') or 0.0):.4f}",
            f"20日趋势偏离: {float(features.get('trend_20d') or 0.0):.4f}",
            f"20日波动率: {float(features.get('volatility_20d') or 0.0):.4f}",
            f"20日量比: {float(features.get('volume_ratio_20d') or 0.0):.4f}",
        ]
    )


def build_stock_profile_vector_payload(
    *,
    stock_info: dict[str, Any],
    financial_row: Optional[dict[str, Any]] = None,
    klines: Optional[list[dict[str, Any]]] = None,
    profile_type: str = "both",
    version: str = "v1",
) -> Optional[dict[str, Any]]:
    code = str(stock_info.get("code") or "").strip()
    if not code:
        return None
    normalized_profile_type = str(profile_type or "both").strip().lower()
    if normalized_profile_type not in _PROFILE_TYPES:
        normalized_profile_type = "both"
    features = build_stock_profile_features(stock_info, financial_row, klines)
    embedding = build_stock_profile_embedding(features, profile_type=normalized_profile_type)
    if not embedding:
        return None
    summary = build_stock_profile_summary(stock_info, features, profile_type=normalized_profile_type)
    entity_id = f"{code}|{normalized_profile_type}"
    signature_basis = json.dumps(
        {
            "entity_id": entity_id,
            "version": str(version or "v1"),
            "features": {key: round(float(features.get(key) or 0.0), 8) for key in _FEATURE_ORDER},
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return {
        "collection_name": "stock_profile_embeddings",
        "entity_type": "stock_profile",
        "entity_id": entity_id,
        "stock_code": code,
        "profile_type": normalized_profile_type,
        "model_id": "stock-profile-v1",
        "vector_dim": len(embedding),
        "metric": "cosine",
        "version": str(version or "v1"),
        "signature": hashlib.sha1(signature_basis.encode("utf-8")).hexdigest(),
        "status": "active",
        "embedding": embedding,
        "metadata": {
            "stock_name": stock_info.get("name") or stock_info.get("stock_name") or "",
            "industry": stock_info.get("industry") or stock_info.get("sector") or "",
            "summary_text": summary,
            "feature_order": list(_FEATURE_ORDER),
            "feature_coverage": sorted(list(_FEATURE_SET_BY_TYPE.get(normalized_profile_type, set()))),
            "raw_features": {key: round(float(features.get(key) or 0.0), 8) for key in _FEATURE_ORDER},
        },
    }


async def load_stock_profile_context(
    db,
    code: str,
    *,
    kline_limit: int = 90,
) -> Optional[dict[str, Any]]:
    stock_info = dict(await db.get_stock_info(code) or {})
    if not stock_info:
        return None
    stock_info["code"] = str(stock_info.get("code") or code).strip()
    financial_row = None
    try:
        financials = await db.get_financials(code, limit=1)
        if financials:
            financial_row = dict(financials[0] or {})
    except Exception:
        financial_row = None
    klines = []
    try:
        klines = list(await db.get_klines(code, limit=max(30, int(kline_limit or 90))) or [])
    except Exception:
        klines = []
    return {
        "stock_info": stock_info,
        "financial_row": financial_row,
        "klines": klines,
    }


async def build_stock_profile_payload(
    db,
    code: str,
    *,
    profile_type: str = "both",
    kline_limit: int = 90,
    version: str = "v1",
) -> Optional[dict[str, Any]]:
    context = await load_stock_profile_context(db, code, kline_limit=kline_limit)
    if not context:
        return None
    return build_stock_profile_vector_payload(
        stock_info=context.get("stock_info") or {},
        financial_row=context.get("financial_row"),
        klines=context.get("klines") or [],
        profile_type=profile_type,
        version=version,
    )


async def _load_candidate_rows(
    db,
    *,
    stock_codes: list[str],
    code_limit: int,
) -> list[dict[str, Any]]:
    if stock_codes:
        rows: list[dict[str, Any]] = []
        for code in stock_codes:
            info = dict(await db.get_stock_info(code) or {})
            info["code"] = str(info.get("code") or code).strip()
            rows.append(info)
        return [row for row in rows if row.get("code")]
    if hasattr(db, "list_stock_universe"):
        rows = await db.list_stock_universe(limit=code_limit)
        return [dict(row or {}) for row in rows if str(dict(row or {}).get("code") or "").strip()]
    return []


async def _profile_exists(db, *, entity_id: str, version: str) -> bool:
    if not hasattr(db, "list_vector_profiles"):
        return False
    try:
        rows = await db.list_vector_profiles(
            collection_name="stock_profile_embeddings",
            entity_id=entity_id,
            version=version,
            limit=1,
        )
    except Exception:
        return False
    return bool(rows)


async def backfill_stock_profile_vectors(
    db,
    *,
    stock_codes: Any = None,
    code_limit: Any = 200,
    profile_types: Any = None,
    kline_limit: Any = 90,
    version: str = "v1",
    rebuild_existing: Any = False,
    dry_run: Any = False,
) -> dict[str, Any]:
    resolved_codes = _normalize_codes(stock_codes)
    resolved_code_limit = _normalize_positive_int(code_limit, 200, minimum=1, maximum=5000)
    resolved_profile_types = _normalize_profile_types(profile_types)
    resolved_kline_limit = _normalize_positive_int(kline_limit, 90, minimum=30, maximum=500)
    resolved_rebuild_existing = bool(rebuild_existing)
    resolved_dry_run = bool(dry_run)

    candidate_rows = await _load_candidate_rows(
        db,
        stock_codes=resolved_codes,
        code_limit=resolved_code_limit,
    )
    results = {
        "stock_codes": [str(row.get("code") or "").strip() for row in candidate_rows if str(row.get("code") or "").strip()],
        "code_count": len(candidate_rows),
        "profile_types": list(resolved_profile_types),
        "kline_limit": resolved_kline_limit,
        "version": str(version or "v1"),
        "rebuild_existing": resolved_rebuild_existing,
        "dry_run": resolved_dry_run,
        "processed_codes": 0,
        "skipped_codes": 0,
        "candidate_profiles": 0,
        "skipped_existing_profiles": 0,
        "saved_profiles": 0,
        "errors": [],
    }

    for row in candidate_rows:
        code = str(row.get("code") or "").strip()
        if not code:
            continue
        context = await load_stock_profile_context(db, code, kline_limit=resolved_kline_limit)
        if not context:
            results["skipped_codes"] += 1
            continue
        results["processed_codes"] += 1
        for profile_type in resolved_profile_types:
            payload = build_stock_profile_vector_payload(
                stock_info=context.get("stock_info") or {},
                financial_row=context.get("financial_row"),
                klines=context.get("klines") or [],
                profile_type=profile_type,
                version=str(version or "v1"),
            )
            if not payload:
                continue
            results["candidate_profiles"] += 1
            if not resolved_rebuild_existing and await _profile_exists(
                db,
                entity_id=str(payload.get("entity_id") or ""),
                version=str(payload.get("version") or "v1"),
            ):
                results["skipped_existing_profiles"] += 1
                continue
            if resolved_dry_run:
                results["saved_profiles"] += 1
                continue
            try:
                await db.save_vector_profile(payload)
                results["saved_profiles"] += 1
            except Exception as exc:
                results["errors"].append(f"{code}:{profile_type}:{type(exc).__name__}")

    if len(results["errors"]) > 20:
        total = len(results["errors"])
        results["errors"] = list(results["errors"][:20]) + [f"...及其他 {total - 20} 个错误"]
    return results
