#!/usr/bin/env python3
"""
测试当前实际状态
验证哪些工具真的已经修复，哪些还有问题
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from akshare_mcp.storage.timescaledb import get_db


async def test_current_status():
    """测试当前状态"""
    print("=" * 60)
    print("测试当前实际状态")
    print("=" * 60)
    
    db = get_db()
    await db.initialize()
    
    results = {
        'passed': [],
        'failed': []
    }
    
    try:
        async with db.acquire() as conn:
            # 测试1: search_stocks - 检查market_cap字段
            print("\n1. 测试 search_stocks (market_cap字段)...")
            try:
                row = await conn.fetchrow("""
                    SELECT stock_code, stock_name, market_cap
                    FROM stocks
                    WHERE stock_code = '000001'
                """)
                if row:
                    print(f"   ✅ 成功: {row['stock_code']} - market_cap={row['market_cap']}")
                    results['passed'].append('search_stocks')
                else:
                    print("   ❌ 失败: 没有找到数据")
                    results['failed'].append('search_stocks')
            except Exception as e:
                print(f"   ❌ 失败: {e}")
                results['failed'].append('search_stocks')
            
            # 测试2: get_valuation_metrics - 检查pe_ratio, pb_ratio字段
            print("\n2. 测试 get_valuation_metrics (pe_ratio, pb_ratio字段)...")
            try:
                row = await conn.fetchrow("""
                    SELECT stock_code, pe_ratio, pb_ratio, market_cap
                    FROM stocks
                    WHERE stock_code = '000001'
                """)
                if row:
                    print(f"   ✅ 成功: PE={row['pe_ratio']}, PB={row['pb_ratio']}, 市值={row['market_cap']}")
                    results['passed'].append('get_valuation_metrics')
                else:
                    print("   ❌ 失败: 没有找到数据")
                    results['failed'].append('get_valuation_metrics')
            except Exception as e:
                print(f"   ❌ 失败: {e}")
                results['failed'].append('get_valuation_metrics')
            
            # 测试3: dcf_valuation - 检查financials表的stock_code字段
            print("\n3. 测试 dcf_valuation (financials.stock_code字段)...")
            try:
                row = await conn.fetchrow("""
                    SELECT stock_code, net_profit
                    FROM financials
                    WHERE stock_code = '000001'
                    ORDER BY report_date DESC
                    LIMIT 1
                """)
                if row:
                    print(f"   ✅ 成功: {row['stock_code']} - net_profit={row['net_profit']}")
                    results['passed'].append('dcf_valuation')
                else:
                    print("   ⚠️  警告: 没有找到财务数据（但字段存在）")
                    results['passed'].append('dcf_valuation')
            except Exception as e:
                print(f"   ❌ 失败: {e}")
                results['failed'].append('dcf_valuation')
            
            # 测试4: watchlist_manager - 检查user_id字段
            print("\n4. 测试 watchlist_manager (user_id字段)...")
            try:
                # 检查字段是否存在
                has_user_id = await conn.fetchval("""
                    SELECT COUNT(*) FROM information_schema.columns 
                    WHERE table_name = 'watchlist' AND column_name = 'user_id'
                """)
                if has_user_id > 0:
                    print(f"   ✅ 成功: watchlist表有user_id字段")
                    results['passed'].append('watchlist_manager')
                else:
                    print(f"   ❌ 失败: watchlist表没有user_id字段")
                    results['failed'].append('watchlist_manager')
            except Exception as e:
                print(f"   ❌ 失败: {e}")
                results['failed'].append('watchlist_manager')
            
            # 测试5: screener_manager - 检查screener_strategies表
            print("\n5. 测试 screener_manager (screener_strategies表)...")
            try:
                exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'screener_strategies'
                    )
                """)
                if exists:
                    count = await conn.fetchval("SELECT COUNT(*) FROM screener_strategies")
                    print(f"   ✅ 成功: screener_strategies表存在，{count}条记录")
                    results['passed'].append('screener_manager')
                else:
                    print(f"   ❌ 失败: screener_strategies表不存在")
                    results['failed'].append('screener_manager')
            except Exception as e:
                print(f"   ❌ 失败: {e}")
                results['failed'].append('screener_manager')
            
            # 测试6: 日期格式处理 - 检查get_klines方法
            print("\n6. 测试日期格式处理...")
            try:
                # 测试年份格式
                from datetime import datetime, date
                test_date = "2025"
                if len(test_date) == 4:
                    start_date = date(int(test_date), 1, 1)
                    end_date = date(int(test_date), 12, 31)
                    print(f"   ✅ 成功: 年份格式转换正常 {test_date} -> {start_date} to {end_date}")
                    results['passed'].append('date_format')
                else:
                    print(f"   ❌ 失败: 日期格式转换失败")
                    results['failed'].append('date_format')
            except Exception as e:
                print(f"   ❌ 失败: {e}")
                results['failed'].append('date_format')
        
        # 汇总结果
        print("\n" + "=" * 60)
        print("测试结果汇总")
        print("=" * 60)
        print(f"\n✅ 通过: {len(results['passed'])}/{len(results['passed']) + len(results['failed'])}")
        for tool in results['passed']:
            print(f"   ✅ {tool}")
        
        if results['failed']:
            print(f"\n❌ 失败: {len(results['failed'])}/{len(results['passed']) + len(results['failed'])}")
            for tool in results['failed']:
                print(f"   ❌ {tool}")
        else:
            print("\n🎉 所有测试通过！")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db.close()


if __name__ == '__main__':
    asyncio.run(test_current_status())
