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

from _vector_p0_p4_acceptance_support import *

async def _async_main(args: argparse.Namespace) -> int:
    report_dir = Path(args.report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    version_tag = str(args.version_tag or _now().strftime("acc_%Y%m%d_%H%M%S")).strip()

    report: dict[str, Any] = {
        "started_at": _now_iso(),
        "version_tag": version_tag,
        "root_dir": str(ROOT_DIR),
        "arguments": _json_safe(vars(args)),
        "phases": {},
    }

    db = get_db()
    try:
        p0 = await _check_p0_schema(db, require_pgvector=args.require_pgvector)
        report["phases"]["p0_schema"] = p0

        collection_inventory = await _get_collection_inventory(db)
        report["environment"] = {
            "pgvector_enabled": db.supports_pgvector(),
            "vector_backend": db.get_vector_backend(),
            "collection_count": len(collection_inventory),
            "collections": sorted(collection_inventory),
        }

        stock_codes = _normalize_csv(args.stock_codes)
        stock_code_source = "cli"
        if not stock_codes:
            stock_codes, stock_code_source = await _pick_codes_from_db(db, args.code_limit)
        report["selected_stock_codes"] = stock_codes
        report["selected_stock_code_source"] = stock_code_source

        market_doc_codes = list(stock_codes)
        market_doc_code_source = stock_code_source
        if stock_code_source != "cli":
            market_doc_codes, market_doc_code_source = await _pick_market_doc_codes_from_db(
                db,
                preferred_codes=stock_codes,
                doc_types=_normalize_csv(args.doc_types) or ["news", "notice", "research"],
                limit=max(1, min(len(stock_codes) or args.code_limit, args.code_limit)),
            )
        report["selected_market_doc_codes"] = market_doc_codes
        report["selected_market_doc_code_source"] = market_doc_code_source

        if not args.skip_strategy:
            try:
                report["phases"]["p1_strategy"] = await _run_strategy_phase(
                    db,
                    index_version=f"{version_tag}_strategy",
                    strategy_limit=args.strategy_limit,
                    strategy_statuses=_normalize_csv(args.strategy_statuses) or ["listed", "incubating"],
                    sample_size=args.sample_size,
                    top_k=args.top_k,
                    persist_snapshot_metrics=not args.no_persist_benchmark,
                )
            except Exception as exc:
                report["phases"]["p1_strategy"] = _build_phase("failed", summary=str(exc))

        if not args.skip_market_docs:
            try:
                report["phases"]["p2_market_docs"] = await _run_market_docs_phase(
                    db,
                    stock_codes=market_doc_codes,
                    doc_types=_normalize_csv(args.doc_types) or ["news", "notice", "research"],
                    version=f"{version_tag}_market",
                    index_version=f"{version_tag}_market_idx",
                    sample_size=args.sample_size,
                    top_k=args.top_k,
                    persist_snapshot_metrics=not args.no_persist_benchmark,
                    dry_run=args.dry_run,
                )
            except Exception as exc:
                report["phases"]["p2_market_docs"] = _build_phase("failed", summary=str(exc))

        if not args.skip_kline:
            try:
                report["phases"]["p3_kline_patterns"] = await _run_kline_phase(
                    db,
                    stock_codes=stock_codes,
                    version=f"{version_tag}_kline",
                    index_version=f"{version_tag}_kline_idx",
                    sample_size=args.sample_size,
                    top_k=args.top_k,
                    persist_snapshot_metrics=not args.no_persist_benchmark,
                    dry_run=args.dry_run,
                )
            except Exception as exc:
                report["phases"]["p3_kline_patterns"] = _build_phase("failed", summary=str(exc))

        if not args.skip_stock_profiles:
            try:
                report["phases"]["p4_stock_profiles"] = await _run_stock_profiles_phase(
                    db,
                    stock_codes=stock_codes,
                    version=f"{version_tag}_stock_profile",
                    index_version=f"{version_tag}_stock_profile_idx",
                    sample_size=args.sample_size,
                    top_k=args.top_k,
                    persist_snapshot_metrics=not args.no_persist_benchmark,
                    dry_run=args.dry_run,
                )
            except Exception as exc:
                report["phases"]["p4_stock_profiles"] = _build_phase("failed", summary=str(exc))

        if not args.skip_factor_candidates:
            try:
                report["phases"]["p4_factor_candidates"] = await _run_factor_candidates_phase(
                    db,
                    codes=_normalize_csv(args.factor_codes),
                    version=f"{version_tag}_factor_candidate",
                    index_version=f"{version_tag}_factor_candidate_idx",
                    factor_limit=args.factor_limit,
                    sample_size=args.sample_size,
                    top_k=args.top_k,
                    persist_snapshot_metrics=not args.no_persist_benchmark,
                    dry_run=args.dry_run,
                )
            except Exception as exc:
                report["phases"]["p4_factor_candidates"] = _build_phase("failed", summary=str(exc))

        report["finished_at"] = _now_iso()
        report["summary"] = _summarize(report["phases"])

        json_path = report_dir / f"vector_p0_p4_acceptance_{version_tag}.json"
        md_path = report_dir / f"vector_p0_p4_acceptance_{version_tag}.md"
        json_path.write_text(json.dumps(_json_safe(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _write_markdown(report, md_path)

        print(f"overall_status: {report['summary']['overall_status']}")
        print(f"exit_code: {report['summary']['exit_code']}")
        print(f"report_json: {json_path}")
        print(f"report_md: {md_path}")
        for phase_name, item in report["phases"].items():
            print(f"{phase_name}: {item.get('status')} | {item.get('summary')}")
        return int(report["summary"]["exit_code"])
    except Exception as exc:
        failed_report = {
            **report,
            "finished_at": _now_iso(),
            "summary": {"overall_status": "failed", "exit_code": 1, "status_counts": {"failed": 1}},
            "fatal_error": str(exc),
        }
        json_path = report_dir / f"vector_p0_p4_acceptance_{version_tag}_fatal.json"
        json_path.write_text(json.dumps(_json_safe(failed_report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"fatal_error: {exc}")
        print(f"report_json: {json_path}")
        return 1

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run P0-P4 vector acceptance against the live database.")
    parser.add_argument("--stock-codes", default="", help="Comma-separated stock codes for P2-P4 phases.")
    parser.add_argument("--factor-codes", default="", help="Comma-separated codes to scope factor candidate backfill.")
    parser.add_argument("--doc-types", default="news,notice,research", help="Comma-separated market document types.")
    parser.add_argument("--code-limit", type=int, default=20, help="Auto-detected stock code limit when --stock-codes is empty.")
    parser.add_argument("--strategy-limit", type=int, default=200, help="Max strategies to rebuild for P1.")
    parser.add_argument("--factor-limit", type=int, default=200, help="Max factor candidates to backfill for P4.")
    parser.add_argument("--strategy-statuses", default="listed,incubating", help="Strategy statuses included in P1 rebuild.")
    parser.add_argument("--sample-size", type=int, default=10, help="Benchmark query sample size.")
    parser.add_argument("--top-k", type=int, default=5, help="Benchmark top-k.")
    parser.add_argument("--version-tag", default="", help="Optional version tag prefix for backfill/snapshot artifacts.")
    parser.add_argument("--report-dir", default=str(ROOT_DIR / "reports" / "vector-acceptance"), help="Directory for JSON/Markdown reports.")
    parser.add_argument("--dry-run", action="store_true", help="Run backfill phases in dry-run mode.")
    parser.add_argument("--skip-strategy", action="store_true", help="Skip P1 strategy unified rebuild.")
    parser.add_argument("--skip-market-docs", action="store_true", help="Skip P2 market docs backfill.")
    parser.add_argument("--skip-kline", action="store_true", help="Skip P3 kline pattern backfill.")
    parser.add_argument("--skip-stock-profiles", action="store_true", help="Skip P4 stock profile backfill.")
    parser.add_argument("--skip-factor-candidates", action="store_true", help="Skip P4 factor candidate backfill.")
    parser.add_argument("--no-persist-benchmark", action="store_true", help="Do not write benchmark metrics back to snapshots.")
    parser.add_argument("--require-pgvector", action="store_true", help="Fail P0 when pgvector extension is unavailable.")
    return parser

def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return int(run_with_db_cleanup(_async_main(args)))
