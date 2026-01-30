#!/usr/bin/env python3
"""
创建缺失的数据库表
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from akshare_mcp.storage.timescaledb import get_db


async def create_missing_tables():
    """创建缺失的数据库表"""
    print("=" * 60)
    print("开始创建缺失的数据库表...")
    print("=" * 60)
    
    db = get_db()
    await db.initialize()
    
    try:
        async with db.acquire() as conn:
            # 1. 创建选股策略表
            print("\n1. 创建选股策略表 (screener_strategies)...")
            try:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS screener_strategies (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        conditions JSONB NOT NULL,
                        created_by TEXT DEFAULT 'system',
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_screener_strategies_name 
                    ON screener_strategies(name);
                """)
                print("   ✅ screener_strategies表创建成功")
                
                # 插入一些默认策略
                await conn.execute("""
                    INSERT INTO screener_strategies (name, description, conditions)
                    VALUES 
                        ('低估值', '市盈率<20且市净率<3', '{"pe_ratio": {"operator": "<", "value": 20}, "pb_ratio": {"operator": "<", "value": 3}}'::jsonb),
                        ('高ROE', 'ROE>15%', '{"roe": {"operator": ">", "value": 0.15}}'::jsonb),
                        ('高增长', '营收增长>20%', '{"revenue_growth": {"operator": ">", "value": 0.20}}'::jsonb)
                    ON CONFLICT (name) DO NOTHING
                """)
                print("   ✅ 默认策略插入成功")
                
            except Exception as e:
                print(f"   ⚠️  screener_strategies表创建失败: {e}")
            
            # 2. 修复watchlist表（添加user_id字段）
            print("\n2. 修复watchlist表...")
            try:
                # 检查是否已有user_id字段
                has_user_id = await conn.fetchval("""
                    SELECT COUNT(*) FROM information_schema.columns 
                    WHERE table_name = 'watchlist' AND column_name = 'user_id'
                """)
                
                if has_user_id == 0:
                    await conn.execute("""
                        ALTER TABLE watchlist 
                        ADD COLUMN IF NOT EXISTS user_id TEXT DEFAULT 'default'
                    """)
                    print("   ✅ watchlist表user_id字段添加成功")
                else:
                    print("   ✅ watchlist表已有user_id字段")
                
            except Exception as e:
                print(f"   ⚠️  watchlist表修复失败: {e}")
            
            # 3. 创建新闻缓存表（用于缓存新闻数据）
            print("\n3. 创建新闻缓存表 (news_cache)...")
            try:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS news_cache (
                        id SERIAL PRIMARY KEY,
                        stock_code TEXT,
                        news_type TEXT NOT NULL,
                        title TEXT NOT NULL,
                        content TEXT,
                        source TEXT,
                        url TEXT,
                        publish_date TIMESTAMPTZ,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_news_cache_stock 
                    ON news_cache(stock_code, publish_date DESC);
                    
                    CREATE INDEX IF NOT EXISTS idx_news_cache_type 
                    ON news_cache(news_type, publish_date DESC);
                """)
                print("   ✅ news_cache表创建成功")
                
            except Exception as e:
                print(f"   ⚠️  news_cache表创建失败: {e}")
            
            # 4. 创建龙虎榜数据表
            print("\n4. 创建龙虎榜数据表 (dragon_tiger_list)...")
            try:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS dragon_tiger_list (
                        id SERIAL PRIMARY KEY,
                        trade_date DATE NOT NULL,
                        stock_code TEXT NOT NULL,
                        stock_name TEXT,
                        close_price DOUBLE PRECISION,
                        change_pct DOUBLE PRECISION,
                        turnover_rate DOUBLE PRECISION,
                        net_amount DOUBLE PRECISION,
                        buy_amount DOUBLE PRECISION,
                        sell_amount DOUBLE PRECISION,
                        reason TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(trade_date, stock_code)
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_dragon_tiger_date 
                    ON dragon_tiger_list(trade_date DESC);
                    
                    CREATE INDEX IF NOT EXISTS idx_dragon_tiger_stock 
                    ON dragon_tiger_list(stock_code, trade_date DESC);
                """)
                print("   ✅ dragon_tiger_list表创建成功")
                
            except Exception as e:
                print(f"   ⚠️  dragon_tiger_list表创建失败: {e}")
            
            # 5. 创建龙虎榜明细表
            print("\n5. 创建龙虎榜明细表 (dragon_tiger_details)...")
            try:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS dragon_tiger_details (
                        id SERIAL PRIMARY KEY,
                        trade_date DATE NOT NULL,
                        stock_code TEXT NOT NULL,
                        broker_name TEXT NOT NULL,
                        buy_amount DOUBLE PRECISION,
                        sell_amount DOUBLE PRECISION,
                        net_amount DOUBLE PRECISION,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_dragon_tiger_details_date 
                    ON dragon_tiger_details(trade_date DESC, stock_code);
                """)
                print("   ✅ dragon_tiger_details表创建成功")
                
            except Exception as e:
                print(f"   ⚠️  dragon_tiger_details表创建失败: {e}")
            
            # 6. 验证所有表
            print("\n6. 验证所有表...")
            tables = [
                'screener_strategies',
                'watchlist',
                'news_cache',
                'dragon_tiger_list',
                'dragon_tiger_details'
            ]
            
            for table in tables:
                exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = $1
                    )
                """, table)
                
                if exists:
                    count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                    print(f"   ✅ {table}: 存在，{count} 条记录")
                else:
                    print(f"   ❌ {table}: 不存在")
            
            print("\n" + "=" * 60)
            print("数据库表创建完成！")
            print("=" * 60)
            
    except Exception as e:
        print(f"\n❌ 创建失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db.close()


if __name__ == '__main__':
    asyncio.run(create_missing_tables())
