"""
实时数据推送路由
提供WebSocket实时数据推送和AI推送功能
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from typing import Dict, Set, List, Any, Optional
import asyncio
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["实时数据"])

# 配置常量
MAX_CONNECTIONS = 100  # 最大连接数
MAX_SUBSCRIPTIONS_PER_CLIENT = 50  # 每个客户端最大订阅数
HEARTBEAT_INTERVAL = 30  # 心跳间隔（秒）


# ==================== 连接管理器 ====================

class EnhancedConnectionManager:
    """增强的WebSocket连接管理器"""
    
    def __init__(self, max_connections: int = MAX_CONNECTIONS):
        self.max_connections = max_connections
        # 活跃连接
        self.active_connections: Set[WebSocket] = set()
        # 股票订阅映射 {stock_code: set(websocket)}
        self.stock_subscriptions: Dict[str, Set[WebSocket]] = {}
        # 用户订阅映射 {user_id: websocket}
        self.user_connections: Dict[str, WebSocket] = {}
        # AI推送订阅
        self.ai_push_subscribers: Set[WebSocket] = set()
        # 客户端订阅计数 {websocket: count}
        self.client_subscription_count: Dict[WebSocket, int] = {}
    
    async def connect(self, websocket: WebSocket, user_id: Optional[str] = None) -> bool:
        """建立连接，返回是否成功"""
        # 检查连接数限制
        if len(self.active_connections) >= self.max_connections:
            logger.warning(f"连接数已达上限 ({self.max_connections})，拒绝新连接")
            await websocket.close(code=1013, reason="服务器连接数已满")
            return False
        
        await websocket.accept()
        self.active_connections.add(websocket)
        self.client_subscription_count[websocket] = 0
        
        if user_id:
            # 如果用户已有连接，关闭旧连接
            if user_id in self.user_connections:
                old_ws = self.user_connections[user_id]
                await self._close_connection(old_ws, "新连接替换")
            self.user_connections[user_id] = websocket
        
        logger.info(f"新连接建立，当前连接数: {len(self.active_connections)}")
        return True
    
    async def _close_connection(self, websocket: WebSocket, reason: str = ""):
        """关闭单个连接"""
        try:
            await websocket.close(code=1000, reason=reason)
        except Exception:
            pass
        self.disconnect(websocket)
    
    def disconnect(self, websocket: WebSocket):
        """断开连接"""
        self.active_connections.discard(websocket)
        self.ai_push_subscribers.discard(websocket)
        self.client_subscription_count.pop(websocket, None)
        
        # 清理股票订阅
        for stock_code in list(self.stock_subscriptions.keys()):
            self.stock_subscriptions[stock_code].discard(websocket)
            if not self.stock_subscriptions[stock_code]:
                del self.stock_subscriptions[stock_code]
        
        # 清理用户连接
        for user_id, ws in list(self.user_connections.items()):
            if ws == websocket:
                del self.user_connections[user_id]
        
        logger.info(f"连接断开，当前连接数: {len(self.active_connections)}")
    
    def subscribe_stock(self, websocket: WebSocket, stock_code: str) -> bool:
        """订阅股票，返回是否成功"""
        # 检查订阅数限制
        current_count = self.client_subscription_count.get(websocket, 0)
        if current_count >= MAX_SUBSCRIPTIONS_PER_CLIENT:
            logger.warning(f"客户端订阅数已达上限 ({MAX_SUBSCRIPTIONS_PER_CLIENT})")
            return False
        
        if stock_code not in self.stock_subscriptions:
            self.stock_subscriptions[stock_code] = set()
        
        if websocket not in self.stock_subscriptions[stock_code]:
            self.stock_subscriptions[stock_code].add(websocket)
            self.client_subscription_count[websocket] = current_count + 1
        
        return True
    
    def unsubscribe_stock(self, websocket: WebSocket, stock_code: str):
        """取消订阅股票"""
        if stock_code in self.stock_subscriptions:
            if websocket in self.stock_subscriptions[stock_code]:
                self.stock_subscriptions[stock_code].discard(websocket)
                current_count = self.client_subscription_count.get(websocket, 1)
                self.client_subscription_count[websocket] = max(0, current_count - 1)
    
    def subscribe_ai_push(self, websocket: WebSocket):
        """订阅AI推送"""
        self.ai_push_subscribers.add(websocket)
    
    def unsubscribe_ai_push(self, websocket: WebSocket):
        """取消订阅AI推送"""
        self.ai_push_subscribers.discard(websocket)
    
    async def send_personal(self, websocket: WebSocket, message: dict):
        """发送个人消息"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            print(f"Failed to send personal message: {e}")
    
    async def broadcast_stock(self, stock_code: str, message: dict):
        """广播股票数据"""
        if stock_code in self.stock_subscriptions:
            for websocket in self.stock_subscriptions[stock_code]:
                try:
                    await websocket.send_json(message)
                except Exception:
                    pass
    
    async def broadcast_ai_push(self, message: dict):
        """广播AI推送"""
        for websocket in self.ai_push_subscribers:
            try:
                await websocket.send_json(message)
            except Exception:
                pass
    
    async def broadcast_all(self, message: dict):
        """广播给所有连接"""
        for websocket in self.active_connections:
            try:
                await websocket.send_json(message)
            except Exception:
                pass
    
    def get_subscribed_stocks(self) -> List[str]:
        """获取所有被订阅的股票"""
        return list(self.stock_subscriptions.keys())
    
    def get_connection_count(self) -> int:
        """获取连接数"""
        return len(self.active_connections)


# 全局连接管理器
manager = EnhancedConnectionManager()

# 数据源管理器（延迟初始化）
_data_source_manager = None

def get_data_source_manager():
    """获取数据源管理器"""
    global _data_source_manager
    if _data_source_manager is None:
        try:
            from packages.core.realtime.data_source import DataSourceManager
            _data_source_manager = DataSourceManager()
        except Exception as e:
            logger.error(f"初始化数据源管理器失败: {e}")
    return _data_source_manager


# ==================== WebSocket端点 ====================

@router.websocket("/ws/realtime")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: Optional[str] = Query(None)
):
    """
    实时数据WebSocket端点
    
    支持的消息类型：
    - subscribe: 订阅股票 {action: 'subscribe', stock_code: 'xxx'}
    - subscribe_batch: 批量订阅 {action: 'subscribe_batch', stock_codes: ['xxx', 'yyy']}
    - unsubscribe: 取消订阅 {action: 'unsubscribe', stock_code: 'xxx'}
    - unsubscribe_all: 取消所有订阅 {action: 'unsubscribe_all'}
    - subscribe_ai: 订阅AI推送 {action: 'subscribe_ai'}
    - unsubscribe_ai: 取消AI推送 {action: 'unsubscribe_ai'}
    - ping: 心跳 {action: 'ping'}
    """
    # 尝试建立连接
    connected = await manager.connect(websocket, user_id)
    if not connected:
        return
    
    try:
        # 发送连接成功消息
        await manager.send_personal(websocket, {
            'type': 'connected',
            'message': '连接成功',
            'timestamp': datetime.now().isoformat(),
            'limits': {
                'max_subscriptions': MAX_SUBSCRIPTIONS_PER_CLIENT
            }
        })
        
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=HEARTBEAT_INTERVAL * 2
                )
            except asyncio.TimeoutError:
                # 发送心跳检测
                try:
                    await manager.send_personal(websocket, {
                        'type': 'heartbeat',
                        'timestamp': datetime.now().isoformat()
                    })
                except Exception:
                    break
                continue
            
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await manager.send_personal(websocket, {
                    'type': 'error',
                    'message': '无效的JSON格式'
                })
                continue
            
            action = message.get('action')
            stock_code = message.get('stock_code')
            stock_codes = message.get('stock_codes', [])
            
            if action == 'subscribe' and stock_code:
                success = manager.subscribe_stock(websocket, stock_code)
                await manager.send_personal(websocket, {
                    'type': 'subscribed' if success else 'error',
                    'stock_code': stock_code,
                    'message': None if success else '订阅数已达上限'
                })
            
            elif action == 'subscribe_batch' and stock_codes:
                # 批量订阅
                results = {'success': [], 'failed': []}
                for code in stock_codes[:MAX_SUBSCRIPTIONS_PER_CLIENT]:
                    if manager.subscribe_stock(websocket, code):
                        results['success'].append(code)
                    else:
                        results['failed'].append(code)
                await manager.send_personal(websocket, {
                    'type': 'subscribed_batch',
                    'data': results
                })
                
            elif action == 'unsubscribe' and stock_code:
                manager.unsubscribe_stock(websocket, stock_code)
                await manager.send_personal(websocket, {
                    'type': 'unsubscribed',
                    'stock_code': stock_code
                })
            
            elif action == 'unsubscribe_all':
                # 取消所有订阅
                for code in list(manager.stock_subscriptions.keys()):
                    manager.unsubscribe_stock(websocket, code)
                await manager.send_personal(websocket, {
                    'type': 'unsubscribed_all'
                })
                
            elif action == 'subscribe_ai':
                manager.subscribe_ai_push(websocket)
                await manager.send_personal(websocket, {
                    'type': 'ai_subscribed'
                })
                
            elif action == 'unsubscribe_ai':
                manager.unsubscribe_ai_push(websocket)
                await manager.send_personal(websocket, {
                    'type': 'ai_unsubscribed'
                })
                
            elif action == 'ping':
                await manager.send_personal(websocket, {
                    'type': 'pong',
                    'timestamp': datetime.now().isoformat()
                })
            
            else:
                await manager.send_personal(websocket, {
                    'type': 'error',
                    'message': f'未知操作: {action}'
                })
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# ==================== 推送API ====================

@router.post("/push/quote")
async def push_quote(stock_code: str, data: dict):
    """
    推送行情数据（供内部调用）
    """
    message = {
        'type': 'quote',
        'stock_code': stock_code,
        'data': data,
        'timestamp': datetime.now().isoformat()
    }
    await manager.broadcast_stock(stock_code, message)
    return {"success": True}


@router.post("/push/orderbook")
async def push_orderbook(stock_code: str, data: dict):
    """
    推送盘口数据（供内部调用）
    """
    message = {
        'type': 'orderbook',
        'stock_code': stock_code,
        'data': data,
        'timestamp': datetime.now().isoformat()
    }
    await manager.broadcast_stock(stock_code, message)
    return {"success": True}


@router.post("/push/trade")
async def push_trade(stock_code: str, data: dict):
    """
    推送成交明细（供内部调用）
    """
    message = {
        'type': 'trade',
        'stock_code': stock_code,
        'data': data,
        'timestamp': datetime.now().isoformat()
    }
    await manager.broadcast_stock(stock_code, message)
    return {"success": True}


@router.post("/push/ai")
async def push_ai_message(
    push_type: str,
    title: str,
    content: str,
    stock_code: Optional[str] = None,
    stock_name: Optional[str] = None,
    priority: str = "medium"
):
    """
    推送AI消息（供内部调用）
    """
    message = {
        'type': 'ai_push',
        'data': {
            'type': push_type,
            'title': title,
            'content': content,
            'stock_code': stock_code,
            'stock_name': stock_name,
            'priority': priority,
            'timestamp': datetime.now().isoformat()
        }
    }
    await manager.broadcast_ai_push(message)
    return {"success": True}


@router.get("/status")
async def get_realtime_status():
    """
    获取实时服务状态
    """
    return {
        "success": True,
        "data": {
            "connections": manager.get_connection_count(),
            "subscribed_stocks": manager.get_subscribed_stocks(),
            "ai_subscribers": len(manager.ai_push_subscribers)
        }
    }


# ==================== 实时数据推送 ====================

_push_task = None

async def realtime_quote_push():
    """实时行情推送"""
    data_source = get_data_source_manager()
    
    while True:
        try:
            stocks = manager.get_subscribed_stocks()
            if not stocks:
                await asyncio.sleep(1)
                continue
            
            # 获取实时数据
            if data_source:
                quotes = data_source.get_batch_quotes(stocks)
            else:
                quotes = {}
            
            for stock_code, quote in quotes.items():
                # 格式化行情数据
                data = {
                    'stock_code': stock_code,
                    'stock_name': quote.get('name', ''),
                    'price': quote.get('current', 0),
                    'change': quote.get('change', 0),
                    'change_percent': quote.get('change_pct', 0),
                    'volume': quote.get('volume', 0),
                    'amount': quote.get('amount', 0),
                    'high': quote.get('high', 0),
                    'low': quote.get('low', 0),
                    'open': quote.get('open', 0),
                    'pre_close': quote.get('pre_close', 0)
                }
                
                # 推送行情
                message = {
                    'type': 'quote',
                    'stock_code': stock_code,
                    'data': data,
                    'timestamp': datetime.now().isoformat()
                }
                await manager.broadcast_stock(stock_code, message)
                
                # 推送盘口数据
                order_book = _extract_order_book(quote)
                if order_book:
                    await manager.broadcast_stock(stock_code, {
                        'type': 'orderbook',
                        'stock_code': stock_code,
                        'data': order_book,
                        'timestamp': datetime.now().isoformat()
                    })
            
            await asyncio.sleep(1)  # 每秒推送一次
            
        except Exception as e:
            logger.error(f"实时推送错误: {e}")
            await asyncio.sleep(5)


def _extract_order_book(quote: dict) -> Optional[dict]:
    """从行情数据中提取盘口数据"""
    try:
        asks = []
        bids = []
        for i in range(1, 6):
            ask_price = quote.get(f'ask{i}_price', 0)
            ask_vol = quote.get(f'ask{i}_volume', 0)
            bid_price = quote.get(f'bid{i}_price', 0)
            bid_vol = quote.get(f'bid{i}_volume', 0)
            if ask_price > 0:
                asks.append({'price': ask_price, 'volume': ask_vol})
            if bid_price > 0:
                bids.append({'price': bid_price, 'volume': bid_vol})
        
        if asks or bids:
            return {'asks': asks, 'bids': bids}
    except Exception:
        pass
    return None


def start_realtime_push():
    """启动实时数据推送"""
    global _push_task
    if _push_task is None or _push_task.done():
        _push_task = asyncio.create_task(realtime_quote_push())
        logger.info("实时数据推送已启动")


def stop_realtime_push():
    """停止实时数据推送"""
    global _push_task
    if _push_task and not _push_task.done():
        _push_task.cancel()
        _push_task = None
        logger.info("实时数据推送已停止")
