"""技术分析管理器 - 连接真实服务"""

import json
import logging
from typing import Optional, List, Any

from ...storage import get_db
from ...utils import ok, fail, normalize_code
from ...data_source import data_source

logger = logging.getLogger(__name__)


def _normalize_kwargs(kwargs: dict) -> dict:
    """解析 kwargs 字符串并合并到顶层，便于 MCP 传入的 code/indicators 被正确读取。"""
    extra = kwargs.get("kwargs")
    if extra is not None:
        if isinstance(extra, str):
            try:
                extra = json.loads(extra or "{}")
            except Exception:
                extra = None
        if isinstance(extra, dict):
            kwargs = {**kwargs, **extra}
    return kwargs


def _ensure_serializable(obj: Any) -> Any:
    """确保返回值可 JSON 序列化，避免 numpy 等类型导致客户端解析错误。"""
    if hasattr(obj, "item"):
        return obj.item()
    if isinstance(obj, dict):
        return {k: _ensure_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_ensure_serializable(x) for x in obj]
    if isinstance(obj, (float, int)) and hasattr(obj, "dtype"):
        return float(obj) if getattr(obj, "dtype", None) else obj
    return obj


def register_technical_analysis_manager(mcp):
    """注册技术分析管理器工具"""
    
    @mcp.tool()
    async def technical_analysis_manager(
        action: str, 
        code: Optional[str] = None,
        indicators: Optional[List[str]] = None,
        period: str = 'daily',
        limit: int = 250,
        **kwargs
    ):
        """
        技术分析管理器（统一 action + kwargs 协议，连接真实服务）
        
        Args:
            action (str, required): 操作类型，可选 help/calculate/list_indicators/check_patterns
            code (str, optional): 股票代码，calculate 和 check_patterns 时必填
            indicators (list[str], optional): 指标列表，calculate 时使用，如 ["MA","RSI","MACD","KDJ","BOLL","ATR"]
            period (str, optional): K线周期，默认 "daily"
            limit (int, optional): K线数量，默认 250（MACD 至少需要 35 条数据）
            kwargs: JSON 字符串或关键字参数

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}
            - calculate: 返回 indicators 字典，包含各指标最新值和历史序列
            - list_indicators: 返回支持的指标列表
            - check_patterns: 返回检测到的K线形态列表

        Examples:
            # 查看帮助
            technical_analysis_manager(action="help", kwargs="{}")
            # 计算技术指标
            technical_analysis_manager(action="calculate", code="600519", indicators=["MA","RSI","MACD"], kwargs="{}")
            # 检测K线形态
            technical_analysis_manager(action="check_patterns", code="600519", kwargs="{}")
            # 列出支持的指标
            technical_analysis_manager(action="list_indicators", kwargs="{}")
        """
        try:
            kwargs = _normalize_kwargs(kwargs)
            code = code or kwargs.get("code") or kwargs.get("Code") or kwargs.get("stock_code") or kwargs.get("symbol")
            if indicators is None:
                indicators = kwargs.get("indicators")
            period = kwargs.get("period") or period
            limit = kwargs.get("limit", limit)
            if isinstance(limit, str):
                try:
                    limit = int(limit)
                except ValueError:
                    limit = 250
            if isinstance(indicators, str):
                try:
                    indicators = json.loads(indicators) if indicators.strip().startswith("[") else [indicators.strip()]
                except Exception:
                    indicators = ["MA", "RSI", "MACD"]

            if action == 'help':
                return ok({
                    'supported_actions': {
                        'calculate': '计算技术指标（需要 code, indicators）',
                        'check_patterns': '检测K线形态（需要 code）',
                        'list_indicators': '列出支持的技术指标',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'calculate' and code:
                code = normalize_code(code)
                db = get_db()
                
                # 1. 尝试从DB获取K线
                klines = await db.get_klines(code, limit=limit)
                
                # 2. DB无数据时自动获取
                if not klines:
                    logger.info(f"[TechnicalAnalysisManager] Fetching klines for {code}")
                    klines = data_source.get_kline(code, period, limit)
                    
                    # 保存到DB
                    if klines:
                        try:
                            await db.save_klines(code, klines)
                        except Exception as e:
                            logger.warning(f"[TechnicalAnalysisManager] Failed to save klines: {e}")
                
                if not klines:
                    return fail(f'无法获取K线数据，请检查股票代码 {code}')
                
                # 3. 计算技术指标
                from ...services.technical_analysis import technical_analysis
                indicators = indicators or ['MA', 'RSI', 'MACD']
                
                # 检查MACD所需数据量
                if 'MACD' in indicators and len(klines) < 35:
                    return fail(f'MACD需要至少35天数据，当前只有{len(klines)}天')
                
                results = technical_analysis.calculate_all_indicators(klines, indicators)
                out = {
                    **results,
                    'code': code,
                    'data_source': klines[0].get('source', 'unknown') if klines else 'unknown',
                    'kline_count': len(klines)
                }
                return ok(_ensure_serializable(out))
                
            elif action == 'check_patterns' and code:
                code = normalize_code(code)
                db = get_db()
                
                # 获取K线
                klines = await db.get_klines(code, limit=100)
                if not klines:
                    klines = data_source.get_kline(code, period, 100)
                    if klines:
                        try:
                            await db.save_klines(code, klines)
                        except Exception:
                            pass
                
                if not klines:
                    return fail(f'无法获取K线数据，请检查股票代码 {code}')
                
                # 检测形态
                from ...services.pattern_recognition import pattern_recognition
                patterns = pattern_recognition.detect_patterns(klines)
                
                return ok(_ensure_serializable({
                    'code': code,
                    'patterns': patterns,
                    'kline_count': len(klines)
                }))
                
            elif action == 'list_indicators':
                return ok({
                    'indicators': ['MA', 'EMA', 'RSI', 'MACD', 'KDJ', 'BOLL', 'ATR'],
                    'descriptions': {
                        'MA': '移动平均线 - 趋势跟踪指标',
                        'EMA': '指数移动平均线 - 对近期价格更敏感',
                        'RSI': '相对强弱指标 - 超买超卖判断',
                        'MACD': '指数平滑异同移动平均线 - 趋势和动量',
                        'KDJ': '随机指标 - 超买超卖和转折点',
                        'BOLL': '布林带 - 波动率和支撑阻力',
                        'ATR': '平均真实波幅 - 波动率测量'
                    }
                })
            else:
                return fail(f'Unknown action: {action}. Supported: help, calculate, check_patterns, list_indicators')
        except Exception as e:
            logger.error(f"[TechnicalAnalysisManager] Error: {e}")
            return fail(str(e))
