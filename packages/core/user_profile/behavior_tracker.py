"""
行为追踪器
追踪和记录用户行为，为偏好学习提供数据
"""
import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from collections import OrderedDict

from .models import (
    BehaviorEvent, BehaviorType, QueryHistoryItem,
    DecisionHistoryItem, UserProfile
)
from .profile_service import ProfileService

logger = logging.getLogger(__name__)

# 常量定义
MAX_TOTAL_CACHE_SIZE = 10000  # 总缓存事件数上限
MAX_USER_BUFFER_SIZE = 100  # 每个用户缓存的事件数


class BehaviorTracker:
    """
    行为追踪器
    
    功能：
    1. 记录用户行为事件
    2. 分析行为模式
    3. 提取行为特征
    """
    
    def __init__(self, profile_service: ProfileService = None):
        """
        初始化行为追踪器
        
        Args:
            profile_service: 用户画像服务
        """
        self.profile_service = profile_service or ProfileService()
        self._event_buffer: Dict[str, List[BehaviorEvent]] = OrderedDict()
        self._total_event_count = 0  # 总事件计数
    
    def track(self, user_id: str, event_type: BehaviorType,
              data: Dict[str, Any] = None, **kwargs) -> BehaviorEvent:
        """
        追踪行为事件
        
        Args:
            user_id: 用户ID
            event_type: 事件类型
            data: 事件数据
            **kwargs: 其他参数（stock_code, stock_name, page等）
            
        Returns:
            行为事件
        """
        event = BehaviorEvent(
            id=str(uuid.uuid4()),
            user_id=user_id,
            type=event_type,
            timestamp=datetime.now(),
            data=data or {},
            stock_code=kwargs.get('stock_code'),
            stock_name=kwargs.get('stock_name'),
            page=kwargs.get('page'),
            session_id=kwargs.get('session_id')
        )
        
        # 初始化用户缓存
        if user_id not in self._event_buffer:
            self._event_buffer[user_id] = []
        
        # 添加到缓存
        self._event_buffer[user_id].append(event)
        self._total_event_count += 1
        
        # 限制单用户缓存大小
        if len(self._event_buffer[user_id]) > MAX_USER_BUFFER_SIZE:
            removed = len(self._event_buffer[user_id]) - MAX_USER_BUFFER_SIZE
            self._event_buffer[user_id] = self._event_buffer[user_id][-MAX_USER_BUFFER_SIZE:]
            self._total_event_count -= removed
        
        # 限制总缓存大小（LRU策略：移除最早用户的事件）
        while self._total_event_count > MAX_TOTAL_CACHE_SIZE and self._event_buffer:
            oldest_user = next(iter(self._event_buffer))
            removed = len(self._event_buffer[oldest_user])
            del self._event_buffer[oldest_user]
            self._total_event_count -= removed
            # 将当前用户移到末尾（最近访问）
            if user_id in self._event_buffer:
                self._event_buffer.move_to_end(user_id)
        
        # 更新用户画像
        self._update_profile_from_event(user_id, event)
        
        logger.debug(f"追踪行为: {user_id} - {event_type.value}")
        return event
    
    def track_query(self, user_id: str, query: str, intent: str,
                    stock_codes: List[str] = None, success: bool = True) -> BehaviorEvent:
        """追踪查询行为"""
        # 记录到查询历史
        profile = self.profile_service.get_profile(user_id)
        profile.query_history.append(QueryHistoryItem(
            query=query,
            intent=intent,
            timestamp=datetime.now(),
            stock_codes=stock_codes or [],
            success=success
        ))
        
        # 限制历史记录数量
        if len(profile.query_history) > 100:
            profile.query_history = profile.query_history[-100:]
        
        profile.usage_stats.total_queries += 1
        self.profile_service.save_profile(profile)
        
        return self.track(
            user_id=user_id,
            event_type=BehaviorType.QUERY,
            data={'query': query, 'intent': intent, 'success': success},
            stock_code=stock_codes[0] if stock_codes else None
        )
    
    def track_stock_view(self, user_id: str, stock_code: str, 
                         stock_name: str, duration_seconds: int = 0) -> BehaviorEvent:
        """追踪股票查看行为"""
        return self.track(
            user_id=user_id,
            event_type=BehaviorType.STOCK_VIEW,
            data={'duration_seconds': duration_seconds},
            stock_code=stock_code,
            stock_name=stock_name
        )
    
    def track_stock_add(self, user_id: str, stock_code: str, 
                        stock_name: str, group: str = "default") -> BehaviorEvent:
        """追踪添加自选股行为"""
        return self.track(
            user_id=user_id,
            event_type=BehaviorType.STOCK_ADD,
            data={'group': group},
            stock_code=stock_code,
            stock_name=stock_name
        )
    
    def track_ai_feedback(self, user_id: str, feedback_type: str,
                          is_positive: bool, context: Dict = None) -> BehaviorEvent:
        """追踪AI反馈"""
        # 更新AI关系
        self.profile_service.update_ai_relationship(
            user_id=user_id,
            feedback_positive=is_positive
        )
        
        return self.track(
            user_id=user_id,
            event_type=BehaviorType.AI_FEEDBACK,
            data={
                'feedback_type': feedback_type,
                'is_positive': is_positive,
                'context': context or {}
            }
        )
    
    def track_opportunity_click(self, user_id: str, opportunity_id: str,
                                 stock_code: str, opportunity_type: str) -> BehaviorEvent:
        """追踪机会点击"""
        return self.track(
            user_id=user_id,
            event_type=BehaviorType.OPPORTUNITY_CLICK,
            data={'opportunity_id': opportunity_id, 'type': opportunity_type},
            stock_code=stock_code
        )
    
    def track_decision(self, user_id: str, stock_code: str, stock_name: str,
                       action: str, reason: str, price: float,
                       ai_suggested: bool = False) -> BehaviorEvent:
        """追踪交易决策"""
        profile = self.profile_service.get_profile(user_id)
        profile.decision_history.append(DecisionHistoryItem(
            stock_code=stock_code,
            stock_name=stock_name,
            action=action,
            reason=reason,
            price_at_decision=price,
            timestamp=datetime.now(),
            ai_suggested=ai_suggested
        ))
        
        if len(profile.decision_history) > 100:
            profile.decision_history = profile.decision_history[-100:]
        
        # 如果是AI建议的决策，更新采纳率
        if ai_suggested:
            self.profile_service.update_ai_relationship(
                user_id=user_id,
                followed_suggestion=True
            )
        
        self.profile_service.save_profile(profile)
        
        return self.track(
            user_id=user_id,
            event_type=BehaviorType.TRADE_DECISION,
            data={'action': action, 'reason': reason, 'price': price, 'ai_suggested': ai_suggested},
            stock_code=stock_code,
            stock_name=stock_name
        )
    
    def get_recent_events(self, user_id: str, 
                          event_type: BehaviorType = None,
                          hours: int = 24) -> List[BehaviorEvent]:
        """
        获取最近的行为事件
        
        Args:
            user_id: 用户ID
            event_type: 事件类型（可选）
            hours: 时间范围（小时）
            
        Returns:
            事件列表
        """
        cutoff = datetime.now() - timedelta(hours=hours)
        events = self._event_buffer.get(user_id, [])
        
        filtered = [e for e in events if e.timestamp >= cutoff]
        
        if event_type:
            filtered = [e for e in filtered if e.type == event_type]
        
        return filtered
    
    def get_behavior_summary(self, user_id: str, days: int = 7) -> Dict[str, Any]:
        """
        获取行为摘要
        
        Args:
            user_id: 用户ID
            days: 统计天数
            
        Returns:
            行为摘要
        """
        events = self.get_recent_events(user_id, hours=days * 24)
        
        # 统计各类事件
        event_counts = defaultdict(int)
        stock_views = defaultdict(int)
        query_intents = defaultdict(int)
        active_hours = defaultdict(int)
        
        for event in events:
            event_counts[event.type.value] += 1
            active_hours[event.timestamp.hour] += 1
            
            if event.type == BehaviorType.STOCK_VIEW and event.stock_code:
                stock_views[event.stock_code] += 1
            
            if event.type == BehaviorType.QUERY:
                intent = event.data.get('intent', 'unknown')
                query_intents[intent] += 1
        
        # 找出最活跃的时段
        top_hours = sorted(active_hours.items(), key=lambda x: x[1], reverse=True)[:3]
        
        # 找出最关注的股票
        top_stocks = sorted(stock_views.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'total_events': len(events),
            'event_counts': dict(event_counts),
            'top_viewed_stocks': [{'code': k, 'views': v} for k, v in top_stocks],
            'top_query_intents': dict(query_intents),
            'active_hours': [h for h, _ in top_hours],
            'period_days': days
        }
    
    def _update_profile_from_event(self, user_id: str, event: BehaviorEvent):
        """根据事件更新用户画像"""
        profile = self.profile_service.get_profile(user_id)
        
        # 更新活跃时段
        hour = event.timestamp.hour
        if hour not in profile.usage_stats.active_hours:
            profile.usage_stats.active_hours.append(hour)
            # 只保留最常用的时段
            if len(profile.usage_stats.active_hours) > 10:
                profile.usage_stats.active_hours = profile.usage_stats.active_hours[-10:]
        
        # 记录每日活跃
        self.profile_service.record_daily_active(user_id)
