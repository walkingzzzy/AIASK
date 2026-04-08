"""策略工厂机会扫描与研究任务生成。"""

from __future__ import annotations

from typing import Any, Dict, List

from ..domain.constants import AUTONOMY_MAX_RESEARCH_TASKS, OPPORTUNITY_UNIVERSE_LIMIT
from ._stock_universe_loader import load_stock_universe_rows
from ._opportunity_event import _MarketOpportunityScannerEventMixin
from ._opportunity_snapshot import _MarketOpportunityScannerSnapshotMixin
from ._opportunity_utils import _MarketOpportunityScannerUtilityMixin
from .research_plane_contract import build_task_artifact


class MarketOpportunityScanner(
    _MarketOpportunityScannerUtilityMixin,
    _MarketOpportunityScannerEventMixin,
    _MarketOpportunityScannerSnapshotMixin,
):
    """根据市场快照与事件证据生成自治研究任务。"""

    def __init__(self):
        self.last_report: dict = {
            "summary": {"task_count": 0, "task_types": {}, "themes": [], "task_sources": {}},
            "tasks": [],
        }

    def get_last_report(self) -> dict:
        return dict(self.last_report)

    async def scan(self, db, snapshot: dict[str, Any]) -> dict[str, Any]:
        snapshot = dict(snapshot or {})
        universe_page_size = max(100, min(int(OPPORTUNITY_UNIVERSE_LIMIT), 1000))
        try:
            universe_rows, universe_meta = await load_stock_universe_rows(
                db,
                limit=OPPORTUNITY_UNIVERSE_LIMIT,
                page_size=universe_page_size,
                start_offset=0,
            )
        except Exception:
            universe_rows, universe_meta = [], {
                "pages_loaded": 0,
                "loaded_count": 0,
                "complete": False,
                "truncated": False,
                "page_size": universe_page_size,
            }

        rows = [dict(item or {}) for item in list(universe_rows or [])]
        tasks: List[dict] = []

        event_tasks = self._deduplicate_tasks(self._build_event_driven_tasks(snapshot, rows))
        snapshot_tasks = self._deduplicate_tasks(self._build_snapshot_tasks(snapshot, rows))
        if event_tasks:
            tasks.extend(event_tasks)
            tasks.extend(self._select_snapshot_tasks_for_event_mix(event_tasks, snapshot_tasks))
        else:
            tasks.extend(snapshot_tasks)

        tasks = self._deduplicate_tasks(tasks)
        tasks.sort(key=self._task_sort_key, reverse=True)
        tasks = tasks[:AUTONOMY_MAX_RESEARCH_TASKS]
        task_sources = self._build_task_source_counts(tasks)

        type_counts: Dict[str, int] = {}
        for task in tasks:
            opportunity_type = str(task.get("opportunity_type") or "unknown")
            type_counts[opportunity_type] = type_counts.get(opportunity_type, 0) + 1

        report = {
            "summary": {
                "task_count": len(tasks),
                "task_types": type_counts,
                "themes": [str(item.get("theme") or "") for item in tasks],
                "task_sources": dict(task_sources),
                "event_task_count": len([item for item in tasks if item.get("task_source") == "event_driven"]),
                "max_tasks": AUTONOMY_MAX_RESEARCH_TASKS,
                "universe_limit": int(OPPORTUNITY_UNIVERSE_LIMIT),
                "universe_page_size": int(universe_meta.get("page_size") or universe_page_size),
                "universe_row_count": len(rows),
                "universe_pages_loaded": int(universe_meta.get("pages_loaded") or 0),
                "universe_complete": bool(universe_meta.get("complete")),
                "universe_truncated": bool(universe_meta.get("truncated")),
            },
            "tasks": tasks,
        }
        task_artifact = build_task_artifact(
            {
                "task_scan": report,
                "task_source_counts": dict(task_sources),
                "event_task_count": int(report["summary"].get("event_task_count") or 0),
                "snapshot_task_count": int(task_sources.get("snapshot") or 0),
                "bulk_stock_task_count": 0,
            }
        )
        report["task_artifact"] = task_artifact
        report["summary"] = {
            **dict(report.get("summary") or {}),
            "task_artifact_contract_version": task_artifact.get("contract_version"),
            "task_artifact_available": bool(task_artifact.get("available")),
        }
        self.last_report = report
        return self.get_last_report()


__all__ = ["MarketOpportunityScanner"]
