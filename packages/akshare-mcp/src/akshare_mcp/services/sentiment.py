"""情绪分析服务 — 三分量复合评分"""
import math
from datetime import date, datetime
from typing import List, Dict, Any, Optional

import numpy as np

# ── 新闻情绪关键词库 ──
_BULLISH_KEYWORDS = [
    '利好', '大涨', '涨停', '突破', '新高', '放量', '加仓', '抄底',
    '回暖', '反弹', '景气', '超预期', '增持', '回购', '分红',
    '订单', '中标', '扩产', '盈利', '业绩增长',
]
_BEARISH_KEYWORDS = [
    '利空', '大跌', '跌停', '破位', '新低', '缩量', '减持', '清仓',
    '暴雷', '亏损', '退市', '违规', '处罚', '下调', '预警',
    '裁员', '诉讼', '暴跌', '崩盘', '爆仓',
]


class SentimentAnalyzer:
    @staticmethod
    def _parse_kline_date(value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        text = str(value or "").strip()
        if not text:
            return None
        for parser in (
            lambda item: date.fromisoformat(item[:10]),
            lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")).date(),
        ):
            try:
                return parser(text)
            except Exception:
                continue
        digits = "".join(ch for ch in text if ch.isdigit())
        if len(digits) >= 8:
            try:
                return date.fromisoformat(f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}")
            except Exception:
                return None
        return None

    @classmethod
    def _sort_klines(cls, klines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(
            [dict(item) for item in list(klines or []) if isinstance(item, dict)],
            key=lambda item: (
                cls._parse_kline_date(item.get("date")) or date.min,
                str(item.get("date") or ""),
            ),
        )

    # ── 分量 1: 价量动量（40%权重） ──
    @classmethod
    def _price_momentum_score(cls, klines: List[Dict[str, Any]]) -> float:
        """基于价格变化和量比计算动量得分 0~100"""
        ordered_klines = cls._sort_klines(klines)
        if not ordered_klines or len(ordered_klines) < 20:
            return 50.0
        closes = [k['close'] for k in ordered_klines]
        volumes = [k['volume'] for k in ordered_klines]
        base_close = float(closes[-20] or 0.0)
        if abs(base_close) < 1e-9:
            return 50.0
        price_change = (closes[-1] - base_close) / base_close
        volume_ratio = np.mean(volumes[-5:]) / max(np.mean(volumes[-20:-5]), 1e-9)
        score = 50 + price_change * 100 + (volume_ratio - 1) * 20
        return max(0.0, min(100.0, score))

    # ── 分量 2: 新闻情绪（30%权重） ──
    @staticmethod
    def _news_sentiment_score(headlines: List[str], decay_half_life: int = 5) -> float:
        """基于关键词匹配 + 时间衰减计算新闻情绪得分 0~100
        headlines 按时间倒序排列（最新在前）"""
        if not headlines:
            return 50.0
        decay_rate = math.log(2) / max(decay_half_life, 1)
        total_weight = 0.0
        weighted_score = 0.0
        for i, title in enumerate(headlines):
            w = math.exp(-decay_rate * i)
            total_weight += w
            bull = sum(1 for kw in _BULLISH_KEYWORDS if kw in title)
            bear = sum(1 for kw in _BEARISH_KEYWORDS if kw in title)
            if bull + bear == 0:
                s = 50.0
            else:
                s = 50.0 + 50.0 * (bull - bear) / (bull + bear)
            weighted_score += w * s
        return max(0.0, min(100.0, weighted_score / max(total_weight, 1e-9)))

    # ── 分量 3: 资金流向（30%权重） ──
    @staticmethod
    def _fund_flow_score(fund_flow_data: Optional[Dict[str, Any]]) -> float:
        """基于北向资金净买入和融资余额变化率计算得分 0~100"""
        if not fund_flow_data:
            return 50.0
        score = 50.0
        # 北向资金净买入（正为流入）
        north_net_raw = float(fund_flow_data.get('north_net_buy', 0) or 0)
        north_unit = str(
            fund_flow_data.get('north_net_buy_unit')
            or fund_flow_data.get('north_net_unit')
            or 'yuan'
        ).strip().lower()
        unit_multiplier = {
            'yuan': 1.0,
            'cny': 1.0,
            'rmb': 1.0,
            'ten_thousand_cny': 1e4,
            'wanyuan': 1e4,
            '万元': 1e4,
            'yi': 1e8,
            '亿元': 1e8,
        }.get(north_unit, 1.0)
        north_net = north_net_raw * unit_multiplier
        if north_net != 0:
            # 归一化：假设 ±10亿 为满分偏移
            score += max(-25.0, min(25.0, north_net / 1e9 * 25.0))
        # 融资余额变化率
        margin_change = float(fund_flow_data.get('margin_change_rate', 0) or 0)
        if margin_change != 0:
            score += max(-25.0, min(25.0, margin_change * 250.0))
        return max(0.0, min(100.0, score))

    def analyze_sentiment(
        self,
        klines: List[Dict[str, Any]],
        news_headlines: Optional[List[str]] = None,
        fund_flow_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """三分量复合情绪评分"""
        pm = self._price_momentum_score(klines)
        ns = self._news_sentiment_score(news_headlines or [])
        ff = self._fund_flow_score(fund_flow_data)

        # 加权复合
        composite = pm * 0.4 + ns * 0.3 + ff * 0.3

        if composite > 70:
            sentiment = 'bullish'
        elif composite < 30:
            sentiment = 'bearish'
        else:
            sentiment = 'neutral'

        return {
            'sentiment': sentiment,
            'score': round(composite, 2),
            'components': {
                'price_momentum': round(pm, 2),
                'news_sentiment': round(ns, 2),
                'fund_flow': round(ff, 2),
            },
            'weights': {'price_momentum': 0.4, 'news_sentiment': 0.3, 'fund_flow': 0.3},
        }
    
    @staticmethod
    def calculate_fear_greed_index(
        index_klines: List[Dict[str, Any]] | None = None,
        breadth_data: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """计算恐惧贪婪指数（支持外部传入数据，便于测试与回放）。"""

        def _clamp(v: float) -> int:
            return int(max(0, min(100, round(v))))

        components = {
            'momentum': 50,
            'volatility': 50,
            'volume': 50,
            'breadth': 50,
        }

        # 1) 指数K线驱动：动量、波动、成交量
        ordered_klines = SentimentAnalyzer._sort_klines(index_klines or [])
        if ordered_klines and len(ordered_klines) >= 5:
            closes = [float(k.get('close', 0) or 0) for k in ordered_klines]
            volumes = [float(k.get('volume', 0) or 0) for k in ordered_klines]

            if len(closes) >= 5 and closes[-5] > 0:
                momentum_pct = (closes[-1] - closes[-5]) / closes[-5] * 100.0
                components['momentum'] = _clamp(50 + momentum_pct * 4.0)

            if len(closes) >= 20:
                recent = closes[-20:]
                base = np.mean(recent) if np.mean(recent) else 1.0
                # 波动越大，越偏恐惧（分值越低）
                vol_pct = float(np.std(recent) / base * 100.0)
                components['volatility'] = _clamp(75 - vol_pct * 8.0)

            if len(volumes) >= 20:
                short_v = float(np.mean(volumes[-5:]))
                long_v = float(np.mean(volumes[-20:-5])) if np.mean(volumes[-20:-5]) else 0.0
                if long_v > 0:
                    vr = short_v / long_v
                    components['volume'] = _clamp(50 + (vr - 1.0) * 25.0)

        # 2) 市场广度：外部传入 breadth_data 优先（测试契约依赖）
        if breadth_data:
            lu = float(breadth_data.get('limit_up_count', 0) or 0)
            ld = float(breadth_data.get('limit_down_count', 0) or 0)
            adv = float(breadth_data.get('advance_count', 0) or 0)
            dec = float(breadth_data.get('decline_count', 0) or 0)
            limit_balance = (lu - ld) / max(lu + ld, 1.0)
            adv_balance = (adv - dec) / max(adv + dec, 1.0)
            breadth_score = 50 + limit_balance * 30 + adv_balance * 20
            components['breadth'] = _clamp(breadth_score)

        index = _clamp(sum(components.values()) / 4.0)
        if index >= 80:
            level = 'extreme_greed'
        elif index >= 60:
            level = 'greed'
        elif index <= 20:
            level = 'extreme_fear'
        elif index <= 40:
            level = 'fear'
        else:
            level = 'neutral'

        return {
            'index': index,
            'level': level,
            'components': components,
        }


sentiment_analyzer = SentimentAnalyzer()
