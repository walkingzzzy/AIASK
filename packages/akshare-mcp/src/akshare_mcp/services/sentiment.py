"""情绪分析服务"""
import numpy as np
from typing import List, Dict, Any

class SentimentAnalyzer:
    @staticmethod
    def analyze_sentiment(klines: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not klines or len(klines) < 20:
            return {'sentiment': 'neutral', 'score': 50}
        
        closes = [k['close'] for k in klines]
        volumes = [k['volume'] for k in klines]
        
        price_change = (closes[-1] - closes[-20]) / closes[-20]
        volume_ratio = np.mean(volumes[-5:]) / np.mean(volumes[-20:-5])
        
        score = 50 + price_change * 100 + (volume_ratio - 1) * 20
        score = max(0, min(100, score))
        
        if score > 70:
            sentiment = 'bullish'
        elif score < 30:
            sentiment = 'bearish'
        else:
            sentiment = 'neutral'
        
        return {
            'sentiment': sentiment,
            'score': round(score, 2),
            'price_momentum': round(price_change * 100, 2),
            'volume_ratio': round(volume_ratio, 2)
        }
    
    @staticmethod
    def calculate_fear_greed_index() -> Dict[str, Any]:
        def _clamp(v: float) -> int:
            return int(max(0, min(100, round(v))))

        components = {
            'momentum': 50,
            'volatility': 50,
            'volume': 50,
            'breadth': 50
        }
        notes: List[str] = []

        # 1) 动量 + 波动（上证指数）
        try:
            from ..tools.market.quote import get_index_quote
            idx = get_index_quote("000001")
            data = (idx or {}).get('data') or {}
            change_pct = float(data.get('changePercent') or 0.0)
            pre_close = float(data.get('preClose') or 0.0)
            high = float(data.get('high') or 0.0)
            low = float(data.get('low') or 0.0)

            # 涨跌幅映射到动量：+6% 约对应 +48 分
            components['momentum'] = _clamp(50 + change_pct * 8.0)

            # 振幅越大，恐惧越高（分值越低）
            if pre_close > 0 and high > 0 and low > 0:
                intraday_range_pct = (high - low) / pre_close * 100
                components['volatility'] = _clamp(75 - intraday_range_pct * 8.0)
        except Exception:
            notes.append('index_quote_unavailable')

        # 2) 市场广度（涨停统计）
        try:
            from ..tools.market.limit_up import get_limit_up_statistics
            stat = get_limit_up_statistics()
            data = (stat or {}).get('data') or {}
            total_limit_up = float(data.get('totalLimitUp') or 0.0)
            success_rate = float(data.get('successRate') or 0.0)
            components['breadth'] = _clamp(30 + min(total_limit_up, 120) * 0.4 + success_rate * 0.2)
        except Exception:
            notes.append('limit_up_stats_unavailable')

        # 3) 资金（北向）
        try:
            from ..tools.fund_flow import get_north_fund
            north = get_north_fund(days=1)
            items = ((north or {}).get('data') or {}).get('items') or []
            latest_total = 0.0
            if items:
                latest_total = float(items[-1].get('total') or 0.0)
            # 单位按元估计：每 +10 亿约增加 5 分
            components['volume'] = _clamp(50 + latest_total / 1_000_000_000 * 5.0)
        except Exception:
            notes.append('north_fund_unavailable')

        index = _clamp(sum(components.values()) / 4.0)
        if index >= 67:
            level = 'greed'
        elif index <= 33:
            level = 'fear'
        else:
            level = 'neutral'

        result = {
            'index': index,
            'level': level,
            'components': components
        }
        if notes:
            result['notes'] = notes
        return result

sentiment_analyzer = SentimentAnalyzer()
