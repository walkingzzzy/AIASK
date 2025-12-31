"""
扩展情绪指标计算模块
包含6个新增情绪面指标：股吧情绪、雪球情绪、微博热度、百度搜索、机构关注、市场人气

本模块调用社交媒体情绪数据源模块获取数据
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from .indicator_registry import (IndicatorBase, IndicatorCategory, IndicatorResult,
    auto_register, get_registry
)

# 导入情绪数据源模块
try:
    from a_stock_analysis.sentiment.social_media import (
        SentimentAggregator,
        get_stock_sentiment_quick,
        GubaCrawler,
        XueqiuCrawler,
        WeiboCrawler,
        BaiduIndexCrawler
    )
    SENTIMENT_MODULE_AVAILABLE = True
except ImportError:
    SENTIMENT_MODULE_AVAILABLE = False


@auto_register
class GubaSentimentIndicator(IndicatorBase):
    """股吧情绪指数指标
    
    从东方财富股吧数据计算情绪分数
    """
    name = "guba_sentiment"
    display_name = "股吧情绪指数"
    category = IndicatorCategory.SENTIMENT
    description = "从股吧数据计算的情绪分数"
    
    def __init__(self):
        super().__init__()
        if SENTIMENT_MODULE_AVAILABLE:
            self._crawler = GubaCrawler()
        else:
            self._crawler = None
    
    def calculate(self, stock_code: str = None, sentiment_data: Dict[str, Any] = None,
                  **kwargs) -> Dict[str, Any]:
        # 优先使用传入的情绪数据
        if sentiment_data and 'guba' in sentiment_data:
            guba_data = sentiment_data['guba']
            score = guba_data.get('sentiment_score', 0)
            post_count = guba_data.get('post_count', 0)
        elif self._crawler and stock_code:
            try:
                posts = self._crawler.get_stock_posts(stock_code, page=1)
                guba_sentiment = self._crawler.get_post_sentiment(posts)
                score = guba_sentiment.get('sentiment_score', 0)
                post_count = len(posts)
            except Exception as e:
                return {'value': None, 'description': f'获取股吧数据失败: {str(e)}'}
        else:
            return {'value': None, 'description': '数据不足或模块不可用'}
        
        # score范围通常是-1到1
        normalized_score = (score + 1) / 2 * 100  # 转换为0-100
        
        if score > 0.5:
            desc = f"股吧情绪极度乐观 ({score:.2f})"
            sentiment = "极度看多"
        elif score > 0.2:
            desc = f"股吧情绪偏乐观 ({score:.2f})"
            sentiment = "偏多"
        elif score > -0.2:
            desc = f"股吧情绪中性 ({score:.2f})"
            sentiment = "中性"
        elif score > -0.5:
            desc = f"股吧情绪偏悲观 ({score:.2f})"
            sentiment = "偏空"
        else:
            desc = f"股吧情绪极度悲观 ({score:.2f})"
            sentiment = "极度看空"
        
        return {
            'value': normalized_score,
            'description': desc,
            'extra_data': {
                'raw_score': score,
                'post_count': post_count,
                'sentiment': sentiment
            }
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return max(0, min(100, value))


@auto_register
class XueqiuSentimentIndicator(IndicatorBase):
    """雪球情绪指数指标
    
    从雪球数据计算情绪分数
    """
    name = "xueqiu_sentiment"
    display_name = "雪球情绪指数"
    category = IndicatorCategory.SENTIMENT
    description = "从雪球数据计算的情绪分数"
    
    def __init__(self):
        super().__init__()
        if SENTIMENT_MODULE_AVAILABLE:
            self._crawler = XueqiuCrawler()
        else:
            self._crawler = None
    
    def calculate(self, stock_code: str = None, sentiment_data: Dict[str, Any] = None,
                  **kwargs) -> Dict[str, Any]:
        if sentiment_data and 'xueqiu' in sentiment_data:
            xueqiu_data = sentiment_data['xueqiu']
            score = xueqiu_data.get('sentiment_score', 0)
            mentions = xueqiu_data.get('mentions', 0)
        elif self._crawler and stock_code:
            try:
                posts = self._crawler.get_stock_discussions(stock_code)
                xueqiu_sentiment = self._crawler.analyze_posts_sentiment(posts)
                score = xueqiu_sentiment.get('sentiment_score', 0)
                mentions = len(posts)
            except Exception as e:
                return {'value': None, 'description': f'获取雪球数据失败: {str(e)}'}
        else:
            return {'value': None, 'description': '数据不足或模块不可用'}
        
        normalized_score = (score + 1) / 2 * 100
        
        if score > 0.5:
            desc = f"雪球大V看多 ({score:.2f})"
        elif score > 0.2:
            desc = f"雪球偏乐观 ({score:.2f})"
        elif score > -0.2:
            desc = f"雪球情绪中性 ({score:.2f})"
        elif score > -0.5:
            desc = f"雪球偏悲观 ({score:.2f})"
        else:
            desc = f"雪球普遍看空 ({score:.2f})"
        
        return {
            'value': normalized_score,
            'description': desc,
            'extra_data': {
                'raw_score': score,
                'mentions': mentions
            }
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return max(0, min(100, value))


@auto_register
class WeiboHeatIndicator(IndicatorBase):
    """微博热度指数指标
    
    微博相关话题热度
    """
    name = "weibo_heat"
    display_name = "微博热度指数"
    category = IndicatorCategory.SENTIMENT
    description = "微博相关话题热度"
    
    def __init__(self):
        super().__init__()
        if SENTIMENT_MODULE_AVAILABLE:
            self._crawler = WeiboCrawler()
        else:
            self._crawler = None
    
    def calculate(self, stock_name: str = None, sentiment_data: Dict[str, Any] = None,
                  **kwargs) -> Dict[str, Any]:
        if sentiment_data and 'weibo' in sentiment_data:
            weibo_data = sentiment_data['weibo']
            heat_score = weibo_data.get('heat_score', 0)
            post_count = weibo_data.get('post_count', 0)
            sentiment_score = weibo_data.get('sentiment_score', 0)
        elif self._crawler and stock_name:
            try:
                posts = self._crawler.search_stock_posts(stock_name)
                weibo_sentiment = self._crawler.analyze_posts_sentiment(posts)
                heat_score = len(posts) * 10  # 简单热度计算
                post_count = len(posts)
                sentiment_score = weibo_sentiment.get('sentiment_score', 0)
            except Exception as e:
                return {'value': None, 'description': f'获取微博数据失败: {str(e)}'}
        else:
            return {'value': None, 'description': '数据不足或模块不可用'}
        
        # 热度标准化
        if heat_score > 1000:
            normalized_heat = 100
            desc = f"微博热度爆表，高度关注 (热度: {heat_score})"
        elif heat_score > 500:
            normalized_heat = 80
            desc = f"微博热度很高 (热度: {heat_score})"
        elif heat_score > 100:
            normalized_heat = 60
            desc = f"微博热度中等 (热度: {heat_score})"
        elif heat_score > 20:
            normalized_heat = 40
            desc = f"微博热度较低 (热度: {heat_score})"
        else:
            normalized_heat = 20
            desc = f"微博几乎无热度 (热度: {heat_score})"
        
        return {
            'value': normalized_heat,
            'description': desc,
            'extra_data': {
                'heat_score': heat_score,
                'post_count': post_count,
                'sentiment_score': sentiment_score
            }
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        # 高热度是双刃剑，适中最佳
        if 40 <= value <= 70:
            return 70.0
        elif value > 90:
            return 55.0  # 过热可能有风险
        elif value < 30:
            return 45.0  # 太冷可能缺乏关注
        else:
            return value * 0.8


@auto_register
class BaiduSearchIndicator(IndicatorBase):
    """百度搜索指数指标
    
    百度搜索热度趋势
    """
    name = "baidu_search"
    display_name = "百度搜索指数"
    category = IndicatorCategory.SENTIMENT
    description = "百度搜索热度趋势"
    
    def __init__(self):
        super().__init__()
        if SENTIMENT_MODULE_AVAILABLE:
            self._crawler = BaiduIndexCrawler()
        else:
            self._crawler = None
    
    def calculate(self, stock_name: str = None, sentiment_data: Dict[str, Any] = None,
                  **kwargs) -> Dict[str, Any]:
        if sentiment_data and 'baidu' in sentiment_data:
            baidu_data = sentiment_data['baidu']
            search_index = baidu_data.get('search_index', 0)
            trend_direction = baidu_data.get('trend_direction', '数据不足')
            change_rate = baidu_data.get('change_rate', 0)
        elif self._crawler and stock_name:
            try:
                baidu_data = self._crawler.get_stock_heat_index(stock_name)
                search_index = baidu_data.get('search_index', 0)
                trend_direction = baidu_data.get('trend_direction', '数据不足')
                change_rate = baidu_data.get('change_rate', 0)
            except Exception as e:
                return {'value': None, 'description': f'获取百度指数失败: {str(e)}'}
        else:
            return {'value': None, 'description': '数据不足或模块不可用'}
        
        # 根据趋势方向评分
        trend_scores = {
            '大幅上升': 85,
            '小幅上升': 70,
            '基本持平': 50,
            '小幅下降': 35,
            '大幅下降': 20,
            '数据不足': 50
        }
        
        score = trend_scores.get(trend_direction, 50)
        desc = f"百度搜索{trend_direction} (指数: {search_index}, 变化: {change_rate:+.1f}%)"
        
        return {
            'value': score,
            'description': desc,
            'extra_data': {
                'search_index': search_index,
                'trend_direction': trend_direction,
                'change_rate': change_rate
            }
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return max(0, min(100, value))


@auto_register
class InstitutionAttentionIndicator(IndicatorBase):
    """机构关注度指标
    
    近期研报数量
    """
    name = "institution_attention"
    display_name = "机构关注度"
    category = IndicatorCategory.SENTIMENT
    description = "近期研报数量，反映机构关注程度"
    
    def calculate(self, research_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if research_data is None:
            return {'value': None, 'description': '数据不足'}
        
        # 近30天研报数量
        report_count_30d = research_data.get('report_count_30d', 0)
        # 近90天研报数量
        report_count_90d = research_data.get('report_count_90d', 0)
        # 平均评级
        avg_rating = research_data.get('avg_rating', 0)  # 1-5, 5是最看好
        # 目标价上调/下调比例
        target_price_up_ratio = research_data.get('target_price_up_ratio', 0.5)
        
        # 计算关注度得分
        if report_count_30d > 10:
            attention_score = 90
            desc = f"机构高度关注 ({report_count_30d}篇研报/月)"
        elif report_count_30d > 5:
            attention_score = 75
            desc = f"机构关注较多 ({report_count_30d}篇研报/月)"
        elif report_count_30d > 2:
            attention_score = 55
            desc = f"机构关注适中 ({report_count_30d}篇研报/月)"
        elif report_count_30d > 0:
            attention_score = 40
            desc = f"机构关注较少 ({report_count_30d}篇研报/月)"
        else:
            attention_score = 25
            desc = "机构几乎无关注"
        
        return {
            'value': attention_score,
            'description': desc,
            'extra_data': {
                'report_count_30d': report_count_30d,
                'report_count_90d': report_count_90d,
                'avg_rating': avg_rating,
                'target_price_up_ratio': target_price_up_ratio
            }
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return max(0, min(100, value))


@auto_register
class MarketPopularityIndicator(IndicatorBase):
    """市场人气排名指标
    
    成交活跃度排名
    """
    name = "market_popularity"
    display_name = "市场人气排名"
    category = IndicatorCategory.SENTIMENT
    description = "成交活跃度排名"
    
    def calculate(self, market_data: Dict[str, Any] = None,
                  volume: pd.Series = None, **kwargs) -> Dict[str, Any]:
        if market_data is None and volume is None:
            return {'value': None, 'description': '数据不足'}
        
        if market_data:
            # 使用市场排名数据
            turnover_rank = market_data.get('turnover_rank', 0)  # 换手率排名百分位
            volume_rank = market_data.get('volume_rank', 0)  # 成交量排名百分位
            popularity_rank = (turnover_rank + volume_rank) / 2
        elif volume is not None and len(volume) >= 20:
            # 基于成交量变化计算
            recent_vol = volume.tail(5).mean()
            avg_vol = volume.tail(20).mean()
            vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1
            
            if vol_ratio > 3:
                popularity_rank = 95
            elif vol_ratio > 2:
                popularity_rank = 80
            elif vol_ratio > 1.5:
                popularity_rank = 65
            elif vol_ratio > 1:
                popularity_rank = 50
            elif vol_ratio > 0.7:
                popularity_rank = 35
            else:
                popularity_rank = 20
        else:
            return {'value': None, 'description': '数据不足'}
        
        if popularity_rank > 80:
            desc = f"市场人气极高 (排名前{100-popularity_rank:.0f}%)"
        elif popularity_rank > 60:
            desc = f"市场人气较高 (排名前{100-popularity_rank:.0f}%)"
        elif popularity_rank > 40:
            desc = f"市场人气中等 (排名中间{100-popularity_rank:.0f}%)"
        elif popularity_rank > 20:
            desc = f"市场人气较低 (排名后{popularity_rank:.0f}%)"
        else:
            desc = f"市场人气很低 (排名后{popularity_rank:.0f}%)"
        
        return {
            'value': popularity_rank,
            'description': desc,
            'extra_data': {
                'turnover_rank': market_data.get('turnover_rank') if market_data else None,
                'volume_rank': market_data.get('volume_rank') if market_data else None
            }
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        # 适度人气（40-70）最佳
        if 40 <= value <= 70:
            return 70.0
        elif value > 90:
            return 55.0  # 过热
        elif value < 20:
            return 40.0  # 过冷
        else:
            return value * 0.9


# ==================== 指标汇总 ====================

SENTIMENT_EXTENDED_INDICATORS = [
    'guba_sentiment',
    'xueqiu_sentiment',
    'weibo_heat',
    'baidu_search',
    'institution_attention',
    'market_popularity',
]


def get_all_sentiment_extended_indicators():
    """获取所有扩展情绪面指标名称列表"""
    return SENTIMENT_EXTENDED_INDICATORS.copy()
