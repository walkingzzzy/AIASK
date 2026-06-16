from __future__ import annotations

from typing import Any

from .mcp_client import MCPAggregator


def exception_messages(exc: BaseException) -> list[str]:
    messages = [str(exc)] if str(exc) else [exc.__class__.__name__]
    nested = getattr(exc, "exceptions", None)
    if isinstance(nested, (list, tuple)):
        for item in nested:
            if isinstance(item, BaseException):
                messages.extend(exception_messages(item))
            else:
                messages.append(str(item))
    cause = getattr(exc, "__cause__", None)
    if isinstance(cause, BaseException):
        messages.extend(exception_messages(cause))
    return [message for index, message in enumerate(messages) if message and message not in messages[:index]]


def classify_mcp_error(exc: BaseException) -> tuple[str, str]:
    messages = exception_messages(exc)
    detail = "; ".join(messages)
    lowered = detail.lower()
    if (
        "401" in lowered
        or "unauthorized" in lowered
        or "authentication required" in lowered
        or "invalid_token" in lowered
        or "bearer token env" in lowered
    ):
        return "MCP_DISCOVERY_AUTH_REQUIRED", detail
    if "oauth" in lowered:
        return "MCP_DISCOVERY_OAUTH_REQUIRED", detail
    if "connection" in lowered or "connect" in lowered or "refused" in lowered:
        return "MCP_DISCOVERY_CONNECTION_FAILED", detail
    return "MCP_DISCOVERY_FAILED", detail


def mcp_action_error_payload(*, action: str, server_name: str, exc: BaseException) -> dict[str, Any]:
    error_code, detail = classify_mcp_error(exc)
    auth: dict[str, Any] = {}
    if server_name:
        try:
            auth = MCPAggregator().auth_readiness(server_name)
        except Exception:
            auth = {}
    return {
        "object": f"mcp.{action}",
        "success": False,
        "data": {
            "server": server_name or None,
            "configured": False,
            "status": "failed",
            "detail": detail,
            **auth,
        },
        "error": detail,
        "error_code": error_code,
    }
