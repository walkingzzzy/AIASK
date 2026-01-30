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
        return {
            'index': 50,
            'level': 'neutral',
            'components': {
                'momentum': 50,
                'volatility': 50,
                'volume': 50,
                'breadth': 50
            }
        }

sentiment_analyzer = SentimentAnalyzer()
