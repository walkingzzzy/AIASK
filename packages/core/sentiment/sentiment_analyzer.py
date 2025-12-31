"""
情绪分析器
基于规则和LLM的新闻情绪分析
"""
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
import logging
import re

from .news_crawler import NewsArticle, NewsCrawler

logger = logging.getLogger(__name__)


class SentimentLevel(Enum):
    """情绪级别"""
    VERY_BULLISH = "极度看多"
    BULLISH = "偏多"
    NEUTRAL = "中性"
    BEARISH = "偏空"
    VERY_BEARISH = "极度看空"


@dataclass
class SentimentResult:
    """情绪分析结果"""
    stock_code: str
    stock_name: str = ""
    
    # 综合情绪
    overall_score: float = 0.0       # -1到1，正为看多
    sentiment_level: str = "中性"
    confidence: float = 0.5
    
    # 分项情绪
    news_sentiment: Dict = field(default_factory=dict)
    announcement_sentiment: Dict = field(default_factory=dict)
    research_sentiment: Dict = field(default_factory=dict)
    
    # 情绪变化
    trend: Dict = field(default_factory=dict)
    
    # 关键事件
    key_events: List[Dict] = field(default_factory=list)
    
    # 更新时间
    updated_at: str = ""
    
    def __post_init__(self):
        if not self.updated_at:
            self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def to_dict(self) -> Dict:
        return asdict(self)


class SentimentAnalyzer:
    """
    情绪分析器
    
    功能：
    1. 分析新闻情绪
    2. 分析公告情绪
    3. 分析研报情绪
    4. 综合情绪评分
    """
    
    # 正面词汇及权重
    POSITIVE_WORDS = {
        # 强正面
        '涨停': 1.0, '大涨': 0.9, '暴涨': 1.0, '飙升': 0.9,
        '创新高': 0.8, '突破': 0.7, '利好': 0.8, '重大利好': 1.0,
        '业绩预增': 0.9, '超预期': 0.8, '盈利': 0.6, '大幅增长': 0.8,
        '增持': 0.7, '回购': 0.7, '分红': 0.6, '送股': 0.5,
        '中标': 0.7, '签约': 0.6, '合作': 0.5, '突破性': 0.8,
        '机构买入': 0.8, '北向流入': 0.7, '主力加仓': 0.7,
        '买入评级': 0.7, '强烈推荐': 0.8, '目标价上调': 0.7,
        # 中等正面
        '上涨': 0.5, '走强': 0.5, '反弹': 0.4, '企稳': 0.3,
        '看好': 0.5, '乐观': 0.5, '积极': 0.4, '向好': 0.4,
        '增长': 0.4, '提升': 0.4, '改善': 0.4, '扩张': 0.4,
    }
    
    # 负面词汇及权重
    NEGATIVE_WORDS = {
        # 强负面
        '跌停': -1.0, '大跌': -0.9, '暴跌': -1.0, '崩盘': -1.0,
        '创新低': -0.8, '破位': -0.7, '利空': -0.8, '重大利空': -1.0,
        '业绩预减': -0.9, '亏损': -0.8, '大幅下滑': -0.8, '暴雷': -1.0,
        '减持': -0.7, '清仓': -0.8, '质押': -0.5, '爆仓': -0.9,
        '违规': -0.8, '处罚': -0.7, '调查': -0.7, '立案': -0.8,
        '退市': -1.0, '风险警示': -0.8, 'ST': -0.7, '*ST': -0.9,
        '诉讼': -0.6, '仲裁': -0.6, '纠纷': -0.5,
        '机构卖出': -0.7, '北向流出': -0.7, '主力出逃': -0.8,
        '卖出评级': -0.7, '目标价下调': -0.7,
        # 中等负面
        '下跌': -0.5, '走弱': -0.5, '回调': -0.4, '承压': -0.4,
        '看空': -0.5, '悲观': -0.5, '谨慎': -0.3, '风险': -0.4,
        '下滑': -0.4, '下降': -0.4, '萎缩': -0.5, '收缩': -0.4,
    }
    
    # 研报评级映射
    RATING_SCORES = {
        '买入': 0.8, '强烈推荐': 0.9, '推荐': 0.7,
        '增持': 0.5, '优于大市': 0.4,
        '中性': 0.0, '持有': 0.0, '观望': 0.0,
        '减持': -0.5, '卖出': -0.8, '回避': -0.7,
    }
    
    def __init__(self):
        self.news_crawler = NewsCrawler()
        # 初始化LLM情绪分析器
        try:
            from .llm_sentiment_analyzer import LLMSentimentAnalyzer
            self.llm_analyzer = LLMSentimentAnalyzer()
            self.use_llm = True
            logger.info("LLM情绪分析器已启用")
        except Exception as e:
            logger.warning(f"LLM情绪分析器初始化失败，将使用关键词匹配: {e}")
            self.llm_analyzer = None
            self.use_llm = False
    
    def analyze_stock(self, stock_code: str, 
                      stock_name: str = "") -> SentimentResult:
        """
        分析个股情绪
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            
        Returns:
            SentimentResult
        """
        # 获取新闻
        news_list = self.news_crawler.get_stock_news(stock_code, days=7, limit=20)
        
        # 获取公告
        announcements = self.news_crawler.get_stock_announcements(stock_code, limit=10)
        
        # 获取研报
        reports = self.news_crawler.get_research_reports(stock_code, limit=10)
        
        # 分析各类情绪
        news_sentiment = self._analyze_news_sentiment(news_list)
        announcement_sentiment = self._analyze_announcement_sentiment(announcements)
        research_sentiment = self._analyze_research_sentiment(reports)
        
        # 综合评分
        overall_score = self._calculate_overall_score(
            news_sentiment, announcement_sentiment, research_sentiment
        )
        
        # 判断情绪级别
        sentiment_level = self._get_sentiment_level(overall_score)
        
        # 提取关键事件
        key_events = self._extract_key_events(news_list + announcements)
        
        # 计算置信度
        confidence = self._calculate_confidence(
            len(news_list), len(announcements), len(reports)
        )
        
        return SentimentResult(
            stock_code=stock_code,
            stock_name=stock_name,
            overall_score=round(overall_score, 2),
            sentiment_level=sentiment_level,
            confidence=round(confidence, 2),
            news_sentiment=news_sentiment,
            announcement_sentiment=announcement_sentiment,
            research_sentiment=research_sentiment,
            trend=self._calculate_trend(news_list),
            key_events=key_events
        )
    
    def analyze_text(self, text: str, use_llm: bool = True) -> Tuple[float, List[str]]:
        """
        分析单条文本的情绪

        Args:
            text: 文本内容
            use_llm: 是否使用LLM分析（如果可用）

        Returns:
            (情绪分数, 匹配的关键词)
        """
        # 如果启用LLM且可用，优先使用LLM分析
        if use_llm and self.use_llm and self.llm_analyzer:
            try:
                llm_result = self.llm_analyzer.analyze_text_sync(text)
                # 提取关键因素作为关键词
                keywords = [f"+{factor}" if llm_result.sentiment_score > 0 else f"-{factor}"
                           for factor in llm_result.key_factors]
                return llm_result.sentiment_score, keywords
            except Exception as e:
                logger.warning(f"LLM分析失败，回退到关键词匹配: {e}")

        # 关键词匹配方法（回退方案）
        score = 0.0
        matched_words = []

        # 检查正面词汇
        for word, weight in self.POSITIVE_WORDS.items():
            if word in text:
                score += weight
                matched_words.append(f"+{word}")

        # 检查负面词汇
        for word, weight in self.NEGATIVE_WORDS.items():
            if word in text:
                score += weight  # weight已经是负数
                matched_words.append(f"-{word.replace('-', '')}")

        # 归一化到-1到1
        if score > 0:
            score = min(score / 3, 1.0)
        else:
            score = max(score / 3, -1.0)

        return score, matched_words
    
    def _analyze_news_sentiment(self, news_list: List[NewsArticle]) -> Dict:
        """分析新闻情绪"""
        if not news_list:
            return {
                'score': 0.0,
                'count': 0,
                'positive': 0,
                'negative': 0,
                'neutral': 0
            }
        
        scores = []
        positive = 0
        negative = 0
        neutral = 0
        
        for news in news_list:
            text = news.title + " " + news.content
            score, _ = self.analyze_text(text)
            scores.append(score)
            
            if score > 0.1:
                positive += 1
            elif score < -0.1:
                negative += 1
            else:
                neutral += 1
        
        avg_score = sum(scores) / len(scores) if scores else 0
        
        return {
            'score': round(avg_score, 2),
            'count': len(news_list),
            'positive': positive,
            'negative': negative,
            'neutral': neutral
        }
    
    def _analyze_announcement_sentiment(self, announcements: List[NewsArticle]) -> Dict:
        """分析公告情绪"""
        if not announcements:
            return {
                'score': 0.0,
                'count': 0,
                'important_count': 0
            }
        
        scores = []
        important_count = 0
        
        for ann in announcements:
            score, _ = self.analyze_text(ann.title)
            scores.append(score)
            
            if ann.importance > 0.6:
                important_count += 1
        
        avg_score = sum(scores) / len(scores) if scores else 0
        
        return {
            'score': round(avg_score, 2),
            'count': len(announcements),
            'important_count': important_count
        }
    
    def _analyze_research_sentiment(self, reports: List[NewsArticle]) -> Dict:
        """分析研报情绪"""
        if not reports:
            return {
                'score': 0.0,
                'count': 0,
                'upgrades': 0,
                'downgrades': 0,
                'maintains': 0
            }
        
        scores = []
        upgrades = 0
        downgrades = 0
        maintains = 0
        
        for report in reports:
            # 从内容中提取评级
            content = report.content
            score = 0.0
            
            for rating, rating_score in self.RATING_SCORES.items():
                if rating in content:
                    score = rating_score
                    if rating_score > 0.3:
                        upgrades += 1
                    elif rating_score < -0.3:
                        downgrades += 1
                    else:
                        maintains += 1
                    break
            
            scores.append(score)
        
        avg_score = sum(scores) / len(scores) if scores else 0
        
        return {
            'score': round(avg_score, 2),
            'count': len(reports),
            'upgrades': upgrades,
            'downgrades': downgrades,
            'maintains': maintains
        }
    
    def _calculate_overall_score(self, news: Dict, 
                                  announcement: Dict, 
                                  research: Dict) -> float:
        """
        计算综合情绪分数
        
        权重：
        - 新闻 40%
        - 公告 30%
        - 研报 30%
        """
        news_score = news.get('score', 0) * 0.4
        ann_score = announcement.get('score', 0) * 0.3
        research_score = research.get('score', 0) * 0.3
        
        return news_score + ann_score + research_score
    
    def _get_sentiment_level(self, score: float) -> str:
        """根据分数获取情绪级别"""
        if score >= 0.5:
            return SentimentLevel.VERY_BULLISH.value
        elif score >= 0.2:
            return SentimentLevel.BULLISH.value
        elif score >= -0.2:
            return SentimentLevel.NEUTRAL.value
        elif score >= -0.5:
            return SentimentLevel.BEARISH.value
        else:
            return SentimentLevel.VERY_BEARISH.value
    
    def _extract_key_events(self, articles: List[NewsArticle], 
                            top_n: int = 5) -> List[Dict]:
        """提取关键事件"""
        events = []
        
        # 按重要性排序
        sorted_articles = sorted(articles, 
                                  key=lambda x: x.importance, 
                                  reverse=True)
        
        for article in sorted_articles[:top_n]:
            score, keywords = self.analyze_text(article.title)
            
            impact = "positive" if score > 0.1 else ("negative" if score < -0.1 else "neutral")
            
            events.append({
                'time': article.publish_time,
                'event': article.title,
                'impact': impact,
                'source': article.source,
                'importance': article.importance
            })
        
        return events
    
    def _calculate_confidence(self, news_count: int, 
                               ann_count: int, 
                               report_count: int) -> float:
        """计算置信度"""
        # 数据越多置信度越高
        total = news_count + ann_count + report_count
        
        if total >= 30:
            return 0.9
        elif total >= 20:
            return 0.8
        elif total >= 10:
            return 0.7
        elif total >= 5:
            return 0.6
        else:
            return 0.5
    
    def _calculate_trend(self, news_list: List[NewsArticle]) -> Dict:
        """计算情绪变化趋势"""
        if len(news_list) < 2:
            return {
                'direction': '数据不足',
                'change': 0.0
            }
        
        # 按时间分组（简化：前半部分vs后半部分）
        mid = len(news_list) // 2
        recent = news_list[:mid]
        older = news_list[mid:]
        
        recent_scores = [self.analyze_text(n.title + n.content)[0] for n in recent]
        older_scores = [self.analyze_text(n.title + n.content)[0] for n in older]
        
        recent_avg = sum(recent_scores) / len(recent_scores) if recent_scores else 0
        older_avg = sum(older_scores) / len(older_scores) if older_scores else 0
        
        change = recent_avg - older_avg
        
        if change > 0.1:
            direction = "改善"
        elif change < -0.1:
            direction = "恶化"
        else:
            direction = "稳定"
        
        return {
            'direction': direction,
            'change': round(change, 2),
            'recent_score': round(recent_avg, 2),
            'older_score': round(older_avg, 2)
        }


def analyze_sentiment(stock_code: str, stock_name: str = "") -> SentimentResult:
    """便捷函数：分析股票情绪"""
    analyzer = SentimentAnalyzer()
    return analyzer.analyze_stock(stock_code, stock_name)
