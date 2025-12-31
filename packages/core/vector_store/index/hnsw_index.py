"""
HNSW索引管理模块
提供HNSW索引的创建、更新、查询和持久化功能
"""
import numpy as np
import hnswlib
from typing import List, Tuple, Optional, Dict, Any
from pathlib import Path
import pickle
import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class IndexConfig:
    """HNSW索引配置"""
    dim: int  # 向量维度
    max_elements: int = 10000  # 最大元素数量
    ef_construction: int = 200  # 构建时的ef参数
    M: int = 16  # 每个节点的最大连接数
    ef_search: int = 50  # 搜索时的ef参数
    space: str = 'cosine'  # 距离度量: 'cosine', 'l2', 'ip'


class HNSWIndex:
    """
    HNSW索引管理类

    提供高效的向量相似度搜索功能
    """

    def __init__(self, config: IndexConfig):
        """
        初始化HNSW索引

        Args:
            config: 索引配置
        """
        self.config = config
        self.index = None
        self.id_mapping: Dict[int, str] = {}  # 内部ID到外部ID的映射
        self.reverse_mapping: Dict[str, int] = {}  # 外部ID到内部ID的映射
        self.metadata: Dict[str, Any] = {}  # 元数据存储
        self.current_count = 0
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

        self._initialize_index()

    def _initialize_index(self):
        """初始化hnswlib索引"""
        self.index = hnswlib.Index(space=self.config.space, dim=self.config.dim)
        self.index.init_index(
            max_elements=self.config.max_elements,
            ef_construction=self.config.ef_construction,
            M=self.config.M
        )
        self.index.set_ef(self.config.ef_search)
        logger.info(f"HNSW索引初始化完成: dim={self.config.dim}, space={self.config.space}")

    def add_items(
        self,
        vectors: np.ndarray,
        ids: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        添加向量到索引

        Args:
            vectors: 向量数组 (n, dim)
            ids: 外部ID列表
            metadata: 元数据列表（可选）
        """
        if len(vectors) != len(ids):
            raise ValueError("向量数量和ID数量不匹配")

        if vectors.shape[1] != self.config.dim:
            raise ValueError(f"向量维度不匹配: 期望{self.config.dim}, 实际{vectors.shape[1]}")

        # 检查容量
        if self.current_count + len(vectors) > self.config.max_elements:
            self._resize_index(self.current_count + len(vectors))

        # 生成内部ID
        internal_ids = list(range(self.current_count, self.current_count + len(vectors)))

        # 更新映射
        for internal_id, external_id in zip(internal_ids, ids):
            self.id_mapping[internal_id] = external_id
            self.reverse_mapping[external_id] = internal_id

            # 存储元数据
            if metadata and len(metadata) > internal_id - self.current_count:
                self.metadata[external_id] = metadata[internal_id - self.current_count]

        # 添加到索引
        self.index.add_items(vectors, internal_ids)
        self.current_count += len(vectors)
        self.updated_at = datetime.now()

        logger.info(f"添加{len(vectors)}个向量到索引, 当前总数: {self.current_count}")

    def search(
        self,
        query_vector: np.ndarray,
        k: int = 10,
        filter_func: Optional[callable] = None
    ) -> Tuple[List[str], List[float]]:
        """
        搜索最相似的向量

        Args:
            query_vector: 查询向量 (dim,)
            k: 返回结果数量
            filter_func: 过滤函数，接收external_id和metadata，返回bool

        Returns:
            (ids, distances): 外部ID列表和距离列表
        """
        if query_vector.shape[0] != self.config.dim:
            raise ValueError(f"查询向量维度不匹配: 期望{self.config.dim}, 实际{query_vector.shape[0]}")

        if self.current_count == 0:
            return [], []

        # 搜索更多结果以便过滤
        search_k = min(k * 3 if filter_func else k, self.current_count)

        # 执行搜索
        internal_ids, distances = self.index.knn_query(
            query_vector.reshape(1, -1),
            k=search_k
        )

        # 转换为外部ID
        results_ids = []
        results_distances = []

        for internal_id, distance in zip(internal_ids[0], distances[0]):
            external_id = self.id_mapping.get(internal_id)
            if external_id is None:
                continue

            # 应用过滤器
            if filter_func:
                metadata = self.metadata.get(external_id, {})
                if not filter_func(external_id, metadata):
                    continue

            results_ids.append(external_id)
            results_distances.append(float(distance))

            if len(results_ids) >= k:
                break

        return results_ids, results_distances

    def batch_search(
        self,
        query_vectors: np.ndarray,
        k: int = 10
    ) -> Tuple[List[List[str]], List[List[float]]]:
        """
        批量搜索

        Args:
            query_vectors: 查询向量数组 (n, dim)
            k: 每个查询返回的结果数量

        Returns:
            (ids_list, distances_list): ID列表的列表和距离列表的列表
        """
        if query_vectors.shape[1] != self.config.dim:
            raise ValueError(f"查询向量维度不匹配")

        if self.current_count == 0:
            return [[] for _ in range(len(query_vectors))], [[] for _ in range(len(query_vectors))]

        # 批量搜索
        internal_ids_batch, distances_batch = self.index.knn_query(query_vectors, k=k)

        # 转换结果
        results_ids = []
        results_distances = []

        for internal_ids, distances in zip(internal_ids_batch, distances_batch):
            ids = [self.id_mapping.get(iid, "") for iid in internal_ids]
            results_ids.append(ids)
            results_distances.append([float(d) for d in distances])

        return results_ids, results_distances

    def delete_items(self, ids: List[str]) -> int:
        """删除向量（标记删除）"""
        deleted_count = 0
        for external_id in ids:
            internal_id = self.reverse_mapping.get(external_id)
            if internal_id is not None:
                del self.id_mapping[internal_id]
                del self.reverse_mapping[external_id]
                if external_id in self.metadata:
                    del self.metadata[external_id]
                self.index.mark_deleted(internal_id)
                deleted_count += 1
        self.updated_at = datetime.now()
        logger.info(f"删除{deleted_count}个向量")
        return deleted_count

    def save(self, path: str):
        """保存索引到文件"""
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        index_path = str(path_obj) + ".index"
        self.index.save_index(index_path)
        metadata_path = str(path_obj) + ".meta"
        with open(metadata_path, 'wb') as f:
            pickle.dump({
                'config': self.config,
                'id_mapping': self.id_mapping,
                'reverse_mapping': self.reverse_mapping,
                'metadata': self.metadata,
                'current_count': self.current_count,
                'created_at': self.created_at,
                'updated_at': self.updated_at
            }, f)
        logger.info(f"索引已保存到: {path}")

    @classmethod
    def load(cls, path: str) -> 'HNSWIndex':
        """从文件加载索引"""
        path_obj = Path(path)
        metadata_path = str(path_obj) + ".meta"
        with open(metadata_path, 'rb') as f:
            data = pickle.load(f)
        instance = cls(data['config'])
        instance.id_mapping = data['id_mapping']
        instance.reverse_mapping = data['reverse_mapping']
        instance.metadata = data['metadata']
        instance.current_count = data['current_count']
        instance.created_at = data['created_at']
        instance.updated_at = data['updated_at']
        index_path = str(path_obj) + ".index"
        instance.index.load_index(index_path, max_elements=instance.config.max_elements)
        instance.index.set_ef(instance.config.ef_search)
        logger.info(f"索引已加载: {path}, 元素数量: {instance.current_count}")
        return instance

    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        return {
            'dim': self.config.dim,
            'max_elements': self.config.max_elements,
            'current_count': self.current_count,
            'space': self.config.space,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
