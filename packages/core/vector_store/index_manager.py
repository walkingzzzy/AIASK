"""
HNSW索引管理工具

提供索引构建、重建、统计等功能
"""
import argparse
import logging
from pathlib import Path

from packages.core.vector_store.storage.hnsw_vector_store import (
    HNSWVectorStore,
    get_hnsw_vector_store
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def build_index(db_path: str, dim: int = 768, ef_construction: int = 200, M: int = 16):
    """构建HNSW索引"""
    logger.info(f"开始构建HNSW索引: {db_path}")

    store = HNSWVectorStore(
        db_path=db_path,
        dim=dim,
        ef_construction=ef_construction,
        M=M
    )

    # 重建索引
    store.rebuild_index(ef_construction=ef_construction, M=M)

    # 显示统计信息
    stats = store.get_index_stats()
    logger.info(f"索引构建完成:")
    logger.info(f"  - 向量数量: {stats['total_vectors']}")
    logger.info(f"  - 索引大小: {stats['index_size_mb']:.2f} MB")
    logger.info(f"  - 向量维度: {stats['dimension']}")
    logger.info(f"  - 索引路径: {stats['index_path']}")

    store.close()


def show_stats(db_path: str, dim: int = 768):
    """显示索引统计信息"""
    try:
        store = get_hnsw_vector_store(db_path=db_path, dim=dim)
        stats = store.get_index_stats()

        print("\n=== HNSW索引统计 ===")
        print(f"向量数量: {stats['total_vectors']}")
        print(f"索引大小: {stats['index_size_mb']:.2f} MB")
        print(f"向量维度: {stats['dimension']}")
        print(f"最大容量: {stats['max_elements']}")
        print(f"索引路径: {stats['index_path']}")

        # 文档统计
        doc_count = store.get_document_count()
        print(f"\n文档总数: {doc_count}")

        store.close()

    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")


def benchmark(db_path: str, dim: int = 768, queries: int = 100):
    """性能基准测试"""
    import time
    import numpy as np

    logger.info(f"开始性能测试: {queries} 次查询")

    store = get_hnsw_vector_store(db_path=db_path, dim=dim)

    # 生成随机查询向量
    query_vectors = [np.random.randn(dim).tolist() for _ in range(queries)]

    # 测试HNSW搜索
    start_time = time.time()
    for query_vec in query_vectors:
        store.search_by_vector(query_vec, top_k=10)
    hnsw_time = time.time() - start_time

    avg_time_ms = (hnsw_time / queries) * 1000

    print("\n=== 性能测试结果 ===")
    print(f"查询次数: {queries}")
    print(f"总耗时: {hnsw_time:.2f} 秒")
    print(f"平均延迟: {avg_time_ms:.2f} ms/query")
    print(f"QPS: {queries / hnsw_time:.2f}")

    store.close()


def main():
    parser = argparse.ArgumentParser(description="HNSW索引管理工具")
    parser.add_argument("command", choices=["build", "stats", "benchmark"],
                        help="命令: build(构建索引), stats(统计信息), benchmark(性能测试)")
    parser.add_argument("--db", default="stock_vectors.db",
                        help="数据库路径 (默认: stock_vectors.db)")
    parser.add_argument("--dim", type=int, default=768,
                        help="向量维度 (默认: 768)")
    parser.add_argument("--ef-construction", type=int, default=200,
                        help="HNSW ef_construction参数 (默认: 200)")
    parser.add_argument("--M", type=int, default=16,
                        help="HNSW M参数 (默认: 16)")
    parser.add_argument("--queries", type=int, default=100,
                        help="基准测试查询次数 (默认: 100)")

    args = parser.parse_args()

    if args.command == "build":
        build_index(args.db, args.dim, args.ef_construction, args.M)
    elif args.command == "stats":
        show_stats(args.db, args.dim)
    elif args.command == "benchmark":
        benchmark(args.db, args.dim, args.queries)


if __name__ == "__main__":
    main()
