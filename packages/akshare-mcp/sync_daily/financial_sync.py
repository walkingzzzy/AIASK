"""
财务数据 & 估值数据同步

DailySync 的 Mixin，提供:
- sync_financials: 增量同步财务数据
- sync_valuations: 同步估值 PE/PB/市值
- _find_recent_trade_date, _sync_valuations_tushare, _sync_valuations_akshare
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from .utils import _to_ts_code, _to_date, _safe_float


class FinancialSyncMixin:
    """财务 & 估值同步方法"""

    async def sync_financials(self):
        """增量同步财务数据（Tushare Pro → AkShare）"""
        self.log("\n[3/10] 同步财务数据...")

        async with self.db.acquire() as conn:
            rows = await conn.fetch("""
                SELECT s.stock_code, MAX(f.report_date) as last_report
                FROM stocks s LEFT JOIN financials f ON s.stock_code = f.stock_code
                GROUP BY s.stock_code ORDER BY s.stock_code
            """)

        if not rows:
            return 0

        end_date = datetime.now().strftime('%Y%m%d')
        count = 0
        skipped = 0
        errors = []

        for i, row in enumerate(rows):
            code = row['stock_code']
            last_report = row['last_report']

            # 90天内有财报则跳过
            if last_report:
                days_old = (datetime.now().date() - last_report).days
                if days_old <= 90:
                    skipped += 1
                    self.progress(i + 1, len(rows), f"成功 {count}, 跳过 {skipped}")
                    continue

            # --- Tushare Pro ---
            if self.ts_pro:
                try:
                    ts_code = _to_ts_code(code)
                    start_date = (datetime.now() - timedelta(days=730)).strftime('%Y%m%d')
                    df = self.ts_pro.fina_indicator(ts_code=ts_code, start_date=start_date, end_date=end_date)

                    if df is not None and not df.empty:
                        row_data = df.iloc[0]
                        report_date = _to_date(row_data['end_date'])
                        if report_date:
                            async with self.db.acquire() as conn:
                                await conn.execute("""
                                    INSERT INTO financials (code, stock_code, report_date, revenue, net_profit, roe,
                                        debt_ratio, eps, revenue_growth, profit_growth, updated_at)
                                    VALUES ($1,$1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
                                    ON CONFLICT (stock_code, report_date) DO UPDATE SET
                                        revenue=EXCLUDED.revenue, net_profit=EXCLUDED.net_profit, roe=EXCLUDED.roe,
                                        debt_ratio=EXCLUDED.debt_ratio, eps=EXCLUDED.eps,
                                        revenue_growth=EXCLUDED.revenue_growth, profit_growth=EXCLUDED.profit_growth,
                                        updated_at=NOW()
                                """, code, report_date,
                                    _safe_float(row_data.get('revenue')),
                                    _safe_float(row_data.get('n_income')),
                                    _safe_float(row_data.get('roe')),
                                    _safe_float(row_data.get('debt_to_assets')),
                                    _safe_float(row_data.get('eps')),
                                    _safe_float(row_data.get('or_yoy')),
                                    _safe_float(row_data.get('q_profit_yoy')))
                            count += 1
                            self.progress(i + 1, len(rows), f"成功 {count}, 跳过 {skipped}")
                            if (i + 1) % 20 == 0:
                                await asyncio.sleep(1)
                            continue
                except Exception as e:
                    errors.append(f"{code}(tushare): {e}")

            # --- AkShare 兜底 ---
            try:
                import akshare as ak
                df = ak.stock_financial_abstract_ths(symbol=code)
                if df is not None and not df.empty:
                    r = df.iloc[0]
                    report_date = _to_date(str(r.get('报告期', '')).replace('-', ''))
                    if report_date:
                        async with self.db.acquire() as conn:
                            await conn.execute("""
                                INSERT INTO financials (code, stock_code, report_date, eps, roe, updated_at)
                                VALUES ($1,$1,$2,$3,$4,NOW())
                                ON CONFLICT (stock_code, report_date) DO UPDATE SET
                                    eps=EXCLUDED.eps, roe=EXCLUDED.roe, updated_at=NOW()
                            """, code, report_date,
                                _safe_float(r.get('基本每股收益')),
                                _safe_float(r.get('净资产收益率')))
                        count += 1
            except Exception as e:
                errors.append(f"{code}(akshare): {e}")

            self.progress(i + 1, len(rows), f"成功 {count}, 跳过 {skipped}")
            if (i + 1) % 20 == 0:
                await asyncio.sleep(1)

        print()
        if errors:
            self.log(f"  ⚠️ {len(errors)} 只失败, 前5: {errors[:5]}")
        self.log(f"  ✅ 完成: 同步 {count} 只, 跳过 {skipped} 只")
        return count

    async def sync_valuations(self):
        """同步估值 PE/PB/市值（Tushare Pro → AkShare）"""
        self.log("\n[4/10] 同步估值数据...")

        async with self.db.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT COUNT(*) as cnt, MAX(updated_at) as last_upd FROM stocks WHERE pe_ratio IS NOT NULL"
            )
            cnt = result['cnt'] if result else 0
            last_upd = result['last_upd'] if result else None

        if cnt > 4000 and last_upd:
            hours_old = (datetime.now() - last_upd.replace(tzinfo=None)).total_seconds() / 3600
            if hours_old <= 24:
                self.log(f"  ⏭ 已是最新 ({cnt} 只, 更新于 {last_upd.strftime('%m-%d %H:%M')})")
                return 0

        async with self.db.acquire() as conn:
            rows = await conn.fetch("SELECT stock_code FROM stocks ORDER BY stock_code")
            codes = [r['stock_code'] for r in rows]

        if not codes:
            return 0

        # --- Tushare Pro 批量获取 ---
        if self.ts_pro:
            trade_date = self._find_recent_trade_date()
            if trade_date:
                return await self._sync_valuations_tushare(codes, trade_date)

        # --- AkShare 兜底 ---
        return await self._sync_valuations_akshare(codes)

    def _find_recent_trade_date(self) -> Optional[str]:
        """查找最近的交易日（YYYYMMDD）"""
        for days_back in range(1, 8):
            test_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
            try:
                df = self.ts_pro.daily_basic(ts_code='000001.SZ', trade_date=test_date, fields='ts_code,pe')
                if df is not None and not df.empty:
                    self.log(f"  使用交易日: {test_date[:4]}-{test_date[4:6]}-{test_date[6:]}")
                    return test_date
            except Exception:
                continue
        return None

    async def _sync_valuations_tushare(self, codes: list, trade_date: str) -> int:
        count = 0
        code_set = set(codes)
        try:
            df = self.ts_pro.daily_basic(
                trade_date=trade_date,
                fields='ts_code,pe,pb,total_mv'
            )
            if df is not None and not df.empty:
                async with self.db.acquire() as conn:
                    for idx, row in df.iterrows():
                        ts_code = row.get('ts_code', '')
                        if not ts_code or '.' not in ts_code:
                            continue
                        code = ts_code.split('.')[0]
                        if code not in code_set:
                            continue
                        pe = _safe_float(row.get('pe'))
                        pb = _safe_float(row.get('pb'))
                        cap = _safe_float(row.get('total_mv'))
                        pe = pe if pe and pe > 0 else None
                        pb = pb if pb and pb > 0 else None
                        cap = cap if cap and cap > 0 else None
                        await conn.execute(
                            "UPDATE stocks SET pe_ratio=$1, pb_ratio=$2, market_cap=$3, updated_at=NOW() WHERE stock_code=$4",
                            pe, pb, cap, code)
                        count += 1
                        if (idx + 1) % 500 == 0:
                            self.progress(idx + 1, len(df), f"成功 {count}")
                print()
                self.log(f"  ✅ 完成 (tushare_pro): {count} 只")
            else:
                self.log(f"  ⚠️ Tushare daily_basic 返回空 (trade_date={trade_date})")
        except Exception as e:
            self.log(f"  ⚠️ Tushare 估值失败: {e}")
        return count

    async def _sync_valuations_akshare(self, codes: list) -> int:
        """AkShare 兜底获取估值"""
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return 0
            count = 0
            code_set = set(codes)
            async with self.db.acquire() as conn:
                for _, row in df.iterrows():
                    code = str(row.get('代码', ''))
                    if code not in code_set:
                        continue
                    pe = _safe_float(row.get('市盈率-动态'))
                    pb = _safe_float(row.get('市净率'))
                    cap = _safe_float(row.get('总市值'))
                    if pe or pb or cap:
                        await conn.execute(
                            "UPDATE stocks SET pe_ratio=$1, pb_ratio=$2, market_cap=$3, updated_at=NOW() WHERE stock_code=$4",
                            pe, pb, cap, code)
                        count += 1
            self.log(f"  ✅ 完成 (akshare): {count} 只")
            return count
        except Exception as e:
            self.log(f"  ❌ AkShare 估值失败: {e}")
            return 0
