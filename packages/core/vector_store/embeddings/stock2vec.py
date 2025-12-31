"""
Stock2Vec - 股票关系向量化
借鉴Word2Vec思路，通过股票的涨跌关系学习股票向量表示
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
import pandas as pd
import sqlite3
import pickle
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Stock2Vec:
    """股票关系向量化"""

    def __init__(self, embedding_dim: int = 64, db_path: str = "data/stock_vectors.db"):
        """
        初始化Stock2Vec

        Args:
            embedding_dim: 向量维度
            db_path: 数据库路径
        """
        self.embedding_dim = embedding_dim
        self.db_path = db_path
        self.embeddings = {}  # stock_code -> vector
        self.model = None
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

    def _get_daily_returns(self, days: int = 500) -> pd.DataFrame:
        """
        获取所有股票的日收益率

        Args:
            days: 获取最近N天的数据

        Returns:
            DataFrame, index=date, columns=stock_codes, values=returns
        """
        cursor = self.conn.cursor()

        # 获取最近N天的日期范围
        cursor.execute("""
            SELECT DISTINCT date
            FROM daily_bars
            ORDER BY date DESC
            LIMIT ?
        """, (days,))

        dates = [row['date'] for row in cursor.fetchall()]
        dates.reverse()  # 从旧到新

        if not dates:
            logger.warning("未找到任何交易日期")
            return pd.DataFrame()

        start_date = dates[0]
        end_date = dates[-1]
        logger.info(f"日期范围: {start_date} ~ {end_date}, 共 {len(dates)} 个交易日")

        # 获取所有股票在这个时间范围内的数据
        cursor.execute("""
            SELECT stock_code, date, close
            FROM daily_bars
            WHERE date >= ? AND date <= ?
            ORDER BY stock_code, date
        """, (start_date, end_date))

        # 构建数据列表
        data_list = []
        for row in cursor.fetchall():
            data_list.append({
                'date': row['date'],
                'stock_code': row['stock_code'],
                'close': float(row['close'])
            })

        logger.info(f"获取了 {len(data_list)} 条原始数据")

        if not data_list:
            logger.warning("未获取到任何K线数据")
            return pd.DataFrame()

        # 转换为DataFrame并透视
        df = pd.DataFrame(data_list)
        df = df.pivot(index='date', columns='stock_code', values='close')

        logger.info(f"DataFrame形状: {df.shape} (日期数 x 股票数)")

        # 计算日收益率
        returns = df.pct_change(fill_method=None)

        # 删除第一行（全为NaN）
        returns = returns.iloc[1:]

        # 删除全为NaN的列（股票）
        returns = returns.dropna(axis=1, how='all')

        logger.info(f"获取了 {len(returns.columns)} 只股票，{len(returns)} 个交易日的收益率数据")

        return returns

    def train(self,
              window_size: int = 5,
              epochs: int = 10,
              min_count: int = 10,
              workers: int = 4,
              days: int = 500):
        """
        训练股票向量

        Args:
            window_size: 上下文窗口大小
            epochs: 训练轮数
            min_count: 最小出现次数
            workers: 并行线程数
            days: 使用最近N天的数据
        """
        logger.info("=" * 60)
        logger.info("开始训练Stock2Vec模型")
        logger.info("=" * 60)
        logger.info(f"参数: embedding_dim={self.embedding_dim}, window_size={window_size}, epochs={epochs}")

        # 1. 获取日收益率数据
        returns = self._get_daily_returns(days=days)

        if returns.empty:
            logger.error("没有可用的收益率数据")
            return False

        # 2. 构建训练句子（每天按涨跌幅排序的股票序列）
        sentences = []

        for date in returns.index:
            # 获取当日所有股票的收益率
            day_returns = returns.loc[date].dropna()

            if len(day_returns) < 10:  # 至少需要10只股票
                continue

            # 按收益率排序
            sorted_stocks = day_returns.sort_values().index.tolist()
            sentences.append(sorted_stocks)

        logger.info(f"构建了 {len(sentences)} 个训练句子")

        # 3. 使用gensim Word2Vec训练
        try:
            from gensim.models import Word2Vec

            logger.info("开始训练Word2Vec模型...")

            self.model = Word2Vec(
                sentences=sentences,
                vector_size=self.embedding_dim,
                window=window_size,
                min_count=min_count,
                workers=workers,
                epochs=epochs,
                sg=1,  # Skip-gram
                negative=5,
                seed=42
            )

            logger.info("模型训练完成")

            # 4. 保存向量
            for stock in self.model.wv.key_to_index:
                self.embeddings[stock] = self.model.wv[stock].tolist()

            logger.info(f"生成了 {len(self.embeddings)} 只股票的向量")

            return True

        except ImportError:
            logger.error("需要安装gensim库: pip install gensim")
            return False

        except Exception as e:
            logger.error(f"训练失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def get_similar(self, stock_code: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """
        获取相似股票

        Args:
            stock_code: 股票代码
            top_k: 返回数量

        Returns:
            [(stock_code, similarity), ...]
        """
        if stock_code not in self.embeddings:
            logger.warning(f"{stock_code} 不在训练集中")
            return []

        query_vec = np.array(self.embeddings[stock_code])
        similarities = []

        for code, vec in self.embeddings.items():
            if code != stock_code:
                sim = self._cosine_similarity(query_vec, np.array(vec))
                similarities.append((code, float(sim)))

        # 排序并返回top_k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算余弦相似度"""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def save_to_db(self, model_version: str = "v1.0"):
        """
        保存向量到数据库

        Args:
            model_version: 模型版本
        """
        if not self.embeddings:
            logger.warning("没有可保存的向量")
            return False

        cursor = self.conn.cursor()

        # 清空旧数据
        cursor.execute("DELETE FROM stock_embeddings")

        # 插入新数据
        for stock_code, embedding in self.embeddings.items():
            embedding_bytes = np.array(embedding, dtype=np.float32).tobytes()

            cursor.execute("""
                INSERT INTO stock_embeddings (stock_code, embedding, model_version)
                VALUES (?, ?, ?)
            """, (stock_code, embedding_bytes, model_version))

        self.conn.commit()
        logger.info(f"已保存 {len(self.embeddings)} 只股票的向量到数据库")

        return True

    def load_from_db(self) -> bool:
        """从数据库加载向量"""
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT stock_code, embedding, model_version
            FROM stock_embeddings
        """)

        self.embeddings = {}
        model_version = None

        for row in cursor.fetchall():
            stock_code = row['stock_code']
            embedding_bytes = row['embedding']
            model_version = row['model_version']

            # 解析向量
            embedding = np.frombuffer(embedding_bytes, dtype=np.float32).tolist()
            self.embeddings[stock_code] = embedding

        if self.embeddings:
            logger.info(f"从数据库加载了 {len(self.embeddings)} 只股票的向量 (版本: {model_version})")
            return True
        else:
            logger.warning("数据库中没有股票向量")
            return False

    def save_model(self, filepath: str):
        """
        保存模型到文件

        Args:
            filepath: 文件路径
        """
        if self.model is None:
            logger.warning("没有可保存的模型")
            return False

        try:
            self.model.save(filepath)
            logger.info(f"模型已保存到: {filepath}")
            return True
        except Exception as e:
            logger.error(f"保存模型失败: {e}")
            return False

    def load_model(self, filepath: str):
        """
        从文件加载模型

        Args:
            filepath: 文件路径
        """
        try:
            from gensim.models import Word2Vec

            self.model = Word2Vec.load(filepath)

            # 提取向量
            self.embeddings = {}
            for stock in self.model.wv.key_to_index:
                self.embeddings[stock] = self.model.wv[stock].tolist()

            logger.info(f"从文件加载了模型: {filepath}")
            logger.info(f"包含 {len(self.embeddings)} 只股票的向量")
            return True

        except Exception as e:
            logger.error(f"加载模型失败: {e}")
            return False

    def get_stock_info(self, stock_code: str) -> Optional[Dict]:
        """
        获取股票基本信息

        Args:
            stock_code: 股票代码

        Returns:
            股票信息字典
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT stock_code, stock_name, sector, industry
            FROM stocks
            WHERE stock_code = ?
        """, (stock_code,))

        row = cursor.fetchone()
        if row:
            return {
                'stock_code': row['stock_code'],
                'stock_name': row['stock_name'],
                'sector': row['sector'],
                'industry': row['industry']
            }
        return None

