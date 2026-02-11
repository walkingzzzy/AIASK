"""
TimescaleDB 适配器 — 股票信息 Mixin

提供 get_stock_info / search_stocks 方法。
"""

from typing import Optional, List, Dict, Any


class StockInfoMixin:
    """股票基本信息查询"""

    async def get_stock_info(self, code: str) -> Optional[Dict[str, Any]]:
        """查询股票基本信息"""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    stock_code, stock_name, industry, market_cap,
                    pe_ratio, pb_ratio, list_date
                FROM stocks
                WHERE stock_code = $1
                """,
                code
            )

            if not row:
                return None

            return {
                'code': row['stock_code'],
                'name': row['stock_name'],
                'industry': row['industry'],
                'market_cap': float(row['market_cap']) if row['market_cap'] else None,
                'pe_ratio': float(row['pe_ratio']) if row['pe_ratio'] else None,
                'pb_ratio': float(row['pb_ratio']) if row['pb_ratio'] else None,
                'list_date': row['list_date'].strftime('%Y-%m-%d') if row['list_date'] else None,
            }

    async def search_stocks(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """搜索股票（支持代码和名称）"""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT stock_code, stock_name, industry, market_cap
                FROM stocks
                WHERE stock_code LIKE $1 OR stock_name LIKE $2
                ORDER BY market_cap DESC NULLS LAST
                LIMIT $3
                """,
                f'%{keyword}%', f'%{keyword}%', limit
            )

            return [
                {
                    'code': row['stock_code'],
                    'name': row['stock_name'],
                    'industry': row['industry'],
                    'market_cap': float(row['market_cap']) if row['market_cap'] else None,
                }
                for row in rows
            ]
