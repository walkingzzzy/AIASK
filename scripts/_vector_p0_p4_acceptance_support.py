#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
for relative in ("packages/akshare-mcp/src", "packages/strategy-factory/src"):
    path = ROOT_DIR / relative
    if path.exists():
        sys.path.insert(0, str(path))

from akshare_mcp.services.factor_candidate_vector_backfill import backfill_factor_candidate_vectors
from akshare_mcp.services.pattern_embedding_pipeline import backfill_kline_pattern_vectors
from akshare_mcp.services.stock_profile_pipeline import backfill_stock_profile_vectors
from akshare_mcp.services.unified_vector_benchmark import benchmark_vector_collection_search
from akshare_mcp.services.unified_vector_governance import build_vector_collection_snapshot
from akshare_mcp.services.vector_backfill import backfill_market_document_vectors
from akshare_mcp.services.vector_governance import StrategyVectorGovernanceService
from akshare_mcp.services.vector_platform import get_strategy_vector_platform
from akshare_mcp.storage.timescaledb import get_db, run_with_db_cleanup


REQUIRED_TABLES = [
    "stocks",
    "financials",
    "stock_quotes",
    "vector_collections",
    "vector_profiles",
    "vector_index_snapshots",
    "vector_index_items",
    "market_documents",
    "market_doc_chunks",
    "kline_pattern_windows",
]

REQUIRED_COLLECTIONS = [
    "market_doc_chunks",
    "kline_pattern_embeddings",
    "stock_profile_embeddings",
    "factor_candidate_embeddings",
]

P0_COLUMN_CHECKS = {
    "stocks": ["stock_code", "code"],
    "financials": ["stock_code", "code"],
    "stock_quotes": ["change_amt", "change", "prev_close", "pre_close", "mkt_cap", "market_cap"],
}

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _now_iso() -> str:
    return _now().isoformat()

def _normalize_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]

def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value

def _build_phase(status: str, *, summary: str, **extra: Any) -> dict[str, Any]:
    return {
        "status": status,
        "summary": summary,
        **{key: _json_safe(value) for key, value in extra.items()},
    }

async def _table_exists(conn, table_name: str) -> bool:
    row = await conn.fetchval("SELECT to_regclass($1)", f"public.{table_name}")
    return bool(row)

async def _fetch_columns(conn, table_name: str) -> set[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table_name,
    )
    return {str(dict(row).get("column_name") or "").strip() for row in rows}

async def _count_rows(conn, sql: str, *params: Any) -> int:
    return int(await conn.fetchval(sql, *params) or 0)

async def _count_profiles(
    db,
    *,
    collection_name: str,
    version: str | None = None,
    profile_type: str | None = None,
) -> int:
    clauses = ["collection_name = $1"]
    params: list[Any] = [collection_name]
    idx = 2
    if version:
        clauses.append(f"version = ${idx}")
        params.append(str(version))
        idx += 1
    if profile_type:
        clauses.append(f"profile_type = ${idx}")
        params.append(str(profile_type))
        idx += 1
    async with db.acquire() as conn:
        return await _count_rows(
            conn,
            f"SELECT COUNT(*) FROM vector_profiles WHERE {' AND '.join(clauses)}",
            *params,
        )

async def _pick_codes_from_db(db, limit: int) -> tuple[list[str], str]:
    queries = [
        (
            """
            SELECT DISTINCT COALESCE(NULLIF(stock_code, ''), NULLIF(code, '')) AS code
            FROM stocks
            WHERE COALESCE(NULLIF(stock_code, ''), NULLIF(code, '')) IS NOT NULL
            ORDER BY code
            LIMIT $1
            """,
            "stocks",
        ),
        (
            """
            SELECT code
            FROM (
                SELECT code, MAX(time) AS latest_time
                FROM stock_quotes
                WHERE code IS NOT NULL AND code != ''
                GROUP BY code
            ) t
            ORDER BY latest_time DESC NULLS LAST, code
            LIMIT $1
            """,
            "stock_quotes",
        ),
        (
            """
            SELECT code
            FROM (
                SELECT code, MAX(time) AS latest_time
                FROM kline_1d
                WHERE code IS NOT NULL AND code != ''
                GROUP BY code
            ) t
            ORDER BY latest_time DESC NULLS LAST, code
            LIMIT $1
            """,
            "kline_1d",
        ),
    ]
    async with db.acquire() as conn:
        for sql, source in queries:
            try:
                rows = await conn.fetch(sql, max(1, int(limit)))
            except Exception:
                continue
            codes = [str(dict(row).get("code") or "").strip() for row in rows if str(dict(row).get("code") or "").strip()]
            if codes:
                return codes, source
    return [], "unavailable"

async def _pick_market_doc_codes_from_db(
    db,
    *,
    preferred_codes: list[str] | None,
    doc_types: list[str],
    limit: int,
) -> tuple[list[str], str]:
    resolved_limit = max(1, int(limit or 1))
    resolved_doc_types = [str(item or "").strip().lower() for item in list(doc_types or []) if str(item or "").strip()]
    if not resolved_doc_types:
        resolved_doc_types = ["news", "notice", "research"]
    include_research = "research" in resolved_doc_types
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH doc_counts AS (
                SELECT stock_code AS code, COUNT(*) AS cnt
                FROM market_documents
                WHERE stock_code IS NOT NULL
                  AND stock_code != ''
                  AND LOWER(COALESCE(doc_type, '')) = ANY($1::text[])
                GROUP BY stock_code
                UNION ALL
                SELECT stock_code AS code, COUNT(*) AS cnt
                FROM vector_documents
                WHERE stock_code IS NOT NULL
                  AND stock_code != ''
                  AND LOWER(COALESCE(doc_type, '')) = ANY($1::text[])
                GROUP BY stock_code
                UNION ALL
                SELECT code AS code, COUNT(*) AS cnt
                FROM research_reports
                WHERE $2::boolean
                  AND code IS NOT NULL
                  AND code != ''
                GROUP BY code
            )
            SELECT code
            FROM doc_counts
            GROUP BY code
            ORDER BY SUM(cnt) DESC, code
            LIMIT $3
            """,
            resolved_doc_types,
            include_research,
            max(resolved_limit * 4, 20),
        )
    ranked_codes = [str(dict(row).get("code") or "").strip() for row in rows if str(dict(row).get("code") or "").strip()]
    if not ranked_codes:
        return [], "unavailable"
    ranked_set = set(ranked_codes)
    selected: list[str] = []
    seen: set[str] = set()
    for code in list(preferred_codes or []):
        token = str(code or "").strip()
        if not token or token not in ranked_set or token in seen:
            continue
        seen.add(token)
        selected.append(token)
        if len(selected) >= resolved_limit:
            return selected, "preferred_with_market_docs"
    for code in ranked_codes:
        if code in seen:
            continue
        seen.add(code)
        selected.append(code)
        if len(selected) >= resolved_limit:
            break
    source = "preferred_with_market_docs" if selected and preferred_codes else "market_doc_inventory"
    return selected[:resolved_limit], source

async def _get_collection_inventory(db) -> dict[str, dict[str, Any]]:
    rows = await db.list_vector_collections(limit=500) if hasattr(db, "list_vector_collections") else []
    inventory: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row or {})
        collection_name = str(item.get("collection_name") or "").strip()
        if collection_name:
            inventory[collection_name] = item
    return inventory

async def _check_p0_schema(db, require_pgvector: bool) -> dict[str, Any]:
    await db.initialize()
    async with db.acquire() as conn:
        tables = {name: await _table_exists(conn, name) for name in REQUIRED_TABLES}
        columns = {table: sorted(await _fetch_columns(conn, table)) for table in P0_COLUMN_CHECKS}

    collection_inventory = await _get_collection_inventory(db)
    collection_presence = {name: name in collection_inventory for name in REQUIRED_COLLECTIONS}

    missing_tables = [name for name, present in tables.items() if not present]
    missing_columns = {
        table: [column for column in required if column not in set(columns.get(table) or [])]
        for table, required in P0_COLUMN_CHECKS.items()
    }
    missing_columns = {table: items for table, items in missing_columns.items() if items}
    missing_collections = [name for name, present in collection_presence.items() if not present]

    warnings: list[str] = []
    if not db.supports_pgvector():
        if require_pgvector:
            warnings.append("pgvector extension unavailable")
        else:
            warnings.append("pgvector extension unavailable, running in fallback-capable mode")

    failed_checks = bool(missing_tables or missing_columns or missing_collections or (require_pgvector and not db.supports_pgvector()))
    status = "failed" if failed_checks else ("passed_with_warnings" if warnings else "passed")
    summary = (
        f"tables_missing={len(missing_tables)} "
        f"columns_missing={sum(len(items) for items in missing_columns.values())} "
        f"collections_missing={len(missing_collections)} "
        f"pgvector={'on' if db.supports_pgvector() else 'off'}"
    )
    return _build_phase(
        status,
        summary=summary,
        pgvector_enabled=db.supports_pgvector(),
        vector_backend=db.get_vector_backend(),
        required_tables=tables,
        required_columns=columns,
        missing_tables=missing_tables,
        missing_columns=missing_columns,
        collection_presence=collection_presence,
        warnings=warnings,
    )

async def _build_snapshot_if_needed(
    db,
    *,
    collection_name: str,
    version: str | None,
    index_version: str | None,
    source: str,
    activate: bool,
) -> dict[str, Any] | None:
    if not version:
        return None
    return await build_vector_collection_snapshot(
        db,
        collection_name=collection_name,
        version=version,
        index_version=index_version,
        activate=activate,
        source=source,
    )

async def _run_collection_benchmark(
    db,
    *,
    collection_name: str,
    version: str | None,
    index_version: str | None,
    profile_type: str | None,
    sample_size: int,
    top_k: int,
    persist_snapshot_metrics: bool,
) -> dict[str, Any]:
    return await benchmark_vector_collection_search(
        db,
        collection_name=collection_name,
        version=version,
        index_version=index_version,
        profile_type=profile_type,
        sample_size=sample_size,
        top_k=top_k,
        persist_snapshot_metrics=persist_snapshot_metrics,
    )

async def _run_generic_smoke_search(
    db,
    *,
    collection_name: str,
    version: str | None = None,
    index_version: str | None = None,
    profile_type: str | None = None,
) -> dict[str, Any]:
    rows = await db.list_vector_profiles(
        collection_name=collection_name,
        version=version,
        profile_type=profile_type,
        limit=1,
    )
    if not rows:
        return {"status": "skipped", "reason": "no_query_profile"}
    query_row = dict(rows[0] or {})
    result = await db.search_vector_collection(
        collection_name=collection_name,
        query_embedding=list(query_row.get("embedding") or []),
        version=version or query_row.get("version"),
        index_version=index_version,
        profile_type=profile_type or query_row.get("profile_type"),
        exclude_entity_id=query_row.get("entity_id"),
        limit=3,
        metric=str(query_row.get("metric") or "cosine"),
    )
    items = list((result or {}).get("items") or [])
    return {
        "status": "passed",
        "backend_used": (result or {}).get("backend_used"),
        "fallback_used": bool((result or {}).get("fallback_used")),
        "item_count": len(items),
        "query_entity_id": query_row.get("entity_id"),
        "top_entity_id": items[0].get("entity_id") if items else None,
    }

async def _run_market_doc_smoke_search(db, *, stock_code: str) -> dict[str, Any]:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT title, chunk_text, doc_type
            FROM market_doc_chunks
            WHERE stock_code = $1
            ORDER BY published_at DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            stock_code,
        )
    payload = dict(row or {})
    if not payload:
        return {"status": "skipped", "reason": "no_market_doc_chunk"}
    query_text = str(payload.get("title") or payload.get("chunk_text") or "").strip()[:48]
    rows = await db.search_market_doc_chunks(
        query_text=query_text,
        stock_code=stock_code,
        doc_types=[str(payload.get("doc_type") or "news").strip().lower()],
        limit=3,
    )
    return {
        "status": "passed" if rows else "failed",
        "query_text": query_text,
        "item_count": len(rows),
        "top_entity_id": rows[0].get("entity_id") if rows else None,
        "top_hybrid_score": rows[0].get("hybrid_score") if rows else None,
    }

async def _run_strategy_phase(
    db,
    *,
    index_version: str,
    strategy_limit: int,
    strategy_statuses: list[str],
    sample_size: int,
    top_k: int,
    persist_snapshot_metrics: bool,
) -> dict[str, Any]:
    strategies: list[dict[str, Any]] = []
    seen: set[str] = set()
    for status in strategy_statuses:
        rows = await db.list_strategies(status=status, limit=strategy_limit) if hasattr(db, "list_strategies") else []
        for row in rows:
            item = dict(row or {})
            strategy_id = str(item.get("id") or "").strip()
            if strategy_id and strategy_id not in seen:
                seen.add(strategy_id)
                strategies.append(item)
    if not strategies:
        return _build_phase("skipped", summary="no strategies in target statuses", strategy_statuses=strategy_statuses)

    governance = StrategyVectorGovernanceService()
    rebuild = await governance.rebuild_index(
        db,
        index_name="strategy_behavior",
        index_version=index_version,
        statuses=strategy_statuses,
        limit=strategy_limit,
    )
    platform = get_strategy_vector_platform()
    health = await platform.health_check(db, index_name="strategy_behavior")
    active_index = dict((health or {}).get("active_index") or {})
    collection_name = str(
        active_index.get("collection_name")
        or (((rebuild.get("active_registry") or {}).get("metadata") or {}).get("unified_collection_name"))
        or ""
    ).strip()
    benchmark = None
    smoke = None
    if collection_name:
        profile_count = await _count_profiles(db, collection_name=collection_name, version=index_version, profile_type="behavior")
        if profile_count >= 2:
            benchmark = await _run_collection_benchmark(
                db,
                collection_name=collection_name,
                version=index_version,
                index_version=index_version,
                profile_type="behavior",
                sample_size=sample_size,
                top_k=top_k,
                persist_snapshot_metrics=persist_snapshot_metrics,
            )
        smoke = await _run_generic_smoke_search(
            db,
            collection_name=collection_name,
            version=index_version,
            index_version=index_version,
            profile_type="behavior",
        )
    status = "passed" if int(rebuild.get("built_profiles") or 0) > 0 and collection_name else "failed"
    return _build_phase(
        status,
        summary=f"strategies={len(strategies)} built_profiles={int(rebuild.get('built_profiles') or 0)} collection={collection_name or 'none'}",
        rebuild=rebuild,
        health=health,
        benchmark=benchmark,
        smoke=smoke,
    )

async def _run_market_docs_phase(
    db,
    *,
    stock_codes: list[str],
    doc_types: list[str],
    version: str,
    index_version: str,
    sample_size: int,
    top_k: int,
    persist_snapshot_metrics: bool,
    dry_run: bool,
) -> dict[str, Any]:
    if not stock_codes:
        return _build_phase("skipped", summary="no stock codes available for market docs")
    backfill = await backfill_market_document_vectors(
        db,
        stock_codes=stock_codes,
        doc_types=doc_types,
        limit=max(500, len(stock_codes) * 50),
        batch_size=100,
        embed=True,
        chunk_size=800,
        overlap=120,
        version=version,
        dry_run=dry_run,
    )
    profile_count = 0 if dry_run else await _count_profiles(db, collection_name="market_doc_chunks", version=version)
    snapshot = None if dry_run else await _build_snapshot_if_needed(
        db,
        collection_name="market_doc_chunks",
        version=version,
        index_version=index_version,
        source="vector_p0_p4_acceptance.market_docs",
        activate=True,
    )
    benchmark = None
    if not dry_run and profile_count >= 2:
        benchmark = await _run_collection_benchmark(
            db,
            collection_name="market_doc_chunks",
            version=version,
            index_version=(snapshot or {}).get("index_version") or index_version,
            profile_type=None,
            sample_size=sample_size,
            top_k=top_k,
            persist_snapshot_metrics=persist_snapshot_metrics,
        )
    smoke = None if dry_run else await _run_market_doc_smoke_search(db, stock_code=stock_codes[0])
    if dry_run:
        status = "dry_run"
    elif profile_count > 0 and snapshot and str(snapshot.get("status") or "").lower() in {"active", "built"}:
        status = "passed"
    elif int(backfill.get("saved_chunks") or 0) > 0 and profile_count == 0:
        status = "failed"
    else:
        status = "skipped"
    return _build_phase(
        status,
        summary=f"docs={int(backfill.get('saved_docs') or 0)} chunks={int(backfill.get('saved_chunks') or 0)} profiles={profile_count}",
        backfill=backfill,
        snapshot=snapshot,
        benchmark=benchmark,
        smoke=smoke,
    )

async def _run_kline_phase(
    db,
    *,
    stock_codes: list[str],
    version: str,
    index_version: str,
    sample_size: int,
    top_k: int,
    persist_snapshot_metrics: bool,
    dry_run: bool,
) -> dict[str, Any]:
    if not stock_codes:
        return _build_phase("skipped", summary="no stock codes available for kline patterns")
    backfill = await backfill_kline_pattern_vectors(
        db,
        stock_codes=stock_codes,
        code_limit=len(stock_codes),
        window_size=20,
        lookback_days=180,
        max_windows_per_code=1,
        step_days=5,
        vector_method="returns",
        period="daily",
        adjust="",
        version=version,
        dry_run=dry_run,
    )
    profile_count = 0 if dry_run else await _count_profiles(db, collection_name="kline_pattern_embeddings", version=version)
    snapshot = None if dry_run else await _build_snapshot_if_needed(
        db,
        collection_name="kline_pattern_embeddings",
        version=version,
        index_version=index_version,
        source="vector_p0_p4_acceptance.kline_patterns",
        activate=True,
    )
    benchmark = None
    smoke = None
    if not dry_run and profile_count >= 2:
        benchmark = await _run_collection_benchmark(
            db,
            collection_name="kline_pattern_embeddings",
            version=version,
            index_version=(snapshot or {}).get("index_version") or index_version,
            profile_type=None,
            sample_size=sample_size,
            top_k=top_k,
            persist_snapshot_metrics=persist_snapshot_metrics,
        )
    if not dry_run and profile_count > 0:
        smoke = await _run_generic_smoke_search(
            db,
            collection_name="kline_pattern_embeddings",
            version=version,
            index_version=(snapshot or {}).get("index_version") or index_version,
        )
    if dry_run:
        status = "dry_run"
    elif profile_count > 0 and snapshot and str(snapshot.get("status") or "").lower() in {"active", "built"}:
        status = "passed"
    elif int(backfill.get("saved_profiles") or 0) == 0:
        status = "skipped"
    else:
        status = "failed"
    return _build_phase(
        status,
        summary=f"windows={int(backfill.get('saved_windows') or 0)} profiles={profile_count}",
        backfill=backfill,
        snapshot=snapshot,
        benchmark=benchmark,
        smoke=smoke,
    )

async def _run_stock_profiles_phase(
    db,
    *,
    stock_codes: list[str],
    version: str,
    index_version: str,
    sample_size: int,
    top_k: int,
    persist_snapshot_metrics: bool,
    dry_run: bool,
) -> dict[str, Any]:
    if not stock_codes:
        return _build_phase("skipped", summary="no stock codes available for stock profiles")
    backfill = await backfill_stock_profile_vectors(
        db,
        stock_codes=stock_codes,
        code_limit=len(stock_codes),
        profile_types=["both"],
        kline_limit=90,
        version=version,
        dry_run=dry_run,
    )
    profile_count = 0 if dry_run else await _count_profiles(db, collection_name="stock_profile_embeddings", version=version)
    snapshot = None if dry_run else await _build_snapshot_if_needed(
        db,
        collection_name="stock_profile_embeddings",
        version=version,
        index_version=index_version,
        source="vector_p0_p4_acceptance.stock_profiles",
        activate=True,
    )
    benchmark = None
    smoke = None
    if not dry_run and profile_count >= 2:
        benchmark = await _run_collection_benchmark(
            db,
            collection_name="stock_profile_embeddings",
            version=version,
            index_version=(snapshot or {}).get("index_version") or index_version,
            profile_type=None,
            sample_size=sample_size,
            top_k=top_k,
            persist_snapshot_metrics=persist_snapshot_metrics,
        )
    if not dry_run and profile_count > 0:
        smoke = await _run_generic_smoke_search(
            db,
            collection_name="stock_profile_embeddings",
            version=version,
            index_version=(snapshot or {}).get("index_version") or index_version,
        )
    if dry_run:
        status = "dry_run"
    elif profile_count > 0 and snapshot and str(snapshot.get("status") or "").lower() in {"active", "built"}:
        status = "passed"
    elif int(backfill.get("saved_profiles") or 0) == 0:
        status = "skipped"
    else:
        status = "failed"
    return _build_phase(
        status,
        summary=f"processed_codes={int(backfill.get('processed_codes') or 0)} profiles={profile_count}",
        backfill=backfill,
        snapshot=snapshot,
        benchmark=benchmark,
        smoke=smoke,
    )

async def _run_factor_candidates_phase(
    db,
    *,
    codes: list[str],
    version: str,
    index_version: str,
    factor_limit: int,
    sample_size: int,
    top_k: int,
    persist_snapshot_metrics: bool,
    dry_run: bool,
) -> dict[str, Any]:
    backfill = await backfill_factor_candidate_vectors(
        db,
        limit=factor_limit,
        codes=codes or None,
        version=version,
        dry_run=dry_run,
    )
    profile_count = 0 if dry_run else await _count_profiles(db, collection_name="factor_candidate_embeddings", version=version)
    snapshot = None if dry_run else await _build_snapshot_if_needed(
        db,
        collection_name="factor_candidate_embeddings",
        version=version,
        index_version=index_version,
        source="vector_p0_p4_acceptance.factor_candidates",
        activate=True,
    )
    benchmark = None
    smoke = None
    if not dry_run and profile_count >= 2:
        benchmark = await _run_collection_benchmark(
            db,
            collection_name="factor_candidate_embeddings",
            version=version,
            index_version=(snapshot or {}).get("index_version") or index_version,
            profile_type=None,
            sample_size=sample_size,
            top_k=top_k,
            persist_snapshot_metrics=persist_snapshot_metrics,
        )
    if not dry_run and profile_count > 0:
        smoke = await _run_generic_smoke_search(
            db,
            collection_name="factor_candidate_embeddings",
            version=version,
            index_version=(snapshot or {}).get("index_version") or index_version,
        )
    if dry_run:
        status = "dry_run"
    elif profile_count > 0 and snapshot and str(snapshot.get("status") or "").lower() in {"active", "built"}:
        status = "passed"
    elif int(backfill.get("saved_profiles") or 0) == 0:
        status = "skipped"
    else:
        status = "failed"
    return _build_phase(
        status,
        summary=f"processed_records={int(backfill.get('processed_records') or 0)} profiles={profile_count}",
        backfill=backfill,
        snapshot=snapshot,
        benchmark=benchmark,
        smoke=smoke,
    )

def _summarize(phases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts = {"passed": 0, "passed_with_warnings": 0, "failed": 0, "skipped": 0, "dry_run": 0}
    for item in phases.values():
        status = str((item or {}).get("status") or "skipped")
        counts[status] = counts.get(status, 0) + 1
    if counts.get("failed", 0) > 0:
        overall = "failed"
        exit_code = 1
    elif counts.get("skipped", 0) > 0:
        overall = "incomplete"
        exit_code = 2
    elif counts.get("passed_with_warnings", 0) > 0:
        overall = "passed_with_warnings"
        exit_code = 0
    elif counts.get("dry_run", 0) > 0:
        overall = "dry_run"
        exit_code = 0
    else:
        overall = "passed"
        exit_code = 0
    return {
        "overall_status": overall,
        "exit_code": exit_code,
        "status_counts": counts,
    }

def _write_markdown(report: dict[str, Any], markdown_path: Path) -> None:
    lines = [
        "# Vector P0-P4 Acceptance Report",
        "",
        f"- generated_at: {report.get('finished_at')}",
        f"- overall_status: {((report.get('summary') or {}).get('overall_status'))}",
        f"- exit_code: {((report.get('summary') or {}).get('exit_code'))}",
        f"- pgvector_enabled: {((report.get('environment') or {}).get('pgvector_enabled'))}",
        f"- vector_backend: {((report.get('environment') or {}).get('vector_backend'))}",
        "",
        "## Phases",
        "",
    ]
    for phase_name, item in (report.get("phases") or {}).items():
        phase = dict(item or {})
        lines.extend(
            [
                f"### {phase_name}",
                "",
                f"- status: {phase.get('status')}",
                f"- summary: {phase.get('summary')}",
                "",
            ]
        )
    markdown_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
