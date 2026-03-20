"""Builders for unified decision stock/user context."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

from ..storage import get_db
from ..tools.investment_analysis import get_investment_analysis
from ..tools.semantic.diagnosis import _build_evidence
from ..utils import now_iso, resolve_security_code


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_preferences(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                return decoded
        except Exception:
            return {}
    return {}


def _risk_level_to_bucket(risk_level: str | None) -> str:
    value = str(risk_level or "").strip().lower()
    if value in {"aggressive", "high", "high_risk", "积极", "进取"}:
        return "aggressive"
    if value in {"conservative", "low", "low_risk", "稳健", "保守"}:
        return "conservative"
    return "moderate"


async def build_stock_context(code: str) -> dict[str, Any]:
    """Build structured stock context from the existing investment-analysis path."""
    normalized_code = resolve_security_code(code)
    if not normalized_code:
        raise ValueError("需要提供股票代码")

    analysis_result = await get_investment_analysis(normalized_code)
    warnings: list[str] = []
    if not analysis_result.get("success"):
        raise RuntimeError(str(analysis_result.get("error") or "investment_analysis_failed"))

    analysis_context = analysis_result.get("data", {}) or {}
    evidence, highlights, risks, recommendation, recommendation_text = _build_evidence(analysis_context)
    base_scores = {"buy": 80.0, "hold": 62.0, "wait": 45.0, "sell": 22.0}
    stock_score = base_scores.get(recommendation, 50.0)
    stock_score += len(highlights) * 3.5
    stock_score -= len(risks) * 3.0
    stock_score = round(_clamp(stock_score, 0.0, 100.0), 2)

    basic_info = analysis_context.get("basic_info", {}) if isinstance(analysis_context.get("basic_info"), dict) else {}
    price_context = analysis_context.get("price_context", {}) if isinstance(analysis_context.get("price_context"), dict) else {}
    valuation = analysis_context.get("valuation", {}) if isinstance(analysis_context.get("valuation"), dict) else {}
    risk = analysis_context.get("risk", {}) if isinstance(analysis_context.get("risk"), dict) else {}

    if not valuation:
        warnings.append("valuation_context_missing")
    if not risk:
        warnings.append("risk_context_missing")

    return {
        "code": normalized_code,
        "name": str(basic_info.get("name") or ""),
        "analysis_date": str(price_context.get("analysis_date") or ""),
        "analysis_context": analysis_context,
        "recommendation": recommendation,
        "recommendation_text": recommendation_text,
        "score": stock_score,
        "evidence": evidence,
        "highlights": highlights,
        "risks": risks,
        "current_price": _safe_float(price_context.get("current_price")),
        "volatility_20d": _safe_float(risk.get("volatility_20d")),
        "source_chain": ["decision_context_builder", "tools.investment_analysis"],
        "warnings": warnings,
        "timestamp": analysis_result.get("timestamp") or now_iso(),
    }


async def build_user_context(user_id: str | None) -> dict[str, Any]:
    """Best-effort user context builder. Missing user data never blocks the pipeline."""
    normalized_user_id = str(user_id or "").strip()
    result: dict[str, Any] = {
        "user_id": normalized_user_id or None,
        "risk_level": "moderate",
        "risk_bucket": "moderate",
        "kyc_level": None,
        "preferences": {},
        "weighted_profile": None,
        "profile_source": "anonymous",
        "source_chain": [],
        "warnings": [],
        "timestamp": now_iso(),
    }
    if not normalized_user_id:
        result["profile_source"] = "anonymous_fallback"
        return result

    db = get_db()
    rows: list[Any] = []
    app_users_hit = False
    users_hit = False

    try:
        async with db.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    "SELECT risk_level, preferences FROM app_users WHERE id = $1 LIMIT 1",
                    normalized_user_id,
                )
                if row:
                    app_users_hit = True
                    prefs = _normalize_preferences(row.get("preferences"))
                    risk_level = str(row.get("risk_level") or "").strip() or "moderate"
                    result["risk_level"] = risk_level
                    result["risk_bucket"] = _risk_level_to_bucket(risk_level)
                    result["preferences"] = prefs
                    result["kyc_level"] = prefs.get("kyc_level")
                    result["profile_source"] = "app_users"
                    result["source_chain"].append("db.app_users")
            except Exception as exc:
                result["warnings"].append(f"app_users:{exc}")

            try:
                row = await conn.fetchrow(
                    "SELECT settings FROM users WHERE id = $1 LIMIT 1",
                    normalized_user_id,
                )
                if row:
                    users_hit = True
                    settings = _normalize_preferences(row.get("settings"))
                    if not app_users_hit:
                        result["preferences"] = settings
                        result["kyc_level"] = settings.get("kyc_level") or settings.get("risk_level")
                        result["risk_level"] = str(settings.get("risk_level") or result["risk_level"] or "moderate")
                        result["risk_bucket"] = _risk_level_to_bucket(result["risk_level"])
                        result["profile_source"] = "users"
                    result["source_chain"].append("db.users")
            except Exception as exc:
                result["warnings"].append(f"users:{exc}")

            try:
                rows = await conn.fetch(
                    """SELECT neuroticism, openness, herd_tendency, greed_fear_axis, confidence, created_at
                       FROM user_profile_snapshots
                       WHERE user_id = $1
                       ORDER BY created_at DESC
                       LIMIT 20""",
                    normalized_user_id,
                )
                if rows:
                    now = datetime.now(timezone.utc)
                    decay_rate = math.log(2) / 7.0
                    totals = {
                        "neuroticism": 0.0,
                        "openness": 0.0,
                        "herd_tendency": 0.0,
                        "greed_fear_axis": 0.0,
                        "confidence": 0.0,
                    }
                    total_weight = 0.0
                    for row in rows:
                        created_at = row["created_at"]
                        if created_at.tzinfo is None:
                            created_at = created_at.replace(tzinfo=timezone.utc)
                        age_days = (now - created_at).total_seconds() / 86400.0
                        weight = math.exp(-decay_rate * age_days)
                        total_weight += weight
                        for key in totals:
                            totals[key] += weight * float(row[key] or 0.0)
                    if total_weight > 0:
                        result["weighted_profile"] = {
                            key: round(value / total_weight, 4)
                            for key, value in totals.items()
                        }
                    result["source_chain"].append("db.user_profile_snapshots")
            except Exception as exc:
                result["warnings"].append(f"user_profile_snapshots:{exc}")
    except Exception as exc:
        result["warnings"].append(f"db_acquire:{exc}")

    if not app_users_hit and not users_hit:
        result["profile_source"] = "fallback"

    return result
