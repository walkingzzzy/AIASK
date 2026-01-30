#!/usr/bin/env python3
"""检查实际数据库表结构"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from akshare_mcp.storage.timescaledb import get_db


async def check_schema():
    """检查数据库表结构"""
    db = get_db()
    await db.initialize()
    
    try:
        async with db.acquire() as conn:
            # 检查stocks表结构
            print("\n=== stocks表结构 ===")
            rows = await conn.fetch("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'stocks'
                ORDER BY ordinal_position
            """)
            for row in rows:
                print(f"  {row['column_name']}: {row['data_type']}")
            
            # 检查financials表结构
            print("\n=== financials表结构 ===")
            rows = await conn.fetch("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'financials'
                ORDER BY ordinal_position
            """)
            for row in rows:
                print(f"  {row['column_name']}: {row['data_type']}")
            
            # 检查kline_1d表结构
            print("\n=== kline_1d表结构 ===")
            rows = await conn.fetch("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'kline_1d'
                ORDER BY ordinal_position
            """)
            for row in rows:
                print(f"  {row['column_name']}: {row['data_type']}")
            
            # 检查stock_quotes表结构
            print("\n=== stock_quotes表结构 ===")
            rows = await conn.fetch("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'stock_quotes'
                ORDER BY ordinal_position
            """)
            for row in rows:
                print(f"  {row['column_name']}: {row['data_type']}")
    
    finally:
        await db.close()


if __name__ == '__main__':
    asyncio.run(check_schema())
