#!/usr/bin/env python3
"""
完整数据同步脚本 - 基于项目实际需求
使用 Tushare Pro 作为主要数据源

同步数据清单:
1. 股票基础信息 (stocks) - 代码、名称、行业、市场、上市日期
2. K线数据 (kline_1d) - 日线OHLCV
3. 财务数据 (financials) - 财报指标
4. 估值数据 (stocks) - PE、PB、市值
5. 实时行情 (stock_quotes) - 最新价格
6. 龙虎榜 (dragon_tiger_list, dragon_tiger_details) - 大单交易
7. 北向资金 (需新建表) - 沪深港通资金流向
8. 板块数据 (market_blocks, block_stocks) - 行业板块
9. 新闻数据 (news_cache) - 公告、新闻
10. 宏观数据 - CPI、PPI、M2等
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


class CompleteDataSync:
    """完整数据同步管理器"""
    
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
            
            # 龙虎榜表 (如果不存在)
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
        """1. 同步股票基础信息 (增量同步)"""
        self.log("\n[1/10] 同步股票基础信息...")
        
        if not self.ts_pro:
            self.log("❌ Tushare Pro 未配置")
            return 0
        
        # 检查是否已有数据且最近更新过
        async with self.db.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT COUNT(*) as count, MAX(updated_at) as last_update 
                FROM stocks
            """)
            stock_count = result['count'] if result else 0
            last_update = result['last_update'] if result else None
        
        # 如果有5000+只股票且7天内更新过，跳过
        if stock_count > 5000 and last_update:
            days_old = (datetime.now() - last_update.replace(tzinfo=None)).days
            if days_old <= 7:
                self.log(f"⚠️  股票基础信息已是最新 ({stock_count} 只股票, 最后更新: {last_update.date()})")
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
    
    async def sync_klines(self, days: int = 250):
        """2. 同步K线数据 (增量同步)"""
        self.log(f"\n[2/10] 同步K线数据 (最近{days}天)...")
        
        async with self.db.acquire() as conn:
            # 获取每只股票最新的K线日期
            rows = await conn.fetch("""
                SELECT s.stock_code, MAX(k.time) as last_date
                FROM stocks s
                LEFT JOIN kline_1d k ON s.stock_code = k.code
                GROUP BY s.stock_code
                ORDER BY s.stock_code
            """)
        
        if not rows:
            self.log("⚠️  没有股票数据")
            return 0
        
        end_date = datetime.now().strftime('%Y%m%d')
        count = 0
        skipped = 0
        
        for i, row in enumerate(rows):
            code = row['stock_code']
            last_date = row['last_date']
            
            # 如果有数据，只同步最新日期之后的
            if last_date:
                # 检查是否需要更新（最新数据是否在3天内）
                days_old = (datetime.now().date() - last_date).days
                if days_old <= 3:
                    skipped += 1
                    self.progress(i + 1, len(rows), f"成功 {count}, 跳过 {skipped}")
                    continue
                
                start_date = (last_date + timedelta(days=1)).strftime('%Y%m%d')
            else:
                start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
            
            try:
                ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
                df = self.ts_pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                
                if df is not None and not df.empty:
                    async with self.db.acquire() as conn:
                        for _, row in df.iterrows():
                            trade_date = row['trade_date']
                            date_str = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
                            
                            await conn.execute("""
                                INSERT INTO kline_1d (time, code, open, high, low, close, volume, amount, change_pct, updated_at)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                                ON CONFLICT (time, code) DO UPDATE SET
                                    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                                    close = EXCLUDED.close, volume = EXCLUDED.volume, amount = EXCLUDED.amount,
                                    change_pct = EXCLUDED.change_pct, updated_at = NOW()
                            """, date_str, code,
                                float(row['open']), float(row['high']), float(row['low']), float(row['close']),
                                int(float(row['vol']) * 100) if row['vol'] else 0,
                                float(row['amount']) * 1000 if row['amount'] else 0,
                                float(row['pct_chg']) if row['pct_chg'] else None)
                    count += 1
            except:
                pass
            
            self.progress(i + 1, len(rows), f"成功 {count}, 跳过 {skipped}")
            
            if (i + 1) % 50 == 0:
                await asyncio.sleep(0.5)
        
        print()
        self.log(f"✅ 完成: 同步 {count} 只股票, 跳过 {skipped} 只 (数据已是最新)")
        return count
    
    async def sync_financials(self):
        """3. 同步财务数据 (增量同步)"""
        self.log("\n[3/10] 同步财务数据...")
        
        async with self.db.acquire() as conn:
            # 获取每只股票最新的财报日期
            rows = await conn.fetch("""
                SELECT s.stock_code, MAX(f.report_date) as last_report
                FROM stocks s
                LEFT JOIN financials f ON s.stock_code = f.stock_code
                GROUP BY s.stock_code
                ORDER BY s.stock_code
            """)
        
        if not rows:
            return 0
        
        end_date = datetime.now().strftime('%Y%m%d')
        count = 0
        skipped = 0
        
        for i, row in enumerate(rows):
            code = row['stock_code']
            last_report = row['last_report']
            
            # 如果有最新财报且在90天内，跳过
            if last_report:
                days_old = (datetime.now().date() - last_report).days
                if days_old <= 90:
                    skipped += 1
                    self.progress(i + 1, len(rows), f"成功 {count}, 跳过 {skipped}")
                    continue
            
            try:
                ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
                start_date = (datetime.now() - timedelta(days=730)).strftime('%Y%m%d')
                df = self.ts_pro.fina_indicator(ts_code=ts_code, start_date=start_date, end_date=end_date)
                
                if df is not None and not df.empty:
                    row_data = df.iloc[0]
                    async with self.db.acquire() as conn:
                        end_date_str = row_data['end_date']
                        report_date = f"{end_date_str[:4]}-{end_date_str[4:6]}-{end_date_str[6:]}"
                        
                        await conn.execute("""
                            INSERT INTO financials (stock_code, report_date, revenue, net_profit, roe, debt_ratio, eps, revenue_growth, profit_growth, updated_at)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                            ON CONFLICT (stock_code, report_date) DO UPDATE SET
                                revenue = EXCLUDED.revenue, net_profit = EXCLUDED.net_profit, roe = EXCLUDED.roe,
                                debt_ratio = EXCLUDED.debt_ratio, eps = EXCLUDED.eps,
                                revenue_growth = EXCLUDED.revenue_growth, profit_growth = EXCLUDED.profit_growth,
                                updated_at = NOW()
                        """, code, report_date,
                            float(row_data['revenue']) if row_data['revenue'] else None,
                            float(row_data['n_income']) if row_data['n_income'] else None,
                            float(row_data['roe']) if row_data['roe'] else None,
                            float(row_data['debt_to_assets']) if row_data['debt_to_assets'] else None,
                            float(row_data['eps']) if row_data['eps'] else None,
                            float(row_data['or_yoy']) if row_data['or_yoy'] else None,
                            float(row_data['q_profit_yoy']) if row_data['q_profit_yoy'] else None)
                    count += 1
            except:
                pass
            
            self.progress(i + 1, len(rows), f"成功 {count}, 跳过 {skipped}")
            
            if (i + 1) % 20 == 0:
                await asyncio.sleep(1)
        
        print()
        self.log(f"✅ 完成: 同步 {count} 只股票, 跳过 {skipped} 只 (财报已是最新)")
        return count
    
    async def sync_valuations(self):
        """4. 同步估值数据 (增量同步)"""
        self.log("\n[4/10] 同步估值数据 (PE/PB/市值)...")
        
        # 检查是否最近更新过估值数据
        async with self.db.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT COUNT(*) as count, MAX(updated_at) as last_update 
                FROM stocks 
                WHERE pe_ratio IS NOT NULL
            """)
            valuation_count = result['count'] if result else 0
            last_update = result['last_update'] if result else None
        
        # 如果有大量估值数据且1天内更新过，跳过
        if valuation_count > 4000 and last_update:
            hours_old = (datetime.now() - last_update.replace(tzinfo=None)).total_seconds() / 3600
            if hours_old <= 24:
                self.log(f"⚠️  估值数据已是最新 ({valuation_count} 只股票, 最后更新: {last_update.strftime('%Y-%m-%d %H:%M')})")
                return 0
        
        async with self.db.acquire() as conn:
            rows = await conn.fetch("SELECT stock_code FROM stocks ORDER BY stock_code")
            codes = [row['stock_code'] for row in rows]
        
        if not codes:
            return 0
        
        # 尝试最近几个交易日的数据
        trade_date = None
        for days_back in range(1, 8):
            test_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
            try:
                # 测试这个日期是否有数据
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
    
    async def sync_dragon_tiger(self, days: int = 30):
        """6. 同步龙虎榜数据 (增量同步)"""
        self.log(f"\n[6/10] 同步龙虎榜数据 (最近{days}天)...")
        
        # 获取最新的龙虎榜日期
        async with self.db.acquire() as conn:
            result = await conn.fetchrow("SELECT MAX(trade_date) as last_date FROM dragon_tiger_list")
            last_date = result['last_date'] if result else None
        
        count = 0
        skipped = 0
        
        for i in range(days):
            date_obj = datetime.now() - timedelta(days=i)
            date = date_obj.strftime('%Y%m%d')
            
            # 如果这个日期已经有数据，跳过
            if last_date and date_obj.date() <= last_date:
                skipped += 1
                self.progress(i + 1, days, f"成功 {count}, 跳过 {skipped}")
                continue
            
            try:
                df = self.ts_pro.top_list(trade_date=date)
                
                if df is not None and not df.empty:
                    async with self.db.acquire() as conn:
                        for _, row in df.iterrows():
                            await conn.execute("""
                                INSERT INTO dragon_tiger_list (trade_date, stock_code, stock_name, close_price, change_pct, net_amount, reason)
                                VALUES ($1, $2, $3, $4, $5, $6, $7)
                                ON CONFLICT (trade_date, stock_code) DO NOTHING
                            """, date[:4]+'-'+date[4:6]+'-'+date[6:],
                                row['ts_code'].split('.')[0], row.get('name'),
                                float(row['close']) if row.get('close') else None,
                                float(row['pct_chg']) if row.get('pct_chg') else None,
                                float(row['net_amount']) if row.get('net_amount') else None,
                                row.get('reason'))
                            count += 1
            except:
                pass
            
            self.progress(i + 1, days, f"成功 {count}, 跳过 {skipped}")
            await asyncio.sleep(0.2)
        
        print()
        self.log(f"✅ 完成: 同步 {count} 条记录, 跳过 {skipped} 天 (已有数据)")
        return count
    
    async def sync_north_fund(self, days: int = 90):
        """7. 同步北向资金 (增量同步)"""
        self.log(f"\n[7/10] 同步北向资金 (最近{days}天)...")
        
        try:
            from datetime import date
            
            # 获取最新的北向资金日期
            async with self.db.acquire() as conn:
                result = await conn.fetchrow("SELECT MAX(trade_date) as last_date FROM north_fund_flow")
                last_date = result['last_date'] if result else None
            
            # 如果有数据且在3天内，只同步最新的
            if last_date:
                days_old = (datetime.now().date() - last_date).days
                if days_old <= 3:
                    self.log(f"⚠️  数据已是最新 (最后更新: {last_date})")
                    return 0
                start_date = (last_date + timedelta(days=1)).strftime('%Y%m%d')
            else:
                start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
            
            end_date = datetime.now().strftime('%Y%m%d')
            
            df = self.ts_pro.moneyflow_hsgt(start_date=start_date, end_date=end_date)
            
            if df is None or df.empty:
                self.log("⚠️  未获取到新数据")
                return 0
            
            count = 0
            async with self.db.acquire() as conn:
                for _, row in df.iterrows():
                    trade_date = str(row['trade_date'])
                    # Convert YYYYMMDD to date object
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
            
            self.log(f"✅ 完成: 同步 {count} 条新记录")
            return count
            
        except Exception as e:
            self.log(f"❌ 失败: {e}")
            import traceback
            traceback.print_exc()
            return 0
    
    async def sync_macro(self):
        """10. 同步宏观数据 (增量同步)"""
        self.log("\n[10/10] 同步宏观数据 (CPI/PPI/M2)...")
        
        # 检查最新的宏观数据日期
        async with self.db.acquire() as conn:
            result = await conn.fetchrow("SELECT MAX(period) as last_period FROM macro_data")
            last_period = result['last_period'] if result else None
        
        if last_period:
            # 如果最新数据在30天内，跳过
            try:
                last_date = datetime.strptime(last_period, '%Y-%m')
                days_old = (datetime.now() - last_date).days
                if days_old <= 30:
                    self.log(f"⚠️  宏观数据已是最新 (最后更新: {last_period})")
                    return 0
            except:
                pass
        
        count = 0
        try:
            # CPI - 使用正确的接口名
            try:
                df_cpi = self.ts_pro.cn_cpi()
                if df_cpi is not None and not df_cpi.empty:
                    async with self.db.acquire() as conn:
                        for _, row in df_cpi.head(12).iterrows():
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
            
            # PPI - 使用正确的接口名
            try:
                df_ppi = self.ts_pro.cn_ppi()
                if df_ppi is not None and not df_ppi.empty:
                    async with self.db.acquire() as conn:
                        for _, row in df_ppi.head(12).iterrows():
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
            
            # M2 - 使用正确的接口名
            try:
                df_m2 = self.ts_pro.cn_m()
                if df_m2 is not None and not df_m2.empty:
                    async with self.db.acquire() as conn:
                        for _, row in df_m2.head(12).iterrows():
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
    
    async def run(self, skip_klines=False, skip_financials=False, kline_days=250):
        """运行完整同步"""
        self.start_time = datetime.now()
        
        try:
            await self.db.initialize()
            
            if not self.ts_pro:
                self.log("❌ Tushare Pro 未配置，请设置 TUSHARE_TOKEN")
                return
            
            self.log("=" * 80)
            self.log("  完整数据同步 - 使用 Tushare Pro")
            self.log("=" * 80)
            
            # 创建缺失的表
            await self.create_missing_tables()
            
            # 执行同步
            await self.sync_stocks()
            
            if not skip_klines:
                await self.sync_klines(days=kline_days)
            
            if not skip_financials:
                await self.sync_financials()
            
            await self.sync_valuations()
            await self.sync_dragon_tiger(days=30)
            await self.sync_north_fund(days=90)
            await self.sync_macro()
            
            # 总结
            duration = (datetime.now() - self.start_time).total_seconds() / 60
            self.log("\n" + "=" * 80)
            self.log(f"  ✅ 数据同步完成 (耗时 {duration:.1f} 分钟)")
            self.log("=" * 80)
            
        except Exception as e:
            self.log(f"\n❌ 同步失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.db.close()


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='完整数据同步脚本')
    parser.add_argument('--skip-klines', action='store_true', help='跳过K线数据')
    parser.add_argument('--skip-financials', action='store_true', help='跳过财务数据')
    parser.add_argument('--kline-days', type=int, default=250, help='K线回溯天数')
    
    args = parser.parse_args()
    
    sync = CompleteDataSync()
    await sync.run(
        skip_klines=args.skip_klines,
        skip_financials=args.skip_financials,
        kline_days=args.kline_days
    )


if __name__ == '__main__':
    asyncio.run(main())
