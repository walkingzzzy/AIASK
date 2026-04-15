"""
股票基础信息 & K线数据同步

DailySync 的 Mixin，提供:
- sync_stocks: 同步股票基础信息
- _save_stocks_df: 保存 Tushare DataFrame 到 DB
- sync_klines: 增量同步K线
"""

import asyncio
from datetime import datetime, timedelta

from akshare_mcp.date_utils import get_latest_trading_date
from akshare_mcp.utils import normalize_code
from .utils import _to_date, _safe_float, _safe_int

_INDEX_CODES = {"000001", "000016", "000300", "000905", "399001", "399005", "399006"}


class StockSyncMixin:
    """股票 & K线同步方法"""

    def _normalize_kline_payload(self, klines):
        payload = []
        for kl in klines or []:
            kl_date = kl.get('date', '')
            if not kl_date:
                continue
            kl_date_str = str(kl_date).strip()
            if len(kl_date_str) == 10:
                normalized_date = kl_date_str
            elif len(kl_date_str) == 8:
                normalized_date = f"{kl_date_str[:4]}-{kl_date_str[4:6]}-{kl_date_str[6:8]}"
            else:
                normalized_date = kl_date_str[:10].replace('/', '-')
            payload.append({
                'date': normalized_date,
                'open': _safe_float(kl.get('open')),
                'high': _safe_float(kl.get('high')),
                'low': _safe_float(kl.get('low')),
                'close': _safe_float(kl.get('close')),
                'volume': _safe_int(kl.get('volume')) or 0,
                'amount': _safe_float(kl.get('amount')),
                'turnover': _safe_float(kl.get('turnover')),
                'change_pct': _safe_float(kl.get('change_pct')),
            })
        return payload

    def _build_tushare_payload(self, df, *, source: str):
        if df is None or df.empty:
            return []
        payload = []
        for _, row in df.iloc[::-1].iterrows():
            trade_date = str(row.get('trade_date') or '')
            if len(trade_date) < 8:
                continue
            amount = _safe_float(row.get('amount'))
            payload.append({
                'date': f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}",
                'open': _safe_float(row.get('open')),
                'high': _safe_float(row.get('high')),
                'low': _safe_float(row.get('low')),
                'close': _safe_float(row.get('close')),
                'volume': _safe_int(row.get('vol')) or 0,
                'amount': amount * 1000 if amount is not None else None,
                'turnover': None,
                'change_pct': _safe_float(row.get('pct_chg')),
                'source': source,
            })
        return payload

    async def _upsert_stock_listing(self, row) -> None:
        code = str(row.get('symbol') or '').strip()
        if not code:
            return
        async with self.db.acquire() as conn:
            await conn.execute("""
                INSERT INTO stocks (code, stock_name, industry, list_date, stock_code, updated_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (code) DO UPDATE SET
                    stock_name = EXCLUDED.stock_name,
                    industry = EXCLUDED.industry,
                    list_date = EXCLUDED.list_date,
                    stock_code = EXCLUDED.stock_code,
                    updated_at = NOW()
            """, code, row.get('name'), row.get('industry'), _to_date(row.get('list_date')), code)

    async def _sync_auxiliary_klines(self, latest_trading_date, days: int):
        if self.ts_pro is None:
            return 0, 0, []

        active_df = self.ts_pro.stock_basic(
            exchange='', list_status='L',
            fields='ts_code,symbol,name,area,industry,market,list_date'
        )
        active_symbols = {}
        if active_df is not None and not active_df.empty:
            for _, active_row in active_df.iterrows():
                symbol = str(active_row.get('symbol') or '').strip()
                if symbol:
                    active_symbols[symbol] = active_row

        async with self.db.acquire() as conn:
            rows = await conn.fetch("""
                WITH latest AS (
                    SELECT code, MAX(time::date) AS max_date
                    FROM kline_1d
                    GROUP BY code
                )
                SELECT l.code, l.max_date
                FROM latest l
                LEFT JOIN stocks s ON s.code = l.code
                WHERE s.code IS NULL
                  AND ($1::date IS NULL OR l.max_date < $1::date)
                ORDER BY l.code
            """, latest_trading_date)

        synced = 0
        skipped = 0
        errors = []
        for row in rows:
            raw_code = str(row['code'])
            last_date = row['max_date']
            normalized = normalize_code(raw_code)
            anchor_date = latest_trading_date or datetime.now().date()
            need_days = days if not last_date else (anchor_date - last_date).days + 5
            limit = min(max(need_days, 5), days)
            payload = []

            try:
                if raw_code.startswith(('sh', 'sz')) or normalized in _INDEX_CODES:
                    ts_code = f"{normalized}.SZ" if normalized.startswith('39') else f"{normalized}.SH"
                    df = self.ts_pro.index_daily(
                        ts_code=ts_code,
                        start_date=(anchor_date - timedelta(days=limit * 2)).strftime('%Y%m%d'),
                        end_date=anchor_date.strftime('%Y%m%d'),
                    )
                    payload = self._build_tushare_payload(df, source='tushare_index')
                elif normalized.startswith('510'):
                    df = self.ts_pro.fund_daily(
                        ts_code=f"{normalized}.SH",
                        start_date=(anchor_date - timedelta(days=limit * 2)).strftime('%Y%m%d'),
                        end_date=anchor_date.strftime('%Y%m%d'),
                    )
                    payload = self._build_tushare_payload(df, source='tushare_fund')
                elif normalized in active_symbols:
                    await self._upsert_stock_listing(active_symbols[normalized])
                    payload = self._normalize_kline_payload(
                        self._get_kline_multi_source(normalized, 'daily', limit)
                    )
                else:
                    skipped += 1
                    continue

                if payload:
                    await self.db.save_klines(raw_code, payload)
                    synced += 1
                else:
                    skipped += 1
            except Exception as exc:
                errors.append(f"{raw_code}: {exc}")

        return synced, skipped, errors

    async def sync_stocks(self):
        """同步股票基础信息（Tushare Pro → AkShare）"""
        self.log("\n[1/10] 同步股票基础信息...")

        # 检查是否需要更新
        async with self.db.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT COUNT(*) as cnt, MAX(updated_at) as last_upd, MAX(list_date) as last_list_date FROM stocks"
            )
            cnt = result['cnt'] if result else 0
            last_upd = result['last_upd'] if result else None
            last_list_date = result['last_list_date'] if result else None

        stock_basic_df = None

        if cnt > 5000 and last_upd:
            days_old = (datetime.now() - last_upd.replace(tzinfo=None)).days
            if days_old <= 7:
                if self.ts_pro:
                    try:
                        stock_basic_df = self.ts_pro.stock_basic(
                            exchange='', list_status='L',
                            fields='ts_code,symbol,name,area,industry,market,list_date'
                        )
                        if stock_basic_df is not None and not stock_basic_df.empty:
                            latest_source_list_date = str(stock_basic_df['list_date'].astype(str).max())
                            latest_db_list_date = last_list_date.strftime('%Y%m%d') if last_list_date else ''
                            if latest_db_list_date and latest_source_list_date <= latest_db_list_date:
                                self.log(f"  ⏭ 已是最新 ({cnt} 只, 更新于 {last_upd.date()})")
                                return 0
                            pending = stock_basic_df[stock_basic_df['list_date'].astype(str) > latest_db_list_date]
                            self.log(f"  ↻ 检测到 {len(pending)} 只新上市/漏同步股票，执行补刷")
                    except Exception as e:
                        self.log(f"  ⚠️ 新股补齐检查失败，继续全量刷新: {e}")
                else:
                    self.log(f"  ⏭ 已是最新 ({cnt} 只, 更新于 {last_upd.date()})")
                    return 0

        # --- 数据源1: Tushare Pro ---
        if self.ts_pro:
            try:
                df = stock_basic_df
                if df is None:
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
                        INSERT INTO stocks (code, stock_name, industry, list_date, stock_code, updated_at)
                        VALUES ($1, $2, $3, $4, $5, NOW())
                        ON CONFLICT (code) DO UPDATE SET
                            stock_name = EXCLUDED.stock_name,
                            industry = EXCLUDED.industry,
                            list_date = EXCLUDED.list_date,
                            stock_code = EXCLUDED.stock_code,
                            updated_at = NOW()
                    """, code, name, industry, list_date, code)
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
        """增量同步K线（Tushare Pro → Baostock → eFinance → AkShare）"""
        self.log(f"\n[2/10] 同步K线数据 (最近{days}天)...")
        latest_trading_date = _to_date(get_latest_trading_date())

        async with self.db.acquire() as conn:
            rows = await conn.fetch("""
                SELECT s.code, MAX(k.time::date) as last_date
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

            # 已到最新交易日才跳过，避免周末/节假日后把上个交易日误判为最新。
            if last_date:
                if latest_trading_date and last_date >= latest_trading_date:
                    skipped += 1
                    self.progress(i + 1, len(rows), f"成功 {count}, 跳过 {skipped}")
                    continue

            # 计算需要回溯的天数
            need_days = days
            if last_date:
                anchor_date = latest_trading_date or datetime.now().date()
                need_days = (anchor_date - last_date).days + 5

            try:
                klines = self._get_kline_multi_source(code, 'daily', min(need_days, days))

                if klines:
                    payload = []
                    for kl in klines:
                        kl_date = kl.get('date', '')
                        if not kl_date:
                            continue
                        kl_date_str = str(kl_date).strip()
                        if len(kl_date_str) == 10:
                            normalized_date = kl_date_str
                        elif len(kl_date_str) == 8:
                            normalized_date = f"{kl_date_str[:4]}-{kl_date_str[4:6]}-{kl_date_str[6:8]}"
                        else:
                            normalized_date = kl_date_str[:10].replace('/', '-')
                        payload.append({
                            'date': normalized_date,
                            'open': _safe_float(kl.get('open')),
                            'high': _safe_float(kl.get('high')),
                            'low': _safe_float(kl.get('low')),
                            'close': _safe_float(kl.get('close')),
                            'volume': _safe_int(kl.get('volume')) or 0,
                            'amount': _safe_float(kl.get('amount')),
                            'turnover': _safe_float(kl.get('turnover')),
                            'change_pct': _safe_float(kl.get('change_pct')),
                        })
                    if payload:
                        await self.db.save_klines(code, payload)
                    count += 1
            except Exception as e:
                errors.append(f"{code}: {e}")

            self.progress(i + 1, len(rows), f"成功 {count}, 跳过 {skipped}")

            # 限流
            if (i + 1) % 50 == 0:
                await asyncio.sleep(0.3)

        print()
        aux_synced, aux_skipped, aux_errors = await self._sync_auxiliary_klines(latest_trading_date, days)
        if aux_synced or aux_skipped or aux_errors:
            self.log(f"  ℹ️ 辅助资产补数: 同步 {aux_synced}，跳过 {aux_skipped}，错误 {len(aux_errors)}")
            errors.extend(aux_errors)

        if errors:
            self.log(f"  ⚠️ {len(errors)} 只失败, 前5: {errors[:5]}")
        self.log(f"  ✅ 完成: 同步 {count} 只, 跳过 {skipped} 只 (已是最新)")
        return count
