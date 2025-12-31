"""
异常检测和技术形态识别
"""
from typing import List, Dict, Optional
from .pattern_matcher import PatternMatcher, AnomalyResult, PatternMatch


class PatternAnalyzer:
    """模式分析器 - 异常检测和形态识别"""

    def __init__(self, matcher: PatternMatcher):
        """
        初始化分析器

        Args:
            matcher: 模式匹配器实例
        """
        self.matcher = matcher

    def detect_anomaly(
        self,
        current_ohlcv: List[Dict],
        threshold: float = 0.5
    ) -> AnomalyResult:
        """
        异常检测

        如果当前走势与历史所有模式的相似度都低于阈值，则为异常

        Args:
            current_ohlcv: 当前K线数据
            threshold: 相似度阈值

        Returns:
            异常检测结果
        """
        similar = self.matcher.find_similar_patterns(
            current_ohlcv,
            top_k=1,
            include_future=False
        )

        if not similar or similar[0].similarity < threshold:
            return AnomalyResult(
                is_anomaly=True,
                max_similarity=similar[0].similarity if similar else 0,
                message="当前走势与历史模式差异较大，可能存在异常",
                nearest_pattern=similar[0] if similar else None
            )

        return AnomalyResult(
            is_anomaly=False,
            max_similarity=similar[0].similarity,
            message="当前走势正常",
            nearest_pattern=similar[0]
        )

    def find_technical_pattern(
        self,
        pattern_type: str,
        stock_code: Optional[str] = None,
        top_k: int = 10
    ) -> List[PatternMatch]:
        """
        识别技术形态

        Args:
            pattern_type: 形态类型 ["head_shoulders", "double_bottom", "triangle", etc.]
            stock_code: 股票代码（可选）
            top_k: 返回数量

        Returns:
            匹配的形态列表
        """
        # 预定义形态的向量模板
        pattern_template = self._get_pattern_template(pattern_type)

        if pattern_template is None:
            return []

        filters = {}
        if stock_code:
            filters['stock_code'] = stock_code

        return self.matcher.find_similar_patterns(
            pattern_template,
            top_k=top_k,
            filters=filters
        )

    def _get_pattern_template(self, pattern_type: str) -> Optional[List[Dict]]:
        """
        获取技术形态模板

        Args:
            pattern_type: 形态类型

        Returns:
            K线数据模板
        """
        # TODO: 实现各种技术形态的模板
        # 这里可以预定义一些经典的技术形态
        templates = {
            "head_shoulders": self._create_head_shoulders_template(),
            "double_bottom": self._create_double_bottom_template(),
            # 可以添加更多形态
        }

        return templates.get(pattern_type)

    def _create_head_shoulders_template(self) -> List[Dict]:
        """创建头肩顶形态模板"""
        # 简化的头肩顶模板：左肩-头部-右肩
        template = []
        base_price = 100

        # 左肩
        for i in range(5):
            template.append({
                'date': f'2024-01-{i+1:02d}',
                'open': base_price,
                'high': base_price + 5,
                'low': base_price - 2,
                'close': base_price + 3,
                'volume': 1000000
            })

        # 头部
        for i in range(5, 10):
            template.append({
                'date': f'2024-01-{i+1:02d}',
                'open': base_price + 3,
                'high': base_price + 10,
                'low': base_price,
                'close': base_price + 7,
                'volume': 1200000
            })

        # 右肩
        for i in range(10, 15):
            template.append({
                'date': f'2024-01-{i+1:02d}',
                'open': base_price + 7,
                'high': base_price + 6,
                'low': base_price - 1,
                'close': base_price + 2,
                'volume': 1000000
            })

        # 下跌
        for i in range(15, 20):
            template.append({
                'date': f'2024-01-{i+1:02d}',
                'open': base_price + 2,
                'high': base_price + 1,
                'low': base_price - 5,
                'close': base_price - 3,
                'volume': 1500000
            })

        return template

    def _create_double_bottom_template(self) -> List[Dict]:
        """创建双底形态模板"""
        template = []
        base_price = 100

        # 第一个底部
        for i in range(7):
            price_change = -5 if i < 3 else (5 if i > 4 else 0)
            template.append({
                'date': f'2024-01-{i+1:02d}',
                'open': base_price + price_change,
                'high': base_price + price_change + 2,
                'low': base_price + price_change - 2,
                'close': base_price + price_change + 1,
                'volume': 1000000
            })

        # 反弹
        for i in range(7, 13):
            template.append({
                'date': f'2024-01-{i+1:02d}',
                'open': base_price,
                'high': base_price + 3,
                'low': base_price - 1,
                'close': base_price + 2,
                'volume': 900000
            })

        # 第二个底部
        for i in range(13, 20):
            price_change = -5 if i < 16 else 0
            template.append({
                'date': f'2024-01-{i+1:02d}',
                'open': base_price + price_change,
                'high': base_price + price_change + 2,
                'low': base_price + price_change - 2,
                'close': base_price + price_change + 1,
                'volume': 1000000
            })

        return template
