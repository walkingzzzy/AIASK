#!/usr/bin/env python3
"""
补充缺失数据脚本 - 只同步数据库中缺失的部分
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# 加载环境变量
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from akshare_mcp.storage.timescaledb import get_db
from akshare_mcp.data_source import data_source


class MissingDataSync:
    """补充缺失数据"""
    
    def __init__(self):
        self.db = get_db()
        self.ts_pro = data_source.get_tushare_pro()
        self.start_time = None
    
    def log(self, msg: str):
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"[{timestamp}] {msg}")
    
    def progress(self, current: int, total: int, desc: str = ""):
        if total == 0:
            return
        pct = (current / total * 100)
        bar_len = 40
        filled = int(bar_len * current / total)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r  [{bar}] {pct:5.1f}% ({current}/{total}) {desc}", end="", flush=True)
    
    async def sync_missing_klines(self):
        """补充缺失的K线数据（2021-2023）"""
        self.log("\n[1] 补充2021-2023年K线数据...")
        
        # 获取K线数据不完整的股票（少于1000条的）
        async with self.db.acquire() as conn:
            rows = await conn.fetch("""
                SELECT s.stock_code, COUNT(k.time) as kline_count
                FROM stocks s
                LEFT JOIN kline_1d k ON s.stock_code = k.code
                GROUP BY s.stock_code
                HAVING COUNT(k.time) < 1000 OR COUNT(k.time) = 0
                ORDER BY s.stock_code
            """)
        
        if not rows:
            self.log("  ✅ 所有股票K线数据完整")
            return 0
        
        self.log(f"  需要补充 {len(rows)} 只股票")
        
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = '20210101'
        
        count = 0
        for i, row in enumerate(rows):
            code = row['stock_code']
            try:
                ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
                df = self.ts_pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                
                if df is not None and not df.empty:
                    async with self.db.acquire() as conn:
                        from datetime import date
                        for _, data_row in df.iterrows():
                            trade_date = str(data_row['trade_date'])
                            # 转换为 date 对象
                            date_obj = date(int(trade_date[:4]), int(trade_date[4:6]), int(trade_date[6:]))
                            
                            await conn.execute("""
                                INSERT INTO kline_1d (time, code, open, high, low, close, volume, amount, change_pct, updated_at)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                                ON CONFLICT (time, code) DO NOTHING
                            """, date_obj, code,
                                float(data_row['open']), float(data_row['high']), 
                                float(data_row['low']), float(data_row['close']),
                                int(float(data_row['vol']) * 100) if data_row['vol'] else 0,
                                float(data_row['amount']) * 1000 if data_row['amount'] else 0,
                                float(data_row['pct_chg']) if data_row['pct_chg'] else None)
                    count += 1
            except Exception as e:
                pass
            
            self.progress(i + 1, len(rows), f"成功 {count}")
            
            if (i + 1) % 50 == 0:
                await asyncio.sleep(0.5)
        
        print()
        self.log(f"✅ 完成: 补充 {count} 只股票")
        return count
    
    async def sync_missing_financials(self):
        """补充缺失的财务数据（5年）"""
        self.log("\n[2] 补充财务数据（近5年）...")
        
        # 获取财务数据不完整的股票（少于10条的）
        async with self.db.acquire() as conn:
            rows = await conn.fetch("""
                SELECT s.stock_code, COUNT(f.report_date) as fin_count
                FROM stocks s
                LEFT JOIN financials f ON s.stock_code = f.stock_code
                GROUP BY s.stock_code
                HAVING COUNT(f.report_date) < 10
                ORDER BY s.stock_code
            """)
        
        if not rows:
            self.log("  ✅ 所有股票财务数据完整")
            return 0
        
        self.log(f"  需要补充 {len(rows)} 只股票")
        
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=1825)).strftime('%Y%m%d')
        
        count = 0
        for i, row in enumerate(rows):
            code = row['stock_code']
            try:
                ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
                df = self.ts_pro.fina_indicator(ts_code=ts_code, start_date=start_date, end_date=end_date)
                
                if df is not None and not df.empty:
                    async with self.db.acquire() as conn:
                        from datetime import date
                        for _, data_row in df.iterrows():
                            end_date_str = str(data_row['end_date'])
                            # 转换为 date 对象
                            report_date = date(int(end_date_str[:4]), int(end_date_str[4:6]), int(end_date_str[6:]))
                            
                            await conn.execute("""
                                INSERT INTO financials (stock_code, report_date, revenue, net_profit, roe, debt_ratio, eps, revenue_growth, profit_growth, updated_at)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                                ON CONFLICT (stock_code, report_date) DO NOTHING
                            """, code, report_date,
                                float(data_row['revenue']) if data_row['revenue'] else None,
                                float(data_row['n_income']) if data_row['n_income'] else None,
                                float(data_row['roe']) if data_row['roe'] else None,
                                float(data_row['debt_to_assets']) if data_row['debt_to_assets'] else None,
                                float(data_row['eps']) if data_row['eps'] else None,
                                float(data_row['or_yoy']) if data_row['or_yoy'] else None,
                                float(data_row['q_profit_yoy']) if data_row['q_profit_yoy'] else None)
                    count += 1
            except:
                pass
            
            self.progress(i + 1, len(rows), f"成功 {count}")
            
            if (i + 1) % 20 == 0:
                await asyncio.sleep(1)
        
        print()
        self.log(f"✅ 完成: 补充 {count} 只股票")
        return count
    
    async def sync_valuations(self):
        """同步估值数据"""
        self.log("\n[3] 同步估值数据...")
        
        async with self.db.acquire() as conn:
            rows = await conn.fetch("""
                SELECT stock_code 
                FROM stocks 
                WHERE pe_ratio IS NULL
                ORDER BY stock_code
            """)
            codes = [row['stock_code'] for row in rows]
        
        if not codes:
            self.log("  ✅ 所有股票已有估值数据")
            return 0
        
        self.log(f"  需要同步 {len(codes)} 只股票")
        
        # 查找最近的交易日
        trade_date = None
        for days_back in range(1, 8):
            test_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
            try:
                test_df = self.ts_pro.daily_basic(ts_code='000001.SZ', trade_date=test_date, fields='ts_code,pe')
                if test_df is not None and not test_df.empty:
                    trade_date = test_date
                    self.log(f"  使用交易日: {test_date[:4]}-{test_date[4:6]}-{test_date[6:]}")
                    break
            except:
                continue
        
        if not trade_date:
            self.log("  ⚠️  未找到有效的交易日数据")
            return 0
        
        count = 0
        batch_size = 100
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i+batch_size]
            ts_codes = [f"{c}.SH" if c.startswith('6') else f"{c}.SZ" for c in batch]
            
            try:
                df = self.ts_pro.daily_basic(ts_code=','.join(ts_codes), trade_date=trade_date, 
                                            fields='ts_code,pe,pb,total_mv')
                
                if df is not None and not df.empty:
                    async with self.db.acquire() as conn:
                        for _, row in df.iterrows():
                            code = row['ts_code'].split('.')[0]
                            pe = float(row['pe']) if row['pe'] and row['pe'] > 0 else None
                            pb = float(row['pb']) if row['pb'] and row['pb'] > 0 else None
                            cap = float(row['total_mv']) if row['total_mv'] and row['total_mv'] > 0 else None
                            
                            await conn.execute("""
                                UPDATE stocks 
                                SET pe_ratio = $1, pb_ratio = $2, market_cap = $3, updated_at = NOW()
                                WHERE stock_code = $4
                            """, pe, pb, cap, code)
                            count += 1
            except:
                pass
            
            self.progress(i + batch_size, len(codes), f"成功 {count}")
            await asyncio.sleep(0.3)
        
        print()
        self.log(f"✅ 完成: 同步 {count} 只股票")
        return count
    
    async def sync_dragon_tiger(self):
        """同步龙虎榜数据（近1年）"""
        self.log("\n[4] 同步龙虎榜数据（近1年）...")
        
        from datetime import date
        count = 0
        for i in range(365):
            trade_date_str = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
            
            try:
                df = self.ts_pro.top_list(trade_date=trade_date_str)
                
                if df is not None and not df.empty:
                    async with self.db.acquire() as conn:
                        for _, row in df.iterrows():
                            # 转换为 date 对象
                            date_obj = date(int(trade_date_str[:4]), int(trade_date_str[4:6]), int(trade_date_str[6:]))
                            
                            await conn.execute("""
                                INSERT INTO dragon_tiger_list (trade_date, stock_code, stock_name, close_price, change_pct, net_amount, reason)
                                VALUES ($1, $2, $3, $4, $5, $6, $7)
                                ON CONFLICT (trade_date, stock_code) DO NOTHING
                            """, date_obj,
                                row['ts_code'].split('.')[0], row.get('name'),
                                float(row['close']) if row.get('close') else None,
                                float(row['pct_chg']) if row.get('pct_chg') else None,
                                float(row['net_amount']) if row.get('net_amount') else None,
                                row.get('reason'))
                            count += 1
            except:
                pass
            
            self.progress(i + 1, 365, f"成功 {count}")
            await asyncio.sleep(0.2)
        
        print()
        self.log(f"✅ 完成: 同步 {count} 条记录")
        return count
    
    async def run(self):
        """运行补充数据同步"""
        self.start_time = datetime.now()
        
        try:
            await self.db.initialize()
            
            if not self.ts_pro:
                self.log("❌ Tushare Pro 未配置")
                return
            
            self.log("=" * 80)
            self.log("  补充缺失数据")
            self.log("=" * 80)
            
            await self.sync_missing_klines()
            await self.sync_missing_financials()
            await self.sync_valuations()
            await self.sync_dragon_tiger()
            
            duration = (datetime.now() - self.start_time).total_seconds() / 60
            self.log("\n" + "=" * 80)
            self.log(f"  ✅ 数据补充完成 (耗时 {duration:.1f} 分钟)")
            self.log("=" * 80)
            
        except Exception as e:
            self.log(f"\n❌ 同步失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.db.close()


async def main():
    sync = MissingDataSync()
    await sync.run()


if __name__ == '__main__':
    asyncio.run(main())
