"""Helpers for the Agent tool catalog HTTP response."""

from __future__ import annotations

from typing import Any

from ..runtime import AgentRuntime

TOOL_CONTRACT_CATALOG_FIELDS = (
    "input_schema",
    "output_schema",
    "freshness",
    "examples",
    "contract_version",
    "contract_source",
    "source_policy",
    "standard_model",
    "provider_choices",
    "provider_status",
    "quality_gate",
    "reconciliation",
    "form_schema",
)


def tool_catalog_item_payload(item: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    payload = dict(item)
    payload["parameters"] = parameters
    for field in TOOL_CONTRACT_CATALOG_FIELDS:
        if field in item and item.get(field) is not None:
            payload[field] = item.get(field)
    return payload


def build_tool_catalog_payload(selected: AgentRuntime, *, implementation: str | None = None) -> dict[str, Any]:
    schemas = {
        item["function"]["name"]: item["function"]
        for item in selected.tool_registry.openai_tools()
        if item.get("type") == "function" and isinstance(item.get("function"), dict)
    }
    payload = {
        "object": "list",
        "data": [
            tool_catalog_item_payload(
                dict(item),
                schemas.get(str(item.get("name")), {}).get("parameters", {}),
            )
            for item in selected.tool_registry.catalog
        ],
    }
    if implementation:
        payload["implementation"] = implementation
    return payload
