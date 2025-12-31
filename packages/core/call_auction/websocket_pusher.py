"""
竞价数据WebSocket推送模块
提供实时竞价数据和预警的WebSocket推送功能
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from .models import Alert

logger = logging.getLogger(__name__)


class AuctionWebSocketPusher:
    """
    竞价数据WebSocket推送器
    
    提供功能：
    - 实时数据推送
    - 预警推送
    - 连接管理
    - 消息广播
    Attributes:
        clients: 已连接的WebSocket客户端集合
        is_running: 推送器是否运行中"""
    
    def __init__(self, ping_interval: int = 30):
        """
        初始化WebSocket推送器
        
        Args:
            ping_interval: 心跳间隔（秒）
        """
        self._clients: Set[Any] = set()
        self._is_running = False
        self._ping_interval = ping_interval
        self._lock = asyncio.Lock()
        
        # 消息队列
        self._message_queue: asyncio.Queue = asyncio.Queue()
        # 推送任务
        self._push_task: Optional[asyncio.Task] = None# 消息处理器
        self._message_handlers: Dict[str, Callable] = {}
        
        logger.info(f"AuctionWebSocketPusher initialized with ping_interval={ping_interval}s")
    
    async def start(self) -> None:
        """
        启动推送服务
        """
        if self._is_running:
            logger.warning("WebSocket pusher is already running")
            return
        
        self._is_running = True
        self._push_task = asyncio.create_task(self._push_loop())
        logger.info("WebSocket pusher started")
    
    async def stop(self) -> None:
        """
        停止推送服务
        """
        if not self._is_running:
            logger.warning("WebSocket pusher is not running")
            return
        
        self._is_running = False
        if self._push_task:
            self._push_task.cancel()
            try:
                await self._push_task
            except asyncio.CancelledError:
                pass
            self._push_task = None
        
        # 关闭所有连接
        await self._close_all_connections()
        
        logger.info("WebSocket pusher stopped")
    
    async def register_client(self, websocket: Any) -> None:
        """
        注册WebSocket客户端
        
        Args:
            websocket: WebSocket连接对象
        """
        async with self._lock:
            self._clients.add(websocket)
            logger.info(f"Client registered, total clients: {len(self._clients)}")
    
    async def unregister_client(self, websocket: Any) -> None:
        """
        注销WebSocket客户端
        
        Args:
            websocket: WebSocket连接对象
        """
        async with self._lock:
            self._clients.discard(websocket)
            logger.info(f"Client unregistered, total clients: {len(self._clients)}")
    
    async def push_update(self, data: Dict[str, Any]) -> None:
        """
        推送数据更新
        
        Args:
            data: 要推送的数据
        """
        message = {
            'type': 'update',
            'timestamp': datetime.now().isoformat(),
            'data': data,}
        await self._broadcast(message)
    
    async def push_alert(self, alert: Alert) -> None:
        """
        推送预警
        
        Args:
            alert: 预警对象
        """
        message = {
            'type': 'alert',
            'timestamp': datetime.now().isoformat(),
            'alert': alert.to_dict(),
        }
        await self._broadcast(message)
    
    async def push_stock_update(self, stock_code: str, stock_data: Dict[str, Any]) -> None:
        """
        推送单只股票更新
        
        Args:
            stock_code: 股票代码
            stock_data: 股票数据
        """
        message = {
            'type': 'stock_update',
            'timestamp': datetime.now().isoformat(),
            'stock_code': stock_code,
            'data': stock_data,
        }
        await self._broadcast(message)
    
    async def push_ranking(self, ranking_data: Dict[str, Any]) -> None:
        """
        推送排行榜更新
        
        Args:
            ranking_data: 排行榜数据
        """
        message = {
            'type': 'ranking',
            'timestamp': datetime.now().isoformat(),
            'data': ranking_data,
        }
        await self._broadcast(message)
    
    async def push_status(self, status: Dict[str, Any]) -> None:
        """
        推送系统状态
        
        Args:
            status: 状态信息
        """
        message = {
            'type': 'status',
            'timestamp': datetime.now().isoformat(),
            'data': status,
        }
        await self._broadcast(message)
    
    async def send_to_client(self, websocket: Any, message: Dict[str, Any]) -> bool:
        """
        向特定客户端发送消息
        
        Args:
            websocket: WebSocket连接对象
            message: 要发送的消息
            
        Returns:
            是否发送成功
        """
        try:
            message_str = json.dumps(message, ensure_ascii=False, default=str)
            
            # 适配不同的WebSocket库
            if hasattr(websocket, 'send'):
                # websockets 库
                await websocket.send(message_str)elif hasattr(websocket, 'send_text'):
                # FastAPI/Starlette WebSocket
                await websocket.send_text(message_str)
            elif hasattr(websocket, 'send_json'):
                # 某些框架支持直接发送JSON
                await websocket.send_json(message)
            else:
                logger.warning(f"Unsupported WebSocket type: {type(websocket)}")return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending to client: {e}")
            return False
    
    async def _broadcast(self, message: Dict[str, Any]) -> None:
        """
        广播消息给所有客户端
        
        Args:
            message: 要广播的消息
        """
        if not self._clients:
            logger.debug("No clients to broadcast to")
            return
        
        async with self._lock:
            clients = self._clients.copy()
        
        disconnected = set()
        
        for client in clients:
            success = await self.send_to_client(client, message)
            if not success:
                disconnected.add(client)
        
        # 移除断开的连接
        if disconnected:
            async with self._lock:
                self._clients -= disconnected
            logger.info(f"Removed {len(disconnected)} disconnected clients")
    
    async def _push_loop(self) -> None:
        """
        推送循环
        """
        logger.info("Push loop started")
        
        while self._is_running:
            try:
                # 从队列获取消息
                try:
                    message = await asyncio.wait_for(
                        self._message_queue.get(),
                        timeout=self._ping_interval
                    )
                await self._broadcast(message)
                except asyncio.TimeoutError:
                    # 发送心跳
                    await self._send_ping()
                except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in push loop: {e}", exc_info=True)
                await asyncio.sleep(1)
        
        logger.info("Push loop ended")
    
    async def _send_ping(self) -> None:
        """
        发送心跳
        """
        message = {
            'type': 'ping',
            'timestamp': datetime.now().isoformat(),
        }
        await self._broadcast(message)
    
    async def _close_all_connections(self) -> None:
        """
        关闭所有连接
        """
        async with self._lock:
            for client in self._clients:
                try:
                    if hasattr(client, 'close'):
                        await client.close()
                except Exception as e:
                    logger.error(f"Error closing client: {e}")
            self._clients.clear()
    
    def queue_message(self, message: Dict[str, Any]) -> None:
        """
        将消息加入队列
        
        Args:
            message: 要发送的消息
        """
        try:
            self._message_queue.put_nowait(message)
        except asyncio.QueueFull:
            logger.warning("Message queue is full, dropping message")
    
    def register_handler(self, message_type: str, handler: Callable) -> None:
        """
        注册消息处理器
        
        Args:
            message_type: 消息类型
            handler: 处理函数
        """
        self._message_handlers[message_type] = handler
        logger.info(f"Registered handler for message type: {message_type}")
    
    async def handle_message(self, websocket: Any, message: str) -> None:
        """
        处理客户端消息
        
        Args:
            websocket: WebSocket连接对象
            message: 接收到的消息
        """
        try:
            data = json.loads(message)
            message_type = data.get('type', 'unknown')
            
            if message_type in self._message_handlers:
                handler = self._message_handlers[message_type]
                await handler(websocket, data)
            elif message_type == 'pong':
                # 心跳响应
                logger.debug(f"Received pong from client")
            elif message_type == 'subscribe':
                # 订阅请求
                await self._handle_subscribe(websocket, data)
            elif message_type == 'unsubscribe':
                # 取消订阅
                await self._handle_unsubscribe(websocket, data)
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON message: {message}")
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
    
    async def _handle_subscribe(self, websocket: Any, data: Dict[str, Any]) -> None:
        """
        处理订阅请求
        
        Args:
            websocket: WebSocket连接对象
            data: 订阅数据
        """
        stocks = data.get('stocks', [])
        logger.info(f"Client subscribed to stocks: {stocks}")
        
        # 发送确认
        response = {
            'type': 'subscribe_ack',
            'timestamp': datetime.now().isoformat(),
            'stocks': stocks,
        }
        await self.send_to_client(websocket, response)
    
    async def _handle_unsubscribe(self, websocket: Any, data: Dict[str, Any]) -> None:
        """
        处理取消订阅请求
        
        Args:
            websocket: WebSocket连接对象
            data: 取消订阅数据
        """
        stocks = data.get('stocks', [])
        logger.info(f"Client unsubscribed from stocks: {stocks}")
        
        # 发送确认
        response = {
            'type': 'unsubscribe_ack',
            'timestamp': datetime.now().isoformat(),
            'stocks': stocks,
        }
        await self.send_to_client(websocket, response)
    @property
    def client_count(self) -> int:
        """
        获取当前客户端数量
        
        Returns:
            客户端数量
        """
        return len(self._clients)
    
    @property
    def is_running(self) -> bool:
        """
        获取运行状态
        
        Returns:
            是否运行中
        """
        return self._is_running
    def get_status(self) -> Dict[str, Any]:
        """
        获取推送器状态
        
        Returns:
            状态信息
        """
        return {
            'is_running': self._is_running,
            'client_count': len(self._clients),
            'queue_size': self._message_queue.qsize(),
            'ping_interval': self._ping_interval,
        }


class AuctionWebSocketHandler:
    """竞价WebSocket处理器
    
    用于集成FastAPI/Starlette等Web框架
    """
    
    def __init__(self, pusher: AuctionWebSocketPusher):
        """
        初始化处理器
        
        Args:
            pusher: WebSocket推送器实例
        """
        self._pusher = pusher
    async def handle_connection(self, websocket: Any) -> None:
        """
        处理WebSocket连接
        
        Args:
            websocket: WebSocket连接对象
        """
        await self._pusher.register_client(websocket)
        
        try:
            # 发送欢迎消息
            welcome = {
                'type': 'welcome',
                'timestamp': datetime.now().isoformat(),
                'message': '连接成功，开始接收竞价数据推送',
            }
            await self._pusher.send_to_client(websocket, welcome)
            
            # 接收消息循环
            while True:
                try:
                    # 适配不同的WebSocket库
                    if hasattr(websocket, 'recv'):
                        message = await websocket.recv()
                    elif hasattr(websocket, 'receive_text'):
                        message = await websocket.receive_text()
                    else:
                        break    await self._pusher.handle_message(websocket, message)
                    
                except Exception as e:
                    logger.error(f"Error receiving message: {e}")
                    break
                    
        finally:
            await self._pusher.unregister_client(websocket)
    
    def get_pusher(self) -> AuctionWebSocketPusher:
        """
        获取推送器实例
        
        Returns:
            推送器实例
        """
        return self._pusher