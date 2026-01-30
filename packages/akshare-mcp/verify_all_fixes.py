#!/usr/bin/env python3
"""
验证所有修复的脚本
测试数据库字段映射、日期格式处理等问题
"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from akshare_mcp.storage.timescaledb import get_db


async def test_database_fields():
    """测试数据库字段映射"""
    print("\n=== 测试数据库字段映射 ===")
    
    db = get_db()
    await db.initialize()
    
    try:
        # 测试1: stocks表字段
        print("\n1. 测试stocks表字段...")
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT stock_code, stock_name, pe_ratio, pb_ratio, market_cap
                   FROM stocks
                   LIMIT 1"""
            )
            if row:
                print(f"✅ stocks表字段正确: stock_code={row['stock_code']}, market_cap={row['market_cap']}")
            else:
                print("⚠️  stocks表无数据")
        
        # 测试2: financials表字段
        print("\n2. 测试financials表字段...")
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT stock_code, report_date, net_profit, roe, debt_ratio
                   FROM financials
                   LIMIT 1"""
            )
            if row:
                print(f"✅ financials表字段正确: stock_code={row['stock_code']}, net_profit={row['net_profit']}")
            else:
                print("⚠️  financials表无数据")
        
        # 测试3: kline_1d表字段
        print("\n3. 测试kline_1d表字段...")
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT time, code, open, high, low, close, volume
                   FROM kline_1d
                   LIMIT 1"""
            )
            if row:
                print(f"✅ kline_1d表字段正确: code={row['code']}, close={row['close']}")
            else:
                print("⚠️  kline_1d表无数据")
        
        # 测试4: stock_quotes表字段
        print("\n4. 测试stock_quotes表字段...")
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT time, code, price, pe, pb, mkt_cap
                   FROM stock_quotes
                   LIMIT 1"""
            )
            if row:
                print(f"✅ stock_quotes表字段正确: code={row['code']}, mkt_cap={row['mkt_cap']}")
            else:
                print("⚠️  stock_quotes表无数据")
        
        print("\n✅ 所有数据库字段测试通过")
        return True
        
    except Exception as e:
        print(f"\n❌ 数据库字段测试失败: {e}")
        return False
    finally:
        await db.close()


async def test_date_format():
    """测试日期格式处理"""
    print("\n=== 测试日期格式处理 ===")
    
    db = get_db()
    await db.initialize()
    
    try:
        # 测试1: 年份格式 (YYYY)
        print("\n1. 测试年份格式 (2025)...")
        klines = await db.get_klines('000001', start_date='2025', limit=5)
        if klines:
            print(f"✅ 年份格式支持正常，获取到 {len(klines)} 条K线数据")
            print(f"   最新日期: {klines[0]['date']}")
        else:
            print("⚠️  未获取到K线数据（可能是数据库无数据）")
        
        # 测试2: 完整日期格式 (YYYY-MM-DD)
        print("\n2. 测试完整日期格式 (2025-01-01)...")
        klines = await db.get_klines('000001', start_date='2025-01-01', end_date='2025-12-31', limit=5)
        if klines:
            print(f"✅ 完整日期格式支持正常，获取到 {len(klines)} 条K线数据")
        else:
            print("⚠️  未获取到K线数据（可能是数据库无数据）")
        
        print("\n✅ 日期格式测试通过")
        return True
        
    except Exception as e:
        print(f"\n❌ 日期格式测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await db.close()


async def test_search_stocks():
    """测试搜索股票功能"""
    print("\n=== 测试搜索股票功能 ===")
    
    db = get_db()
    await db.initialize()
    
    try:
        print("\n1. 测试搜索股票（使用stock_code字段）...")
        async with db.acquire() as conn:
            rows = await conn.fetch(
                """SELECT stock_code, stock_name, industry, market_cap
                   FROM stocks
                   WHERE stock_code LIKE $1 OR stock_name LIKE $2
                   ORDER BY market_cap DESC NULLS LAST
                   LIMIT 5""",
                '%0000%', '%平安%'
            )
            
            if rows:
                print(f"✅ 搜索功能正常，找到 {len(rows)} 只股票")
                for row in rows[:3]:
                    print(f"   {row['stock_code']} {row['stock_name']} - 市值: {row['market_cap']}")
            else:
                print("⚠️  未找到股票（可能是数据库无数据）")
        
        print("\n✅ 搜索股票测试通过")
        return True
        
    except Exception as e:
        print(f"\n❌ 搜索股票测试失败: {e}")
        return False
    finally:
        await db.close()


async def test_valuation_queries():
    """测试估值查询"""
    print("\n=== 测试估值查询 ===")
    
    db = get_db()
    await db.initialize()
    
    try:
        print("\n1. 测试估值指标查询...")
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT stock_code, stock_name, pe_ratio, pb_ratio, market_cap
                   FROM stocks
                   WHERE stock_code = $1""",
                '000001'
            )
            
            if row:
                print(f"✅ 估值查询正常")
                print(f"   股票: {row['stock_code']} {row['stock_name']}")
                print(f"   PE: {row['pe_ratio']}, PB: {row['pb_ratio']}, 市值: {row['market_cap']}")
            else:
                print("⚠️  未找到股票数据")
        
        print("\n2. 测试财务数据查询（DCF估值用）...")
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT net_profit FROM financials
                   WHERE stock_code = $1
                   ORDER BY report_date DESC
                   LIMIT 1""",
                '000001'
            )
            
            if row:
                print(f"✅ 财务数据查询正常")
                print(f"   净利润: {row['net_profit']}")
            else:
                print("⚠️  未找到财务数据")
        
        print("\n✅ 估值查询测试通过")
        return True
        
    except Exception as e:
        print(f"\n❌ 估值查询测试失败: {e}")
        return False
    finally:
        await db.close()


async def main():
    """主测试函数"""
    print("=" * 60)
    print("开始验证所有修复...")
    print("=" * 60)
    
    results = []
    
    # 运行所有测试
    results.append(await test_database_fields())
    results.append(await test_date_format())
    results.append(await test_search_stocks())
    results.append(await test_valuation_queries())
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"\n通过: {passed}/{total}")
    
    if passed == total:
        print("\n✅ 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
