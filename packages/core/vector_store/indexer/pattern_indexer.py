"""
模式索引器 - 将历史K线转为向量
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import sqlite3
import numpy as np
import json
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

from packages.core.vector_store.embeddings.time_series_embedding import TimeSeriesEmbedding

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class IndexStats:
    """索引统计"""
    new_docs: int = 0
    total_docs: int = 0
    skipped: int = 0
    failed: int = 0


class PatternIndexer:
    """模式索引器 - 将历史K线转为向量"""

    def __init__(self,
                 db_path: str = "data/stock_vectors.db",
                 window_size: int = 20,
                 step_size: int = 5,
                 strategy: str = "indicators"):
        """
        初始化模式索引器

        Args:
            db_path: 数据库路径
            window_size: 窗口大小（天数）
            step_size: 滑动步长（天数）
            strategy: 向量化策略
        """
        self.db_path = db_path
        self.window_size = window_size
        self.step_size = step_size
        self.embedding = TimeSeriesEmbedding(window_size=window_size, strategy=strategy)
        self.conn = None

    def connect(self):
        """连接数据库"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        logger.info(f"已连接到数据库: {self.db_path}")

    def close(self):
        """关闭连接"""
        if self.conn:
            self.conn.close()
            logger.info("数据库连接已关闭")

    def _get_daily_bars(self, stock_code: str) -> List[Dict]:
        """获取历史K线数据"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT date, open, high, low, close, volume
            FROM daily_bars
            WHERE stock_code = ?
            ORDER BY date ASC
        """, (stock_code,))

        bars = []
        for row in cursor.fetchall():
            bars.append({
                'date': row['date'],
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume'] or 0
            })

        return bars

    def _calculate_window_return(self, window: List[Dict]) -> float:
        """计算窗口收益率"""
        if not window or len(window) < 2:
            return 0.0

        start_price = float(window[0]['close'])
        end_price = float(window[-1]['close'])

        if start_price == 0:
            return 0.0

        return (end_price - start_price) / start_price

    def _calculate_volatility(self, window: List[Dict]) -> float:
        """计算窗口波动率"""
        if not window or len(window) < 2:
            return 0.0

        closes = [float(d['close']) for d in window]
        returns = [(closes[i] - closes[i-1]) / closes[i-1] if closes[i-1] != 0 else 0
                   for i in range(1, len(closes))]

        return float(np.std(returns)) if returns else 0.0

    def index_stock_patterns(self, stock_code: str) -> IndexStats:
        """
        索引单只股票的所有历史模式

        使用滑动窗口生成向量
        """
        stats = IndexStats()

        # 1. 获取历史K线
        bars = self._get_daily_bars(stock_code)
        if len(bars) < self.window_size:
            logger.debug(f"{stock_code}: 数据不足（{len(bars)}天 < {self.window_size}天）")
            stats.skipped += 1
            return stats

        # 2. 滑动窗口生成模式
        cursor = self.conn.cursor()

        for i in range(0, len(bars) - self.window_size + 1, self.step_size):
            window = bars[i:i + self.window_size]

            try:
                # 向量化
                embedding = self.embedding.embed_window(window)

                # 元数据
                metadata = {
                    "return": self._calculate_window_return(window),
                    "volatility": self._calculate_volatility(window)
                }

                # 存储
                cursor.execute("""
                    INSERT OR REPLACE INTO pattern_vectors (
                        stock_code, start_date, end_date, window_size,
                        pattern_type, embedding, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    stock_code,
                    window[0]['date'],
                    window[-1]['date'],
                    self.window_size,
                    "price_window",
                    embedding.tobytes(),
                    json.dumps(metadata)
                ))

                stats.new_docs += 1

            except Exception as e:
                logger.error(f"{stock_code} 窗口 {window[0]['date']}-{window[-1]['date']} 索引失败: {e}")
                stats.failed += 1

        self.conn.commit()
        stats.total_docs = stats.new_docs
        return stats

    def index_all_stocks(self, stock_codes: Optional[List[str]] = None) -> IndexStats:
        """批量索引所有股票"""
        total_stats = IndexStats()

        # 如果未指定股票列表，获取所有股票
        if stock_codes is None:
            cursor = self.conn.cursor()
            cursor.execute("SELECT DISTINCT stock_code FROM daily_bars ORDER BY stock_code")
            stock_codes = [row['stock_code'] for row in cursor.fetchall()]

        logger.info(f"开始索引 {len(stock_codes)} 只股票的历史模式...")
        logger.info(f"窗口大小: {self.window_size}天, 步长: {self.step_size}天")

        for i, code in enumerate(stock_codes):
            if (i + 1) % 100 == 0:
                logger.info(f"进度: {i+1}/{len(stock_codes)} (新增:{total_stats.new_docs}, 跳过:{total_stats.skipped}, 失败:{total_stats.failed})")

            stats = self.index_stock_patterns(code)
            total_stats.new_docs += stats.new_docs
            total_stats.total_docs += stats.total_docs
            total_stats.skipped += stats.skipped
            total_stats.failed += stats.failed

        logger.info(f"\n索引完成:")
        logger.info(f"  新增模式: {total_stats.new_docs}")
        logger.info(f"  跳过股票: {total_stats.skipped}")
        logger.info(f"  失败: {total_stats.failed}")

        return total_stats
