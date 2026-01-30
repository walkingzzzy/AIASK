"""
数据存储层
提供 TimescaleDB 适配器和数据访问接口
"""

from .timescaledb import TimescaleDBAdapter, get_db

__all__ = ['TimescaleDBAdapter', 'get_db']
