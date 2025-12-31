"""
雪球数据采集器

实现功能：
1. 无需登录的公开数据获取
2. 帖子内容、点赞数、评论数、转发数解析
3. 情感分析功能
4. 反爬虫处理
"""
import re
import random
import time
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass

try:
    import requests
except ImportError:
    requests = None

# 配置日志
logger = logging.getLogger(__name__)


@dataclass
class XueqiuPost:
    """雪球帖子数据类"""
    post_id: str
    title: str
    text: str
    user_name: str
    user_id: str
    created_at: str
    like_count: int
    reply_count: int
    retweet_count: int
    sentiment: float = 0.0


class XueqiuCrawler:
    """雪球数据爬虫
    
    实现对雪球公开API的数据获取和情感分析功能。雪球提供了多个公开API接口，无需登录即可获取部分数据。Attributes:
        base_url: 雪球基础URL
        api_base: API基础地址
        headers: 请求头
    Example:
        >>> crawler = XueqiuCrawler()
        >>> posts = crawler.get_stock_discussions("SH600519")>>> sentiment = crawler.analyze_posts_sentiment(posts)>>> print(sentiment)
    """

    # User-Agent列表
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    ]

    # 看多关键词
    BULLISH_KEYWORDS = [
        "涨", "牛", "买入", "加仓", "看好", "利好", "突破", "新高", "放量", "底部",
        "起飞", "腾飞", "翻倍", "龙头", "黑马", "强势", "上攻", "爆发", "启动", "反弹",
        "大涨", "暴涨", "涨停", "金股", "牛股", "潜力", "价值", "低估", "布局", "机会",
        "进场", "抄底", "拉升", "突破", "站稳", "企稳", "回升", "向上", "走强", "看涨",
        "赚钱", "发财", "收获", "盈利", "分红", "持有", "坚定", "长线"
    ]

    # 看空关键词
    BEARISH_KEYWORDS = [
        "跌", "熊", "卖出", "减仓", "看空", "利空", "破位", "新低", "缩量", "顶部",
        "下跌", "暴跌", "跌停", "割肉", "清仓", "逃跑", "出逃", "套牢", "亏损", "危险",
        "风险", "崩盘", "跳水", "大跌", "腰斩", "血亏", "绿了", "完蛋", "垃圾", "骗子",
        "跑路", "注意", "小心", "警惕", "回调", "下行", "走弱", "看跌", "做空", "空头"
    ]

    def __init__(
        self,
        min_delay: float = 1.0,
        max_delay: float = 3.0,
        timeout: int = 10
    ):
        """
        初始化雪球爬虫
        
        Args:
            min_delay: 最小请求延迟（秒）
            max_delay: 最大请求延迟（秒）
            timeout: 请求超时时间（秒）
        """
        self.base_url = "https://xueqiu.com"
        self.api_base = "https://xueqiu.com"
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.timeout = timeout
        self._last_request_time =0
        self._session = None
        self._cookies = {}if requests is None:
            logger.warning("requests库未安装，请使用 pip install requests")

    def _get_session(self) -> requests.Session:
        """获取或创建会话"""
        if self._session is None:
            self._session = requests.Session()
            # 先访问首页获取cookie
            try:
                self._session.get(
                    self.base_url,
                    headers=self._get_random_headers(),
                    timeout=self.timeout
                )except Exception as e:
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
            "Origin": "https://xueqiu.com",
            "Referer": "https://xueqiu.com/",
        }

    def _random_delay(self) -> None:
        """随机延迟，避免被反爬"""
        elapsed = time.time() - self._last_request_time
        delay = random.uniform(self.min_delay, self.max_delay)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_time = time.time()

    def _convert_stock_code(self, stock_code: str) -> str:
        """
        转换股票代码为雪球格式
        
        Args:
            stock_code: 股票代码（如600519, SH600519）
            
        Returns:
            雪球格式股票代码（如SH600519）
        """
        code = stock_code.strip().upper()
        
        # 如果已经有前缀，直接返回
        if code.startswith(('SH', 'SZ', 'BJ')):
            return code
            
        # 根据代码判断市场
        if code.startswith('6'):
            return f"SH{code}"
        elif code.startswith('0') or code.startswith('3'):
            return f"SZ{code}"
        elif code.startswith('8') or code.startswith('4'):
            return f"BJ{code}"
        else:
            return f"SH{code}"

    def get_stock_discussions(
        self,
        stock_code: str,
        count: int = 20,
        source: str = "all"
    ) -> List[Dict[str, Any]]:
        """
        获取股票讨论帖子
        
        Args:
            stock_code: 股票代码
            count: 获取数量
            source: 来源筛选（all/user/news）
            
        Returns:
            讨论帖子列表
        """
        if requests is None:
            logger.error("requests库未安装")
            return []
            
        symbol = self._convert_stock_code(stock_code)
        
        # 尝试使用公开的时间线API
        posts = self._get_timeline_posts(symbol, count)
        
        # 如果失败，尝试其他接口
        if not posts:
            posts = self._get_statuses_by_symbol(symbol, count)
            
        # 分析每个帖子的情感
        for post in posts:
            text = post.get('title', '') + ' ' + post.get('text', '')
            post['sentiment'] = self._analyze_sentiment(text)
            
        return posts

    def _get_timeline_posts(
        self,
        symbol: str,
        count: int
    ) -> List[Dict[str, Any]]:
        """从时间线API获取帖子"""
        try:
            self._random_delay()
            
            session = self._get_session()
            
            #雪球公开时间线API
            url = f"{self.api_base}/v4/statuses/public_timeline_by_symbol.json"
            params = {
                "symbol": symbol,
                "count": count,
                "comment":0,
                "hl": 0,
            }
            
            response = session.get(
                url,
                params=params,
                headers=self._get_random_headers(),
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.warning(f"API请求失败，状态码: {response.status_code}")
                return []
                
            data = response.json()
            return self._parse_timeline_response(data)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"请求异常: {e}")
            return []except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return []

    def _get_statuses_by_symbol(
        self,
        symbol: str,
        count: int
    ) -> List[Dict[str, Any]]:
        """从股票状态API获取帖子"""
        try:
            self._random_delay()
            
            session = self._get_session()
            
            # 另一个可用的API接口
            url = f"{self.api_base}/statuses/stock_timeline.json"
            params = {
                "symbol_id": symbol,
                "count": count,
                "source": "all",
                "sort": "time",}
            
            response = session.get(
                url,
                params=params,
                headers=self._get_random_headers(),
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.warning(f"备用API请求失败，状态码: {response.status_code}")
                return []
                
            data = response.json()
            return self._parse_statuses_response(data)
            
        except Exception as e:
            logger.error(f"备用API请求异常: {e}")
            return []

    def _parse_timeline_response(self, data: Dict) -> List[Dict[str, Any]]:
        """解析时间线API响应"""
        posts = []
        
        statuses = data.get('list', []) or data.get('statuses', [])
        
        for item in statuses:
            try:
                user = item.get('user', {}) or {}
                post = {
                    'post_id': str(item.get('id', '')),
                    'title': item.get('title', '') or '',
                    'text': self._clean_text(item.get('text', '') or item.get('description', '')),
                    'user_name': user.get('screen_name', ''),
                    'user_id': str(user.get('id', '')),
                    'created_at': self._format_timestamp(item.get('created_at', 0)),
                    'like_count': int(item.get('like_count', 0) or 0),
                    'reply_count': int(item.get('reply_count', 0) or 0),
                    'retweet_count': int(item.get('retweet_count', 0) or 0),
                    'view_count': int(item.get('view_count', 0) or 0),
                    'source': item.get('source', ''),
                }
                
                if post['text'] or post['title']:
                    posts.append(post)except Exception as e:
                logger.debug(f"解析帖子失败: {e}")
                continue
                
        return posts

    def _parse_statuses_response(self, data: Dict) -> List[Dict[str, Any]]:
        """解析状态API响应"""
        posts = []
        
        statuses = data.get('list', []) or data.get('statuses', []) or []
        
        for item in statuses:
            try:
                user = item.get('user', {}) or {}
                
                post = {
                    'post_id': str(item.get('id', '')),
                    'title': item.get('title', '') or '',
                    'text': self._clean_text(item.get('text', '') or ''),
                    'user_name': user.get('screen_name', ''),
                    'user_id': str(user.get('id', '')),
                    'created_at': self._format_timestamp(item.get('created_at', 0)),
                    'like_count': int(item.get('like_count', 0) or 0),
                    'reply_count': int(item.get('reply_count', 0) or 0),
                    'retweet_count': int(item.get('retweet_count', 0) or 0),
                    'view_count': int(item.get('view_count', 0) or 0),
                }
                
                if post['text'] or post['title']:
                    posts.append(post)
                    
            except Exception as e:
                logger.debug(f"解析帖子失败: {e}")
                continue
                
        return posts

    def _clean_text(self, text: str) -> str:
        """清理HTML标签和特殊字符"""
        if not text:
            return ''
            
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        # 移除多余空白
        text = re.sub(r'\s+', ' ', text)
        # 移除特殊Unicode字符
        text = re.sub(r'[\u200b-\u200f\u2028-\u202f]', '', text)
        return text.strip()

    def _format_timestamp(self, timestamp: Any) -> str:
        """格式化时间戳"""
        if not timestamp:
            return ''
            
        try:
            if isinstance(timestamp, (int, float)):
                #雪球使用毫秒时间戳
                if timestamp > 1e12:
                    timestamp = timestamp / 1000
                dt = datetime.fromtimestamp(timestamp)
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(timestamp, str):
                return timestamp
        except Exception:
            pass
            
        return str(timestamp)

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

    def get_hot_stocks(self, count: int = 50) -> List[Dict[str, Any]]:
        """
        获取热门股票
        
        Args:
            count: 数量
            
        Returns:
            热门股票列表，包含:
            - symbol: 股票代码
            - name: 股票名称
            - current: 当前价格
            - percent:涨跌幅
            - tweet: 讨论热度
        """
        if requests is None:
            return []
            
        try:
            self._random_delay()
            
            session = self._get_session()
            
            # 热门股票API
            url = f"{self.api_base}/stock/hot_stock/list.json"
            params = {
                "size": count,
                "type": "10",  # 10=最热门
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
            items = data.get('data', {}).get('items', [])
            
            hot_stocks = []
            for item in items:
                stock = {
                    'symbol': item.get('code', ''),
                    'name': item.get('name', ''),
                    'current': float(item.get('current', 0) or 0),
                    'percent': float(item.get('percent', 0) or 0),
                    'tweet': int(item.get('tweet', 0) or 0),'followers': int(item.get('followers', 0) or 0),
                }
                hot_stocks.append(stock)
                
            return hot_stocks
            
        except Exception as e:
            logger.error(f"获取热门股票失败: {e}")
            return []

    def get_stock_mentions(self, stock_code: str) -> int:
        """
        获取股票提及次数（24小时内）
        
        Args:
            stock_code: 股票代码
            
        Returns:
            提及次数
        """
        posts = self.get_stock_discussions(stock_code, count=50)
        return len(posts)

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
                "sentiment_score": 0.0,"total_posts": 0,"avg_like_count": 0,
                "avg_reply_count": 0,
                "engagement_score": 0.0
            }

        bullish = 0
        bearish = 0
        neutral = 0
        total_likes = 0
        total_replies = 0
        weighted_sentiment = 0.0
        total_weight = 0
        
        for post in posts:
            sentiment = post.get('sentiment', 0)
            like_count = post.get('like_count', 0)
            reply_count = post.get('reply_count', 0)
            
            # 根据互动量加权
            weight = max(1, like_count + reply_count * 2)
            weighted_sentiment += sentiment * weight
            total_weight += weight
            
            if sentiment > 0.2:
                bullish += 1
            elif sentiment < -0.2:
                bearish += 1
            else:
                neutral += 1
                
            total_likes += like_count
            total_replies += reply_count

        sentiment_score = weighted_sentiment / total_weight if total_weight > 0 else 0.0
        
        # 计算参与度分数
        engagement = (total_likes + total_replies * 2) / len(posts) if posts else 0
        
        return {
            "bullish_count": bullish,
            "bearish_count": bearish,
            "neutral_count": neutral,
            "sentiment_score": round(sentiment_score, 4),
            "total_posts": len(posts),
            "avg_like_count": round(total_likes / len(posts), 2),
            "avg_reply_count": round(total_replies / len(posts), 2),
            "engagement_score": round(engagement, 2)
        }

    def get_stock_info(self, stock_code: str) -> Dict[str, Any]:
        """
        获取股票基本信息
        
        Args:
            stock_code: 股票代码
            
        Returns:
            股票信息
        """
        if requests is None:
            return {}
            
        symbol = self._convert_stock_code(stock_code)
        
        try:
            self._random_delay()
            
            session = self._get_session()
            
            url = f"{self.api_base}/v4/stock/quote.json"
            params = {
                "symbol": symbol,
                "extend": "detail",
            }
            
            response = session.get(
                url,
                params=params,
                headers=self._get_random_headers(),
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                return {}
                
            data = response.json()
            quote = data.get('data', {}).get('quote', {})
            
            return {
                'symbol': quote.get('symbol', ''),
                'name': quote.get('name', ''),
                'current': quote.get('current', 0),
                'percent': quote.get('percent', 0),
                'chg': quote.get('chg', 0),
                'high': quote.get('high', 0),
                'low': quote.get('low', 0),
                'open': quote.get('open', 0),
                'volume': quote.get('volume', 0),
                'amount': quote.get('amount', 0),
                'market_capital': quote.get('market_capital', 0),
                'followers': quote.get('followers', 0),}
            
        except Exception as e:
            logger.error(f"获取股票信息失败: {e}")
            return {}

    def get_user_posts(
        self,
        user_id: str,
        count: int = 20
    ) -> List[Dict[str, Any]]:
        """
        获取用户发布的帖子
        
        Args:
            user_id: 用户ID
            count: 数量
            
        Returns:
            帖子列表
        """
        if requests is None:
            return []
            
        try:
            self._random_delay()
            
            session = self._get_session()
            
            url = f"{self.api_base}/v4/statuses/user_timeline.json"
            params = {
                "user_id": user_id,
                "count": count,
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
            return self._parse_timeline_response(data)
            
        except Exception as e:
            logger.error(f"获取用户帖子失败: {e}")
            return []

    def get_sentiment_trend(
        self,
        stock_code: str,
        count: int = 100
    ) -> Dict[str, Any]:
        """
        获取情绪趋势
        
        Args:
            stock_code: 股票代码
            count: 分析帖子数量
            
        Returns:
            情绪趋势数据
        """
        posts = self.get_stock_discussions(stock_code, count=count)
        sentiment = self.analyze_posts_sentiment(posts)
        
        sentiments = [p.get('sentiment', 0) for p in posts]
        
        return {
            "stock_code": stock_code,
            "total_posts_analyzed": len(posts),
            "sentiment_summary": sentiment,
            "sentiment_distribution": {
                "max": max(sentiments) if sentiments else 0,
                "min": min(sentiments) if sentiments else 0,
                "avg": sum(sentiments) / len(sentiments) if sentiments else 0
            }
        }

    def search_posts(
        self,
        keyword: str,
        count: int = 20
    ) -> List[Dict[str, Any]]:
        """
        搜索帖子
        
        Args:
            keyword: 搜索关键词
            count: 数量
            
        Returns:
            帖子列表
        """
        if requests is None:
            return []
            
        try:
            self._random_delay()
            
            session = self._get_session()
            
            url = f"{self.api_base}/statuses/search.json"
            params = {
                "q": keyword,
                "count": count,"sort": "time",
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
            return self._parse_timeline_response(data)
            
        except Exception as e:
            logger.error(f"搜索帖子失败: {e}")
            return []