"""
模式匹配API示例
展示如何使用模式匹配功能
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from typing import Dict, List, Optional
from packages.core.vector_store.retrieval.pattern_matcher import PatternMatcher
from packages.core.vector_store.retrieval.pattern_analyzer import PatternAnalyzer


class PatternMatchingAPI:
    """模式匹配API封装"""

    def __init__(self, db_path: str = "data/stock_vectors.db"):
        """初始化API"""
        self.matcher = PatternMatcher(db_path=db_path)
        self.analyzer = PatternAnalyzer(self.matcher)
        self.matcher.connect()

    def close(self):
        """关闭连接"""
        self.matcher.close()

    def find_similar_patterns(
        self,
        stock_code: str,
        end_date: Optional[str] = None,
        top_k: int = 10
    ) -> Dict:
        """
        查找相似走势

        Args:
            stock_code: 股票代码
            end_date: 结束日期（默认最新）
            top_k: 返回数量

        Returns:
            {
                "success": True,
                "data": {
                    "query": {...},
                    "matches": [...],
                    "execution_time_ms": 45
                }
            }
        """
        import time
        start_time = time.time()

        try:
            matches = self.matcher.find_similar_by_stock_date(
                stock_code=stock_code,
                end_date=end_date,
                top_k=top_k,
                exclude_self=True
            )

            # 获取查询信息
            cursor = self.matcher.conn.cursor()
            if end_date is None:
                cursor.execute("""
                    SELECT date FROM daily_bars
                    WHERE stock_code = ?
                    ORDER BY date DESC
                    LIMIT 1
                """, (stock_code,))
                row = cursor.fetchone()
                end_date = row['date'] if row else None

            # 计算开始日期
            cursor.execute("""
                SELECT date FROM daily_bars
                WHERE stock_code = ? AND date <= ?
                ORDER BY date DESC
                LIMIT 1 OFFSET ?
            """, (stock_code, end_date, self.matcher.window_size - 1))
            row = cursor.fetchone()
            start_date = row['date'] if row else None

            execution_time = (time.time() - start_time) * 1000

            return {
                "success": True,
                "data": {
                    "query": {
                        "stock_code": stock_code,
                        "start_date": start_date,
                        "end_date": end_date
                    },
                    "matches": [
                        {
                            "stock_code": m.stock_code,
                            "start_date": m.start_date,
                            "end_date": m.end_date,
                            "similarity": round(m.similarity, 4),
                            "future_return": round(m.future_return, 4) if m.future_return else None,
                            "metadata": m.metadata
                        }
                        for m in matches
                    ],
                    "execution_time_ms": round(execution_time, 2)
                }
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def detect_anomaly(
        self,
        stock_code: str,
        threshold: float = 0.5
    ) -> Dict:
        """
        异常检测

        Args:
            stock_code: 股票代码
            threshold: 相似度阈值

        Returns:
            {
                "success": True,
                "data": {
                    "is_anomaly": True,
                    "max_similarity": 0.35,
                    "message": "...",
                    "nearest_pattern": {...}
                }
            }
        """
        try:
            # 获取最新数据
            cursor = self.matcher.conn.cursor()
            cursor.execute("""
                SELECT date, open, high, low, close, volume
                FROM daily_bars
                WHERE stock_code = ?
                ORDER BY date DESC
                LIMIT ?
            """, (stock_code, self.matcher.window_size))

            rows = cursor.fetchall()
            if len(rows) < self.matcher.window_size:
                return {
                    "success": False,
                    "error": "数据不足"
                }

            current_ohlcv = []
            for row in reversed(rows):
                current_ohlcv.append({
                    'date': row['date'],
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'volume': row['volume'] or 0
                })

            result = self.analyzer.detect_anomaly(current_ohlcv, threshold=threshold)

            return {
                "success": True,
                "data": {
                    "is_anomaly": result.is_anomaly,
                    "max_similarity": round(result.max_similarity, 4),
                    "message": result.message,
                    "nearest_pattern": {
                        "stock_code": result.nearest_pattern.stock_code,
                        "start_date": result.nearest_pattern.start_date,
                        "end_date": result.nearest_pattern.end_date,
                        "similarity": round(result.nearest_pattern.similarity, 4)
                    } if result.nearest_pattern else None
                }
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# 使用示例
if __name__ == "__main__":
    import json

    api = PatternMatchingAPI()

    try:
        # 示例1: 查找相似走势
        print("=" * 60)
        print("示例1: 查找相似走势")
        print("=" * 60)

        result = api.find_similar_patterns(
            stock_code="000001",
            top_k=5
        )

        print(json.dumps(result, indent=2, ensure_ascii=False))

        # 示例2: 异常检测
        print("\n" + "=" * 60)
        print("示例2: 异常检测")
        print("=" * 60)

        result = api.detect_anomaly(
            stock_code="000001",
            threshold=0.7
        )

        print(json.dumps(result, indent=2, ensure_ascii=False))

    finally:
        api.close()
