"""
订阅管理器
管理WebSocket客户端的股票订阅
"""
from typing import Dict, Set, List, Optional
from collections import defaultdict
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class SubscriptionManager:
    """
    订阅管理器

    功能：
    1. 管理客户端订阅关系
    2. 跟踪订阅的股票列表
    3. 优化数据推送
    """

    def __init__(self):
        # 客户端ID -> 订阅的股票代码集合
        self.client_subscriptions: Dict[str, Set[str]] = defaultdict(set)

        # 股票代码 -> 订阅该股票的客户端ID集合
        self.stock_subscribers: Dict[str, Set[str]] = defaultdict(set)

        # 客户端元数据
        self.client_metadata: Dict[str, Dict] = {}

    def subscribe(self, client_id: str, stock_codes: List[str]) -> Dict:
        """
        订阅股票

        Args:
            client_id: 客户端ID
            stock_codes: 股票代码列表

        Returns:
            订阅结果
        """
        added_codes = []
        existing_codes = []

        for code in stock_codes:
            if code not in self.client_subscriptions[client_id]:
                # 新订阅
                self.client_subscriptions[client_id].add(code)
                self.stock_subscribers[code].add(client_id)
                added_codes.append(code)
            else:
                # 已订阅
                existing_codes.append(code)

        # 更新元数据
        if client_id not in self.client_metadata:
            self.client_metadata[client_id] = {
                'connected_at': datetime.now(),
                'last_activity': datetime.now()
            }
        else:
            self.client_metadata[client_id]['last_activity'] = datetime.now()

        logger.info(
            f"客户端 {client_id} 订阅: "
            f"新增{len(added_codes)}个, 已存在{len(existing_codes)}个"
        )

        return {
            'success': True,
            'added': added_codes,
            'existing': existing_codes,
            'total_subscriptions': len(self.client_subscriptions[client_id])
        }

    def unsubscribe(self, client_id: str, stock_codes: List[str]) -> Dict:
        """
        取消订阅股票

        Args:
            client_id: 客户端ID
            stock_codes: 股票代码列表

        Returns:
            取消订阅结果
        """
        removed_codes = []
        not_found_codes = []

        for code in stock_codes:
            if code in self.client_subscriptions[client_id]:
                # 移除订阅
                self.client_subscriptions[client_id].discard(code)
                self.stock_subscribers[code].discard(client_id)

                # 如果没有客户端订阅该股票，清理记录
                if not self.stock_subscribers[code]:
                    del self.stock_subscribers[code]

                removed_codes.append(code)
            else:
                not_found_codes.append(code)

        logger.info(
            f"客户端 {client_id} 取消订阅: "
            f"移除{len(removed_codes)}个, 未找到{len(not_found_codes)}个"
        )

        return {
            'success': True,
            'removed': removed_codes,
            'not_found': not_found_codes,
            'remaining_subscriptions': len(self.client_subscriptions[client_id])
        }

    def unsubscribe_all(self, client_id: str) -> Dict:
        """
        取消客户端的所有订阅

        Args:
            client_id: 客户端ID

        Returns:
            取消订阅结果
        """
        if client_id not in self.client_subscriptions:
            return {'success': True, 'removed_count': 0}

        # 获取该客户端订阅的所有股票
        subscribed_codes = list(self.client_subscriptions[client_id])

        # 从股票订阅者列表中移除该客户端
        for code in subscribed_codes:
            self.stock_subscribers[code].discard(client_id)
            if not self.stock_subscribers[code]:
                del self.stock_subscribers[code]

        # 清空客户端订阅
        removed_count = len(self.client_subscriptions[client_id])
        del self.client_subscriptions[client_id]

        # 清理元数据
        if client_id in self.client_metadata:
            del self.client_metadata[client_id]

        logger.info(f"客户端 {client_id} 取消所有订阅: {removed_count}个")

        return {
            'success': True,
            'removed_count': removed_count
        }

    def get_client_subscriptions(self, client_id: str) -> List[str]:
        """
        获取客户端订阅的股票列表

        Args:
            client_id: 客户端ID

        Returns:
            股票代码列表
        """
        return list(self.client_subscriptions.get(client_id, set()))

    def get_stock_subscribers(self, stock_code: str) -> List[str]:
        """
        获取订阅某股票的客户端列表

        Args:
            stock_code: 股票代码

        Returns:
            客户端ID列表
        """
        return list(self.stock_subscribers.get(stock_code, set()))

    def get_all_subscribed_stocks(self) -> List[str]:
        """
        获取所有被订阅的股票列表

        Returns:
            股票代码列表
        """
        return list(self.stock_subscribers.keys())

    def get_client_count(self) -> int:
        """获取客户端数量"""
        return len(self.client_subscriptions)

    def get_subscription_count(self) -> int:
        """获取订阅总数"""
        return sum(len(subs) for subs in self.client_subscriptions.values())

    def get_stats(self) -> Dict:
        """
        获取统计信息

        Returns:
            统计数据
        """
        return {
            'total_clients': self.get_client_count(),
            'total_subscriptions': self.get_subscription_count(),
            'total_stocks': len(self.stock_subscribers),
            'avg_subscriptions_per_client': (
                self.get_subscription_count() / max(self.get_client_count(), 1)
            ),
            'avg_subscribers_per_stock': (
                sum(len(subs) for subs in self.stock_subscribers.values()) /
                max(len(self.stock_subscribers), 1)
            )
        }

    def get_top_subscribed_stocks(self, limit: int = 10) -> List[tuple]:
        """
        获取订阅最多的股票

        Args:
            limit: 返回数量

        Returns:
            [(stock_code, subscriber_count), ...]
        """
        stock_counts = [
            (code, len(subscribers))
            for code, subscribers in self.stock_subscribers.items()
        ]
        stock_counts.sort(key=lambda x: x[1], reverse=True)
        return stock_counts[:limit]

    def cleanup_inactive_clients(self, timeout_seconds: int = 300):
        """
        清理不活跃的客户端

        Args:
            timeout_seconds: 超时时间（秒）
        """
        now = datetime.now()
        inactive_clients = []

        for client_id, metadata in self.client_metadata.items():
            last_activity = metadata.get('last_activity')
            if last_activity:
                inactive_duration = (now - last_activity).total_seconds()
                if inactive_duration > timeout_seconds:
                    inactive_clients.append(client_id)

        # 清理不活跃客户端
        for client_id in inactive_clients:
            self.unsubscribe_all(client_id)
            logger.info(f"清理不活跃客户端: {client_id}")

        return len(inactive_clients)
