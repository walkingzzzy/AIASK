"""
TimescaleDB 适配器 — 实时行情与统计 Mixin

提供 save_quote / get_stats 方法。
"""

from typing import Dict, Any
from datetime import datetime


class QuotesMixin:
    """实时行情保存与数据库统计"""

    async def save_quote(self, quote: Dict[str, Any]) -> None:
        """保存实时行情（统一字段映射）

        字段映射规则（对齐Node版本）：
        - prev_close（标准） ← pre_close（兼容）
        - change_amt（标准） ← change（兼容）
        - mkt_cap（标准） ← market_cap（兼容）
        """
        async with self.acquire() as conn:
            normalized_quote = {
                'code': quote.get('code'),
                'name': quote.get('name'),
                'price': quote.get('price'),
                'change_amt': quote.get('change_amt') or quote.get('change'),
                'change_pct': quote.get('change_pct'),
                'open': quote.get('open'),
                'high': quote.get('high'),
                'low': quote.get('low'),
                'prev_close': quote.get('prev_close') or quote.get('pre_close'),
                'volume': quote.get('volume'),
                'amount': quote.get('amount'),
                'pe': quote.get('pe'),
                'pb': quote.get('pb'),
                'mkt_cap': quote.get('mkt_cap') or quote.get('market_cap'),
            }

            await conn.execute(
                """
                INSERT INTO stock_quotes (
                    time, code, name, price, change_amt, change_pct,
                    open, high, low, prev_close, volume, amount,
                    pe, pb, mkt_cap
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                ON CONFLICT (time, code) DO UPDATE SET
                    name = EXCLUDED.name,
                    price = EXCLUDED.price,
                    change_amt = EXCLUDED.change_amt,
                    change_pct = EXCLUDED.change_pct,
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    prev_close = EXCLUDED.prev_close,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount,
                    pe = EXCLUDED.pe,
                    pb = EXCLUDED.pb,
                    mkt_cap = EXCLUDED.mkt_cap
                """,
                datetime.now(),
                normalized_quote['code'],
                normalized_quote['name'],
                normalized_quote['price'],
                normalized_quote['change_amt'],
                normalized_quote['change_pct'],
                normalized_quote['open'],
                normalized_quote['high'],
                normalized_quote['low'],
                normalized_quote['prev_close'],
                normalized_quote['volume'],
                normalized_quote['amount'],
                normalized_quote['pe'],
                normalized_quote['pb'],
                normalized_quote['mkt_cap']
            )

    async def get_stats(self) -> Dict[str, int]:
        """获取数据库统计信息"""
        async with self.acquire() as conn:
            stock_count = await conn.fetchval("SELECT COUNT(*) FROM stocks")
            kline_count = await conn.fetchval("SELECT COUNT(*) FROM kline_1d")
            financial_count = await conn.fetchval("SELECT COUNT(*) FROM financials")
            quote_count = await conn.fetchval("SELECT COUNT(*) FROM stock_quotes")

            return {
                'stock_count': stock_count or 0,
                'kline_count': kline_count or 0,
                'financial_count': financial_count or 0,
                'quote_count': quote_count or 0,
            }
