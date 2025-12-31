"""
东方财富股吧数据采集器

实现功能：
1. 帖子标题、内容、时间、阅读数、评论数解析
2. 情感分析（基于关键词匹配）
3. 反爬虫处理（随机延迟、User-Agent轮换）
"""
import re
import random
import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None

# 配置日志
logger = logging.getLogger(__name__)


@dataclass
class GubaPost:
    """股吧帖子数据类"""
    post_id: str
    title: str
    content: str
    author: str
    publish_time: str
    read_count: int
    comment_count: int
    sentiment: float = 0.0


class GubaCrawler:
    """东方财富股吧爬虫
    
    实现对东方财富股吧的帖子爬取和情感分析功能。Attributes:
        base_url: 股吧基础URL
        api_url: 股吧API接口URL
        headers: 请求头
        min_delay: 最小请求延迟（秒）
        max_delay: 最大请求延迟（秒）
    
    Example:
        >>> crawler = GubaCrawler()
        >>> posts = crawler.get_stock_posts("600519", page=1)
        >>> sentiment = crawler.get_post_sentiment(posts)
        >>> print(sentiment)
    """

    # User-Agent列表，用于轮换
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0",]

    # 看多关键词
    BULLISH_KEYWORDS = [
        "涨", "牛", "买入", "加仓", "看好", "利好", "突破", "新高", "放量", "底部",
        "起飞", "腾飞", "翻倍", "龙头", "黑马", "强势", "上攻", "爆发", "启动", "反弹",
        "大涨", "暴涨", "涨停", "金股", "牛股", "潜力", "价值", "低估", "布局", "机会",
        "进场", "抄底", "拉升", "突破", "站稳", "企稳", "回升", "向上", "走强", "看涨",
        "赚钱", "发财", "收获", "盈利", "红包", "福利", "收益", "分红"
    ]

    # 看空关键词
    BEARISH_KEYWORDS = [
        "跌", "熊", "卖出", "减仓", "看空", "利空", "破位", "新低", "缩量", "顶部",
        "下跌", "暴跌", "跌停", "割肉", "清仓", "逃跑", "出逃", "套牢", "亏损", "危险",
        "风险", "崩盘", "跳水", "大跌", "腰斩", "血亏", "绿了", "完蛋", "垃圾", "骗子",
        "跑路", "注意", "小心", "警惕", "回调", "下行", "走弱", "看跌", "做空", "空头",
        "赔钱", "亏了", "坑人", "别买", "远离"
    ]

    def __init__(
        self,
        min_delay: float = 1.0,
        max_delay: float = 3.0,
        timeout: int = 10
    ):
        """
        初始化股吧爬虫
        
        Args:
            min_delay: 最小请求延迟（秒）
            max_delay: 最大请求延迟（秒）
            timeout: 请求超时时间（秒）
        """
        self.base_url = "https://guba.eastmoney.com"
        self.api_url = "https://gbapi.eastmoney.com/guba/api"
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.timeout = timeout
        self._last_request_time =0
        
        if requests is None:
            logger.warning("requests库未安装，请使用 pip install requests")if BeautifulSoup is None:
            logger.warning("beautifulsoup4库未安装，请使用 pip install beautifulsoup4")

    def _get_random_headers(self) -> Dict[str, str]:
        """获取随机请求头"""
        return {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
            "Referer": "https://guba.eastmoney.com/",
        }

    def _random_delay(self) -> None:
        """随机延迟，避免被反爬"""
        # 计算距离上次请求的时间
        elapsed = time.time() - self._last_request_time
        delay = random.uniform(self.min_delay, self.max_delay)
        if elapsed < delay:
            sleep_time = delay - elapsed
            time.sleep(sleep_time)
            
        self._last_request_time = time.time()

    def _convert_stock_code(self, stock_code: str) -> tuple:
        """
        转换股票代码格式
        
        Args:
            stock_code: 股票代码（如600519）
            
        Returns:
            元组 (市场前缀, 纯代码)，如 ('sh', '600519')
        """
        code = stock_code.strip()
        
        # 移除可能存在的前缀
        if code.upper().startswith(('SH', 'SZ', 'BJ')):
            prefix = code[:2].lower()
            code = code[2:]
        else:
            # 根据代码判断市场
            if code.startswith('6'):
                prefix ='sh'  # 上证
            elif code.startswith('0') or code.startswith('3'):
                prefix = 'sz'  # 深证
            elif code.startswith('8') or code.startswith('4'):
                prefix = 'bj'  # 北交所
            else:
                prefix = 'sh'  # 默认上证
                
        return prefix, code

    def get_stock_posts(
        self,
        stock_code: str,
        page: int = 1,
        page_size: int = 30
    ) -> List[Dict[str, Any]]:
        """
        获取股票相关帖子
        
        Args:
            stock_code: 股票代码
            page: 页码（从1开始）
            page_size: 每页数量
            
        Returns:
            帖子列表，每个帖子包含:
            - post_id: 帖子ID
            - title: 标题
            - content: 内容摘要
            - author: 作者
            - publish_time: 发布时间
            - read_count: 阅读数
            - comment_count: 评论数
            - sentiment: 情感分数(-1到1)
        """
        if requests is None:
            logger.error("requests库未安装")
            return []
            
        prefix, code = self._convert_stock_code(stock_code)
        
        #尝试使用API接口获取数据
        posts = self._get_posts_from_api(prefix, code, page, page_size)
        
        if not posts:
            # 如果API失败，尝试HTML解析
            posts = self._get_posts_from_html(prefix, code, page)
            
        # 为每个帖子计算情感分数
        for post in posts:
            post['sentiment'] = self._analyze_sentiment(
                post.get('title', '') + ' ' + post.get('content', '')
            )
            
        return posts

    def _get_posts_from_api(
        self,
        prefix: str,
        code: str,
        page: int,
        page_size: int
    ) -> List[Dict[str, Any]]:
        """从API接口获取帖子数据"""
        try:
            self._random_delay()
            
            # 东方财富股吧API接口
            api_url = f"https://guba.eastmoney.com/interface/GetData.aspx"
            params = {
                "path": "newtopic/api/getgubalist",
                "code": code,
                "ps": page_size,
                "p": page,
                "type": "1",}
            
            response = requests.get(
                api_url,
                params=params,
                headers=self._get_random_headers(),
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.warning(f"API请求失败，状态码: {response.status_code}")
                return []
            # 解析JSON响应
            try:
                data = response.json()
                if isinstance(data, dict) and 'result' in data:
                    return self._parse_api_response(data['result'])
            except Exception as e:
                logger.debug(f"JSON解析失败: {e}")
                return []
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API请求异常: {e}")
            return []

    def _parse_api_response(self, data: Any) -> List[Dict[str, Any]]:
        """解析API响应数据"""
        posts = []
        
        if not isinstance(data, dict):
            return posts
            
        topic_list = data.get('list', [])
        
        for item in topic_list:
            try:
                post = {
                    'post_id': str(item.get('post_id', '')),
                    'title': item.get('post_title', '').strip(),
                    'content': item.get('post_abstract', '').strip(),
                    'author': item.get('post_user', {}).get('user_nickname', ''),
                    'publish_time': item.get('post_publish_time', ''),
                    'read_count': int(item.get('post_click_count', 0)),
                    'comment_count': int(item.get('post_comment_count', 0)),
                }
                posts.append(post)except Exception as e:
                logger.debug(f"解析帖子失败: {e}")
                continue
                
        return posts

    def _get_posts_from_html(
        self,
        prefix: str,
        code: str,
        page: int
    ) -> List[Dict[str, Any]]:
        """从HTML页面解析帖子数据"""
        if BeautifulSoup is None:
            logger.error("beautifulsoup4库未安装")
            return []
            
        try:
            self._random_delay()
            
            # 构建URL，股吧使用纯数字代码
            url = f"{self.base_url}/list,{code}_{page}.html"
            
            response = requests.get(
                url,
                headers=self._get_random_headers(),
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.warning(f"HTML请求失败，状态码: {response.status_code}")
                return []
                
            response.encoding = 'utf-8'
            return self._parse_posts(response.text)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"HTML请求异常: {e}")
            return []

    def _parse_posts(self, html: str) -> List[Dict[str, Any]]:
        """
        解析帖子HTML
        
        Args:
            html: 页面HTML内容
            
        Returns:
            帖子列表
        """
        if BeautifulSoup is None:
            return []
            
        posts = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # 查找帖子列表容器
            # 股吧页面结构：每个帖子在articleh 或 listitem 类下
            post_elements = soup.select('.listitem, .articleh')
            
            # 如果找不到，尝试其他选择器
            if not post_elements:
                post_elements = soup.select('div[class*="list"] tr, div[class*="post"] tr')
                
            # 如果还是找不到，尝试解析表格结构
            if not post_elements:
                post_elements = soup.select('#articlelistnew li, .mainlist li')
                
            for element in post_elements:
                try:
                    post = self._parse_single_post(element)
                    if post and post.get('title'):
                        posts.append(post)
                except Exception as e:
                    logger.debug(f"解析单个帖子失败: {e}")
                    continue# 如果上述方法都失败，尝试更通用的解析
            if not posts:
                posts = self._parse_posts_fallback(soup)
                    
        except Exception as e:
            logger.error(f"HTML解析失败: {e}")
            
        return posts

    def _parse_single_post(self, element) -> Optional[Dict[str, Any]]:
        """解析单个帖子元素"""
        post = {
            'post_id': '',
            'title': '',
            'content': '',
            'author': '',
            'publish_time': '',
            'read_count': 0,
            'comment_count': 0,
        }
        
        # 尝试获取帖子ID和标题
        title_link = element.select_one('a[href*="/news,"]')
        if title_link:
            href = title_link.get('href', '')
            # 从链接中提取帖子ID
            match = re.search(r'/news,(\w+),(\d+)', href)
            if match:
                post['post_id'] = match.group(2)
            post['title'] = title_link.get_text(strip=True)
            
        # 如果没找到标题链接，尝试其他方式
        if not post['title']:
            title_elem = element.select_one('.title, .l3, .tit')
            if title_elem:
                post['title'] = title_elem.get_text(strip=True)
                
        # 获取作者
        author_elem = element.select_one('.author, .l4a, .user')
        if author_elem:
            post['author'] = author_elem.get_text(strip=True)
            
        # 获取阅读数
        read_elem = element.select_one('.l1, .read, .view')
        if read_elem:
            read_text = read_elem.get_text(strip=True)
            read_count = self._parse_count(read_text)
            if read_count > 0:
                post['read_count'] = read_count
                
        # 获取评论数
        comment_elem = element.select_one('.l2, .reply, .comment')
        if comment_elem:
            comment_text = comment_elem.get_text(strip=True)
            comment_count = self._parse_count(comment_text)
            if comment_count > 0:
                post['comment_count'] = comment_count
                
        # 获取发布时间
        time_elem = element.select_one('.l5, .time, .update')
        if time_elem:
            post['publish_time'] = time_elem.get_text(strip=True)
            
        return post if post['title'] else None

    def _parse_posts_fallback(self, soup) -> List[Dict[str, Any]]:
        """备用解析方法：从页面中提取所有可能的帖子"""
        posts = []
        
        # 查找所有包含帖子链接的元素
        links = soup.find_all('a', href=re.compile(r'/news,\w+,\d+'))
        
        for link in links:
            try:
                href = link.get('href', '')
                match = re.search(r'/news,(\w+),(\d+)', href)
                if match:
                    post = {
                        'post_id': match.group(2),
                        'title': link.get_text(strip=True),
                        'content': '',
                        'author': '',
                        'publish_time': '',
                        'read_count': 0,
                        'comment_count': 0,
                    }
                    if post['title'] and len(post['title']) > 2:
                        posts.append(post)except Exception:
                continue
                
        return posts

    def _parse_count(self, text: str) -> int:
        """解析数量文本（如 "1.2万" -> 12000）"""
        if not text:
            return 0
            
        text = text.strip()
        
        try:
            # 处理"万"单位
            if '万' in text:
                num = float(re.sub(r'[^\d.]', '', text))
                return int(num * 10000)
            else:
                return int(re.sub(r'[^\d]', '', text) or 0)
        except (ValueError, TypeError):
            return 0

    def _analyze_sentiment(self, text: str) -> float:
        """
        分析文本情感
        
        使用关键词匹配方法进行简单的情感分析。
        Args:
            text: 要分析的文本
            
        Returns:
            情感分数，范围 [-1, 1]
            - 正数表示看多/积极
            - 负数表示看空/消极
            - 0 表示中性
        """
        if not text:
            return 0.0
            
        text = text.lower()
        
        bullish_count = 0
        bearish_count = 0
        
        # 计算看多关键词匹配数
        for keyword in self.BULLISH_KEYWORDS:
            if keyword in text:
                bullish_count += 1
                
        # 计算看空关键词匹配数
        for keyword in self.BEARISH_KEYWORDS:
            if keyword in text:
                bearish_count += 1
                
        # 计算情感分数
        total = bullish_count + bearish_count
        if total == 0:
            return 0.0
            
        sentiment = (bullish_count - bearish_count) / total
        
        # 限制在[-1, 1] 范围内
        return max(-1.0, min(1.0, sentiment))

    def get_post_sentiment(self, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        分析帖子列表的整体情绪
        
        Args:
            posts: 帖子列表
            
        Returns:
            情绪统计，包含:
            - bullish_count: 看多帖子数
            - bearish_count: 看空帖子数
            - neutral_count: 中性帖子数
            - sentiment_score: 综合情绪分数
            - total_posts: 总帖子数
            - avg_read_count: 平均阅读数
            - avg_comment_count: 平均评论数
        """
        if not posts:
            return {
                "bullish_count": 0,
                "bearish_count": 0,
                "neutral_count": 0,
                "sentiment_score": 0.0,
                "total_posts": 0,
                "avg_read_count": 0,
                "avg_comment_count": 0
            }

        bullish = 0
        bearish = 0
        neutral = 0
        total_read = 0
        total_comment = 0
        weighted_sentiment = 0.0
        total_weight = 0
        
        for post in posts:
            sentiment = post.get('sentiment', 0)
            read_count = post.get('read_count', 1)
            comment_count = post.get('comment_count', 0)
            
            # 根据阅读量加权计算情绪
            weight = max(1, read_count)
            weighted_sentiment += sentiment * weight
            total_weight += weight
            
            # 统计分类
            if sentiment > 0.2:
                bullish += 1
            elif sentiment < -0.2:
                bearish += 1
            else:
                neutral += 1
                
            total_read += read_count
            total_comment += comment_count

        # 计算加权平均情绪分数
        sentiment_score = weighted_sentiment / total_weight if total_weight > 0 else 0.0
        
        return {
            "bullish_count": bullish,
            "bearish_count": bearish,
            "neutral_count": neutral,
            "sentiment_score": round(sentiment_score, 4),
            "total_posts": len(posts),
            "avg_read_count": round(total_read / len(posts), 2),
            "avg_comment_count": round(total_comment / len(posts), 2)
        }

    def get_hot_posts(
        self,
        stock_code: str,
        count: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取热门帖子（按阅读量排序）
        
        Args:
            stock_code: 股票代码
            count: 返回数量
            
        Returns:
            热门帖子列表
        """
        posts = self.get_stock_posts(stock_code, page=1, page_size=50)
        
        # 按阅读量排序
        posts.sort(key=lambda x: x.get('read_count', 0), reverse=True)
        
        return posts[:count]

    def get_latest_posts(
        self,
        stock_code: str,
        count: int = 20
    ) -> List[Dict[str, Any]]:
        """
        获取最新帖子
        
        Args:
            stock_code: 股票代码
            count: 返回数量
            
        Returns:
            最新帖子列表
        """
        posts = self.get_stock_posts(stock_code, page=1, page_size=count)
        return posts[:count]

    def get_sentiment_trend(
        self,
        stock_code: str,
        pages: int = 3
    ) -> Dict[str, Any]:
        """
        获取情绪趋势（多页数据）
        
        Args:
            stock_code: 股票代码
            pages: 爬取页数
            
        Returns:
            情绪趋势数据
        """
        all_posts = []
        
        for page in range(1, pages + 1):
            posts = self.get_stock_posts(stock_code, page=page)
            all_posts.extend(posts)
            
        sentiment = self.get_post_sentiment(all_posts)
        
        # 计算情绪分布
        sentiments = [p.get('sentiment', 0) for p in all_posts]
        
        return {
            "stock_code": stock_code,
            "total_posts_analyzed": len(all_posts),
            "sentiment_summary": sentiment,
            "sentiment_distribution": {
                "max": max(sentiments) if sentiments else 0,
                "min": min(sentiments) if sentiments else 0,
                "avg": sum(sentiments) / len(sentiments) if sentiments else 0
            }
        }