"""
WebSocket实时数据推送
"""
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set, Any, List, Optional
import asyncio
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        # 活跃连接
        self.active_connections: Set[WebSocket] = set()
        # 订阅关系：股票代码 -> WebSocket集合
        self.subscriptions: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket):
        """接受新连接"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"新连接建立，当前连接数: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """断开连接"""
        self.active_connections.discard(websocket)

        # 清理订阅
        for stock_code in list(self.subscriptions.keys()):
            self.subscriptions[stock_code].discard(websocket)
            if not self.subscriptions[stock_code]:
                del self.subscriptions[stock_code]

        logger.info(f"连接断开，当前连接数: {len(self.active_connections)}")

    def subscribe(self, websocket: WebSocket, stock_code: str):
        """订阅股票"""
        if stock_code not in self.subscriptions:
            self.subscriptions[stock_code] = set()
        self.subscriptions[stock_code].add(websocket)
        logger.info(f"订阅股票: {stock_code}")

    def unsubscribe(self, websocket: WebSocket, stock_code: str):
        """取消订阅"""
        if stock_code in self.subscriptions:
            self.subscriptions[stock_code].discard(websocket)
            if not self.subscriptions[stock_code]:
                del self.subscriptions[stock_code]
        logger.info(f"取消订阅: {stock_code}")

    def get_subscribed_stocks(self) -> List[str]:
        """获取所有被订阅的股票"""
        return list(self.subscriptions.keys())

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """发送个人消息"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"发送消息失败: {e}")

    async def broadcast(self, message: dict):
        """广播消息给所有连接"""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"广播失败: {e}")
                disconnected.add(connection)

        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)

    async def send_to_subscribers(self, stock_code: str, message: dict):
        """发送消息给特定股票的订阅者"""
        if stock_code not in self.subscriptions:
            return

        disconnected = set()
        for connection in self.subscriptions[stock_code]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"推送失败: {e}")
                disconnected.add(connection)

        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)


class RealtimeDataPusher:
    """实时数据推送器"""

    def __init__(self, manager: ConnectionManager, data_source=None):
        self.manager = manager
        self.is_running = False
        self.data_source = data_source
        self.push_interval = 1  # 推送间隔（秒）

    def set_data_source(self, data_source):
        """设置数据源"""
        self.data_source = data_source

    async def start(self):
        """启动推送"""
        self.is_running = True
        asyncio.create_task(self._push_loop())
        logger.info("实时数据推送已启动")

    async def stop(self):
        """停止推送"""
        self.is_running = False
        logger.info("实时数据推送已停止")

    async def _push_loop(self):
        """推送循环"""
        while self.is_running:
            try:
                # 获取订阅的股票列表
                stock_codes = self.manager.get_subscribed_stocks()
                if not stock_codes:
                    await asyncio.sleep(self.push_interval)
                    continue

                # 获取实时数据
                data = await self._fetch_realtime_data(stock_codes)

                # 推送给订阅者
                for stock_code, quote in data.items():
                    await self.push_quote(stock_code, quote)

                await asyncio.sleep(self.push_interval)

            except Exception as e:
                logger.error(f"推送循环错误: {e}")
                await asyncio.sleep(5)

    async def _fetch_realtime_data(self, stock_codes: List[str]) -> Dict[str, Any]:
        """获取实时数据"""
        if not self.data_source:
            return {}
        
        try:
            # 使用线程池执行同步的数据源调用
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self.data_source.get_batch_quotes,
                stock_codes
            )
            return result or {}
        except Exception as e:
            logger.error(f"获取实时数据失败: {e}")
            return {}

    async def push_quote(self, stock_code: str, quote: Dict[str, Any]):
        """推送行情数据"""
        # 格式化盘口数据
        order_book = self._extract_order_book(quote)
        
        message = {
            'type': 'quote',
            'stock_code': stock_code,
            'data': {
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
                'pre_close': quote.get('pre_close', 0),
            },
            'timestamp': quote.get('timestamp', '')
        }
        await self.manager.send_to_subscribers(stock_code, message)
        
        # 同时推送盘口数据
        if order_book:
            await self.push_order_book(stock_code, order_book)

    def _extract_order_book(self, quote: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
                return {
                    'asks': asks,
                    'bids': bids,
                    'timestamp': quote.get('timestamp', '')
                }
        except Exception:
            pass
        return None

    async def push_trade(self, stock_code: str, trade: Dict[str, Any]):
        """推送成交数据"""
        message = {
            'type': 'trade',
            'stock_code': stock_code,
            'data': trade,
            'timestamp': trade.get('timestamp', '')
        }
        await self.manager.send_to_subscribers(stock_code, message)

    async def push_order_book(self, stock_code: str, order_book: Dict[str, Any]):
        """推送盘口数据"""
        message = {
            'type': 'orderbook',
            'stock_code': stock_code,
            'data': order_book,
            'timestamp': order_book.get('timestamp', '')
        }
        await self.manager.send_to_subscribers(stock_code, message)

    async def push_alert(self, alert: Dict[str, Any]):
        """推送预警消息"""
        message = {
            'type': 'alert',
            'data': alert
        }
        await self.manager.broadcast(message)