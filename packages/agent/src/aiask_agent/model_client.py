from __future__ import annotations

import json
import os
import re
import inspect
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from .env_config import load_project_env
from .model_providers import ModelProviderRegistry, ProviderSpec, ProviderUsageStore


@dataclass
class ModelResponse:
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    raw: Any = None


class ModelClient(Protocol):
    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
    ) -> ModelResponse:
        ...


class OpenAIChatClient:
    def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def aclose(self) -> None:
        closer = getattr(self.client, "close", None)
        if callable(closer):
            result = closer()
            if inspect.isawaitable(result):
                await result

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
    ) -> ModelResponse:
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools or None,
            tool_choice="auto" if tools else None,
        )
        choice = response.choices[0]
        message = choice.message
        tool_calls: list[dict[str, Any]] = []
        for call in list(message.tool_calls or []):
            tool_calls.append(
                {
                    "id": call.id,
                    "type": call.type,
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments or "{}",
                    },
                }
            )
        usage_obj = getattr(response, "usage", None)
        if hasattr(usage_obj, "model_dump"):
            usage = usage_obj.model_dump()
        elif isinstance(usage_obj, dict):
            usage = dict(usage_obj)
        else:
            usage = {}
        return ModelResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            usage=usage,
            raw=response,
        )


class MockModelClient:
    """Deterministic local model used when no external provider is configured."""

    _TOOL_PATTERN = re.compile(r"tool:([A-Za-z0-9_]+)(?:\s+(\{.*\}))?", re.DOTALL)

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
    ) -> ModelResponse:
        tool_messages = [msg for msg in messages if msg.get("role") == "tool"]
        if tool_messages:
            latest = tool_messages[-1]
            return ModelResponse(
                content=f"工具调用完成: {latest.get('name') or latest.get('tool_call_id')}",
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

        last_user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user = str(msg.get("content") or "")
                break
        match = self._TOOL_PATTERN.search(last_user)
        allowed_names = {
            (tool.get("function") or {}).get("name")
            for tool in tools
            if isinstance(tool, dict)
        }
        if match and match.group(1) in allowed_names:
            name = match.group(1)
            raw_args = match.group(2) or "{}"
            try:
                parsed_args = json.loads(raw_args)
            except Exception:
                parsed_args = {}
            return ModelResponse(
                content="",
                tool_calls=[
                    {
                        "id": f"call_{uuid4().hex[:12]}",
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(parsed_args, ensure_ascii=False),
                        },
                    }
                ],
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

        return ModelResponse(
            content=last_user or "AIASK Agent ready.",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )


class ProviderPoolModelClient:
    """OpenAI-compatible provider fallback with credential attempt accounting."""

    def __init__(self, *, registry: ModelProviderRegistry | None = None) -> None:
        self.registry = registry or ModelProviderRegistry(usage_store=ProviderUsageStore())

    async def aclose(self) -> None:
        return None

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
    ) -> ModelResponse:
        errors: list[str] = []
        providers = {item.name: item for item in self.registry.providers() if item.enabled}
        allow_mock_fallback = str(os.getenv("AIASK_AGENT_ALLOW_MOCK_FALLBACK", "")).strip().lower() in {"1", "true", "yes", "on"}
        for provider_name in self.registry.fallback_order():
            provider = providers.get(provider_name)
            if provider is None:
                continue
            if provider.provider_type == "mock":
                if self.registry.active_provider_name() != "mock" and not allow_mock_fallback:
                    continue
                return await MockModelClient().complete(messages=messages, tools=tools, model=model)
            for credential in self._credentials_for(provider):
                if not credential.secret_value:
                    continue
                client = OpenAIChatClient(api_key=credential.secret_value, base_url=provider.base_url)
                try:
                    response = await client.complete(messages=messages, tools=tools, model=provider.model or model)
                    self.registry.record_attempt(provider=provider.name, credential_id=credential.credential_id, success=True)
                    return response
                except Exception as exc:
                    error_class = self.registry.classify_error(exc)
                    self.registry.record_attempt(
                        provider=provider.name,
                        credential_id=credential.credential_id,
                        success=False,
                        error=str(exc),
                    )
                    errors.append(f"{provider.name}:{credential.credential_id}:{error_class}")
                    if error_class not in {"auth_failed", "rate_limited", "timeout", "network_error"}:
                        raise
                finally:
                    await client.aclose()
        raise RuntimeError("all configured model providers failed or are unavailable: " + "; ".join(errors))

    def _credentials_for(self, provider: ProviderSpec) -> list[Any]:
        configured = [item for item in provider.credentials if item.configured]
        usage = self.registry.usage_store.summary()
        return sorted(
            configured,
            key=lambda item: (
                int((usage.get(item.credential_id) or {}).get("failure_count") or 0),
                str((usage.get(item.credential_id) or {}).get("last_used_at") or ""),
                item.credential_id,
            ),
        )


def build_model_client_from_env() -> ModelClient:
    load_project_env()
    provider = str(os.getenv("AIASK_AGENT_MODEL_PROVIDER", "")).strip().lower()
    api_key = str(os.getenv("OPENAI_API_KEY", "")).strip()
    base_url = str(os.getenv("OPENAI_BASE_URL", "")).strip() or None
    has_provider_pool = bool(str(os.getenv("OPENAI_API_KEYS", "")).strip() or str(os.getenv("AIASK_AGENT_MODEL_PROVIDERS", "")).strip())
    if provider == "mock" or (not provider and not api_key and not has_provider_pool):
        return MockModelClient()
    if has_provider_pool or provider not in {"", "openai"}:
        registry = ModelProviderRegistry(usage_store=ProviderUsageStore())
        if has_provider_pool and provider in {"", "openai"}:
            return ProviderPoolModelClient(registry=registry)
        if provider in {item.name for item in registry.providers()}:
            return ProviderPoolModelClient(registry=registry)
        if provider not in {"", "openai"}:
            raise ValueError(f"unsupported AIASK_AGENT_MODEL_PROVIDER: {provider}")
    if provider in {"", "openai"}:
        return OpenAIChatClient(api_key=api_key or None, base_url=base_url)
    raise ValueError(f"unsupported AIASK_AGENT_MODEL_PROVIDER: {provider}")
