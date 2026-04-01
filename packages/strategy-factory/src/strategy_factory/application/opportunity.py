"""策略工厂机会扫描与研究任务生成。"""

from __future__ import annotations

import inspect
from typing import Any, Dict, List

from ..domain.constants import AUTONOMY_MAX_RESEARCH_TASKS
from ._opportunity_event import _MarketOpportunityScannerEventMixin
from ._opportunity_snapshot import _MarketOpportunityScannerSnapshotMixin
from ._opportunity_utils import _MarketOpportunityScannerUtilityMixin


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
        universe_rows: List[dict[str, Any]] = []
        list_stock_universe = getattr(db, "list_stock_universe", None)
        if callable(list_stock_universe):
            try:
                result = list_stock_universe(limit=120, offset=0)
                if inspect.isawaitable(result):
                    result = await result
                if isinstance(result, list):
                    universe_rows = result
                elif isinstance(result, tuple):
                    universe_rows = list(result)
                else:
                    try:
                        universe_rows = list(result or [])
                    except Exception:
                        universe_rows = []
            except Exception:
                universe_rows = []

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

        self.last_report = {
            "summary": {
                "task_count": len(tasks),
                "task_types": type_counts,
                "themes": [str(item.get("theme") or "") for item in tasks],
                "task_sources": dict(task_sources),
                "event_task_count": len([item for item in tasks if item.get("task_source") == "event_driven"]),
                "max_tasks": AUTONOMY_MAX_RESEARCH_TASKS,
            },
            "tasks": tasks,
        }
        return self.get_last_report()


__all__ = ["MarketOpportunityScanner"]
