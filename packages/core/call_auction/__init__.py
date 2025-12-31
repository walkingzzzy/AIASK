"""
集合竞价分析模块
提供竞价数据获取、异动识别、排行榜、实时监控、预警等功能

主要组件：
- CallAuctionAnalyzer: 集合竞价分析器
- AuctionMonitor: 竞价时段实时监控器
- MonitorReporter: 监控报告生成器
- AuctionWebSocketPusher: WebSocket推送器
- Alert: 预警信息数据类
- AlertRule: 预警规则基类
- 多种预警规则实现
"""

# 分析器
from .auction_analyzer import CallAuctionAnalyzer, AuctionStock

# 监控器
from .auction_monitor import AuctionMonitor

# 报告生成器
from .monitor_reporter import MonitorReporter

# WebSocket推送
from .websocket_pusher import AuctionWebSocketPusher, AuctionWebSocketHandler

# 数据模型
from .models import Alert

# 预警规则
from .alert_rules import (
    AlertRule,HighOpenRule,
    LowOpenRule,
    VolumeAnomalyRule,
    LimitUpExpectedRule,
    LimitDownExpectedRule,
    BigOrderRule,
    PriceVolatilityRule,
)

__all__ = [
    # 分析器
    'CallAuctionAnalyzer',
    'AuctionStock',
    
    # 监控器
    'AuctionMonitor',
    
    # 报告生成器
    'MonitorReporter',
    
    # WebSocket推送
    'AuctionWebSocketPusher',
    'AuctionWebSocketHandler',
    
    # 数据模型
    'Alert',
    
    # 预警规则
    'AlertRule',
    'HighOpenRule',
    'LowOpenRule',
    'VolumeAnomalyRule',
    'LimitUpExpectedRule',
    'LimitDownExpectedRule',
    'BigOrderRule',
    'PriceVolatilityRule',
]
