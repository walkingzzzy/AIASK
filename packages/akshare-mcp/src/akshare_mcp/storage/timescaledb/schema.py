"""
TimescaleDB 适配器 — 连接管理与表结构初始化（thin entry-point）

实际实现拆分为四个子模块：
- schema_base.py:    SchemaBase 类（连接池、acquire、pgvector 检测、close）
- schema_market.py:  市场数据表 DDL（~30 张表）
- schema_strategy.py: 策略相关表 DDL（~25 张表）
- schema_vector.py:  统一向量层 DDL（collection / profile / chunk / ANN）

SchemaBase._init_tables() 依次调用
    init_market_tables(conn)
    init_strategy_tables(conn, pgvector_enabled)
    init_vector_tables(conn, pgvector_enabled)

向后兼容：
    from .schema import SchemaBase          # 仍然有效
    from .schema import init_market_tables  # 也可直接导入 DDL 函数
"""

from .schema_base import SchemaBase
from .schema_market import init_market_tables
from .schema_strategy import init_strategy_tables
from .schema_vector import init_vector_tables

__all__ = [
    'SchemaBase',
    'init_market_tables',
    'init_strategy_tables',
    'init_vector_tables',
]
