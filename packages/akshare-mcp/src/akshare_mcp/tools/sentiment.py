"""情绪分析工具"""
from ..services.sentiment import sentiment_analyzer
from ..storage import get_db
from ..utils import ok, fail

def register(mcp):
    @mcp.tool()
    async def analyze_stock_sentiment(code: str):
        try:
            db = get_db()
            klines = await db.get_klines(code, limit=100)

            if not klines:
                return fail('No data')

            result = sentiment_analyzer.analyze_sentiment(klines)
            result['code'] = code

            return ok(result)
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def calculate_fear_greed_index():
        """计算市场恐惧贪婪指数（基于上证指数K线和涨跌停统计）"""
        try:
            db = get_db()
            # 获取上证指数K线作为市场基准
            index_klines = await db.get_klines('sh000001', limit=60)
            # 获取涨跌停统计作为市场广度数据
            breadth_data = None
            try:
                limit_up = await db.get_limit_up_stats()
                if limit_up:
                    breadth_data = limit_up
            except Exception:
                pass
            result = sentiment_analyzer.calculate_fear_greed_index(
                index_klines=index_klines or None,
                breadth_data=breadth_data,
            )
            return ok(result)
        except Exception as e:
            return fail(str(e))
