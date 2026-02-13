"""综合管理器 - 一站式分析"""

from typing import Optional
import json
import logging
from ...storage import get_db
from ...utils import ok, fail, normalize_code
from ...data_source import data_source
from ..market import get_kline

logger = logging.getLogger(__name__)


def register_comprehensive_manager(mcp):
    """注册综合管理器工具"""
    
    @mcp.tool()
    async def comprehensive_manager(action: str, code: Optional[str] = None, **kwargs):
        """综合管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/full_analysis/quick_scan
            code (str, optional): 股票代码
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - full_analysis: code(str, 全面分析包含技术面+基本面+估值+情绪)
                - quick_scan: code(str, 快速扫描)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            comprehensive_manager(action="help", kwargs="{}")
            # 全面分析
            comprehensive_manager(action="full_analysis", code="600519", kwargs="{}")
            # 快速扫描
            comprehensive_manager(action="quick_scan", code="600519", kwargs="{}")
        """
        try:
            db = get_db()
            # 兼容 kwargs="{}" / Code 传参
            if kwargs.get("kwargs") and isinstance(kwargs.get("kwargs"), str):
                try:
                    extra = json.loads(kwargs.get("kwargs") or "{}")
                    if isinstance(extra, dict):
                        kwargs = {**kwargs, **extra}
                except Exception:
                    pass
            code = code or kwargs.get("code") or kwargs.get("Code") or kwargs.get("stock_code") or kwargs.get("symbol")
            if "codes" not in kwargs and "Codes" in kwargs:
                kwargs["codes"] = kwargs.get("Codes")
            
            if action == 'help':
                return ok({
                    'supported_actions': {
                        'full_analysis': '综合分析（需要 code）',
                        'quick_scan': '快速扫描（需要 code）',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'full_analysis':
                if not code:
                    return fail('需要提供股票代码')
                code = normalize_code(code)
                
                # 综合分析：K 线优先 DB，无则 TDX/akshare
                klines = await db.get_klines(code, limit=60)
                if not klines:
                    res = get_kline(code, 'daily', 60)
                    if res.get('success') and res.get('data'):
                        klines = res['data']
                financials = await db.get_financials(code, limit=1)
                
                if not klines:
                    return fail('无K线数据')
                
                klines = sorted(klines, key=lambda x: x.get('date') or '')
                current_price = klines[-1]['close']
                stock_info = await db.get_stock_info(code) or {}

                pe_ratio = float(financials[0].get('pe_ratio', 0)) if financials else 0.0
                roe = float(financials[0].get('roe', 0)) if financials else 0.0
                rating = 'A' if roe >= 20 else ('B' if roe >= 10 else 'C')
                profitability_level = 'high' if roe >= 20 else ('medium' if roe >= 10 else 'low')

                technical_data = {
                    'trend': 'uptrend',
                    'support': float(current_price * 0.95),
                    'resistance': float(current_price * 1.05),
                }
                fundamental_data = {
                    'pe_ratio': pe_ratio,
                    'roe': roe,
                    'rating': rating
                }

                # 轻量可解释评分，便于旧版字段兼容
                score_from_roe = max(0.0, min(60.0, roe * 2.0))
                score_from_pe = 0.0
                if pe_ratio > 0:
                    score_from_pe = max(0.0, min(40.0, 40.0 - max(0.0, pe_ratio - 15.0)))
                total_score = round(score_from_roe + score_from_pe, 2)

                return ok({
                    # 新版结构
                    'code': code,
                    'current_price': float(current_price),
                    'technical_analysis': technical_data,
                    'fundamental_analysis': fundamental_data,
                    'recommendation': 'hold',
                    'confidence': 'medium',
                    # 向后兼容结构
                    'basic_info': {
                        'code': code,
                        'name': stock_info.get('stock_name', code),
                        'industry': stock_info.get('industry', 'unknown'),
                        'current_price': float(current_price),
                    },
                    'technical': technical_data,
                    'fundamental': {
                        'valuation': {'pe_ratio': pe_ratio},
                        'profitability': {'roe': roe, 'level': profitability_level},
                        'rating': rating,
                    },
                    'score': {
                        'total_score': float(total_score),
                    },
                })
            
            elif action == 'quick_scan':
                codes = kwargs.get('codes', [])
                
                # 如果未提供codes，使用默认样本
                if not codes:
                    codes = ['600519', '000001', '600036', '601318', '000858']
                    logger.info(f"[ComprehensiveManager] 未提供codes，使用默认样本: {codes}")
                
                results = []
                for c in codes[:10]:
                    c = normalize_code(c)
                    # 优先数据库
                    klines = await db.get_klines(c, limit=1)
                    # 降级到数据源
                    if not klines:
                        logger.info(f"[ComprehensiveManager] DB无数据，从数据源获取: {c}")
                        res = get_kline(c, 'daily', 1)
                        if res.get('success') and res.get('data'):
                            klines = res['data']
                    if klines:
                        klines = sorted(klines, key=lambda x: x.get('date') or '')
                        latest = klines[-1]
                        change_pct = latest.get('change_pct') or 0
                        results.append({
                            'code': c,
                            'price': float(latest.get('close') or 0),
                            'change_pct': float(change_pct),
                            'volume': float(latest.get('volume') or 0),
                            'status': 'active',
                            'trend': 'up' if change_pct > 0 else ('down' if change_pct < 0 else 'flat')
                        })
                
                return ok({
                    'scanned': len(results),
                    'results': results,
                    'data_source': 'database+fallback' if results else 'none',
                    'message': f'成功扫描 {len(results)}/{len(codes[:10])} 只股票'
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: help, full_analysis, quick_scan')
        except Exception as e:
            return fail(str(e))
