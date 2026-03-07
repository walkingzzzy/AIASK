"""
市场数据同步（龙虎榜、北向资金、板块、大宗交易、宏观、成分股）

DailySync 的 Mixin，提供:
- sync_dragon_tiger: 龙虎榜
- sync_north_fund: 北向资金
- sync_market_blocks: 板块数据
- sync_block_trades: 大宗交易
- sync_macro: 宏观数据
- sync_block_stocks: 板块成分股
"""

import asyncio
from datetime import datetime, timedelta

from .utils import _to_date, _safe_float


class MarketSyncMixin:
    """市场数据同步方法"""

    async def sync_dragon_tiger(self, days: int = 30):
        """同步龙虎榜（Tushare Pro → AkShare）"""
        self.log(f"\n[5/10] 同步龙虎榜 (最近{days}天)...")

        async with self.db.acquire() as conn:
            result = await conn.fetchrow("SELECT MAX(trade_date) as last_date FROM dragon_tiger_list")
            last_date = result['last_date'] if result else None

        count = 0
        skipped = 0

        for i in range(days):
            date_obj = (datetime.now() - timedelta(days=i)).date()
            date_str = date_obj.strftime('%Y%m%d')

            if last_date and date_obj <= last_date:
                skipped += 1
                self.progress(i + 1, days, f"成功 {count}, 跳过 {skipped}")
                continue

            # --- Tushare Pro ---
            if self.ts_pro:
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
                        self.progress(i + 1, days, f"成功 {count}, 跳过 {skipped}")
                        await asyncio.sleep(0.2)
                        continue
                except Exception:
                    pass

            # --- AkShare 兜底 ---
            try:
                import akshare as ak
                df = ak.stock_lhb_detail_em(start_date=date_str, end_date=date_str)
                if df is not None and not df.empty:
                    async with self.db.acquire() as conn:
                        for _, row in df.iterrows():
                            try:
                                await conn.execute("""
                                    INSERT INTO dragon_tiger_list (trade_date, stock_code, stock_name, reason)
                                    VALUES ($1,$2,$3,$4)
                                    ON CONFLICT (trade_date, stock_code) DO NOTHING
                                """, date_obj,
                                    str(row.get('代码', '')),
                                    str(row.get('名称', '')),
                                    str(row.get('上榜原因', '')))
                                count += 1
                            except Exception:
                                pass
            except Exception:
                pass

            self.progress(i + 1, days, f"成功 {count}, 跳过 {skipped}")
            await asyncio.sleep(0.2)

        print()
        self.log(f"  ✅ 完成: {count} 条, 跳过 {skipped} 天")
        return count

    async def sync_north_fund(self, days: int = 90):
        """同步北向资金（Tushare Pro → AkShare）"""
        self.log(f"\n[6/10] 同步北向资金 (最近{days}天)...")

        async with self.db.acquire() as conn:
            result = await conn.fetchrow("SELECT MAX(trade_date) as last_date FROM north_fund_flow")
            last_date = result['last_date'] if result else None

        if last_date:
            days_old = (datetime.now().date() - last_date).days
            if days_old <= 3:
                self.log(f"  ⏭ 已是最新 (最后: {last_date})")
                return 0
            start_date = (last_date + timedelta(days=1)).strftime('%Y%m%d')
        else:
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

        end_date = datetime.now().strftime('%Y%m%d')

        # --- Tushare Pro ---
        if self.ts_pro:
            try:
                df = self.ts_pro.moneyflow_hsgt(start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
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
                    self.log(f"  ✅ 完成 (tushare_pro): {count} 条")
                    return count
            except Exception as e:
                self.log(f"  ⚠️ Tushare Pro 失败: {e}")

        # --- AkShare 兜底 ---
        try:
            import akshare as ak
            df = ak.stock_hsgt_north_net_flow_in_em()
            if df is not None and not df.empty:
                count = 0
                async with self.db.acquire() as conn:
                    for _, row in df.tail(days).iterrows():
                        try:
                            d = _to_date(str(row.get('日期', '')).replace('-', ''))
                            if not d:
                                continue
                            await conn.execute("""
                                INSERT INTO north_fund_flow (trade_date, net_amount)
                                VALUES ($1,$2)
                                ON CONFLICT (trade_date) DO UPDATE SET net_amount=EXCLUDED.net_amount
                            """, d, _safe_float(row.get('当日净流入')))
                            count += 1
                        except Exception:
                            pass
                self.log(f"  ✅ 完成 (akshare): {count} 条")
                return count
        except Exception as e:
            self.log(f"  ❌ AkShare 也失败: {e}")

        return 0

    async def sync_market_blocks(self):
        """同步行业/概念板块（TDX → Tushare Pro → AkShare）"""
        self.log("\n[7/10] 同步板块数据...")
        count = 0

        # --- 方案A: 从 stocks 表提取行业 ---
        try:
            async with self.db.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT DISTINCT industry FROM stocks
                    WHERE industry IS NOT NULL AND industry != ''
                """)
                for row in rows:
                    industry = row['industry']
                    await conn.execute("""
                        INSERT INTO market_blocks (block_code, block_name, block_type, updated_at)
                        VALUES ($1, $2, 'industry', NOW())
                        ON CONFLICT (block_code, block_type) DO UPDATE SET
                            block_name=EXCLUDED.block_name, updated_at=NOW()
                    """, f"IND_{industry}", industry)
                    count += 1
            self.log(f"  行业板块 (stocks表): {count} 个")
        except Exception as e:
            self.log(f"  ⚠️ 行业提取失败: {e}")

        # --- 方案B: Tushare Pro 概念板块 ---
        concept_count = 0
        if self.ts_pro:
            try:
                df = self.ts_pro.concept()
                if df is not None and not df.empty:
                    async with self.db.acquire() as conn:
                        for _, row in df.iterrows():
                            await conn.execute("""
                                INSERT INTO market_blocks (block_code, block_name, block_type, updated_at)
                                VALUES ($1, $2, 'concept', NOW())
                                ON CONFLICT (block_code, block_type) DO UPDATE SET
                                    block_name=EXCLUDED.block_name, updated_at=NOW()
                            """, str(row.get('code', '')), str(row.get('name', '')))
                            concept_count += 1
                self.log(f"  概念板块 (tushare): {concept_count} 个")
            except Exception as e:
                self.log(f"  ⚠️ Tushare 概念板块失败: {e}")

        # --- 方案C: AkShare 兜底 ---
        if concept_count == 0:
            try:
                import akshare as ak
                df = ak.stock_board_industry_name_em()
                if df is not None and not df.empty:
                    async with self.db.acquire() as conn:
                        for _, row in df.iterrows():
                            await conn.execute("""
                                INSERT INTO market_blocks (block_code, block_name, block_type, updated_at)
                                VALUES ($1, $2, 'industry', NOW())
                                ON CONFLICT (block_code, block_type) DO UPDATE SET
                                    block_name=EXCLUDED.block_name, updated_at=NOW()
                            """, str(row.get('板块代码', '')), str(row.get('板块名称', '')))
                            concept_count += 1
                self.log(f"  行业板块 (akshare): {concept_count} 个")
            except Exception as e:
                self.log(f"  ⚠️ AkShare 板块也失败: {e}")

        total = count + concept_count
        self.log(f"  ✅ 完成: 共 {total} 个板块")
        return total

    async def sync_block_trades(self, days: int = 30):
        """同步大宗交易（Tushare Pro → AkShare）"""
        self.log(f"\n[8/10] 同步大宗交易 (最近{days}天)...")

        if not self.ts_pro:
            self.log("  ⚠️ 需要 Tushare Pro，跳过")
            return 0

        count = 0
        errors = []
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
                                VALUES ($1,$2,$3,$4,$5,$6)
                                ON CONFLICT DO NOTHING
                            """, code, date_obj,
                                _safe_float(row.get('price')),
                                _safe_float(row.get('vol')),
                                row.get('buyer'), row.get('seller'))
                            count += 1
            except Exception as e:
                err_str = str(e).lower()
                if 'permission' in err_str or '权限' in err_str:
                    self.log(f"  ⚠️ 大宗交易接口权限不足，跳过")
                    break
                errors.append(f"{date_str}: {e}")
            self.progress(i + 1, days, f"成功 {count}")
            await asyncio.sleep(0.2)

        print()
        if errors:
            self.log(f"  ⚠️ {len(errors)} 天失败")
        self.log(f"  ✅ 完成: {count} 条大宗交易")
        return count

    async def sync_macro(self):
        """同步宏观数据 CPI/PPI/M2（Tushare Pro → AkShare）"""
        self.log("\n[9/10] 同步宏观数据...")

        async with self.db.acquire() as conn:
            result = await conn.fetchrow("SELECT MAX(period) as last_period FROM macro_data")
            last_period = result['last_period'] if result else None

        if last_period:
            try:
                last_dt = datetime.strptime(last_period, '%Y-%m')
                if (datetime.now() - last_dt).days <= 30:
                    self.log(f"  ⏭ 已是最新 (最后: {last_period})")
                    return 0
            except Exception:
                pass

        count = 0

        # --- Tushare Pro ---
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
                            for _, row in df.head(12).iterrows():
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
                    self.log(f"  ⚠️ {indicator} (tushare) 失败: {e}")

        # --- AkShare 兜底 ---
        if count == 0:
            try:
                import akshare as ak
                for indicator, func_name in [
                    ('CPI', 'macro_china_cpi'),
                    ('PPI', 'macro_china_ppi'),
                ]:
                    try:
                        df = getattr(ak, func_name)()
                        if df is not None and not df.empty:
                            async with self.db.acquire() as conn:
                                for _, row in df.tail(12).iterrows():
                                    period = None
                                    for col in ['月份', '统计时间', '日期']:
                                        if col in row.index:
                                            period = str(row[col])
                                            break
                                    if not period:
                                        continue
                                    value = None
                                    for col in ['今值', '全国', 'CPI', 'PPI']:
                                        if col in row.index:
                                            value = _safe_float(row[col])
                                            if value is not None:
                                                break
                                    if value is None:
                                        continue
                                    await conn.execute("""
                                        INSERT INTO macro_data (indicator, period, value)
                                        VALUES ($1,$2,$3)
                                        ON CONFLICT (indicator, period) DO UPDATE SET value=EXCLUDED.value
                                    """, indicator, period, value)
                                    count += 1
                    except Exception as e:
                        self.log(f"  ⚠️ {indicator} (akshare) 失败: {e}")
            except ImportError:
                pass

        self.log(f"  ✅ 完成: {count} 条宏观数据")
        return count

    async def sync_block_stocks(self):
        """从 stocks 表反向填充 block_stocks（行业→成分股映射）"""
        self.log("\n[10/10] 同步板块成分股...")

        try:
            count = 0
            async with self.db.acquire() as conn:
                stocks = await conn.fetch("""
                    SELECT code as stock_code, stock_name, industry FROM stocks
                    WHERE industry IS NOT NULL AND industry != ''
                """)
                for row in stocks:
                    block_code = f"IND_{row['industry']}"
                    await conn.execute("""
                        INSERT INTO block_stocks (block_code, stock_code, stock_name, updated_at)
                        VALUES ($1, $2, $3, NOW())
                        ON CONFLICT (block_code, stock_code) DO UPDATE SET
                            stock_name=EXCLUDED.stock_name, updated_at=NOW()
                    """, block_code, row['code'], row['stock_name'])
                    count += 1
            self.log(f"  ✅ 完成: {count} 条成分股映射")
            return count
        except Exception as e:
            self.log(f"  ❌ 失败: {e}")
            return 0
