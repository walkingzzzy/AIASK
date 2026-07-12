from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile


DesktopAssetCall = Callable[[str, str, dict[str, Any] | None], Awaitable[dict[str, Any]]]
DesktopFileUpload = Callable[[list[UploadFile], dict[str, Any] | None], Awaitable[dict[str, Any]]]


def _raise_http_error(result: dict[str, Any]) -> None:
    detail = result.get("error") or "desktop asset request failed"
    error_code = str(result.get("error_code") or "")
    status = 400
    if error_code.endswith("NOT_FOUND"):
        status = 404
    elif error_code.endswith("UPSTREAM_UNAVAILABLE"):
        status = 503
    elif error_code.endswith("UNAUTHORIZED"):
        status = 401
    raise HTTPException(status_code=status, detail=detail)


def _empty_asset_list(user_id: str, resource: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "object": "desktop.asset",
        "success": True,
        "data": [],
        "error": None,
        "error_code": None,
        "meta": {
            "user_id": user_id,
            "resource": resource,
            "degraded": True,
            "reason": result.get("error_code") or result.get("error") or "desktop_asset_empty",
        },
        "secrets_redacted": True,
    }


def _is_missing_asset_collection(result: dict[str, Any]) -> bool:
    return str(result.get("error_code") or "") in {"DESKTOP_API_NOT_FOUND", "DESKTOP_API_UPSTREAM_UNAVAILABLE"}


def create_desktop_assets_router(
    *,
    require_api: Callable[[Request], None],
    require_full: Callable[[Request], Any],
    desktop_asset_call: DesktopAssetCall,
    desktop_file_upload: DesktopFileUpload,
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/desktop/users/{user_id}/strategies")
    async def desktop_user_strategies(request: Request, user_id: str) -> dict[str, Any]:
        require_api(request)
        result = await desktop_asset_call("GET", f"/v1/users/{user_id}/strategies", None)
        if not result.get("success"):
            if _is_missing_asset_collection(result):
                return _empty_asset_list(user_id, "strategies", result)
            _raise_http_error(result)
        return result

    @router.post("/v1/desktop/users/{user_id}/strategies")
    async def desktop_user_strategy_create(request: Request, user_id: str) -> dict[str, Any]:
        require_full(request)
        result = await desktop_asset_call("POST", f"/v1/users/{user_id}/strategies", dict(await request.json() or {}))
        if not result.get("success"):
            _raise_http_error(result)
        return result

    @router.patch("/v1/desktop/users/{user_id}/strategies/{strategy_id}")
    async def desktop_user_strategy_update(request: Request, user_id: str, strategy_id: str) -> dict[str, Any]:
        require_full(request)
        result = await desktop_asset_call("PATCH", f"/v1/users/{user_id}/strategies/{strategy_id}", dict(await request.json() or {}))
        if not result.get("success"):
            _raise_http_error(result)
        return result

    @router.delete("/v1/desktop/users/{user_id}/strategies/{strategy_id}")
    async def desktop_user_strategy_delete(request: Request, user_id: str, strategy_id: str) -> dict[str, Any]:
        require_full(request)
        result = await desktop_asset_call("DELETE", f"/v1/users/{user_id}/strategies/{strategy_id}", None)
        if not result.get("success"):
            _raise_http_error(result)
        return result

    @router.post("/v1/desktop/users/{user_id}/strategies/reorder")
    async def desktop_user_strategy_reorder(request: Request, user_id: str) -> dict[str, Any]:
        require_full(request)
        result = await desktop_asset_call("POST", f"/v1/users/{user_id}/strategies/reorder", dict(await request.json() or {}))
        if not result.get("success"):
            _raise_http_error(result)
        return result

    @router.get("/v1/desktop/users/{user_id}/stock-pools")
    async def desktop_user_stock_pools(request: Request, user_id: str) -> dict[str, Any]:
        require_api(request)
        result = await desktop_asset_call("GET", f"/v1/users/{user_id}/stock-pools", None)
        if not result.get("success"):
            if _is_missing_asset_collection(result):
                return _empty_asset_list(user_id, "stock_pools", result)
            _raise_http_error(result)
        return result

    @router.post("/v1/desktop/users/{user_id}/stock-pools")
    async def desktop_user_stock_pool_create(request: Request, user_id: str) -> dict[str, Any]:
        require_full(request)
        result = await desktop_asset_call("POST", f"/v1/users/{user_id}/stock-pools", dict(await request.json() or {}))
        if not result.get("success"):
            _raise_http_error(result)
        return result

    @router.patch("/v1/desktop/users/{user_id}/stock-pools/{pool_id}")
    async def desktop_user_stock_pool_update(request: Request, user_id: str, pool_id: str) -> dict[str, Any]:
        require_full(request)
        result = await desktop_asset_call("PATCH", f"/v1/users/{user_id}/stock-pools/{pool_id}", dict(await request.json() or {}))
        if not result.get("success"):
            _raise_http_error(result)
        return result

    @router.delete("/v1/desktop/users/{user_id}/stock-pools/{pool_id}")
    async def desktop_user_stock_pool_delete(request: Request, user_id: str, pool_id: str) -> dict[str, Any]:
        require_full(request)
        result = await desktop_asset_call("DELETE", f"/v1/users/{user_id}/stock-pools/{pool_id}", None)
        if not result.get("success"):
            _raise_http_error(result)
        return result

    @router.post("/v1/desktop/users/{user_id}/stock-pools/reorder")
    async def desktop_user_stock_pool_reorder(request: Request, user_id: str) -> dict[str, Any]:
        require_full(request)
        result = await desktop_asset_call("POST", f"/v1/users/{user_id}/stock-pools/reorder", dict(await request.json() or {}))
        if not result.get("success"):
            _raise_http_error(result)
        return result

    @router.post("/v1/desktop/users/{user_id}/stock-pools/{pool_id}/stocks")
    async def desktop_user_stock_pool_add_stock(request: Request, user_id: str, pool_id: str) -> dict[str, Any]:
        require_full(request)
        result = await desktop_asset_call("POST", f"/v1/users/{user_id}/stock-pools/{pool_id}/stocks", dict(await request.json() or {}))
        if not result.get("success"):
            _raise_http_error(result)
        return result

    @router.delete("/v1/desktop/users/{user_id}/stock-pools/{pool_id}/stocks/{stock_code}")
    async def desktop_user_stock_pool_remove_stock(request: Request, user_id: str, pool_id: str, stock_code: str) -> dict[str, Any]:
        require_full(request)
        result = await desktop_asset_call("DELETE", f"/v1/users/{user_id}/stock-pools/{pool_id}/stocks/{stock_code}", None)
        if not result.get("success"):
            _raise_http_error(result)
        return result

    @router.post("/v1/desktop/users/{user_id}/stock-pools/{pool_id}/stocks/batch-remove")
    async def desktop_user_stock_pool_batch_remove(request: Request, user_id: str, pool_id: str) -> dict[str, Any]:
        require_full(request)
        result = await desktop_asset_call(
            "POST",
            f"/v1/users/{user_id}/stock-pools/{pool_id}/stocks/batch-remove",
            dict(await request.json() or {}),
        )
        if not result.get("success"):
            _raise_http_error(result)
        return result

    @router.post("/v1/desktop/files/upload")
    async def desktop_files_upload(
        request: Request,
        files: list[UploadFile] = File(...),
        session_id: str | None = Form(None),
        thread_id: str | None = Form(None),
    ) -> dict[str, Any]:
        require_full(request)
        result = await desktop_file_upload(
            files,
            {"session_id": session_id, "thread_id": thread_id},
        )
        if not result.get("success"):
            _raise_http_error(result)
        return result

    @router.get("/v1/desktop/files")
    async def desktop_files_list(request: Request, user_id: str = "default") -> dict[str, Any]:
        require_api(request)
        result = await desktop_asset_call("GET", f"/v1/files?user_id={user_id}", None)
        if not result.get("success"):
            _raise_http_error(result)
        return result

    @router.post("/v1/desktop/files/save")
    async def desktop_files_save(request: Request) -> dict[str, Any]:
        require_full(request)
        result = await desktop_asset_call("POST", "/v1/files/save", dict(await request.json() or {}))
        if not result.get("success"):
            _raise_http_error(result)
        return result

    @router.delete("/v1/desktop/files/{file_id}")
    async def desktop_files_delete(request: Request, file_id: str) -> dict[str, Any]:
        require_full(request)
        result = await desktop_asset_call("DELETE", f"/v1/files/{file_id}", None)
        if not result.get("success"):
            _raise_http_error(result)
        return result

    @router.post("/v1/sessions/batch/archive")
    async def desktop_sessions_batch_archive(request: Request) -> dict[str, Any]:
        full = require_full(request)
        payload = dict(await request.json() or {})
        session_ids = [str(item).strip() for item in list(payload.get("session_ids") or []) if str(item).strip()]
        if not session_ids:
            raise HTTPException(400, detail="session_ids is required")

        session_store = full.session_store
        results = []
        for session_id in session_ids:
            try:
                archived = session_store.set_session_archived(
                    session_id,
                    archived=True,
                    reason=str(payload.get("reason") or "desktop batch archive"),
                    actor=str(payload.get("actor") or payload.get("user_id") or "control_token"),
                )
                results.append({"session_id": session_id, "success": True, "data": archived})
            except FileNotFoundError:
                results.append({"session_id": session_id, "success": False, "error": "session_not_found", "error_code": "SESSION_NOT_FOUND"})
            except Exception as exc:
                results.append({"session_id": session_id, "success": False, "error": str(exc), "error_code": "SESSION_ARCHIVE_FAILED"})

        return {
            "object": "aiask.session_archive_batch",
            "success": True,
            "data": {
                "results": results,
                "archived_count": sum(1 for item in results if item.get("success")),
                "failed_count": sum(1 for item in results if not item.get("success")),
            },
            "error": None,
            "error_code": None,
            "secrets_redacted": True,
        }

    return router
