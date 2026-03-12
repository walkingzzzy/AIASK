"""
数据存储层
提供 TimescaleDB 适配器和数据访问接口
"""

from .timescaledb import (
    TimescaleDBAdapter,
    await_with_db_cleanup,
    close_db,
    get_db,
    run_with_db_cleanup,
)

__all__ = [
    'TimescaleDBAdapter',
    'get_db',
    'close_db',
    'await_with_db_cleanup',
    'run_with_db_cleanup',
]
