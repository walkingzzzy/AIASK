from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .adapters import akshare as akshare_adapter
from .adapters import quant as quant_adapter
from .adapters import strategy_factory as strategy_factory_adapter
from .general_tools import build_general_tool_handlers
from .intents import ActionIntentStore
from .mcp_client import MCPAggregator, MCPOAuthRequired
from .memory import FinancialMemoryStore
from .native_capabilities import build_native_capability_handlers
from .plugin_runtime import NativePluginManager
from .quant_research import QuantResearchStore
from .scheduler import AgentJobStore
from .session_store import AgentSessionStore
from .tools.catalog import GENERAL_TOOL_CATALOG, FINANCE_SAFE_TOOL_CATALOG, SAFE_TOOL_CATALOG, catalog_for_toolset, tool_descriptions
from .tools.policy import ToolPolicyEngine, assert_safe_catalog_names, build_policy_from_env, ensure_agent_tool_name
from .tools.schemas import TOOL_SCHEMAS
from .tool_risk import mcp_call_side_effect, mcp_tool_metadata, strategy_action_params


ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]]


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    metadata: dict[str, Any] | None = None

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class AgentToolRegistry:
    def __init__(self, *, policy_engine: ToolPolicyEngine | None = None) -> None:
        self._tools: dict[str, AgentTool] = {}
        self.policy_engine = policy_engine or ToolPolicyEngine()
        self.catalog: list[dict[str, Any]] = []

    def register(
        self,
        name: str,
        *,
        description: str,
        parameters: dict[str, Any] | None = None,
        handler: ToolHandler,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        normalized_name = ensure_agent_tool_name(name)
        self.policy_engine.require_allowed(normalized_name, metadata)
        self._tools[normalized_name] = AgentTool(
            name=normalized_name,
            description=description,
            parameters=parameters or {"type": "object", "properties": {}, "additionalProperties": True},
            handler=handler,
            metadata=dict(metadata or {}),
        )
        catalog_item = {
            "name": normalized_name,
            "description": description,
            **dict(metadata or {}),
        }
        self.catalog = [item for item in self.catalog if item.get("name") != normalized_name]
        self.catalog.append(catalog_item)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get(name)

    def openai_tools(self) -> list[dict[str, Any]]:
        return [self._tools[name].openai_schema() for name in self.names()]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        tool = self.get(name)
        if tool is None:
            return aiask_envelope(
                False,
                data=None,
                error=f"tool is not registered: {name}",
                tool_name=name,
                source_chain=["aiask_agent.tool_registry"],
                error_code="TOOL_NOT_FOUND",
            )
        try:
            result = tool.handler(dict(arguments or {}))
            if inspect.isawaitable(result):
                result = await result
            payload = ensure_aiask_envelope(
                result,
                tool_name=name,
                source_chain=["aiask_agent.tool_registry"],
            )
            payload["meta"]["toolset"] = self.policy_engine.toolset
            return payload
        except Exception as exc:
            return aiask_envelope(
                False,
                data=None,
                error=str(exc),
                tool_name=name,
                source_chain=["aiask_agent.tool_registry"],
                error_code="TOOL_EXECUTION_ERROR",
            )


def aiask_envelope(
    success: bool,
    *,
    data: Any,
    error: str | None,
    tool_name: str,
    source_chain: list[str] | None = None,
    side_effect: dict[str, Any] | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    meta = {
        "trace_id": f"aiask-agent:{tool_name}:{int(time.time() * 1000)}:{uuid4().hex[:8]}",
        "source_chain": list(source_chain or ["aiask_agent"]),
        "side_effect": side_effect
        or {
            "level": "read_only",
            "target": tool_name,
            "confirmation_required": False,
            "idempotent": True,
        },
    }
    payload = {
        "success": bool(success),
        "data": data,
        "error": error,
        "meta": meta,
    }
    if error_code:
        payload["error_code"] = error_code
    return payload


def ensure_aiask_envelope(
    value: Any,
    *,
    tool_name: str,
    source_chain: list[str] | None = None,
) -> dict[str, Any]:
    if isinstance(value, dict) and {"success", "data", "error"}.issubset(value):
        result = dict(value)
        meta = dict(result.get("meta") or {})
        meta.setdefault(
            "trace_id",
            f"aiask-agent:{tool_name}:{int(time.time() * 1000)}:{uuid4().hex[:8]}",
        )
        chain = meta.get("source_chain") or source_chain or ["aiask_agent"]
        meta["source_chain"] = [str(item) for item in chain if str(item).strip()]
        side_effect = meta.get("side_effect")
        if not isinstance(side_effect, dict):
            side_effect = {
                "level": "read_only",
                "target": tool_name,
                "confirmation_required": False,
                "idempotent": True,
            }
        meta["side_effect"] = side_effect
        meta.setdefault("toolset", "finance_safe")
        result["meta"] = meta
        return result
    return aiask_envelope(
        True,
        data=value,
        error=None,
        tool_name=tool_name,
        source_chain=source_chain,
    )


def build_default_tool_registry(
    intent_store: ActionIntentStore | None = None,
    *,
    policy_engine: ToolPolicyEngine | None = None,
    session_store: AgentSessionStore | None = None,
    memory_store: FinancialMemoryStore | None = None,
    job_store: AgentJobStore | None = None,
    mcp_aggregator: MCPAggregator | None = None,
) -> AgentToolRegistry:
    assert_safe_catalog_names(item["name"] for item in FINANCE_SAFE_TOOL_CATALOG)
    policy_engine = policy_engine or ToolPolicyEngine(build_policy_from_env())
    registry = AgentToolRegistry(policy_engine=policy_engine)
    intents = intent_store or ActionIntentStore()
    sessions = session_store or AgentSessionStore()
    memories = memory_store or FinancialMemoryStore(getattr(sessions, "path", None))
    jobs = job_store or AgentJobStore(getattr(sessions, "path", None))
    mcp = mcp_aggregator or MCPAggregator()
    quant_store = QuantResearchStore(getattr(sessions, "path", None))
    visible_catalog = catalog_for_toolset(
        policy_engine.toolset,
        include_general=policy_engine.policy.general_tools_enabled,
    )

    async def tool_catalog(_: dict[str, Any]) -> dict[str, Any]:
        return aiask_envelope(
            True,
            data={
                "toolset": policy_engine.toolset,
                "tools": [dict(item) for item in visible_catalog],
                "count": len(visible_catalog),
            },
            error=None,
            tool_name="agent_tool_catalog",
            source_chain=["aiask_agent.tools.safe_catalog"],
        )

    async def action_intent_create(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            intent = intents.create(
                action=str(arguments.get("action") or ""),
                params=dict(arguments.get("params") or {}),
                user_id=arguments.get("user_id"),
                rationale=arguments.get("rationale"),
                ttl_seconds=int(arguments.get("ttl_seconds") or 86400),
            )
            return aiask_envelope(
                True,
                data={"intent": intent},
                error=None,
                tool_name="agent_action_intent_create",
                source_chain=["aiask_agent.intents"],
                side_effect={
                    "level": "stateful",
                    "target": intent.get("intent_id"),
                    "confirmation_required": True,
                    "idempotent": False,
                },
            )
        except Exception as exc:
            return aiask_envelope(
                False,
                data=None,
                error=str(exc),
                tool_name="agent_action_intent_create",
                source_chain=["aiask_agent.intents"],
                error_code="INTENT_CREATE_FAILED",
            )

    async def action_intent_get(arguments: dict[str, Any]) -> dict[str, Any]:
        intent_id = str(arguments.get("intent_id") or "").strip()
        intent = intents.get(intent_id) if intent_id else None
        if intent is None:
            return aiask_envelope(
                False,
                data=None,
                error=f"intent not found: {intent_id}",
                tool_name="agent_action_intent_get",
                source_chain=["aiask_agent.intents"],
                error_code="NOT_FOUND",
            )
        return aiask_envelope(
            True,
            data={"intent": intent},
            error=None,
            tool_name="agent_action_intent_get",
            source_chain=["aiask_agent.intents"],
        )

    async def memory_save(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            item = memories.add(
                content=str(arguments.get("content") or ""),
                user_id=arguments.get("user_id"),
                symbol=arguments.get("symbol"),
                strategy_id=arguments.get("strategy_id"),
                research_topic=arguments.get("research_topic"),
            )
            return aiask_envelope(
                True,
                data={"memory": item},
                error=None,
                tool_name="agent_memory_save",
                source_chain=["aiask_agent.memory"],
                side_effect={
                    "level": "stateful",
                    "target": item["memory_id"],
                    "confirmation_required": False,
                    "idempotent": False,
                },
            )
        except Exception as exc:
            return aiask_envelope(
                False,
                data=None,
                error=str(exc),
                tool_name="agent_memory_save",
                source_chain=["aiask_agent.memory"],
                error_code="MEMORY_SAVE_FAILED",
            )

    async def memory_search(arguments: dict[str, Any]) -> dict[str, Any]:
        return aiask_envelope(
            True,
            data={
                "items": memories.search(
                    query=arguments.get("query"),
                    user_id=arguments.get("user_id"),
                    symbol=arguments.get("symbol"),
                    strategy_id=arguments.get("strategy_id"),
                    research_topic=arguments.get("research_topic"),
                    limit=int(arguments.get("limit") or 20),
                )
            },
            error=None,
            tool_name="agent_memory_search",
            source_chain=["aiask_agent.memory"],
        )

    async def memory(arguments: dict[str, Any]) -> dict[str, Any]:
        action = str(arguments.get("action") or "search").strip().lower()
        if action == "save":
            return await memory_save(arguments)
        if action == "search":
            return await memory_search(arguments)
        if action == "status":
            return aiask_envelope(
                True,
                data={"provider": "aiask_builtin", "configured": True},
                error=None,
                tool_name="agent_memory",
                source_chain=["aiask_agent.memory"],
            )
        return aiask_envelope(
            False,
            data=None,
            error=f"unsupported memory action: {action}",
            tool_name="agent_memory",
            source_chain=["aiask_agent.memory"],
            error_code="INVALID_REQUEST",
        )

    async def session_search(arguments: dict[str, Any]) -> dict[str, Any]:
        return aiask_envelope(
            True,
            data={
                "items": sessions.search(
                    query=str(arguments.get("query") or ""),
                    session_id=arguments.get("session_id"),
                    user_id=arguments.get("user_id"),
                    limit=int(arguments.get("limit") or 20),
                )
            },
            error=None,
            tool_name="agent_session_search",
            source_chain=["aiask_agent.session_store"],
        )

    async def quant_research_run(arguments: dict[str, Any]) -> dict[str, Any]:
        return await quant_adapter.quant_research_run(arguments, store=quant_store)

    async def job_create(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            job = jobs.create(
                name=str(arguments.get("name") or ""),
                prompt=str(arguments.get("prompt") or ""),
                schedule=arguments.get("schedule"),
                interval_seconds=arguments.get("interval_seconds"),
                toolset=str(arguments.get("toolset") or "finance_safe"),
                enabled=bool(arguments.get("enabled", True)),
            )
            return aiask_envelope(
                True,
                data={"job": job},
                error=None,
                tool_name="agent_job_create",
                source_chain=["aiask_agent.scheduler"],
                side_effect={
                    "level": "stateful",
                    "target": job["job_id"],
                    "confirmation_required": False,
                    "idempotent": False,
                },
            )
        except Exception as exc:
            return aiask_envelope(
                False,
                data=None,
                error=str(exc),
                tool_name="agent_job_create",
                source_chain=["aiask_agent.scheduler"],
                error_code="JOB_CREATE_FAILED",
            )

    async def job_list(_: dict[str, Any]) -> dict[str, Any]:
        return aiask_envelope(
            True,
            data={"jobs": jobs.list()},
            error=None,
            tool_name="agent_job_list",
            source_chain=["aiask_agent.scheduler"],
        )

    async def job_run(arguments: dict[str, Any]) -> dict[str, Any]:
        return aiask_envelope(
            False,
            data=None,
            error="job execution requires an attached AgentRuntime",
            tool_name="agent_job_run",
            source_chain=["aiask_agent.scheduler"],
            error_code="RUNTIME_NOT_ATTACHED",
        )

    async def cronjob(arguments: dict[str, Any]) -> dict[str, Any]:
        action = str(arguments.get("action") or "list").strip().lower()
        try:
            if action == "list":
                data = {"jobs": jobs.list()}
            elif action == "create":
                data = {
                    "job": jobs.create(
                        name=str(arguments.get("name") or ""),
                        prompt=str(arguments.get("prompt") or ""),
                        schedule=arguments.get("schedule"),
                        interval_seconds=arguments.get("interval_seconds"),
                        toolset=str(arguments.get("toolset") or "finance_safe"),
                        enabled=bool(arguments.get("enabled", True)),
                        payload={
                            "script": arguments.get("script"),
                            "skills": list(arguments.get("skills") or []),
                            "silent_pattern": arguments.get("silent_pattern"),
                        },
                    )
                }
            elif action in {"pause", "resume"}:
                data = {"job": jobs.update(str(arguments.get("job_id") or ""), enabled=action == "resume")}
            elif action == "update":
                data = {"job": jobs.update(str(arguments.get("job_id") or ""), **{k: v for k, v in arguments.items() if k in {"name", "prompt", "schedule", "interval_seconds", "toolset", "enabled"}})}
            elif action == "remove":
                data = {"deleted": jobs.delete(str(arguments.get("job_id") or ""))}
            elif action == "trigger":
                return await job_run(arguments)
            else:
                raise ValueError(f"unsupported cronjob action: {action}")
            return aiask_envelope(
                True,
                data=data,
                error=None,
                tool_name="agent_cronjob",
                source_chain=["aiask_agent.scheduler"],
                side_effect={
                    "level": "stateful" if action != "list" else "read_only",
                    "target": arguments.get("job_id") or arguments.get("name") or "cronjob",
                    "confirmation_required": False,
                    "idempotent": False,
                },
            )
        except Exception as exc:
            return aiask_envelope(
                False,
                data=None,
                error=str(exc),
                tool_name="agent_cronjob",
                source_chain=["aiask_agent.scheduler"],
                error_code="CRONJOB_FAILED",
            )

    descriptions = tool_descriptions()
    metadata_by_name = {item["name"]: dict(item) for item in (*FINANCE_SAFE_TOOL_CATALOG, *GENERAL_TOOL_CATALOG)}
    for item in FINANCE_SAFE_TOOL_CATALOG:
        metadata_by_name[item["name"]] = dict(item)
    finance_registrations: tuple[tuple[str, ToolHandler], ...] = (
        ("agent_tool_catalog", tool_catalog),
        ("agent_analyze_stock", akshare_adapter.analyze_stock),
        ("agent_governance_check", akshare_adapter.governance_check),
        ("agent_data_validation", akshare_adapter.data_validation),
        ("agent_quant_data_gate", quant_adapter.quant_data_gate),
        ("agent_factor_validation", quant_adapter.factor_validation),
        ("agent_backtest_suite", quant_adapter.backtest_suite),
        ("agent_portfolio_risk", quant_adapter.portfolio_risk),
        ("agent_quant_research_run", quant_research_run),
        ("agent_factory_status", strategy_factory_adapter.factory_status),
        ("agent_factory_runs", strategy_factory_adapter.factory_runs),
        ("agent_strategy_review_snapshot", strategy_factory_adapter.strategy_review_snapshot),
        ("agent_strategy_domain_events", strategy_factory_adapter.strategy_domain_events),
        ("agent_incubation_factory_status", strategy_factory_adapter.incubation_factory_status),
        ("agent_action_intent_create", action_intent_create),
        ("agent_action_intent_get", action_intent_get),
        ("agent_memory", memory),
        ("agent_memory_save", memory_save),
        ("agent_memory_search", memory_search),
        ("agent_session_search", session_search),
    )
    for name, handler in finance_registrations:
        if name not in TOOL_SCHEMAS:
            continue
        registry.register(
            name,
            description=descriptions.get(name, name),
            parameters=TOOL_SCHEMAS[name],
            handler=handler,
            metadata=metadata_by_name.get(name, {"category": "financial_read", "side_effect": "read_only"}),
        )
    if policy_engine.policy.general_tools_enabled and policy_engine.toolset == "general_full":
        for name, handler in build_general_tool_handlers(
            policy_engine.policy,
            state_path=getattr(sessions, "path", None),
        ).items():
            registry.register(
                name,
                description=descriptions.get(name, name),
                parameters=TOOL_SCHEMAS[name],
                handler=handler,
                metadata=metadata_by_name.get(name, {"category": "general_execute", "side_effect": "process"}),
            )
        for name, handler in build_native_capability_handlers(
            policy=policy_engine.policy,
            session_store=sessions,
            todo_store=None,
        ).items():
            registry.register(
                name,
                description=descriptions.get(name, name),
                parameters=TOOL_SCHEMAS[name],
                handler=handler,
                metadata=metadata_by_name.get(name, {"category": "general_read", "side_effect": "read_only"}),
            )
        for name, handler in {
            "agent_job_create": job_create,
            "agent_job_list": job_list,
            "agent_job_run": job_run,
            "agent_cronjob": cronjob,
        }.items():
            registry.register(
                name,
                description=descriptions.get(name, name),
                parameters=TOOL_SCHEMAS[name],
                handler=handler,
                metadata=metadata_by_name.get(name, {"category": "cron_admin", "side_effect": "stateful"}),
            )
    for mcp_tool in mcp.financial_tools():
        wrapped_name = mcp_tool["wrapped_name"]
        raw_tool_name = str(mcp_tool.get("name") or "")

        async def mcp_handler(
            arguments: dict[str, Any],
            tool_name: str = wrapped_name,
            raw_name: str = raw_tool_name,
            raw_side_effect: Any = mcp_tool.get("side_effect"),
        ) -> dict[str, Any]:
            side_effect = mcp_call_side_effect(raw_name, arguments, raw_side_effect=raw_side_effect)
            if side_effect.get("level") != "read_only":
                action = str(side_effect.get("target") or raw_name).replace("strategy_manager.", "")
                if raw_name != "strategy_manager":
                    return aiask_envelope(
                        False,
                        data={
                            "tool": raw_name,
                            "side_effect": side_effect,
                            "reason": "Stateful financial MCP tools require an AIASK-native confirmation adapter before direct execution.",
                        },
                        error="Stateful MCP tool calls are blocked by default",
                        tool_name=tool_name,
                        source_chain=["aiask_agent.mcp_client", "aiask_agent.tool_risk"],
                        side_effect=side_effect,
                        error_code="MCP_STATEFUL_ACTION_BLOCKED",
                    )
                return aiask_envelope(
                    False,
                    data={
                        "required_tool": "agent_action_intent_create",
                        "action": f"strategy_manager.{action}",
                        "params": strategy_action_params(arguments),
                        "reason": "Stateful financial MCP actions require a durable confirmation intent.",
                    },
                    error="MCP action requires durable intent confirmation",
                    tool_name=tool_name,
                    source_chain=["aiask_agent.mcp_client", "aiask_agent.tool_risk"],
                    side_effect=side_effect,
                    error_code="ACTION_INTENT_REQUIRED",
                )
            try:
                data = await mcp.call(tool_name, arguments)
                return aiask_envelope(
                    True,
                    data=data,
                    error=None,
                    tool_name=tool_name,
                    source_chain=["aiask_agent.mcp_client"],
                )
            except MCPOAuthRequired as exc:
                return aiask_envelope(
                    False,
                    data=exc.payload,
                    error="MCP OAuth authorization is required",
                    tool_name=tool_name,
                    source_chain=["aiask_agent.mcp_client"],
                    error_code="MCP_OAUTH_REQUIRED",
                )
            except Exception as exc:
                return aiask_envelope(
                    False,
                    data=None,
                    error=str(exc),
                    tool_name=tool_name,
                    source_chain=["aiask_agent.mcp_client"],
                    error_code="MCP_CALL_FAILED",
                )

        registry.register(
            wrapped_name,
            description=mcp_tool["description"],
            parameters=mcp_tool["parameters"],
            handler=mcp_handler,
            metadata=mcp_tool_metadata(mcp_tool),
        )
    if policy_engine.policy.general_tools_enabled and policy_engine.toolset == "general_full":
        plugin_manager = NativePluginManager()
        for plugin_tool in plugin_manager.tool_definitions():
            wrapped_name = plugin_tool["name"]

            async def plugin_handler(arguments: dict[str, Any], tool_name: str = wrapped_name) -> dict[str, Any]:
                try:
                    data = await plugin_manager.call_tool(tool_name, arguments)
                    return aiask_envelope(
                        True,
                        data=data,
                        error=None,
                        tool_name=tool_name,
                        source_chain=["aiask_agent.plugin_runtime"],
                    )
                except Exception as exc:
                    return aiask_envelope(
                        False,
                        data=None,
                        error=str(exc),
                        tool_name=tool_name,
                        source_chain=["aiask_agent.plugin_runtime"],
                        error_code="PLUGIN_TOOL_FAILED",
                    )

            registry.register(
                wrapped_name,
                description=plugin_tool["description"],
                parameters=plugin_tool["parameters"],
                handler=plugin_handler,
                metadata={
                    "capability": "dynamic_plugin_tools",
                    "category": "plugins",
                    "side_effect": plugin_tool.get("side_effect") or "stateful",
                    "plugin": plugin_tool["plugin"],
                },
            )
    return registry
