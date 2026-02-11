"""决策管理器 - AI辅助决策（增强版）"""

import numpy as np
import json
from ...storage import get_db
from ...utils import ok, fail, normalize_code
from ...data_source import data_source
import logging

logger = logging.getLogger(__name__)

def _normalize_kwargs(kwargs: dict) -> dict:
    # 支持 MCP 将全部参数放在 kwargs 字符串里传入
    extra = kwargs.get("kwargs")
    if extra is not None:
        if isinstance(extra, str):
            try:
                extra = json.loads(extra or "{}")
            except Exception:
                extra = None
        if isinstance(extra, dict):
            kwargs = {**kwargs, **extra}
    # 统一 code 的多种传参方式
    code = kwargs.get("code") or kwargs.get("Code") or kwargs.get("stock_code") or kwargs.get("symbol")
    if code is not None and isinstance(code, str):
        code = code.strip() or None
    kwargs["code"] = code
    return kwargs


def register_decision_manager(mcp):
    """注册决策管理器工具"""
    
    @mcp.tool()
    async def decision_manager(action: str, **kwargs):
        """决策管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/analyze/recommend/portfolio_advice
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - analyze: code(str, 股票代码)
                - recommend: investment_style(str, optional, "aggressive"/"balanced"/"conservative")
                - portfolio_advice: codes(list[str]), weights(list[float], optional)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            decision_manager(action="help", kwargs="{}")
            # 综合分析
            decision_manager(action="analyze", kwargs='{"code":"600519"}')
            # 推荐股票
            decision_manager(action="recommend", kwargs='{"investment_style":"balanced"}')
            # 组合建议
            decision_manager(action="portfolio_advice", kwargs='{"codes":["600519","000858","002304"],"weights":[0.4,0.3,0.3]}')
        """
        try:
            db = get_db()
            kwargs = _normalize_kwargs(dict(kwargs))
            # action 可能也在 kwargs 里（部分 MCP 客户端把所有参数放进 kwargs）
            if not action and kwargs.get("action"):
                action = kwargs.get("action")
            
            if action == 'help':
                return ok({
                    'supported_actions': {
                        'analyze': '综合分析（需要 code）',
                        'recommend': '推荐股票（可选 criteria, limit）',
                        'portfolio_advice': '组合建议（需要 portfolio_id）',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'analyze':
                code = kwargs.get('code')
                if not code:
                    return fail('需要提供股票代码（可传 code / stock_code / symbol，或放在 kwargs 的 JSON 中）')
                
                code = normalize_code(code)
                
                # 自动获取K线数据
                klines = await db.get_klines(code, limit=100)
                if not klines:
                    logger.info(f"[DecisionManager] Fetching klines for {code}")
                    klines = data_source.get_kline(code, 'daily', 100)
                    if klines:
                        try:
                            await db.save_klines(code, klines)
                        except Exception:
                            pass
                
                if not klines or len(klines) < 20:
                    return fail(f'K线数据不足，无法分析（需要至少20天数据，当前{len(klines) if klines else 0}天）')
                
                prices = np.array([k['close'] for k in klines])
                volumes = np.array([k['volume'] for k in klines])
                
                ma5 = np.mean(prices[-5:])
                ma20 = np.mean(prices[-20:])
                ma60 = np.mean(prices[-60:]) if len(prices) >= 60 else ma20
                
                current_price = prices[-1]
                
                trend_score = 0
                if current_price > ma5 > ma20 > ma60:
                    trend = 'strong_uptrend'
                    trend_score = 80
                elif current_price > ma5 > ma20:
                    trend = 'uptrend'
                    trend_score = 60
                elif current_price < ma5 < ma20 < ma60:
                    trend = 'strong_downtrend'
                    trend_score = 20
                elif current_price < ma5 < ma20:
                    trend = 'downtrend'
                    trend_score = 40
                else:
                    trend = 'sideways'
                    trend_score = 50
                
                financials = await db.get_financials(code, limit=1)
                fundamental_score = 50
                
                if financials:
                    latest = financials[0]
                    roe = latest.get('roe', 0)
                    pe_ratio = latest.get('pe_ratio', 0)
                    debt_ratio = latest.get('debt_ratio', 0)
                    
                    if roe > 15 and pe_ratio < 25 and debt_ratio < 0.5:
                        fundamental_score = 80
                    elif roe > 10 and pe_ratio < 35:
                        fundamental_score = 65
                    elif roe < 5 or pe_ratio > 50:
                        fundamental_score = 30
                
                avg_volume = np.mean(volumes[-20:])
                recent_volume = np.mean(volumes[-5:])
                volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1
                
                sentiment_score = 50
                if volume_ratio > 1.5:
                    sentiment_score = 70
                elif volume_ratio < 0.7:
                    sentiment_score = 40
                
                total_score = (
                    trend_score * 0.4 +
                    fundamental_score * 0.4 +
                    sentiment_score * 0.2
                )
                
                if total_score >= 75:
                    decision = 'strong_buy'
                    confidence = 'high'
                    reason = '技术面、基本面、情绪面均表现良好'
                elif total_score >= 60:
                    decision = 'buy'
                    confidence = 'medium'
                    reason = '整体表现较好，可适当买入'
                elif total_score >= 45:
                    decision = 'hold'
                    confidence = 'medium'
                    reason = '表现中性，建议观望'
                elif total_score >= 30:
                    decision = 'sell'
                    confidence = 'medium'
                    reason = '表现较弱，建议减仓'
                else:
                    decision = 'strong_sell'
                    confidence = 'high'
                    reason = '多方面表现不佳，建议清仓'
                
                return ok({
                    'code': code,
                    'decision': decision,
                    'confidence': confidence,
                    'total_score': float(total_score),
                    'reason': reason,
                    'analysis': {
                        'technical': {
                            'score': float(trend_score),
                            'trend': trend,
                            'current_price': float(current_price),
                            'ma5': float(ma5),
                            'ma20': float(ma20),
                            'ma60': float(ma60),
                        },
                        'fundamental': {
                            'score': float(fundamental_score),
                            'roe': float(financials[0].get('roe', 0)) if financials else 0,
                            'pe_ratio': float(financials[0].get('pe_ratio', 0)) if financials else 0,
                        },
                        'sentiment': {
                            'score': float(sentiment_score),
                            'volume_ratio': float(volume_ratio),
                            'status': 'active' if volume_ratio > 1.2 else ('weak' if volume_ratio < 0.8 else 'normal')
                        }
                    },
                    'risk_warning': '投资有风险，决策仅供参考' if total_score < 60 else None
                })
            
            elif action == 'recommend':
                criteria = kwargs.get('criteria', {})
                limit = kwargs.get('limit', 10)
                
                min_score = criteria.get('min_score', 60)
                sectors = criteria.get('sectors', [])
                
                recommendations = []
                
                sample_codes = ['600519', '000858', '002304', '000001', '600036']
                
                for code in sample_codes[:limit]:
                    result = await decision_manager(action='analyze', code=code)
                    
                    if result.get('success'):
                        data = result['data']
                        if data['total_score'] >= min_score:
                            recommendations.append({
                                'code': code,
                                'decision': data['decision'],
                                'score': data['total_score'],
                                'reason': data['reason']
                            })
                
                recommendations.sort(key=lambda x: x['score'], reverse=True)
                
                return ok({
                    'recommendations': recommendations,
                    'count': len(recommendations),
                    'criteria': criteria
                })
            
            elif action == 'portfolio_advice':
                portfolio_id = kwargs.get('portfolio_id')
                
                async with db.acquire() as conn:
                    holdings = await conn.fetch(
                        "SELECT * FROM holdings WHERE portfolio_id = $1",
                        portfolio_id
                    )
                
                if not holdings:
                    return ok({'message': '当前组合无持仓，请先添加持仓后再操作'})
                
                advice_list = []
                
                for holding in holdings:
                    code = holding['code']
                    
                    result = await decision_manager(action='analyze', code=code)
                    
                    if result.get('success'):
                        data = result['data']
                        advice_list.append({
                            'code': code,
                            'decision': data['decision'],
                            'score': data['total_score'],
                            'action': '建议加仓' if data['decision'] in ['strong_buy', 'buy'] else (
                                '建议减仓' if data['decision'] in ['sell', 'strong_sell'] else '建议持有'
                            )
                        })
                
                avg_score = np.mean([a['score'] for a in advice_list])
                
                if avg_score >= 65:
                    overall_advice = '组合整体表现良好，可继续持有'
                elif avg_score >= 50:
                    overall_advice = '组合表现中性，建议优化持仓结构'
                else:
                    overall_advice = '组合表现较弱，建议调整持仓'
                
                return ok({
                    'portfolio_id': portfolio_id,
                    'overall_score': float(avg_score),
                    'overall_advice': overall_advice,
                    'holdings_advice': advice_list
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: help, analyze, recommend, portfolio_advice')
        except Exception as e:
            return fail(str(e))
