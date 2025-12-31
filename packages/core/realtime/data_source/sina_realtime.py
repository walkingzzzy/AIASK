"""
新浪实时行情数据适配器
"""
import requests
import re
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SinaRealtimeAdapter:
    """新浪实时行情适配器"""

    BASE_URL = "http://hq.sinajs.cn/list="
    # 备用URL
    BACKUP_URL = "https://hq.sinajs.cn/list="

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://finance.sina.com.cn'
        })

    def get_realtime_quote(self, stock_code: str) -> Optional[Dict]:
        """
        获取实时行情

        Args:
            stock_code: 股票代码 (如 sh600519, sz000001)

        Returns:
            行情数据字典
        """
        try:
            # 转换代码格式
            sina_code = self._convert_code(stock_code)

            # 尝试主URL
            for base_url in [self.BASE_URL, self.BACKUP_URL]:
                try:
                    url = f"{base_url}{sina_code}"
                    response = self.session.get(url, timeout=3)
                    response.encoding = 'gbk'
                    
                    # 解析数据
                    data = self._parse_response(response.text, stock_code)
                    if data:
                        return data
                except requests.exceptions.Timeout:
                    logger.warning(f"新浪行情请求超时: {base_url}")
                    continue
                except Exception as e:
                    logger.warning(f"新浪行情请求失败: {e}")
                    continue
            
            return None

        except Exception as e:
            logger.error(f"获取新浪实时行情失败 {stock_code}: {e}")
            return None

    def get_batch_quotes(self, stock_codes: List[str]) -> Dict[str, Dict]:
        """
        批量获取实时行情

        Args:
            stock_codes: 股票代码列表

        Returns:
            {code: quote_data}
        """
        try:
            # 转换代码
            sina_codes = [self._convert_code(code) for code in stock_codes]

            # 批量请求（新浪支持一次请求多个股票）
            url = f"{self.BASE_URL}{','.join(sina_codes)}"
            response = self.session.get(url, timeout=10)
            response.encoding = 'gbk'

            # 解析每个股票的数据
            results = {}
            lines = response.text.strip().split('\n')

            for line, code in zip(lines, stock_codes):
                data = self._parse_response(line, code)
                if data:
                    results[code] = data

            return results

        except Exception as e:
            logger.error(f"批量获取新浪实时行情失败: {e}")
            return {}

    def _convert_code(self, stock_code: str) -> str:
        """转换股票代码为新浪格式"""
        # 去除后缀
        code = stock_code.split('.')[0]

        # 判断市场
        if stock_code.endswith('.SH') or code.startswith('6'):
            return f"sh{code}"
        elif stock_code.endswith('.SZ') or code.startswith(('0', '3')):
            return f"sz{code}"
        else:
            return f"sh{code}"  # 默认上海

    def _parse_response(self, response_text: str, stock_code: str) -> Optional[Dict]:
        """解析响应数据"""
        try:
            # 提取数据部分
            match = re.search(r'"(.+)"', response_text)
            if not match:
                return None

            data_str = match.group(1)
            if not data_str:
                return None

            # 分割数据
            fields = data_str.split(',')
            if len(fields) < 32:
                return None

            # 构建数据字典
            quote = {
                'code': stock_code,
                'name': fields[0],
                'open': float(fields[1]),
                'pre_close': float(fields[2]),
                'current': float(fields[3]),
                'high': float(fields[4]),
                'low': float(fields[5]),
                'bid': float(fields[6]),  # 买一价
                'ask': float(fields[7]),  # 卖一价
                'volume': int(fields[8]),  # 成交量（股）
                'amount': float(fields[9]),  # 成交额（元）
                'bid1_volume': int(fields[10]),
                'bid1_price': float(fields[11]),
                'bid2_volume': int(fields[12]),
                'bid2_price': float(fields[13]),
                'bid3_volume': int(fields[14]),
                'bid3_price': float(fields[15]),
                'bid4_volume': int(fields[16]),
                'bid4_price': float(fields[17]),
                'bid5_volume': int(fields[18]),
                'bid5_price': float(fields[19]),
                'ask1_volume': int(fields[20]),
                'ask1_price': float(fields[21]),
                'ask2_volume': int(fields[22]),
                'ask2_price': float(fields[23]),
                'ask3_volume': int(fields[24]),
                'ask3_price': float(fields[25]),
                'ask4_volume': int(fields[26]),
                'ask4_price': float(fields[27]),
                'ask5_volume': int(fields[28]),
                'ask5_price': float(fields[29]),
                'date': fields[30],
                'time': fields[31],
                'timestamp': datetime.now().isoformat(),
                'source': 'sina'
            }

            # 计算涨跌幅
            if quote['pre_close'] > 0:
                quote['change'] = quote['current'] - quote['pre_close']
                quote['change_pct'] = (quote['change'] / quote['pre_close']) * 100
            else:
                quote['change'] = 0
                quote['change_pct'] = 0

            return quote

        except Exception as e:
            logger.error(f"解析新浪数据失败 {stock_code}: {e}")
            return None

    def is_available(self) -> bool:
        """检查数据源是否可用"""
        try:
            # 测试请求
            response = self.session.get(f"{self.BASE_URL}sh000001", timeout=3)
            return response.status_code == 200
        except:
            return False
