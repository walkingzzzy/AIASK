"""Persistence helpers for strategy factory optional storage operations.

This module centralises optional persistence calls that may or may not be
supported by the underlying db adapter, replacing ad-hoc ``_call_optional_async``
patterns scattered across the application layer.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def _maybe_await(result: Any) -> Any:
    if inspect.isawaitable(result):
        return await result
    return result


class FactoryPersistenceHelper:
    """Wraps optional persistence calls with explicit failure tracking.

    Usage::

        helper = FactoryPersistenceHelper(db, persistence_failures, stage="autonomy")
        row = await helper.save_strategy_task_run(payload)
        await helper.update_strategy_task_run(task_run_id, status="completed", result=result)
    """

    def __init__(
        self,
        db: Any,
        persistence_failures: list[dict[str, Any]],
        stage: str = "unknown",
    ) -> None:
        self._db = db
        self._failures = persistence_failures
        self._stage = stage

    def _record_failure(self, operation: str, exc: Exception) -> None:
        self._failures.append(
            {
                "operation": operation,
                "stage": self._stage,
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )

    async def _call_optional(
        self,
        method_name: str,
        *args: Any,
        default: Any = None,
        **kwargs: Any,
    ) -> Any:
        method = getattr(self._db, method_name, None)
        if not callable(method):
            return default
        try:
            return await _maybe_await(method(*args, **kwargs))
        except (StopIteration, StopAsyncIteration):
            return default
        except Exception as exc:
            self._record_failure(method_name, exc)
            return default

    async def _call_required(
        self,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Call a method that must exist; record failure but do not raise."""
        method = getattr(self._db, method_name, None)
        if not callable(method):
            logger.warning(
                "FactoryPersistence: db does not expose %s (stage=%s)",
                method_name,
                self._stage,
            )
            self._failures.append(
                {
                    "operation": method_name,
                    "stage": self._stage,
                    "error_type": "MissingMethod",
                    "error": f"db does not expose {method_name}",
                }
            )
            return None
        try:
            return await _maybe_await(method(*args, **kwargs))
        except Exception as exc:
            logger.warning(
                "FactoryPersistence: %s failed (stage=%s): %s",
                method_name,
                self._stage,
                exc,
            )
            self._record_failure(method_name, exc)
            return None

    # ------------------------------------------------------------------
    # Factory run persistence (hard dependencies per P2 contract)
    # ------------------------------------------------------------------

    async def save_strategy_factory_run(self, results: dict[str, Any]) -> Any:
        return await self._call_required("save_strategy_factory_run", results)

    async def save_daily_snapshot(self, snapshot_date: Any, snapshot: dict[str, Any]) -> Any:
        return await self._call_required("save_daily_snapshot", snapshot_date, snapshot)

    async def save_strategy_factory_run_artifact(self, payload: dict[str, Any]) -> Any:
        return await self._call_optional("save_strategy_factory_run_artifact", payload, default=None)

    async def list_strategy_factory_run_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        result = await self._call_optional("list_strategy_factory_run_artifacts", run_id, default=[])
        return list(result or [])

    async def create_strategy_factory_dispatch(self, payload: dict[str, Any]) -> Any:
        return await self._call_optional("create_strategy_factory_dispatch", payload, default=None)

    async def update_strategy_factory_dispatch(self, dispatch_id: str, **kwargs: Any) -> Any:
        return await self._call_optional(
            "update_strategy_factory_dispatch",
            dispatch_id,
            default=None,
            **kwargs,
        )

    async def get_strategy_factory_dispatch(self, dispatch_id: str) -> Optional[dict[str, Any]]:
        result = await self._call_optional("get_strategy_factory_dispatch", dispatch_id, default=None)
        return result if isinstance(result, dict) else None

    # ------------------------------------------------------------------
    # Task-run tracking (semi-hard; failure is recorded but run continues)
    # ------------------------------------------------------------------

    async def save_strategy_task_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self._call_optional("save_strategy_task_run", payload, default={"id": None})
        return result if isinstance(result, dict) else {"id": None}

    async def update_strategy_task_run(self, task_run_id: Any, **kwargs: Any) -> None:
        if task_run_id is None:
            return
        await self._call_optional("update_strategy_task_run", task_run_id, **kwargs, default=None)

    # ------------------------------------------------------------------
    # Optional evidence / evidence persistence
    # ------------------------------------------------------------------

    async def save_factory_task_evidence(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        result = await self._call_optional("save_factory_task_evidence", payload, default=None)
        return result if isinstance(result, dict) else None

    async def save_strategy_candidate_evidence(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        result = await self._call_optional("save_strategy_candidate_evidence", payload, default=None)
        return result if isinstance(result, dict) else None

    async def save_strategy_signal_evidence(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        result = await self._call_optional("save_strategy_signal_evidence", payload, default=None)
        return result if isinstance(result, dict) else None

    async def save_strategy_generation_experiment(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        result = await self._call_optional("save_strategy_generation_experiment", payload, default=None)
        return result if isinstance(result, dict) else None

    async def save_factory_theme_definition(self, payload: dict[str, Any]) -> None:
        await self._call_optional("save_factory_theme_definition", payload, default=None)


def check_hard_dependencies(db: Any) -> list[str]:
    """Return list of missing hard-dependency method names on *db*.

    Call this at run entry to surface dependency gaps before execution begins.
    """
    hard_deps = [
        "save_strategy_factory_run",
        "save_daily_snapshot",
        "save_strategy",
        "save_strategy_quality_report",
        "save_strategy_task_run",
        "update_strategy_task_run",
    ]
    return [name for name in hard_deps if not callable(getattr(db, name, None))]


__all__ = [
    "FactoryPersistenceHelper",
    "check_hard_dependencies",
]
