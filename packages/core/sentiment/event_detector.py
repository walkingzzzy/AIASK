"""
事件检测器
检测和分类股票相关的重大事件
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
import re
import logging

from .news_crawler import NewsArticle

logger = logging.getLogger(__name__)


class EventType(Enum):
    """事件类型"""
    # 业绩相关
    EARNINGS_BEAT = "业绩超预期"
    EARNINGS_MISS = "业绩不及预期"
    EARNINGS_PREVIEW = "业绩预告"
    
    # 资本运作
    MERGER = "并购重组"
    SHARE_BUYBACK = "股份回购"
    SHARE_INCREASE = "增持"
    SHARE_DECREASE = "减持"
    DIVIDEND = "分红派息"
    
    # 经营相关
    CONTRACT_WIN = "中标/签约"
    PRODUCT_LAUNCH = "新产品发布"
    CAPACITY_EXPANSION = "产能扩张"
    
    # 风险事件
    REGULATORY_ACTION = "监管处罚"
    LITIGATION = "诉讼仲裁"
    DELISTING_RISK = "退市风险"
    PLEDGE_RISK = "质押风险"
    
    # 市场事件
    LIMIT_UP = "涨停"
    LIMIT_DOWN = "跌停"
    NORTH_FUND_BUY = "北向资金买入"
    NORTH_FUND_SELL = "北向资金卖出"
    INSTITUTION_BUY = "机构买入"
    INSTITUTION_SELL = "机构卖出"
    
    # 评级变动
    RATING_UPGRADE = "评级上调"
    RATING_DOWNGRADE = "评级下调"
    
    # 其他
    OTHER = "其他"


class EventImpact(Enum):
    """事件影响"""
    VERY_POSITIVE = "重大利好"
    POSITIVE = "利好"
    NEUTRAL = "中性"
    NEGATIVE = "利空"
    VERY_NEGATIVE = "重大利空"


@dataclass
class StockEvent:
    """股票事件"""
    stock_code: str
    stock_name: str = ""
    event_type: str = ""
    event_title: str = ""
    event_summary: str = ""
    impact: str = "中性"
    impact_score: float = 0.0      # -1到1
    confidence: float = 0.5
    source: str = ""
    event_time: str = ""
    keywords: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return asdict(self)


class EventDetector:
    """
    事件检测器
    
    功能：
    1. 从新闻中检测事件
    2. 分类事件类型
    3. 评估事件影响
    """
    
    # 事件模式匹配规则
    EVENT_PATTERNS = {
        # 业绩相关
        EventType.EARNINGS_BEAT: [
            r'业绩.*超预期', r'净利润.*增长', r'营收.*大增',
            r'业绩.*翻倍', r'盈利.*超出'
        ],
        EventType.EARNINGS_MISS: [
            r'业绩.*不及预期', r'净利润.*下滑', r'营收.*下降',
            r'业绩.*亏损', r'盈利.*低于'
        ],
        EventType.EARNINGS_PREVIEW: [
            r'业绩预告', r'业绩快报', r'业绩预增', r'业绩预减',
            r'业绩预亏', r'业绩预盈'
        ],
        
        # 资本运作
        EventType.MERGER: [
            r'并购', r'重组', r'收购', r'合并', r'借壳'
        ],
        EventType.SHARE_BUYBACK: [
            r'回购', r'股份回购', r'注销'
        ],
        EventType.SHARE_INCREASE: [
            r'增持', r'举牌', r'买入'
        ],
        EventType.SHARE_DECREASE: [
            r'减持', r'清仓', r'套现'
        ],
        EventType.DIVIDEND: [
            r'分红', r'派息', r'送股', r'转增'
        ],
        
        # 经营相关
        EventType.CONTRACT_WIN: [
            r'中标', r'签约', r'签订.*合同', r'获得.*订单'
        ],
        EventType.PRODUCT_LAUNCH: [
            r'新产品', r'发布会', r'上市.*产品', r'推出'
        ],
        EventType.CAPACITY_EXPANSION: [
            r'扩产', r'产能.*扩张', r'新建.*项目', r'投产'
        ],
        
        # 风险事件
        EventType.REGULATORY_ACTION: [
            r'处罚', r'违规', r'警示函', r'监管', r'立案'
        ],
        EventType.LITIGATION: [
            r'诉讼', r'仲裁', r'起诉', r'被告'
        ],
        EventType.DELISTING_RISK: [
            r'退市', r'\*ST', r'暂停上市', r'终止上市'
        ],
        EventType.PLEDGE_RISK: [
            r'质押', r'爆仓', r'平仓', r'强制'
        ],
        
        # 市场事件
        EventType.LIMIT_UP: [
            r'涨停', r'一字板', r'连板'
        ],
        EventType.LIMIT_DOWN: [
            r'跌停', r'一字跌停'
        ],
        EventType.NORTH_FUND_BUY: [
            r'北向.*买入', r'北向.*流入', r'外资.*增持'
        ],
        EventType.NORTH_FUND_SELL: [
            r'北向.*卖出', r'北向.*流出', r'外资.*减持'
        ],
        EventType.INSTITUTION_BUY: [
            r'机构.*买入', r'机构.*增持', r'基金.*加仓'
        ],
        EventType.INSTITUTION_SELL: [
            r'机构.*卖出', r'机构.*减持', r'基金.*减仓'
        ],
        
        # 评级变动
        EventType.RATING_UPGRADE: [
            r'上调.*评级', r'目标价.*上调', r'买入评级', r'强烈推荐'
        ],
        EventType.RATING_DOWNGRADE: [
            r'下调.*评级', r'目标价.*下调', r'卖出评级', r'减持评级'
        ],
    }
    
    # 事件影响评分
    EVENT_IMPACT_SCORES = {
        EventType.EARNINGS_BEAT: 0.8,
        EventType.EARNINGS_MISS: -0.8,
        EventType.EARNINGS_PREVIEW: 0.0,  # 取决于具体内容
        EventType.MERGER: 0.5,
        EventType.SHARE_BUYBACK: 0.6,
        EventType.SHARE_INCREASE: 0.5,
        EventType.SHARE_DECREASE: -0.5,
        EventType.DIVIDEND: 0.4,
        EventType.CONTRACT_WIN: 0.6,
        EventType.PRODUCT_LAUNCH: 0.4,
        EventType.CAPACITY_EXPANSION: 0.5,
        EventType.REGULATORY_ACTION: -0.7,
        EventType.LITIGATION: -0.5,
        EventType.DELISTING_RISK: -0.9,
        EventType.PLEDGE_RISK: -0.6,
        EventType.LIMIT_UP: 0.7,
        EventType.LIMIT_DOWN: -0.7,
        EventType.NORTH_FUND_BUY: 0.5,
        EventType.NORTH_FUND_SELL: -0.5,
        EventType.INSTITUTION_BUY: 0.5,
        EventType.INSTITUTION_SELL: -0.5,
        EventType.RATING_UPGRADE: 0.6,
        EventType.RATING_DOWNGRADE: -0.6,
        EventType.OTHER: 0.0,
    }
    
    def detect_events(self, articles: List[NewsArticle], 
                      stock_code: str,
                      stock_name: str = "") -> List[StockEvent]:
        """
        从文章列表中检测事件
        
        Args:
            articles: 文章列表
            stock_code: 股票代码
            stock_name: 股票名称
            
        Returns:
            事件列表
        """
        events = []
        
        for article in articles:
            event = self.detect_single_event(article, stock_code, stock_name)
            if event and event.event_type != EventType.OTHER.value:
                events.append(event)
        
        # 按影响分数排序
        events.sort(key=lambda x: abs(x.impact_score), reverse=True)
        
        return events
    
    def detect_single_event(self, article: NewsArticle,
                            stock_code: str,
                            stock_name: str = "") -> Optional[StockEvent]:
        """
        检测单篇文章的事件
        
        Args:
            article: 文章
            stock_code: 股票代码
            stock_name: 股票名称
            
        Returns:
            StockEvent或None
        """
        text = article.title + " " + article.content
        
        # 检测事件类型
        event_type, matched_keywords = self._detect_event_type(text)
        
        # 计算影响分数
        base_score = self.EVENT_IMPACT_SCORES.get(event_type, 0.0)
        impact_score = self._adjust_impact_score(base_score, text)
        
        # 判断影响级别
        impact = self._get_impact_level(impact_score)
        
        # 计算置信度
        confidence = self._calculate_confidence(len(matched_keywords), article.importance)
        
        return StockEvent(
            stock_code=stock_code,
            stock_name=stock_name,
            event_type=event_type.value,
            event_title=article.title,
            event_summary=article.content[:200] if article.content else "",
            impact=impact,
            impact_score=round(impact_score, 2),
            confidence=round(confidence, 2),
            source=article.source,
            event_time=article.publish_time,
            keywords=matched_keywords
        )
    
    def _detect_event_type(self, text: str) -> tuple:
        """检测事件类型"""
        matched_keywords = []
        best_match = EventType.OTHER
        max_matches = 0
        
        for event_type, patterns in self.EVENT_PATTERNS.items():
            matches = 0
            keywords = []
            
            for pattern in patterns:
                if re.search(pattern, text):
                    matches += 1
                    keywords.append(pattern)
            
            if matches > max_matches:
                max_matches = matches
                best_match = event_type
                matched_keywords = keywords
        
        return best_match, matched_keywords
    
    def _adjust_impact_score(self, base_score: float, text: str) -> float:
        """根据文本内容调整影响分数"""
        score = base_score
        
        # 强化词
        if any(word in text for word in ['重大', '突发', '紧急', '大幅']):
            score *= 1.3
        
        # 弱化词
        if any(word in text for word in ['小幅', '轻微', '略微', '可能']):
            score *= 0.7
        
        # 归一化
        return max(-1.0, min(1.0, score))
    
    def _get_impact_level(self, score: float) -> str:
        """获取影响级别"""
        if score >= 0.6:
            return EventImpact.VERY_POSITIVE.value
        elif score >= 0.2:
            return EventImpact.POSITIVE.value
        elif score >= -0.2:
            return EventImpact.NEUTRAL.value
        elif score >= -0.6:
            return EventImpact.NEGATIVE.value
        else:
            return EventImpact.VERY_NEGATIVE.value
    
    def _calculate_confidence(self, match_count: int, 
                               importance: float) -> float:
        """计算置信度"""
        base_confidence = 0.5
        
        # 匹配数量加成
        base_confidence += min(match_count * 0.1, 0.3)
        
        # 重要性加成
        base_confidence += (importance - 0.5) * 0.2
        
        return min(base_confidence, 1.0)
    
    def get_event_summary(self, events: List[StockEvent]) -> Dict:
        """
        生成事件摘要
        
        Args:
            events: 事件列表
            
        Returns:
            摘要字典
        """
        if not events:
            return {
                'total_events': 0,
                'positive_events': 0,
                'negative_events': 0,
                'neutral_events': 0,
                'overall_impact': '无事件',
                'key_events': []
            }
        
        positive = sum(1 for e in events if e.impact_score > 0.1)
        negative = sum(1 for e in events if e.impact_score < -0.1)
        neutral = len(events) - positive - negative
        
        avg_impact = sum(e.impact_score for e in events) / len(events)
        
        if avg_impact > 0.2:
            overall = "偏正面"
        elif avg_impact < -0.2:
            overall = "偏负面"
        else:
            overall = "中性"
        
        return {
            'total_events': len(events),
            'positive_events': positive,
            'negative_events': negative,
            'neutral_events': neutral,
            'overall_impact': overall,
            'avg_impact_score': round(avg_impact, 2),
            'key_events': [e.to_dict() for e in events[:5]]
        }


def detect_events(articles: List[NewsArticle], 
                  stock_code: str,
                  stock_name: str = "") -> List[StockEvent]:
    """便捷函数：检测事件"""
    detector = EventDetector()
    return detector.detect_events(articles, stock_code, stock_name)
