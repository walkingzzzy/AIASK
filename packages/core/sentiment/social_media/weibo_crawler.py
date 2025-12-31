"""
微博财经数据采集器

实现功能：
1. 股票相关话题爬取
2. 财经博主帖子获取
3. 热搜话题分析
4. 情感分析功能
"""
import re
import random
import time
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import quote
from dataclasses import dataclass

try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# 配置日志
logger = logging.getLogger(__name__)


@dataclass
class WeiboPost:
    """微博帖子数据类"""
    post_id: str
    text: str
    user_name: str
    user_id: str
    created_at: str
    reposts_count: int
    comments_count: int
    attitudes_count: int
    sentiment: float = 0.0


class WeiboCrawler:
    """微博财经数据爬虫
    
    实现对微博公开数据的获取和情感分析功能。
    使用微博移动端接口，部分接口无需登录即可访问。
    Attributes:
        base_url: 微博移动端基础URL
        search_url: 搜索API地址
        headers: 请求头
    Example:
        >>> crawler = WeiboCrawler()
        >>> posts = crawler.search_stock_posts("茅台")
        >>> sentiment = crawler.analyze_posts_sentiment(posts)>>> print(sentiment)
    """

    # User-Agent列表（移动端）
    USER_AGENTS = [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",]

    # 看多关键词
    BULLISH_KEYWORDS = [
        "涨", "牛", "买入", "加仓", "看好", "利好", "突破", "新高", "放量", "底部",
        "起飞", "翻倍", "龙头", "黑马", "强势", "爆发", "启动", "反弹", "大涨", "暴涨",
        "涨停", "金股", "牛股", "潜力", "价值", "低估", "布局", "机会", "抄底", "拉升",
        "走强", "看涨", "赚钱", "盈利", "分红", "利润", "增长", "业绩", "订单", "签约"
    ]

    # 看空关键词
    BEARISH_KEYWORDS = [
        "跌", "熊", "卖出", "减仓", "看空", "利空", "破位", "新低", "缩量", "顶部",
        "下跌", "暴跌", "跌停", "割肉", "清仓", "套牢", "亏损", "危险", "风险", "崩盘",
        "跳水", "大跌", "腰斩", "血亏", "完蛋", "垃圾", "跑路", "警惕", "回调", "走弱",
        "看跌", "做空", "赔钱", "坑人", "远离", "暴雷", "爆仓", "退市", "造假", "处罚"
    ]

    # 财经相关话题标签
    FINANCE_TOPICS = [
        "股票", "A股", "股市", "大盘", "牛市", "熊市", "基金", "投资",
        "财经", "金融", "证券", "涨停", "跌停", "龙头股", "概念股"
    ]

    def __init__(
        self,
        min_delay: float = 2.0,
        max_delay: float = 5.0,
        timeout: int = 15
    ):
        """
        初始化微博爬虫
        
        Args:
            min_delay: 最小请求延迟（秒）
            max_delay: 最大请求延迟（秒）
            timeout: 请求超时时间（秒）
        """
        self.base_url = "https://m.weibo.cn"
        self.search_url = "https://m.weibo.cn/api/container/getIndex"
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.timeout = timeout
        self._last_request_time =0
        self._session = Noneif requests is None:
            logger.warning("requests库未安装，请使用 pip install requests")

    def _get_session(self) -> requests.Session:
        """获取或创建会话"""
        if self._session is None:
            self._session = requests.Session()
            # 访问首页获取cookie
            try:
                self._session.get(
                    self.base_url,
                    headers=self._get_random_headers(),
                    timeout=self.timeout
                )
            except Exception as e:
                logger.debug(f"获取cookie失败: {e}")
                
        return self._session

    def _get_random_headers(self) -> Dict[str, str]:
        """获取随机请求头"""
        return {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": "https://m.weibo.cn/",
            "X-Requested-With": "XMLHttpRequest",
            "MWeibo-Pwa": "1",}

    def _random_delay(self) -> None:
        """随机延迟，避免被反爬"""
        elapsed = time.time() - self._last_request_time
        delay = random.uniform(self.min_delay, self.max_delay)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_time = time.time()

    def search_stock_posts(
        self,
        keyword: str,
        page: int = 1,
        count: int = 20
    ) -> List[Dict[str, Any]]:
        """
        搜索股票相关帖子
        
        Args:
            keyword: 搜索关键词（如股票名称）
            page: 页码
            count: 数量（建议不超过20）
            
        Returns:帖子列表
        """
        if requests is None:
            logger.error("requests库未安装")
            return []
        try:
            self._random_delay()
            
            session = self._get_session()
            
            # 使用微博移动端搜索API
            params = {
                "containerid": f"100103type=1&q={quote(keyword)}",
                "page_type": "searchall",
                "page": page,
            }
            
            response = session.get(
                self.search_url,
                params=params,
                headers=self._get_random_headers(),
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.warning(f"搜索请求失败，状态码: {response.status_code}")
                return []
                
            data = response.json()
            return self._parse_search_response(data)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"请求异常: {e}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return []

    def _parse_search_response(self, data: Dict) -> List[Dict[str, Any]]:
        """解析搜索响应"""
        posts = []
        
        try:
            cards = data.get('data', {}).get('cards', [])
            
            for card in cards:
                #跳过非微博类型的卡片
                card_type = card.get('card_type')
                if card_type == 9:  # 单条微博
                    mblog = card.get('mblog', {})
                    if mblog:
                        post = self._parse_mblog(mblog)
                        if post:
                            posts.append(post)
                elif card_type == 11:  # 微博列表
                    card_group = card.get('card_group', [])
                    for item in card_group:
                        if item.get('card_type') == 9:
                            mblog = item.get('mblog', {})
                            if mblog:
                                post = self._parse_mblog(mblog)
                                if post:
                                    posts.append(post)    
        except Exception as e:
            logger.error(f"解析搜索结果失败: {e}")
            
        return posts

    def _parse_mblog(self, mblog: Dict) -> Optional[Dict[str, Any]]:
        """解析单条微博"""
        try:
            user = mblog.get('user', {}) or {}
            
            # 提取文本，移除HTML标签
            text = mblog.get('text', '')
            text = self._clean_text(text)
            
            post = {
                'post_id': str(mblog.get('id', '')),
                'mid': str(mblog.get('mid', '')),
                'text': text,
                'user_name': user.get('screen_name', ''),
                'user_id': str(user.get('id', '')),
                'created_at': mblog.get('created_at', ''),
                'reposts_count': int(mblog.get('reposts_count', 0) or 0),
                'comments_count': int(mblog.get('comments_count', 0) or 0),
                'attitudes_count': int(mblog.get('attitudes_count', 0) or 0),  # 点赞数
                'source': mblog.get('source', ''),
                'is_long_text': mblog.get('isLongText', False),
            }
            
            # 计算情感分数
            post['sentiment'] = self._analyze_sentiment(text)
            
            return post if text else None
            
        except Exception as e:
            logger.debug(f"解析微博失败: {e}")
            return None

    def _clean_text(self, text: str) -> str:
        """清理HTML标签和特殊字符"""
        if not text:
            return ''
            
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        # 移除@用户
        text = re.sub(r'@[\w\u4e00-\u9fff]+', '', text)
        # 移除话题标签中的#
        text = re.sub(r'#([^#]+)#', r'\1', text)
        # 移除链接
        text = re.sub(r'https?://\S+', '', text)
        # 移除表情代码
        text = re.sub(r'\[[\w\u4e00-\u9fff]+\]', '', text)
        # 移除多余空白
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _analyze_sentiment(self, text: str) -> float:
        """
        分析文本情感
        
        Args:
            text: 要分析的文本
            
        Returns:
            情感分数，范围 [-1, 1]
        """
        if not text:
            return 0.0
            
        text = text.lower()
        
        bullish_count = 0
        bearish_count = 0
        
        for keyword in self.BULLISH_KEYWORDS:
            if keyword in text:
                bullish_count += 1
                
        for keyword in self.BEARISH_KEYWORDS:
            if keyword in text:
                bearish_count += 1
                
        total = bullish_count + bearish_count
        if total == 0:
            return 0.0
            
        sentiment = (bullish_count - bearish_count) / total
        return max(-1.0, min(1.0, sentiment))

    def get_hot_search(self) -> List[Dict[str, Any]]:
        """
        获取微博热搜榜
        
        Returns:
            热搜列表，包含:
            - rank: 排名
            - keyword: 热搜关键词
            - hot: 热度值
            - is_finance: 是否财经相关
        """
        if requests is None:
            return []
            
        try:
            self._random_delay()
            
            session = self._get_session()
            
            # 热搜API
            url = f"{self.base_url}/api/container/getIndex"
            params = {
                "containerid": "106003type=25&t=3&disable_hot=1&filter_type=realtimehot",
            }
            
            response = session.get(
                url,
                params=params,
                headers=self._get_random_headers(),
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                return []
                
            data = response.json()
            cards = data.get('data', {}).get('cards', [])
            
            hot_list = []
            
            for card in cards:
                card_group = card.get('card_group', [])
                for idx, item in enumerate(card_group):
                    keyword = item.get('desc', '')
                    if keyword:
                        # 检查是否财经相关
                        is_finance = any(
                            topic in keyword 
                            for topic in self.FINANCE_TOPICS
                        )
                        
                        hot_list.append({
                            'rank': idx + 1,
                            'keyword': keyword,
                            'hot': item.get('desc_extr', 0),
                            'scheme': item.get('scheme', ''),
                            'is_finance': is_finance,
                        })
                        
            return hot_list
            
        except Exception as e:
            logger.error(f"获取热搜失败: {e}")
            return []

    def get_finance_hot_search(self) -> List[Dict[str, Any]]:
        """
        获取财经相关热搜
        
        Returns:
            财经热搜列表
        """
        hot_list = self.get_hot_search()
        return [item for item in hot_list if item.get('is_finance')]

    def get_topic_posts(
        self,
        topic: str,
        count: int = 20
    ) -> List[Dict[str, Any]]:
        """
        获取话题下的帖子
        
        Args:
            topic: 话题名称（不含#）
            count: 数量
            
        Returns:
            帖子列表
        """
        # 话题搜索使用特殊格式
        return self.search_stock_posts(f"#{topic}#", count=count)

    def get_user_posts(
        self,
        user_id: str,
        page: int = 1
    ) -> List[Dict[str, Any]]:
        """
        获取用户发布的帖子
        
        Args:
            user_id: 用户ID
            page: 页码
            
        Returns:
            帖子列表
        """
        if requests is None:
            return []
            
        try:
            self._random_delay()
            
            session = self._get_session()
            
            params = {
                "containerid": f"107603{user_id}",
                "page": page,
            }
            
            response = session.get(
                self.search_url,
                params=params,
                headers=self._get_random_headers(),
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                return []
                
            data = response.json()
            cards = data.get('data', {}).get('cards', [])
            
            posts = []
            for card in cards:
                if card.get('card_type') == 9:
                    mblog = card.get('mblog', {})
                    if mblog:
                        post = self._parse_mblog(mblog)
                        if post:
                            posts.append(post)
                            return posts
            
        except Exception as e:
            logger.error(f"获取用户帖子失败: {e}")
            return []

    def analyze_posts_sentiment(
        self,
        posts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        分析帖子列表的整体情绪
        
        Args:
            posts: 帖子列表
            
        Returns:
            情绪统计
        """
        if not posts:
            return {
                "bullish_count": 0,
                "bearish_count": 0,
                "neutral_count": 0,
                "sentiment_score": 0.0,
                "total_posts": 0,"avg_reposts": 0,
                "avg_comments": 0,
                "avg_attitudes": 0,"engagement_score": 0.0
            }

        bullish = 0
        bearish = 0
        neutral = 0
        total_reposts = 0
        total_comments = 0
        total_attitudes = 0
        weighted_sentiment = 0.0
        total_weight = 0
        
        for post in posts:
            sentiment = post.get('sentiment', 0)
            reposts = post.get('reposts_count', 0)
            comments = post.get('comments_count', 0)
            attitudes = post.get('attitudes_count', 0)
            
            # 根据互动量加权
            weight = max(1, reposts + comments * 2 + attitudes)
            weighted_sentiment += sentiment * weight
            total_weight += weight
            
            if sentiment > 0.2:
                bullish += 1
            elif sentiment < -0.2:
                bearish += 1
            else:
                neutral += 1
                
            total_reposts += reposts
            total_comments += comments
            total_attitudes += attitudes

        sentiment_score = weighted_sentiment / total_weight if total_weight > 0 else 0.0
        
        # 计算参与度分数
        engagement = (total_reposts + total_comments * 2 + total_attitudes) / len(posts) if posts else 0
        
        return {
            "bullish_count": bullish,
            "bearish_count": bearish,
            "neutral_count": neutral,
            "sentiment_score": round(sentiment_score, 4),
            "total_posts": len(posts),
            "avg_reposts": round(total_reposts / len(posts), 2),
            "avg_comments": round(total_comments / len(posts), 2),
            "avg_attitudes": round(total_attitudes / len(posts), 2),
            "engagement_score": round(engagement, 2)
        }

    def get_stock_sentiment(
        self,
        stock_name: str,
        pages: int = 2
    ) -> Dict[str, Any]:
        """
        获取股票情绪分析
        
        Args:
            stock_name: 股票名称
            pages: 爬取页数
            
        Returns:
            情绪分析结果
        """
        all_posts = []
        
        for page in range(1, pages + 1):
            posts = self.search_stock_posts(stock_name, page=page)
            all_posts.extend(posts)
            
        sentiment = self.analyze_posts_sentiment(all_posts)
        
        return {
            "stock_name": stock_name,
            "total_posts_analyzed": len(all_posts),
            "sentiment_summary": sentiment,
            "sample_posts": all_posts[:5] if all_posts else []
        }

    def search_finance_bloggers(
        self,
        keyword: str = "股票"
    ) -> List[Dict[str, Any]]:
        """
        搜索财经博主
        
        Args:
            keyword:搜索关键词
            
        Returns:
            博主列表
        """
        if requests is None:
            return []
            
        try:
            self._random_delay()
            
            session = self._get_session()
            
            # 用户搜索API
            params = {
                "containerid": f"100103type=3&q={quote(keyword)}",
                "page_type": "searchall",}
            
            response = session.get(
                self.search_url,
                params=params,
                headers=self._get_random_headers(),
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                return []
                
            data = response.json()
            cards = data.get('data', {}).get('cards', [])
            
            bloggers = []
            
            for card in cards:
                card_group = card.get('card_group', [])
                for item in card_group:
                    user = item.get('user', {})
                    if user:
                        bloggers.append({
                            'user_id': str(user.get('id', '')),
                            'screen_name': user.get('screen_name', ''),
                            'description': user.get('description', ''),
                            'followers_count': int(user.get('followers_count', 0) or 0),
                            'statuses_count': int(user.get('statuses_count', 0) or 0),
                            'verified': user.get('verified', False),
                            'verified_reason': user.get('verified_reason', ''),
                        })
                        
            return bloggers
            
        except Exception as e:
            logger.error(f"搜索博主失败: {e}")
            return []

    def get_trending_stocks(self) -> List[Dict[str, Any]]:
        """
        从热搜中提取股票相关话题
        
        Returns:
            股票相关热搜列表
        """
        hot_list = self.get_hot_search()
        
        # 股票相关关键词
        stock_keywords = [
            "股", "A股", "涨停", "跌停", "大盘", "牛市", "熊市",
            "基金", "证券", "概念", "板块", "龙头"
        ]
        
        trending = []
        for item in hot_list:
            keyword = item.get('keyword', '')
            if any(k in keyword for k in stock_keywords):
                trending.append(item)
                
        return trending

    def get_sentiment_trend(
        self,
        keyword: str,
        pages: int = 3
    ) -> Dict[str, Any]:
        """
        获取情绪趋势
        
        Args:
            keyword: 搜索关键词
            pages: 爬取页数
            
        Returns:
            情绪趋势数据
        """
        all_posts = []
        
        for page in range(1, pages + 1):
            posts = self.search_stock_posts(keyword, page=page)
            all_posts.extend(posts)
            
        sentiment = self.analyze_posts_sentiment(all_posts)
        sentiments = [p.get('sentiment', 0) for p in all_posts]
        
        return {
            "keyword": keyword,
            "total_posts_analyzed": len(all_posts),
            "sentiment_summary": sentiment,
            "sentiment_distribution": {
                "max": max(sentiments) if sentiments else 0,
                "min": min(sentiments) if sentiments else 0,
                "avg": sum(sentiments) / len(sentiments) if sentiments else 0
            }
        }