"""
AKShare MCP Server v2
提供完整的A股量化分析服务
"""
from __future__ import annotations

import asyncio
import atexit
import os
import logging
from pathlib import Path

# 禁用 tqdm 进度条输出，避免 AKShare/Tushare 内部进度条写入 stderr 被 MCP 当 [error] 刷屏
os.environ.setdefault("TQDM_DISABLE", "1")

# 在首次使用 get_db() 前加载 .env，使数据库使用实际配置（DB_PASSWORD、DB_NAME 等）
# 注意：如果环境变量已设置（来自 MCP 配置），则不覆盖，确保 MCP 配置优先级更高
_env_path = Path(__file__).resolve().parent.parent.parent / '.env'
if _env_path.exists():
    try:
        _env_content = _env_path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        _env_content = ""
    for line in _env_content.splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            k, v = key.strip(), value.strip()
            # 如果环境变量已设置（来自 MCP 配置），则不覆盖
            # 只有在环境变量未设置时才从 .env 加载
            if k.startswith('DB_'):
                if k not in os.environ:
                    os.environ[k] = v
            else:
                os.environ.setdefault(k, v)

# 在所有导入之前抑制警告，避免干扰 MCP 协议通信
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*Pydantic.*")
warnings.filterwarnings("ignore", message=".*invalid escape sequence.*")

# 抑制 MCP 框架的 INFO 日志写入 stderr，避免被 Cursor 当 [error] 刷屏
for _log_name in ("mcp", "mcp.server", "mcp.server.server", "fastmcp", "uvicorn"):
    logging.getLogger(_log_name).setLevel(logging.WARNING)

from mcp.server.fastmcp import FastMCP

# 分步导入以便 UnicodeDecodeError 时定位到具体子模块
_tool_names = (
    "market", "finance", "fund_flow", "macro", "news", "options",
    "technical", "backtest", "portfolio", "valuation", "decision",
    "search", "semantic", "data_warmup", "alerts",
    "vector", "skills", "quant", "sentiment", "market_blocks",
    "tdx_formula", "basic_data", "data_sync", "tdx_integration", "tdx_trading_data", "tdx_file_sector", "tdx_realtime", "managers",
)
try:
    from .tools import (
        market, finance, fund_flow, macro, news, options,
        technical, backtest, portfolio, valuation, decision,
        search, semantic, data_warmup, alerts,
        vector, skills, quant, sentiment, market_blocks,
        tdx_formula, basic_data, data_sync, tdx_integration, tdx_trading_data, tdx_file_sector, tdx_realtime, managers,
    )
except UnicodeDecodeError as e:
    # 定位是哪个子模块触发的解码错误（多为路径或插件内文件编码问题）
    import importlib
    for _n in _tool_names:
        try:
            importlib.import_module(f"akshare_mcp.tools.{_n}")
        except UnicodeDecodeError:
            raise RuntimeError(
                f"UnicodeDecodeError when loading akshare_mcp.tools.{_n}. "
                "Ensure all .py files are UTF-8 and start with: python -X utf8 start_server.py"
            ) from e
    raise


from .services.data_sync import data_sync_service


def _safe_shutdown_data_sync() -> None:
    """进程退出时尽力 flush/关闭数据同步后台任务。"""
    try:
        asyncio.run(data_sync_service.shutdown())
    except RuntimeError:
        # 若解释器退出阶段事件循环不可用，忽略并记录
        logging.getLogger(__name__).warning("[Server] skip data_sync shutdown: event loop unavailable")
    except Exception as e:
        logging.getLogger(__name__).warning(
            "[Server] data_sync shutdown failed", extra={"error": str(e)}
        )


atexit.register(_safe_shutdown_data_sync)


# ===== FastMCP app =====

mcp = FastMCP("AKShare Stock Data Server v2")

market.register(mcp)
finance.register(mcp)
fund_flow.register(mcp)
macro.register(mcp)
news.register(mcp)
options.register(mcp)
technical.register(mcp)
backtest.register(mcp)
portfolio.register(mcp)
valuation.register(mcp)
decision.register(mcp)
search.register(mcp)
semantic.register(mcp)
data_warmup.register(mcp)
alerts.register(mcp)
managers.register(mcp)  # Phase 5: 统一注册，消除重复
vector.register(mcp)
skills.register(mcp)
quant.register(mcp)
sentiment.register(mcp)

# 注册 TDX 公式计算工具 (Phase 1)
tdx_formula.register(mcp)

# 注册基础数据工具 (Phase 3)
basic_data.register(mcp)

# 注册数据同步工具 (Phase 4)
data_sync.register(mcp)

# 注册 TdxQuant 前端集成工具 (Phase 5)
tdx_integration.register(mcp)

# 注册 TDX 交易数据工具 (Phase 1 扩展 - GP/BK/SC 系列)
tdx_trading_data.register(mcp)

# 注册 TDX 文件交互与板块管理补全工具 (Phase 2 扩展)
tdx_file_sector.register(mcp)

# 注册 TDX 行情订阅与缓存管理工具 (Phase 4 扩展)
tdx_realtime.register(mcp)

# 注册市场板块工具
@mcp.tool()
async def get_market_blocks(block_type: str = "industry", limit: int | None = None):
    """获取市场板块列表

    Args:
        block_type (str, optional): 板块类型，可选 "industry"(行业) / "concept"(概念) / "region"(地域)，默认 "industry"
        limit (int | None, optional): 返回数量上限，None 表示不限制

    Returns:
        dict: {"success": bool, "data": {"blocks": [{"code": str, "name": str, ...}]}, "error": str|None}

    Errors:
        - block_type 不在枚举范围内时返回空列表
        - 数据源不可用时返回 success=false

    Examples:
        # 获取行业板块列表
        get_market_blocks(block_type="industry")
        # 获取概念板块（限制返回10个）
        get_market_blocks(block_type="concept", limit=10)
    """
    return await market_blocks.get_market_blocks(block_type=block_type, limit=limit)


@mcp.tool()
async def get_block_stocks(block_code: str):
    """获取指定板块的成分股列表

    Args:
        block_code (str, required): 板块代码，来自 get_market_blocks 返回的 code 字段

    Returns:
        dict: {"success": bool, "data": {"stocks": [{"code": str, "name": str, ...}]}, "error": str|None}

    Errors:
        - block_code 无效时返回空列表

    Examples:
        # 获取指定板块的成分股
        get_block_stocks(block_code="BK0477")
    """
    return await market_blocks.get_block_stocks(block_code=block_code)


def main() -> None:
    """启动 MCP Server"""
    # 不再在 main() 中创建/关闭独立的事件循环
    # 之前的实现会 asyncio.new_event_loop() + loop.close()，
    # 导致 FastMCP 启动后所有 async 工具报 "Event loop is closed"
    #
    # 数据库状态检查改为懒加载：TimescaleDBAdapter.acquire() 内部已有
    # if not self._initialized: await self.initialize() 的逻辑，
    # 会在首次工具调用时自动初始化，无需提前检查。
    mcp.run()


if __name__ == "__main__":
    main()
