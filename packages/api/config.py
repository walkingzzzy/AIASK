"""API配置常量"""
import os
from typing import List

# 环境
ENV = os.getenv("ENV", "development")
IS_PRODUCTION = ENV == "production"

# 数据库路径
DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/user_data.db")

# CORS配置
def get_cors_origins() -> List[str]:
    """获取CORS允许的来源列表"""
    default = "http://localhost:3000,http://localhost:5173,http://localhost:1420,http://127.0.0.1:3000,http://127.0.0.1:5173,http://127.0.0.1:1420"
    cors_origins = os.getenv("CORS_ORIGINS", default)
    return list(set(origin.strip() for origin in cors_origins.split(",") if origin.strip()))

ALLOWED_HEADERS = ["Content-Type", "Authorization", "X-Request-ID", "Accept", "Origin"]
ALLOWED_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]

# 限流配置 - 通用接口
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "1000"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_CLEANUP_INTERVAL = 300  # 清理间隔（秒）

# 限流配置 - 高频行情接口（更宽松）
QUOTE_RATE_LIMIT_MAX_REQUESTS = int(os.getenv("QUOTE_RATE_LIMIT_MAX_REQUESTS", "2000"))
QUOTE_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("QUOTE_RATE_LIMIT_WINDOW_SECONDS", "60"))

# AI评分限流（更严格）
AI_SCORE_RATE_LIMIT = int(os.getenv("AI_SCORE_RATE_LIMIT", "30"))
AI_SCORE_RATE_WINDOW = 60

# 批量查询配置
BATCH_QUOTE_MAX_SIZE = int(os.getenv("BATCH_QUOTE_MAX_SIZE", "50"))  # 批量查询最大股票数

# WebSocket配置
WS_MAX_CONNECTIONS = int(os.getenv("WS_MAX_CONNECTIONS", "100"))
WS_MAX_SUBSCRIPTIONS = int(os.getenv("WS_MAX_SUBSCRIPTIONS", "50"))
WS_HEARTBEAT_INTERVAL = 30

# 分页默认值
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# 股票代码正则
STOCK_CODE_PATTERN = r"^[0-9]{6}(\.(SH|SZ))?$"

# API版本
API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"
