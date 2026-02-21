"""TimescaleDB 适配器包 — 拆分自 timescaledb.py

子模块:
- schema: 连接管理与 DDL 初始化 (SchemaBase)
- kline: K线数据读写 (KlineMixin)
- stock_info: 股票信息查询 (StockInfoMixin)
- financials: 财务数据查询 (FinancialsMixin)
- quotes: 实时行情保存与统计 (QuotesMixin)
- artifacts: 策略工件持久化 (ArtifactMixin)

向后兼容：
    from .timescaledb import TimescaleDBAdapter, get_db
仍然有效。
"""

from typing import Optional

from .schema import SchemaBase
from .kline import KlineMixin
from .stock_info import StockInfoMixin
from .financials import FinancialsMixin
from .quotes import QuotesMixin
from .artifacts import ArtifactMixin
from .strategy import StrategyMixin
from .factor_storage import FactorStorageMixin


class TimescaleDBAdapter(
    KlineMixin,
    StockInfoMixin,
    FinancialsMixin,
    QuotesMixin,
    ArtifactMixin,
    StrategyMixin,
    FactorStorageMixin,
    SchemaBase,
):
    """TimescaleDB 异步适配器（Mixin 组合）

    通过 Mixin 组合:
    - SchemaBase: 连接池管理、事件循环检测、DDL 初始化
    - KlineMixin: K线数据 get_klines / save_klines
    - StockInfoMixin: 股票信息 get_stock_info / search_stocks
    - FinancialsMixin: 财务数据 get_financials
    - QuotesMixin: 实时行情 save_quote / get_stats
    - ArtifactMixin: 策略工件 save_artifact / get_artifact_by_id / list_artifacts_db
    - StrategyMixin: 策略超市 save_strategy / list_strategies / subscribe / review
    - FactorStorageMixin: 因子持久化 save_factor_values / get_factor_values / save_factor_ic
    """
    pass


# 全局单例
_db_instance: Optional[TimescaleDBAdapter] = None


def get_db() -> TimescaleDBAdapter:
    """获取数据库实例（全局单例）

    TimescaleDBAdapter 内部会自动检测事件循环变更并重建连接池，
    因此单例模式是安全的。
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = TimescaleDBAdapter()
    return _db_instance


__all__ = [
    'TimescaleDBAdapter',
    'get_db',
]
