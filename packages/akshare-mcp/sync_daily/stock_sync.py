"""
股票基础信息 & K线数据同步

DailySync 的 Mixin，提供:
- sync_stocks: 同步股票基础信息
- _save_stocks_df: 保存 Tushare DataFrame 到 DB
- sync_klines: 增量同步K线
"""

import asyncio
from datetime import datetime

from .utils import _to_date, _safe_float, _safe_int


class StockSyncMixin:
    """股票 & K线同步方法"""

    async def sync_stocks(self):
        """同步股票基础信息（TDX → Tushare Pro → AkShare）"""
        self.log("\n[1/10] 同步股票基础信息...")

        # 检查是否需要更新
        async with self.db.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT COUNT(*) as cnt, MAX(updated_at) as last_upd FROM stocks"
            )
            cnt = result['cnt'] if result else 0
            last_upd = result['last_upd'] if result else None

        if cnt > 5000 and last_upd:
            days_old = (datetime.now() - last_upd.replace(tzinfo=None)).days
            if days_old <= 7:
                self.log(f"  ⏭ 已是最新 ({cnt} 只, 更新于 {last_upd.date()})")
                return 0

        # --- 数据源1: Tushare Pro ---
        if self.ts_pro:
            try:
                df = self.ts_pro.stock_basic(
                    exchange='', list_status='L',
                    fields='ts_code,symbol,name,area,industry,market,list_date'
                )
                if df is not None and not df.empty:
                    return await self._save_stocks_df(df, source='tushare_pro')
            except Exception as e:
                self.log(f"  ⚠️ Tushare Pro 失败: {e}")

        # --- 数据源2: AkShare 兜底 ---
        try:
            import akshare as ak
            df = ak.stock_info_a_code_name()
            if df is not None and not df.empty:
                count = 0
                async with self.db.acquire() as conn:
                    for _, row in df.iterrows():
                        code = str(row.get('code', ''))
                        name = str(row.get('name', ''))
                        if not code or not name:
                            continue
                        try:
                            await conn.execute("""
                                INSERT INTO stocks (code, stock_name, updated_at)
                                VALUES ($1, $2, NOW())
                                ON CONFLICT (code) DO UPDATE SET
                                    stock_name = EXCLUDED.stock_name, updated_at = NOW()
                            """, code, name)
                            count += 1
                        except Exception:
                            pass
                self.log(f"  ✅ AkShare 兜底: {count} 只股票")
                return count
        except Exception as e:
            self.log(f"  ⚠️ AkShare 也失败: {e}")

        self.log("  ❌ 所有数据源均失败")
        return 0

    async def _save_stocks_df(self, df, source: str) -> int:
        """将 Tushare stock_basic DataFrame 写入 DB"""
        count = 0
        errors = []
        async with self.db.acquire() as conn:
            for idx, row in df.iterrows():
                try:
                    code = row['symbol']
                    name = row['name']
                    market = row.get('market')
                    industry = row.get('industry')
                    list_date = _to_date(row.get('list_date'))

                    await conn.execute("""
                        INSERT INTO stocks (code, stock_name, market, industry, list_date, updated_at)
                        VALUES ($1, $2, $3, $4, $5, NOW())
                        ON CONFLICT (code) DO UPDATE SET
                            stock_name = EXCLUDED.stock_name,
                            market = EXCLUDED.market,
                            industry = EXCLUDED.industry,
                            list_date = EXCLUDED.list_date,
                            updated_at = NOW()
                    """, code, name, market, industry, list_date)
                    count += 1
                except Exception as e:
                    errors.append(f"{row.get('symbol','?')}: {e}")

                self.progress(idx + 1, len(df), f"已同步 {count}")

        print()
        if errors:
            self.log(f"  ⚠️ {len(errors)} 条失败, 前3: {errors[:3]}")
        self.log(f"  ✅ 完成 ({source}): {count} 只股票")
        return count

    async def sync_klines(self, days: int = 250):
        """增量同步K线（TDX → Tushare Pro → Baostock → eFinance → AkShare）"""
        self.log(f"\n[2/10] 同步K线数据 (最近{days}天)...")

        async with self.db.acquire() as conn:
            rows = await conn.fetch("""
                SELECT s.code, MAX(k.time) as last_date
                FROM stocks s LEFT JOIN kline_1d k ON s.code = k.code
                GROUP BY s.code ORDER BY s.code
            """)

        if not rows:
            self.log("  ⚠️ 无股票数据，请先同步 stocks")
            return 0

        count = 0
        skipped = 0
        errors = []

        for i, row in enumerate(rows):
            code = row['code']
            last_date = row['last_date']

            # 3天内有数据则跳过
            if last_date:
                days_old = (datetime.now().date() - (last_date.date() if hasattr(last_date, 'date') else last_date)).days
                if days_old <= 3:
                    skipped += 1
                    self.progress(i + 1, len(rows), f"成功 {count}, 跳过 {skipped}")
                    continue

            # 计算需要回溯的天数
            need_days = days
            if last_date:
                need_days = (datetime.now().date() - (last_date.date() if hasattr(last_date, 'date') else last_date)).days + 5

            try:
                klines = self._get_kline_multi_source(code, 'daily', min(need_days, days))

                if klines:
                    async with self.db.acquire() as conn:
                        for kl in klines:
                            kl_date = kl.get('date', '')
                            if not kl_date:
                                continue
                            kl_date_str = str(kl_date).strip()
                            if len(kl_date_str) == 10:  # YYYY-MM-DD
                                dt = _to_date(kl_date_str.replace('-', ''))
                            elif len(kl_date_str) == 8:  # YYYYMMDD
                                dt = _to_date(kl_date_str)
                            else:
                                dt = _to_date(kl_date_str[:10].replace('-', ''))
                            if not dt:
                                continue

                            await conn.execute("""
                                INSERT INTO kline_1d (time, code, open, high, low, close, volume, amount, turnover, change_pct, updated_at)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                                ON CONFLICT (time, code) DO UPDATE SET
                                    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                                    close=EXCLUDED.close, volume=EXCLUDED.volume, amount=EXCLUDED.amount,
                                    turnover=EXCLUDED.turnover, change_pct=EXCLUDED.change_pct, updated_at=NOW()
                            """, dt, code,
                                _safe_float(kl.get('open')), _safe_float(kl.get('high')),
                                _safe_float(kl.get('low')), _safe_float(kl.get('close')),
                                _safe_int(kl.get('volume')) or 0,
                                _safe_float(kl.get('amount')),
                                _safe_float(kl.get('turnover')),
                                _safe_float(kl.get('change_pct')))
                    count += 1
            except Exception as e:
                errors.append(f"{code}: {e}")

            self.progress(i + 1, len(rows), f"成功 {count}, 跳过 {skipped}")

            # 限流
            if (i + 1) % 50 == 0:
                await asyncio.sleep(0.3)

        print()
        if errors:
            self.log(f"  ⚠️ {len(errors)} 只失败, 前5: {errors[:5]}")
        self.log(f"  ✅ 完成: 同步 {count} 只, 跳过 {skipped} 只 (已是最新)")
        return count
