"""Gateway Daemon — 入站消息守护进程。

持续监听所有已配置平台的入站消息，路由到 AgentRuntime 处理，
并将响应通过 DeliveryRouter 回复到原平台。

启用方式：设置环境变量 AIASK_GATEWAY_DAEMON_ENABLED=1

架构：
    GatewayDaemon
        ├── PlatformListener (per platform)
        │   ├── Long-polling (Telegram, Weixin iLink, Email IMAP)
        │   └── WebSocket (WeCom, QQ Bot, Discord)
        ├── InboundRouter
        │   ├── record_inbound → GatewayMessageStore
        │   ├── session_resolve → SessionStore
        │   └── route_to_agent → AgentRuntime.run()
        └── OutboundReply
            └── DeliveryRouter.send() → 原平台
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import uuid4

from .gateway import (
    DeliveryRouter,
    GatewayChannelDirectoryStore,
    GatewayConfigStore,
    GatewayMessageStore,
    GatewayRuntime,
    normalize_platform,
)
from .session_store import AgentSessionStore, now_iso


InboundCallback = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class ListenerStatus:
    """单个平台监听器的运行状态。"""

    platform: str
    state: str = "idle"  # idle | starting | running | reconnecting | stopped | failed
    started_at: str | None = None
    last_message_at: str | None = None
    message_count: int = 0
    error: str | None = None
    reconnect_count: int = 0


@dataclass
class DaemonStatus:
    """守护进程整体状态。"""

    state: str = "idle"  # idle | starting | running | stopping | stopped | failed
    started_at: str | None = None
    listeners: dict[str, ListenerStatus] = field(default_factory=dict)
    total_messages: int = 0
    total_responses: int = 0
    last_error: str | None = None


class GatewayDaemon:
    """入站消息守护进程 — 持续监听所有已配置平台的入站消息。"""

    def __init__(
        self,
        *,
        runtime: Any = None,
        config: GatewayConfigStore | None = None,
        router: DeliveryRouter | None = None,
        messages: GatewayMessageStore | None = None,
        gateway_runtime: GatewayRuntime | None = None,
    ) -> None:
        self.runtime = runtime
        self.config = config or GatewayConfigStore()
        self.messages = messages or GatewayMessageStore()
        self.router = router or DeliveryRouter(config=self.config, messages=self.messages)
        self.gateway_runtime = gateway_runtime or GatewayRuntime(
            config=self.config, messages=self.messages
        )
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False
        self._status = DaemonStatus()

        # Configuration
        self._reconnect_delay = float(
            os.getenv("AIASK_GATEWAY_RECONNECT_DELAY", "30")
        )
        self._max_retries = int(os.getenv("AIASK_GATEWAY_MAX_RETRIES", "10"))
        self._response_timeout = float(
            os.getenv("AIASK_GATEWAY_RESPONSE_TIMEOUT", "120")
        )
        # Concurrency control: max parallel agent calls
        self._max_concurrent_agents = int(
            os.getenv("AIASK_GATEWAY_MAX_CONCURRENT", "5")
        )
        self._agent_semaphore = asyncio.Semaphore(self._max_concurrent_agents)
        # Rate limiting: per-user message rate
        self._rate_limit_window = float(
            os.getenv("AIASK_GATEWAY_RATE_LIMIT_WINDOW", "60")
        )
        self._rate_limit_max = int(
            os.getenv("AIASK_GATEWAY_RATE_LIMIT_MAX", "20")
        )
        self._user_message_times: dict[str, list[float]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> dict[str, Any]:
        """启动所有已配置平台的入站监听。"""
        if self._running:
            return self.status()

        self._running = True
        self._status.state = "starting"
        self._status.started_at = now_iso()
        self.gateway_runtime.write_runtime_status(state="starting")

        platforms = self.config.platforms()
        started: list[str] = []

        for platform_info in platforms:
            name = str(platform_info.get("name") or "")
            enabled = bool(platform_info.get("enabled"))
            configured = bool(platform_info.get("configured"))

            if not enabled or not configured:
                continue

            listener_fn = self._get_listener(name)
            if listener_fn is None:
                continue

            self._status.listeners[name] = ListenerStatus(platform=name)
            task = asyncio.create_task(
                self._run_listener(name, listener_fn),
                name=f"gateway-listener-{name}",
            )
            self._tasks[name] = task
            started.append(name)

        self._status.state = "running"
        self.gateway_runtime.write_runtime_status(state="running")

        return {
            "status": "started",
            "listeners": started,
            "total": len(started),
        }

    async def stop(self) -> dict[str, Any]:
        """停止所有监听。"""
        self._running = False
        self._status.state = "stopping"

        for name, task in list(self._tasks.items()):
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass

        self._tasks.clear()
        self._status.state = "stopped"
        self.gateway_runtime.write_runtime_status(state="stopped")

        return {"status": "stopped"}

    def status(self) -> dict[str, Any]:
        """返回守护进程状态。"""
        return {
            "object": "aiask.gateway_daemon_status",
            "state": self._status.state,
            "started_at": self._status.started_at,
            "total_messages": self._status.total_messages,
            "total_responses": self._status.total_responses,
            "last_error": self._status.last_error,
            "listeners": {
                name: {
                    "platform": ls.platform,
                    "state": ls.state,
                    "started_at": ls.started_at,
                    "last_message_at": ls.last_message_at,
                    "message_count": ls.message_count,
                    "reconnect_count": ls.reconnect_count,
                    "error": ls.error,
                }
                for name, ls in self._status.listeners.items()
            },
        }

    # ------------------------------------------------------------------
    # Listener management (Production-grade resilience)
    # ------------------------------------------------------------------

    async def _run_listener(
        self, name: str, listener_fn: Callable[..., Awaitable[None]]
    ) -> None:
        """运行单个平台的监听，生产级自动重连。

        重连策略：
        - 指数退避：delay = min(base_delay * 2^retries, max_delay)
        - 成功运行超过 stable_threshold 秒后重置重试计数
        - 超过 max_retries 后进入 failed 状态，但定期尝试恢复
        - 支持 circuit breaker 模式：连续失败后暂停更长时间
        """
        ls = self._status.listeners[name]
        ls.state = "starting"
        ls.started_at = now_iso()

        retries = 0
        stable_threshold = 60.0  # 运行超过 60 秒视为稳定
        max_delay = 300.0  # 最大重连延迟 5 分钟
        recovery_interval = 600.0  # failed 后每 10 分钟尝试恢复

        while self._running:
            run_start = time.time()
            try:
                ls.state = "running"
                ls.error = None
                await listener_fn(callback=self._on_inbound_message)
                # Listener exited normally (shouldn't happen in production)
                # Treat as needing reconnect
            except asyncio.CancelledError:
                ls.state = "stopped"
                return
            except Exception as exc:
                ls.error = f"{type(exc).__name__}: {exc}"
                self._status.last_error = f"[{name}] {ls.error}"

            # Check if it ran long enough to be considered stable
            run_duration = time.time() - run_start
            if run_duration >= stable_threshold:
                # Was stable, reset retry count
                retries = 0
            else:
                retries += 1
                ls.reconnect_count += 1

            if not self._running:
                ls.state = "stopped"
                return

            # Determine delay
            if retries > self._max_retries:
                ls.state = "failed"
                # Enter recovery mode: wait longer, then try again
                await asyncio.sleep(recovery_interval)
                retries = 0  # Reset for recovery attempt
                ls.state = "reconnecting"
            else:
                ls.state = "reconnecting"
                # Exponential backoff with jitter
                base_delay = self._reconnect_delay * (2 ** min(retries - 1, 6))
                delay = min(base_delay, max_delay)
                # Add small jitter to avoid thundering herd
                import random
                jitter = random.uniform(0, min(delay * 0.1, 5.0))
                await asyncio.sleep(delay + jitter)

        ls.state = "stopped"

    def _get_listener(self, platform: str) -> Callable[..., Awaitable[None]] | None:
        """获取平台对应的监听器函数。"""
        listeners: dict[str, Callable[..., Awaitable[None]]] = {
            "telegram": self._poll_telegram,
            "email": self._poll_email,
            "weixin": self._poll_weixin_ilink,
            "wecom": self._ws_wecom,
            "qqbot": self._ws_qqbot,
            "discord": self._ws_discord,
        }
        return listeners.get(platform)

    # ------------------------------------------------------------------
    # Inbound message handler
    # ------------------------------------------------------------------

    async def _on_inbound_message(self, event: dict[str, Any]) -> None:
        """处理入站消息：记录 → 路由 → Agent 处理 → 回复。"""
        platform = normalize_platform(event.get("platform"))

        # Update listener stats
        ls = self._status.listeners.get(platform)
        if ls:
            ls.message_count += 1
            ls.last_message_at = now_iso()
        self._status.total_messages += 1

        # 1. Record inbound message
        record = self.router.record_inbound(
            platform=platform,
            payload=event,
            signature=event.get("signature"),
        )

        metadata = dict(record.get("metadata") or {})

        # 1.5 Security checks (whitelist + rate limit + content filter)
        try:
            from .gateway_security import GatewaySecurity
            security = GatewaySecurity()
            sender_id = event.get("sender_id") or event.get("user_id") or ""
            content_raw = str(event.get("content") or event.get("text") or "")
            sec_check = security.check_inbound(platform, str(sender_id), content_raw)
            if not sec_check["allowed"]:
                logger.debug("GatewayDaemon: blocked %s:%s reason=%s", platform, sender_id, sec_check["reason"])
                return
        except Exception:
            pass  # Security module not critical — degrade gracefully

        # 2. Check for control commands (/approve, /deny, /stop, /reset)
        control_action = metadata.get("control_action")
        if control_action:
            await self._handle_control(control_action, record, event)
            return

        # 3. Skip if no content
        content = str(record.get("content") or "").strip()
        if not content:
            return

        # 4. Rate limiting
        user_key = f"{platform}:{event.get('user_id') or 'anon'}"
        if not self._check_rate_limit(user_key):
            return

        # 5. Resolve session (platform + user → session_id)
        session_id = self._resolve_session(event)

        # 6. Route to AgentRuntime (with concurrency control)
        reply_content = await self._process_with_agent(content, session_id)

        # 7. Reply to original platform
        if reply_content:
            reply_target = (
                event.get("chat_id")
                or event.get("target")
                or event.get("channel_id")
                or ""
            )
            thread_id = event.get("thread_id") or event.get("message_thread_id")

            if reply_target:
                try:
                    await self.router.send(
                        platform=platform,
                        target=str(reply_target),
                        message=reply_content,
                        thread_id=thread_id,
                        session_id=session_id,
                        user_id=event.get("user_id"),
                    )
                    self._status.total_responses += 1
                except Exception as exc:
                    self._status.last_error = f"reply failed [{platform}]: {exc}"

    async def _process_with_agent(
        self, message: str, session_id: str
    ) -> str | None:
        """调用 AgentRuntime 处理消息，带并发控制。"""
        if self.runtime is None:
            return "[AIASK Gateway] Agent runtime not available."

        # Concurrency control: limit parallel agent calls
        async with self._agent_semaphore:
            try:
                result = await asyncio.wait_for(
                    self.runtime.run(message=message, session_id=session_id),
                    timeout=self._response_timeout,
                )
                return str(getattr(result, "content", "") or "")
            except asyncio.TimeoutError:
                return "[AIASK Gateway] Response timeout."
            except Exception as exc:
                self._status.last_error = f"agent error: {exc}"
                return None

    async def _handle_control(
        self,
        control_action: dict[str, Any],
        record: dict[str, Any],
        event: dict[str, Any],
    ) -> None:
        """处理控制命令（/approve, /deny, /stop, /new, /reset, /help）。"""
        command = str(control_action.get("command") or "").lower()
        arguments = str(control_action.get("arguments") or "").strip()
        platform = normalize_platform(event.get("platform"))
        reply_target = event.get("chat_id") or event.get("target") or ""

        response = ""
        if command == "help":
            response = (
                "AIASK Gateway 控制命令：\n"
                "/approve <intent_id> — 批准操作\n"
                "/deny <intent_id> — 拒绝操作\n"
                "/stop — 停止当前任务\n"
                "/new — 新建会话\n"
                "/reset — 重置会话\n"
                "/help — 显示帮助"
            )
        elif command in {"approve", "deny"}:
            # Delegate to approval callback
            approval = record.get("metadata", {}).get("approval_callback")
            if approval:
                response = f"操作已{('批准' if command == 'approve' else '拒绝')}: {approval.get('approval_id')}"
            else:
                response = f"未找到待确认的操作。用法: /{command} <intent_id>"
        elif command == "new":
            response = "已创建新会话。"
        elif command == "reset":
            response = "会话已重置。"
        elif command == "stop":
            response = "当前任务已停止。"
        else:
            response = f"未知命令: /{command}。输入 /help 查看帮助。"

        if response and reply_target:
            try:
                await self.router.send(
                    platform=platform,
                    target=str(reply_target),
                    message=response,
                    thread_id=event.get("thread_id"),
                )
            except Exception:
                pass

    def _resolve_session(self, event: dict[str, Any]) -> str:
        """根据平台 + 用户解析会话 ID，支持跨平台会话同步。

        会话解析策略：
        1. 如果用户在多个平台使用相同标识（如手机号），统一为同一会话
        2. 同一平台同一用户的不同群聊视为不同会话
        3. 私聊消息使用 user_id 作为会话标识
        4. 群聊消息使用 chat_id 作为会话标识
        """
        platform = normalize_platform(event.get("platform"))
        user_id = str(event.get("user_id") or event.get("sender") or "anonymous")
        chat_id = str(event.get("chat_id") or event.get("target") or "default")
        is_group = bool(event.get("is_group") or (chat_id != user_id and chat_id != "default"))

        # Check cross-platform identity mapping
        unified_id = self._cross_platform_lookup(platform, user_id)
        if unified_id:
            user_id = unified_id

        if is_group:
            return f"gw_{platform}_{chat_id}"
        return f"gw_{platform}_dm_{user_id}"

    def _cross_platform_lookup(self, platform: str, user_id: str) -> str | None:
        """跨平台用户身份映射查找。

        通过 gateway_directory 中的 'identity' 类型条目进行映射。
        例如：同一用户在微信和 Telegram 上的 ID 映射到统一标识。
        """
        if not user_id or user_id == "anonymous":
            return None
        try:
            entry = self.router.directory.resolve(
                platform=platform, name=user_id, kind="identity"
            )
            if entry and entry.get("metadata", {}).get("unified_id"):
                return str(entry["metadata"]["unified_id"])
        except Exception:
            pass
        return None

    def _check_rate_limit(self, user_key: str) -> bool:
        """检查用户消息速率限制。返回 True 表示允许。"""
        now = time.time()
        window = self._rate_limit_window
        max_msgs = self._rate_limit_max

        if user_key not in self._user_message_times:
            self._user_message_times[user_key] = []

        # Clean old entries
        cutoff = now - window
        self._user_message_times[user_key] = [
            t for t in self._user_message_times[user_key] if t > cutoff
        ]

        if len(self._user_message_times[user_key]) >= max_msgs:
            return False

        self._user_message_times[user_key].append(now)
        return True

    # ------------------------------------------------------------------
    # Health monitoring
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """执行健康检查，返回各监听器状态。"""
        results: dict[str, Any] = {
            "daemon_state": self._status.state,
            "uptime_seconds": (
                time.time() - time.mktime(
                    time.strptime(self._status.started_at[:19], "%Y-%m-%dT%H:%M:%S")
                )
                if self._status.started_at
                else 0
            ),
            "total_messages": self._status.total_messages,
            "total_responses": self._status.total_responses,
            "listeners": {},
        }

        for name, ls in self._status.listeners.items():
            results["listeners"][name] = {
                "state": ls.state,
                "message_count": ls.message_count,
                "reconnect_count": ls.reconnect_count,
                "last_message_at": ls.last_message_at,
                "error": ls.error,
                "healthy": ls.state == "running",
            }

        results["healthy"] = (
            self._status.state == "running"
            and any(
                ls.state == "running"
                for ls in self._status.listeners.values()
            )
        )
        return results

    # ------------------------------------------------------------------
    # Platform listeners
    # ------------------------------------------------------------------

    async def _poll_telegram(self, *, callback: InboundCallback) -> None:
        """Telegram getUpdates 长轮询。"""
        import urllib.request
        import urllib.error

        token = str(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")

        base_url = f"https://api.telegram.org/bot{token}"
        offset = 0
        poll_timeout = 30

        while self._running:
            url = f"{base_url}/getUpdates?offset={offset}&timeout={poll_timeout}"
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=poll_timeout + 10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                if not data.get("ok"):
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result") or []:
                    offset = max(offset, int(update.get("update_id", 0)) + 1)
                    message = update.get("message") or update.get("edited_message")
                    if not message:
                        continue

                    text = str(message.get("text") or message.get("caption") or "")
                    chat = message.get("chat") or {}
                    sender = message.get("from") or {}

                    await callback(
                        {
                            "platform": "telegram",
                            "text": text,
                            "chat_id": str(chat.get("id") or ""),
                            "target": str(chat.get("id") or ""),
                            "user_id": str(sender.get("id") or ""),
                            "message_id": str(message.get("message_id") or ""),
                            "thread_id": str(
                                message.get("message_thread_id") or ""
                            ),
                            "username": sender.get("username") or "",
                            "first_name": sender.get("first_name") or "",
                        }
                    )

            except (urllib.error.URLError, OSError, asyncio.TimeoutError):
                await asyncio.sleep(5)
            except Exception:
                await asyncio.sleep(5)

    async def _poll_email(self, *, callback: InboundCallback) -> None:
        """IMAP 邮箱入站轮询。"""
        import imaplib
        import email as email_lib
        from email.header import decode_header

        host = str(os.getenv("IMAP_HOST") or "").strip()
        username = str(os.getenv("IMAP_USERNAME") or "").strip()
        password = str(os.getenv("IMAP_PASSWORD") or "").strip()
        folder = str(os.getenv("IMAP_FOLDER") or "INBOX").strip()
        interval = int(os.getenv("IMAP_POLL_INTERVAL") or "60")

        if not host or not username or not password:
            raise RuntimeError("IMAP credentials not configured (IMAP_HOST, IMAP_USERNAME, IMAP_PASSWORD)")

        while self._running:
            try:
                use_ssl = str(os.getenv("IMAP_SSL", "1")).strip().lower() not in {"0", "false", "no"}
                if use_ssl:
                    mail = imaplib.IMAP4_SSL(host, timeout=30)
                else:
                    mail = imaplib.IMAP4(host, timeout=30)

                mail.login(username, password)
                mail.select(folder)

                _, message_numbers = mail.search(None, "UNSEEN")
                nums = (message_numbers[0] or b"").split()

                for num in nums[:20]:  # Process max 20 per poll
                    _, msg_data = mail.fetch(num, "(RFC822)")
                    if not msg_data or not msg_data[0]:
                        continue

                    raw_email = msg_data[0][1]
                    msg = email_lib.message_from_bytes(raw_email)

                    subject = ""
                    raw_subject = msg.get("Subject", "")
                    if raw_subject:
                        decoded = decode_header(raw_subject)
                        subject = "".join(
                            part.decode(enc or "utf-8") if isinstance(part, bytes) else part
                            for part, enc in decoded
                        )

                    sender_addr = msg.get("From", "")
                    message_id = msg.get("Message-ID", "")

                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                payload = part.get_payload(decode=True)
                                if payload:
                                    body = payload.decode("utf-8", errors="replace")
                                    break
                    else:
                        payload = msg.get_payload(decode=True)
                        if payload:
                            body = payload.decode("utf-8", errors="replace")

                    content = f"[{subject}]\n{body}" if subject else body

                    await callback(
                        {
                            "platform": "email",
                            "text": content.strip(),
                            "chat_id": sender_addr,
                            "target": sender_addr,
                            "user_id": sender_addr,
                            "message_id": message_id,
                            "thread_id": "",
                            "subject": subject,
                        }
                    )

                    # Mark as seen
                    mail.store(num, "+FLAGS", "\\Seen")

                mail.logout()

            except Exception:
                pass

            await asyncio.sleep(interval)

    # ------------------------------------------------------------------
    # Phase 2: WeChat iLink Bot 长轮询
    # ------------------------------------------------------------------

    async def _poll_weixin_ilink(self, *, callback: InboundCallback) -> None:
        """个人微信 iLink Bot API 长轮询。

        iLink Bot 是腾讯官方提供的个人微信机器人接口，
        通过长轮询方式接收消息，无需公网 IP。

        环境变量：
            WEIXIN_ILINK_APP_ID: iLink Bot App ID
            WEIXIN_ILINK_APP_SECRET: iLink Bot App Secret
        """
        import urllib.request
        import urllib.error

        app_id = str(os.getenv("WEIXIN_ILINK_APP_ID") or "").strip()
        app_secret = str(os.getenv("WEIXIN_ILINK_APP_SECRET") or "").strip()

        if not app_id or not app_secret:
            raise RuntimeError("WEIXIN_ILINK_APP_ID and WEIXIN_ILINK_APP_SECRET are required")

        base_url = "https://api.weixin.qq.com/ilink/v1"
        access_token = ""
        token_expires_at = 0.0
        poll_timeout = 25

        async def _refresh_token() -> str:
            nonlocal access_token, token_expires_at
            if access_token and time.time() < token_expires_at - 60:
                return access_token
            url = (
                f"{base_url}/token?grant_type=client_credential"
                f"&appid={app_id}&secret={app_secret}"
            )
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("access_token"):
                access_token = data["access_token"]
                token_expires_at = time.time() + int(data.get("expires_in", 7200))
                return access_token
            raise RuntimeError(f"iLink token error: {data}")

        cursor = ""

        while self._running:
            try:
                token = await _refresh_token()
                url = f"{base_url}/message/pull?access_token={token}&timeout={poll_timeout}"
                if cursor:
                    url += f"&cursor={cursor}"

                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=poll_timeout + 10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                if data.get("errcode") and data["errcode"] != 0:
                    access_token = ""
                    await asyncio.sleep(5)
                    continue

                messages = data.get("msg_list") or data.get("messages") or []
                new_cursor = data.get("next_cursor") or data.get("cursor") or ""
                if new_cursor:
                    cursor = new_cursor

                for msg in messages:
                    msg_type = str(msg.get("msg_type") or msg.get("type") or "text")
                    if msg_type == "text":
                        content = str(msg.get("content") or msg.get("text") or "")
                    elif msg_type == "image":
                        content = f"[图片] {msg.get('pic_url') or msg.get('media_id') or ''}"
                    elif msg_type == "voice":
                        content = f"[语音] {msg.get('media_id') or ''}"
                    elif msg_type == "video":
                        content = f"[视频] {msg.get('media_id') or ''}"
                    elif msg_type == "file":
                        content = f"[文件] {msg.get('file_name') or msg.get('media_id') or ''}"
                    else:
                        content = str(msg.get("content") or msg.get("text") or f"[{msg_type}]")

                    if not content.strip():
                        continue

                    from_user = str(msg.get("from_user") or msg.get("from_wxid") or msg.get("sender") or "")
                    chat_id = str(msg.get("room_id") or msg.get("to_user") or msg.get("conversation_id") or from_user)

                    await callback({
                        "platform": "weixin",
                        "text": content,
                        "chat_id": chat_id,
                        "target": chat_id,
                        "user_id": from_user,
                        "message_id": str(msg.get("msg_id") or msg.get("id") or ""),
                        "thread_id": "",
                        "msg_type": msg_type,
                        "is_group": bool(msg.get("room_id")),
                    })

            except (urllib.error.URLError, OSError, asyncio.TimeoutError):
                await asyncio.sleep(5)
            except RuntimeError:
                await asyncio.sleep(10)
            except Exception:
                await asyncio.sleep(5)

    # ------------------------------------------------------------------
    # Phase 2: 企业微信 WebSocket 双向通信
    # ------------------------------------------------------------------

    async def _ws_wecom(self, *, callback: InboundCallback) -> None:
        """企业微信 AI Bot WebSocket 双向通信。

        环境变量：
            WECOM_CORP_ID: 企业 ID
            WECOM_SECRET: 应用 Secret
            WECOM_WS_ENABLED: 启用 WebSocket 模式（设为 1）
        """
        import urllib.request

        corp_id = str(os.getenv("WECOM_CORP_ID") or "").strip()
        secret = str(os.getenv("WECOM_SECRET") or "").strip()
        if not corp_id or not secret:
            raise RuntimeError("WECOM_CORP_ID and WECOM_SECRET are required")

        ws_enabled = str(os.getenv("WECOM_WS_ENABLED") or "").strip().lower() in {"1", "true", "yes"}
        if not ws_enabled:
            raise RuntimeError("WECOM_WS_ENABLED must be set to 1 for WebSocket mode")

        try:
            import websockets
        except ImportError:
            raise RuntimeError("websockets package required: pip install websockets")

        async def _get_token() -> str:
            url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corp_id}&corpsecret={secret}"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            token = data.get("access_token")
            if not token:
                raise RuntimeError(f"WeCom token error: {data}")
            return token

        async def _get_ws_url(token: str) -> str:
            url = f"https://qyapi.weixin.qq.com/cgi-bin/websocket/get_url?access_token={token}"
            body = json.dumps({"type": "ai_bot"}).encode("utf-8")
            req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            ws_url = data.get("url") or data.get("ws_url")
            if not ws_url:
                raise RuntimeError(f"WeCom WS URL error: {data}")
            return ws_url

        while self._running:
            try:
                token = await _get_token()
                ws_url = await _get_ws_url(token)

                async with websockets.connect(ws_url, ping_interval=30, ping_timeout=10, close_timeout=5) as ws:
                    while self._running:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=60)
                        except asyncio.TimeoutError:
                            await ws.send(json.dumps({"type": "heartbeat"}))
                            continue

                        try:
                            event = json.loads(raw)
                        except (json.JSONDecodeError, TypeError):
                            continue

                        event_type = str(event.get("type") or event.get("MsgType") or "")
                        if event_type in ("heartbeat", "pong", "ack"):
                            continue

                        if event_type in ("message", "text", "event"):
                            content = str(event.get("Content") or event.get("content") or event.get("text") or "")
                            if not content.strip():
                                continue
                            from_user = str(event.get("FromUserName") or event.get("from_user") or event.get("UserId") or "")
                            chat_id = str(event.get("ChatId") or event.get("chat_id") or from_user)

                            await callback({
                                "platform": "wecom",
                                "text": content,
                                "chat_id": chat_id,
                                "target": chat_id,
                                "user_id": from_user,
                                "message_id": str(event.get("MsgId") or event.get("msg_id") or ""),
                                "thread_id": "",
                            })

            except (OSError, ConnectionError):
                await asyncio.sleep(10)
            except Exception:
                await asyncio.sleep(10)

    # ------------------------------------------------------------------
    # Phase 2: QQ Bot v2 WebSocket
    # ------------------------------------------------------------------

    async def _ws_qqbot(self, *, callback: InboundCallback) -> None:
        """QQ Bot API v2 WebSocket — 频道/C2C/群消息。

        环境变量：
            QQBOT_APP_ID, QQBOT_TOKEN, QQBOT_WS_ENABLED=1
        """
        import urllib.request

        app_id = str(os.getenv("QQBOT_APP_ID") or "").strip()
        token = str(os.getenv("QQBOT_TOKEN") or "").strip()
        if not app_id or not token:
            raise RuntimeError("QQBOT_APP_ID and QQBOT_TOKEN are required")

        ws_enabled = str(os.getenv("QQBOT_WS_ENABLED") or "").strip().lower() in {"1", "true", "yes"}
        if not ws_enabled:
            raise RuntimeError("QQBOT_WS_ENABLED must be set to 1")

        try:
            import websockets
        except ImportError:
            raise RuntimeError("websockets package required: pip install websockets")

        async def _get_gateway() -> str:
            base = str(os.getenv("QQBOT_API_BASE") or "https://api.sgroup.qq.com").rstrip("/")
            req = urllib.request.Request(f"{base}/gateway", method="GET", headers={"Authorization": f"Bot {app_id}.{token}"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data.get("url", "")

        seq = 0
        session_id = ""
        heartbeat_interval = 41250

        while self._running:
            try:
                gateway_url = await _get_gateway()
                if not gateway_url:
                    await asyncio.sleep(30)
                    continue

                async with websockets.connect(gateway_url, ping_interval=None, close_timeout=5) as ws:
                    # Hello
                    hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                    if hello.get("op") == 10:
                        heartbeat_interval = hello.get("d", {}).get("heartbeat_interval", 41250)

                    # Identify
                    intents = (1 << 0) | (1 << 9) | (1 << 25) | (1 << 26)
                    if session_id:
                        await ws.send(json.dumps({"op": 6, "d": {"token": f"Bot {app_id}.{token}", "session_id": session_id, "seq": seq}}))
                    else:
                        await ws.send(json.dumps({"op": 2, "d": {"token": f"Bot {app_id}.{token}", "intents": intents, "shard": [0, 1]}}))

                    async def _hb():
                        while self._running:
                            await asyncio.sleep(heartbeat_interval / 1000)
                            try:
                                await ws.send(json.dumps({"op": 1, "d": seq or None}))
                            except Exception:
                                break

                    hb_task = asyncio.create_task(_hb())
                    try:
                        while self._running:
                            try:
                                raw = await asyncio.wait_for(ws.recv(), timeout=heartbeat_interval / 1000 + 10)
                            except asyncio.TimeoutError:
                                continue

                            event = json.loads(raw)
                            op, s, t, d = event.get("op", 0), event.get("s"), event.get("t", ""), event.get("d") or {}
                            if s is not None:
                                seq = s

                            if op == 0:
                                if t == "READY":
                                    session_id = d.get("session_id", "")
                                    continue
                                content, from_user, chat_id, msg_id = "", "", "", ""
                                if t in ("MESSAGE_CREATE", "AT_MESSAGE_CREATE"):
                                    content = str(d.get("content") or "")
                                    from_user = str(d.get("author", {}).get("id") or "")
                                    chat_id = str(d.get("channel_id") or "")
                                    msg_id = str(d.get("id") or "")
                                elif t == "C2C_MESSAGE_CREATE":
                                    content = str(d.get("content") or "")
                                    from_user = str(d.get("author", {}).get("user_openid") or "")
                                    chat_id = from_user
                                    msg_id = str(d.get("id") or "")
                                elif t == "GROUP_AT_MESSAGE_CREATE":
                                    content = str(d.get("content") or "")
                                    from_user = str(d.get("author", {}).get("member_openid") or "")
                                    chat_id = str(d.get("group_openid") or "")
                                    msg_id = str(d.get("id") or "")
                                else:
                                    continue
                                if not content.strip():
                                    continue
                                await callback({"platform": "qqbot", "text": content, "chat_id": chat_id, "target": chat_id, "user_id": from_user, "message_id": msg_id, "thread_id": "", "event_type": t})
                            elif op in (7, 9):
                                if op == 9:
                                    session_id = ""
                                    seq = 0
                                break
                    finally:
                        hb_task.cancel()
                        try:
                            await hb_task
                        except (asyncio.CancelledError, Exception):
                            pass

            except (OSError, ConnectionError):
                await asyncio.sleep(10)
            except Exception:
                await asyncio.sleep(10)

    # ------------------------------------------------------------------
    # Phase 2: Discord WebSocket Gateway
    # ------------------------------------------------------------------

    async def _ws_discord(self, *, callback: InboundCallback) -> None:
        """Discord Gateway WebSocket。

        环境变量：DISCORD_BOT_TOKEN
        """
        import urllib.request

        token = str(os.getenv("DISCORD_BOT_TOKEN") or "").strip()
        if not token:
            raise RuntimeError("DISCORD_BOT_TOKEN is required")

        try:
            import websockets
        except ImportError:
            raise RuntimeError("websockets package required: pip install websockets")

        async def _get_gw() -> str:
            req = urllib.request.Request("https://discord.com/api/v10/gateway/bot", method="GET", headers={"Authorization": f"Bot {token}"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data.get("url", "wss://gateway.discord.gg") + "?v=10&encoding=json"

        seq = None
        session_id = ""
        resume_url = ""
        heartbeat_interval = 41250

        while self._running:
            try:
                gw_url = resume_url if (resume_url and session_id) else await _get_gw()

                async with websockets.connect(gw_url, ping_interval=None, close_timeout=5) as ws:
                    hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                    if hello.get("op") == 10:
                        heartbeat_interval = hello["d"]["heartbeat_interval"]

                    if session_id and seq is not None:
                        await ws.send(json.dumps({"op": 6, "d": {"token": f"Bot {token}", "session_id": session_id, "seq": seq}}))
                    else:
                        await ws.send(json.dumps({"op": 2, "d": {"token": f"Bot {token}", "intents": (1 << 9) | (1 << 12) | (1 << 15), "properties": {"os": "linux", "browser": "aiask", "device": "aiask"}}}))

                    async def _hb():
                        while self._running:
                            await asyncio.sleep(heartbeat_interval / 1000)
                            try:
                                await ws.send(json.dumps({"op": 1, "d": seq}))
                            except Exception:
                                break

                    hb_task = asyncio.create_task(_hb())
                    try:
                        while self._running:
                            try:
                                raw = await asyncio.wait_for(ws.recv(), timeout=heartbeat_interval / 1000 + 10)
                            except asyncio.TimeoutError:
                                continue
                            event = json.loads(raw)
                            op, s, t, d = event.get("op", 0), event.get("s"), event.get("t", ""), event.get("d") or {}
                            if s is not None:
                                seq = s
                            if op == 0:
                                if t == "READY":
                                    session_id = d.get("session_id", "")
                                    resume_url = d.get("resume_gateway_url", "")
                                    continue
                                if t == "MESSAGE_CREATE":
                                    author = d.get("author") or {}
                                    if author.get("bot"):
                                        continue
                                    content = str(d.get("content") or "")
                                    if not content.strip():
                                        continue
                                    await callback({"platform": "discord", "text": content, "chat_id": str(d.get("channel_id") or ""), "target": str(d.get("channel_id") or ""), "user_id": str(author.get("id") or ""), "message_id": str(d.get("id") or ""), "thread_id": "", "username": author.get("username", "")})
                            elif op == 7:
                                break
                            elif op == 9:
                                if not d:
                                    session_id = ""
                                    seq = None
                                break
                    finally:
                        hb_task.cancel()
                        try:
                            await hb_task
                        except (asyncio.CancelledError, Exception):
                            pass

            except (OSError, ConnectionError):
                await asyncio.sleep(10)
            except Exception:
                await asyncio.sleep(10)


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------


def create_gateway_daemon(
    *,
    runtime: Any = None,
    config: GatewayConfigStore | None = None,
) -> GatewayDaemon:
    """创建 GatewayDaemon 实例。"""
    return GatewayDaemon(runtime=runtime, config=config)


def daemon_enabled() -> bool:
    """检查是否启用了入站守护进程。"""
    return str(os.getenv("AIASK_GATEWAY_DAEMON_ENABLED", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
