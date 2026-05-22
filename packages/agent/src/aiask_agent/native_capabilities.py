from __future__ import annotations

import asyncio
import base64
import html
import ipaddress
import json
import mimetypes
import os
import re
import shutil
import socket
import sqlite3
import time
from contextlib import closing
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from . import homeassistant as ha_native
from .acp import ACPManager
from .approvals import ApprovalStore
from .gateway import DeliveryRouter, GatewayChannelDirectoryStore, GatewayConfigStore, GatewayMessageStore, GatewayRuntime
from .financial_skill_templates import FINANCIAL_SKILL_TEMPLATES
from .mcp_client import MCPAggregator, MCPOAuthRequired
from .memory_providers import MemoryProviderManager
from .model_providers import ModelProviderRegistry, ProviderUsageStore
from .paths import aiask_agent_home, default_state_db_path
from .platform_apis import DiscordServerClient, FeishuClient
from .plugin_runtime import NativePluginManager
from .rl_atropos import RLAtroposManager
from .security import SecurityScanner
from .session_store import AgentSessionStore, now_iso
from .skill_packs import SkillPackManager
from .terminal_backends import list_backends, sessions as terminal_backend_sessions
from .todo import FinancialTodoStore
from .tools.policy import ToolPolicy
from .tui import status as tui_status_payload
from .webhooks import WebhookStore


def _envelope(
    success: bool,
    *,
    data: Any = None,
    error: str | None = None,
    tool_name: str,
    level: str = "read_only",
    target: str | None = None,
    idempotent: bool = True,
) -> dict[str, Any]:
    return {
        "success": bool(success),
        "data": data,
        "error": error,
        "meta": {
            "trace_id": f"aiask-agent:{tool_name}:{int(time.time() * 1000)}:{uuid4().hex[:8]}",
            "source_chain": ["aiask_agent.native_capabilities"],
            "side_effect": {
                "level": level,
                "target": target or tool_name,
                "confirmation_required": False,
                "idempotent": idempotent,
            },
        },
    }


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip(".-")
    return slug[:120] or f"item-{uuid4().hex[:8]}"


def _limit(value: str, max_chars: int) -> tuple[str, bool]:
    limit = max(1, min(int(max_chars or 20000), 200000))
    return value[:limit], len(value) > limit


def _is_private_target(url: str) -> bool:
    host = urlparse(url).hostname
    if not host:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
            return True
    return False


def _validate_public_url(url: str) -> str:
    normalized = str(url or "").strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url must be an absolute http(s) URL")
    if os.getenv("AIASK_AGENT_ALLOW_PRIVATE_WEB", "").strip().lower() not in {"1", "true", "yes", "on"}:
        if _is_private_target(normalized):
            raise PermissionError("private, loopback, and link-local web targets are blocked")
    return normalized


def _fetch_url(url: str, *, max_bytes: int = 262144, timeout: float = 15.0) -> tuple[str, str, int | None]:
    normalized = _validate_public_url(url)
    request = Request(
        normalized,
        headers={
            "User-Agent": "AIASK-Agent/0.1 (+native-web-tool)",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
        },
    )
    with urlopen(request, timeout=max(1.0, min(float(timeout or 15), 60.0))) as response:
        raw = response.read(max(1, min(int(max_bytes or 262144), 1024 * 1024)))
        content_type = str(response.headers.get("Content-Type") or "")
        status = getattr(response, "status", None)
    return raw.decode("utf-8", errors="replace"), content_type, status


def _fetch_binary_url(url: str, *, max_bytes: int = 25 * 1024 * 1024, timeout: float = 60.0) -> tuple[bytes, str, int | None]:
    normalized = _validate_public_url(url)
    limit = max(1, min(int(max_bytes or 25 * 1024 * 1024), 100 * 1024 * 1024))
    request = Request(normalized, headers={"User-Agent": "AIASK-Agent/0.1 (+native-provider-tool)", "Accept": "*/*"})
    with urlopen(request, timeout=max(1.0, min(float(timeout or 60), 300.0))) as response:
        raw = response.read(limit + 1)
        content_type = str(response.headers.get("Content-Type") or "application/octet-stream").split(";", 1)[0].strip()
        status = getattr(response, "status", None)
    if len(raw) > limit:
        raise ValueError(f"remote file exceeds max_bytes={limit}")
    return raw, content_type, status


def _json_request(method: str, url: str, payload: dict[str, Any] | None = None, *, headers: dict[str, str] | None = None, timeout: float = 30.0) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, method=method, headers={"Content-Type": "application/json", **dict(headers or {})})
    try:
        with urlopen(request, timeout=max(1.0, min(float(timeout or 30), 300.0))) as response:
            raw = response.read(1024 * 1024)
            text = raw.decode("utf-8", errors="replace")
            parsed = json.loads(text) if text else {}
            return {"ok": 200 <= getattr(response, "status", 200) < 300, "status_code": getattr(response, "status", None), "body": parsed}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "error_type": type(exc).__name__}


def _response_text(response: Any) -> str:
    direct = getattr(response, "output_text", None)
    if direct:
        return str(direct)
    parts: list[str] = []
    for item in list(getattr(response, "output", []) or []):
        for content in list(getattr(item, "content", []) or []):
            text = getattr(content, "text", None)
            if text:
                parts.append(str(text))
    return "\n".join(parts).strip()


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag.lower() in {"p", "br", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag.lower() in {"p", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self.parts.append(data)

    def text(self) -> str:
        text = html.unescape(" ".join(self.parts))
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n\s+", "\n", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()


def _extract_text(content: str, content_type: str = "") -> str:
    if "html" not in content_type.lower() and "<html" not in content[:1000].lower():
        return content.strip()
    parser = _TextExtractor()
    parser.feed(content)
    return parser.text()


def _extract_links(content: str, base_url: str, limit: int = 10) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for href, label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', content, flags=re.I | re.S):
        clean_label = re.sub(r"<[^>]+>", " ", label)
        clean_label = re.sub(r"\s+", " ", html.unescape(clean_label)).strip()
        clean_href = html.unescape(href)
        if clean_href.startswith("//"):
            clean_href = f"{urlparse(base_url).scheme}:{clean_href}"
        elif clean_href.startswith("/"):
            parsed = urlparse(base_url)
            clean_href = f"{parsed.scheme}://{parsed.netloc}{clean_href}"
        if clean_href.startswith("http") and clean_label:
            links.append({"title": clean_label[:240], "url": clean_href})
        if len(links) >= limit:
            break
    return links


class SkillStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or aiask_agent_home() / "skills"
        self.archive_root = self.root / ".archive"
        self.backup_root = self.root / ".curator_backups"
        self.usage_path = self.root / ".usage.json"

    def _load_usage(self) -> dict[str, Any]:
        if not self.usage_path.exists():
            return {}
        try:
            loaded = json.loads(self.usage_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return dict(loaded) if isinstance(loaded, dict) else {}

    def _save_usage(self, usage: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.usage_path.write_text(json.dumps(usage, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def _metadata_for(self, name: str) -> dict[str, Any]:
        usage = self._load_usage()
        row = dict(usage.get(name) or {})
        row.setdefault("state", "active")
        row.setdefault("pinned", False)
        row.setdefault("view_count", 0)
        row.setdefault("use_count", 0)
        return row

    def _update_metadata(self, name: str, **updates: Any) -> dict[str, Any]:
        skill_name = _safe_slug(name)
        usage = self._load_usage()
        row = dict(usage.get(skill_name) or {})
        row.update(updates)
        row["updated_at"] = time.time()
        usage[skill_name] = row
        self._save_usage(usage)
        return row

    def _active_skill_path(self, name: str) -> Path:
        return self.root / _safe_slug(name) / "SKILL.md"

    def list(self) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*/SKILL.md")):
            if any(part.startswith(".") for part in path.relative_to(self.root).parts):
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
            first_line = next((line.strip("# ").strip() for line in content.splitlines() if line.strip()), path.parent.name)
            metadata = self._metadata_for(path.parent.name)
            items.append(
                {
                    "name": path.parent.name,
                    "title": first_line,
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "updated_at": path.stat().st_mtime,
                    "state": metadata.get("state") or "active",
                    "pinned": bool(metadata.get("pinned")),
                    "view_count": int(metadata.get("view_count") or 0),
                    "use_count": int(metadata.get("use_count") or 0),
                    "last_viewed_at": metadata.get("last_viewed_at"),
                    "last_used_at": metadata.get("last_used_at"),
                }
            )
        return items

    def view(self, name: str, *, max_chars: int = 50000) -> dict[str, Any]:
        skill_name = _safe_slug(name)
        path = self._active_skill_path(skill_name)
        if not path.exists():
            raise FileNotFoundError(f"skill not found: {skill_name}")
        content, truncated = _limit(path.read_text(encoding="utf-8", errors="replace"), max_chars)
        metadata = self._metadata_for(skill_name)
        self._update_metadata(
            skill_name,
            **{
                **metadata,
                "state": "active",
                "view_count": int(metadata.get("view_count") or 0) + 1,
                "last_viewed_at": time.time(),
            },
        )
        return {"name": skill_name, "path": str(path), "content": content, "truncated": truncated}

    def save(self, name: str, content: str, *, description: str | None = None) -> dict[str, Any]:
        skill_name = _safe_slug(name)
        if not str(content or "").strip():
            raise ValueError("skill content is required")
        path = self._active_skill_path(skill_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = str(content)
        if description and "description:" not in text[:500].lower():
            text = f"---\ndescription: {description}\n---\n\n{text}"
        path.write_text(text, encoding="utf-8")
        metadata = self._metadata_for(skill_name)
        self._update_metadata(
            skill_name,
            **{
                **metadata,
                "state": "active",
                "pinned": bool(metadata.get("pinned")),
                "patch_count": int(metadata.get("patch_count") or 0) + 1,
                "last_used_at": time.time(),
                "agent_created": True,
                "archived_at": None,
            },
        )
        return {"name": skill_name, "path": str(path), "bytes": len(text.encode("utf-8"))}

    def pin(self, name: str, pinned: bool = True) -> dict[str, Any]:
        skill_name = _safe_slug(name)
        if not self._active_skill_path(skill_name).exists():
            raise FileNotFoundError(f"skill not found: {skill_name}")
        metadata = self._metadata_for(skill_name)
        metadata["pinned"] = bool(pinned)
        metadata["state"] = "active"
        self._update_metadata(skill_name, **metadata)
        return {"name": skill_name, "pinned": bool(pinned)}

    def archive(self, name: str, *, reason: str | None = None) -> dict[str, Any]:
        skill_name = _safe_slug(name)
        metadata = self._metadata_for(skill_name)
        if metadata.get("pinned"):
            raise PermissionError(f"skill is pinned: {skill_name}")
        path = self.root / skill_name
        if not path.exists():
            raise FileNotFoundError(f"skill not found: {skill_name}")
        self.archive_root.mkdir(parents=True, exist_ok=True)
        dest = self.archive_root / f"{skill_name}-{int(time.time())}"
        shutil.move(str(path), str(dest))
        metadata.update({"state": "archived", "archived_at": time.time(), "archive_reason": reason or "archived"})
        self._update_metadata(skill_name, **metadata)
        return {"name": skill_name, "archived": True, "archive_path": str(dest), "reason": reason or "archived"}

    def restore(self, name: str) -> dict[str, Any]:
        skill_name = _safe_slug(name)
        if self._active_skill_path(skill_name).exists():
            return {"name": skill_name, "restored": False, "reason": "already_active"}
        matches = sorted(self.archive_root.glob(f"{skill_name}-*/SKILL.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not matches:
            raise FileNotFoundError(f"archived skill not found: {skill_name}")
        src_dir = matches[0].parent
        dest_dir = self.root / skill_name
        shutil.move(str(src_dir), str(dest_dir))
        metadata = self._metadata_for(skill_name)
        metadata.update({"state": "active", "archived_at": None})
        self._update_metadata(skill_name, **metadata)
        return {"name": skill_name, "restored": True, "path": str(dest_dir / "SKILL.md")}

    def backup(self, *, reason: str | None = None) -> dict[str, Any]:
        self.backup_root.mkdir(parents=True, exist_ok=True)
        backup_id = f"backup-{int(time.time())}-{uuid4().hex[:8]}"
        dest = self.backup_root / backup_id
        dest.mkdir(parents=True, exist_ok=False)
        for item in self.root.iterdir() if self.root.exists() else []:
            if item.name == ".curator_backups":
                continue
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        manifest = {"backup_id": backup_id, "reason": reason or "manual", "created_at": time.time()}
        (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return {"backup_id": backup_id, "path": str(dest), "reason": manifest["reason"]}

    def rollback(self, backup_id: str | None = None) -> dict[str, Any]:
        if not self.backup_root.exists():
            raise FileNotFoundError("no skill backups found")
        backups = sorted([p for p in self.backup_root.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
        if backup_id:
            backups = [p for p in backups if p.name == backup_id]
        if not backups:
            raise FileNotFoundError(f"skill backup not found: {backup_id or 'latest'}")
        selected = backups[0]
        self.backup(reason=f"pre-rollback:{selected.name}")
        self.root.mkdir(parents=True, exist_ok=True)
        for item in list(self.root.iterdir()):
            if item.name == ".curator_backups":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        for item in selected.iterdir():
            if item.name == "manifest.json":
                continue
            target = self.root / item.name
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        return {"rolled_back": True, "backup_id": selected.name, "root": str(self.root)}

    def audit(self, *, dry_run: bool = True) -> dict[str, Any]:
        skills = self.list()
        issues: list[dict[str, Any]] = []
        seen_titles: dict[str, str] = {}
        for item in skills:
            name = str(item.get("name") or "")
            path = Path(str(item.get("path") or ""))
            content = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
            if "description:" not in content[:800].lower():
                issues.append({"severity": "warning", "skill": name, "code": "missing_description", "message": "Skill lacks frontmatter description."})
            if len(content.strip()) < 80:
                issues.append({"severity": "warning", "skill": name, "code": "too_short", "message": "Skill content is too short to be operational."})
            title = str(item.get("title") or "").strip().lower()
            if title and title in seen_titles:
                issues.append({"severity": "info", "skill": name, "code": "duplicate_title", "message": f"Title duplicates {seen_titles[title]}."})
            elif title:
                seen_titles[title] = name
        if not skills:
            issues.append({"severity": "info", "code": "no_skills_installed", "message": "No AIASK native skills are installed in the active skill store."})
        return {
            "skills": skills,
            "issues": issues,
            "issue_count": len(issues),
            "dry_run": bool(dry_run),
            "archive_candidates": [
                item for item in skills
                if not item.get("pinned") and int(item.get("view_count") or 0) == 0 and int(item.get("use_count") or 0) == 0
            ],
        }

    def install_finance_templates(self, *, overwrite: bool = False) -> dict[str, Any]:
        installed: list[dict[str, Any]] = []
        skipped: list[str] = []
        for name, spec in FINANCIAL_SKILL_TEMPLATES.items():
            if self._active_skill_path(name).exists() and not overwrite:
                skipped.append(name)
                continue
            installed.append(self.save(name, spec["content"], description=spec.get("description")))
        return {"installed": installed, "skipped": skipped, "count": len(installed)}


class MessageOutbox:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_state_db_path()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS message_outbox (
                message_id TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                target TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        return conn

    def send(self, *, platform: str, target: str, message: str) -> dict[str, Any]:
        if not str(platform or "").strip():
            raise ValueError("platform is required")
        if not str(target or "").strip():
            raise ValueError("target is required")
        if not str(message or "").strip():
            raise ValueError("message is required")
        message_id = f"msg_{uuid4().hex}"
        result: dict[str, Any] = {"delivered": False, "transport": "outbox"}
        status = "queued"
        webhook = str(os.getenv("AIASK_AGENT_MESSAGE_WEBHOOK_URL", "")).strip()
        if webhook:
            payload = json.dumps({"platform": platform, "target": target, "message": message}).encode("utf-8")
            request = Request(webhook, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=15) as response:
                result = {"delivered": 200 <= int(response.status) < 300, "status": response.status, "transport": "webhook"}
                status = "sent" if result["delivered"] else "failed"
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO message_outbox
                    (message_id, platform, target, message, status, result_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (message_id, platform, target, message, status, json.dumps(result, ensure_ascii=False), now_iso()),
            )
            conn.commit()
        return {"message_id": message_id, "platform": platform, "target": target, "status": status, "result": result}


async def _generate_image(arguments: dict[str, Any]) -> dict[str, Any]:
    prompt = str(arguments.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    api_key = str(os.getenv("OPENAI_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for native image generation")
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    response = await client.images.generate(
        model=str(arguments.get("model") or os.getenv("AIASK_AGENT_IMAGE_MODEL", "gpt-image-1")),
        prompt=prompt,
        size=str(arguments.get("size") or "1024x1024"),
    )
    item = response.data[0]
    output_dir = aiask_agent_home() / "generated" / "images"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"image_{uuid4().hex}.png"
    b64 = getattr(item, "b64_json", None)
    if b64:
        path.write_bytes(base64.b64decode(b64))
        return {"path": str(path), "url": None, "model": response.model if hasattr(response, "model") else None}
    return {"path": None, "url": getattr(item, "url", None)}


async def _text_to_speech(arguments: dict[str, Any]) -> dict[str, Any]:
    text = str(arguments.get("text") or "").strip()
    if not text:
        raise ValueError("text is required")
    provider = str(arguments.get("provider") or os.getenv("AIASK_AGENT_TTS_PROVIDER", "openai")).strip().lower() or "openai"
    output_dir = aiask_agent_home() / "generated" / "audio"
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_format = str(arguments.get("format") or os.getenv("AIASK_AGENT_TTS_FORMAT", "mp3")).strip().lower() or "mp3"
    path = output_dir / f"speech_{uuid4().hex}.{audio_format}"
    if provider == "edge_tts":
        voice = str(arguments.get("voice") or os.getenv("AIASK_AGENT_TTS_VOICE", "en-US-AriaNeural"))
        try:
            import edge_tts
        except Exception:
            return {"configured": False, "provider": "edge_tts", "path": None, "error": "edge-tts is not installed"}
        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(path))
            return {"configured": True, "provider": "edge_tts", "path": str(path), "voice": voice, "bytes": path.stat().st_size}
        except Exception as exc:
            return {"configured": True, "provider": "edge_tts", "path": None, "error": str(exc)}
    api_key = str(os.getenv("OPENAI_API_KEY", "")).strip()
    if not api_key:
        return {"configured": False, "provider": "openai", "path": None, "error": "OPENAI_API_KEY is required"}
    from openai import AsyncOpenAI

    model = str(arguments.get("model") or os.getenv("AIASK_AGENT_TTS_MODEL", "gpt-4o-mini-tts"))
    voice = str(arguments.get("voice") or os.getenv("AIASK_AGENT_TTS_VOICE", "alloy"))
    kwargs: dict[str, Any] = {"model": model, "voice": voice, "input": text, "response_format": audio_format}
    if arguments.get("speed") is not None:
        kwargs["speed"] = float(arguments.get("speed") or 1.0)
    try:
        response = await AsyncOpenAI(api_key=api_key).audio.speech.create(**kwargs)
        if hasattr(response, "aread"):
            raw = await response.aread()
        elif hasattr(response, "read"):
            raw = response.read()
        else:
            raw = getattr(response, "content", b"")
        path.write_bytes(bytes(raw or b""))
        return {
            "configured": True,
            "provider": "openai",
            "model": model,
            "voice": voice,
            "format": audio_format,
            "path": str(path),
            "bytes": path.stat().st_size,
        }
    except Exception as exc:
        return {"configured": True, "provider": "openai", "model": model, "voice": voice, "path": None, "error": str(exc)}


async def _transcribe_audio(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = str(arguments.get("provider") or os.getenv("AIASK_AGENT_STT_PROVIDER", "openai")).strip().lower() or "openai"
    if provider != "openai":
        return {"configured": False, "provider": provider, "text": None, "error": f"unsupported STT provider: {provider}"}
    api_key = str(os.getenv("OPENAI_API_KEY", "")).strip()
    if not api_key:
        return {"configured": False, "provider": "openai", "text": None}
    audio = str(arguments.get("audio_path") or "").strip()
    audio_url = str(arguments.get("audio_url") or "").strip()
    if not audio and not audio_url:
        return {"configured": False, "provider": "openai", "text": None, "error": "audio_path or audio_url is required"}
    from openai import AsyncOpenAI

    downloaded: Path | None = None
    if audio_url:
        raw, content_type, _ = _fetch_binary_url(
            audio_url,
            max_bytes=int(arguments.get("max_bytes") or 25 * 1024 * 1024),
            timeout=float(arguments.get("timeout_seconds") or 60),
        )
        suffix = mimetypes.guess_extension(content_type) or ".audio"
        input_dir = aiask_agent_home() / "generated" / "audio-input"
        input_dir.mkdir(parents=True, exist_ok=True)
        downloaded = input_dir / f"audio_{uuid4().hex}{suffix}"
        downloaded.write_bytes(raw)
        path = downloaded
    else:
        path = Path(audio).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(str(path))
    client = AsyncOpenAI(api_key=api_key)
    kwargs: dict[str, Any] = {
        "model": str(arguments.get("model") or os.getenv("AIASK_AGENT_STT_MODEL", "gpt-4o-mini-transcribe")),
    }
    for key in ("language", "prompt", "response_format"):
        if arguments.get(key):
            kwargs[key] = arguments[key]
    try:
        with path.open("rb") as fh:
            result = await client.audio.transcriptions.create(file=fh, **kwargs)
        return {
            "configured": True,
            "provider": "openai",
            "model": kwargs["model"],
            "text": getattr(result, "text", "") if not isinstance(result, str) else result,
            "audio_path": str(path),
            "downloaded": bool(downloaded),
        }
    except Exception as exc:
        return {"configured": True, "provider": "openai", "model": kwargs["model"], "text": None, "audio_path": str(path), "error": str(exc)}


def build_native_capability_handlers(
    *,
    policy: ToolPolicy,
    session_store: AgentSessionStore,
    todo_store: FinancialTodoStore | None = None,
    skill_store: SkillStore | None = None,
    plugin_store: NativePluginManager | None = None,
    outbox: MessageOutbox | None = None,
) -> dict[str, Any]:
    todos = todo_store or FinancialTodoStore(session_store.path)
    skills = skill_store or SkillStore()
    plugins = plugin_store or NativePluginManager()
    messages = outbox or MessageOutbox(session_store.path)
    mcp = MCPAggregator()
    model_registry = ModelProviderRegistry(usage_store=ProviderUsageStore(session_store.path))
    memory_providers = MemoryProviderManager(path=session_store.path)
    acp = ACPManager(mcp=mcp)
    security_scanner = SecurityScanner(policy=policy)
    skill_packs = SkillPackManager(skill_store=skills)
    webhooks = WebhookStore(session_store.path)
    directory = GatewayChannelDirectoryStore(session_store.path)
    gateway = GatewayRuntime(
        config=GatewayConfigStore(),
        messages=GatewayMessageStore(session_store.path),
        directory=directory,
    )
    delivery = DeliveryRouter(config=gateway.config, messages=gateway.messages, directory=directory)
    rl = RLAtroposManager(session_store.path)
    from .learning_loop import LearningLoop

    learning = LearningLoop(session_store=session_store, state_path=session_store.path)

    async def web_extract(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_web_extract"
        try:
            content, content_type, status = _fetch_url(
                str(arguments.get("url") or ""),
                max_bytes=int(arguments.get("max_bytes") or 262144),
                timeout=float(arguments.get("timeout_seconds") or 15),
            )
            text = _extract_text(content, content_type)
            limited, truncated = _limit(text, int(arguments.get("max_chars") or 20000))
            return _envelope(
                True,
                data={
                    "url": str(arguments.get("url") or ""),
                    "status": status,
                    "content_type": content_type,
                    "text": limited,
                    "truncated": truncated,
                    "links": _extract_links(content, str(arguments.get("url") or ""), limit=20),
                },
                tool_name=tool,
                level="read_only",
                target=str(arguments.get("url") or ""),
            )
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="read_only")

    async def web_search(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_web_search"
        query = str(arguments.get("query") or "").strip()
        try:
            if not query:
                raise ValueError("query is required")
            limit = max(1, min(int(arguments.get("limit") or 5), 20))
            url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
            content, content_type, status = _fetch_url(url, max_bytes=524288, timeout=20)
            links = _extract_links(content, url, limit=limit * 3)
            results: list[dict[str, str]] = []
            seen: set[str] = set()
            for item in links:
                href = item["url"]
                if "duckduckgo.com" in urlparse(href).netloc and "uddg=" in href:
                    match = re.search(r"uddg=([^&]+)", href)
                    if match:
                        from urllib.parse import unquote

                        href = unquote(match.group(1))
                if href in seen or not href.startswith("http"):
                    continue
                seen.add(href)
                results.append({"title": item["title"], "url": href})
                if len(results) >= limit:
                    break
            return _envelope(
                True,
                data={"query": query, "results": results, "status": status, "provider": "duckduckgo_html"},
                tool_name=tool,
                level="read_only",
                target=query,
            )
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="read_only")

    async def x_search(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_x_search"
        query = str(arguments.get("query") or "").strip()
        token = str(os.getenv("X_BEARER_TOKEN") or os.getenv("X_API_KEY") or "").strip()
        base_url = str(os.getenv("AIASK_X_API_BASE") or "https://api.twitter.com/2").rstrip("/")
        if not query:
            return _envelope(False, error="query is required", tool_name=tool, level="read_only")
        if not token:
            return _envelope(
                False,
                data={
                    "configured": False,
                    "provider": "x_api_v2",
                    "required_env": ["X_BEARER_TOKEN", "X_API_KEY"],
                    "query": query,
                    "results": [],
                    "secrets_redacted": True,
                },
                error="X search credentials are not configured",
                tool_name=tool,
                level="read_only",
                target=query,
            )
        try:
            max_results = max(10, min(int(arguments.get("max_results") or arguments.get("limit") or 10), 100))
            params = {"query": query, "max_results": str(max_results), "tweet.fields": "created_at,author_id,public_metrics"}
            if arguments.get("since_id"):
                params["since_id"] = str(arguments.get("since_id"))
            if arguments.get("next_token"):
                params["next_token"] = str(arguments.get("next_token"))
            query_string = "&".join(f"{quote_plus(key)}={quote_plus(value)}" for key, value in params.items())
            result = await asyncio.to_thread(
                _json_request,
                "GET",
                f"{base_url}/tweets/search/recent?{query_string}",
                None,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            body = result.get("body") if isinstance(result.get("body"), dict) else {}
            tweets = list(dict(body).get("data") or []) if isinstance(body, dict) else []
            meta = dict(dict(body).get("meta") or {}) if isinstance(body, dict) else {}
            data = {
                "configured": True,
                "provider": "x_api_v2",
                "query": query,
                "results": tweets[: max(1, min(int(arguments.get("limit") or len(tweets) or 10), 100))],
                "next_token": meta.get("next_token"),
                "result_count": meta.get("result_count", len(tweets)),
                "response": {key: value for key, value in result.items() if key != "body"},
                "secrets_redacted": True,
            }
            return _envelope(bool(result.get("ok")), data=data, error=None if result.get("ok") else str(result.get("error") or "X API request failed"), tool_name=tool, level="read_only", target=query)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="read_only", target=query)

    async def clarify(arguments: dict[str, Any]) -> dict[str, Any]:
        question = str(arguments.get("question") or "").strip()
        if not question:
            return _envelope(False, error="question is required", tool_name="agent_clarify", level="read_only")
        options = [str(item) for item in list(arguments.get("options") or []) if str(item).strip()]
        return _envelope(
            True,
            data={"question": question, "options": options, "requires_user_input": True},
            tool_name="agent_clarify",
            level="read_only",
            target="user",
        )

    async def todo_set(arguments: dict[str, Any]) -> dict[str, Any]:
        session_id = str(arguments.get("session_id") or "default").strip() or "default"
        items = list(arguments.get("items") or [])
        result = todos.set_items(
            session_id=session_id,
            user_id=arguments.get("user_id"),
            items=[dict(item) for item in items if isinstance(item, dict)],
            merge=bool(arguments.get("merge", False)),
        )
        return _envelope(
            True,
            data={"session_id": session_id, "items": result},
            tool_name="agent_todo_set",
            level="stateful",
            target=session_id,
            idempotent=False,
        )

    async def todo_list(arguments: dict[str, Any]) -> dict[str, Any]:
        session_id = str(arguments.get("session_id") or "default").strip() or "default"
        return _envelope(
            True,
            data={"session_id": session_id, "items": todos.list_items(session_id=session_id)},
            tool_name="agent_todo_list",
            level="read_only",
            target=session_id,
        )

    async def todo(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_todo"
        action = str(arguments.get("action") or "list").strip().lower()
        session_id = str(arguments.get("session_id") or "default").strip() or "default"
        try:
            if action == "list":
                data = {"session_id": session_id, "items": todos.list_items(session_id=session_id)}
            elif action == "clear":
                data = {"session_id": session_id, "items": todos.set_items(session_id=session_id, user_id=arguments.get("user_id"), items=[])}
            elif action in {"add", "update"}:
                item_id = str(arguments.get("item_id") or uuid4().hex[:8])
                existing = todos.list_items(session_id=session_id)
                if action == "update":
                    existing = [item for item in existing if item.get("item_id") != item_id]
                existing.append(
                    {
                        "id": item_id,
                        "content": str(arguments.get("content") or "").strip() or "(no description)",
                        "status": str(arguments.get("status") or "pending"),
                    }
                )
                data = {"session_id": session_id, "items": todos.set_items(session_id=session_id, user_id=arguments.get("user_id"), items=existing)}
            elif action == "status":
                items = todos.list_items(session_id=session_id)
                counts: dict[str, int] = {}
                for item in items:
                    counts[str(item.get("status") or "pending")] = counts.get(str(item.get("status") or "pending"), 0) + 1
                data = {"session_id": session_id, "count": len(items), "by_status": counts}
            else:
                raise ValueError(f"unsupported todo action: {action}")
            return _envelope(True, data=data, tool_name=tool, level="stateful", target=session_id, idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="stateful", idempotent=False)

    async def subgoal(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_subgoal"
        action = str(arguments.get("action") or "list").strip().lower()
        session_id = str(arguments.get("session_id") or "default").strip() or "default"
        try:
            if action == "list":
                data = {"session_id": session_id, "subgoals": session_store.list_subgoals(session_id=session_id)}
                level = "read_only"
            elif action == "status":
                items = session_store.list_subgoals(session_id=session_id)
                counts: dict[str, int] = {}
                for item in items:
                    counts[str(item.get("status") or "pending")] = counts.get(str(item.get("status") or "pending"), 0) + 1
                data = {"session_id": session_id, "count": len(items), "by_status": counts, "subgoals": items}
                level = "read_only"
            elif action == "clear":
                data = {"session_id": session_id, "subgoals": session_store.clear_subgoals(session_id=session_id)}
                level = "stateful"
            elif action in {"add", "update"}:
                title = str(arguments.get("title") or "").strip()
                if not title and action == "update" and arguments.get("subgoal_id"):
                    current = session_store.get_subgoal(str(arguments.get("subgoal_id") or ""))
                    title = str((current or {}).get("title") or "")
                item = session_store.upsert_subgoal(
                    session_id=session_id,
                    subgoal_id=arguments.get("subgoal_id") if action == "update" else arguments.get("subgoal_id"),
                    user_id=arguments.get("user_id"),
                    title=title,
                    criteria=[str(item) for item in list(arguments.get("criteria") or [])],
                    status=str(arguments.get("status") or "pending"),
                )
                data = {"session_id": session_id, "subgoal": item, "subgoals": session_store.list_subgoals(session_id=session_id)}
                level = "stateful"
            else:
                raise ValueError(f"unsupported subgoal action: {action}")
            return _envelope(True, data=data, tool_name=tool, level=level, target=session_id, idempotent=level == "read_only")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="stateful", idempotent=False)

    async def skill_list(_: dict[str, Any]) -> dict[str, Any]:
        return _envelope(True, data={"skills": skills.list()}, tool_name="agent_skill_list")

    async def skill_view(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return _envelope(
                True,
                data={"skill": skills.view(str(arguments.get("name") or ""), max_chars=int(arguments.get("max_chars") or 50000))},
                tool_name="agent_skill_view",
                level="read_only",
                target=str(arguments.get("name") or ""),
            )
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name="agent_skill_view", level="read_only")

    async def skill_save(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            item = skills.save(
                str(arguments.get("name") or ""),
                str(arguments.get("content") or ""),
                description=arguments.get("description"),
            )
            return _envelope(
                True,
                data={"skill": item},
                tool_name="agent_skill_save",
                level="filesystem_write",
                target=item["path"],
                idempotent=False,
            )
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name="agent_skill_save", level="filesystem_write", idempotent=False)

    async def skill_manage(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_skill_manage"
        action = str(arguments.get("action") or "search").strip().lower()
        try:
            if action == "search":
                query = str(arguments.get("query") or "").lower()
                data = {"skills": [item for item in skills.list() if not query or query in json.dumps(item, ensure_ascii=False).lower()]}
                level = "read_only"
            elif action in {"install", "update"}:
                item = skills.save(
                    str(arguments.get("name") or ""),
                    str(arguments.get("content") or ""),
                    description=arguments.get("description"),
                )
                data = {"skill": item}
                level = "filesystem_write"
            elif action == "uninstall":
                name = _safe_slug(str(arguments.get("name") or ""))
                path = skills.root / name
                archived = skills.archive(name, reason="uninstall") if path.exists() else None
                data = {"name": name, "deleted": bool(path.exists() or archived), "archived": archived}
                level = "filesystem_write"
            elif action == "audit":
                data = skills.audit(dry_run=bool(arguments.get("dry_run", True)))
                level = "read_only"
            elif action == "snapshot":
                data = {"skills": skills.list(), "root": str(skills.root)}
                if bool(arguments.get("create_backup")):
                    data["backup"] = skills.backup(reason=str(arguments.get("reason") or "snapshot"))
                level = "read_only"
            elif action == "pin":
                data = {"skill": skills.pin(str(arguments.get("name") or ""), True)}
                level = "stateful"
            elif action == "unpin":
                data = {"skill": skills.pin(str(arguments.get("name") or ""), False)}
                level = "stateful"
            elif action == "archive":
                data = {"skill": skills.archive(str(arguments.get("name") or ""), reason=arguments.get("reason"))}
                level = "filesystem_write"
            elif action == "restore":
                data = {"skill": skills.restore(str(arguments.get("name") or ""))}
                level = "filesystem_write"
            elif action == "rollback":
                data = {"rollback": skills.rollback(str(arguments.get("backup_id") or "").strip() or None)}
                level = "filesystem_write"
            elif action == "install_finance_templates":
                data = skills.install_finance_templates(overwrite=bool(arguments.get("overwrite")))
                level = "filesystem_write"
            else:
                raise ValueError(f"unsupported skill action: {action}")
            return _envelope(True, data=data, tool_name=tool, level=level, target=str(arguments.get("name") or "skills"), idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="filesystem_write", idempotent=False)

    async def plugin_list(_: dict[str, Any]) -> dict[str, Any]:
        return _envelope(True, data={"plugins": plugins.list()}, tool_name="agent_plugin_list")

    async def plugin_set_enabled(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            item = plugins.set_enabled(
                str(arguments.get("name") or ""),
                bool(arguments.get("enabled", True)),
                description=arguments.get("description"),
            )
            return _envelope(
                True,
                data={"plugin": item},
                tool_name="agent_plugin_set_enabled",
                level="stateful",
                target=item["name"],
                idempotent=False,
            )
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name="agent_plugin_set_enabled", level="stateful", idempotent=False)

    async def plugin_manage(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_plugin_manage"
        action = str(arguments.get("action") or "list").strip().lower()
        try:
            if action == "list":
                data = {"plugins": plugins.list()}
                level = "read_only"
            elif action == "inspect":
                data = {"plugin": plugins.get(str(arguments.get("name") or ""))}
                level = "read_only"
            elif action in {"enable", "disable"}:
                data = {"plugin": plugins.set_enabled(str(arguments.get("name") or ""), action == "enable", description=arguments.get("description"))}
                level = "stateful"
            elif action == "upsert":
                data = {"plugin": plugins.update(str(arguments.get("name") or ""), manifest=dict(arguments.get("manifest") or {}))}
                level = "stateful"
            else:
                raise ValueError(f"unsupported plugin action: {action}")
            return _envelope(True, data=data, tool_name=tool, level=level, target=str(arguments.get("name") or "plugins"), idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="stateful", idempotent=False)

    async def mcp_manage(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_mcp_manage"
        action = str(arguments.get("action") or "servers").strip().lower()
        try:
            if action == "servers":
                data = {"servers": mcp.servers_summary(include_all=True)}
            elif action == "tools":
                data = {"tools": mcp.tools_summary(include_all=True)}
            elif action in {"resources", "prompts"}:
                summary = mcp.resources_summary(include_all=True) if action == "resources" else mcp.prompts_summary(include_all=True)
                data = {action: summary, "enabled": bool(summary)}
            elif action == "oauth_status":
                data = {"servers": mcp.oauth_status(include_all=True)}
            elif action == "discover":
                data = await mcp.discover(str(arguments.get("server") or ""))
            elif action == "resource_read":
                data = await mcp.read_resource(str(arguments.get("server") or ""), str(arguments.get("uri") or ""))
            elif action == "prompt_get":
                data = await mcp.get_prompt(
                    str(arguments.get("server") or ""),
                    str(arguments.get("prompt") or arguments.get("name") or ""),
                    dict(arguments.get("arguments") or {}),
                )
            elif action == "oauth_start":
                data = mcp.oauth_start(
                    str(arguments.get("server") or ""),
                    redirect_uri=arguments.get("redirect_uri"),
                    scope=arguments.get("scope"),
                )
            elif action == "oauth_callback":
                data = mcp.oauth_callback(str(arguments.get("server") or ""), dict(arguments.get("token") or arguments))
            elif action == "test":
                server_name = str(arguments.get("server") or "")
                data = {"server": server_name, "configured": any(item.get("name") == server_name for item in mcp.servers_summary(include_all=True))}
            else:
                raise ValueError(f"unsupported mcp action: {action}")
            return _envelope(True, data=data, tool_name=tool, level="read_only")
        except MCPOAuthRequired as exc:
            return _envelope(False, data=exc.payload, error="MCP OAuth authorization is required", tool_name=tool, level="stateful")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="stateful", idempotent=False)

    async def model_manage(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_model_manage"
        action = str(arguments.get("action") or "status").strip().lower()
        try:
            if action == "status":
                data = model_registry.status()
                level = "read_only"
            elif action == "providers":
                usage = model_registry.usage_store.summary()
                data = {"providers": [item.public(usage) for item in model_registry.providers()]}
                level = "read_only"
            elif action == "credential_pool":
                data = model_registry.credential_pool_status(arguments.get("provider"))
                level = "read_only"
            elif action == "select":
                provider = str(arguments.get("provider") or model_registry.active_provider_name())
                selected = model_registry.select_credential(provider)
                data = {"provider": provider, "credential": selected.public() if selected else None, "selected": bool(selected)}
                level = "read_only"
            elif action == "record_attempt":
                data = model_registry.record_attempt(
                    provider=str(arguments.get("provider") or model_registry.active_provider_name()),
                    credential_id=str(arguments.get("credential_id") or ""),
                    success=bool(arguments.get("success")),
                    error=arguments.get("error"),
                )
                level = "stateful"
            elif action == "classify_error":
                data = {"error_class": model_registry.classify_error(arguments.get("error"))}
                level = "read_only"
            else:
                raise ValueError(f"unsupported model action: {action}")
            return _envelope(True, data=data, tool_name=tool, level=level, target=action, idempotent=level == "read_only")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="stateful", idempotent=False)

    async def memory_manage(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_memory_manage"
        action = str(arguments.get("action") or "status").strip().lower()
        try:
            if action == "status":
                data = memory_providers.status()
                level = "read_only"
            elif action == "save":
                data = {"memory": memory_providers.save(arguments)}
                level = "stateful"
            elif action == "search":
                data = {"memories": memory_providers.search(arguments)}
                level = "read_only"
            elif action == "audit":
                data = memory_providers.audit()
                level = "read_only"
            else:
                raise ValueError(f"unsupported memory action: {action}")
            return _envelope(True, data=data, tool_name=tool, level=level, target=action, idempotent=level == "read_only")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="stateful", idempotent=False)

    async def acp_manage(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_acp_manage"
        action = str(arguments.get("action") or "status").strip().lower()
        try:
            if action == "status":
                data = acp.status()
                level = "read_only"
            elif action == "readiness":
                data = acp.readiness()
                level = "read_only"
            elif action == "register_mcp_server":
                data = acp.register_server(arguments)
                level = "stateful"
            elif action == "remove_mcp_server":
                data = acp.remove_server(str(arguments.get("name") or ""))
                level = "stateful"
            else:
                raise ValueError(f"unsupported ACP action: {action}")
            return _envelope(True, data=data, tool_name=tool, level=level, target=str(arguments.get("name") or action), idempotent=level == "read_only")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="stateful", idempotent=False)

    async def security_scan(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_security_scan"
        try:
            return _envelope(
                True,
                data=security_scanner.scan(arguments),
                tool_name=tool,
                level="read_only",
                target=str(arguments.get("path") or arguments.get("url") or "inline"),
            )
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="read_only")

    async def skill_pack_manage(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_skill_pack_manage"
        action = str(arguments.get("action") or "list").strip().lower()
        try:
            if action == "list":
                data = {"packs": skill_packs.list()}
                level = "read_only"
            elif action == "status":
                data = skill_packs.status()
                level = "read_only"
            elif action == "install":
                pack = str(arguments.get("pack") or arguments.get("name") or "")
                data = skill_packs.install(pack, overwrite=bool(arguments.get("overwrite")))
                level = "filesystem_write"
            elif action == "audit":
                data = skill_packs.audit()
                level = "read_only"
            else:
                raise ValueError(f"unsupported skill pack action: {action}")
            return _envelope(True, data=data, tool_name=tool, level=level, target=str(arguments.get("pack") or action), idempotent=level == "read_only")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="filesystem_write", idempotent=False)

    async def vision_analyze(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_vision_analyze"
        image = str(arguments.get("image_path") or arguments.get("image_url") or "").strip()
        if not image:
            return _envelope(False, error="image_path or image_url is required", tool_name=tool)
        try:
            provider = str(arguments.get("provider") or os.getenv("AIASK_AGENT_VISION_PROVIDER", "openai")).strip().lower() or "openai"
            data: dict[str, Any] = {"image": image, "prompt": arguments.get("prompt"), "provider": provider}
            if image.startswith("http"):
                _validate_public_url(image)
                data["source"] = "url"
                image_url = image
            else:
                path = Path(image).expanduser().resolve()
                if not path.exists() or not path.is_file():
                    raise FileNotFoundError(str(path))
                data.update({"source": "file", "path": str(path), "bytes": path.stat().st_size})
                mime = mimetypes.guess_type(str(path))[0] or "image/png"
                image_url = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
                try:
                    from PIL import Image

                    with Image.open(path) as img:
                        data.update({"width": img.width, "height": img.height, "format": img.format})
                except Exception:
                    data["metadata_only"] = True
            if provider != "openai":
                data["configured"] = False
                return _envelope(False, data=data, error=f"unsupported vision provider: {provider}", tool_name=tool, level="read_only", target=image)
            model = str(arguments.get("model") or os.getenv("AIASK_AGENT_VISION_MODEL", "")).strip()
            if not os.getenv("OPENAI_API_KEY") or not model:
                data["configured"] = False
                return _envelope(False, data=data, error="vision provider is not configured", tool_name=tool, level="read_only", target=image)
            from openai import AsyncOpenAI

            data["configured"] = True
            data["model"] = model
            prompt = str(arguments.get("prompt") or "Analyze the image and describe the visible evidence relevant to the user's task.").strip()
            try:
                response = await AsyncOpenAI(api_key=str(os.getenv("OPENAI_API_KEY"))).responses.create(
                    model=model,
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": prompt},
                                {"type": "input_image", "image_url": image_url},
                            ],
                        }
                    ],
                )
                data["analysis"] = _response_text(response)
                return _envelope(True, data=data, tool_name=tool, level="read_only", target=image)
            except Exception as exc:
                data["error"] = str(exc)
                return _envelope(False, data=data, error=str(exc), tool_name=tool, level="read_only", target=image)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="read_only")

    async def image_generate(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_image_generate"
        try:
            data = await _generate_image(arguments)
            return _envelope(True, data=data, tool_name=tool, level="external_generation", target=data.get("path"), idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="external_generation", idempotent=False)

    async def video_generate(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_video_generate"
        action = str(arguments.get("action") or "status").strip().lower()
        provider = str(arguments.get("provider") or os.getenv("AIASK_VIDEO_PROVIDER") or "openai_compatible").strip()
        endpoint = str(os.getenv("AIASK_VIDEO_API_URL") or os.getenv("AIASK_VIDEO_BASE_URL") or "").strip()
        api_key = str(os.getenv("AIASK_VIDEO_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
        configured = bool(endpoint and api_key)
        base = {
            "configured": configured,
            "provider": provider,
            "required_env": ["AIASK_VIDEO_API_URL", "AIASK_VIDEO_API_KEY"],
            "secrets_redacted": True,
            "actions": ["status", "create", "status_check"],
        }
        if action == "status":
            return _envelope(True, data=base, tool_name=tool, level="read_only")
        if not configured:
            return _envelope(
                False,
                data=base,
                error="video generation provider is not configured",
                tool_name=tool,
                level="external_generation",
                idempotent=False,
            )
        try:
            if action == "create":
                prompt = str(arguments.get("prompt") or "").strip()
                if not prompt:
                    raise ValueError("prompt is required")
                payload = {
                    "prompt": prompt,
                    "model": arguments.get("model") or os.getenv("AIASK_VIDEO_MODEL") or "video",
                    "size": arguments.get("size") or os.getenv("AIASK_VIDEO_SIZE") or "1280x720",
                    "duration_seconds": int(arguments.get("duration_seconds") or os.getenv("AIASK_VIDEO_DURATION_SECONDS") or 5),
                    "metadata": dict(arguments.get("metadata") or {}),
                }
                result = await asyncio.to_thread(
                    _json_request,
                    "POST",
                    endpoint.rstrip("/") + "/videos",
                    payload,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=60,
                )
                body = result.get("body") if isinstance(result.get("body"), dict) else {}
                data = {**base, "job": body, "response": {key: value for key, value in result.items() if key != "body"}}
                return _envelope(bool(result.get("ok")), data=data, error=None if result.get("ok") else str(result.get("error") or "video generation request failed"), tool_name=tool, level="external_generation", target=str(body.get("id") or ""), idempotent=False)
            if action == "status_check":
                job_id = str(arguments.get("job_id") or "").strip()
                if not job_id:
                    raise ValueError("job_id is required")
                result = await asyncio.to_thread(
                    _json_request,
                    "GET",
                    endpoint.rstrip("/") + f"/videos/{quote_plus(job_id)}",
                    None,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=30,
                )
                data = {**base, "job_id": job_id, "job": result.get("body"), "response": {key: value for key, value in result.items() if key != "body"}}
                return _envelope(bool(result.get("ok")), data=data, error=None if result.get("ok") else str(result.get("error") or "video status request failed"), tool_name=tool, level="read_only", target=job_id)
            raise ValueError(f"unsupported video_generate action: {action}")
        except Exception as exc:
            return _envelope(False, data=base, error=str(exc), tool_name=tool, level="external_generation", idempotent=False)

    async def text_to_speech(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_text_to_speech"
        try:
            data = await _text_to_speech(arguments)
            success = bool(data.get("configured")) and not data.get("error")
            return _envelope(
                success,
                data=data,
                error=None if success else str(data.get("error") or "text-to-speech provider is not configured"),
                tool_name=tool,
                level="external_generation",
                target=data.get("path"),
                idempotent=False,
            )
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="external_generation", idempotent=False)

    async def transcribe_audio(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_transcribe_audio"
        try:
            data = await _transcribe_audio(arguments)
            success = bool(data.get("configured")) and not data.get("error")
            return _envelope(
                success,
                data=data,
                error=None if success else str(data.get("error") or "speech-to-text provider is not configured"),
                tool_name=tool,
                level="external_generation",
                target=arguments.get("audio_path") or arguments.get("audio_url"),
                idempotent=False,
            )
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="external_generation", idempotent=False)

    async def terminal_backends(arguments: dict[str, Any]) -> dict[str, Any]:
        action = str(arguments.get("action") or "list").strip().lower()
        try:
            if action == "sessions":
                data = {"sessions": terminal_backend_sessions(state_path=session_store.path, limit=int(arguments.get("limit") or 200))}
            elif action == "list":
                data = {"backends": list_backends()}
            else:
                raise ValueError(f"unsupported terminal backend action: {action}")
            return _envelope(True, data=data, tool_name="agent_terminal_backends", level="read_only")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name="agent_terminal_backends", level="read_only")

    async def tui_status(_: dict[str, Any]) -> dict[str, Any]:
        return _envelope(True, data=tui_status_payload(), tool_name="agent_tui_status", level="read_only")

    async def gateway_status(_: dict[str, Any]) -> dict[str, Any]:
        return _envelope(True, data=gateway.status(), tool_name="agent_gateway_status", level="read_only")

    async def gateway_platforms(arguments: dict[str, Any]) -> dict[str, Any]:
        platform = str(arguments.get("platform") or "").strip()
        data = {"platforms": [gateway.config.platform_status(platform).to_dict()] if platform else gateway.list_platforms()}
        return _envelope(True, data=data, tool_name="agent_gateway_platforms", level="read_only")

    async def gateway_send_message(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_gateway_send_message"
        try:
            action = str(arguments.get("action") or "send").strip().lower()
            if action == "list":
                return _envelope(True, data={"platforms": gateway.list_platforms()}, tool_name=tool, level="read_only")
            if action != "send":
                raise ValueError(f"unsupported gateway message action: {action}")
            data = await delivery.send(
                platform=str(arguments.get("platform") or "local"),
                target=str(arguments.get("target") or ""),
                message=str(arguments.get("message") or ""),
                thread_id=arguments.get("thread_id"),
                session_id=arguments.get("session_id"),
                user_id=arguments.get("user_id"),
                media_paths=[str(item) for item in list(arguments.get("media_paths") or [])],
            )
            success = bool(dict(data.get("adapter") or {}).get("ok"))
            return _envelope(success, data=data, error=None if success else dict(data.get("adapter") or {}).get("status"), tool_name=tool, level="external_message", target=str(arguments.get("target") or ""), idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="external_message", idempotent=False)

    async def gateway_history(arguments: dict[str, Any]) -> dict[str, Any]:
        return _envelope(
            True,
            data={"messages": gateway.messages.list(platform=arguments.get("platform"), limit=int(arguments.get("limit") or 100))},
            tool_name="agent_gateway_history",
            level="read_only",
        )

    async def gateway_pairing(arguments: dict[str, Any]) -> dict[str, Any]:
        action = str(arguments.get("action") or "status").strip().lower()
        payload = {
            "action": action,
            "platform": arguments.get("platform"),
            "user_id": arguments.get("user_id"),
            "session_id": arguments.get("session_id"),
            "configured": True,
        }
        return _envelope(True, data=payload, tool_name="agent_gateway_pairing", level="stateful" if action == "create" else "read_only", idempotent=False)

    async def gateway_directory(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_gateway_directory"
        action = str(arguments.get("action") or "list").strip().lower()
        try:
            if action == "list":
                data = {
                    "items": directory.list(
                        platform=arguments.get("platform"),
                        kind=arguments.get("kind"),
                        limit=int(arguments.get("limit") or 200),
                    )
                }
                level = "read_only"
            elif action == "resolve":
                data = {
                    "item": directory.resolve(
                        platform=arguments.get("platform"),
                        name=str(arguments.get("name") or arguments.get("target") or ""),
                        kind=arguments.get("kind"),
                    )
                }
                level = "read_only"
            elif action == "refresh":
                data = directory.refresh(config=gateway.config)
                level = "stateful"
            elif action == "upsert":
                data = {
                    "item": directory.upsert(
                        platform=str(arguments.get("platform") or "local"),
                        name=str(arguments.get("name") or ""),
                        target=str(arguments.get("target") or ""),
                        kind=str(arguments.get("kind") or "channel"),
                        thread_id=arguments.get("thread_id"),
                        metadata=dict(arguments.get("metadata") or {}),
                    )
                }
                level = "stateful"
            else:
                raise ValueError(f"unsupported gateway directory action: {action}")
            return _envelope(True, data=data, tool_name=tool, level=level, idempotent=level == "read_only")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="stateful", idempotent=False)

    async def gateway_direct_deliver(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_gateway_direct_deliver"
        try:
            data = await delivery.send(
                platform=str(arguments.get("platform") or "local"),
                target=str(arguments.get("target") or ""),
                message=str(arguments.get("message") or ""),
                thread_id=arguments.get("thread_id"),
                session_id=arguments.get("session_id"),
                user_id=arguments.get("user_id"),
                media_paths=[str(item) for item in list(arguments.get("media_paths") or [])],
            )
            data["deliver_mode"] = "direct_platform"
            success = bool(dict(data.get("adapter") or {}).get("ok"))
            return _envelope(success, data=data, error=None if success else dict(data.get("adapter") or {}).get("status"), tool_name=tool, level="external_message", target=str(arguments.get("target") or ""), idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="external_message", idempotent=False)

    async def session_handoff(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_session_handoff"
        action = str(arguments.get("action") or "status").strip().lower()
        try:
            if action == "request":
                item = session_store.request_handoff(
                    session_id=str(arguments.get("session_id") or "default").strip() or "default",
                    user_id=arguments.get("user_id"),
                    target=arguments.get("target"),
                    reason=arguments.get("reason"),
                    summary=arguments.get("summary"),
                    metadata=dict(arguments.get("metadata") or {}),
                )
                data = {"handoff": item}
                level = "stateful"
            elif action == "status":
                handoff_id = str(arguments.get("handoff_id") or "").strip()
                if handoff_id:
                    data = {"handoff": session_store.get_handoff(handoff_id)}
                else:
                    items = session_store.list_handoffs(session_id=arguments.get("session_id"), limit=int(arguments.get("limit") or 20))
                    data = {"handoffs": items, "latest": items[0] if items else None}
                level = "read_only"
            elif action == "list":
                data = {"handoffs": session_store.list_handoffs(session_id=arguments.get("session_id"), limit=int(arguments.get("limit") or 100))}
                level = "read_only"
            elif action in {"complete", "fail"}:
                status = "completed" if action == "complete" else "failed"
                data = {
                    "handoff": session_store.update_handoff(
                        str(arguments.get("handoff_id") or ""),
                        status=status,
                        metadata=dict(arguments.get("metadata") or {}),
                    )
                }
                level = "stateful"
            else:
                raise ValueError(f"unsupported session handoff action: {action}")
            return _envelope(True, data=data, tool_name=tool, level=level, target=str(arguments.get("session_id") or arguments.get("handoff_id") or ""), idempotent=level == "read_only")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="stateful", idempotent=False)

    async def learning_status(_: dict[str, Any]) -> dict[str, Any]:
        return _envelope(True, data=learning.status(), tool_name="agent_learning_status", level="read_only")

    async def learning_review(arguments: dict[str, Any]) -> dict[str, Any]:
        return _envelope(
            True,
            data={"proposals": learning.review(status=arguments.get("status"), limit=int(arguments.get("limit") or 100))},
            tool_name="agent_learning_review",
            level="read_only",
        )

    async def learning_apply(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_learning_apply"
        try:
            data = {"proposal": learning.apply(str(arguments.get("proposal_id") or ""))}
            return _envelope(True, data=data, tool_name=tool, level="filesystem_write", idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="filesystem_write", idempotent=False)

    async def skill_reflect(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_skill_reflect"
        try:
            data = {"proposal": learning.reflect_skill(name=str(arguments.get("name") or ""), observation=str(arguments.get("observation") or ""))}
            return _envelope(True, data=data, tool_name=tool, level="stateful", idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="stateful", idempotent=False)

    async def ha_list_entities(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            data = ha_native.list_entities(domain=arguments.get("domain"), area=arguments.get("area"))
            return _envelope(bool(data.get("configured", True)), data=data, error=None if data.get("configured", True) else "Home Assistant is not configured", tool_name="agent_ha_list_entities")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name="agent_ha_list_entities")

    async def ha_get_state(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            data = ha_native.get_state(str(arguments.get("entity_id") or ""))
            return _envelope(bool(data.get("configured", True)), data=data, error=None if data.get("configured", True) else "Home Assistant is not configured", tool_name="agent_ha_get_state")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name="agent_ha_get_state")

    async def ha_list_services(_: dict[str, Any]) -> dict[str, Any]:
        try:
            data = ha_native.list_services()
            return _envelope(bool(data.get("configured", True)), data=data, error=None if data.get("configured", True) else "Home Assistant is not configured", tool_name="agent_ha_list_services")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name="agent_ha_list_services")

    async def ha_list_events(_: dict[str, Any]) -> dict[str, Any]:
        try:
            data = ha_native.list_events()
            return _envelope(bool(data.get("configured", True)), data=data, error=None if data.get("configured", True) else "Home Assistant is not configured", tool_name="agent_ha_list_events")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name="agent_ha_list_events")

    async def ha_list_registry(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            data = ha_native.list_registry(str(arguments.get("kind") or "entity"))
            return _envelope(bool(data.get("configured", True)), data=data, error=None if data.get("configured", True) else "Home Assistant is not configured", tool_name="agent_ha_list_registry")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name="agent_ha_list_registry")

    async def ha_call_service(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_ha_call_service"
        try:
            data = ha_native.call_service(
                domain=str(arguments.get("domain") or ""),
                service=str(arguments.get("service") or ""),
                entity_id=arguments.get("entity_id"),
                data=dict(arguments.get("data") or {}),
                approval_id=arguments.get("approval_id"),
                state_path=session_store.path,
            )
            if data.get("approval_required"):
                payload = _envelope(False, data=data, error="approval required", tool_name=tool, level="physical_state_change", idempotent=False)
                payload["error_code"] = "APPROVAL_REQUIRED"
                return payload
            return _envelope(True, data=data, tool_name=tool, level="physical_state_change", idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="physical_state_change", idempotent=False)

    async def feishu_doc_read(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            data = FeishuClient(domain=str(arguments.get("domain") or "feishu")).read_doc(
                document_id=arguments.get("document_id"),
                url=arguments.get("url"),
            )
            success = bool(data.get("configured")) and not data.get("error")
            return _envelope(success, data=data, error=None if success else str(data.get("error") or "Feishu credentials are not configured"), tool_name="agent_feishu_doc_read")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name="agent_feishu_doc_read")

    async def feishu_comments(arguments: dict[str, Any], *, tool_name: str) -> dict[str, Any]:
        try:
            client = FeishuClient(domain=str(arguments.get("domain") or "feishu"))
            if tool_name == "agent_feishu_drive_list_comments":
                data = client.list_comments(
                    file_token=str(arguments.get("file_token") or ""),
                    file_type=str(arguments.get("file_type") or "docx"),
                    page_token=arguments.get("page_token"),
                    page_size=int(arguments.get("page_size") or 50),
                )
                level = "read_only"
            elif tool_name == "agent_feishu_drive_list_comment_replies":
                data = client.list_comment_replies(
                    file_token=str(arguments.get("file_token") or ""),
                    comment_id=str(arguments.get("comment_id") or ""),
                    file_type=str(arguments.get("file_type") or "docx"),
                    page_token=arguments.get("page_token"),
                    page_size=int(arguments.get("page_size") or 100),
                )
                level = "read_only"
            elif tool_name == "agent_feishu_drive_reply_comment":
                data = client.reply_comment(file_token=str(arguments.get("file_token") or ""), comment_id=str(arguments.get("comment_id") or ""), message=str(arguments.get("message") or ""))
                level = "external_message"
            else:
                data = client.add_comment(file_token=str(arguments.get("file_token") or ""), message=str(arguments.get("message") or ""))
                level = "external_message"
            response = dict(data.get("response") or {})
            success = bool(data.get("configured")) and (not response or bool(response.get("ok")))
            return _envelope(success, data=data, error=None if success else str(response.get("error") or "Feishu API call failed"), tool_name=tool_name, level=level, idempotent=level == "read_only")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool_name, level="external_message", idempotent=False)

    async def discord_channel_send(arguments: dict[str, Any]) -> dict[str, Any]:
        data = await delivery.send(
            platform="discord",
            target=str(arguments.get("channel_id") or ""),
            message=str(arguments.get("message") or ""),
            thread_id=arguments.get("thread_id"),
        )
        success = bool(dict(data.get("adapter") or {}).get("ok"))
        return _envelope(success, data=data, error=None if success else dict(data.get("adapter") or {}).get("status"), tool_name="agent_discord_channel_send", level="external_message", idempotent=False)

    async def discord_server(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_discord_server"
        action = str(arguments.get("action") or "").strip()
        admin_actions = {"pin_message", "unpin_message", "create_thread", "add_role", "remove_role"}
        try:
            if action in admin_actions:
                approvals = ApprovalStore(session_store.path)
                approval_id = str(arguments.get("approval_id") or "").strip()
                approval = approvals.get(approval_id) if approval_id else None
                if not approval or approval.get("status") != "approved":
                    pending = approvals.create(
                        tool_name=tool,
                        action=f"discord_server.{action}",
                        arguments={key: value for key, value in dict(arguments or {}).items() if key != "approval_id"},
                        reason="Discord server management actions can change channel or member state",
                    )
                    payload = _envelope(False, data={"approval": pending}, error="approval required", tool_name=tool, level="platform_admin", idempotent=False)
                    payload["error_code"] = "APPROVAL_REQUIRED"
                    return payload
            data = DiscordServerClient().call(
                action=action,
                guild_id=str(arguments.get("guild_id") or ""),
                channel_id=str(arguments.get("channel_id") or ""),
                user_id=str(arguments.get("user_id") or ""),
                role_id=str(arguments.get("role_id") or ""),
                message_id=str(arguments.get("message_id") or ""),
                query=str(arguments.get("query") or ""),
                name=str(arguments.get("name") or ""),
                limit=int(arguments.get("limit") or 50),
                before=str(arguments.get("before") or ""),
                after=str(arguments.get("after") or ""),
                auto_archive_duration=int(arguments.get("auto_archive_duration") or 1440),
            )
            success = bool(data.get("configured")) and data.get("ok") is not False
            level = "platform_admin" if action in admin_actions else "read_only"
            return _envelope(success, data=data, error=None if success else str(data.get("error") or "Discord API call failed"), tool_name=tool, level=level, idempotent=action not in admin_actions)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="platform_admin", idempotent=False)

    async def rl_list_environments(_: dict[str, Any]) -> dict[str, Any]:
        return _envelope(True, data=rl.list_environments(), tool_name="agent_rl_list_environments")

    async def rl_select_environment(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return _envelope(True, data=rl.select_environment(str(arguments.get("environment") or "")), tool_name="agent_rl_select_environment", level="stateful", idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name="agent_rl_select_environment", level="stateful", idempotent=False)

    async def rl_get_config(_: dict[str, Any]) -> dict[str, Any]:
        return _envelope(True, data=rl.current_config(), tool_name="agent_rl_get_config")

    async def rl_edit_config(arguments: dict[str, Any]) -> dict[str, Any]:
        return _envelope(True, data=rl.edit_config(dict(arguments.get("config") or arguments.get("patch") or {})), tool_name="agent_rl_edit_config", level="stateful", idempotent=False)

    async def rl_start_training(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_rl_start_training"
        try:
            data = rl.start_training(environment=arguments.get("environment"), config_patch=dict(arguments.get("config") or {}))
            success = bool(data.get("started", True)) and data.get("configured", True) is not False
            return _envelope(success, data=data, error=None if success else "RL training credentials are not configured", tool_name=tool, level="process_execution", idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="process_execution", idempotent=False)

    async def rl_check_status(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return _envelope(True, data={"run": rl.check_status(str(arguments.get("run_id") or ""))}, tool_name="agent_rl_check_status")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name="agent_rl_check_status")

    async def rl_stop_training(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return _envelope(True, data={"run": rl.stop_training(str(arguments.get("run_id") or ""))}, tool_name="agent_rl_stop_training", level="process_control", idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name="agent_rl_stop_training", level="process_control", idempotent=False)

    async def rl_get_results(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return _envelope(True, data=rl.results(str(arguments.get("run_id") or "")), tool_name="agent_rl_get_results")
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name="agent_rl_get_results")

    async def rl_list_runs(arguments: dict[str, Any]) -> dict[str, Any]:
        return _envelope(True, data={"runs": rl.list_runs(limit=int(arguments.get("limit") or 100))}, tool_name="agent_rl_list_runs")

    async def rl_test_inference(arguments: dict[str, Any]) -> dict[str, Any]:
        return _envelope(True, data=rl.test_inference(str(arguments.get("prompt") or "")), tool_name="agent_rl_test_inference", level="external_generation", idempotent=False)

    async def message_send(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_message_send"
        try:
            action = str(arguments.get("action") or "send").strip().lower()
            if action == "list":
                return _envelope(True, data={"platforms": gateway.list_platforms()}, tool_name=tool, level="read_only")
            if action != "send":
                raise ValueError(f"unsupported message action: {action}")
            gateway_data = await delivery.send(
                platform=str(arguments.get("platform") or ""),
                target=str(arguments.get("target") or ""),
                message=str(arguments.get("message") or ""),
                thread_id=arguments.get("thread_id"),
                session_id=arguments.get("session_id"),
                user_id=arguments.get("user_id"),
                media_paths=[str(item) for item in list(arguments.get("media_paths") or [])],
            )
            if not dict(gateway_data.get("adapter") or {}).get("ok"):
                data = messages.send(
                    platform=str(arguments.get("platform") or ""),
                    target=str(arguments.get("target") or ""),
                    message=str(arguments.get("message") or ""),
                )
                data["gateway"] = gateway_data
                return _envelope(True, data=data, tool_name=tool, level="external_message", target=data["target"], idempotent=False)
            return _envelope(True, data=gateway_data, tool_name=tool, level="external_message", target=str(arguments.get("target") or ""), idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="external_message", idempotent=False)

    async def webhook(arguments: dict[str, Any]) -> dict[str, Any]:
        tool = "agent_webhook"
        action = str(arguments.get("action") or "list").strip().lower()
        try:
            if action == "list":
                data = {"webhooks": webhooks.list()}
                level = "read_only"
            elif action == "subscribe":
                deliver_mode = str(arguments.get("deliver_mode") or "").strip()
                deliver_value = str(arguments.get("deliver") or "desktop_inbox")
                if deliver_mode == "direct_platform":
                    deliver_value = json.dumps(
                        {
                            "mode": "direct_platform",
                            "platform": str(arguments.get("platform") or "local"),
                            "target": str(arguments.get("target") or ""),
                            "thread_id": arguments.get("thread_id"),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                data = {
                    "webhook": webhooks.subscribe(
                        name=str(arguments.get("name") or ""),
                        events=[str(item) for item in list(arguments.get("events") or [])],
                        prompt=str(arguments.get("prompt") or ""),
                        deliver=deliver_value,
                        secret=arguments.get("secret"),
                    )
                }
                level = "stateful"
            elif action == "remove":
                data = {"deleted": webhooks.remove(str(arguments.get("webhook_id") or ""))}
                level = "stateful"
            elif action == "trigger":
                data = webhooks.render_trigger(
                    str(arguments.get("webhook_id") or ""),
                    event=str(arguments.get("event") or "event"),
                    payload=dict(arguments.get("payload") or {}),
                    signature=arguments.get("signature"),
                )
                deliver_config = data.get("deliver") if isinstance(data.get("deliver"), dict) else {}
                if isinstance(deliver_config, dict) and deliver_config.get("mode") == "direct_platform":
                    routed = await delivery.send(
                        platform=str(deliver_config.get("platform") or "local"),
                        target=str(deliver_config.get("target") or ""),
                        thread_id=deliver_config.get("thread_id"),
                        message=str(data.get("prompt") or ""),
                    )
                    data["direct_delivery"] = routed
                level = "subrun"
            else:
                raise ValueError(f"unsupported webhook action: {action}")
            return _envelope(True, data=data, tool_name=tool, level=level, target=action, idempotent=False)
        except Exception as exc:
            return _envelope(False, error=str(exc), tool_name=tool, level="stateful", idempotent=False)

    return {
        "agent_web_search": web_search,
        "agent_web_extract": web_extract,
        "agent_x_search": x_search,
        "agent_clarify": clarify,
        "agent_todo_set": todo_set,
        "agent_todo_list": todo_list,
        "agent_todo": todo,
        "agent_subgoal": subgoal,
        "agent_skill_list": skill_list,
        "agent_skill_view": skill_view,
        "agent_skill_save": skill_save,
        "agent_skill_manage": skill_manage,
        "agent_plugin_list": plugin_list,
        "agent_plugin_set_enabled": plugin_set_enabled,
        "agent_plugin_manage": plugin_manage,
        "agent_mcp_manage": mcp_manage,
        "agent_model_manage": model_manage,
        "agent_memory_manage": memory_manage,
        "agent_acp_manage": acp_manage,
        "agent_security_scan": security_scan,
        "agent_skill_pack_manage": skill_pack_manage,
        "agent_terminal_backends": terminal_backends,
        "agent_tui_status": tui_status,
        "agent_gateway_status": gateway_status,
        "agent_gateway_platforms": gateway_platforms,
        "agent_gateway_send_message": gateway_send_message,
        "agent_gateway_history": gateway_history,
        "agent_gateway_pairing": gateway_pairing,
        "agent_gateway_directory": gateway_directory,
        "agent_gateway_direct_deliver": gateway_direct_deliver,
        "agent_session_handoff": session_handoff,
        "agent_learning_status": learning_status,
        "agent_learning_review": learning_review,
        "agent_learning_apply": learning_apply,
        "agent_skill_reflect": skill_reflect,
        "agent_ha_list_entities": ha_list_entities,
        "agent_ha_get_state": ha_get_state,
        "agent_ha_list_services": ha_list_services,
        "agent_ha_list_events": ha_list_events,
        "agent_ha_list_registry": ha_list_registry,
        "agent_ha_call_service": ha_call_service,
        "agent_feishu_doc_read": feishu_doc_read,
        "agent_feishu_drive_list_comments": lambda arguments: feishu_comments(arguments, tool_name="agent_feishu_drive_list_comments"),
        "agent_feishu_drive_list_comment_replies": lambda arguments: feishu_comments(arguments, tool_name="agent_feishu_drive_list_comment_replies"),
        "agent_feishu_drive_reply_comment": lambda arguments: feishu_comments(arguments, tool_name="agent_feishu_drive_reply_comment"),
        "agent_feishu_drive_add_comment": lambda arguments: feishu_comments(arguments, tool_name="agent_feishu_drive_add_comment"),
        "agent_discord_channel_send": discord_channel_send,
        "agent_discord_server": discord_server,
        "agent_rl_list_environments": rl_list_environments,
        "agent_rl_select_environment": rl_select_environment,
        "agent_rl_get_config": rl_get_config,
        "agent_rl_edit_config": rl_edit_config,
        "agent_rl_start_training": rl_start_training,
        "agent_rl_check_status": rl_check_status,
        "agent_rl_stop_training": rl_stop_training,
        "agent_rl_get_results": rl_get_results,
        "agent_rl_list_runs": rl_list_runs,
        "agent_rl_test_inference": rl_test_inference,
        "agent_vision_analyze": vision_analyze,
        "agent_image_generate": image_generate,
        "agent_video_generate": video_generate,
        "agent_text_to_speech": text_to_speech,
        "agent_transcribe_audio": transcribe_audio,
        "agent_message_send": message_send,
        "agent_webhook": webhook,
    }
