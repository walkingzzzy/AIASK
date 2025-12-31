# 自然语言查询模块
from .intent_parser import IntentParser, QueryIntent, IntentType
from .query_executor import QueryExecutor, QueryResult
from .stock_database import StockDatabase, get_stock_database
from .llm_intent_parser import LLMIntentParser, LLMConfig, parse_query_with_llm
from .conversation_manager import (
    ConversationManager,
    ConversationSession,
    ConversationMessage,
    get_conversation_manager
)

__all__ = [
    # 规则匹配解析器（旧版）
    'IntentParser', 'QueryIntent', 'IntentType',
    'QueryExecutor', 'QueryResult',
    # 股票数据库
    'StockDatabase', 'get_stock_database',
    # LLM解析器（新版）
    'LLMIntentParser', 'LLMConfig', 'parse_query_with_llm',
    # 对话管理
    'ConversationManager', 'ConversationSession', 'ConversationMessage',
    'get_conversation_manager'
]
