"""研究报告工具（DB版本）— 从 TimescaleDB research_reports 表搜索、分析和汇总。

与 news/research.py（Tushare 外部 API 版本）互补。
"""

from datetime import date, timedelta
from ..utils import ok, fail


def register(mcp):
    @mcp.tool()
    async def search_research_db(keyword: str = None, stock_code: str = None, days: int = 30):
        """从数据库搜索研究报告

        Args:
            keyword: 搜索关键词（标题或摘要）
            stock_code: 股票代码
            days: 查询最近多少天（默认30）
        """
        try:
            from ..storage import get_db
            db = get_db()
            since = date.today() - timedelta(days=days)
            conditions = ["publish_date >= $1"]
            params: list = [since]
            idx = 2

            if stock_code:
                conditions.append(f"code = ${idx}")
                params.append(stock_code.strip())
                idx += 1
            if keyword:
                conditions.append(f"(title ILIKE ${idx} OR summary ILIKE ${idx})")
                params.append(f"%{keyword.strip()}%")
                idx += 1

            where = " AND ".join(conditions)
            query = f"SELECT * FROM research_reports WHERE {where} ORDER BY publish_date DESC LIMIT 50"
            async with db.acquire() as conn:
                rows = await conn.fetch(query, *params)

            reports = [dict(r) for r in rows] if rows else []
            return ok({'reports': reports, 'count': len(reports), 'keyword': keyword, 'stock_code': stock_code})
        except Exception as e:
            return ok({'reports': [], 'count': 0, 'keyword': keyword, 'stock_code': stock_code, 'note': f'DB查询失败: {e}'})

    @mcp.tool()
    async def analyze_research_report(code: str):
        """分析指定股票的最新研究报告

        Args:
            code: 股票代码
        """
        try:
            from ..storage import get_db
            db = get_db()
            async with db.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM research_reports WHERE code = $1 ORDER BY publish_date DESC LIMIT 10",
                    code.strip(),
                )

            reports = [dict(r) for r in rows] if rows else []
            ratings = [r['rating'] for r in reports if r.get('rating')]
            target_prices = [float(r['target_price']) for r in reports if r.get('target_price')]
            institutions = list({r['institution'] for r in reports if r.get('institution')})

            analysis = {
                'code': code,
                'report_count': len(reports),
                'latest_reports': reports[:5],
                'rating_distribution': {r: ratings.count(r) for r in set(ratings)} if ratings else {},
                'avg_target_price': round(sum(target_prices) / len(target_prices), 2) if target_prices else None,
                'institutions': institutions[:10],
                'signals': [],
            }
            return ok(analysis)
        except Exception as e:
            return ok({
                'code': code,
                'report_count': 0,
                'latest_reports': [],
                'rating_distribution': {},
                'avg_target_price': None,
                'institutions': [],
                'signals': [],
                'note': f'DB查询失败: {e}',
            })

    @mcp.tool()
    async def get_research_summary(code: str, limit: int = 10):
        """获取指定股票的研报摘要列表

        Args:
            code: 股票代码
            limit: 返回数量上限（默认10）
        """
        try:
            from ..storage import get_db
            db = get_db()
            async with db.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT title, rating, target_price, institution, analyst, publish_date, summary "
                    "FROM research_reports WHERE code = $1 ORDER BY publish_date DESC LIMIT $2",
                    code.strip(), min(limit, 50),
                )

            summaries = [dict(r) for r in rows] if rows else []
            return ok({'code': code, 'summaries': summaries, 'count': len(summaries)})
        except Exception as e:
            return ok({'code': code, 'summaries': [], 'count': 0, 'note': f'DB查询失败: {e}'})
