"""
HNSW向量存储
使用hnswlib实现高性能向量检索
"""
import os
import pickle
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import logging

try:
    import hnswlib
    HNSWLIB_AVAILABLE = True
except ImportError:
    HNSWLIB_AVAILABLE = False
    logging.warning("hnswlib not installed. Install with: pip install hnswlib")

from .sqlite_vector_store import (
    SQLiteVectorStore,
    StockDocument,
    SearchResult
)

logger = logging.getLogger(__name__)


class HNSWVectorStore(SQLiteVectorStore):
    """
    HNSW向量存储

    在SQLite基础上增加HNSW索引，大幅提升检索性能

    特点：
    1. 继承SQLite存储的所有功能
    2. 使用HNSW索引加速向量检索
    3. 支持增量索引更新
    4. 自动持久化索引

    性能：
    - 暴力搜索: O(n) 线性时间
    - HNSW搜索: O(log n) 对数时间
    - 100万向量检索: 从秒级降至毫秒级
    """

    def __init__(self,
                 db_path: str = "stock_vectors.db",
                 index_path: Optional[str] = None,
                 dim: int = 768,
                 max_elements: int = 1000000,
                 ef_construction: int = 200,
                 M: int = 16):
        """
        初始化HNSW向量存储

        Args:
            db_path: SQLite数据库路径
            index_path: HNSW索引文件路径
            dim: 向量维度
            max_elements: 最大元素数量
            ef_construction: 构建时的ef参数（越大越精确但越慢）
            M: HNSW的M参数（连接数，越大越精确但占用更多内存）
        """
        super().__init__(db_path)

        if not HNSWLIB_AVAILABLE:
            raise ImportError(
                "hnswlib is required for HNSWVectorStore. "
                "Install with: pip install hnswlib"
            )

        self.dim = dim
        self.max_elements = max_elements
        self.index_path = index_path or db_path.replace(".db", "_hnsw.bin")
        self.id_mapping_path = self.index_path.replace(".bin", "_mapping.pkl")

        # 初始化HNSW索引
        self.index = hnswlib.Index(space='cosine', dim=dim)
        self.doc_id_to_index = {}  # 文档ID到HNSW索引的映射
        self.index_to_doc_id = {}  # HNSW索引到文档ID的映射
        self.next_index_id = 0

        # 加载或创建索引
        if os.path.exists(self.index_path):
            self._load_index()
        else:
            self._create_index(ef_construction, M)

    def _create_index(self, ef_construction: int, M: int):
        """创建新索引"""
        self.index.init_index(
            max_elements=self.max_elements,
            ef_construction=ef_construction,
            M=M
        )
        self.index.set_ef(50)  # 查询时的ef参数
        logger.info(f"创建HNSW索引: dim={self.dim}, M={M}, ef_construction={ef_construction}")

    def _load_index(self):
        """加载已有索引"""
        try:
            self.index.load_index(self.index_path, max_elements=self.max_elements)

            # 加载ID映射
            if os.path.exists(self.id_mapping_path):
                with open(self.id_mapping_path, 'rb') as f:
                    mapping_data = pickle.load(f)
                    self.doc_id_to_index = mapping_data['doc_id_to_index']
                    self.index_to_doc_id = mapping_data['index_to_doc_id']
                    self.next_index_id = mapping_data['next_index_id']

            logger.info(f"加载HNSW索引: {len(self.doc_id_to_index)} 个向量")
        except Exception as e:
            logger.error(f"加载索引失败: {e}")
            # 重新创建索引
            self._create_index(200, 16)

    def _save_index(self):
        """保存索引到磁盘"""
        try:
            self.index.save_index(self.index_path)

            # 保存ID映射
            mapping_data = {
                'doc_id_to_index': self.doc_id_to_index,
                'index_to_doc_id': self.index_to_doc_id,
                'next_index_id': self.next_index_id
            }
            with open(self.id_mapping_path, 'wb') as f:
                pickle.dump(mapping_data, f)

            logger.info(f"保存HNSW索引: {len(self.doc_id_to_index)} 个向量")
        except Exception as e:
            logger.error(f"保存索引失败: {e}")

    def add_document(self, doc: StockDocument, embedding: List[float]) -> int:
        """
        添加文档（重写以更新HNSW索引）

        Args:
            doc: 文档对象
            embedding: 向量

        Returns:
            文档ID
        """
        # 调用父类方法添加到SQLite
        doc_id = super().add_document(doc, embedding)

        # 添加到HNSW索引
        try:
            embedding_array = np.array(embedding, dtype=np.float32)
            self.index.add_items(embedding_array, self.next_index_id)

            # 更新映射
            self.doc_id_to_index[doc_id] = self.next_index_id
            self.index_to_doc_id[self.next_index_id] = doc_id
            self.next_index_id += 1

            # 更频繁的持久化策略：每10个文档保存一次映射
            if self.next_index_id % 10 == 0:
                self._save_index()

        except Exception as e:
            logger.error(f"添加向量到HNSW索引失败: {e}")
            # 发生错误时也尝试保存当前状态
            self._save_index()

        return doc_id

    def add_documents_batch(self, docs: List[Tuple[StockDocument, List[float]]]) -> List[int]:
        """
        批量添加文档（重写以更新HNSW索引）

        Args:
            docs: 文档和向量的列表

        Returns:
            文档ID列表
        """
        # 调用父类方法添加到SQLite
        doc_ids = super().add_documents_batch(docs)

        # 批量添加到HNSW索引
        try:
            embeddings = [np.array(emb, dtype=np.float32) for _, emb in docs]
            embeddings_array = np.vstack(embeddings)

            index_ids = list(range(self.next_index_id, self.next_index_id + len(docs)))
            self.index.add_items(embeddings_array, index_ids)

            # 更新映射
            for doc_id, index_id in zip(doc_ids, index_ids):
                self.doc_id_to_index[doc_id] = index_id
                self.index_to_doc_id[index_id] = doc_id

            self.next_index_id += len(docs)

            # 保存索引
            self._save_index()

        except Exception as e:
            logger.error(f"批量添加向量到HNSW索引失败: {e}")

        return doc_ids

    def search_by_vector(self, query_embedding: List[float],
                         top_k: int = 10,
                         filters: Optional[Dict] = None) -> List[SearchResult]:
        """
        向量相似度搜索（使用HNSW加速）

        Args:
            query_embedding: 查询向量
            top_k: 返回数量
            filters: 过滤条件

        Returns:
            搜索结果列表
        """
        if not self.doc_id_to_index:
            # 索引为空，使用父类的暴力搜索
            return super().search_by_vector(query_embedding, top_k, filters)

        try:
            # 使用HNSW搜索
            query_vec = np.array(query_embedding, dtype=np.float32)

            # 搜索更多结果以应用过滤器
            search_k = min(top_k * 10, len(self.doc_id_to_index))
            labels, distances = self.index.knn_query(query_vec, k=search_k)

            # 转换为文档ID
            doc_ids = [self.index_to_doc_id.get(int(label)) for label in labels[0]]
            doc_ids = [doc_id for doc_id in doc_ids if doc_id is not None]

            if not doc_ids:
                return []

            # 从SQLite获取文档详情
            conn = self._get_conn()
            cursor = conn.cursor()

            placeholders = ",".join("?" * len(doc_ids))
            where_clauses = [f"id IN ({placeholders})"]
            params = doc_ids

            # 应用过滤器
            if filters:
                if filters.get("stock_code"):
                    where_clauses.append("stock_code = ?")
                    params.append(filters["stock_code"])
                if filters.get("doc_type"):
                    where_clauses.append("doc_type = ?")
                    params.append(filters["doc_type"])
                if filters.get("date_from"):
                    where_clauses.append("date >= ?")
                    params.append(filters["date_from"])
                if filters.get("date_to"):
                    where_clauses.append("date <= ?")
                    params.append(filters["date_to"])

            where_sql = " AND ".join(where_clauses)

            cursor.execute(f"""
                SELECT id, stock_code, content, date, doc_type, importance
                FROM vector_documents
                WHERE {where_sql}
            """, params)

            # 构建结果
            doc_map = {row["id"]: row for row in cursor.fetchall()}
            results = []

            for doc_id, distance in zip(doc_ids, distances[0]):
                if doc_id in doc_map:
                    row = doc_map[doc_id]
                    # HNSW返回的是距离，转换为相似度
                    similarity = 1.0 - float(distance)

                    results.append(SearchResult(
                        doc_id=row["id"],
                        stock_code=row["stock_code"],
                        content=row["content"],
                        similarity=similarity,
                        date=row["date"],
                        doc_type=row["doc_type"],
                        importance=row["importance"]
                    ))

            # 按相似度排序并返回top_k
            results.sort(key=lambda x: x.similarity, reverse=True)
            return results[:top_k]

        except Exception as e:
            logger.error(f"HNSW搜索失败，回退到暴力搜索: {e}")
            return super().search_by_vector(query_embedding, top_k, filters)

    def rebuild_index(self, ef_construction: int = 200, M: int = 16):
        """
        重建HNSW索引

        当索引损坏或需要优化参数时使用

        Args:
            ef_construction: 构建时的ef参数
            M: HNSW的M参数
        """
        logger.info("开始重建HNSW索引...")

        # 重置索引
        self.index = hnswlib.Index(space='cosine', dim=self.dim)
        self._create_index(ef_construction, M)
        self.doc_id_to_index = {}
        self.index_to_doc_id = {}
        self.next_index_id = 0

        # 从SQLite加载所有向量
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, embedding
            FROM vector_documents
            WHERE embedding IS NOT NULL
            ORDER BY id
        """)

        batch_size = 1000
        batch_ids = []
        batch_embeddings = []

        for row in cursor.fetchall():
            doc_id = row["id"]
            embedding = np.frombuffer(row["embedding"], dtype=np.float32)

            batch_ids.append(doc_id)
            batch_embeddings.append(embedding)

            if len(batch_ids) >= batch_size:
                self._add_to_index_batch(batch_ids, batch_embeddings)
                batch_ids = []
                batch_embeddings = []

        # 处理剩余的
        if batch_ids:
            self._add_to_index_batch(batch_ids, batch_embeddings)

        # 保存索引
        self._save_index()
        logger.info(f"HNSW索引重建完成: {len(self.doc_id_to_index)} 个向量")

    def _add_to_index_batch(self, doc_ids: List[int], embeddings: List[np.ndarray]):
        """批量添加到索引（内部方法）"""
        embeddings_array = np.vstack(embeddings)
        index_ids = list(range(self.next_index_id, self.next_index_id + len(doc_ids)))

        self.index.add_items(embeddings_array, index_ids)

        for doc_id, index_id in zip(doc_ids, index_ids):
            self.doc_id_to_index[doc_id] = index_id
            self.index_to_doc_id[index_id] = doc_id

        self.next_index_id += len(doc_ids)

    def get_index_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        return {
            "total_vectors": len(self.doc_id_to_index),
            "index_size_mb": os.path.getsize(self.index_path) / (1024 * 1024) if os.path.exists(self.index_path) else 0,
            "dimension": self.dim,
            "max_elements": self.max_elements,
            "index_path": self.index_path
        }

    def close(self):
        """关闭连接并保存索引"""
        self._save_index()
        super().close()


# 全局单例
_hnsw_store_instance: Optional[HNSWVectorStore] = None


def get_hnsw_vector_store(db_path: str = "stock_vectors.db",
                           dim: int = 768) -> HNSWVectorStore:
    """获取HNSW向量存储单例"""
    global _hnsw_store_instance
    if _hnsw_store_instance is None:
        _hnsw_store_instance = HNSWVectorStore(db_path=db_path, dim=dim)
    return _hnsw_store_instance
