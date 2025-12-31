"""
百度指数数据采集器

实现功能：
1. 股票相关搜索热度获取
2. 趋势数据分析
3. 地域分布分析
4. 人群画像分析

注意：百度指数需要登录Cookie才能访问完整数据。
使用前请按照说明获取Cookie。
"""
import re
import json
import time
import random
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

try:
    import requests
except ImportError:
    requests = None

# 配置日志
logger = logging.getLogger(__name__)


@dataclass
class BaiduIndexData:
    """百度指数数据类"""
    keyword: str
    date: str
    index_value: int
    all_index: int  # 整体指数
    pc_index: int   # PC指数
    mobile_index: int  # 移动指数


class BaiduIndexCrawler:
    """百度指数数据爬虫
    
    用于获取股票相关关键词的百度搜索热度数据。
    百度指数需要登录Cookie才能获取完整数据。
    Attributes:
        base_url: 百度指数基础URL
        cookie: 登录Cookie
        headers: 请求头
    使用说明：
        1. 访问 https://index.baidu.com/ 并登录百度账号
        2. 打开浏览器开发者工具（F12），切换到Network标签
        3.刷新页面，找到任意请求，复制Cookie值
        4. 使用 set_cookie() 方法设置Cookie
        
    Example:
        >>> crawler = BaiduIndexCrawler()
        >>> crawler.set_cookie("your_cookie_here")
        >>> data = crawler.get_index("贵州茅台")
        >>> print(data)
    """

    # User-Agent列表
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    def __init__(
        self,
        cookie: str = "",
        timeout: int = 15
    ):
        """
        初始化百度指数爬虫
        
        Args:
            cookie: 百度登录Cookie（可后续通过set_cookie设置）
            timeout: 请求超时时间（秒）
        """
        self.base_url = "https://index.baidu.com"
        self.api_url = "https://index.baidu.com/api"
        self.cookie = cookie
        self.timeout = timeout
        self._session = None
        self._cipher_key = Noneif requests is None:
            logger.warning("requests库未安装，请使用 pip install requests")

    def set_cookie(self, cookie: str) -> None:
        """
        设置登录Cookie
        
        Args:
            cookie: 百度登录Cookie字符串
            
        使用方法：
            1. 登录百度指数网站: https://index.baidu.com
            2. 打开浏览器开发者工具 (F12)
            3. 在Network标签中找到任意请求
            4. 复制请求头中的Cookie值
            5. 调用此方法设置Cookie
        """
        self.cookie = cookie
        self._session = None# 重置session
        logger.info("Cookie已设置")

    def _get_session(self) -> requests.Session:
        """获取或创建会话"""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update(self._get_headers())
        return self._session

    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        headers = {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": "https://index.baidu.com/v2/main/index.html",
            "Origin": "https://index.baidu.com",}
        
        if self.cookie:
            headers["Cookie"] = self.cookie
            
        return headers

    def _check_cookie(self) -> bool:
        """检查Cookie是否有效"""
        if not self.cookie:
            logger.warning("未设置Cookie，部分功能将不可用")
            return False
        return True

    def get_index(
        self,
        keyword: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        area: int = 0
    ) -> Dict[str, Any]:
        """
        获取关键词的百度指数
        
        Args:
            keyword: 搜索关键词（如股票名称）
            start_date: 开始日期（格式：YYYY-MM-DD）
            end_date: 结束日期（格式：YYYY-MM-DD）
            area: 地区代码（0表示全国）
            
        Returns:
            指数数据，包含:
            - keyword: 关键词
            - start_date: 开始日期
            - end_date: 结束日期
            - all_index: 整体搜索指数
            - pc_index: PC端搜索指数
            - mobile_index: 移动端搜索指数
            - trend: 趋势数据列表
        """
        if requests is None:
            logger.error("requests库未安装")
            return self._empty_result(keyword)
            
        if not self._check_cookie():
            logger.error("未设置Cookie，无法获取百度指数数据")
            return self._empty_result(keyword)
            
        # 设置默认日期范围（最近30天）
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            
        try:
            # 1. 获取加密的密钥
            uniqid = self._get_uniqid(keyword, start_date, end_date)
            if not uniqid:
                logger.error("获取uniqid失败")
                return self._empty_result(keyword)
                
            # 2. 获取搜索指数数据
            index_data = self._get_search_index(
                keyword, start_date, end_date, uniqid, area
            )
            
            return index_data
            
        except Exception as e:
            logger.error(f"获取百度指数失败: {e}")
            return self._empty_result(keyword)

    def _get_uniqid(
        self,
        keyword: str,
        start_date: str,
        end_date: str
    ) -> Optional[str]:
        """获取请求的唯一ID"""
        try:
            session = self._get_session()
            
            url = f"{self.api_url}/SearchApi/index"
            params = {
                "word": f'[[{{"name":"{keyword}","wordType":1}}]]',
                "startDate": start_date,
                "endDate": end_date,
                "area": 0,}
            
            response = session.get(
                url,
                params=params,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.warning(f"获取uniqid失败，状态码: {response.status_code}")
                return None
            data = response.json()
            
            if data.get('status') != 0:
                logger.warning(f"API返回错误: {data.get('message')}")
                return None
                
            return data.get('data', {}).get('uniqid')
            
        except Exception as e:
            logger.error(f"获取uniqid异常: {e}")
            return None

    def _get_search_index(
        self,
        keyword: str,
        start_date: str,
        end_date: str,
        uniqid: str,
        area: int
    ) -> Dict[str, Any]:
        """获取搜索指数数据"""
        try:
            session = self._get_session()
            
            # 获取密钥
            key = self._get_ptbk(uniqid)
            if not key:
                logger.error("获取解密密钥失败")
                return self._empty_result(keyword)
                
            url = f"{self.api_url}/SearchApi/index"
            params = {
                "word": f'[[{{"name":"{keyword}","wordType":1}}]]',
                "startDate": start_date,
                "endDate": end_date,
                "area": area,}
            
            response = session.get(
                url,
                params=params,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.error(f"获取搜索指数失败，状态码: {response.status_code}")
                return self._empty_result(keyword)
                
            data = response.json()
            
            if data.get('status') != 0:
                logger.error(f"API返回错误: {data.get('message')}")
                return self._empty_result(keyword)
                
            # 解密并解析数据
            result = self._parse_index_data(data.get('data', {}), key, keyword, start_date, end_date)
            return result
            
        except Exception as e:
            logger.error(f"获取搜索指数异常: {e}")
            return self._empty_result(keyword)

    def _get_ptbk(self, uniqid: str) -> Optional[str]:
        """获取解密密钥"""
        try:
            session = self._get_session()
            
            url = f"{self.api_url}/ptbk"
            params = {"uniqid": uniqid}
            
            response = session.get(
                url,
                params=params,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                return None
                
            data = response.json()
            return data.get('data')
            
        except Exception as e:
            logger.error(f"获取密钥异常: {e}")
            return None

    def _decrypt_data(self, encrypted: str, key: str) -> List[int]:
        """
        解密百度指数数据
        
        百度指数使用一种简单的替换加密：
        加密字符串中的每个字符对应key中的索引位置
        """
        if not encrypted or not key:
            return []
            
        try:
            # 创建解密映射
            key_map = {}
            for i, char in enumerate(key):
                key_map[char] = str(i % 10)
                
            # 解密
            decrypted = ""
            for char in encrypted:
                if char in key_map:
                    decrypted += key_map[char]
                else:
                    decrypted += char
                    
            # 分割成数字列表
            values = [int(v) for v in decrypted.split(',') if v]
            return values
            
        except Exception as e:
            logger.error(f"解密数据失败: {e}")
            return []

    def _parse_index_data(
        self,
        data: Dict,
        key: str,
        keyword: str,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """解析指数数据"""
        result = {
            "keyword": keyword,
            "start_date": start_date,
            "end_date": end_date,
            "all_index": [],
            "pc_index": [],
            "mobile_index": [],
            "trend": [],"avg_index": 0,
            "max_index": 0,
            "min_index": 0,}
        
        try:
            user_indexes = data.get('userIndexes', [])
            if not user_indexes:
                return result
                
            index_data = user_indexes[0]
            
            # 解密各类指数数据
            all_encrypted = index_data.get('all', {}).get('data', '')
            pc_encrypted = index_data.get('pc', {}).get('data', '')
            mobile_encrypted = index_data.get('wise', {}).get('data', '')
            
            all_values = self._decrypt_data(all_encrypted, key)
            pc_values = self._decrypt_data(pc_encrypted, key)
            mobile_values = self._decrypt_data(mobile_encrypted, key)
            
            result["all_index"] = all_values
            result["pc_index"] = pc_values
            result["mobile_index"] = mobile_values
            
            if all_values:
                result["avg_index"] = sum(all_values) / len(all_values)
                result["max_index"] = max(all_values)
                result["min_index"] = min(all_values)
                
            # 生成趋势数据
            result["trend"] = self._generate_trend(
                start_date, all_values, pc_values, mobile_values
            )
            
        except Exception as e:
            logger.error(f"解析指数数据失败: {e}")
            
        return result

    def _generate_trend(
        self,
        start_date: str,
        all_values: List[int],
        pc_values: List[int],
        mobile_values: List[int]
    ) -> List[Dict[str, Any]]:
        """生成趋势数据"""
        trend = []
        
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            
            for i, all_val in enumerate(all_values):
                date = start + timedelta(days=i)
                trend.append({
                    "date": date.strftime('%Y-%m-%d'),
                    "all": all_val,
                    "pc": pc_values[i] if i < len(pc_values) else 0,
                    "mobile": mobile_values[i] if i < len(mobile_values) else 0,
                })
                
        except Exception as e:
            logger.error(f"生成趋势数据失败: {e}")
            
        return trend

    def _empty_result(self, keyword: str) -> Dict[str, Any]:
        """返回空结果"""
        return {
            "keyword": keyword,
            "start_date": "",
            "end_date": "",
            "all_index": [],
            "pc_index": [],
            "mobile_index": [],
            "trend": [],
            "avg_index": 0,
            "max_index": 0,
            "min_index": 0,"error": "无法获取数据"
        }

    def get_related_words(self, keyword: str) -> List[Dict[str, Any]]:
        """
        获取相关搜索词
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            相关词列表
        """
        if requests is None:
            logger.error("requests库未安装")
            return []
        
        if not self._check_cookie():
            logger.error("未设置Cookie，无法获取相关词数据")
            return []
            
        try:
            session = self._get_session()
            
            url = f"{self.api_url}/RelatedWord/getRelatedWord"
            params = {
                "word": keyword,
            }
            
            response = session.get(
                url,
                params=params,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.error(f"获取相关词失败，状态码: {response.status_code}")
                return []
                
            data = response.json()
            
            if data.get('status') != 0:
                logger.error(f"API返回错误: {data.get('message')}")
                return []
                
            # 解析相关词
            result = data.get('data', {}).get('result', [])
            related = []
            
            for item in result:
                words = item.get('wordInfo', [])
                for word in words:
                    related.append({
                        "word": word.get('word', ''),
                        "searchIndex": word.get('searchIndex', 0),
                    })
                    
            return related
            
        except Exception as e:
            logger.error(f"获取相关词失败: {e}")
            return []

    def get_crowd_profile(self, keyword: str) -> Dict[str, Any]:
        """
        获取搜索人群画像
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            人群画像数据
        """
        if requests is None:
            logger.error("requests库未安装")
            return {}
        
        if not self._check_cookie():
            logger.error("未设置Cookie，无法获取人群画像数据")
            return {}
            
        try:
            session = self._get_session()
            
            url = f"{self.api_url}/SocialApi/baseAttributes"
            params = {
                "wordlist[]": keyword,
            }
            
            response = session.get(
                url,
                params=params,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.error(f"获取人群画像失败，状态码: {response.status_code}")
                return {}
                
            data = response.json()
            
            if data.get('status') != 0:
                logger.error(f"API返回错误: {data.get('message')}")
                return {}
                
            return self._parse_crowd_profile(data.get('data', {}))
            
        except Exception as e:
            logger.error(f"获取人群画像失败: {e}")
            return {}

    def _parse_crowd_profile(self, data: Dict) -> Dict[str, Any]:
        """解析人群画像数据"""
        result = {
            "age_distribution": {},
            "gender_distribution": {},
            "interests": [],
        }
        
        try:
            # 年龄分布
            age_data = data.get('age', {})
            for item in age_data.get('list', []):
                result["age_distribution"][item.get('name', '')] = item.get('pct', 0)
                
            # 性别分布
            gender_data = data.get('gender', {})
            for item in gender_data.get('list', []):
                result["gender_distribution"][item.get('name', '')] = item.get('pct', 0)
                
            # 兴趣爱好
            interest_data = data.get('interest', {})
            result["interests"] = [
                {"name": item.get('name', ''), "pct": item.get('pct', 0)}
                for item in interest_data.get('list', [])
            ]
            
        except Exception as e:
            logger.error(f"解析人群画像失败: {e}")
            
        return result

    def get_region_distribution(self, keyword: str) -> Dict[str, Any]:
        """
        获取地域分布
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            地域分布数据
        """
        if requests is None:
            logger.error("requests库未安装")
            return {}
        
        if not self._check_cookie():
            logger.error("未设置Cookie，无法获取地域分布数据")
            return {}
            
        try:
            session = self._get_session()
            
            url = f"{self.api_url}/SocialApi/region"
            params = {
                "wordlist[]": keyword,
            }
            
            response = session.get(
                url,
                params=params,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.error(f"获取地域分布失败，状态码: {response.status_code}")
                return {}
                
            data = response.json()
            
            if data.get('status') != 0:
                logger.error(f"API返回错误: {data.get('message')}")
                return {}
                
            # 解析地域数据
            region_data = data.get('data', {}).get('region', [])
            provinces = []
            cities = []
            
            for item in region_data:
                if item.get('type') == 'province':
                    provinces.append({
                        "name": item.get('name', ''),
                        "pct": item.get('pct', 0),})
                elif item.get('type') == 'city':
                    cities.append({
                        "name": item.get('name', ''),
                        "pct": item.get('pct', 0),
                    })
                    
            return {
                "keyword": keyword,
                "provinces": provinces[:10],  # Top 10
                "cities": cities[:10],  # Top 10
            }
            
        except Exception as e:
            logger.error(f"获取地域分布失败: {e}")
            return {}

    def compare_keywords(
        self,
        keywords: List[str],
        days: int = 30
    ) -> Dict[str, Any]:
        """
        比较多个关键词的搜索热度
        
        Args:
            keywords: 关键词列表
            days: 比较天数
            
        Returns:
            比较结果
        """
        result = {
            "keywords": keywords,
            "comparison": [],
            "trend_comparison": [],
        }
        
        for keyword in keywords[:5]:  # 最多比较5个
            index_data = self.get_index(keyword)
            result["comparison"].append({
                "keyword": keyword,
                "avg_index": index_data.get("avg_index", 0),
                "max_index": index_data.get("max_index", 0),
                "min_index": index_data.get("min_index", 0),
            })
            return result

    def get_stock_heat_index(
        self,
        stock_name: str
    ) -> Dict[str, Any]:
        """
        获取股票热度指数（简化接口）
        
        Args:
            stock_name: 股票名称
            
        Returns:
            热度指数数据
        """
        index_data = self.get_index(stock_name)
        
        # 计算热度等级
        avg_index = index_data.get("avg_index", 0)
        if avg_index > 5000:
            heat_level = "非常热门"
        elif avg_index > 2000:
            heat_level = "比较热门"
        elif avg_index > 500:
            heat_level = "一般关注"
        elif avg_index > 100:
            heat_level = "较少关注"
        else:
            heat_level = "冷门"
            
        return {
            "stock_name": stock_name,
            "avg_index": round(avg_index, 2),
            "max_index": index_data.get("max_index", 0),
            "min_index": index_data.get("min_index", 0),
            "heat_level": heat_level,
            "trend_direction": self._calculate_trend_direction(index_data.get("all_index", [])),
            "is_mock": index_data.get("is_mock", False),
        }

    def _calculate_trend_direction(self, values: List[int]) -> str:
        """计算趋势方向"""
        if not values or len(values) < 7:
            return "数据不足"
            
        # 比较最近7天与之前7天的平均值
        recent = values[-7:]
        previous = values[-14:-7] if len(values) >= 14 else values[:7]
        
        recent_avg = sum(recent) / len(recent)
        previous_avg = sum(previous) / len(previous)
        
        change_pct = (recent_avg - previous_avg) / previous_avg * 100 if previous_avg > 0 else 0
        
        if change_pct > 20:
            return "大幅上升"
        elif change_pct > 5:
            return "小幅上升"
        elif change_pct > -5:
            return "基本持平"
        elif change_pct > -20:
            return "小幅下降"
        else:
            return "大幅下降"