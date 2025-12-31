"""
模式匹配器 - 时序模式匹配和相似性搜索
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import sqlite3
import numpy as np
import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

from packages.core.vector_store.embeddings.time_series_embedding import TimeSeriesEmbedding


@dataclass
class PatternMatch:
    """模式匹配结果"""
    stock_code: str
    start_date: str
    end_date: str
    similarity: float
    future_return: Optional[float] = None
    future_data: Optional[List[Dict]] = None
    metadata: Optional[Dict] = None


@dataclass
class AnomalyResult:
    """异常检测结果"""
    is_anomaly: bool
    max_similarity: float
    message: str
    nearest_pattern: Optional[PatternMatch] = None


class PatternMatcher:
    """时序模式匹配器"""

    def __init__(self,
                 db_path: str = "data/stock_vectors.db",
                 window_size: int = 20,
                 strategy: str = "indicators"):
        """
        初始化模式匹配器

        Args:
            db_path: 数据库路径
            window_size: 窗口大小
            strategy: 向量化策略
        """
        self.db_path = db_path
        self.window_size = window_size
        self.embedding = TimeSeriesEmbedding(window_size=window_size, strategy=strategy)
        self.conn = None

    def connect(self):
        """连接数据库"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        """关闭连接"""
        if self.conn:
            self.conn.close()

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算余弦相似度"""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))

    def _get_future_data(self, stock_code: str, end_date: str, days: int = 10) -> List[Dict]:
        """获取未来N天的数据"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT date, open, high, low, close, volume
            FROM daily_bars
            WHERE stock_code = ? AND date > ?
            ORDER BY date ASC
            LIMIT ?
        """, (stock_code, end_date, days))

        future_data = []
        for row in cursor.fetchall():
            future_data.append({
                'date': row['date'],
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume']
            })

        return future_data

    def _calculate_return(self, future_data: List[Dict]) -> Optional[float]:
        """计算未来收益率"""
        if not future_data or len(future_data) < 2:
            return None

        start_price = float(future_data[0]['close'])
        end_price = float(future_data[-1]['close'])

        if start_price == 0:
            return None

        return (end_price - start_price) / start_price

    def find_similar_patterns(
        self,
        query_ohlcv: List[Dict],
        top_k: int = 10,
        filters: Optional[Dict] = None,
        include_future: bool = True
    ) -> List[PatternMatch]:
        """
        找历史相似走势

        Args:
            query_ohlcv: 查询的K线数据
            top_k: 返回数量
            filters: 过滤条件 {stock_code, date_from, date_to}
            include_future: 是否包含后续走势信息

        Returns:
            相似模式列表，包含后续走势信息
        """
        # 1. 向量化查询模式
        query_vec = self.embedding.embed_window(query_ohlcv)

        # 2. 获取所有候选模式
        cursor = self.conn.cursor()

        sql = "SELECT id, stock_code, start_date, end_date, embedding, metadata FROM pattern_vectors WHERE 1=1"
        params = []

        if filters:
            if 'stock_code' in filters and filters['stock_code']:
                sql += " AND stock_code = ?"
                params.append(filters['stock_code'])
            if 'date_from' in filters and filters['date_from']:
                sql += " AND end_date >= ?"
                params.append(filters['date_from'])
            if 'date_to' in filters and filters['date_to']:
                sql += " AND start_date <= ?"
                params.append(filters['date_to'])

        cursor.execute(sql, params)

        # 3. 计算相似度
        similarities = []
        for row in cursor.fetchall():
            pattern_vec = np.frombuffer(row['embedding'], dtype=np.float32)
            similarity = self._cosine_similarity(query_vec, pattern_vec)

            similarities.append({
                'stock_code': row['stock_code'],
                'start_date': row['start_date'],
                'end_date': row['end_date'],
                'similarity': similarity,
                'metadata': json.loads(row['metadata']) if row['metadata'] else {}
            })

        # 4. 排序并取top_k
        similarities.sort(key=lambda x: x['similarity'], reverse=True)
        top_matches = similarities[:top_k]

        # 5. 获取后续走势
        matches = []
        for m in top_matches:
            future_data = None
            future_return = None

            if include_future:
                future_data = self._get_future_data(m['stock_code'], m['end_date'], days=10)
                future_return = self._calculate_return(future_data)

            matches.append(PatternMatch(
                stock_code=m['stock_code'],
                start_date=m['start_date'],
                end_date=m['end_date'],
                similarity=m['similarity'],
                future_return=future_return,
                future_data=future_data,
                metadata=m['metadata']
            ))

        return matches

    def find_similar_by_stock_date(
        self,
        stock_code: str,
        end_date: Optional[str] = None,
        top_k: int = 10,
        exclude_self: bool = True
    ) -> List[PatternMatch]:
        """
        根据股票代码和日期查找相似模式

        Args:
            stock_code: 股票代码
            end_date: 结束日期（默认最新）
            top_k: 返回数量
            exclude_self: 是否排除自身

        Returns:
            相似模式列表
        """
        # 1. 获取查询窗口的K线数据
        cursor = self.conn.cursor()

        if end_date is None:
            cursor.execute("""
                SELECT date FROM daily_bars
                WHERE stock_code = ?
                ORDER BY date DESC
                LIMIT 1
            """, (stock_code,))
            row = cursor.fetchone()
            if not row:
                return []
            end_date = row['date']

        # 获取窗口数据
        cursor.execute("""
            SELECT date, open, high, low, close, volume
            FROM daily_bars
            WHERE stock_code = ? AND date <= ?
            ORDER BY date DESC
            LIMIT ?
        """, (stock_code, end_date, self.window_size))

        rows = cursor.fetchall()
        if len(rows) < self.window_size:
            return []

        # 反转顺序（从旧到新）
        query_ohlcv = []
        for row in reversed(rows):
            query_ohlcv.append({
                'date': row['date'],
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume'] or 0
            })

        # 2. 查找相似模式
        matches = self.find_similar_patterns(query_ohlcv, top_k=top_k * 2 if exclude_self else top_k)

        # 3. 排除自身
        if exclude_self:
            matches = [m for m in matches if not (m.stock_code == stock_code and m.end_date == end_date)]
            matches = matches[:top_k]

        return matches

