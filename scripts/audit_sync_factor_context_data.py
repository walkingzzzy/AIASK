#!/usr/bin/env python3
"""Audit and backfill factor-mining text/fund-flow context into DB."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AKSHARE_MCP_SRC = ROOT / "packages" / "akshare-mcp" / "src"
STRATEGY_FACTORY_SRC = ROOT / "packages" / "strategy-factory" / "src"

for path in (str(AKSHARE_MCP_SRC), str(STRATEGY_FACTORY_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

from akshare_mcp.env_loader import load_mcp_env  # noqa: E402
from akshare_mcp.services.artifact_registry import get_artifact_async  # noqa: E402
from akshare_mcp.services.factor_candidate_storage import get_factor_candidate_record_async  # noqa: E402
from akshare_mcp.storage import get_db, run_with_db_cleanup  # noqa: E402
from akshare_mcp.tools.fund_flow import get_stock_fund_flow  # noqa: E402
from akshare_mcp.tools.news.news_feed import get_stock_news  # noqa: E402
from akshare_mcp.tools.news.notices import get_stock_notices  # noqa: E402
from akshare_mcp.tools.news.research import get_research_reports  # noqa: E402
from strategy_factory.domain.constants import REPRESENTATIVE_STOCKS  # noqa: E402
from strategy_factory.domain.targets import _normalize_target_codes  # noqa: E402


DEFAULT_CODES = list(REPRESENTATIVE_STOCKS) or ["600519", "000858", "601318", "000001"]
_MARKET_CODE_PATTERN = re.compile(r"^\d{6}$")


def _normalize_market_code(value) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    token = raw.split(".", 1)[0].strip()
    if not token:
        return None
    return token if _MARKET_CODE_PATTERN.fullmatch(token) else None


def _parse_codes(raw: str | None, *, default: list[str]) -> list[str]:
    if not raw:
        return [token for item in default if (token := _normalize_market_code(item))]
    items: list[str] = []
    seen: set[str] = set()
    for part in str(raw).replace(";", ",").split(","):
        token = _normalize_market_code(part)
        if not token or token in seen:
            continue
        seen.add(token)
        items.append(token)
    return items


def _parse_scope_sources(raw: str | None) -> list[str]:
    if raw is None:
        raw = "explicit,representative,active_pool,factory_targets"
    items: list[str] = []
    seen: set[str] = set()
    for part in str(raw).replace(";", ",").split(","):
        token = str(part or "").strip().lower()
        if not token or token in seen:
            continue
        seen.add(token)
        items.append(token)
    return items


def _merge_code_sets(*groups) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for code in list(group or []):
            token = _normalize_market_code(code)
            if not token or token in seen:
                continue
            seen.add(token)
            merged.append(token)
    return merged


def _print_section(title: str, payload) -> None:
    print(f"\n## {title}")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


async def _audit_context_tables(db) -> dict:
    async with db.acquire() as conn:
        vector_total = await conn.fetchval("SELECT COUNT(*) FROM vector_documents")
        news_total = await conn.fetchval("SELECT COUNT(*) FROM vector_documents WHERE doc_type = 'news'")
        notice_total = await conn.fetchval("SELECT COUNT(*) FROM vector_documents WHERE doc_type = 'notice'")
        research_doc_total = await conn.fetchval("SELECT COUNT(*) FROM vector_documents WHERE doc_type = 'research'")
        research_total = await conn.fetchval("SELECT COUNT(*) FROM research_reports")
        fund_flow_total = await conn.fetchval("SELECT COUNT(*) FROM stock_fund_flow")
        latest_fund_flow = await conn.fetchval("SELECT MAX(trade_date) FROM stock_fund_flow")

    return {
        "vector_documents_total": int(vector_total or 0),
        "vector_documents_news": int(news_total or 0),
        "vector_documents_notice": int(notice_total or 0),
        "vector_documents_research": int(research_doc_total or 0),
        "research_reports": int(research_total or 0),
        "stock_fund_flow": int(fund_flow_total or 0),
        "stock_fund_flow_latest_trade_date": latest_fund_flow.isoformat() if latest_fund_flow else None,
    }


async def _load_active_pool_codes_from_snapshot(db, *, limit: int = 12) -> dict:
    snapshot = await db.get_daily_snapshot() if hasattr(db, "get_daily_snapshot") else None
    factor_research = dict((snapshot or {}).get("factor_research") or {})
    active_pool = dict(factor_research.get("active_candidate_pool") or {})
    top_candidates = list(active_pool.get("top_candidates") or [])[: max(1, int(limit or 12))]
    artifact_ids: list[str] = []
    codes: list[str] = []

    for item in top_candidates:
        artifact_id = str((item or {}).get("artifact_id") or "").strip()
        if artifact_id:
            artifact_ids.append(artifact_id)
            codes = _merge_code_sets(codes, await _load_codes_from_artifact_id(artifact_id))
        codes = _merge_code_sets(codes, _normalize_target_codes(item, limit=12))

    return {
        "snapshot_date": (snapshot or {}).get("date") or (snapshot or {}).get("snapshot_date"),
        "artifact_ids": artifact_ids,
        "codes": codes,
        "run_id": None,
        "source": "daily_snapshot",
        "factor_source_mode": str((factor_research.get("summary") or {}).get("factor_source_mode") or "").strip() or None,
    }


def _coerce_started_date(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "date"):
        try:
            return value.date().isoformat()
        except Exception:
            pass
    raw = str(value or "").strip()
    if len(raw) >= 10:
        return raw[:10]
    return None


def _extract_codes_from_artifact(artifact: dict | None) -> list[str]:
    payload = dict((artifact or {}).get("payload") or artifact or {})
    coverage = dict(payload.get("coverage") or {})
    per_code_stats = [
        str((item or {}).get("code") or "").strip()
        for item in list(coverage.get("per_code_stats") or [])
        if isinstance(item, dict)
    ]
    return _merge_code_sets(
        payload.get("codes"),
        per_code_stats,
        payload.get("code"),
        _normalize_target_codes(payload, limit=12),
    )


async def _load_codes_from_artifact_id(artifact_id: str) -> list[str]:
    try:
        record = await get_factor_candidate_record_async(artifact_id)
    except Exception:
        record = None
    if isinstance(record, dict):
        return _merge_code_sets(record.get("codes"), _normalize_target_codes(record, limit=12))

    try:
        artifact = await get_artifact_async(artifact_id)
    except Exception:
        artifact = None
    if isinstance(artifact, dict):
        return _extract_codes_from_artifact(artifact)
    return []


async def _load_active_pool_codes_from_factory_run(db, *, limit: int = 12, run_limit: int = 10) -> dict:
    latest_run = None
    if hasattr(db, "get_latest_strategy_factory_run"):
        try:
            latest_run = await db.get_latest_strategy_factory_run()
        except Exception:
            latest_run = None
    if latest_run is None and hasattr(db, "list_strategy_factory_runs"):
        try:
            rows = await db.list_strategy_factory_runs(limit=max(1, int(run_limit or 10)))
        except Exception:
            rows = []
        latest_run = list(rows or [None])[0]

    payload = {
        "snapshot_date": None,
        "artifact_ids": [],
        "codes": [],
        "run_id": str((latest_run or {}).get("run_id") or "").strip() or None,
        "source": "factory_run" if latest_run else "factory_run_unavailable",
        "factor_source_mode": None,
    }
    if not latest_run:
        return payload

    snapshot_summary = dict((latest_run or {}).get("snapshot_summary") or {})
    factor_research = dict(snapshot_summary.get("factor_research") or {})
    factor_summary = dict(factor_research.get("summary") or {})
    active_pool = dict(factor_research.get("active_candidate_pool") or {})
    top_candidates = list(active_pool.get("top_candidates") or [])[: max(1, int(limit or 12))]
    artifact_ids: list[str] = []
    codes: list[str] = []

    for item in top_candidates:
        if not isinstance(item, dict):
            continue
        artifact_id = str((item or {}).get("artifact_id") or "").strip()
        if artifact_id and artifact_id not in artifact_ids:
            artifact_ids.append(artifact_id)
        codes = _merge_code_sets(codes, _normalize_target_codes(item, limit=12))

    summary = dict((latest_run or {}).get("summary") or {})
    for item in list(summary.get("autonomy_task_briefs") or []):
        artifact_id = str((item or {}).get("source_candidate_artifact_id") or "").strip()
        if artifact_id and artifact_id not in artifact_ids:
            artifact_ids.append(artifact_id)

    for artifact_id in list(artifact_ids):
        codes = _merge_code_sets(codes, await _load_codes_from_artifact_id(artifact_id))

    payload.update(
        {
            "snapshot_date": snapshot_summary.get("date") or _coerce_started_date((latest_run or {}).get("started_at")),
            "artifact_ids": artifact_ids,
            "codes": codes,
            "factor_source_mode": str(factor_summary.get("factor_source_mode") or "").strip() or None,
        }
    )
    return payload


async def _load_active_pool_codes(db, *, limit: int = 12, run_limit: int = 10) -> dict:
    factory_payload = await _load_active_pool_codes_from_factory_run(db, limit=limit, run_limit=run_limit)
    if factory_payload.get("artifact_ids") or factory_payload.get("codes"):
        return factory_payload
    snapshot_payload = await _load_active_pool_codes_from_snapshot(db, limit=limit)
    if snapshot_payload.get("artifact_ids") or snapshot_payload.get("codes"):
        return snapshot_payload
    return factory_payload if factory_payload.get("run_id") else snapshot_payload


async def _load_factory_target_codes(
    db,
    *,
    snapshot_date: str | None = None,
    limit: int = 50,
) -> dict:
    if not hasattr(db, "list_strategy_task_runs"):
        return {"snapshot_date": snapshot_date, "codes": [], "task_keys": [], "matched_runs": 0}

    rows = await db.list_strategy_task_runs(
        task_name="strategy_research_task",
        task_scope="strategy_factory",
        limit=max(1, int(limit or 50)),
    )
    target_day = str(snapshot_date or date.today().isoformat())[:10]
    codes: list[str] = []
    task_keys: list[str] = []
    seen_task_keys: set[str] = set()
    matched_runs = 0

    for row in list(rows or []):
        run_day = _coerce_started_date((row or {}).get("started_at"))
        if run_day and run_day != target_day:
            continue
        matched_runs += 1
        payload = dict((row or {}).get("payload") or {})
        task_key = str((row or {}).get("task_key") or "").strip()
        if task_key and task_key not in seen_task_keys:
            seen_task_keys.add(task_key)
            task_keys.append(task_key)
        codes = _merge_code_sets(
            codes,
            _normalize_target_codes(
                [
                    payload,
                    payload.get("research_task"),
                    payload.get("event_context"),
                    (payload.get("research_task") or {}).get("event_context"),
                ],
                limit=12,
            ),
        )

    return {
        "snapshot_date": target_day,
        "codes": codes,
        "task_keys": [item for item in task_keys if item],
        "matched_runs": matched_runs,
    }


async def _resolve_scope_codes(db, args) -> tuple[list[str], dict]:
    selected_sources = _parse_scope_sources(getattr(args, "scope_sources", None))
    explicit_codes = _parse_codes(getattr(args, "codes", None), default=[])
    representative_codes = list(REPRESENTATIVE_STOCKS)

    active_pool_payload = {"snapshot_date": None, "artifact_ids": [], "codes": []}
    factory_target_payload = {"snapshot_date": date.today().isoformat(), "codes": [], "task_keys": [], "matched_runs": 0}

    if "active_pool" in selected_sources:
        active_pool_payload = await _load_active_pool_codes(
            db,
            limit=max(1, int(getattr(args, "active_pool_limit", 12) or 12)),
            run_limit=max(1, int(getattr(args, "factory_run_limit", 10) or 10)),
        )
    if "factory_targets" in selected_sources:
        factory_target_payload = await _load_factory_target_codes(
            db,
            snapshot_date=active_pool_payload.get("snapshot_date"),
            limit=max(1, int(getattr(args, "task_run_limit", 50) or 50)),
        )

    resolved_codes: list[str] = []
    if "explicit" in selected_sources:
        resolved_codes = _merge_code_sets(resolved_codes, explicit_codes)
    if "representative" in selected_sources:
        resolved_codes = _merge_code_sets(resolved_codes, representative_codes)
    if "active_pool" in selected_sources:
        resolved_codes = _merge_code_sets(resolved_codes, active_pool_payload.get("codes"))
    if "factory_targets" in selected_sources:
        resolved_codes = _merge_code_sets(resolved_codes, factory_target_payload.get("codes"))

    if not resolved_codes:
        resolved_codes = _merge_code_sets(explicit_codes, DEFAULT_CODES)

    summary = {
        "scope_sources": selected_sources,
        "explicit_codes": explicit_codes,
        "representative_codes": representative_codes if "representative" in selected_sources else [],
        "active_pool": active_pool_payload,
        "factory_targets": factory_target_payload,
        "resolved_codes": resolved_codes,
        "resolved_count": len(resolved_codes),
    }
    return resolved_codes, summary


async def _sync_code_context(
    db,
    code: str,
    *,
    news_days: int,
    notice_days: int,
    item_limit: int,
) -> dict:
    end_date = date.today()
    news_start = end_date - timedelta(days=max(int(news_days or 1), 1))
    notice_start = end_date - timedelta(days=max(int(notice_days or 1), 1))
    result = {
        "code": code,
        "news_fetched": 0,
        "news_saved": 0,
        "notice_fetched": 0,
        "notice_saved": 0,
        "research_fetched": 0,
        "research_saved": 0,
        "research_docs_saved": 0,
        "fund_flow_saved": 0,
        "errors": [],
    }

    try:
        news_resp = get_stock_news(code, limit=max(item_limit, 1), prefer_db=False)
        news_items = list(news_resp.get("data") or []) if news_resp.get("success") and isinstance(news_resp.get("data"), list) else []
        result["news_fetched"] = len(news_items)
        if news_items:
            result["news_saved"] = await db.save_vector_documents(code, "news", news_items)
    except Exception as exc:
        result["errors"].append(f"news:{exc}")

    try:
        notice_resp = get_stock_notices(
            notice_start.isoformat(),
            end_date.isoformat(),
            ["全部"],
            code,
            prefer_db=False,
        )
        notice_items = []
        if notice_resp.get("success"):
            payload = notice_resp.get("data")
            if isinstance(payload, dict):
                notice_items = [dict(item) for item in (payload.get("events") or []) if isinstance(item, dict)]
        result["notice_fetched"] = len(notice_items)
        if notice_items:
            result["notice_saved"] = await db.save_vector_documents(code, "notice", notice_items)
    except Exception as exc:
        result["errors"].append(f"notice:{exc}")

    try:
        report_resp = get_research_reports(code, limit=max(item_limit, 1), prefer_db=False)
        report_items = []
        if report_resp.get("success"):
            payload = report_resp.get("data")
            if isinstance(payload, dict):
                report_items = [dict(item) for item in (payload.get("reports") or []) if isinstance(item, dict)]
            elif isinstance(payload, list):
                report_items = [dict(item) for item in payload if isinstance(item, dict)]
        result["research_fetched"] = len(report_items)
        if report_items:
            result["research_saved"] = await db.save_research_reports(code, report_items)
            result["research_docs_saved"] = await db.save_vector_documents(code, "research", report_items)
    except Exception as exc:
        result["errors"].append(f"research:{exc}")

    try:
        flow_resp = get_stock_fund_flow(code, prefer_db=False)
        flow_payload = dict(flow_resp.get("data") or {}) if flow_resp.get("success") and isinstance(flow_resp.get("data"), dict) else {}
        if flow_payload:
            result["fund_flow_saved"] = await db.save_stock_fund_flow(code, flow_payload, trade_date=end_date)
    except Exception as exc:
        result["errors"].append(f"fund_flow:{exc}")

    return result


async def _main(args) -> int:
    load_mcp_env(override=False)
    db = get_db()
    await db.initialize()
    codes, scope_summary = await _resolve_scope_codes(db, args)
    _print_section("factor_context_scope", scope_summary)

    before = await _audit_context_tables(db)
    _print_section("factor_context_before", before)

    results = []
    for code in codes:
        results.append(
            await _sync_code_context(
                db,
                code,
                news_days=args.news_days,
                notice_days=args.notice_days,
                item_limit=args.item_limit,
            )
        )
    _print_section("sync_factor_context", results)

    after = await _audit_context_tables(db)
    _print_section("factor_context_after", after)

    summary = {
        "scope_sources": scope_summary.get("scope_sources"),
        "codes": codes,
        "news_saved": sum(int(item.get("news_saved") or 0) for item in results),
        "notice_saved": sum(int(item.get("notice_saved") or 0) for item in results),
        "research_saved": sum(int(item.get("research_saved") or 0) for item in results),
        "research_docs_saved": sum(int(item.get("research_docs_saved") or 0) for item in results),
        "fund_flow_saved": sum(int(item.get("fund_flow_saved") or 0) for item in results),
        "error_count": sum(len(item.get("errors") or []) for item in results),
    }
    _print_section("summary", summary)
    return 0 if summary["error_count"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit and backfill factor-mining context data")
    parser.add_argument("--codes", type=str, default="", help="comma-separated explicit stock codes to merge into scope")
    parser.add_argument(
        "--scope-sources",
        type=str,
        default="explicit,representative,active_pool,factory_targets",
        help="comma-separated scope sources: explicit,representative,active_pool,factory_targets",
    )
    parser.add_argument("--active-pool-limit", type=int, default=12, help="max active-pool candidates to inspect")
    parser.add_argument("--factory-run-limit", type=int, default=10, help="max strategy_factory runs to inspect when latest run is unavailable")
    parser.add_argument("--task-run-limit", type=int, default=50, help="max strategy_factory task runs to inspect")
    parser.add_argument("--news-days", type=int, default=30, help="days of news lookback")
    parser.add_argument("--notice-days", type=int, default=30, help="days of notice lookback")
    parser.add_argument("--item-limit", type=int, default=10, help="per-code fetch limit")
    args = parser.parse_args()
    return run_with_db_cleanup(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
