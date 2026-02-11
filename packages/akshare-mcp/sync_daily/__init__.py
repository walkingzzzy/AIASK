"""
sync_daily — 日常增量同步包

原 sync_daily.py 拆分为:
- utils.py: 工具函数
- stock_sync.py: 股票 & K线同步 (StockSyncMixin)
- financial_sync.py: 财务 & 估值同步 (FinancialSyncMixin)
- market_sync.py: 市场数据同步 (MarketSyncMixin)
- engine.py: DailySync 主类 + CLI 入口
"""

from .engine import DailySync, main

__all__ = ['DailySync', 'main']
