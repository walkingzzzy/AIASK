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
    def calculate_fear_greed_index():
        try:
            result = sentiment_analyzer.calculate_fear_greed_index()
            return ok(result)
        except Exception as e:
            return fail(str(e))
