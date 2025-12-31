"""
API路由模块
"""
from .watchlist import router as watchlist_router
from .valuation import router as valuation_router
from .insight import router as insight_router
from .user_profile import router as user_profile_router
from .ai_chat import router as ai_chat_router
from .decision import router as decision_router
from .realtime import router as realtime_router
from .backtest import router as backtest_router
from .research import router as research_router
from .stock import router as stock_router
from .ai_score import router as ai_score_router
from .sentiment import router as sentiment_router
from .limit_up import router as limit_up_router
from .margin import router as margin_router
from .block_trade import router as block_trade_router
from .dragon_tiger import router as dragon_tiger_router
from .portfolio import router as portfolio_router
from .risk_monitor import router as risk_monitor_router
from .screener import router as screener_router
from .data_center import router as data_center_router
from .call_auction import router as call_auction_router
from .nlp_query import router as nlp_query_router
from .health import router as health_router

__all__ = [
    'watchlist_router', 'valuation_router', 'insight_router',
    'user_profile_router', 'ai_chat_router', 'decision_router',
    'realtime_router', 'backtest_router', 'research_router',
    'stock_router', 'ai_score_router', 'sentiment_router',
    'limit_up_router', 'margin_router', 'block_trade_router',
    'dragon_tiger_router', 'portfolio_router', 'risk_monitor_router',
    'screener_router', 'data_center_router', 'call_auction_router',
    'nlp_query_router', 'health_router'
]
