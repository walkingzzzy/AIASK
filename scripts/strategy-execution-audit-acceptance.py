#!/usr/bin/env python3
"""Run real execution-audit acceptance against the configured TimescaleDB."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
for relative in ("packages/akshare-mcp/src", "packages/strategy-factory/src"):
    path = ROOT_DIR / relative
    if path.exists():
        sys.path.insert(0, str(path))

from akshare_mcp.env_loader import load_mcp_env
from akshare_mcp.storage import get_db, run_with_db_cleanup


ACCEPTANCE_REPORT_TYPE = "execution_audit_acceptance"
ACCEPTANCE_REPORT_SCHEMA_VERSION = "execution_audit_acceptance.v2"
SAMPLE_GAP_CATEGORY = "sample_gap"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _normalize_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _unique_tokens(values) -> list[str]:
    tokens: list[str] = []
    for item in list(values or []):
        token = str(item or "").strip()
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def _normalize_detail_dimension(
    *,
    top_level_values,
    blocker_details: list[dict[str, Any]],
    detail_key: str,
    field_name: str,
    strategy_id: str,
) -> list[str]:
    direct = _unique_tokens(top_level_values)
    derived = _unique_tokens(item.get(detail_key) for item in blocker_details)
    if direct and derived and set(direct) != set(derived):
        raise ValueError(
            "execution_audit_acceptance contract mismatch for "
            f"{strategy_id or '<unknown>'}: {field_name}={sorted(direct)} detail_{field_name}={sorted(derived)}"
        )
    return direct or derived


async def _select_runtime_evidence_strategy_ids(
    db,
    *,
    statuses: list[str],
    limit: int,
    offset: int,
) -> list[str]:
    acquire = getattr(db, "acquire", None)
    if not callable(acquire):
        return []

    normalized_statuses = [item.strip().lower() for item in list(statuses or []) if item.strip()]
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH runtime_counts AS (
                SELECT
                    s.id,
                    s.created_at,
                    s.status,
                    COALESCE((SELECT COUNT(*) FROM paper_orders po WHERE po.strategy_id = s.id), 0)::int AS order_count,
                    COALESCE((SELECT COUNT(*) FROM paper_trades pt WHERE pt.strategy_id = s.id), 0)::int AS trade_count,
                    COALESCE((SELECT COUNT(*) FROM strategy_trade_positions stp WHERE stp.strategy_id = s.id), 0)::int AS position_count
                FROM strategies s
                WHERE (
                    COALESCE(array_length($1::text[], 1), 0) = 0
                    OR lower(COALESCE(s.status, '')) = ANY($1::text[])
                )
            )
            SELECT id
            FROM runtime_counts
            WHERE order_count > 0 OR trade_count > 0 OR position_count > 0
            ORDER BY (order_count + trade_count + position_count) DESC, created_at DESC
            OFFSET $2
            LIMIT $3
            """,
            normalized_statuses,
            max(0, int(offset or 0)),
            max(1, int(limit or 20)),
        )
    return [str(row.get("id") or "").strip() for row in rows if str(row.get("id") or "").strip()]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    global_verification = dict(report.get("global_verification") or {})
    global_schema = dict(global_verification.get("schema") or {})
    global_migrations = dict(global_verification.get("migrations") or {})
    summary = dict(report.get("summary") or {})
    strategy_rows = list(report.get("strategy_results") or [])

    lines = [
        "# Execution Audit Acceptance",
        "",
        f"- Generated at: {report.get('finished_at') or _now_iso()}",
        f"- Database URL source: {report.get('env_source') or 'unknown'}",
        f"- Report schema: {report.get('schema_version') or ACCEPTANCE_REPORT_SCHEMA_VERSION}",
        f"- Global schema ready: {bool(global_schema.get('all_required_tables_present') and global_schema.get('all_required_columns_present'))}",
        f"- Global migration ready: {bool(global_migrations.get('all_required_keys_applied'))}",
        f"- Strategies included: {summary.get('strategy_count', 0)}",
        f"- Strategies checked: {summary.get('checked_strategy_count', summary.get('strategy_count', 0))}",
        f"- Strategies excluded: {summary.get('excluded_strategy_count', 0)}",
        f"- Strategies ready: {summary.get('ready_count', 0)}",
        f"- Sample-gap strategies: {summary.get('sample_gap_strategy_count', 0)}",
        f"- Overall ready: {bool(summary.get('overall_ready'))}",
        "",
        "## Strategies",
        "",
        "| Strategy | Status | Strategy Status | Included | Overall | Sample Gap | Gap Categories | Blockers | TODO Count |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for row in strategy_rows:
        blockers = ", ".join(row.get("blockers") or []) or "-"
        gap_categories = ", ".join(row.get("gap_categories") or []) or "-"
        lines.append(
            f"| {row.get('strategy_id') or '-'} | {row.get('status') or '-'} | "
            f"{row.get('strategy_status') or '-'} | "
            f"{'no' if row.get('excluded_from_acceptance') else 'yes'} | "
            f"{'ready' if row.get('overall_ready') else 'pending'} | "
            f"{'yes' if row.get('has_sample_gap') else 'no'} | {gap_categories} | "
            f"{blockers} | {int(row.get('todo_count') or 0)} |"
        )

    if not strategy_rows:
        lines.append("| - | - | - | - | - | - | - | - | - |")

    top_blockers = list(summary.get("top_blockers") or [])
    if top_blockers:
        lines.extend(["", "## Top Blockers", ""])
        for item in top_blockers:
            lines.append(f"- {item.get('blocker')}: {item.get('count')}")

    top_gap_categories = list(summary.get("top_gap_categories") or [])
    if top_gap_categories:
        lines.extend(["", "## Top Gap Categories", ""])
        for item in top_gap_categories:
            lines.append(f"- {item.get('category')}: {item.get('count')}")

    lines.extend(["", "## Actionable TODOs", ""])
    emitted_todos: set[str] = set()
    for row in strategy_rows:
        for todo in row.get("actionable_todos") or []:
            token = str(todo or "").strip()
            if not token or token in emitted_todos:
                continue
            emitted_todos.add(token)
            lines.append(f"- {token}")
    if not emitted_todos:
        lines.append("- None")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _async_main(args: argparse.Namespace) -> int:
    started_at = _now_iso()
    env_path = load_mcp_env(override=False)
    db = get_db()
    report_dir = Path(args.report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    version_tag = args.version_tag or _now().strftime("exec_audit_%Y%m%d_%H%M%S")

    if not hasattr(db, "get_execution_audit_verification") or not hasattr(db, "run_execution_audit_acceptance"):
        raise RuntimeError("Configured DB adapter does not expose execution-audit acceptance APIs")

    strategy_ids = _normalize_csv(args.strategy_ids)
    statuses = _normalize_csv(args.statuses) or ["listed", "incubating"]
    limit = max(1, int(args.limit or 20))
    offset = max(0, int(args.offset or 0))

    if not strategy_ids:
        if args.selection_mode == "runtime_evidence":
            strategy_ids = await _select_runtime_evidence_strategy_ids(
                db,
                statuses=statuses,
                limit=limit,
                offset=offset,
            )
        if not strategy_ids:
            rows = await db.list_strategies(status=statuses, limit=limit, offset=offset)
            strategy_ids = [str(item.get("id") or "").strip() for item in rows if str(item.get("id") or "").strip()]

    global_verification = await db.get_execution_audit_verification(strategy_id=None)
    strategy_results: list[dict[str, Any]] = []
    blocker_counter: Counter[str] = Counter()
    gap_category_counter: Counter[str] = Counter()
    excluded_statuses = {
        item.strip().lower()
        for item in _normalize_csv(args.exclude_statuses)
        if item.strip()
    }

    for strategy_id in strategy_ids:
        actual_strategy_status = ""
        try:
            strategy_row = await db.get_strategy(strategy_id)
            actual_strategy_status = str((strategy_row or {}).get("status") or "").strip().lower()
        except Exception:
            actual_strategy_status = ""
        result = await db.run_execution_audit_acceptance(
            strategy_id=strategy_id,
            backfill=bool(args.backfill),
        )
        blocker_details = [
            dict(item)
            for item in list(result.get("blocker_details") or [])
            if isinstance(item, dict)
        ]
        acceptance_matrix = dict(result.get("acceptance_matrix") or {})
        blockers = _normalize_detail_dimension(
            top_level_values=result.get("blockers"),
            blocker_details=blocker_details,
            detail_key="blocker",
            field_name="blockers",
            strategy_id=strategy_id,
        )
        gap_categories = _normalize_detail_dimension(
            top_level_values=result.get("gap_categories"),
            blocker_details=blocker_details,
            detail_key="category",
            field_name="gap_categories",
            strategy_id=strategy_id,
        )
        actionable_todos = _normalize_detail_dimension(
            top_level_values=result.get("actionable_todos"),
            blocker_details=blocker_details,
            detail_key="todo",
            field_name="actionable_todos",
            strategy_id=strategy_id,
        )
        excluded_from_acceptance = bool(
            actual_strategy_status and actual_strategy_status in excluded_statuses
        )
        if not excluded_from_acceptance:
            blocker_counter.update(blockers)
            gap_category_counter.update(gap_categories)
        strategy_results.append(
            {
                "strategy_id": strategy_id,
                "status": str(result.get("status") or ""),
                "strategy_status": actual_strategy_status or None,
                "excluded_from_acceptance": excluded_from_acceptance,
                "exclusion_reason": (
                    f"strategy_status:{actual_strategy_status}"
                    if excluded_from_acceptance
                    else None
                ),
                "overall_ready": bool(acceptance_matrix.get("overall_ready")),
                "has_sample_gap": SAMPLE_GAP_CATEGORY in gap_categories,
                "acceptance_matrix": acceptance_matrix,
                "blockers": blockers,
                "blocker_details": blocker_details,
                "gap_categories": gap_categories,
                "actionable_todos": actionable_todos,
                "todo_count": len(actionable_todos),
                "recommendation_count": len(list(result.get("recommendations") or [])),
                "result": _json_safe(result),
            }
        )

    global_schema_ready = bool(
        dict(global_verification.get("schema") or {}).get("all_required_tables_present")
        and dict(global_verification.get("schema") or {}).get("all_required_columns_present")
    )
    global_migration_ready = bool(
        dict(global_verification.get("migrations") or {}).get("all_required_keys_applied")
    )
    included_strategy_results = [
        item for item in strategy_results if not item.get("excluded_from_acceptance")
    ]
    ready_count = sum(1 for item in included_strategy_results if item.get("overall_ready"))
    sample_gap_strategy_count = sum(1 for item in included_strategy_results if item.get("has_sample_gap"))
    overall_ready = global_schema_ready and global_migration_ready and (
        not included_strategy_results or ready_count == len(included_strategy_results)
    )

    report = {
        "report_type": ACCEPTANCE_REPORT_TYPE,
        "schema_version": ACCEPTANCE_REPORT_SCHEMA_VERSION,
        "started_at": started_at,
        "finished_at": _now_iso(),
        "version_tag": version_tag,
        "env_source": str(env_path) if env_path else None,
        "arguments": _json_safe(vars(args)),
        "global_verification": _json_safe(global_verification),
        "strategy_results": strategy_results,
        "summary": {
            "strategy_count": len(included_strategy_results),
            "checked_strategy_count": len(strategy_results),
            "excluded_strategy_count": len(strategy_results) - len(included_strategy_results),
            "excluded_statuses": sorted(excluded_statuses),
            "ready_count": ready_count,
            "pending_count": len(included_strategy_results) - ready_count,
            "sample_gap_strategy_count": sample_gap_strategy_count,
            "global_schema_ready": global_schema_ready,
            "global_migration_ready": global_migration_ready,
            "overall_ready": overall_ready,
            "top_blockers": [
                {"blocker": blocker, "count": count}
                for blocker, count in blocker_counter.most_common(10)
            ],
            "top_gap_categories": [
                {"category": category, "count": count}
                for category, count in gap_category_counter.most_common(10)
            ],
            "exit_code": 0 if overall_ready or not args.fail_on_blockers else 1,
        },
    }

    json_path = report_dir / f"execution_audit_acceptance_{version_tag}.json"
    md_path = report_dir / f"execution_audit_acceptance_{version_tag}.md"
    json_path.write_text(json.dumps(_json_safe(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_markdown(report, md_path)

    print(f"overall_ready: {report['summary']['overall_ready']}")
    print(f"strategy_count: {report['summary']['strategy_count']}")
    print(f"ready_count: {report['summary']['ready_count']}")
    print(f"report_json: {json_path}")
    print(f"report_md: {md_path}")
    for item in strategy_results:
        print(
            f"{item['strategy_id']}: {item['status']} | "
            f"{'ready' if item['overall_ready'] else 'pending'} | blockers={len(item['blockers'])}"
        )
    return int(report["summary"]["exit_code"])


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run execution-audit acceptance against the configured TimescaleDB."
    )
    parser.add_argument("--strategy-ids", default="", help="Comma-separated strategy IDs. Empty means auto-select by status.")
    parser.add_argument("--statuses", default="listed,incubating", help="Comma-separated statuses used when strategy IDs are omitted.")
    parser.add_argument("--limit", type=int, default=20, help="Max strategies to inspect when auto-selecting.")
    parser.add_argument("--offset", type=int, default=0, help="Auto-selection offset.")
    parser.add_argument(
        "--selection-mode",
        choices=("status", "runtime_evidence"),
        default="status",
        help="How to auto-select strategies when --strategy-ids is omitted.",
    )
    parser.add_argument("--backfill", action="store_true", help="Run linkage/fill backfill before acceptance.")
    parser.add_argument(
        "--exclude-statuses",
        default="rejected,archived,deprecated",
        help="Comma-separated strategy statuses to report but exclude from the overall acceptance denominator.",
    )
    parser.add_argument("--fail-on-blockers", action="store_true", help="Exit non-zero unless all selected strategies are ready.")
    parser.add_argument(
        "--report-dir",
        default=str(ROOT_DIR / "reports" / "execution-audit-acceptance"),
        help="Directory for JSON/Markdown acceptance reports.",
    )
    parser.add_argument("--version-tag", default="", help="Optional report version tag.")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return int(run_with_db_cleanup(_async_main(args)))


if __name__ == "__main__":
    raise SystemExit(main())
