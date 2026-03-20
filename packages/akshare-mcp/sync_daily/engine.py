"""
DailySync 核心引擎 + CLI 入口

组合所有 Mixin，提供:
- DailySync 类（__init__, log, progress, run, ensure_extra_tables）
- main() CLI 入口
"""

import asyncio
import sys
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# 环境初始化
# ---------------------------------------------------------------------------
env_path = Path(__file__).resolve().parent.parent / '.env'
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip()

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))

from akshare_mcp.storage import run_with_db_cleanup
from akshare_mcp.storage.timescaledb import get_db
from akshare_mcp.data_source import data_source

from .stock_sync import StockSyncMixin
from .financial_sync import FinancialSyncMixin
from .market_sync import MarketSyncMixin

logger = logging.getLogger('sync_daily')


class DailySync(StockSyncMixin, FinancialSyncMixin, MarketSyncMixin):
    """日常增量同步管理器

    数据源优先级: Tushare Pro → Baostock → eFinance → AkShare
    """

    def __init__(self):
        self.db = get_db()
        self.ts_pro = data_source.get_tushare_pro()
        self.start_time = None
        self.stats = {}
        self.errors: List[str] = []

    # ---- 日志 / 进度 ----

    def log(self, msg: str):
        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[{ts}] {msg}")

    def progress(self, cur: int, total: int, desc: str = ""):
        if total == 0:
            return
        pct = cur / total * 100
        bar_len = 40
        filled = int(bar_len * cur / total)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r  [{bar}] {pct:5.1f}% ({cur}/{total}) {desc}", end="", flush=True)

    # ---- 数据获取 ----

    def _get_kline_multi_source(self, code: str, period: str = 'daily', limit: int = 250):
        """多数据源获取K线（Tushare → Baostock → eFinance → AkShare）"""
        return data_source.get_kline(code, period, limit)

    # ---- 建表 ----

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
                CREATE TABLE IF NOT EXISTS news_cache (
                    id SERIAL PRIMARY KEY,
                    stock_code TEXT,
                    title TEXT NOT NULL,
                    content TEXT,
                    source TEXT,
                    url TEXT,
                    publish_date TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(title, stock_code)
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

    # ---- 主编排 ----

    async def run(self, skip_klines: bool = False, skip_financials: bool = False,
                  kline_days: int = 250, only: Optional[str] = None):
        """运行日常增量同步

        Args:
            skip_klines: 跳过K线同步
            skip_financials: 跳过财务同步
            kline_days: K线回溯天数
            only: 仅运行指定步骤 (stocks/klines/financials/valuations/dragon_tiger/
                  north_fund/blocks/block_trades/macro/block_stocks)
        """
        self.start_time = datetime.now()

        try:
            await self.db.initialize()

            sources = []
            if self.ts_pro:
                sources.append("Tushare Pro")
            sources.append("AkShare/东财(兜底)")

            self.log("=" * 60)
            self.log(f"  日常增量同步 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            self.log(f"  数据源: {' → '.join(sources)}")
            self.log("=" * 60)

            await self.ensure_extra_tables()

            steps = {
                'stocks': lambda: self.sync_stocks(),
                'klines': lambda: self.sync_klines(days=kline_days),
                'financials': lambda: self.sync_financials(),
                'valuations': lambda: self.sync_valuations(),
                'dragon_tiger': lambda: self.sync_dragon_tiger(),
                'north_fund': lambda: self.sync_north_fund(),
                'blocks': lambda: self.sync_market_blocks(),
                'block_trades': lambda: self.sync_block_trades(),
                'macro': lambda: self.sync_macro(),
                'block_stocks': lambda: self.sync_block_stocks(),
            }

            if only:
                if only in steps:
                    await steps[only]()
                else:
                    self.log(f"❌ 未知步骤: {only}, 可选: {', '.join(steps.keys())}")
                    return
            else:
                await self.sync_stocks()
                if not skip_klines:
                    await self.sync_klines(days=kline_days)
                if not skip_financials:
                    await self.sync_financials()
                await self.sync_valuations()
                await self.sync_dragon_tiger()
                await self.sync_north_fund()
                await self.sync_market_blocks()
                await self.sync_block_trades()
                await self.sync_macro()
                await self.sync_block_stocks()

            duration = (datetime.now() - self.start_time).total_seconds() / 60
            self.log("\n" + "=" * 60)
            self.log(f"  ✅ 同步完成 (耗时 {duration:.1f} 分钟)")
            if self.errors:
                self.log(f"  ⚠️ {len(self.errors)} 个错误")
            self.log("=" * 60)

        except Exception as e:
            self.log(f"\n❌ 同步失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.db.close()


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='日常增量同步（数据源: Tushare Pro→AkShare/东财）'
    )
    parser.add_argument('--skip-klines', action='store_true', help='跳过K线同步')
    parser.add_argument('--skip-financials', action='store_true', help='跳过财务同步')
    parser.add_argument('--kline-days', type=int, default=250, help='K线回溯天数 (默认250)')
    parser.add_argument('--only', type=str, default=None,
                        help='仅运行指定步骤 (stocks/klines/financials/valuations/'
                             'dragon_tiger/north_fund/blocks/block_trades/macro/block_stocks)')

    args = parser.parse_args()

    sync = DailySync()
    await sync.run(
        skip_klines=args.skip_klines,
        skip_financials=args.skip_financials,
        kline_days=args.kline_days,
        only=args.only,
    )


if __name__ == '__main__':
    run_with_db_cleanup(main())
