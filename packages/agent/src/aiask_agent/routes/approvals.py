from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request


def create_approvals_router(
    *,
    require_full: Callable[[Request], Any],
    approval_store_factory: Callable[[], Any],
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/approvals")
    async def approvals(request: Request, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": approval_store_factory().list(status=status, limit=limit)}

    @router.post("/v1/approvals/{approval_id}/{decision}")
    async def approval_decide(request: Request, approval_id: str, decision: str) -> dict[str, Any]:
        require_full(request)
        payload = await request.json()
        item = approval_store_factory().decide(
            approval_id,
            approved=decision == "approve",
            reason=payload.get("reason"),
        )
        if item is None:
            raise HTTPException(404, detail=f"approval not found: {approval_id}")
        return {"object": "approval", **item}

    return router
