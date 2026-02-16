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
        if index_klines and len(index_klines) >= 5:
            closes = [float(k.get('close', 0) or 0) for k in index_klines if isinstance(k, dict)]
            volumes = [float(k.get('volume', 0) or 0) for k in index_klines if isinstance(k, dict)]

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
