"""
A股分析工具模块
包含基于AKShare的各种数据获取和分析工具
"""

from .a_stock_data_tool import AStockDataTool
from .financial_tool import FinancialAnalysisTool
from .market_sentiment_tool import MarketSentimentTool
from .calculator_tool import CalculatorTool
from .ai_score_tool import AIScoreTool, BatchAIScoreTool
from .technical_indicator_tool import TechnicalIndicatorTool
from .nlp_query_tool import NLPQueryTool
from .north_fund_tool import (
    NorthFundTracker,
    NorthFundFlowTool,
    NorthFundHoldingTool,
    NorthFundTopTool,
)
from .dragon_tiger_tool import (
    DragonTigerAnalyzer,
    DragonTigerDailyTool,
    DragonTigerStockTool,
)
from .sector_rotation_tool import (
    SectorRotationAnalyzer,
    SectorRealtimeTool,
    SectorFundFlowTool,
    SectorRotationTool,
    SectorStocksTool,
)
# P2新增工具
from .sentiment_tool import (
    StockSentimentTool,
    MarketSentimentTool as MarketSentimentAnalysisTool,
    StockNewsTool,
    EventDetectionTool,
    ResearchReportTool,
    get_sentiment_tools,
)
from .limit_up_tool import (
    DailyLimitUpTool,
    LimitUpReasonTool,
    ContinuationPredictTool,
    LimitUpStatisticsTool,
    HotConceptTool,
    get_limit_up_tools,
)
# P3新增工具
from .margin_tool import (
    MarketMarginTool,
    StockMarginTool,
    MarginRankingTool,
    get_margin_tools,
)
from .block_trade_tool import (
    DailyBlockTradeTool,
    StockBlockTradeTool,
    AbnormalBlockTradeTool,
    get_block_trade_tools,
)
# P2新增 - 估值分析工具
from .valuation_tool import ValuationTool

__all__ = [
    # 原有工具
    'AStockDataTool',
    'FinancialAnalysisTool',
    'MarketSentimentTool',
    'CalculatorTool',
    # P0新增工具
    'AIScoreTool',
    'BatchAIScoreTool',
    'TechnicalIndicatorTool',
    'NLPQueryTool',
    # P1新增工具
    'NorthFundTracker',
    'NorthFundFlowTool',
    'NorthFundHoldingTool',
    'NorthFundTopTool',
    'DragonTigerAnalyzer',
    'DragonTigerDailyTool',
    'DragonTigerStockTool',
    # 板块轮动工具
    'SectorRotationAnalyzer',
    'SectorRealtimeTool',
    'SectorFundFlowTool',
    'SectorRotationTool',
    'SectorStocksTool',
    # P2新增 - 情绪分析工具
    'StockSentimentTool',
    'MarketSentimentAnalysisTool',
    'StockNewsTool',
    'EventDetectionTool',
    'ResearchReportTool',
    'get_sentiment_tools',
    # P2新增 - 涨停分析工具
    'DailyLimitUpTool',
    'LimitUpReasonTool',
    'ContinuationPredictTool',
    'LimitUpStatisticsTool',
    'HotConceptTool',
    'get_limit_up_tools',
    # P3新增 - 融资融券工具
    'MarketMarginTool',
    'StockMarginTool',
    'MarginRankingTool',
    'get_margin_tools',
    # P3新增 - 大宗交易工具
    'DailyBlockTradeTool',
    'StockBlockTradeTool',
    'AbnormalBlockTradeTool',
    'get_block_trade_tools',
    # P2新增 - 估值分析工具
    'ValuationTool',
]
