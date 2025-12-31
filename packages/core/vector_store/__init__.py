"""
向量知识库模块
提供股票数据的向量化存储和检索功能
"""
from .embeddings.embedding_models import (
    BaseEmbedding,
    OpenAIEmbedding,
    get_embedding_model,
)
from .storage.sqlite_vector_store import (
    SQLiteVectorStore,
    StockDocument,
    get_vector_store,
)
from .retrieval.retriever import (
    StockRetriever,
    RetrievalResult,
    get_retriever,
)
from .indexer.stock_indexer import (
    StockDataIndexer,
    IndexStats,
    get_stock_indexer,
)

__all__ = [
    # Embeddings
    "BaseEmbedding",
    "OpenAIEmbedding",
    "get_embedding_model",
    # Storage
    "SQLiteVectorStore",
    "StockDocument",
    "get_vector_store",
    # Retrieval
    "StockRetriever",
    "RetrievalResult",
    "get_retriever",
    # Indexer
    "StockDataIndexer",
    "IndexStats",
    "get_stock_indexer",
]
