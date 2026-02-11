#!/usr/bin/env python3
"""修复数据库表缺失的列"""

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


async def fix_tables():
    """修复数据库表"""
    db_config = {
        'database': os.getenv('DB_NAME', 'postgres'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'password'),
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '5432')),
    }
    
    conn = await asyncpg.connect(**db_config)
    
    try:
        print("修复数据库表结构...\n")
        
        # 1. 修复 watchlist_groups 表
        print("1. 检查 watchlist_groups 表...")
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'watchlist_groups'
            )
        """)
        
        if exists:
            has_user_id = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'watchlist_groups' AND column_name = 'user_id'
                )
            """)
            
            if not has_user_id:
                print("   添加 user_id 列...")
                await conn.execute("""
                    ALTER TABLE watchlist_groups 
                    ADD COLUMN user_id TEXT DEFAULT 'default'
                """)
                print("   ✅ user_id 列已添加")
            else:
                print("   ✅ user_id 列已存在")
        else:
            print("   表不存在，将在初始化时创建")
        
        # 2. 修复 screener_strategies 表
        print("\n2. 检查 screener_strategies 表...")
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'screener_strategies'
            )
        """)
        
        if exists:
            has_user_id = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'screener_strategies' AND column_name = 'user_id'
                )
            """)
            
            if not has_user_id:
                print("   添加 user_id 列...")
                await conn.execute("""
                    ALTER TABLE screener_strategies 
                    ADD COLUMN user_id TEXT DEFAULT 'default'
                """)
                print("   ✅ user_id 列已添加")
            else:
                print("   ✅ user_id 列已存在")
        else:
            print("   表不存在，将在初始化时创建")
        
        # 3. 修复 portfolios 表
        print("\n3. 检查 portfolios 表...")
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'portfolios'
            )
        """)
        
        if exists:
            has_user_id = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'portfolios' AND column_name = 'user_id'
                )
            """)
            
            if not has_user_id:
                print("   添加 user_id 列...")
                await conn.execute("""
                    ALTER TABLE portfolios 
                    ADD COLUMN user_id TEXT DEFAULT 'default'
                """)
                print("   ✅ user_id 列已添加")
            else:
                print("   ✅ user_id 列已存在")
        else:
            print("   表不存在，将在初始化时创建")
        
        print("\n✅ 数据库修复完成!")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(fix_tables())
