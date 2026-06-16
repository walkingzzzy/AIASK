from __future__ import annotations

from typing import Any


def plugin_tools(plugin: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in list(plugin.get("tools") or []) if isinstance(item, dict) and item.get("name")]


def plugin_self_test_payload(plugin: dict[str, Any], name: str) -> dict[str, Any]:
    tools = plugin_tools(plugin)
    commands = [dict(item) for item in list(plugin.get("commands") or []) if isinstance(item, dict) and item.get("name")]
    return {
        "object": "plugin.tool_test",
        "success": True,
        "data": {
            "plugin": str(plugin.get("name") or name),
            "test_type": "manifest",
            "enabled": bool(plugin.get("enabled")),
            "manifest_valid": True,
            "tools_count": len(tools),
            "commands_count": len(commands),
            "hooks_count": len(list(plugin.get("hooks") or [])),
            "available_tools": [str(item.get("name") or "") for item in tools],
            "available_commands": [str(item.get("name") or "") for item in commands],
            "note": "plugin manifest is readable; no executable tool runner is required for this self-test",
        },
        "error": None,
    }
