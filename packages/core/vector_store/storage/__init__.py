"""向量存储"""
from .sqlite_vector_store import SQLiteVectorStore, StockDocument, get_vector_store

try:
    from .hnsw_vector_store import HNSWVectorStore, get_hnsw_vector_store
    __all__ = [
        "SQLiteVectorStore",
        "StockDocument",
        "get_vector_store",
        "HNSWVectorStore",
        "get_hnsw_vector_store"
    ]
except ImportError:
    # hnswlib未安装时只导出SQLite版本
    __all__ = ["SQLiteVectorStore", "StockDocument", "get_vector_store"]
