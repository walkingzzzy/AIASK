"""
TimescaleDB 适配器 — 财务数据 Mixin

提供 get_financials 方法，兼容 stock_code / code 两种列名。
"""

from typing import List, Dict, Any


class FinancialsMixin:
    """财务数据查询"""

    async def _financials_code_column(self, conn) -> str:
        """兼容历史库：financials 可能用 stock_code 或 code 作为代码列"""
        try:
            rows = await conn.fetch(
                """SELECT column_name FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'financials'"""
            )
            cols = {r["column_name"] for r in rows} if rows else set()
            if "stock_code" in cols:
                return "stock_code"
            if "code" in cols:
                return "code"
        except Exception:
            pass
        return "stock_code"

    async def get_financials(
        self,
        code: str,
        limit: int = 4
    ) -> List[Dict[str, Any]]:
        """查询财务数据"""
        async with self.acquire() as conn:
            code_col = await self._financials_code_column(conn)
            rows = await conn.fetch(
                f"""
                SELECT
                    {code_col}, report_date, revenue, net_profit,
                    roe, debt_ratio, revenue_growth, profit_growth
                FROM financials
                WHERE {code_col} = $1
                ORDER BY report_date DESC
                LIMIT $2
                """,
                code, limit
            )

            return [
                {
                    'code': row[code_col],
                    'report_date': row['report_date'].strftime('%Y-%m-%d') if row['report_date'] else None,
                    'revenue': float(row['revenue']) if row['revenue'] else None,
                    'net_profit': float(row['net_profit']) if row['net_profit'] else None,
                    'roe': float(row['roe']) if row['roe'] else None,
                    'debt_ratio': float(row['debt_ratio']) if row['debt_ratio'] else None,
                    'revenue_growth': float(row['revenue_growth']) if row['revenue_growth'] else None,
                    'profit_growth': float(row['profit_growth']) if row['profit_growth'] else None,
                }
                for row in rows
            ]
