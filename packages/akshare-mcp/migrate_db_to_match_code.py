#!/usr/bin/env python3
"""
数据库迁移脚本 - 使数据库结构与代码匹配
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from akshare_mcp.storage.timescaledb import get_db


async def migrate_database():
    """迁移数据库结构"""
    print("=" * 60)
    print("开始数据库迁移...")
    print("=" * 60)
    
    db = get_db()
    await db.initialize()
    
    try:
        async with db.acquire() as conn:
            # 1. 为stocks表添加缺失的字段
            print("\n1. 为stocks表添加估值字段...")
            try:
                await conn.execute("""
                    ALTER TABLE stocks 
                    ADD COLUMN IF NOT EXISTS market_cap DOUBLE PRECISION,
                    ADD COLUMN IF NOT EXISTS pe_ratio DOUBLE PRECISION,
                    ADD COLUMN IF NOT EXISTS pb_ratio DOUBLE PRECISION
                """)
                print("✅ stocks表字段添加成功")
            except Exception as e:
                print(f"⚠️  stocks表字段添加失败: {e}")
            
            # 2. 为financials表重命名code字段为stock_code
            print("\n2. 检查financials表字段...")
            # 先检查是否已经有stock_code字段
            has_stock_code = await conn.fetchval("""
                SELECT COUNT(*) FROM information_schema.columns 
                WHERE table_name = 'financials' AND column_name = 'stock_code'
            """)
            
            if has_stock_code == 0:
                print("   需要重命名code字段为stock_code...")
                try:
                    # 重命名字段
                    await conn.execute("""
                        ALTER TABLE financials 
                        RENAME COLUMN code TO stock_code
                    """)
                    print("✅ financials表字段重命名成功")
                except Exception as e:
                    print(f"⚠️  financials表字段重命名失败: {e}")
            else:
                print("✅ financials表已有stock_code字段")
            
            # 3. 从stock_quotes表同步估值数据到stocks表
            print("\n3. 同步估值数据到stocks表...")
            try:
                # 获取最新的估值数据并更新到stocks表
                await conn.execute("""
                    UPDATE stocks s
                    SET 
                        market_cap = sq.mkt_cap,
                        pe_ratio = sq.pe,
                        pb_ratio = sq.pb
                    FROM (
                        SELECT DISTINCT ON (code) 
                            code, mkt_cap, pe, pb
                        FROM stock_quotes
                        WHERE mkt_cap IS NOT NULL OR pe IS NOT NULL OR pb IS NOT NULL
                        ORDER BY code, time DESC
                    ) sq
                    WHERE s.stock_code = sq.code
                """)
                
                updated_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM stocks 
                    WHERE market_cap IS NOT NULL OR pe_ratio IS NOT NULL OR pb_ratio IS NOT NULL
                """)
                print(f"✅ 估值数据同步成功，更新了 {updated_count} 条记录")
            except Exception as e:
                print(f"⚠️  估值数据同步失败: {e}")
            
            # 4. 验证迁移结果
            print("\n4. 验证迁移结果...")
            
            # 检查stocks表
            stocks_row = await conn.fetchrow("""
                SELECT stock_code, stock_name, market_cap, pe_ratio, pb_ratio
                FROM stocks
                WHERE market_cap IS NOT NULL
                LIMIT 1
            """)
            if stocks_row:
                print(f"✅ stocks表验证成功:")
                print(f"   {stocks_row['stock_code']} {stocks_row['stock_name']}")
                print(f"   市值: {stocks_row['market_cap']}, PE: {stocks_row['pe_ratio']}, PB: {stocks_row['pb_ratio']}")
            else:
                print("⚠️  stocks表无估值数据")
            
            # 检查financials表
            financials_row = await conn.fetchrow("""
                SELECT stock_code, report_date, net_profit, roe
                FROM financials
                LIMIT 1
            """)
            if financials_row:
                print(f"✅ financials表验证成功:")
                print(f"   {financials_row['stock_code']} - {financials_row['report_date']}")
                print(f"   净利润: {financials_row['net_profit']}, ROE: {financials_row['roe']}")
            else:
                print("⚠️  financials表无数据")
            
            print("\n" + "=" * 60)
            print("数据库迁移完成！")
            print("=" * 60)
            
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db.close()


if __name__ == '__main__':
    asyncio.run(migrate_database())
