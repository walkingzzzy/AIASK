"""
向量存储迁移脚本
将现有的向量数据迁移到HNSW索引
"""
import numpy as np
import logging
from typing import List, Dict, Any, Optional
from tqdm import tqdm
import argparse

from packages.core.vector_store.index.hnsw_index import HNSWIndex, IndexConfig
from packages.core.vector_store.storage.hnsw_vector_store import HNSWVectorStore

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VectorStoreMigration:
    """向量存储迁移工具"""

    def __init__(
        self,
        source_path: str,
        target_path: str,
        dim: int = 768,
        batch_size: int = 1000
    ):
        """
        初始化迁移工具

        Args:
            source_path: 源数据路径
            target_path: 目标HNSW索引路径
            dim: 向量维度
            batch_size: 批处理大小
        """
        self.source_path = Path(source_path)
        self.target_path = Path(target_path)
        self.dim = dim
        self.batch_size = batch_size

    def migrate_from_numpy(self, vectors_file: str, ids_file: str, metadata_file: Optional[str] = None):
        """
        从numpy文件迁移

        Args:
            vectors_file: 向量数据文件 (.npy)
            ids_file: ID列表文件 (.npy 或 .txt)
            metadata_file: 元数据文件 (.json 或 .pkl)
        """
        logger.info("开始从numpy文件迁移...")

        # 加载数据
        logger.info(f"加载向量数据: {vectors_file}")
        vectors = np.load(vectors_file)
        logger.info(f"向量形状: {vectors.shape}")

        logger.info(f"加载ID数据: {ids_file}")
        if ids_file.endswith('.npy'):
            ids = np.load(ids_file).tolist()
        else:
            with open(ids_file, 'r') as f:
                ids = [line.strip() for line in f]

        # 加载元数据（如果有）
        metadata_list = None
        if metadata_file:
            logger.info(f"加载元数据: {metadata_file}")
            if metadata_file.endswith('.json'):
                import json
                with open(metadata_file, 'r') as f:
                    metadata_list = json.load(f)
            elif metadata_file.endswith('.pkl'):
                import pickle
                with open(metadata_file, 'rb') as f:
                    metadata_list = pickle.load(f)

        # 创建HNSW索引
        logger.info("创建HNSW索引...")
        config = IndexConfig(
            dim=vectors.shape[1],
            max_elements=len(vectors) + 10000,  # 预留空间
            ef_construction=200,
            M=16
        )
        index = HNSWIndex(config)

        # 批量添加数据
        logger.info("批量添加数据到索引...")
        total_batches = (len(vectors) + self.batch_size - 1) // self.batch_size

        for i in tqdm(range(0, len(vectors), self.batch_size), total=total_batches, desc="迁移进度"):
            end_idx = min(i + self.batch_size, len(vectors))
            batch_vectors = vectors[i:end_idx]
            batch_ids = ids[i:end_idx]
            batch_metadata = metadata_list[i:end_idx] if metadata_list else None

            index.add_items(batch_vectors, batch_ids, batch_metadata)

        # 保存索引
        logger.info(f"保存索引到: {self.target_path}")
        index.save(str(self.target_path))

        # 验证
        stats = index.get_stats()
        logger.info(f"迁移完成! 统计信息: {stats}")

        return index

    def migrate_from_chroma(self, collection_name: str):
        """
        从ChromaDB迁移

        Args:
            collection_name: ChromaDB集合名称
        """
        logger.info(f"开始从ChromaDB迁移集合: {collection_name}")

        try:
            import chromadb
        except ImportError:
            logger.error("需要安装chromadb: pip install chromadb")
            return None

        # 连接ChromaDB
        client = chromadb.PersistentClient(path=str(self.source_path))
        collection = client.get_collection(collection_name)

        # 获取所有数据
        logger.info("获取ChromaDB数据...")
        results = collection.get(include=['embeddings', 'metadatas', 'documents'])

        vectors = np.array(results['embeddings'])
        ids = results['ids']
        metadata_list = results['metadatas']

        logger.info(f"获取到 {len(ids)} 条数据")

        # 创建HNSW索引
        config = IndexConfig(
            dim=vectors.shape[1],
            max_elements=len(vectors) + 10000,
            ef_construction=200,
            M=16
        )
        index = HNSWIndex(config)

        # 批量添加
        logger.info("批量添加数据到索引...")
        total_batches = (len(vectors) + self.batch_size - 1) // self.batch_size

        for i in tqdm(range(0, len(vectors), self.batch_size), total=total_batches):
            end_idx = min(i + self.batch_size, len(vectors))
            batch_vectors = vectors[i:end_idx]
            batch_ids = ids[i:end_idx]
            batch_metadata = metadata_list[i:end_idx] if metadata_list else None

            index.add_items(batch_vectors, batch_ids, batch_metadata)

        # 保存
        logger.info(f"保存索引到: {self.target_path}")
        index.save(str(self.target_path))

        stats = index.get_stats()
        logger.info(f"迁移完成! 统计信息: {stats}")

        return index

    def verify_migration(self, original_vectors: np.ndarray, original_ids: List[str]):
        """
        验证迁移结果

        Args:
            original_vectors: 原始向量
            original_ids: 原始ID列表
        """
        logger.info("验证迁移结果...")

        # 加载迁移后的索引
        index = HNSWIndex.load(str(self.target_path))

        # 随机抽样验证
        sample_size = min(100, len(original_ids))
        sample_indices = np.random.choice(len(original_ids), sample_size, replace=False)

        correct_count = 0
        for idx in tqdm(sample_indices, desc="验证进度"):
            query_vector = original_vectors[idx]
            expected_id = original_ids[idx]

            # 搜索最相似的向量
            result_ids, distances = index.search(query_vector, k=1)

            if result_ids and result_ids[0] == expected_id:
                correct_count += 1

        accuracy = correct_count / sample_size * 100
        logger.info(f"验证完成! 准确率: {accuracy:.2f}% ({correct_count}/{sample_size})")

        return accuracy


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='向量存储迁移工具')
    parser.add_argument('--source', required=True, help='源数据路径')
    parser.add_argument('--target', required=True, help='目标索引路径')
    parser.add_argument('--type', choices=['numpy', 'chroma'], default='numpy', help='源数据类型')
    parser.add_argument('--vectors', help='向量文件路径 (numpy模式)')
    parser.add_argument('--ids', help='ID文件路径 (numpy模式)')
    parser.add_argument('--metadata', help='元数据文件路径 (可选)')
    parser.add_argument('--collection', help='集合名称 (chroma模式)')
    parser.add_argument('--dim', type=int, default=768, help='向量维度')
    parser.add_argument('--batch-size', type=int, default=1000, help='批处理大小')
    parser.add_argument('--verify', action='store_true', help='验证迁移结果')

    args = parser.parse_args()

    # 创建迁移工具
    migration = VectorStoreMigration(
        source_path=args.source,
        target_path=args.target,
        dim=args.dim,
        batch_size=args.batch_size
    )

    # 执行迁移
    if args.type == 'numpy':
        if not args.vectors or not args.ids:
            logger.error("numpy模式需要指定 --vectors 和 --ids 参数")
            return

        index = migration.migrate_from_numpy(
            vectors_file=args.vectors,
            ids_file=args.ids,
            metadata_file=args.metadata
        )

        # 验证
        if args.verify and index:
            vectors = np.load(args.vectors)
            if args.ids.endswith('.npy'):
                ids = np.load(args.ids).tolist()
            else:
                with open(args.ids, 'r') as f:
                    ids = [line.strip() for line in f]
            migration.verify_migration(vectors, ids)

    elif args.type == 'chroma':
        if not args.collection:
            logger.error("chroma模式需要指定 --collection 参数")
            return

        migration.migrate_from_chroma(collection_name=args.collection)

    logger.info("迁移任务完成!")


if __name__ == '__main__':
    main()
