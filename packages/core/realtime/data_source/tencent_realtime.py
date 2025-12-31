"""
腾讯实时行情数据适配器
"""
import requests
import json
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TencentRealtimeAdapter:
    """腾讯实时行情适配器"""

    BASE_URL = "http://qt.gtimg.cn/q="

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://gu.qq.com/'
        })

    def get_realtime_quote(self, stock_code: str) -> Optional[Dict]:
        """获取实时行情"""
        try:
            # 转换代码格式
            qq_code = self._convert_code(stock_code)

            # 请求数据
            url = f"{self.BASE_URL}{qq_code}"
            response = self.session.get(url, timeout=5)
            response.encoding = 'gbk'

            # 解析数据
            data = self._parse_response(response.text, stock_code)
            return data

        except Exception as e:
            logger.error(f"获取腾讯实时行情失败 {stock_code}: {e}")
            return None

    def get_batch_quotes(self, stock_codes: List[str]) -> Dict[str, Dict]:
        """批量获取实时行情"""
        try:
            # 转换代码
            qq_codes = [self._convert_code(code) for code in stock_codes]

            # 批量请求
            url = f"{self.BASE_URL}{','.join(qq_codes)}"
            response = self.session.get(url, timeout=10)
            response.encoding = 'gbk'

            # 解析数据
            results = {}
            lines = response.text.strip().split('\n')

            for line, code in zip(lines, stock_codes):
                data = self._parse_response(line, code)
                if data:
                    results[code] = data

            return results

        except Exception as e:
            logger.error(f"批量获取腾讯实时行情失败: {e}")
            return {}

    def _convert_code(self, stock_code: str) -> str:
        """转换股票代码为腾讯格式"""
        code = stock_code.split('.')[0]

        if stock_code.endswith('.SH') or code.startswith('6'):
            return f"sh{code}"
        elif stock_code.endswith('.SZ') or code.startswith(('0', '3')):
            return f"sz{code}"
        else:
            return f"sh{code}"

    def _parse_response(self, response_text: str, stock_code: str) -> Optional[Dict]:
        """解析响应数据"""
        try:
            # 提取数据部分
            if '~' not in response_text:
                return None

            # 分割数据
            parts = response_text.split('~')
            if len(parts) < 50:
                return None

            # 构建数据字典
            quote = {
                'code': stock_code,
                'name': parts[1],
                'current': float(parts[3]),
                'pre_close': float(parts[4]),
                'open': float(parts[5]),
                'volume': int(parts[6]),  # 成交量（手）
                'bid_volume': int(parts[7]),  # 外盘
                'ask_volume': int(parts[8]),  # 内盘
                'bid1_price': float(parts[9]),
                'bid1_volume': int(parts[10]),
                'bid2_price': float(parts[11]),
                'bid2_volume': int(parts[12]),
                'bid3_price': float(parts[13]),
                'bid3_volume': int(parts[14]),
                'bid4_price': float(parts[15]),
                'bid4_volume': int(parts[16]),
                'bid5_price': float(parts[17]),
                'bid5_volume': int(parts[18]),
                'ask1_price': float(parts[19]),
                'ask1_volume': int(parts[20]),
                'ask2_price': float(parts[21]),
                'ask2_volume': int(parts[22]),
                'ask3_price': float(parts[23]),
                'ask3_volume': int(parts[24]),
                'ask4_price': float(parts[25]),
                'ask4_volume': int(parts[26]),
                'ask5_price': float(parts[27]),
                'ask5_volume': int(parts[28]),
                'high': float(parts[33]),
                'low': float(parts[34]),
                'amount': float(parts[37]),  # 成交额（万元）
                'turnover_rate': float(parts[38]),  # 换手率
                'pe_ratio': float(parts[39]),  # 市盈率
                'timestamp': datetime.now().isoformat(),
                'source': 'tencent'
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
            logger.error(f"解析腾讯数据失败 {stock_code}: {e}")
            return None

    def is_available(self) -> bool:
        """检查数据源是否可用"""
        try:
            response = self.session.get(f"{self.BASE_URL}sh000001", timeout=3)
            return response.status_code == 200
        except:
            return False
