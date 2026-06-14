from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request


def create_run_control_router(
    *,
    require_api: Callable[[Request], None],
    require_full: Callable[[Request], Any],
    session_store: Any,
    truthy: Callable[[Any], bool],
) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/runs/{run_id}/cancel")
    async def run_cancel(request: Request, run_id: str) -> dict[str, Any]:
        require_api(request)
        item = session_store.get_run(run_id)
        if item is None:
            raise HTTPException(404, detail=f"run not found: {run_id}")
        payload = dict(item.get("payload") or {})
        payload["cancelled_at"] = int(time.time())
        session_store.update_run(run_id, status="cancelled", payload=payload)
        event = session_store.append_run_event(run_id, "run.cancelled", {"reason": "api_request"})
        return {"object": "run", "run_id": run_id, "status": "cancelled", "event": event}

    @router.post("/v1/runs/{run_id}/stop")
    async def run_stop(request: Request, run_id: str) -> dict[str, Any]:
        return await run_cancel(request, run_id)

    @router.post("/v1/runs/{run_id}/steer")
    async def run_steer(request: Request, run_id: str) -> dict[str, Any]:
        require_api(request)
        item = session_store.get_run(run_id)
        if item is None:
            raise HTTPException(404, detail=f"run not found: {run_id}")
        payload = await request.json()
        instruction = str(dict(payload or {}).get("instruction") or "").strip()
        if not instruction:
            raise HTTPException(400, detail="instruction is required")
        event = session_store.append_run_event(run_id, "run.steer", {"instruction": instruction})
        return {"object": "run.steer", "run_id": run_id, "event": event}

    @router.post("/v1/sessions/{session_id}/undo")
    async def session_undo(request: Request, session_id: str) -> dict[str, Any]:
        require_full(request)
        try:
            payload = dict(await request.json() or {})
        except Exception:
            payload = {}
        result = session_store.undo_last_turns(
            session_id,
            turns=payload.get("turns") or 1,
            reason=str(payload.get("reason") or "hermes_undo"),
            deleted_by=str(payload.get("deleted_by") or payload.get("user_id") or "control_token"),
        )
        return {"object": "aiask.session_undo", "implementation": "aiask_native", **result}

    @router.post("/v1/sessions/{session_id}/archive")
    async def session_archive(request: Request, session_id: str) -> dict[str, Any]:
        require_full(request)
        try:
            payload = dict(await request.json() or {})
        except Exception:
            payload = {}
        archived = truthy(payload.get("archived", True))
        try:
            result = session_store.set_session_archived(
                session_id,
                archived=archived,
                reason=str(payload.get("reason") or ("desktop archive" if archived else "desktop unarchive")),
                actor=str(payload.get("actor") or payload.get("user_id") or "control_token"),
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, detail=str(exc)) from exc
        return {"object": "aiask.session_archive", "implementation": "aiask_native", **result}

    return router
