"""
新闻爬虫模块
从多个来源获取股票相关新闻
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import logging
import re

try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    ak = None

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    requests = None
    BeautifulSoup = None

logger = logging.getLogger(__name__)


class NewsSource(Enum):
    """新闻来源"""
    EASTMONEY = "eastmoney"      # 东方财富
    SINA = "sina"                # 新浪财经
    CNSTOCK = "cnstock"          # 中国证券报
    ANNOUNCEMENT = "announcement" # 公司公告
    RESEARCH = "research"        # 研报


@dataclass
class NewsArticle:
    """新闻文章"""
    title: str                   # 标题
    content: str                 # 内容摘要
    source: str                  # 来源
    publish_time: str            # 发布时间
    url: str = ""                # 链接
    stock_codes: List[str] = None  # 相关股票
    keywords: List[str] = None   # 关键词
    importance: float = 0.5      # 重要性 0-1
    
    def __post_init__(self):
        if self.stock_codes is None:
            self.stock_codes = []
        if self.keywords is None:
            self.keywords = []
    
    def to_dict(self) -> Dict:
        return asdict(self)


class NewsCrawler:
    """
    新闻爬虫
    
    功能：
    1. 获取个股相关新闻
    2. 获取市场热点新闻
    3. 获取公司公告
    4. 获取研报摘要
    """
    
    # 重要关键词（用于判断新闻重要性）
    IMPORTANT_KEYWORDS = [
        '重大', '突发', '利好', '利空', '涨停', '跌停',
        '业绩', '预增', '预减', '亏损', '盈利',
        '收购', '并购', '重组', '增持', '减持',
        '回购', '分红', '送股', '转增',
        '违规', '处罚', '调查', '退市',
        '中标', '合同', '订单', '突破',
        '机构', '北向', '外资', '主力'
    ]
    
    # 负面关键词
    NEGATIVE_KEYWORDS = [
        '利空', '下跌', '跌停', '亏损', '预减', '减持',
        '违规', '处罚', '调查', '退市', '风险', '警示',
        '诉讼', '仲裁', '质押', '爆仓', '暴雷'
    ]
    
    # 正面关键词
    POSITIVE_KEYWORDS = [
        '利好', '上涨', '涨停', '盈利', '预增', '增持',
        '回购', '分红', '中标', '突破', '创新高',
        '机构买入', '北向流入', '业绩超预期'
    ]
    
    def __init__(self):
        self.session = None
        if HAS_REQUESTS:
            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
    
    def get_stock_news(self, stock_code: str, 
                       days: int = 7,
                       limit: int = 20) -> List[NewsArticle]:
        """
        获取个股相关新闻
        
        Args:
            stock_code: 股票代码
            days: 获取最近几天的新闻
            limit: 返回数量限制
            
        Returns:
            新闻列表
        """
        news_list = []
        
        # 从AKShare获取新闻
        if HAS_AKSHARE:
            news_list.extend(self._get_news_from_akshare(stock_code, limit))
        
        # 从东方财富获取
        news_list.extend(self._get_news_from_eastmoney(stock_code, limit))
        
        # 去重
        seen_titles = set()
        unique_news = []
        for news in news_list:
            if news.title not in seen_titles:
                seen_titles.add(news.title)
                unique_news.append(news)
        
        # 按时间排序
        unique_news.sort(key=lambda x: x.publish_time, reverse=True)
        
        # 计算重要性
        for news in unique_news:
            news.importance = self._calculate_importance(news)
        
        return unique_news[:limit]
    
    def get_market_news(self, limit: int = 30) -> List[NewsArticle]:
        """
        获取市场热点新闻
        
        Args:
            limit: 返回数量
            
        Returns:
            新闻列表
        """
        news_list = []
        
        if HAS_AKSHARE:
            try:
                # 获取财经新闻
                df = ak.stock_news_em(symbol="财经导读")
                if df is not None and not df.empty:
                    for _, row in df.head(limit).iterrows():
                        news_list.append(NewsArticle(
                            title=str(row.get('新闻标题', '')),
                            content=str(row.get('新闻内容', ''))[:200],
                            source='eastmoney',
                            publish_time=str(row.get('发布时间', '')),
                            url=str(row.get('新闻链接', ''))
                        ))
            except Exception as e:
                logger.warning(f"获取市场新闻失败: {e}")
        
        # 如果没有获取到数据，记录日志
        if not news_list:
            logger.warning("未获取到市场新闻数据")
        
        return news_list[:limit]
    
    def get_stock_announcements(self, stock_code: str,
                                 limit: int = 10) -> List[NewsArticle]:
        """
        获取公司公告
        
        Args:
            stock_code: 股票代码
            limit: 返回数量
            
        Returns:
            公告列表
        """
        announcements = []
        
        if HAS_AKSHARE:
            try:
                code = stock_code.split('.')[0] if '.' in stock_code else stock_code
                df = ak.stock_notice_report(symbol=code)
                
                if df is not None and not df.empty:
                    for _, row in df.head(limit).iterrows():
                        announcements.append(NewsArticle(
                            title=str(row.get('公告标题', '')),
                            content=str(row.get('公告标题', '')),  # 公告通常只有标题
                            source='announcement',
                            publish_time=str(row.get('公告日期', '')),
                            stock_codes=[stock_code],
                            importance=0.7  # 公告通常较重要
                        ))
            except Exception as e:
                logger.warning(f"获取公告失败: {e}")
        
        return announcements
    
    def get_research_reports(self, stock_code: str,
                              limit: int = 10) -> List[NewsArticle]:
        """
        获取研报摘要
        
        Args:
            stock_code: 股票代码
            limit: 返回数量
            
        Returns:
            研报列表
        """
        reports = []
        
        if HAS_AKSHARE:
            try:
                code = stock_code.split('.')[0] if '.' in stock_code else stock_code
                df = ak.stock_research_report_em(symbol=code)
                
                if df is not None and not df.empty:
                    for _, row in df.head(limit).iterrows():
                        reports.append(NewsArticle(
                            title=str(row.get('报告名称', '')),
                            content=f"评级: {row.get('评级', '')} | 机构: {row.get('机构', '')}",
                            source='research',
                            publish_time=str(row.get('日期', '')),
                            stock_codes=[stock_code],
                            importance=0.8  # 研报较重要
                        ))
            except Exception as e:
                logger.warning(f"获取研报失败: {e}")
        
        return reports
    
    def _get_news_from_akshare(self, stock_code: str, 
                                limit: int) -> List[NewsArticle]:
        """从AKShare获取新闻"""
        news_list = []
        
        try:
            code = stock_code.split('.')[0] if '.' in stock_code else stock_code
            df = ak.stock_news_em(symbol=code)
            
            if df is not None and not df.empty:
                for _, row in df.head(limit).iterrows():
                    news_list.append(NewsArticle(
                        title=str(row.get('新闻标题', '')),
                        content=str(row.get('新闻内容', ''))[:300],
                        source='eastmoney',
                        publish_time=str(row.get('发布时间', '')),
                        url=str(row.get('新闻链接', '')),
                        stock_codes=[stock_code]
                    ))
        except Exception as e:
            logger.warning(f"AKShare获取新闻失败: {e}")
        
        return news_list
    
    def _get_news_from_eastmoney(self, stock_code: str,
                                  limit: int) -> List[NewsArticle]:
        """从东方财富获取新闻（备用）"""
        # 如果AKShare已经获取了，这里作为备用
        return []
    
    def _calculate_importance(self, news: NewsArticle) -> float:
        """
        计算新闻重要性
        
        基于关键词匹配计算
        """
        importance = 0.5
        text = news.title + news.content
        
        # 检查重要关键词
        important_count = sum(1 for kw in self.IMPORTANT_KEYWORDS if kw in text)
        importance += min(important_count * 0.1, 0.3)
        
        # 公告和研报默认较重要
        if news.source in ['announcement', 'research']:
            importance += 0.1
        
        return min(importance, 1.0)
    
    def extract_stock_codes(self, text: str) -> List[str]:
        """
        从文本中提取股票代码
        
        Args:
            text: 文本内容
            
        Returns:
            股票代码列表
        """
        # 匹配6位数字股票代码
        pattern = r'[036]\d{5}'
        codes = re.findall(pattern, text)
        return list(set(codes))
    
    def extract_keywords(self, text: str) -> List[str]:
        """
        提取关键词
        
        Args:
            text: 文本内容
            
        Returns:
            关键词列表
        """
        keywords = []
        
        # 检查预定义关键词
        all_keywords = self.IMPORTANT_KEYWORDS + self.POSITIVE_KEYWORDS + self.NEGATIVE_KEYWORDS
        for kw in all_keywords:
            if kw in text:
                keywords.append(kw)
        
        return list(set(keywords))


# 便捷函数
def get_news_crawler() -> NewsCrawler:
    """获取新闻爬虫实例"""
    return NewsCrawler()
