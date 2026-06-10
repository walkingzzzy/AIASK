from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import socket
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from .context import ContextManager
from .env_config import load_project_env
from .general_tools import WorkspaceGuard, _limit_bytes, _sanitized_env
from .json_utils import dumps_json
from .model_client import ModelClient, ModelResponse, build_model_client_from_env
from .numeric import bounded_float, bounded_int
from .planner import TaskPlanner
from .plugin_runtime import NativePluginManager
from .recovery import retry_async
from .scheduler import AgentJobStore, BackgroundScheduler
from .session_store import AgentSessionStore, now_iso
from .tool_guardrails import ToolLoopGuardrails, attach_guardrail_metadata
from .tool_registry import AgentToolRegistry, aiask_envelope, build_default_tool_registry
from .tool_risk import metadata_is_read_only
from .todo import FinancialTodoStore
from .tools.policy import FINANCE_SAFE_TOOLSET, GENERAL_FULL_TOOLSET, ToolPolicy, ToolPolicyEngine
from .tools.schemas import TOOL_SCHEMAS
from .memory import FinancialMemoryStore


DEFAULT_SYSTEM_PROMPT = (
    "You are AIASK Agent, a financial research and strategy review runtime. "
    "Use only the tools currently provided by the AIASK Agent runtime and follow the active toolset policy. "
    "Never request live trading or direct manager access."
)


@dataclass
class AgentRunResult:
    response_id: str
    session_id: str
    run_id: str
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    status: str = "completed"
    context_summary_id: str | None = None
    planner_steps: list[dict[str, Any]] = field(default_factory=list)
    subruns: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentRuntime:
    def __init__(
        self,
        *,
        model_client: ModelClient | None = None,
        tool_registry: AgentToolRegistry | None = None,
        session_store: AgentSessionStore | None = None,
        context_manager: ContextManager | None = None,
        planner: TaskPlanner | None = None,
        model: str | None = None,
        max_iterations: int | None = None,
        model_timeout_seconds: float | None = None,
        tool_timeout_seconds: float | None = None,
        retry_attempts: int | None = None,
    ) -> None:
        load_project_env()
        self.model_client = model_client or build_model_client_from_env()
        self.session_store = session_store or AgentSessionStore()
        self.session_store.ensure_ready()
        self.tool_registry = tool_registry or build_default_tool_registry(session_store=self.session_store)
        self.context_manager = context_manager or ContextManager(
            model_client=self.model_client,
            memory_store=FinancialMemoryStore(self.session_store.path)
        )
        self.planner = planner or TaskPlanner(todo_store=FinancialTodoStore(self.session_store.path))
        self.model = model or os.getenv("AIASK_AGENT_MODEL", "gpt-4.1-mini")
        self.max_iterations = bounded_int(
            max_iterations if max_iterations is not None else os.getenv("AIASK_AGENT_MAX_ITERATIONS", "8"),
            default=8,
            minimum=1,
        )
        self.model_timeout_seconds = bounded_float(
            model_timeout_seconds if model_timeout_seconds is not None else os.getenv("AIASK_AGENT_MODEL_TIMEOUT", "120"),
            default=120.0,
            minimum=1.0,
            maximum=3600.0,
        )
        self.tool_timeout_seconds = bounded_float(
            tool_timeout_seconds if tool_timeout_seconds is not None else os.getenv("AIASK_AGENT_TOOL_TIMEOUT", "120"),
            default=120.0,
            minimum=1.0,
            maximum=3600.0,
        )
        self.retry_attempts = bounded_int(
            retry_attempts if retry_attempts is not None else os.getenv("AIASK_AGENT_RETRY_ATTEMPTS", "3"),
            default=3,
            minimum=1,
        )
        self.job_store = AgentJobStore(self.session_store.path)
        self.scheduler = BackgroundScheduler(runtime=self, store=self.job_store)
        self.plugin_manager = NativePluginManager()
        self.subruns: list[dict[str, Any]] = []
        self._register_runtime_bound_tools()
        if os.getenv("AIASK_AGENT_ENABLE_CRON", "").strip().lower() in {"1", "true", "yes", "on"}:
            self.scheduler.start()
        self._closed = False

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.scheduler.stop()
        closer = getattr(self.model_client, "aclose", None) or getattr(self.model_client, "close", None)
        if callable(closer):
            result = closer()
            if inspect.isawaitable(result):
                await result
        store_closer = getattr(self.session_store, "close", None)
        if callable(store_closer):
            store_closer()

    def close(self) -> None:
        asyncio.run(self.aclose())

    def refresh_tool_registry(self) -> None:
        self.tool_registry = build_default_tool_registry(session_store=self.session_store)
        self._register_runtime_bound_tools()

    async def __aenter__(self) -> "AgentRuntime":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.aclose()

    async def run(
        self,
        messages: list[dict[str, Any]],
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        stream: bool = False,
    ) -> AgentRunResult:
        self.subruns = []
        sid = self.session_store.create_session(session_id=session_id, user_id=user_id)
        run_id = self.session_store.create_run(
            sid,
            {
                "user_id": user_id,
                "message_count": len(messages or []),
                "started_at": now_iso(),
                "stream": bool(stream),
            },
        )
        audit_events: list[dict[str, Any]] = []
        persisted_events: list[dict[str, Any]] = []

        def emit(event_type: str, payload: dict[str, Any] | None = None) -> None:
            event = self.session_store.append_run_event(run_id, event_type, dict(payload or {}))
            persisted_events.append(event)
            audit_events.append({"event": event_type, "run_id": run_id, **dict(payload or {}), "created_at": event["created_at"]})

        emit("run.started", {"session_id": sid, "stream": bool(stream)})
        try:
            for plugin_event in await self.plugin_manager.on_session_start(session_id=sid, run_id=run_id):
                emit("plugin.hook", plugin_event)
        except Exception as exc:
            emit("plugin.hook_failed", {"hook": "on_session_start", "error": str(exc)})
        for message in list(messages or []):
            normalized = self._normalize_message(message)
            self.session_store.append_message(sid, normalized)

        working_messages = self._build_context(sid)
        planner_result = self.planner.plan(messages=working_messages, session_id=sid, user_id=user_id)
        planner_steps = planner_result.steps
        if planner_steps:
            emit("planner.plan_created", {"steps": planner_steps})
            if planner_result.prompt_message:
                insert_at = 1 if working_messages and working_messages[0].get("role") == "system" else 0
                working_messages.insert(insert_at, planner_result.prompt_message)
        context_result = await self.context_manager.prepare(working_messages, user_id=user_id)
        context_summary_id = context_result.summary_id
        if context_result.compacted:
            emit(
                "context.compacted",
                {
                    "context_summary_id": context_summary_id,
                    "estimated_tokens_before": self._estimate_tokens(working_messages),
                    "estimated_tokens_after": self._estimate_tokens(context_result.messages),
                },
            )
            self.session_store.append_message(
                sid,
                {
                    "role": "system",
                    "name": "context_summary",
                    "content": context_result.summary or "",
                    "metadata": {"context_summary_id": context_summary_id},
                },
            )
            working_messages = context_result.messages
        all_tool_calls: list[dict[str, Any]] = []
        total_usage: dict[str, Any] = {}
        final_content = ""
        status = "completed"
        explicit_tool_directive_used = False
        tool_guardrails = ToolLoopGuardrails()
        guardrail_halt: dict[str, Any] | None = None

        try:
            for iteration in range(1, self.max_iterations + 1):
                model_started = time.perf_counter()
                emit("model.started", {"iteration": iteration, "model": self.model})

                async def call_model() -> Any:
                    nonlocal explicit_tool_directive_used
                    if not explicit_tool_directive_used:
                        explicit_tool_call = self._explicit_tool_call_from_context(working_messages)
                        if explicit_tool_call:
                            explicit_tool_directive_used = True
                            emit(
                                "tool.directive_detected",
                                {
                                    "tool": explicit_tool_call["function"]["name"],
                                    "tool_call_id": explicit_tool_call["id"],
                                    "iteration": iteration,
                                },
                            )
                            return ModelResponse(content="", tool_calls=[explicit_tool_call], usage={})
                    model_messages, plugin_events = await self.plugin_manager.pre_llm_call(
                        messages=working_messages,
                        model=self.model,
                        tools=self.tool_registry.openai_tools(),
                    )
                    for plugin_event in plugin_events:
                        emit("plugin.hook", plugin_event)
                    return await asyncio.wait_for(
                        self.model_client.complete(
                            messages=model_messages,
                            tools=self.tool_registry.openai_tools(),
                            model=self.model,
                        ),
                        timeout=self.model_timeout_seconds,
                    )

                model_response = await retry_async(
                    call_model,
                    attempts=self.retry_attempts,
                    audit_events=audit_events,
                    event_factory=lambda event: emit("model.retry", event),
                )
                try:
                    for plugin_event in await self.plugin_manager.post_llm_call(
                        messages=working_messages,
                        model=self.model,
                        response={
                            "content": model_response.content,
                            "tool_calls": model_response.tool_calls,
                            "usage": model_response.usage,
                        },
                    ):
                        emit("plugin.hook", plugin_event)
                except Exception as exc:
                    emit("plugin.hook_failed", {"hook": "post_llm_call", "error": str(exc)})
                emit(
                    "model.completed",
                    {
                        "iteration": iteration,
                        "latency_ms": int((time.perf_counter() - model_started) * 1000),
                        "tool_call_count": len(model_response.tool_calls),
                    },
                )
                if model_response.content:
                    emit("model.delta", {"iteration": iteration, "content": model_response.content})
                elif not model_response.tool_calls:
                    emit("model.empty_response", {"iteration": iteration})
                total_usage = self._merge_usage(total_usage, model_response.usage)
                assistant_message = {
                    "role": "assistant",
                    "content": model_response.content,
                }
                if model_response.tool_calls:
                    assistant_message["tool_calls"] = model_response.tool_calls
                working_messages.append(assistant_message)
                self.session_store.append_message(sid, assistant_message)
                final_content = model_response.content or final_content

                if not model_response.tool_calls:
                    break

                for call in model_response.tool_calls:
                    tool_name, arguments, args_corrected = self._parse_tool_call(call)
                    tool_call_record = {
                        "id": call.get("id") or f"call_{uuid4().hex[:12]}",
                        "name": tool_name,
                        "arguments": arguments,
                    }
                    if args_corrected:
                        emit(
                            "tool.arguments_corrected",
                            {
                                "tool": tool_name,
                                "tool_call_id": tool_call_record["id"],
                                "iteration": iteration,
                            },
                        )
                    tool_started = time.perf_counter()
                    blocked, plugin_events = await self.plugin_manager.pre_tool_call(
                        tool_name=tool_name,
                        arguments=arguments,
                        session_id=sid,
                        run_id=run_id,
                    )
                    for plugin_event in plugin_events:
                        emit("plugin.hook", plugin_event)
                    if blocked:
                        result = aiask_envelope(
                            False,
                            data={"block": blocked},
                            error=str(blocked.get("reason") or "blocked by plugin hook"),
                            tool_name=tool_name,
                            source_chain=["aiask_agent.plugin_runtime"],
                            error_code="PLUGIN_HOOK_BLOCKED",
                        )
                        tool_call_record["result"] = result
                        all_tool_calls.append(tool_call_record)
                        emit(
                            "tool.blocked",
                            {
                                "tool": tool_name,
                                "tool_call_id": tool_call_record["id"],
                                "plugin": blocked.get("plugin"),
                                "reason": blocked.get("reason"),
                            },
                        )
                        working_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call_record["id"],
                                "name": tool_name,
                                "content": dumps_json(result, ensure_ascii=False),
                            }
                        )
                        self.session_store.append_message(sid, working_messages[-1])
                        continue
                    emit(
                        "tool.started",
                        {
                            "tool": tool_name,
                            "tool_call_id": tool_call_record["id"],
                            "iteration": iteration,
                        },
                    )

                    async def call_tool() -> dict[str, Any]:
                        return await asyncio.wait_for(
                            self.tool_registry.call_tool(tool_name, arguments),
                            timeout=self.tool_timeout_seconds,
                        )

                    result = await retry_async(
                        call_tool,
                        attempts=self.retry_attempts
                        if metadata_is_read_only(
                            dict(getattr(self.tool_registry.get(tool_name), "metadata", {}) or {}),
                            target=tool_name,
                        )
                        else 1,
                        audit_events=audit_events,
                        event_factory=lambda event: emit("tool.retry", event),
                    )
                    result, plugin_events = self.plugin_manager.transform_tool_result(tool_name=tool_name, result=result)
                    for plugin_event in plugin_events:
                        emit("plugin.hook", plugin_event)
                    try:
                        for plugin_event in await self.plugin_manager.post_tool_call(
                            tool_name=tool_name,
                            arguments=arguments,
                            result=result,
                            session_id=sid,
                            run_id=run_id,
                        ):
                            emit("plugin.hook", plugin_event)
                    except Exception as exc:
                        emit("plugin.hook_failed", {"hook": "post_tool_call", "tool": tool_name, "error": str(exc)})
                    if result.get("error_code") == "APPROVAL_REQUIRED":
                        emit(
                            "approval.pending",
                            {
                                "tool": tool_name,
                                "tool_call_id": tool_call_record["id"],
                                "approval": dict(result.get("data") or {}).get("approval"),
                            },
                        )
                    if tool_name == "agent_clarify" and dict(result.get("data") or {}).get("requires_user_input"):
                        emit(
                            "clarify.pending",
                            {
                                "tool": tool_name,
                                "tool_call_id": tool_call_record["id"],
                                "question": dict(result.get("data") or {}).get("question"),
                                "options": dict(result.get("data") or {}).get("options") or [],
                            },
                        )
                    if tool_name == "agent_delegate_task" and result.get("success"):
                        emit("subagent.spawned", dict(result.get("data") or {}))
                    if tool_name in {"agent_cronjob", "agent_job_run"}:
                        emit("cron.triggered", {"tool": tool_name, "success": bool(result.get("success"))})
                    if tool_name == "agent_webhook":
                        emit("webhook.triggered", {"success": bool(result.get("success"))})
                    guardrail_decision = tool_guardrails.observe(tool_name, arguments, result)
                    if guardrail_decision is not None:
                        result = attach_guardrail_metadata(result, guardrail_decision)
                        emit(
                            "tool.guardrail_halt" if guardrail_decision.action == "halt" else "tool.guardrail_warning",
                            {
                                "tool": tool_name,
                                "tool_call_id": tool_call_record["id"],
                                **guardrail_decision.to_metadata(),
                            },
                        )
                    tool_call_record["result"] = result
                    all_tool_calls.append(tool_call_record)
                    emit(
                        "tool.completed" if result.get("success") else "tool.failed",
                        {
                            "tool": tool_name,
                            "tool_call_id": tool_call_record["id"],
                            "success": bool(result.get("success")),
                            "latency_ms": int((time.perf_counter() - tool_started) * 1000),
                            "error_code": result.get("error_code"),
                        },
                    )
                    tool_message = {
                        "role": "tool",
                        "tool_call_id": tool_call_record["id"],
                        "name": tool_name,
                        "content": dumps_json(result, ensure_ascii=False, sort_keys=True),
                    }
                    working_messages.append(tool_message)
                    self.session_store.append_message(sid, tool_message)
                    if guardrail_decision is not None and guardrail_decision.action == "halt":
                        guardrail_halt = guardrail_decision.to_metadata()
                        status = "guardrail_halted"
                        final_content = guardrail_decision.message
                        break
                if guardrail_halt is not None:
                    break
            else:
                status = "max_iterations_reached"
                final_content = final_content or "Agent stopped after reaching max_iterations."
                emit("run.max_iterations_reached", {"max_iterations": self.max_iterations})
        except Exception as exc:
            status = "failed"
            final_content = f"Agent run failed: {exc}"
            emit("run.failed", {"error": str(exc)})

        if status != "failed" and not final_content:
            if all_tool_calls:
                names = ", ".join(item.get("name", "unknown_tool") for item in all_tool_calls)
                final_content = f"工具调用完成: {names}"
                emit("response.fallback", {"reason": "empty_model_after_tool_calls", "tool_call_count": len(all_tool_calls)})
            else:
                final_content = "AIASK model returned an empty response."
                emit("response.fallback", {"reason": "empty_model_response"})

        if status != "failed":
            emit("run.completed", {"status": status})
        try:
            for plugin_event in await self.plugin_manager.on_session_end(session_id=sid, run_id=run_id, status=status):
                emit("plugin.hook", plugin_event)
        except Exception as exc:
            emit("plugin.hook_failed", {"hook": "on_session_end", "error": str(exc)})
        response_id = f"resp_{uuid4().hex}"
        result = AgentRunResult(
            response_id=response_id,
            session_id=sid,
            run_id=run_id,
            content=final_content,
            tool_calls=all_tool_calls,
            usage=total_usage,
            audit_events=audit_events,
            messages=working_messages,
            events=persisted_events,
            status=status,
            context_summary_id=context_summary_id,
            planner_steps=planner_steps,
            subruns=list(self.subruns),
        )
        try:
            from .learning_loop import LearningLoop

            learning_events = LearningLoop(session_store=self.session_store, state_path=self.session_store.path).observe_run(result)
            for learning_event in learning_events:
                emit("learning.observed", learning_event)
            result.audit_events = audit_events
            result.events = persisted_events
        except Exception as exc:
            emit("learning.failed", {"error": str(exc)})
            result.audit_events = audit_events
            result.events = persisted_events
        payload = result.to_dict()
        try:
            for plugin_event in await self.plugin_manager.on_session_finalize(
                session_id=sid,
                run_id=run_id,
                status=status,
                response=payload,
            ):
                emit("plugin.hook", plugin_event)
            result.audit_events = audit_events
            result.events = persisted_events
            payload = result.to_dict()
        except Exception as exc:
            emit("plugin.hook_failed", {"hook": "on_session_finalize", "error": str(exc)})
            result.audit_events = audit_events
            result.events = persisted_events
            payload = result.to_dict()
        self.session_store.save_response(response_id, sid, payload)
        self.session_store.update_run(run_id, status=status, payload=payload)
        return result

    def _build_context(self, session_id: str) -> list[dict[str, Any]]:
        history = self.session_store.get_messages(session_id)
        if history and history[0].get("role") == "system":
            return list(history)
        return [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}, *history]

    @staticmethod
    def _normalize_message(message: dict[str, Any]) -> dict[str, Any]:
        payload = dict(message or {})
        role = str(payload.get("role") or "user").strip() or "user"
        payload["role"] = role
        payload.setdefault("content", "")
        return payload

    def _explicit_tool_call_from_context(self, messages: list[dict[str, Any]]) -> dict[str, Any] | None:
        text = self._latest_user_text(messages)
        if not text:
            return None
        match = re.search(r"tool:\s*(agent_[A-Za-z0-9_]+)", text)
        explicit_tool_syntax = True
        if not match:
            match = re.search(
                r"(?:调用|执行|运行|使用|call|use|run)\s*(?:工具|tool)?\s*[:：]?\s*(agent_[A-Za-z0-9_]+)",
                text,
                flags=re.IGNORECASE,
            )
            explicit_tool_syntax = False
        if not match:
            return None
        tool_name = match.group(1)
        tool = self.tool_registry.get(tool_name)
        if tool is None:
            return None
        metadata = dict(getattr(tool, "metadata", {}) or {})
        if not explicit_tool_syntax and not metadata_is_read_only(metadata, target=tool_name):
            return None
        arguments = self._json_object_after(text, match.end())
        return {
            "id": f"call_{uuid4().hex[:12]}",
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": dumps_json(arguments, ensure_ascii=False, sort_keys=True),
            },
        }

    @staticmethod
    def _latest_user_text(messages: list[dict[str, Any]]) -> str:
        for message in reversed(messages or []):
            if message.get("role") == "user":
                return str(message.get("content") or "")
        return ""

    @staticmethod
    def _json_object_after(text: str, start: int) -> dict[str, Any]:
        tail = str(text or "")[start:].lstrip()
        if not tail.startswith("{"):
            return {}
        try:
            parsed, _ = json.JSONDecoder().raw_decode(tail)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _register_runtime_bound_tools(self) -> None:
        policy = self.tool_registry.policy_engine.policy
        if policy.toolset != GENERAL_FULL_TOOLSET or not policy.general_tools_enabled:
            return
        descriptions = {
            "agent_delegate_task": "Delegate a bounded task to an in-process AIASK subagent.",
            "agent_execute_python": "Run Python code with AIASK tool RPC access to selected enabled tools.",
            "agent_job_run": "Run one local AIASK Agent background job immediately.",
            "agent_moa": "Run AIASK native mixture-of-agents synthesis through the configured model client.",
        }
        self.tool_registry.register(
            "agent_execute_python",
            description=descriptions["agent_execute_python"],
            parameters=TOOL_SCHEMAS["agent_execute_python"],
            handler=self._execute_python_tool,
            metadata={"category": "general_execute", "side_effect": "code_execution", "capability": "execute_python"},
        )
        self.tool_registry.register(
            "agent_delegate_task",
            description=descriptions["agent_delegate_task"],
            parameters=TOOL_SCHEMAS["agent_delegate_task"],
            handler=self._delegate_task,
            metadata={"category": "delegation", "side_effect": "subrun", "capability": "delegation"},
        )
        self.tool_registry.register(
            "agent_job_run",
            description=descriptions["agent_job_run"],
            parameters=TOOL_SCHEMAS["agent_job_run"],
            handler=self._run_job_tool,
            metadata={"category": "cron_admin", "side_effect": "subrun", "capability": "cron_run"},
        )
        self.tool_registry.register(
            "agent_moa",
            description=descriptions["agent_moa"],
            parameters=TOOL_SCHEMAS["agent_moa"],
            handler=self._moa_tool,
            metadata={"category": "moa", "side_effect": "external_generation", "capability": "mixture_of_agents"},
        )
        self.tool_registry.register(
            "agent_cronjob",
            description="Unified cron action API: create, list, update, pause, resume, remove, or trigger jobs.",
            parameters=TOOL_SCHEMAS["agent_cronjob"],
            handler=self._cronjob_tool,
            metadata={"category": "cron_admin", "side_effect": "stateful", "capability": "cronjob"},
            )

    async def _moa_tool(self, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_moa"
        try:
            from .moa import run_moa

            data = await run_moa(
                model_client=self.model_client,
                user_prompt=str(arguments.get("user_prompt") or ""),
                default_model=self.model,
                max_reference_tokens=arguments.get("max_reference_tokens"),
            )
            return aiask_envelope(
                bool(data.get("content")),
                data=data,
                error=None if data.get("content") else "MoA did not produce content",
                tool_name=tool,
                source_chain=["aiask_agent.moa"],
                side_effect={
                    "level": "external_generation",
                    "target": tool,
                    "confirmation_required": False,
                    "idempotent": False,
                },
            )
        except Exception as exc:
            return aiask_envelope(
                False,
                data=None,
                error=str(exc),
                tool_name=tool,
                source_chain=["aiask_agent.moa"],
                error_code="MOA_FAILED",
            )

    async def _execute_python_tool(self, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_execute_python"
        code = str(arguments.get("code") or "")
        if not code.strip():
            return aiask_envelope(
                False,
                data=None,
                error="code is required",
                tool_name=tool,
                source_chain=["aiask_agent.code_execution"],
                error_code="INVALID_REQUEST",
            )
        guard = WorkspaceGuard(self.tool_registry.policy_engine.policy)
        try:
            cwd = guard.resolve(arguments.get("cwd") or ".", must_exist=True)
        except Exception as exc:
            return aiask_envelope(
                False,
                data=None,
                error=str(exc),
                tool_name=tool,
                source_chain=["aiask_agent.code_execution"],
                error_code="INVALID_CWD",
            )
        max_output = bounded_int(arguments.get("max_output_bytes"), default=65536, minimum=1, maximum=1024 * 1024)
        timeout = bounded_float(arguments.get("timeout_seconds"), default=30.0, minimum=1.0, maximum=300.0)
        max_tool_calls = bounded_int(arguments.get("max_tool_calls"), default=20, minimum=0, maximum=50)
        allowed_tools = self._code_rpc_allowed_tools()
        tool_call_log: list[dict[str, Any]] = []
        tool_call_count = 0

        with tempfile.TemporaryDirectory(prefix="aiask_agent_code_") as tmp:
            tmp_path = Path(tmp)
            module_path = tmp_path / "aiask_tools.py"
            script_path = tmp_path / "snippet.py"
            socket_path: Path | None = None
            rpc_host = ""
            rpc_port = 0

            async def handle_rpc(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                nonlocal tool_call_count
                try:
                    while True:
                        line = await reader.readline()
                        if not line:
                            break
                        try:
                            request = json.loads(line.decode("utf-8"))
                            name = str(request.get("tool") or "").strip()
                            args = dict(request.get("args") or {})
                        except Exception as exc:
                            response = {"success": False, "error": f"invalid RPC request: {exc}", "data": None}
                        else:
                            if name not in allowed_tools:
                                response = {
                                    "success": False,
                                    "error": f"tool is not available in agent_execute_python: {name}",
                                    "data": None,
                                    "error_code": "TOOL_NOT_ALLOWED",
                                }
                            elif tool_call_count >= max_tool_calls:
                                response = {
                                    "success": False,
                                    "error": f"tool call limit reached: {max_tool_calls}",
                                    "data": None,
                                    "error_code": "TOOL_CALL_LIMIT",
                                }
                            else:
                                if name == "agent_terminal":
                                    for blocked in ("background", "approval_id"):
                                        args.pop(blocked, None)
                                started = time.perf_counter()
                                response = await self.tool_registry.call_tool(name, args)
                                tool_call_count += 1
                                tool_call_log.append(
                                    {
                                        "tool": name,
                                        "success": bool(response.get("success")),
                                        "latency_ms": int((time.perf_counter() - started) * 1000),
                                    }
                                )
                        writer.write((dumps_json(response, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
                        await writer.drain()
                finally:
                    writer.close()
                    await writer.wait_closed()

            if hasattr(asyncio, "start_unix_server") and os.name != "nt":
                socket_path = Path("/tmp") / f"aiask_rpc_{uuid4().hex}.sock"
                server = await asyncio.start_unix_server(handle_rpc, path=str(socket_path))
                rpc_socket = str(socket_path)
            else:
                server = await asyncio.start_server(handle_rpc, host="127.0.0.1", port=0)
                sock = next((item for item in (server.sockets or []) if item.family in {socket.AF_INET, socket.AF_INET6}), None)
                if sock is None:
                    raise RuntimeError("AIASK tool RPC server did not bind a TCP socket")
                rpc_host, rpc_port = sock.getsockname()[:2]
                rpc_socket = ""
            module_path.write_text(self._build_aiask_tools_module(allowed_tools), encoding="utf-8")
            script_path.write_text(code, encoding="utf-8")
            try:
                env = _sanitized_env()
                env["AIASK_RPC_SOCKET"] = rpc_socket
                if rpc_host and rpc_port:
                    env["AIASK_RPC_HOST"] = str(rpc_host)
                    env["AIASK_RPC_PORT"] = str(rpc_port)
                env["PYTHONDONTWRITEBYTECODE"] = "1"
                env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), env.get("PYTHONPATH", "")]).strip(os.pathsep)
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    str(script_path),
                    cwd=str(cwd),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                    timed_out = False
                except asyncio.TimeoutError:
                    proc.kill()
                    stdout, stderr = await proc.communicate()
                    timed_out = True
                out_text, out_truncated = _limit_bytes(stdout or b"", max_output)
                err_text, err_truncated = _limit_bytes(stderr or b"", max_output)
            finally:
                server.close()
                await server.wait_closed()
                if socket_path is not None:
                    try:
                        socket_path.unlink()
                    except FileNotFoundError:
                        pass
        return aiask_envelope(
            proc.returncode == 0 and not timed_out,
            data={
                "cwd": str(cwd),
                "returncode": proc.returncode,
                "stdout": out_text,
                "stderr": err_text,
                "timed_out": timed_out,
                "truncated": out_truncated or err_truncated,
                "available_rpc_tools": sorted(allowed_tools),
                "tool_calls": tool_call_log,
            },
            error=None if proc.returncode == 0 and not timed_out else "python execution failed",
            tool_name=tool,
            source_chain=["aiask_agent.code_execution"],
            side_effect={
                "level": "code_execution",
                "target": str(cwd),
                "confirmation_required": False,
                "idempotent": False,
            },
            error_code=None if proc.returncode == 0 and not timed_out else "PYTHON_EXECUTION_FAILED",
        )

    def _code_rpc_allowed_tools(self) -> set[str]:
        candidates = {
            "agent_web_search",
            "agent_web_extract",
            "agent_file_read",
            "agent_file_write",
            "agent_file_search",
            "agent_file_patch",
            "agent_terminal",
        }
        return {name for name in candidates if self.tool_registry.get(name) is not None}

    @staticmethod
    def _build_aiask_tools_module(tool_names: set[str]) -> str:
        header = '''"""Auto-generated AIASK tool RPC stubs."""
import json
import os
import shlex
import socket
import time

_sock = None

def _connect():
    global _sock
    if _sock is None:
        if os.environ.get("AIASK_RPC_SOCKET"):
            _sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            _sock.connect(os.environ["AIASK_RPC_SOCKET"])
        else:
            _sock = socket.create_connection((os.environ["AIASK_RPC_HOST"], int(os.environ["AIASK_RPC_PORT"])), timeout=300)
        _sock.settimeout(300)
    return _sock

def _call(tool_name, args=None, **kwargs):
    payload = dict(args or {})
    payload.update(kwargs)
    conn = _connect()
    conn.sendall((json.dumps({"tool": tool_name, "args": payload}) + "\\n").encode("utf-8"))
    buf = b""
    while not buf.endswith(b"\\n"):
        chunk = conn.recv(65536)
        if not chunk:
            raise RuntimeError("AIASK RPC disconnected")
        buf += chunk
    return json.loads(buf.decode("utf-8"))

def call_tool(tool_name, **kwargs):
    return _call(tool_name, kwargs)

def shell_quote(value):
    return shlex.quote(str(value))

def retry(fn, max_attempts=3, delay=1.0):
    last_error = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if attempt < max_attempts - 1:
                time.sleep(delay * (2 ** attempt))
    raise last_error

'''
        stubs = []
        for name in sorted(tool_names):
            stubs.append(
                f"def {name}(**kwargs):\n"
                f"    return _call({name!r}, kwargs)\n"
            )
        return header + "\n".join(stubs)

    async def _delegate_task(self, arguments: dict[str, Any]) -> dict[str, Any]:
        task = str(arguments.get("task") or "").strip()
        if not task:
            return aiask_envelope(
                False,
                data=None,
                error="task is required",
                tool_name="agent_delegate_task",
                source_chain=["aiask_agent.subagents"],
                error_code="INVALID_REQUEST",
            )
        requested_toolset = str(arguments.get("toolset") or FINANCE_SAFE_TOOLSET).strip()
        if requested_toolset == GENERAL_FULL_TOOLSET and not self.tool_registry.policy_engine.policy.general_tools_enabled:
            requested_toolset = FINANCE_SAFE_TOOLSET
        child_policy = ToolPolicy(
            toolset=requested_toolset if requested_toolset in {FINANCE_SAFE_TOOLSET, GENERAL_FULL_TOOLSET} else FINANCE_SAFE_TOOLSET,
            general_tools_enabled=self.tool_registry.policy_engine.policy.general_tools_enabled,
            workspace_roots=self.tool_registry.policy_engine.policy.workspace_roots,
        )
        child_registry = build_default_tool_registry(
            policy_engine=ToolPolicyEngine(child_policy),
            session_store=self.session_store,
        )
        child = AgentRuntime(
            model_client=self.model_client,
            tool_registry=child_registry,
            session_store=self.session_store,
            model=self.model,
            max_iterations=bounded_int(
                arguments.get("max_iterations"),
                default=min(self.max_iterations, 4),
                minimum=1,
                maximum=self.max_iterations,
            ),
            model_timeout_seconds=self.model_timeout_seconds,
            tool_timeout_seconds=self.tool_timeout_seconds,
            retry_attempts=self.retry_attempts,
        )
        child.scheduler.stop()
        
        system_prompt = arguments.get("system_prompt")
        role = arguments.get("role")
        messages = []
        if system_prompt or role:
            role_desc = role or "Financial Sub-Agent"
            prompt_content = system_prompt or f"You are acting as: {role_desc}. Focus only on the requested task."
            messages.append({"role": "system", "content": prompt_content})
            
        messages.append({"role": "user", "content": task})
        
        result = await child.run(messages, user_id=arguments.get("user_id"))
        record = {"run_id": result.run_id, "response_id": result.response_id, "toolset": child_policy.toolset}
        self.subruns.append(record)
        return aiask_envelope(
            True,
            data={"subrun": record, "content": result.content},
            error=None,
            tool_name="agent_delegate_task",
            source_chain=["aiask_agent.subagents"],
            side_effect={
                "level": "subrun",
                "target": result.run_id,
                "confirmation_required": False,
                "idempotent": False,
            },
        )

    async def _run_job_tool(self, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await self.scheduler.run_job(str(arguments.get("job_id") or ""))
        return aiask_envelope(
            bool(result.get("success")),
            data=result.get("data"),
            error=result.get("error"),
            tool_name="agent_job_run",
            source_chain=["aiask_agent.scheduler"],
            side_effect={
                "level": "subrun",
                "target": arguments.get("job_id"),
                "confirmation_required": False,
                "idempotent": False,
            },
            error_code=result.get("error_code"),
        )

    async def _cronjob_tool(self, arguments: dict[str, Any]) -> dict[str, Any]:
        action = str(arguments.get("action") or "list").strip().lower()
        if action == "trigger":
            return await self._run_job_tool(arguments)
        try:
            if action == "list":
                data = {"jobs": self.job_store.list()}
            elif action == "create":
                data = {
                    "job": self.job_store.create(
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
                data = {"job": self.job_store.update(str(arguments.get("job_id") or ""), enabled=action == "resume")}
            elif action == "update":
                data = {"job": self.job_store.update(str(arguments.get("job_id") or ""), **{k: v for k, v in arguments.items() if k in {"name", "prompt", "schedule", "interval_seconds", "toolset", "enabled"}})}
            elif action == "remove":
                data = {"deleted": self.job_store.delete(str(arguments.get("job_id") or ""))}
            else:
                raise ValueError(f"unsupported cronjob action: {action}")
            return aiask_envelope(
                True,
                data=data,
                error=None,
                tool_name="agent_cronjob",
                source_chain=["aiask_agent.scheduler"],
                side_effect={
                    "level": "read_only" if action == "list" else "stateful",
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

    @staticmethod
    def _parse_tool_call(call: dict[str, Any]) -> tuple[str, dict[str, Any], bool]:
        function = dict(call.get("function") or {})
        name = str(function.get("name") or call.get("name") or "").strip()
        raw_arguments = function.get("arguments", call.get("arguments", {}))
        if isinstance(raw_arguments, dict):
            arguments = dict(raw_arguments)
            corrected = False
        else:
            try:
                parsed = json.loads(str(raw_arguments or "{}"))
                arguments = parsed if isinstance(parsed, dict) else {}
                corrected = False
            except Exception:
                arguments = {}
                corrected = True
        return name, arguments, corrected

    @staticmethod
    def _merge_usage(current: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
        merged = dict(current or {})
        for key, value in dict(update or {}).items():
            if isinstance(value, (int, float)):
                merged[key] = merged.get(key, 0) + value
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
        return sum(max(1, len(str(message.get("content") or "")) // 4) + 8 for message in messages)
