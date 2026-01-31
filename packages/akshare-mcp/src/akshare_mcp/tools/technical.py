"""技术分析工具"""

from typing import List, Optional
from ..services import technical_analysis, pattern_recognition
from ..storage import get_db
from ..utils import ok, fail


def register(mcp):
    """注册技术分析工具"""
    
    @mcp.tool()
    async def calculate_technical_indicators(
        code: str,
        indicators: List[str],
        period: str = 'daily',
        limit: int = 250
    ):
        """
        计算技术指标
        
        Args:
            code: 股票代码
            indicators: 指标列表 ['MA', 'EMA', 'RSI', 'MACD', 'KDJ', 'BOLL', 'ATR']
            period: K线周期
            limit: K线数量 (默认250，确保MACD等指标有足够数据)
        """
        try:
            db = get_db()
            klines = await db.get_klines(code, limit=limit)
            
            if not klines:
                return fail('No kline data found')
            
            # 检查MACD所需的最小数据量
            if 'MACD' in indicators and len(klines) < 35:
                return fail(f'MACD需要至少35天数据，当前只有{len(klines)}天。请增加limit参数或检查数据源。')
            
            results = technical_analysis.calculate_all_indicators(klines, indicators)
            
            return ok(results)
        
        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    async def check_candlestick_patterns(
        code: str,
        period: str = 'daily',
        limit: int = 100
    ):
        """
        检测K线形态
        
        Args:
            code: 股票代码
            period: K线周期
            limit: K线数量
        """
        try:
            db = get_db()
            klines = await db.get_klines(code, limit=limit)
            
            if not klines:
                return fail('No kline data found')
            
            patterns = pattern_recognition.detect_patterns(klines)
            
            return ok({'patterns': patterns})
        
        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    def get_available_patterns():
        """获取支持的K线形态列表"""
        try:
            patterns = pattern_recognition.get_available_patterns()
            return ok({'patterns': patterns})
        except Exception as e:
            return fail(str(e))
