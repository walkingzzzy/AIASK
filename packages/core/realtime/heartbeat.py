"""
心跳检测模块
维护WebSocket连接的心跳机制
"""
import asyncio
from typing import Dict, Callable, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class HeartbeatManager:
    """
    心跳管理器

    功能：
    1. 定期发送心跳包
    2. 检测客户端连接状态
    3. 自动清理断开的连接
    """

    def __init__(
        self,
        interval: int = 30,
        timeout: int = 60,
        on_timeout: Optional[Callable] = None
    ):
        """
        初始化心跳管理器

        Args:
            interval: 心跳间隔（秒）
            timeout: 超时时间（秒）
            on_timeout: 超时回调函数
        """
        self.interval = interval
        self.timeout = timeout
        self.on_timeout = on_timeout

        # 客户端心跳记录
        self.heartbeats: Dict[str, datetime] = {}

        # 运行状态
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """启动心跳检测"""
        if self.is_running:
            logger.warning("心跳管理器已在运行")
            return

        self.is_running = True
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info(f"心跳管理器已启动: interval={self.interval}s, timeout={self.timeout}s")

    async def stop(self):
        """停止心跳检测"""
        if not self.is_running:
            return

        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("心跳管理器已停止")

    def register_client(self, client_id: str):
        """
        注册客户端

        Args:
            client_id: 客户端ID
        """
        self.heartbeats[client_id] = datetime.now()
        logger.debug(f"注册客户端心跳: {client_id}")

    def update_heartbeat(self, client_id: str):
        """
        更新客户端心跳

        Args:
            client_id: 客户端ID
        """
        self.heartbeats[client_id] = datetime.now()
        logger.debug(f"更新客户端心跳: {client_id}")

    def unregister_client(self, client_id: str):
        """
        注销客户端

        Args:
            client_id: 客户端ID
        """
        if client_id in self.heartbeats:
            del self.heartbeats[client_id]
            logger.debug(f"注销客户端心跳: {client_id}")

    def is_alive(self, client_id: str) -> bool:
        """
        检查客户端是否存活

        Args:
            client_id: 客户端ID

        Returns:
            是否存活
        """
        if client_id not in self.heartbeats:
            return False

        last_heartbeat = self.heartbeats[client_id]
        elapsed = (datetime.now() - last_heartbeat).total_seconds()
        return elapsed < self.timeout

    def get_inactive_clients(self) -> list:
        """
        获取不活跃的客户端列表

        Returns:
            客户端ID列表
        """
        now = datetime.now()
        inactive = []

        for client_id, last_heartbeat in self.heartbeats.items():
            elapsed = (now - last_heartbeat).total_seconds()
            if elapsed >= self.timeout:
                inactive.append(client_id)

        return inactive

    async def _heartbeat_loop(self):
        """心跳检测循环"""
        logger.info("心跳检测循环已启动")

        while self.is_running:
            try:
                # 检查超时客户端
                inactive_clients = self.get_inactive_clients()

                if inactive_clients:
                    logger.warning(f"发现 {len(inactive_clients)} 个超时客户端")

                    # 处理超时客户端
                    for client_id in inactive_clients:
                        logger.info(f"客户端超时: {client_id}")

                        # 调用超时回调
                        if self.on_timeout:
                            try:
                                if asyncio.iscoroutinefunction(self.on_timeout):
                                    await self.on_timeout(client_id)
                                else:
                                    self.on_timeout(client_id)
                            except Exception as e:
                                logger.error(f"超时回调执行失败: {e}")

                        # 注销客户端
                        self.unregister_client(client_id)

                # 等待下一次检测
                await asyncio.sleep(self.interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳检测循环异常: {e}")
                await asyncio.sleep(self.interval)

        logger.info("心跳检测循环已停止")

    def get_stats(self) -> Dict:
        """
        获取统计信息

        Returns:
            统计数据
        """
        now = datetime.now()
        active_count = 0
        inactive_count = 0

        for last_heartbeat in self.heartbeats.values():
            elapsed = (now - last_heartbeat).total_seconds()
            if elapsed < self.timeout:
                active_count += 1
            else:
                inactive_count += 1

        return {
            'total_clients': len(self.heartbeats),
            'active_clients': active_count,
            'inactive_clients': inactive_count,
            'interval': self.interval,
            'timeout': self.timeout,
            'is_running': self.is_running
        }

    def __repr__(self) -> str:
        return (
            f"HeartbeatManager("
            f"clients={len(self.heartbeats)}, "
            f"interval={self.interval}s, "
            f"timeout={self.timeout}s, "
            f"running={self.is_running})"
        )
