from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request


def create_learning_rl_router(
    *,
    require_full: Callable[[Request], Any],
    learning_loop_factory: Callable[[], Any],
    rl_manager_factory: Callable[[], Any],
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/learning/status")
    async def learning_status_api(request: Request) -> dict[str, Any]:
        require_full(request)
        return learning_loop_factory().status()

    @router.get("/v1/learning/review")
    async def learning_review_api(request: Request, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": learning_loop_factory().review(status=status, limit=limit)}

    @router.post("/v1/learning/apply")
    async def learning_apply_api(request: Request) -> dict[str, Any]:
        require_full(request)
        payload = dict(await request.json() or {})
        proposal = learning_loop_factory().apply(str(payload.get("proposal_id") or ""))
        return {"object": "learning.proposal", "data": proposal}

    @router.get("/v1/rl/environments")
    async def rl_environments_api(request: Request) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": rl_manager_factory().list_environments()}

    @router.get("/v1/rl/config")
    async def rl_config_api(request: Request) -> dict[str, Any]:
        require_full(request)
        return {"object": "rl.config", "data": rl_manager_factory().current_config()}

    @router.patch("/v1/rl/config")
    async def rl_config_patch_api(request: Request) -> dict[str, Any]:
        require_full(request)
        payload = dict(await request.json() or {})
        return {"object": "rl.config", "data": rl_manager_factory().edit_config(dict(payload.get("config") or payload.get("patch") or payload))}

    @router.get("/v1/rl/runs")
    async def rl_runs_api(request: Request, limit: int = 100) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": rl_manager_factory().list_runs(limit=limit)}

    @router.post("/v1/rl/runs")
    async def rl_run_create_api(request: Request) -> dict[str, Any]:
        require_full(request)
        payload = dict(await request.json() or {})
        data = rl_manager_factory().start_training(environment=payload.get("environment"), config_patch=dict(payload.get("config") or {}))
        return {"object": "rl.run", "data": data}

    @router.get("/v1/rl/runs/{run_id}")
    async def rl_run_get_api(request: Request, run_id: str) -> dict[str, Any]:
        require_full(request)
        return {"object": "rl.run", "data": rl_manager_factory().check_status(run_id)}

    @router.post("/v1/rl/runs/{run_id}/stop")
    async def rl_run_stop_api(request: Request, run_id: str) -> dict[str, Any]:
        require_full(request)
        return {"object": "rl.run", "data": rl_manager_factory().stop_training(run_id)}

    @router.get("/v1/rl/runs/{run_id}/results")
    async def rl_run_results_api(request: Request, run_id: str) -> dict[str, Any]:
        require_full(request)
        return {"object": "rl.results", "data": rl_manager_factory().results(run_id)}

    @router.get("/v1/rl/runs/{run_id}/logs")
    async def rl_run_logs_api(request: Request, run_id: str, max_bytes: int = 65536, tail: bool = True) -> dict[str, Any]:
        require_full(request)
        return {"object": "rl.logs", "data": rl_manager_factory().logs(run_id, max_bytes=max_bytes, tail=tail)}

    return router
