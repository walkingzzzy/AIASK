#!/usr/bin/env python3
"""
同步估值数据到stocks表
从实时行情获取PE、PB、市值等数据
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from akshare_mcp.storage.timescaledb import get_db
from akshare_mcp.data_source import DataSource


async def sync_valuation_data():
    """同步估值数据"""
    print("=" * 60)
    print("开始同步估值数据...")
    print("=" * 60)
    
    db = get_db()
    await db.initialize()
    
    try:
        # 1. 获取所有股票代码
        print("\n1. 获取股票列表...")
        async with db.acquire() as conn:
            rows = await conn.fetch("""
                SELECT stock_code, stock_name 
                FROM stocks 
                ORDER BY stock_code
            """)
            
            stock_codes = [(row['stock_code'], row['stock_name']) for row in rows]
            print(f"   找到 {len(stock_codes)} 只股票")
        
        if not stock_codes:
            print("⚠️  没有找到股票数据")
            return
        
        # 2. 批量获取实时行情（包含估值数据）
        print("\n2. 获取实时行情数据...")
        data_source = DataSource()
        
        updated_count = 0
        failed_count = 0
        batch_size = 50
        
        for i in range(0, len(stock_codes), batch_size):
            batch = stock_codes[i:i+batch_size]
            codes = [code for code, _ in batch]
            
            print(f"\n   处理批次 {i//batch_size + 1}/{(len(stock_codes)-1)//batch_size + 1} ({len(codes)}只股票)...")
            
            try:
                # 批量获取行情
                quotes = await data_source.get_batch_quotes(codes)
                
                if quotes:
                    # 更新到数据库
                    async with db.acquire() as conn:
                        for quote in quotes:
                            try:
                                # 提取估值数据
                                code = quote.get('code')
                                pe = quote.get('pe')
                                pb = quote.get('pb')
                                market_cap = quote.get('market_cap') or quote.get('mkt_cap')
                                
                                # 更新stocks表
                                if code and (pe or pb or market_cap):
                                    await conn.execute("""
                                        UPDATE stocks
                                        SET 
                                            pe_ratio = $1,
                                            pb_ratio = $2,
                                            market_cap = $3,
                                            updated_at = NOW()
                                        WHERE stock_code = $4
                                    """, pe, pb, market_cap, code)
                                    updated_count += 1
                            except Exception as e:
                                print(f"      ⚠️  更新 {code} 失败: {e}")
                                failed_count += 1
                    
                    print(f"      ✅ 批次处理完成，已更新 {len(quotes)} 只股票")
                else:
                    print(f"      ⚠️  批次无数据")
                    failed_count += len(codes)
                
                # 避免请求过快
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"      ❌ 批次处理失败: {e}")
                failed_count += len(codes)
        
        # 3. 验证结果
        print("\n3. 验证同步结果...")
        async with db.acquire() as conn:
            # 统计有估值数据的股票数量
            count_with_pe = await conn.fetchval("""
                SELECT COUNT(*) FROM stocks WHERE pe_ratio IS NOT NULL
            """)
            count_with_pb = await conn.fetchval("""
                SELECT COUNT(*) FROM stocks WHERE pb_ratio IS NOT NULL
            """)
            count_with_cap = await conn.fetchval("""
                SELECT COUNT(*) FROM stocks WHERE market_cap IS NOT NULL
            """)
            
            print(f"   有PE数据的股票: {count_with_pe}")
            print(f"   有PB数据的股票: {count_with_pb}")
            print(f"   有市值数据的股票: {count_with_cap}")
            
            # 显示示例数据
            print("\n   示例数据（前5只）:")
            rows = await conn.fetch("""
                SELECT stock_code, stock_name, pe_ratio, pb_ratio, market_cap
                FROM stocks
                WHERE pe_ratio IS NOT NULL OR pb_ratio IS NOT NULL OR market_cap IS NOT NULL
                ORDER BY market_cap DESC NULLS LAST
                LIMIT 5
            """)
            
            for row in rows:
                print(f"      {row['stock_code']} {row['stock_name']}")
                print(f"         PE: {row['pe_ratio']}, PB: {row['pb_ratio']}, 市值: {row['market_cap']}")
        
        print("\n" + "=" * 60)
        print(f"估值数据同步完成！")
        print(f"成功: {updated_count}, 失败: {failed_count}")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 同步失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db.close()


if __name__ == '__main__':
    asyncio.run(sync_valuation_data())
