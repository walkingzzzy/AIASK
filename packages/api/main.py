"""
FastAPI后端服务
为Tauri桌面应用提供API接口
"""
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List, Dict, Any
import logging
from collections import defaultdict
import time

# 导入配置
from packages.api.config import (
    RATE_LIMIT_MAX_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
    QUOTE_RATE_LIMIT_MAX_REQUESTS,
    QUOTE_RATE_LIMIT_WINDOW_SECONDS,
)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== 模块状态跟踪 ====================
MODULE_STATUS: Dict[str, Dict[str, Any]] = {}


def _try_import(module_name: str, import_func):
    """尝试导入模块并记录状态"""
    try:
        result = import_func()
        MODULE_STATUS[module_name] = {"available": True, "error": None}
        return result
    except (ImportError, SyntaxError) as e:
        MODULE_STATUS[module_name] = {"available": False, "error": str(e)}
        logger.warning(f"模块 {module_name} 导入失败: {e}")
        return None


# 预加载核心模块状态
_try_import("StockDataService", lambda: __import__("packages.core.services.stock_data_service", fromlist=["StockDataService"]))
_try_import("sentiment", lambda: __import__("packages.core.sentiment", fromlist=["SentimentAnalyzer"]))
_try_import("limit_up", lambda: __import__("packages.core.limit_up", fromlist=["LimitUpAnalyzer"]))
_try_import("margin", lambda: __import__("packages.core.margin", fromlist=["MarginAnalyzer"]))
_try_import("block_trade", lambda: __import__("packages.core.block_trade", fromlist=["BlockTradeAnalyzer"]))
_try_import("CallAuctionAnalyzer", lambda: __import__("packages.core.call_auction.auction_analyzer", fromlist=["CallAuctionAnalyzer"]))


def get_module_status_summary() -> Dict[str, Any]:
    """获取模块状态摘要"""
    available = [k for k, v in MODULE_STATUS.items() if v["available"]]
    unavailable = [k for k, v in MODULE_STATUS.items() if not v["available"]]
    return {
        "total": len(MODULE_STATUS),
        "available": len(available),
        "unavailable": len(unavailable),
        "available_modules": available,
        "unavailable_modules": {k: MODULE_STATUS[k]["error"] for k in unavailable}
    }


# ==================== 安全配置 ====================

def get_cors_origins() -> List[str]:
    """获取CORS允许的来源列表"""
    cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,http://localhost:1420")
    origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
    origins.extend([
        "http://localhost:1420", "http://localhost:8080",
        "http://127.0.0.1:3000", "http://127.0.0.1:5173",
        "http://127.0.0.1:1420", "http://127.0.0.1:8080",
    ])
    return list(set(origins))


# ==================== 请求限流 ====================

class RateLimiter:
    """简单的请求限流器"""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, List[float]] = defaultdict(list)
    
    def is_allowed(self, client_id: str, cost: int = 1) -> bool:
        """检查是否允许请求，cost为请求消耗的配额"""
        now = time.time()
        window_start = now - self.window_seconds
        self.requests[client_id] = [t for t in self.requests[client_id] if t > window_start]
        if len(self.requests[client_id]) + cost > self.max_requests:
            return False
        # 记录请求（按cost添加多个时间戳）
        for _ in range(cost):
            self.requests[client_id].append(now)
        return True
    
    def get_remaining(self, client_id: str) -> int:
        now = time.time()
        window_start = now - self.window_seconds
        current = len([t for t in self.requests[client_id] if t > window_start])
        return max(0, self.max_requests - current)
    
    def cleanup(self):
        """清理过期的请求记录"""
        now = time.time()
        for client_id in list(self.requests.keys()):
            window_start = now - self.window_seconds
            self.requests[client_id] = [t for t in self.requests[client_id] if t > window_start]
            if not self.requests[client_id]:
                del self.requests[client_id]


# 全局速率限制器 - 通用接口（宽松限制）
rate_limiter = RateLimiter(
    max_requests=RATE_LIMIT_MAX_REQUESTS,
    window_seconds=RATE_LIMIT_WINDOW_SECONDS
)

# 行情接口专用限制器 - 更高的限制
quote_rate_limiter = RateLimiter(
    max_requests=QUOTE_RATE_LIMIT_MAX_REQUESTS,
    window_seconds=QUOTE_RATE_LIMIT_WINDOW_SECONDS
)

# 高频路径白名单（这些路径使用更宽松的限制）
HIGH_FREQ_PATHS = {
    "/api/stock/quote",
    "/api/stock/quotes/batch",
    "/api/stock/orderbook",
    "/api/stock/trades",
}


# ==================== FastAPI应用 ====================

app = FastAPI(
    title="A股智能分析API",
    description="为桌面应用提供股票分析服务",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ==================== 中间件 ====================

def _is_high_freq_path(path: str) -> bool:
    """检查是否是高频访问路径"""
    for prefix in HIGH_FREQ_PATHS:
        if path.startswith(prefix):
            return True
    return False


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """请求限流中间件 - 针对不同接口使用不同限制"""
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path
    
    # 跳过健康检查
    if path.startswith("/api/health"):
        return await call_next(request)
    
    # 选择合适的限制器
    if _is_high_freq_path(path):
        # 高频接口使用更宽松的限制
        limiter = quote_rate_limiter
    else:
        # 普通接口使用标准限制
        limiter = rate_limiter
    
    if not limiter.is_allowed(client_ip):
        remaining = limiter.get_remaining(client_ip)
        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "error": "请求过于频繁，请稍后再试",
                "retry_after": 60,
                "limit": limiter.max_requests,
                "remaining": remaining
            },
            headers={
                "Retry-After": "60",
                "X-RateLimit-Limit": str(limiter.max_requests),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(int(time.time()) + 60)
            }
        )
    
    response = await call_next(request)
    response.headers["X-RateLimit-Remaining"] = str(limiter.get_remaining(client_ip))
    response.headers["X-RateLimit-Limit"] = str(limiter.max_requests)
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """请求日志中间件"""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(f"{request.method} {request.url.path} - Status: {response.status_code} - Time: {process_time:.3f}s")
    return response


# ==================== 注册路由 ====================

# 原有路由
from packages.api.routes.valuation import router as valuation_router
from packages.api.routes.watchlist import router as watchlist_router
from packages.api.routes.insight import router as insight_router
from packages.api.routes.user_profile import router as user_profile_router
from packages.api.routes.ai_chat import router as ai_chat_router
from packages.api.routes.decision import router as decision_router
from packages.api.routes.realtime import router as realtime_router
from packages.api.routes.backtest import router as backtest_router
from packages.api.routes.research import router as research_router

# 新拆分的路由
from packages.api.routes.stock import router as stock_router
from packages.api.routes.ai_score import router as ai_score_router
from packages.api.routes.sentiment import router as sentiment_router
from packages.api.routes.limit_up import router as limit_up_router
from packages.api.routes.margin import router as margin_router
from packages.api.routes.block_trade import router as block_trade_router
from packages.api.routes.dragon_tiger import router as dragon_tiger_router
from packages.api.routes.portfolio import router as portfolio_router
from packages.api.routes.risk_monitor import router as risk_monitor_router
from packages.api.routes.screener import router as screener_router
from packages.api.routes.data_center import router as data_center_router
from packages.api.routes.call_auction import router as call_auction_router
from packages.api.routes.nlp_query import router as nlp_query_router

# 注册所有路由
app.include_router(valuation_router)
app.include_router(watchlist_router)
app.include_router(insight_router)
app.include_router(user_profile_router)
app.include_router(ai_chat_router)
app.include_router(decision_router)
app.include_router(realtime_router)
app.include_router(backtest_router)
app.include_router(research_router)
app.include_router(stock_router)
app.include_router(ai_score_router)
app.include_router(sentiment_router)
app.include_router(limit_up_router)
app.include_router(margin_router)
app.include_router(block_trade_router)
app.include_router(dragon_tiger_router)
app.include_router(portfolio_router)
app.include_router(risk_monitor_router)
app.include_router(screener_router)
app.include_router(data_center_router)
app.include_router(call_auction_router)
app.include_router(nlp_query_router)


# ==================== 基础路由 ====================

@app.get("/")
async def root():
    """API根路径"""
    return {
        "name": "A股智能分析API",
        "version": "1.0.0",
        "status": "running",
        "modules_available": get_module_status_summary()["available"]
    }


@app.get("/api/health")
async def health_check():
    """健康检查"""
    summary = get_module_status_summary()
    return {
        "status": "healthy",
        "modules": summary,
        "using_mock_data": summary["unavailable"] > 0
    }


@app.get("/api/modules")
async def get_modules_status():
    """获取模块状态详情"""
    return {"success": True, "data": get_module_status_summary()}


# ==================== 启动入口 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
