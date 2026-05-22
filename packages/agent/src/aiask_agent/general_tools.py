from __future__ import annotations

import asyncio
import base64
import difflib
import hashlib
import json
import os
import sys
import tempfile
import time
import tomllib
from pathlib import Path
from typing import Any
from uuid import uuid4

from .approvals import ApprovalStore, command_requires_approval
from .plugin_runtime import NativePluginManager
from .process_registry import ProcessRegistry
from .terminal_backends import TerminalBackendError, TerminalBackendManager, TerminalInvocation, backend_status, command_targets_aiask_runtime
from .tools.policy import ToolPolicy, build_policy_from_env


def _envelope(
    success: bool,
    *,
    data: Any = None,
    error: str | None = None,
    tool_name: str,
    level: str,
    target: str | None = None,
    idempotent: bool = True,
) -> dict[str, Any]:
    return {
        "success": bool(success),
        "data": data,
        "error": error,
        "meta": {
            "trace_id": f"aiask-agent:{tool_name}:{int(time.time() * 1000)}:{uuid4().hex[:8]}",
            "source_chain": ["aiask_agent.general_tools"],
            "side_effect": {
                "level": level,
                "target": target or tool_name,
                "confirmation_required": False,
                "idempotent": idempotent,
            },
        },
    }


class WorkspaceGuard:
    def __init__(self, policy: ToolPolicy | None = None) -> None:
        self.policy = policy or build_policy_from_env()
        self.roots = tuple(Path(root).expanduser().resolve() for root in self.policy.workspace_roots)

    def resolve(self, raw: str | None, *, must_exist: bool = False) -> Path:
        token = str(raw or ".").strip() or "."
        path = Path(token).expanduser()
        if not path.is_absolute():
            path = self.roots[0] / path
        resolved = path.resolve()
        if must_exist and not resolved.exists():
            raise FileNotFoundError(str(resolved))
        if not self._is_allowed(resolved):
            allowed = ", ".join(str(root) for root in self.roots)
            raise PermissionError(f"path is outside allowed AIASK Agent workspace roots: {resolved}; roots={allowed}")
        return resolved

    def _is_allowed(self, path: Path) -> bool:
        for root in self.roots:
            try:
                path.relative_to(root)
                return True
            except ValueError:
                continue
        return False


def _limit_bytes(value: bytes, limit: int) -> tuple[str, bool]:
    limited = max(1, min(int(limit or 65536), 1024 * 1024))
    truncated = len(value) > limited
    return value[:limited].decode("utf-8", errors="replace"), truncated


def _is_binary(raw: bytes) -> bool:
    if not raw:
        return False
    sample = raw[:4096]
    return b"\x00" in sample


def _truthy_env(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _sanitized_env() -> dict[str, str]:
    blocked = ("KEY", "TOKEN", "SECRET", "PASSWORD", "COOKIE", "AUTH", "CREDENTIAL")
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if any(token in upper for token in blocked):
            continue
        env[key] = value
    return env


def _sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mutation_verification(path: Path, guard: WorkspaceGuard, *, operation: str, before_sha256: str | None = None) -> dict[str, Any]:
    exists = path.exists()
    stat = path.stat() if exists else None
    after_sha256 = _sha256_file(path)
    return {
        "operation": operation,
        "path": str(path),
        "exists": exists,
        "is_file": bool(path.is_file()) if exists else False,
        "allowed_workspace": guard._is_allowed(path.resolve()),
        "size_bytes": stat.st_size if stat else None,
        "mtime": stat.st_mtime if stat else None,
        "sha256": after_sha256,
        "before_sha256": before_sha256,
        "changed": before_sha256 != after_sha256,
    }


def _python_diagnostics(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() != ".py" or not path.exists() or not path.is_file():
        return []
    import py_compile

    try:
        py_compile.compile(str(path), doraise=True)
        return [{"path": str(path), "language": "python", "status": "passed", "source": "py_compile"}]
    except py_compile.PyCompileError as exc:
        error = exc.exc_value
        return [
            {
                "path": str(path),
                "language": "python",
                "status": "failed",
                "source": "py_compile",
                "message": str(error),
                "line": getattr(error, "lineno", None),
                "offset": getattr(error, "offset", None),
            }
        ]
    except Exception as exc:
        return [{"path": str(path), "language": "python", "status": "failed", "source": "py_compile", "message": str(exc)}]


def _json_diagnostics(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() != ".json" or not path.exists() or not path.is_file():
        return []
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return [{"path": str(path), "language": "json", "status": "passed", "source": "json"}]
    except json.JSONDecodeError as exc:
        return [
            {
                "path": str(path),
                "language": "json",
                "status": "failed",
                "source": "json",
                "message": exc.msg,
                "line": exc.lineno,
                "offset": exc.colno,
            }
        ]


def _toml_diagnostics(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() != ".toml" or not path.exists() or not path.is_file():
        return []
    try:
        tomllib.loads(path.read_text(encoding="utf-8"))
        return [{"path": str(path), "language": "toml", "status": "passed", "source": "tomllib"}]
    except tomllib.TOMLDecodeError as exc:
        return [{"path": str(path), "language": "toml", "status": "failed", "source": "tomllib", "message": str(exc)}]


def _yaml_diagnostics(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() not in {".yaml", ".yml"} or not path.exists() or not path.is_file():
        return []
    try:
        import yaml  # type: ignore[import-not-found]
    except Exception:
        return [
            {
                "path": str(path),
                "language": "yaml",
                "status": "skipped",
                "source": "pyyaml",
                "message": "PyYAML not installed; YAML diagnostics skipped (best-effort).",
            }
        ]
    try:
        yaml.safe_load(path.read_text(encoding="utf-8"))
        return [{"path": str(path), "language": "yaml", "status": "passed", "source": "pyyaml"}]
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        return [
            {
                "path": str(path),
                "language": "yaml",
                "status": "failed",
                "source": "pyyaml",
                "message": str(getattr(exc, "problem", exc)),
                "line": (mark.line + 1) if mark is not None else None,
                "offset": (mark.column + 1) if mark is not None else None,
            }
        ]


def _write_diagnostics(path: Path) -> list[dict[str, Any]]:
    return [*_python_diagnostics(path), *_json_diagnostics(path), *_toml_diagnostics(path), *_yaml_diagnostics(path)]


def build_general_tool_handlers(policy: ToolPolicy | None = None, *, state_path: Path | None = None) -> dict[str, Any]:
    guard = WorkspaceGuard(policy)
    processes = ProcessRegistry(state_path)
    approvals = ApprovalStore(state_path)
    session_cwds: dict[str, str] = {}
    processes.recover_running(allowed_roots=guard.roots)
    terminal_manager = TerminalBackendManager(processes, allowed_roots=guard.roots)
    plugin_manager = NativePluginManager()

    async def file_read(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_file_read"
        try:
            path = guard.resolve(arguments.get("path"), must_exist=True)
            if not path.is_file():
                raise IsADirectoryError(str(path))
            raw = path.read_bytes()
            if _is_binary(raw):
                raise ValueError("binary file reads are blocked by AIASK file safety")
            content, truncated = _limit_bytes(raw, int(arguments.get("max_bytes") or 262144))
            return _envelope(
                True,
                data={"path": str(path), "content": content, "bytes": len(raw), "truncated": truncated},
                tool_name=tool,
                level="read_only",
                target=str(path),
            )
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="read_only")

    async def file_write(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_file_write"
        try:
            path = guard.resolve(arguments.get("path"))
            before_sha256 = _sha256_file(path)
            if bool(arguments.get("create_parent_dirs", False)):
                path.parent.mkdir(parents=True, exist_ok=True)
            content = str(arguments.get("content") or "")
            path.write_text(content, encoding="utf-8")
            return _envelope(
                True,
                data={
                    "path": str(path),
                    "bytes": len(content.encode("utf-8")),
                    "mutation_verification": _mutation_verification(path, guard, operation="write", before_sha256=before_sha256),
                    "diagnostics": _write_diagnostics(path),
                },
                tool_name=tool,
                level="filesystem_write",
                target=str(path),
                idempotent=False,
            )
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="filesystem_write", idempotent=False)

    async def file_list(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_file_list"
        try:
            root = guard.resolve(arguments.get("path"), must_exist=True)
            limit = max(1, min(int(arguments.get("limit") or 200), 1000))
            iterator = root.rglob("*") if bool(arguments.get("recursive", False)) else root.iterdir()
            items: list[dict[str, Any]] = []
            for item in iterator:
                if not guard._is_allowed(item.resolve()):
                    continue
                items.append(
                    {
                        "path": str(item),
                        "name": item.name,
                        "type": "directory" if item.is_dir() else "file",
                        "bytes": item.stat().st_size if item.is_file() else None,
                    }
                )
                if len(items) >= limit:
                    break
            return _envelope(True, data={"path": str(root), "items": items}, tool_name=tool, level="read_only")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="read_only")

    async def file_search(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_file_search"
        try:
            root = guard.resolve(arguments.get("path"), must_exist=True)
            query = str(arguments.get("query") or "")
            if not query:
                raise ValueError("query is required")
            limit = max(1, min(int(arguments.get("limit") or 50), 200))
            files = [root] if root.is_file() else list(root.rglob("*"))
            matches: list[dict[str, Any]] = []
            for file_path in files:
                if len(matches) >= limit:
                    break
                if not file_path.is_file() or not guard._is_allowed(file_path.resolve()):
                    continue
                try:
                    for lineno, line in enumerate(file_path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                        if query.lower() in line.lower():
                            matches.append({"path": str(file_path), "line": lineno, "text": line[:500]})
                            if len(matches) >= limit:
                                break
                except Exception:
                    continue
            return _envelope(True, data={"query": query, "matches": matches}, tool_name=tool, level="read_only")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="read_only")

    async def file_patch(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_file_patch"
        try:
            path = guard.resolve(arguments.get("path"), must_exist=True)
            before_sha256 = _sha256_file(path)
            old = str(arguments.get("old") or "")
            new = str(arguments.get("new") or "")
            if not old:
                raise ValueError("old text is required")
            count = max(1, int(arguments.get("count") or 1))
            text = path.read_text(encoding="utf-8")
            if old not in text:
                candidates = difflib.get_close_matches(old, text.splitlines(), n=1, cutoff=0.75)
                if not candidates:
                    raise ValueError("old text was not found")
                old = candidates[0]
            updated = text.replace(old, new, count)
            path.write_text(updated, encoding="utf-8")
            return _envelope(
                True,
                data={
                    "path": str(path),
                    "replacements": min(count, text.count(old)),
                    "mutation_verification": _mutation_verification(path, guard, operation="patch", before_sha256=before_sha256),
                    "diagnostics": _write_diagnostics(path),
                },
                tool_name=tool,
                level="filesystem_write",
                target=str(path),
                idempotent=False,
            )
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="filesystem_write", idempotent=False)

    async def file_mutation_verify(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_file_mutation_verify"
        try:
            path = guard.resolve(arguments.get("path"), must_exist=False)
            operation = str(arguments.get("operation") or "verify").strip().lower() or "verify"
            before_sha256 = str(arguments.get("before_sha256") or "").strip() or None
            data = _mutation_verification(path, guard, operation=operation, before_sha256=before_sha256)
            if bool(arguments.get("include_diagnostics", True)):
                data["diagnostics"] = _write_diagnostics(path)
            return _envelope(True, data=data, tool_name=tool, level="read_only", target=str(path))
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="read_only")

    async def terminal(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_terminal"
        try:
            command = str(arguments.get("command") or "").strip()
            if not command:
                raise ValueError("command is required")
            approval_id = str(arguments.get("approval_id") or "").strip()
            if command_targets_aiask_runtime(command) or command_requires_approval(command):
                approval = approvals.get(approval_id) if approval_id else None
                if not approval or approval.get("status") != "approved":
                    reason = "command targets the AIASK server or gateway runtime" if command_targets_aiask_runtime(command) else "dangerous command requires control-plane approval"
                    pending = approvals.create(
                        tool_name=tool,
                        action="terminal",
                        arguments={"command": command, "cwd": arguments.get("cwd") or "."},
                        reason=reason,
                    )
                    payload = _envelope(
                        False,
                        data={"approval": pending},
                        error="approval required",
                        tool_name=tool,
                        level="process_execution",
                        idempotent=False,
                    )
                    payload["error_code"] = "APPROVAL_REQUIRED"
                    return payload
            if command.lower().startswith("aiask-allow "):
                command = command[len("aiask-allow ") :].strip()
            backend = str(arguments.get("backend") or "local").strip().lower() or "local"
            backend_info = backend_status(backend)
            session_id = str(arguments.get("session_id") or "").strip()
            cwd_raw = arguments.get("cwd")
            if cwd_raw is None and session_id and session_id in session_cwds:
                cwd_raw = session_cwds[session_id]
            if backend in {"local", "docker", "singularity"}:
                cwd = guard.resolve(cwd_raw or ".", must_exist=True)
                cwd_value = str(cwd)
            else:
                cwd_value = str(cwd_raw or ".")
            if session_id:
                session_cwds[session_id] = cwd_value
            timeout = max(1.0, min(float(arguments.get("timeout_seconds") or 30), 300.0))
            max_output = max(1, min(int(arguments.get("max_output_bytes") or 65536), 1024 * 1024))
            env = _sanitized_env()
            for key in list(arguments.get("env_allowlist") or []):
                key = str(key or "").strip()
                if key and key in os.environ:
                    env[key] = os.environ[key]
            data = await terminal_manager.execute(
                TerminalInvocation(
                    command=command,
                    cwd=cwd_value,
                    backend=backend,
                    session_id=session_id or None,
                    stdin=arguments.get("stdin"),
                    background=bool(arguments.get("background", False)),
                    pty=bool(arguments.get("pty", False)),
                    image=arguments.get("image"),
                    resource_limits=dict(arguments.get("resource_limits") or {}),
                    timeout_seconds=timeout,
                    max_output_bytes=max_output,
                    env=env,
                    notify_on_complete=bool(arguments.get("notify_on_complete", False)),
                )
            )
            data, plugin_events = await plugin_manager.transform_terminal_output(command=command, output=data)
            if plugin_events:
                data["plugin_events"] = plugin_events
            return _envelope(
                True,
                data=data,
                tool_name=tool,
                level="process_execution",
                target=cwd_value,
                idempotent=False,
            )
        except TerminalBackendError as exc:
            payload = _envelope(
                False,
                data={"backend": exc.status.to_dict() if exc.status else None},
                error=str(exc),
                tool_name=tool,
                level="process_execution",
                idempotent=False,
            )
            payload["error_code"] = exc.code
            return payload
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="process_execution", idempotent=False)

    async def process(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_process"
        action = str(arguments.get("action") or "list").strip().lower()
        try:
            if action == "list":
                data = {
                    "items": processes.list(
                        session_id=arguments.get("session_id"),
                        limit=int(arguments.get("limit") or 100),
                    )
                }
            elif action == "read":
                process_id = str(arguments.get("process_id") or "").strip()
                data = processes.read_output(
                    process_id,
                    max_bytes=int(arguments.get("max_output_bytes") or 65536),
                    tail=bool(arguments.get("tail", True)),
                )
            elif action == "kill":
                data = await terminal_manager.process_action(arguments)
            elif action == "wait":
                data = await terminal_manager.process_action(arguments)
            else:
                data = await terminal_manager.process_action(arguments)
            return _envelope(True, data=data, tool_name=tool, level="process_control", idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="process_control", idempotent=False)

    async def execute_python(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_execute_python"
        code = str(arguments.get("code") or "")
        if not code:
            return _envelope(False, error="code is required", tool_name=tool, level="code_execution", idempotent=False)
        with tempfile.TemporaryDirectory(prefix="aiask_agent_code_") as tmp:
            script = Path(tmp) / "snippet.py"
            script.write_text(code, encoding="utf-8")
            next_args = dict(arguments)
            next_args["command"] = f"{sys.executable} {script}"
            next_args.setdefault("cwd", arguments.get("cwd") or str(guard.roots[0]))
            result = await terminal(next_args)
            result["meta"]["source_chain"].append("aiask_agent.general_tools.execute_python")
            result["meta"]["side_effect"]["level"] = "code_execution"
            return result

    browser_state: dict[str, Any] = {"playwright": None, "browser": None, "page": None, "console": []}

    async def ensure_page() -> Any:
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:
            raise RuntimeError("browser automation requires optional dependency: playwright") from exc
        if browser_state["page"] is not None:
            return browser_state["page"]
        browser_state["playwright"] = await async_playwright().start()
        browser_state["browser"] = await browser_state["playwright"].chromium.launch(headless=True)
        browser_state["page"] = await browser_state["browser"].new_page()
        browser_state["page"].on(
            "console",
            lambda msg: browser_state["console"].append(
                {"type": msg.type, "text": msg.text, "timestamp": int(time.time() * 1000)}
            ),
        )
        return browser_state["page"]

    async def browser_navigate(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_browser_navigate"
        url = str(arguments.get("url") or "").strip()
        try:
            if not url:
                raise ValueError("url is required")
            page = await ensure_page()
            response = await page.goto(url, wait_until="domcontentloaded")
            return _envelope(
                True,
                data={"url": page.url, "status": response.status if response else None, "title": await page.title()},
                tool_name=tool,
                level="browser_state",
                target=url,
                idempotent=False,
            )
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="browser_state", idempotent=False)

    async def browser_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_browser_snapshot"
        try:
            page = await ensure_page()
            return _envelope(
                True,
                data={"url": page.url, "title": await page.title(), "text": (await page.locator("body").inner_text())[:20000]},
                tool_name=tool,
                level="read_only",
                target=page.url,
            )
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="read_only")

    async def browser_click(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_browser_click"
        try:
            selector = str(arguments.get("selector") or "").strip()
            if not selector:
                raise ValueError("selector is required")
            page = await ensure_page()
            await page.locator(selector).first.click()
            return _envelope(
                True,
                data={"url": page.url, "selector": selector},
                tool_name=tool,
                level="browser_state",
                target=selector,
                idempotent=False,
            )
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="browser_state", idempotent=False)

    async def browser_type(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_browser_type"
        try:
            selector = str(arguments.get("selector") or "").strip()
            text = str(arguments.get("text") or "")
            if not selector:
                raise ValueError("selector is required")
            page = await ensure_page()
            await page.locator(selector).first.fill(text)
            return _envelope(
                True,
                data={"url": page.url, "selector": selector, "chars": len(text)},
                tool_name=tool,
                level="browser_state",
                target=selector,
                idempotent=False,
            )
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="browser_state", idempotent=False)

    async def browser_extract(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_browser_extract"
        try:
            selector = str(arguments.get("selector") or "body").strip() or "body"
            page = await ensure_page()
            text = await page.locator(selector).first.inner_text()
            return _envelope(
                True,
                data={"url": page.url, "selector": selector, "text": text[:20000], "truncated": len(text) > 20000},
                tool_name=tool,
                level="read_only",
                target=selector,
            )
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="read_only")

    async def browser_scroll(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_browser_scroll"
        try:
            page = await ensure_page()
            amount = max(1, min(int(arguments.get("amount") or 600), 5000))
            direction = str(arguments.get("direction") or "down").lower()
            dx = amount if direction == "right" else -amount if direction == "left" else 0
            dy = amount if direction == "down" else -amount if direction == "up" else 0
            selector = str(arguments.get("selector") or "").strip()
            if selector:
                await page.locator(selector).first.evaluate("(el, delta) => el.scrollBy(delta.x, delta.y)", {"x": dx, "y": dy})
            else:
                await page.mouse.wheel(dx, dy)
            return _envelope(True, data={"url": page.url, "direction": direction, "amount": amount}, tool_name=tool, level="browser_state", idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="browser_state", idempotent=False)

    async def browser_back(_: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_browser_back"
        try:
            page = await ensure_page()
            response = await page.go_back(wait_until="domcontentloaded")
            return _envelope(True, data={"url": page.url, "status": response.status if response else None}, tool_name=tool, level="browser_state", idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="browser_state", idempotent=False)

    async def browser_press(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_browser_press"
        try:
            key = str(arguments.get("key") or "").strip()
            if not key:
                raise ValueError("key is required")
            page = await ensure_page()
            await page.keyboard.press(key)
            return _envelope(True, data={"url": page.url, "key": key}, tool_name=tool, level="browser_state", idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="browser_state", idempotent=False)

    async def browser_get_images(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_browser_get_images"
        try:
            page = await ensure_page()
            limit = max(1, min(int(arguments.get("limit") or 30), 100))
            images = await page.locator("img").evaluate_all(
                "(imgs, limit) => imgs.slice(0, limit).map((img) => ({src: img.currentSrc || img.src, alt: img.alt || '', width: img.naturalWidth || img.width, height: img.naturalHeight || img.height}))",
                limit,
            )
            return _envelope(True, data={"url": page.url, "images": images}, tool_name=tool, level="read_only")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="read_only")

    async def browser_vision(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_browser_vision"
        try:
            page = await ensure_page()
            shot = await page.screenshot(full_page=False)
            return _envelope(
                True,
                data={"url": page.url, "title": await page.title(), "screenshot_bytes": len(shot), "prompt": arguments.get("prompt")},
                tool_name=tool,
                level="read_only",
            )
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="read_only")

    async def browser_console(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_browser_console"
        limit = max(1, min(int(arguments.get("limit") or 100), 500))
        return _envelope(True, data={"messages": list(browser_state["console"])[-limit:]}, tool_name=tool, level="read_only")

    async def browser_cdp(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_browser_cdp"
        try:
            method = str(arguments.get("method") or "").strip()
            if not method:
                raise ValueError("method is required")
            if not method.startswith(("Runtime.", "Page.", "DOM.", "Network.")):
                raise PermissionError("CDP method is outside the AIASK allowed namespaces")
            page = await ensure_page()
            session = await page.context.new_cdp_session(page)
            result = await session.send(method, dict(arguments.get("params") or {}))
            return _envelope(True, data={"method": method, "result": result}, tool_name=tool, level="browser_state", idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="browser_state", idempotent=False)

    async def computer_use(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_computer_use"
        action = str(arguments.get("action") or "status").strip().lower()
        enabled = _truthy_env("AIASK_AGENT_ENABLE_COMPUTER_USE")
        base_status = {
            "configured": enabled,
            "enabled": enabled,
            "backend": "browser_session",
            "os_desktop_control": False,
            "required_env": ["AIASK_AGENT_ENABLE_COMPUTER_USE"],
            "actions": ["status", "screenshot", "browser_click", "browser_type", "browser_key"],
        }
        if action == "status":
            return _envelope(True, data=base_status, tool_name=tool, level="read_only")
        if not enabled:
            return _envelope(
                False,
                data=base_status,
                error="computer_use is disabled",
                tool_name=tool,
                level="browser_state",
                idempotent=False,
            )
        try:
            page = await ensure_page()
            if action == "screenshot":
                shot = await page.screenshot(full_page=bool(arguments.get("full_page", False)))
                include_base64 = bool(arguments.get("include_base64", False))
                data: dict[str, Any] = {
                    **base_status,
                    "url": page.url,
                    "title": await page.title(),
                    "screenshot_bytes": len(shot),
                    "image_format": "png",
                }
                if include_base64:
                    data["screenshot_base64"] = base64.b64encode(shot).decode("ascii")
                return _envelope(True, data=data, tool_name=tool, level="read_only", target=page.url)
            if action == "browser_click":
                selector = str(arguments.get("selector") or "").strip()
                if not selector:
                    raise ValueError("selector is required")
                await page.locator(selector).first.click()
                return _envelope(True, data={**base_status, "url": page.url, "selector": selector}, tool_name=tool, level="browser_state", target=selector, idempotent=False)
            if action == "browser_type":
                selector = str(arguments.get("selector") or "").strip()
                text = str(arguments.get("text") or "")
                if not selector:
                    raise ValueError("selector is required")
                await page.locator(selector).first.fill(text)
                return _envelope(True, data={**base_status, "url": page.url, "selector": selector, "chars": len(text)}, tool_name=tool, level="browser_state", target=selector, idempotent=False)
            if action == "browser_key":
                key = str(arguments.get("key") or "").strip()
                if not key:
                    raise ValueError("key is required")
                await page.keyboard.press(key)
                return _envelope(True, data={**base_status, "url": page.url, "key": key}, tool_name=tool, level="browser_state", target=key, idempotent=False)
            raise ValueError(f"unsupported computer_use action: {action}")
        except Exception as exc:
            return _envelope(False, data=base_status, error=str(exc), tool_name=tool, level="browser_state", idempotent=False)

    return {
        "agent_file_read": file_read,
        "agent_file_write": file_write,
        "agent_file_list": file_list,
        "agent_file_search": file_search,
        "agent_file_patch": file_patch,
        "agent_file_mutation_verify": file_mutation_verify,
        "agent_terminal": terminal,
        "agent_process": process,
        "agent_execute_python": execute_python,
        "agent_computer_use": computer_use,
        "agent_browser_navigate": browser_navigate,
        "agent_browser_snapshot": browser_snapshot,
        "agent_browser_click": browser_click,
        "agent_browser_type": browser_type,
        "agent_browser_extract": browser_extract,
        "agent_browser_scroll": browser_scroll,
        "agent_browser_back": browser_back,
        "agent_browser_press": browser_press,
        "agent_browser_get_images": browser_get_images,
        "agent_browser_vision": browser_vision,
        "agent_browser_console": browser_console,
        "agent_browser_cdp": browser_cdp,
    }
