#!/usr/bin/env python3
"""
首次部署 / 历史数据深度同步脚本（合并版）

用于初始化数据库并回填近N年的完整历史数据。
日常使用请用 sync_daily.py。

数据源优先级: Tushare Pro → 公开数据源

同步数据清单（10类，深度回填）:
1.  股票基础信息 (stocks)
2.  K线数据 (kline_1d) — 近N年全量
3.  财务数据 (financials) — 近N年全量
4.  估值数据 (stocks.pe_ratio/pb_ratio/market_cap)
5.  龙虎榜 (dragon_tiger_list) — 近1年
6.  北向资金 (north_fund_flow) — 近1年
7.  板块数据 (market_blocks) — 行业+概念
8.  大宗交易 (block_trades) — 近1年
9.  宏观数据 (macro_data) — 近N年
10. 板块成分股 (block_stocks)

用法:
    python sync_init.py                # 默认回填5年
    python sync_init.py --years 3      # 回填3年
    python sync_init.py --years 10     # 回填10年
"""

import asyncio
import sys
import os
import logging
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# 环境初始化
# ---------------------------------------------------------------------------
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from akshare_mcp.storage import run_with_db_cleanup
from akshare_mcp.storage.timescaledb import get_db
from akshare_mcp.data_source import data_source

logger = logging.getLogger('sync_init')


# ---------------------------------------------------------------------------
# 工具函数（与 sync_daily.py 相同）
# ---------------------------------------------------------------------------

def _to_ts_code(code: str) -> str:
    if code.startswith('6'):
        return f"{code}.SH"
    elif code.startswith(('0', '3')):
        return f"{code}.SZ"
    return f"{code}.BJ"


def _to_date(s: str) -> Optional[date]:
    try:
        s = str(s).strip()
        if len(s) >= 8:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except (ValueError, TypeError):
        pass
    return None


def _safe_float(v) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
        if f != f:
            return None
        return f
    except (ValueError, TypeError):
        return None


def _safe_int(v) -> Optional[int]:
    f = _safe_float(v)
    return int(f) if f is not None else None


# ---------------------------------------------------------------------------
# 主同步类
# ---------------------------------------------------------------------------

class InitSync:
    """首次部署 / 历史深度同步

    与 DailySync 的区别:
    - K线/财务回填N年全量（而非增量）
    - 龙虎榜/北向资金/大宗交易回填1年
    - 宏观数据回填N年
    """

    def __init__(self):
        self.db = get_db()
        self.ts_pro = data_source.get_tushare_pro()
        self.start_time = None

    def _safe_print(self, text: str, end: str = "\n", flush: bool = False):
        """安全输出：避免 Windows/GBK 控制台因特殊字符报编码错误。"""
        try:
            print(text, end=end, flush=flush)
        except UnicodeEncodeError:
            enc = getattr(sys.stdout, 'encoding', None) or 'utf-8'
            safe_text = text.encode(enc, errors='replace').decode(enc, errors='replace')
            print(safe_text, end=end, flush=flush)

    def log(self, msg: str):
        ts = datetime.now().strftime('%H:%M:%S')
        self._safe_print(f"[{ts}] {msg}")

    def progress(self, cur: int, total: int, desc: str = ""):
        if total == 0:
            return
        pct = cur / total * 100
        bar_len = 40
        filled = int(bar_len * cur / total)
        # 使用 ASCII 进度条，避免 GBK 环境输出异常
        bar = "#" * filled + "-" * (bar_len - filled)
        self._safe_print(f"\r  [{bar}] {pct:5.1f}% ({cur}/{total}) {desc}", end="", flush=True)

    # ==================================================================
    # 1. 股票基础信息（同 daily）
    # ==================================================================

    async def sync_stocks(self):
        self.log("\n[1/10] 同步股票基础信息...")

        if self.ts_pro:
            try:
                df = self.ts_pro.stock_basic(
                    exchange='', list_status='L',
                    fields='ts_code,symbol,name,area,industry,market,list_date'
                )
                if df is not None and not df.empty:
                    count = 0
                    errors = []
                    async with self.db.acquire() as conn:
                        for idx, row in df.iterrows():
                            try:
                                await conn.execute("""
                                    INSERT INTO stocks (code, stock_name, market, industry, list_date, updated_at)
                                    VALUES ($1,$2,$3,$4,$5,NOW())
                                    ON CONFLICT (code) DO UPDATE SET
                                        stock_name=EXCLUDED.stock_name, market=EXCLUDED.market,
                                        industry=EXCLUDED.industry, list_date=EXCLUDED.list_date, updated_at=NOW()
                                """, row['symbol'], row['name'], row.get('market'),
                                    row.get('industry'), _to_date(row.get('list_date')))
                                count += 1
                            except Exception as e:
                                errors.append(str(e))
                            self.progress(idx + 1, len(df), f"已同步 {count}")
                    print()
                    if errors:
                        self.log(f"  ⚠️ {len(errors)} 条失败")
                    self.log(f"  ✅ 完成: {count} 只股票")
                    return count
            except Exception as e:
                self.log(f"  ❌ Tushare Pro 失败: {e}")

        self.log("  ❌ 需要 Tushare Pro 进行首次初始化")
        return 0

    # ==================================================================
    # 2. K线数据（全量回填N年）
    # ==================================================================

    async def sync_klines(self, years: int = 5):
        """全量回填K线（Tushare Pro → Baostock → eFinance）"""
        self.log(f"\n[2/10] 同步K线数据 (近{years}年全量)...")

        async with self.db.acquire() as conn:
            rows = await conn.fetch("SELECT code FROM stocks ORDER BY code")
            codes = [r['code'] for r in rows]

        if not codes:
            self.log("  ⚠️ 无股票数据")
            return 0

        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=years * 365)).strftime('%Y%m%d')
        self.log(f"  范围: {start_date[:4]}-{start_date[4:6]}-{start_date[6:]} → {end_date[:4]}-{end_date[4:6]}-{end_date[6:]}")

        count = 0
        failed = 0
        errors = []

        for i, code in enumerate(codes):
            klines = []

            # --- 多源聚合链路 ---
            try:
                klines = data_source.get_kline(code, 'daily', years * 250)
            except Exception:
                klines = []

            # --- Tushare Pro ---
            if not klines and self.ts_pro:
                try:
                    ts_code = _to_ts_code(code)
                    df = self.ts_pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                    if df is not None and not df.empty:
                        df = df.iloc[::-1]  # 按日期正序
                        klines = []
                        for _, row in df.iterrows():
                            td = str(row['trade_date'])
                            klines.append({
                                'date': f"{td[:4]}-{td[4:6]}-{td[6:]}",
                                'open': _safe_float(row['open']),
                                'high': _safe_float(row['high']),
                                'low': _safe_float(row['low']),
                                'close': _safe_float(row['close']),
                                'volume': _safe_int(float(row['vol']) * 100) if row.get('vol') else 0,
                                'amount': _safe_float(row['amount']) * 1000 if row.get('amount') else None,
                                'change_pct': _safe_float(row.get('pct_chg')),
                            })
                except Exception as e:
                    errors.append(f"{code}: {e}")

            # 写入DB
            if klines:
                try:
                    payload = []
                    for kl in klines:
                        d = kl.get('date', '')[:10]
                        if not d:
                            continue
                        payload.append({
                            'date': d,
                            'open': _safe_float(kl.get('open')),
                            'high': _safe_float(kl.get('high')),
                            'low': _safe_float(kl.get('low')),
                            'close': _safe_float(kl.get('close')),
                            'volume': _safe_int(kl.get('volume')) or 0,
                            'amount': _safe_float(kl.get('amount')),
                            'change_pct': _safe_float(kl.get('change_pct')),
                        })
                    if payload:
                        await self.db.save_klines(code, payload)
                    count += 1
                except Exception as e:
                    errors.append(f"{code}(write): {e}")
                    failed += 1
            else:
                failed += 1

            self.progress(i + 1, len(codes), f"成功 {count}, 失败 {failed}")
            if (i + 1) % 50 == 0:
                await asyncio.sleep(0.3)

        print()
        if errors:
            self.log(f"  ⚠️ {len(errors)} 只失败, 前5: {errors[:5]}")
        self.log(f"  ✅ 完成: {count}/{len(codes)} 只股票")
        return count

    # ==================================================================
    # 3. 财务数据（全量回填N年）
    # ==================================================================

    async def sync_financials(self, years: int = 5):
        """全量回填财务数据（Tushare Pro）"""
        self.log(f"\n[3/10] 同步财务数据 (近{years}年)...")

        async with self.db.acquire() as conn:
            rows = await conn.fetch("SELECT code FROM stocks ORDER BY code")
            codes = [r['code'] for r in rows]

        if not codes:
            return 0

        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=years * 365)).strftime('%Y%m%d')

        count = 0
        failed = 0
        errors = []

        for i, code in enumerate(codes):
            if self.ts_pro:
                try:
                    ts_code = _to_ts_code(code)
                    df = self.ts_pro.fina_indicator(ts_code=ts_code, start_date=start_date, end_date=end_date)

                    if df is not None and not df.empty:
                        async with self.db.acquire() as conn:
                            for _, row in df.iterrows():
                                report_date = _to_date(row['end_date'])
                                if not report_date:
                                    continue
                                await conn.execute("""
                                    INSERT INTO financials (code, report_date, revenue, net_profit, roe,
                                        debt_ratio, eps, revenue_growth, profit_growth, updated_at)
                                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
                                    ON CONFLICT (code, report_date) DO UPDATE SET
                                        revenue=EXCLUDED.revenue, net_profit=EXCLUDED.net_profit, roe=EXCLUDED.roe,
                                        debt_ratio=EXCLUDED.debt_ratio, eps=EXCLUDED.eps,
                                        revenue_growth=EXCLUDED.revenue_growth, profit_growth=EXCLUDED.profit_growth,
                                        updated_at=NOW()
                                """, code, report_date,
                                    _safe_float(row.get('revenue')),
                                    _safe_float(row.get('n_income')),
                                    _safe_float(row.get('roe')),
                                    _safe_float(row.get('debt_to_assets')),
                                    _safe_float(row.get('eps')),
                                    _safe_float(row.get('or_yoy')),
                                    _safe_float(row.get('q_profit_yoy')))
                        count += 1
                    else:
                        failed += 1
                except Exception as e:
                    failed += 1
                    errors.append(f"{code}: {e}")

            self.progress(i + 1, len(codes), f"成功 {count}, 失败 {failed}")
            if (i + 1) % 20 == 0:
                await asyncio.sleep(1)

        print()
        if errors:
            self.log(f"  ⚠️ {len(errors)} 只失败, 前5: {errors[:5]}")
        self.log(f"  ✅ 完成: {count}/{len(codes)} 只股票")
        return count

    # ==================================================================
    # 4-10: 复用 DailySync 的逻辑（导入使用）
    # ==================================================================

    async def sync_valuations(self):
        """同估值（同 daily）"""
        from sync_daily import DailySync
        ds = DailySync.__new__(DailySync)
        ds.db = self.db
        ds.ts_pro = self.ts_pro
        ds.log = self.log
        ds.progress = self.progress
        return await ds.sync_valuations()

    async def sync_dragon_tiger(self, days: int = 365):
        """龙虎榜（回填1年）"""
        self.log(f"\n[5/10] 同步龙虎榜 (近{days}天)...")

        if not self.ts_pro:
            self.log("  ⚠️ 需要 Tushare Pro")
            return 0

        count = 0
        errors = []
        for i in range(days):
            date_obj = (datetime.now() - timedelta(days=i)).date()
            date_str = date_obj.strftime('%Y%m%d')
            try:
                df = self.ts_pro.top_list(trade_date=date_str)
                if df is not None and not df.empty:
                    async with self.db.acquire() as conn:
                        for _, row in df.iterrows():
                            try:
                                await conn.execute("""
                                    INSERT INTO dragon_tiger_list (trade_date, stock_code, stock_name,
                                        close_price, change_pct, net_amount, reason)
                                    VALUES ($1,$2,$3,$4,$5,$6,$7)
                                    ON CONFLICT (trade_date, stock_code) DO NOTHING
                                """, date_obj,
                                    row['ts_code'].split('.')[0], row.get('name'),
                                    _safe_float(row.get('close')),
                                    _safe_float(row.get('pct_chg')),
                                    _safe_float(row.get('net_amount')),
                                    row.get('reason'))
                                count += 1
                            except Exception:
                                pass
            except Exception as e:
                errors.append(f"{date_str}: {e}")
            self.progress(i + 1, days, f"成功 {count}")
            await asyncio.sleep(0.2)

        print()
        if errors:
            self.log(f"  ⚠️ {len(errors)} 天失败")
        self.log(f"  ✅ 完成: {count} 条")
        return count

    async def sync_north_fund(self, days: int = 365):
        """北向资金（回填1年）"""
        self.log(f"\n[6/10] 同步北向资金 (近{days}天)...")

        if not self.ts_pro:
            self.log("  ⚠️ 需要 Tushare Pro")
            return 0

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
        end_date = datetime.now().strftime('%Y%m%d')

        try:
            df = self.ts_pro.moneyflow_hsgt(start_date=start_date, end_date=end_date)
            if df is None or df.empty:
                self.log("  ⚠️ 无数据")
                return 0

            count = 0
            async with self.db.acquire() as conn:
                for _, row in df.iterrows():
                    d = _to_date(row['trade_date'])
                    if not d:
                        continue
                    await conn.execute("""
                        INSERT INTO north_fund_flow (trade_date, north_money, south_money, net_amount)
                        VALUES ($1,$2,$3,$4)
                        ON CONFLICT (trade_date) DO UPDATE SET
                            north_money=EXCLUDED.north_money, south_money=EXCLUDED.south_money,
                            net_amount=EXCLUDED.net_amount
                    """, d,
                        _safe_float(row.get('north_money')),
                        _safe_float(row.get('south_money')),
                        _safe_float(row.get('net_amount')))
                    count += 1
            self.log(f"  ✅ 完成: {count} 条")
            return count
        except Exception as e:
            self.log(f"  ❌ 失败: {e}")
            return 0

    async def sync_market_blocks(self):
        """板块（同 daily）"""
        from sync_daily import DailySync
        ds = DailySync.__new__(DailySync)
        ds.db = self.db
        ds.ts_pro = self.ts_pro
        ds.log = self.log
        ds.progress = self.progress
        return await ds.sync_market_blocks()

    async def sync_block_trades(self, days: int = 365):
        """大宗交易（回填1年）"""
        self.log(f"\n[8/10] 同步大宗交易 (近{days}天)...")

        if not self.ts_pro:
            self.log("  ⚠️ 需要 Tushare Pro")
            return 0

        count = 0
        for i in range(days):
            date_str = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
            date_obj = _to_date(date_str)
            try:
                df = self.ts_pro.block_trade(trade_date=date_str)
                if df is not None and not df.empty:
                    async with self.db.acquire() as conn:
                        for _, row in df.iterrows():
                            code = row['ts_code'].split('.')[0]
                            await conn.execute("""
                                INSERT INTO block_trades (code, trade_date, trade_price, trade_amount, buyer, seller)
                                VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING
                            """, code, date_obj,
                                _safe_float(row.get('price')),
                                _safe_float(row.get('vol')),
                                row.get('buyer'), row.get('seller'))
                            count += 1
            except Exception as e:
                if 'permission' in str(e).lower() or '权限' in str(e).lower():
                    self.log(f"  ⚠️ 权限不足，跳过")
                    break
            self.progress(i + 1, days, f"成功 {count}")
            await asyncio.sleep(0.2)

        print()
        self.log(f"  ✅ 完成: {count} 条")
        return count

    async def sync_macro(self, years: int = 5):
        """宏观数据（回填N年）"""
        self.log(f"\n[9/10] 同步宏观数据 (近{years}年)...")
        months = years * 12
        count = 0

        if self.ts_pro:
            for indicator, api_func, period_key, val_key, yoy_key, mom_key in [
                ('CPI', 'cn_cpi', 'month', 'nt_val', 'nt_yoy', 'nt_mom'),
                ('PPI', 'cn_ppi', 'month', 'ppi', 'ppi_yoy', 'ppi_mom'),
                ('M2', 'cn_m', 'month', 'm2', 'm2_yoy', 'm2_mom'),
            ]:
                try:
                    df = getattr(self.ts_pro, api_func)()
                    if df is not None and not df.empty:
                        async with self.db.acquire() as conn:
                            for _, row in df.head(months).iterrows():
                                period = str(row[period_key])
                                period_str = f"{period[:4]}-{period[4:]}"
                                await conn.execute("""
                                    INSERT INTO macro_data (indicator, period, value, yoy_change, mom_change)
                                    VALUES ($1,$2,$3,$4,$5)
                                    ON CONFLICT (indicator, period) DO UPDATE SET
                                        value=EXCLUDED.value, yoy_change=EXCLUDED.yoy_change,
                                        mom_change=EXCLUDED.mom_change
                                """, indicator, period_str,
                                    _safe_float(row.get(val_key)),
                                    _safe_float(row.get(yoy_key)),
                                    _safe_float(row.get(mom_key)))
                                count += 1
                except Exception as e:
                    self.log(f"  ⚠️ {indicator} 失败: {e}")

        self.log(f"  ✅ 完成: {count} 条")
        return count

    async def sync_block_stocks(self):
        """板块成分股（同 daily）"""
        from sync_daily import DailySync
        ds = DailySync.__new__(DailySync)
        ds.db = self.db
        ds.ts_pro = self.ts_pro
        ds.log = self.log
        ds.progress = self.progress
        return await ds.sync_block_stocks()

    # ==================================================================
    # 建表
    # ==================================================================

    async def ensure_extra_tables(self):
        """确保同步脚本依赖的额外表存在"""
        async with self.db.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS north_fund_flow (
                    trade_date DATE PRIMARY KEY,
                    north_money DOUBLE PRECISION,
                    south_money DOUBLE PRECISION,
                    net_amount DOUBLE PRECISION,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
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

    # ==================================================================
    # 主入口
    # ==================================================================

    async def run(self, years: int = 5):
        """运行首次部署全量同步"""
        self.start_time = datetime.now()

        try:
            await self.db.initialize()

            sources = []
            if self.ts_pro:
                sources.append("Tushare Pro")
            sources.append("东财直接API(兜底)")

            if not self.ts_pro:
                self.log("❌ 首次初始化至少需要配置 Tushare Pro")
                self.log("   请设置 TUSHARE_TOKEN 环境变量")
                return

            self.log("=" * 70)
            self.log(f"  首次部署 — 历史数据深度同步 (近{years}年)")
            self.log(f"  数据源: {' → '.join(sources)}")
            self.log("=" * 70)

            await self.ensure_extra_tables()

            await self.sync_stocks()
            await self.sync_klines(years=years)
            await self.sync_financials(years=years)
            await self.sync_valuations()
            await self.sync_dragon_tiger(days=365)
            await self.sync_north_fund(days=365)
            await self.sync_market_blocks()
            await self.sync_block_trades(days=365)
            await self.sync_macro(years=years)
            await self.sync_block_stocks()

            duration = (datetime.now() - self.start_time).total_seconds() / 60
            self.log("\n" + "=" * 70)
            self.log(f"  ✅ 历史数据同步完成 (耗时 {duration:.1f} 分钟)")
            self.log("=" * 70)

        except Exception as e:
            self.log(f"\n❌ 同步失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.db.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='首次部署 / 历史深度同步（数据源: Tushare Pro→东财API）'
    )
    parser.add_argument('--years', type=int, default=5, help='回填年数 (默认5年)')

    args = parser.parse_args()

    sync = InitSync()
    await sync.run(years=args.years)


if __name__ == '__main__':
    run_with_db_cleanup(main())
