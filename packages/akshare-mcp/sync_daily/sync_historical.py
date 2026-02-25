#!/usr/bin/env python3
"""
历史数据同步脚本 - 用于初始化近5年的完整数据
使用 Tushare Pro 作为主要数据源

同步数据清单:
1. 股票基础信息 (stocks)
2. K线数据 (kline_1d) - 近5年
3. 财务数据 (financials) - 近5年
4. 估值数据 (stocks) - 最新
5. 龙虎榜 (dragon_tiger_list) - 近1年
6. 北向资金 (north_fund_flow) - 近1年
7. 宏观数据 - 近5年
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

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


class HistoricalDataSync:
    """历史数据同步管理器"""
    
    def __init__(self):
        self.db = get_db()
        self.ts_pro = data_source.get_tushare_pro()
        self.stats = {}
        self.start_time = None
    
    def log(self, msg: str):
        """打印日志"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"[{timestamp}] {msg}")
    
    def progress(self, current: int, total: int, desc: str = ""):
        """显示进度"""
        if total == 0:
            return
        pct = (current / total * 100)
        bar_len = 40
        filled = int(bar_len * current / total)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r  [{bar}] {pct:5.1f}% ({current}/{total}) {desc}", end="", flush=True)
    
    async def create_missing_tables(self):
        """创建缺失的数据表"""
        self.log("检查并创建缺失的数据表...")
        
        async with self.db.acquire() as conn:
            # 北向资金表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS north_fund_flow (
                    trade_date DATE PRIMARY KEY,
                    north_money DOUBLE PRECISION,
                    south_money DOUBLE PRECISION,
                    net_amount DOUBLE PRECISION,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            
            # 龙虎榜表
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
                )
            """)
            
            # 新闻缓存表
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
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            
            # 宏观数据表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS macro_data (
                    id SERIAL PRIMARY KEY,
                    indicator TEXT NOT NULL,
                    period TEXT NOT NULL,
                    value DOUBLE PRECISION,
                    yoy_change DOUBLE PRECISION,
                    mom_change DOUBLE PRECISION,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(indicator, period)
                )
            """)
        
        self.log("✅ 数据表检查完成")
    
    async def sync_stocks(self):
        """1. 同步股票基础信息"""
        self.log("\n[1/7] 同步股票基础信息...")
        
        if not self.ts_pro:
            self.log("❌ Tushare Pro 未配置")
            return 0
        
        try:
            df = self.ts_pro.stock_basic(
                exchange='',
                list_status='L',
                fields='ts_code,symbol,name,area,industry,market,list_date'
            )
            
            if df is None or df.empty:
                self.log("❌ 未获取到数据")
                return 0
            
            count = 0
            async with self.db.acquire() as conn:
                for idx, row in df.iterrows():
                    try:
                        code = row['symbol']
                        name = row['name']
                        market = row['market']
                        industry = row['industry']
                        list_date = row['list_date']
                        
                        # 转换日期格式为 date 对象
                        if list_date and len(str(list_date)) == 8:
                            from datetime import date
                            list_date_str = str(list_date)
                            list_date = date(int(list_date_str[:4]), int(list_date_str[4:6]), int(list_date_str[6:]))
                        else:
                            list_date = None
                        
                        await conn.execute("""
                            INSERT INTO stocks (stock_code, stock_name, market, industry, list_date, updated_at)
                            VALUES ($1, $2, $3, $4, $5, NOW())
                            ON CONFLICT (stock_code) DO UPDATE SET
                                stock_name = EXCLUDED.stock_name,
                                market = EXCLUDED.market,
                                industry = EXCLUDED.industry,
                                list_date = EXCLUDED.list_date,
                                updated_at = NOW()
                        """, code, name, market, industry, list_date)
                        
                        count += 1
                    except Exception as e:
                        pass
                    
                    self.progress(idx + 1, len(df), f"已同步 {count}")
            
            print()
            self.log(f"✅ 完成: 同步 {count} 只股票")
            return count
            
        except Exception as e:
            self.log(f"❌ 失败: {e}")
            return 0
    
    async def sync_klines(self, years: int = 5):
        """2. 同步K线数据 - 近N年"""
        self.log(f"\n[2/7] 同步K线数据 (近{years}年)...")
        
        async with self.db.acquire() as conn:
            rows = await conn.fetch("SELECT stock_code FROM stocks ORDER BY stock_code")
            codes = [row['stock_code'] for row in rows]
        
        if not codes:
            self.log("⚠️  没有股票数据")
            return 0
        
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=years*365)).strftime('%Y%m%d')
        
        self.log(f"  时间范围: {start_date[:4]}-{start_date[4:6]}-{start_date[6:]} 至 {end_date[:4]}-{end_date[4:6]}-{end_date[6:]}")
        
        count = 0
        failed = 0
        for i, code in enumerate(codes):
            try:
                ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
                df = self.ts_pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                
                if df is not None and not df.empty:
                    inserted = 0
                    async with self.db.acquire() as conn:
                        from datetime import date
                        for _, row in df.iterrows():
                            trade_date = str(row['trade_date'])
                            # 转换为 date 对象
                            date_obj = date(int(trade_date[:4]), int(trade_date[4:6]), int(trade_date[6:]))
                            
                            result = await conn.fetchrow("""
                                INSERT INTO kline_1d (time, code, open, high, low, close, volume, amount, change_pct, updated_at)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                                ON CONFLICT (time, code) DO UPDATE SET
                                    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                                    close = EXCLUDED.close, volume = EXCLUDED.volume, amount = EXCLUDED.amount,
                                    change_pct = EXCLUDED.change_pct, updated_at = NOW()
                                RETURNING (xmax = 0) AS inserted
                            """, date_obj, code,
                                float(row['open']), float(row['high']), float(row['low']), float(row['close']),
                                int(float(row['vol']) * 100) if row['vol'] else 0,
                                float(row['amount']) * 1000 if row['amount'] else 0,
                                float(row['pct_chg']) if row['pct_chg'] else None)
                            if result and result['inserted']:
                                inserted += 1
                    if inserted > 0:
                        count += 1
                else:
                    failed += 1
                    # 每100个失败打印一次示例
                    if failed <= 3:
                        self.log(f"\n  ⚠️  {code} 无数据")
            except Exception as e:
                failed += 1
                # 打印前几个错误
                if failed <= 3:
                    self.log(f"\n  ❌ {code} 失败: {e}")
            
            self.progress(i + 1, len(codes), f"成功 {count}, 失败 {failed}")
            
            if (i + 1) % 50 == 0:
                await asyncio.sleep(0.5)
        
        print()
        self.log(f"✅ 完成: 同步 {count}/{len(codes)} 只股票")
        return count
    
    async def sync_financials(self, years: int = 5):
        """3. 同步财务数据 - 近N年"""
        self.log(f"\n[3/7] 同步财务数据 (近{years}年)...")
        
        async with self.db.acquire() as conn:
            rows = await conn.fetch("SELECT stock_code FROM stocks ORDER BY stock_code")
            codes = [row['stock_code'] for row in rows]
        
        if not codes:
            return 0
        
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=years*365)).strftime('%Y%m%d')
        
        self.log(f"  时间范围: {start_date[:4]}-{start_date[4:6]}-{start_date[6:]} 至 {end_date[:4]}-{end_date[4:6]}-{end_date[6:]}")
        
        count = 0
        failed = 0
        for i, code in enumerate(codes):
            try:
                ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
                df = self.ts_pro.fina_indicator(ts_code=ts_code, start_date=start_date, end_date=end_date)
                
                if df is not None and not df.empty:
                    inserted = 0
                    async with self.db.acquire() as conn:
                        from datetime import date
                        for _, row in df.iterrows():
                            end_date_str = str(row['end_date'])
                            # 转换为 date 对象
                            report_date = date(int(end_date_str[:4]), int(end_date_str[4:6]), int(end_date_str[6:]))
                            
                            result = await conn.fetchrow("""
                                INSERT INTO financials (stock_code, report_date, revenue, net_profit, roe, debt_ratio, eps, revenue_growth, profit_growth, updated_at)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                                ON CONFLICT (stock_code, report_date) DO UPDATE SET
                                    revenue = EXCLUDED.revenue, net_profit = EXCLUDED.net_profit, roe = EXCLUDED.roe,
                                    debt_ratio = EXCLUDED.debt_ratio, eps = EXCLUDED.eps,
                                    revenue_growth = EXCLUDED.revenue_growth, profit_growth = EXCLUDED.profit_growth,
                                    updated_at = NOW()
                                RETURNING (xmax = 0) AS inserted
                            """, code, report_date,
                                float(row['revenue']) if row['revenue'] else None,
                                float(row['n_income']) if row['n_income'] else None,
                                float(row['roe']) if row['roe'] else None,
                                float(row['debt_to_assets']) if row['debt_to_assets'] else None,
                                float(row['eps']) if row['eps'] else None,
                                float(row['or_yoy']) if row['or_yoy'] else None,
                                float(row['q_profit_yoy']) if row['q_profit_yoy'] else None)
                            if result and result['inserted']:
                                inserted += 1
                    if inserted > 0:
                        count += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                if failed <= 3:
                    self.log(f"\n  ❌ {code} 失败: {e}")
            
            self.progress(i + 1, len(codes), f"成功 {count}, 失败 {failed}")
            
            if (i + 1) % 20 == 0:
                await asyncio.sleep(1)
        
        print()
        self.log(f"✅ 完成: 同步 {count}/{len(codes)} 只股票")
        return count
    
    async def sync_valuations(self):
        """4. 同步估值数据 - 最新"""
        self.log("\n[4/7] 同步估值数据 (PE/PB/市值)...")
        
        async with self.db.acquire() as conn:
            rows = await conn.fetch("SELECT stock_code FROM stocks ORDER BY stock_code")
            codes = [row['stock_code'] for row in rows]
        
        if not codes:
            return 0
        
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
            self.log("⚠️  未找到有效的交易日数据")
            return 0
        
        count = 0
        batch_size = 100
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i+batch_size]
            ts_codes = [f"{c}.SH" if c.startswith('6') else f"{c}.SZ" for c in batch]
            
            try:
                df = self.ts_pro.daily_basic(ts_code=','.join(ts_codes), trade_date=trade_date, fields='ts_code,pe,pb,total_mv')
                
                if df is not None and not df.empty:
                    async with self.db.acquire() as conn:
                        for _, row in df.iterrows():
                            code = row['ts_code'].split('.')[0]
                            pe = float(row['pe']) if row['pe'] and row['pe'] > 0 else None
                            pb = float(row['pb']) if row['pb'] and row['pb'] > 0 else None
                            cap = float(row['total_mv']) if row['total_mv'] and row['total_mv'] > 0 else None
                            
                            await conn.execute("""
                                UPDATE stocks SET pe_ratio = $1, pb_ratio = $2, market_cap = $3, updated_at = NOW()
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
    
    async def sync_dragon_tiger(self, days: int = 365):
        """5. 同步龙虎榜数据 - 近1年"""
        self.log(f"\n[5/7] 同步龙虎榜数据 (近{days}天)...")
        
        from datetime import date
        count = 0
        for i in range(days):
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
            
            self.progress(i + 1, days, f"成功 {count}")
            await asyncio.sleep(0.2)
        
        print()
        self.log(f"✅ 完成: 同步 {count} 条记录")
        return count
    
    async def sync_north_fund(self, days: int = 365):
        """6. 同步北向资金 - 近1年"""
        self.log(f"\n[6/7] 同步北向资金 (近{days}天)...")
        
        try:
            from datetime import date
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
            end_date = datetime.now().strftime('%Y%m%d')
            
            self.log(f"  时间范围: {start_date[:4]}-{start_date[4:6]}-{start_date[6:]} 至 {end_date[:4]}-{end_date[4:6]}-{end_date[6:]}")
            
            df = self.ts_pro.moneyflow_hsgt(start_date=start_date, end_date=end_date)
            
            if df is None or df.empty:
                self.log("⚠️  未获取到数据")
                return 0
            
            count = 0
            async with self.db.acquire() as conn:
                for _, row in df.iterrows():
                    trade_date = str(row['trade_date'])
                    date_obj = date(int(trade_date[:4]), int(trade_date[4:6]), int(trade_date[6:]))
                    
                    await conn.execute("""
                        INSERT INTO north_fund_flow (trade_date, north_money, south_money, net_amount)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (trade_date) DO UPDATE SET
                            north_money = EXCLUDED.north_money,
                            south_money = EXCLUDED.south_money,
                            net_amount = EXCLUDED.net_amount
                    """, date_obj,
                        float(row['north_money']) if row.get('north_money') else None,
                        float(row['south_money']) if row.get('south_money') else None,
                        float(row['net_amount']) if row.get('net_amount') else None)
                    count += 1
            
            self.log(f"✅ 完成: 同步 {count} 条记录")
            return count
            
        except Exception as e:
            self.log(f"❌ 失败: {e}")
            import traceback
            traceback.print_exc()
            return 0
    
    async def sync_macro(self, months: int = 60):
        """7. 同步宏观数据 - 近N个月"""
        self.log(f"\n[7/7] 同步宏观数据 (近{months}个月)...")
        
        count = 0
        try:
            # CPI
            try:
                df_cpi = self.ts_pro.cn_cpi()
                if df_cpi is not None and not df_cpi.empty:
                    async with self.db.acquire() as conn:
                        for _, row in df_cpi.head(months).iterrows():
                            period = str(row['month'])
                            period_str = f"{period[:4]}-{period[4:]}"
                            await conn.execute("""
                                INSERT INTO macro_data (indicator, period, value, yoy_change, mom_change)
                                VALUES ($1, $2, $3, $4, $5)
                                ON CONFLICT (indicator, period) DO UPDATE SET
                                    value = EXCLUDED.value, yoy_change = EXCLUDED.yoy_change, mom_change = EXCLUDED.mom_change
                            """, 'CPI', period_str,
                                float(row['nt_val']) if row.get('nt_val') else None,
                                float(row['nt_yoy']) if row.get('nt_yoy') else None,
                                float(row['nt_mom']) if row.get('nt_mom') else None)
                            count += 1
            except Exception as e:
                self.log(f"⚠️  CPI 同步失败: {e}")
            
            # PPI
            try:
                df_ppi = self.ts_pro.cn_ppi()
                if df_ppi is not None and not df_ppi.empty:
                    async with self.db.acquire() as conn:
                        for _, row in df_ppi.head(months).iterrows():
                            period = str(row['month'])
                            period_str = f"{period[:4]}-{period[4:]}"
                            await conn.execute("""
                                INSERT INTO macro_data (indicator, period, value, yoy_change, mom_change)
                                VALUES ($1, $2, $3, $4, $5)
                                ON CONFLICT (indicator, period) DO UPDATE SET
                                    value = EXCLUDED.value, yoy_change = EXCLUDED.yoy_change, mom_change = EXCLUDED.mom_change
                            """, 'PPI', period_str,
                                float(row['ppi']) if row.get('ppi') else None,
                                float(row['ppi_yoy']) if row.get('ppi_yoy') else None,
                                float(row['ppi_mom']) if row.get('ppi_mom') else None)
                            count += 1
            except Exception as e:
                self.log(f"⚠️  PPI 同步失败: {e}")
            
            # M2
            try:
                df_m2 = self.ts_pro.cn_m()
                if df_m2 is not None and not df_m2.empty:
                    async with self.db.acquire() as conn:
                        for _, row in df_m2.head(months).iterrows():
                            period = str(row['month'])
                            period_str = f"{period[:4]}-{period[4:]}"
                            await conn.execute("""
                                INSERT INTO macro_data (indicator, period, value, yoy_change, mom_change)
                                VALUES ($1, $2, $3, $4, $5)
                                ON CONFLICT (indicator, period) DO UPDATE SET
                                    value = EXCLUDED.value, yoy_change = EXCLUDED.yoy_change, mom_change = EXCLUDED.mom_change
                            """, 'M2', period_str,
                                float(row['m2']) if row.get('m2') else None,
                                float(row['m2_yoy']) if row.get('m2_yoy') else None,
                                float(row['m2_mom']) if row.get('m2_mom') else None)
                            count += 1
            except Exception as e:
                self.log(f"⚠️  M2 同步失败: {e}")
            
            if count > 0:
                self.log(f"✅ 完成: 同步 {count} 条记录")
            else:
                self.log("⚠️  未同步任何宏观数据")
            return count
            
        except Exception as e:
            self.log(f"❌ 失败: {e}")
            import traceback
            traceback.print_exc()
            return 0
    
    async def run(self, years: int = 5):
        """运行完整历史数据同步"""
        self.start_time = datetime.now()
        
        try:
            await self.db.initialize()
            
            if not self.ts_pro:
                self.log("❌ Tushare Pro 未配置，请设置 TUSHARE_TOKEN")
                return
            
            self.log("=" * 80)
            self.log(f"  历史数据同步 - 近{years}年完整数据")
            self.log("=" * 80)
            
            # 创建缺失的表
            await self.create_missing_tables()
            
            # 执行同步
            await self.sync_stocks()
            await self.sync_klines(years=years)
            await self.sync_financials(years=years)
            await self.sync_valuations()
            await self.sync_dragon_tiger(days=365)
            await self.sync_north_fund(days=365)
            await self.sync_macro(months=years*12)
            
            # 总结
            duration = (datetime.now() - self.start_time).total_seconds() / 60
            self.log("\n" + "=" * 80)
            self.log(f"  ✅ 历史数据同步完成 (耗时 {duration:.1f} 分钟)")
            self.log("=" * 80)
            
        except Exception as e:
            self.log(f"\n❌ 同步失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.db.close()


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='历史数据同步脚本')
    parser.add_argument('--years', type=int, default=5, help='同步年数 (默认5年)')
    
    args = parser.parse_args()
    
    sync = HistoricalDataSync()
    await sync.run(years=args.years)


if __name__ == '__main__':
    asyncio.run(main())
