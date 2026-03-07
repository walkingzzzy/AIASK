#!/usr/bin/env python3
"""检查数据库状态"""

import asyncio
import asyncpg
import os
from pathlib import Path

# 加载环境变量
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip()


async def check_status():
    """检查数据库状态"""
    db_config = {
        'database': os.getenv('DB_NAME', 'postgres'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'password'),
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '5432')),
    }
    
    conn = await asyncpg.connect(**db_config)
    
    try:
        print("=" * 60)
        print("  数据库状态检查")
        print("=" * 60)
        
        # 股票数量
        stock_count = await conn.fetchval("SELECT COUNT(*) FROM stocks")
        print(f"\n股票数量: {stock_count}")
        
        # K线数量
        kline_count = await conn.fetchval("SELECT COUNT(*) FROM kline_1d")
        print(f"K线记录: {kline_count}")
        
        # 有K线数据的股票数量
        kline_stocks = await conn.fetchval("SELECT COUNT(DISTINCT code) FROM kline_1d")
        print(f"有K线数据的股票: {kline_stocks}")
        
        # K线日期范围
        kline_range = await conn.fetchrow("""
            SELECT MIN(time)::date as min_date, MAX(time)::date as max_date 
            FROM kline_1d
        """)
        if kline_range and kline_range['min_date']:
            print(f"K线日期范围: {kline_range['min_date']} ~ {kline_range['max_date']}")
        
        # 财务数量
        fin_count = await conn.fetchval("SELECT COUNT(*) FROM financials")
        print(f"财务记录: {fin_count}")
        
        # 有财务数据的股票数量
        fin_stocks = await conn.fetchval("SELECT COUNT(DISTINCT stock_code) FROM financials")
        print(f"有财务数据的股票: {fin_stocks}")
        
        # 检查一些关键表
        print("\n关键表状态:")
        tables = ['stocks', 'kline_1d', 'financials', 'events', 'users', 'backtest_results', 'watchlist']
        for table in tables:
            try:
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                print(f"  {table}: {count} 条记录")
            except Exception as e:
                print(f"  {table}: 表不存在或错误")
        
        print("\n" + "=" * 60)
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(check_status())
