#!/usr/bin/env python3
"""
修复现有数据库结构
添加缺失的字段和表
"""

import asyncio
import sys
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

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


async def fix_database():
    """修复数据库结构"""
    import asyncpg
    
    db_config = {
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'password'),
        'database': os.getenv('DB_NAME', 'postgres'),
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '5432')),
    }
    
    print(f"连接数据库: {db_config['host']}:{db_config['port']}/{db_config['database']}")
    
    conn = await asyncpg.connect(**db_config)
    
    try:
        print("\n开始修复数据库结构...")
        
        # 1. 为 backtest_results 表添加 code 字段
        print("1. 检查 backtest_results.code 字段...")
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'backtest_results' AND column_name = 'code'
            )
        """)
        if not exists:
            try:
                await conn.execute("ALTER TABLE backtest_results ADD COLUMN code TEXT")
                print("   ✅ 添加 backtest_results.code 字段")
            except Exception as e:
                print(f"   ⚠️ {e}")
        else:
            print("   ✓ 字段已存在")
        
        # 2. 为 watchlist 表添加 user_id 字段
        print("2. 检查 watchlist.user_id 字段...")
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'watchlist' AND column_name = 'user_id'
            )
        """)
        if not exists:
            try:
                await conn.execute("ALTER TABLE watchlist ADD COLUMN user_id TEXT DEFAULT 'default'")
                print("   ✅ 添加 watchlist.user_id 字段")
            except Exception as e:
                print(f"   ⚠️ {e}")
        else:
            print("   ✓ 字段已存在")
        
        # 3. 为 watchlist 表添加 note 字段
        print("3. 检查 watchlist.note 字段...")
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'watchlist' AND column_name = 'note'
            )
        """)
        if not exists:
            try:
                await conn.execute("ALTER TABLE watchlist ADD COLUMN note TEXT")
                print("   ✅ 添加 watchlist.note 字段")
            except Exception as e:
                print(f"   ⚠️ {e}")
        else:
            print("   ✓ 字段已存在")
        
        # 4. 为 paper_accounts 表添加 user_id 字段
        print("4. 检查 paper_accounts.user_id 字段...")
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'paper_accounts' AND column_name = 'user_id'
            )
        """)
        if not exists:
            try:
                await conn.execute("ALTER TABLE paper_accounts ADD COLUMN user_id TEXT DEFAULT 'default'")
                print("   ✅ 添加 paper_accounts.user_id 字段")
            except Exception as e:
                print(f"   ⚠️ {e}")
        else:
            print("   ✓ 字段已存在")
        
        # 5. 创建 events 表
        print("5. 检查 events 表...")
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'events'
            )
        """)
        if not exists:
            await conn.execute("""
                CREATE TABLE events (
                    id SERIAL PRIMARY KEY,
                    code TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_date DATE NOT NULL,
                    title TEXT,
                    description TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("CREATE INDEX idx_events_code ON events(code)")
            await conn.execute("CREATE INDEX idx_events_date ON events(event_date)")
            print("   ✅ 创建 events 表")
        else:
            print("   ✓ 表已存在")
        
        # 6. 创建 users 表
        print("6. 检查 users 表...")
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'users'
            )
        """)
        if not exists:
            await conn.execute("""
                CREATE TABLE users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT,
                    settings JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("INSERT INTO users (id, username) VALUES ('default', 'default')")
            print("   ✅ 创建 users 表")
        else:
            print("   ✓ 表已存在")
        
        # 7. 创建 screener_strategies 表
        print("7. 检查 screener_strategies 表...")
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'screener_strategies'
            )
        """)
        if not exists:
            await conn.execute("""
                CREATE TABLE screener_strategies (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT DEFAULT 'default',
                    name TEXT NOT NULL,
                    criteria TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            print("   ✅ 创建 screener_strategies 表")
        else:
            print("   ✓ 表已存在")
        
        # 8. 创建 sync_tasks 表
        print("8. 检查 sync_tasks 表...")
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'sync_tasks'
            )
        """)
        if not exists:
            await conn.execute("""
                CREATE TABLE sync_tasks (
                    id SERIAL PRIMARY KEY,
                    task_id TEXT UNIQUE NOT NULL,
                    task_type TEXT NOT NULL,
                    codes TEXT[],
                    priority TEXT DEFAULT 'normal',
                    status TEXT DEFAULT 'pending',
                    progress INTEGER DEFAULT 0,
                    total INTEGER DEFAULT 0,
                    error_message TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    completed_at TIMESTAMPTZ
                )
            """)
            print("   ✅ 创建 sync_tasks 表")
        else:
            print("   ✓ 表已存在")
        
        # 9. 创建 sync_schedules 表
        print("9. 检查 sync_schedules 表...")
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'sync_schedules'
            )
        """)
        if not exists:
            await conn.execute("""
                CREATE TABLE sync_schedules (
                    id SERIAL PRIMARY KEY,
                    schedule_id TEXT UNIQUE NOT NULL,
                    task_type TEXT NOT NULL,
                    codes TEXT[],
                    schedule TEXT NOT NULL,
                    enabled BOOLEAN DEFAULT true,
                    last_run TIMESTAMPTZ,
                    next_run TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            print("   ✅ 创建 sync_schedules 表")
        else:
            print("   ✓ 表已存在")
        
        # 10. 创建 pattern_vectors 表
        print("10. 检查 pattern_vectors 表...")
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'pattern_vectors'
            )
        """)
        if not exists:
            await conn.execute("""
                CREATE TABLE pattern_vectors (
                    id SERIAL PRIMARY KEY,
                    stock_code TEXT,
                    window_size INTEGER,
                    embedding REAL[],
                    start_date DATE,
                    end_date DATE,
                    pattern_type TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            print("   ✅ 创建 pattern_vectors 表")
        else:
            print("   ✓ 表已存在")
        
        # 11. 创建 watchlist_groups 表
        print("11. 检查 watchlist_groups 表...")
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'watchlist_groups'
            )
        """)
        if not exists:
            await conn.execute("""
                CREATE TABLE watchlist_groups (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    user_id TEXT DEFAULT 'default',
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("INSERT INTO watchlist_groups (id, name, sort_order) VALUES ('default', '默认分组', 0)")
            print("   ✅ 创建 watchlist_groups 表")
        else:
            print("   ✓ 表已存在")
        
        print("\n✅ 数据库结构修复完成!")
        
        # 显示数据库统计
        print("\n数据库统计:")
        
        stock_count = await conn.fetchval("SELECT COUNT(*) FROM stocks")
        print(f"  - 股票数量: {stock_count}")
        
        kline_count = await conn.fetchval("SELECT COUNT(*) FROM kline_1d")
        print(f"  - K线数据: {kline_count}")
        
        financial_count = await conn.fetchval("SELECT COUNT(*) FROM financials")
        print(f"  - 财务数据: {financial_count}")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(fix_database())
