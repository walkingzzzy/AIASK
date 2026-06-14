from __future__ import annotations

import time
from typing import Any


def messages_from_responses_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("messages"), list):
        return [dict(item) for item in payload["messages"] if isinstance(item, dict)]
    raw_input = payload.get("input", "")
    if isinstance(raw_input, str):
        return [{"role": "user", "content": raw_input}]
    if isinstance(raw_input, list):
        messages: list[dict[str, Any]] = []
        for item in raw_input:
            if isinstance(item, dict) and item.get("role"):
                messages.append({"role": item.get("role"), "content": item.get("content", "")})
            elif isinstance(item, str):
                messages.append({"role": "user", "content": item})
        return messages
    return []


def chat_completion_payload(result: Any, *, model: str) -> dict[str, Any]:
    return {
        "id": result.response_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result.content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": result.usage,
        "aiask": {
            "session_id": result.session_id,
            "run_id": result.run_id,
            "tool_calls": result.tool_calls,
            "audit_events": result.audit_events,
            "events": result.events,
            "context_summary_id": result.context_summary_id,
            "planner_steps": result.planner_steps,
            "subruns": result.subruns,
        },
    }


def responses_payload(result: Any, *, model: str) -> dict[str, Any]:
    return {
        "id": result.response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": model,
        "output_text": result.content,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": result.content}],
            }
        ],
        "usage": result.usage,
        "metadata": {
            "session_id": result.session_id,
            "run_id": result.run_id,
            "tool_calls": result.tool_calls,
            "audit_events": result.audit_events,
            "events": result.events,
            "context_summary_id": result.context_summary_id,
            "planner_steps": result.planner_steps,
            "subruns": result.subruns,
        },
    }
