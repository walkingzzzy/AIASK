"""
TimescaleDB 适配器 — K线数据 Mixin

提供 get_klines / save_klines 方法。
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, date


class KlineMixin:
    """K线数据读写"""

    async def get_klines(
        self,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """查询K线数据

        Args:
            code: 股票代码
            start_date: 开始日期 (YYYY-MM-DD 或 YYYY)
            end_date: 结束日期 (YYYY-MM-DD 或 YYYY)
            limit: 限制返回条数
        """
        async with self.acquire() as conn:
            query = """
                SELECT
                    time, code, open, high, low, close,
                    volume, amount, turnover, change_pct
                FROM kline_1d
                WHERE code = $1
            """
            params: list = [code]
            param_idx = 2

            if start_date:
                if isinstance(start_date, str):
                    if len(start_date) == 4:
                        start_date = f"{start_date}-01-01"
                    start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                    query += f" AND time >= ${param_idx}::date"
                    params.append(start_date_obj)
                    param_idx += 1

            if end_date:
                if isinstance(end_date, str):
                    if len(end_date) == 4:
                        end_date = f"{end_date}-12-31"
                    end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                    query += f" AND time <= ${param_idx}::date"
                    params.append(end_date_obj)
                    param_idx += 1

            query += " ORDER BY time DESC"

            if limit:
                query += f" LIMIT ${param_idx}"
                params.append(limit)

            rows = await conn.fetch(query, *params)

            return [
                {
                    'date': row['time'].strftime('%Y-%m-%d') if isinstance(row['time'], (datetime, date)) else str(row['time']),
                    'code': row['code'],
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'volume': int(row['volume']),
                    'amount': float(row['amount']) if row['amount'] else None,
                    'turnover': float(row['turnover']) if row['turnover'] else None,
                    'change_pct': float(row['change_pct']) if row['change_pct'] else None,
                }
                for row in rows
            ]

    async def save_klines(self, code_or_klines, klines: Optional[List[Dict[str, Any]]] = None) -> int:
        """批量保存K线数据

        Args:
            code_or_klines: 兼容参数。支持 save_klines(klines) 和 save_klines(code, klines)
            klines: K线数据列表（当第一个参数是 code 时使用）

        Returns:
            插入/更新的行数
        """
        from datetime import datetime as _dt, date as _date

        if klines is None:
            code = None
            klines_list = code_or_klines
        else:
            code = str(code_or_klines) if code_or_klines is not None else None
            klines_list = klines

        if not klines_list:
            return 0

        if code:
            for k in klines_list:
                if isinstance(k, dict) and not k.get("code"):
                    k["code"] = code

        def _parse_date(val):
            """安全解析日期，兼容多种格式"""
            if isinstance(val, (_dt, _date)):
                return val
            if isinstance(val, str):
                val = val.strip()[:10]
                for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
                    try:
                        return _dt.strptime(val, fmt)
                    except ValueError:
                        continue
            return None

        async with self.acquire() as conn:
            query = """
                INSERT INTO kline_1d (
                    time, code, open, high, low, close,
                    volume, amount, turnover, change_pct, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                ON CONFLICT (time, code) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount,
                    turnover = EXCLUDED.turnover,
                    change_pct = EXCLUDED.change_pct,
                    updated_at = NOW()
            """

            rows = []
            for k in klines_list:
                parsed_date = _parse_date(k.get('date'))
                if parsed_date is None:
                    continue
                rows.append((
                    parsed_date, k['code'], k['open'], k['high'], k['low'], k['close'],
                    k['volume'], k.get('amount'), k.get('turnover'), k.get('change_pct')
                ))

            if rows:
                await conn.executemany(query, rows)

            return len(rows)
