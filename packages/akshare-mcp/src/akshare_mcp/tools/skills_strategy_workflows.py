"""Extracted strategy-factory skill workflows."""

from __future__ import annotations

from typing import Any, Dict, List

from . import skills_support as skill_support


def _skill_support():
    return skill_support


async def exec_strategy_factory(
    params: Dict[str, Any],
    *,
    runtime_strategy_manager,
) -> Dict[str, Any]:
    skill_support = _skill_support()

    task = str(params.get("task") or "factory_cycle").strip().lower()
    supported_tasks = ["factory_cycle", "strategy_review", "runtime_governance", "smoke_test"]
    if task not in supported_tasks:
        return skill_support._unsupported_task_result(task, supported_tasks)

    strategy_id = str(params.get("strategy_id") or params.get("id") or "").strip()
    limit = max(1, min(skill_support._safe_int(params.get("limit"), 5), 100))
    runtime_alert_limit = max(
        1,
        min(skill_support._safe_int(params.get("runtime_alert_limit"), 20), 100),
    )
    trigger_factory_run = bool(skill_support._parse_bool_flag(params.get("trigger_factory_run")))
    trigger_runtime_cycle = bool(skill_support._parse_bool_flag(params.get("trigger_runtime_cycle")))
    index_name = str(params.get("index_name") or "strategy_behavior").strip() or "strategy_behavior"

    steps: List[Dict[str, Any]] = []

    if task in {"factory_cycle", "smoke_test"}:
        status_resp = await runtime_strategy_manager(action="factory_status", params={})
        steps.append(skill_support._step_result("strategy_manager.factory_status", output=status_resp))
        capabilities_resp = await runtime_strategy_manager(action="capabilities", params={})
        steps.append(skill_support._step_result("strategy_manager.capabilities", output=capabilities_resp))
        if task != "smoke_test" and trigger_factory_run:
            run_resp = await runtime_strategy_manager(action="factory_run_once", params={})
            steps.append(skill_support._step_result("strategy_manager.factory_run_once", output=run_resp))
        runs_resp = await runtime_strategy_manager(action="factory_runs", params={"limit": limit})
        steps.append(skill_support._step_result("strategy_manager.factory_runs", output=runs_resp))
        if strategy_id:
            task_runs_resp = await runtime_strategy_manager(
                action="task_runs",
                params={"strategy_id": strategy_id, "limit": limit},
            )
            steps.append(skill_support._step_result("strategy_manager.task_runs", output=task_runs_resp))
        result = skill_support._finalize_skill_result(task, steps)
        result["summary"]["strategy_id"] = strategy_id or None
        result["summary"]["trigger_factory_run"] = trigger_factory_run if task != "smoke_test" else False
        return result

    if task == "strategy_review":
        rank_resp = await runtime_strategy_manager(
            action="rank",
            params={"status": "listed", "limit": limit},
        )
        steps.append(skill_support._step_result("strategy_manager.rank", output=rank_resp))
        if strategy_id:
            detail_resp = await runtime_strategy_manager(
                action="detail",
                params={"strategy_id": strategy_id},
            )
            steps.append(skill_support._step_result("strategy_manager.detail", output=detail_resp))
            review_report_resp = await runtime_strategy_manager(
                action="review_report",
                params={"strategy_id": strategy_id},
            )
            steps.append(
                skill_support._step_result(
                    "strategy_manager.review_report",
                    output=review_report_resp,
                )
            )
            events_resp = await runtime_strategy_manager(
                action="events",
                params={"strategy_id": strategy_id, "limit": limit},
            )
            steps.append(skill_support._step_result("strategy_manager.events", output=events_resp))
        else:
            list_resp = await runtime_strategy_manager(action="list", params={"limit": limit})
            steps.append(skill_support._step_result("strategy_manager.list", output=list_resp))
        result = skill_support._finalize_skill_result(task, steps)
        result["summary"]["strategy_id"] = strategy_id or None
        return result

    capabilities_resp = await runtime_strategy_manager(action="capabilities", params={})
    steps.append(skill_support._step_result("strategy_manager.capabilities", output=capabilities_resp))
    runtime_cycle_status_resp = await runtime_strategy_manager(
        action="runtime_cycle_status",
        params={},
    )
    steps.append(
        skill_support._step_result(
            "strategy_manager.runtime_cycle_status",
            output=runtime_cycle_status_resp,
        )
    )
    vector_health_resp = await runtime_strategy_manager(
        action="vector_health",
        params={"index_name": index_name, "limit_versions": limit},
    )
    steps.append(skill_support._step_result("strategy_manager.vector_health", output=vector_health_resp))
    if trigger_runtime_cycle:
        runtime_cycle_run_resp = await runtime_strategy_manager(action="runtime_cycle_run", params={})
        steps.append(
            skill_support._step_result(
                "strategy_manager.runtime_cycle_run",
                output=runtime_cycle_run_resp,
            )
        )
    if strategy_id:
        runtime_alerts_resp = await runtime_strategy_manager(
            action="runtime_alerts",
            params={"strategy_id": strategy_id, "limit": runtime_alert_limit},
        )
        steps.append(
            skill_support._step_result(
                "strategy_manager.runtime_alerts",
                output=runtime_alerts_resp,
            )
        )
        runtime_control_resp = await runtime_strategy_manager(
            action="runtime_control",
            params={"strategy_id": strategy_id},
        )
        steps.append(
            skill_support._step_result(
                "strategy_manager.runtime_control",
                output=runtime_control_resp,
            )
        )
        promotion_reviews_resp = await runtime_strategy_manager(
            action="promotion_reviews",
            params={"strategy_id": strategy_id, "limit": limit},
        )
        steps.append(
            skill_support._step_result(
                "strategy_manager.promotion_reviews",
                output=promotion_reviews_resp,
            )
        )
    else:
        vector_indexes_resp = await runtime_strategy_manager(
            action="vector_indexes",
            params={"index_name": index_name, "limit": limit},
        )
        steps.append(
            skill_support._step_result(
                "strategy_manager.vector_indexes",
                output=vector_indexes_resp,
            )
        )

    result = skill_support._finalize_skill_result(task, steps)
    result["summary"]["strategy_id"] = strategy_id or None
    result["summary"]["index_name"] = index_name
    result["summary"]["trigger_runtime_cycle"] = trigger_runtime_cycle
    return result
