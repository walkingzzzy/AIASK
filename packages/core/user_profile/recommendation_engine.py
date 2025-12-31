"""
个性化推荐引擎
基于用户画像提供个性化推荐
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field, asdict

from .models import UserProfile, InvestmentStyle
from .profile_service import ProfileService

logger = logging.getLogger(__name__)


@dataclass
class StockRecommendation:
    """股票推荐"""
    stock_code: str
    stock_name: str
    reason: str
    match_score: float  # 匹配度 0-1
    recommendation_type: str  # style_match, sector_match, similar, trending
    supporting_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MorningBrief:
    """个性化早报"""
    user_id: str
    greeting: str
    market_overview: str
    watchlist_summary: List[Dict[str, Any]]
    sector_highlights: List[Dict[str, Any]]
    opportunities: List[Dict[str, Any]]
    risk_alerts: List[Dict[str, Any]]
    todos: List[Dict[str, Any]]
    learning_tip: Optional[str]
    ai_insight: Optional[str]
    generated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['generated_at'] = self.generated_at.isoformat()
        return result


class RecommendationEngine:
    """
    个性化推荐引擎
    
    功能：
    1. 基于投资风格推荐股票
    2. 基于偏好板块推荐
    3. 基于相似股票推荐
    4. 生成个性化早报
    """
    
    # 投资风格对应的选股条件
    STYLE_CRITERIA = {
        InvestmentStyle.VALUE: {
            "pe_max": 20,
            "pb_max": 3,
            "dividend_yield_min": 2,
            "roe_min": 10,
            "description": "低估值、高股息、稳定盈利"
        },
        InvestmentStyle.GROWTH: {
            "revenue_growth_min": 20,
            "profit_growth_min": 20,
            "pe_max": 50,
            "description": "高增长、赛道优质"
        },
        InvestmentStyle.MOMENTUM: {
            "price_above_ma20": True,
            "volume_increase": True,
            "rsi_range": [40, 70],
            "description": "趋势向上、量价配合"
        },
        InvestmentStyle.SWING: {
            "volatility_min": 3,
            "rsi_oversold": 30,
            "description": "波动较大、超跌反弹"
        },
        InvestmentStyle.QUANT: {
            "factor_score_min": 0.7,
            "description": "多因子高分"
        }
    }
    
    def __init__(self, 
                 profile_service: ProfileService = None,
                 stock_service=None,
                 retriever=None):
        """
        初始化推荐引擎
        
        Args:
            profile_service: 用户画像服务
            stock_service: 股票数据服务
            retriever: 向量检索器
        """
        self.profile_service = profile_service or ProfileService()
        self.stock_service = stock_service
        self.retriever = retriever
    
    def get_personalized_stocks(self, user_id: str, 
                                 limit: int = 10) -> List[StockRecommendation]:
        """
        获取个性化股票推荐
        
        Args:
            user_id: 用户ID
            limit: 推荐数量
            
        Returns:
            推荐列表
        """
        profile = self.profile_service.get_profile(user_id)
        recommendations = []
        
        # 1. 基于投资风格推荐
        style_recs = self._get_style_matched_stocks(profile)
        recommendations.extend(style_recs)
        
        # 2. 基于偏好板块推荐
        sector_recs = self._get_sector_stocks(profile)
        recommendations.extend(sector_recs)
        
        # 3. 基于相似股票推荐
        if profile.watchlist:
            similar_recs = self._get_similar_stocks(profile)
            recommendations.extend(similar_recs)
        
        # 4. 去重和排序
        recommendations = self._deduplicate_and_rank(
            recommendations, 
            profile,
            limit
        )
        
        return recommendations
    
    def _get_style_matched_stocks(self, profile: UserProfile) -> List[StockRecommendation]:
        """基于投资风格推荐"""
        recommendations = []
        style = profile.investment_style
        criteria = self.STYLE_CRITERIA.get(style, {})
        
        # 获取符合条件的股票（简化实现，实际需要查询数据库）
        matched_stocks = self._query_stocks_by_criteria(criteria, profile)
        
        for stock in matched_stocks[:5]:
            recommendations.append(StockRecommendation(
                stock_code=stock['code'],
                stock_name=stock['name'],
                reason=f"符合您的{style.value}投资风格：{criteria.get('description', '')}",
                match_score=stock.get('score', 0.7),
                recommendation_type='style_match',
                supporting_data=stock.get('data', {})
            ))
        
        return recommendations
    
    def _get_sector_stocks(self, profile: UserProfile) -> List[StockRecommendation]:
        """基于偏好板块推荐"""
        recommendations = []
        
        for sector in profile.focus_sectors[:3]:
            sector_stocks = self._get_sector_top_stocks(sector)
            
            for stock in sector_stocks[:2]:
                if stock['code'] not in profile.watchlist:
                    recommendations.append(StockRecommendation(
                        stock_code=stock['code'],
                        stock_name=stock['name'],
                        reason=f"您关注的{sector}板块优质标的",
                        match_score=0.65,
                        recommendation_type='sector_match',
                        supporting_data={'sector': sector}
                    ))
        
        return recommendations
    
    def _get_similar_stocks(self, profile: UserProfile) -> List[StockRecommendation]:
        """基于相似股票推荐"""
        recommendations = []
        
        if not self.retriever:
            return recommendations
        
        try:
            # 取最近关注的股票
            recent_watchlist = profile.watchlist[-5:]
            
            for stock_code in recent_watchlist:
                similar = self.retriever.retrieve_similar_stocks(stock_code, top_k=2)
                
                for s in similar:
                    if s['stock_code'] not in profile.watchlist:
                        recommendations.append(StockRecommendation(
                            stock_code=s['stock_code'],
                            stock_name=s.get('stock_name', s['stock_code']),
                            reason=f"与您关注的股票相似",
                            match_score=s.get('score', 0.6),
                            recommendation_type='similar',
                            supporting_data={'similar_to': stock_code}
                        ))
        except Exception as e:
            logger.warning(f"相似股票推荐失败: {e}")
        
        return recommendations
    
    def _deduplicate_and_rank(self, recommendations: List[StockRecommendation],
                               profile: UserProfile,
                               limit: int) -> List[StockRecommendation]:
        """去重和排序"""
        # 去重
        seen = set()
        unique = []
        for rec in recommendations:
            if rec.stock_code not in seen and rec.stock_code not in profile.watchlist:
                if rec.stock_code not in profile.avoided_sectors:  # 排除回避的
                    seen.add(rec.stock_code)
                    unique.append(rec)
        
        # 按匹配度排序
        unique.sort(key=lambda x: x.match_score, reverse=True)
        
        return unique[:limit]
    
    def generate_morning_brief(self, user_id: str) -> MorningBrief:
        """
        生成个性化早报
        
        Args:
            user_id: 用户ID
            
        Returns:
            早报内容
        """
        profile = self.profile_service.get_profile(user_id)
        
        # 生成问候语
        greeting = self._generate_greeting(profile)
        
        # 市场概览
        market_overview = self._generate_market_overview()
        
        # 自选股摘要
        watchlist_summary = self._summarize_watchlist(profile.watchlist)
        
        # 板块亮点
        sector_highlights = self._get_sector_highlights(profile.focus_sectors)
        
        # 机会和风险（简化，实际应调用洞察引擎）
        opportunities = self._get_opportunities_for_brief(profile)
        risk_alerts = self._get_risks_for_brief(profile)
        
        # 今日待办
        todos = self._generate_todos(profile, opportunities, risk_alerts)
        
        # 学习提示
        learning_tip = self._get_learning_tip(profile)
        
        # AI洞察
        ai_insight = self._generate_daily_insight(profile)
        
        return MorningBrief(
            user_id=user_id,
            greeting=greeting,
            market_overview=market_overview,
            watchlist_summary=watchlist_summary,
            sector_highlights=sector_highlights,
            opportunities=opportunities,
            risk_alerts=risk_alerts,
            todos=todos,
            learning_tip=learning_tip,
            ai_insight=ai_insight
        )
    
    def _generate_greeting(self, profile: UserProfile) -> str:
        """生成个性化问候"""
        hour = datetime.now().hour
        name = profile.nickname or "投资者"
        streak = profile.usage_stats.consecutive_days
        
        if hour < 9:
            time_greeting = "早上好"
        elif hour < 12:
            time_greeting = "上午好"
        elif hour < 18:
            time_greeting = "下午好"
        else:
            time_greeting = "晚上好"
        
        greeting = f"{time_greeting}，{name}！"
        
        if streak > 1:
            greeting += f" 您已连续使用{streak}天，继续保持！"
        
        return greeting
    
    def _generate_market_overview(self) -> str:
        """生成市场概览"""
        # 简化实现，实际应获取真实数据
        return "今日A股三大指数涨跌互现，成交量较昨日有所放大。北向资金净流入，市场情绪偏暖。"
    
    def _summarize_watchlist(self, watchlist: List[str]) -> List[Dict[str, Any]]:
        """汇总自选股情况"""
        summary = []
        
        for code in watchlist[:10]:
            # 简化实现
            summary.append({
                'stock_code': code,
                'stock_name': f'股票{code}',
                'change_percent': 0.0,
                'status': 'normal'
            })
        
        return summary
    
    def _get_sector_highlights(self, sectors: List[str]) -> List[Dict[str, Any]]:
        """获取板块亮点"""
        highlights = []
        
        for sector in sectors[:3]:
            highlights.append({
                'sector': sector,
                'change_percent': 0.0,
                'highlight': f'{sector}板块今日表现平稳'
            })
        
        return highlights
    
    def _get_opportunities_for_brief(self, profile: UserProfile) -> List[Dict[str, Any]]:
        """获取早报机会"""
        # 简化实现，实际应调用洞察引擎
        return [
            {
                'type': 'sector_rotation',
                'title': '板块轮动机会',
                'description': '科技板块近期走强，可关注龙头股'
            }
        ]
    
    def _get_risks_for_brief(self, profile: UserProfile) -> List[Dict[str, Any]]:
        """获取早报风险"""
        return []
    
    def _generate_todos(self, profile: UserProfile,
                        opportunities: List[Dict],
                        risks: List[Dict]) -> List[Dict[str, Any]]:
        """生成今日待办建议"""
        todos = []
        
        # 基于机会生成待办
        for opp in opportunities[:2]:
            todos.append({
                'action': '关注',
                'stock_code': None,
                'stock_name': None,
                'reason': opp.get('description', opp.get('title', '')),
                'priority': 'medium'
            })
        
        # 基于风险生成待办
        for risk in risks[:2]:
            todos.append({
                'action': '检查',
                'stock_code': risk.get('stock_code'),
                'stock_name': risk.get('stock_name'),
                'reason': risk.get('description', risk.get('title', '')),
                'priority': 'high'
            })
        
        # 基于持仓生成待办
        if profile.holdings:
            todos.append({
                'action': '复盘',
                'stock_code': None,
                'stock_name': None,
                'reason': f'检查{len(profile.holdings)}只持仓股票的最新动态',
                'priority': 'medium'
            })
        
        return todos
    
    def _get_learning_tip(self, profile: UserProfile) -> Optional[str]:
        """获取学习提示"""
        tips = {
            'beginner': [
                "💡 今日学习：什么是市盈率(PE)？它是衡量股票估值的重要指标。",
                "💡 今日学习：分散投资可以降低风险，建议持有5-10只不同行业的股票。",
            ],
            'intermediate': [
                "💡 进阶技巧：MACD金叉配合成交量放大，是较强的买入信号。",
                "💡 进阶技巧：关注北向资金流向，它往往领先于市场趋势。",
            ],
            'advanced': [
                "💡 高级策略：可以尝试使用期权对冲持仓风险。",
                "💡 高级策略：关注股票的Beta值，构建适合自己风险偏好的组合。",
            ]
        }
        
        level_tips = tips.get(profile.knowledge_level.value, tips['intermediate'])
        
        import random
        return random.choice(level_tips)
    
    def _generate_daily_insight(self, profile: UserProfile) -> Optional[str]:
        """生成每日洞察"""
        style = profile.investment_style.value
        
        insights = {
            'value': "价值投资者关注：当前市场整体估值处于历史中位数附近，可关注低估值蓝筹股。",
            'growth': "成长投资者关注：科技和新能源赛道持续受到资金青睐，关注业绩高增长标的。",
            'momentum': "趋势投资者关注：市场短期动能偏强，可跟随强势板块操作。",
            'swing': "波段交易者关注：近期市场波动加大，注意把握高抛低吸机会。",
            'quant': "量化投资者关注：多因子模型显示，小市值因子近期表现较好。"
        }
        
        return insights.get(style, insights['growth'])
    
    def _query_stocks_by_criteria(self, criteria: Dict, 
                                   profile: UserProfile) -> List[Dict]:
        """根据条件查询股票"""
        if not self.stock_service:
            logger.error("股票数据服务未初始化")
            return []
        
        try:
            stocks = self.stock_service.query_stocks_by_criteria(criteria)
            # 过滤已关注的
            return [s for s in stocks if s['code'] not in profile.watchlist]
        except Exception as e:
            logger.error(f"查询股票失败: {e}")
            return []
    
    def _get_sector_top_stocks(self, sector: str) -> List[Dict]:
        """获取板块龙头股"""
        if not self.stock_service:
            logger.error("股票数据服务未初始化")
            return []
        
        try:
            return self.stock_service.get_sector_top_stocks(sector)
        except Exception as e:
            logger.error(f"获取板块龙头股失败: {e}")
            return []
