"""
股票知识检索器
提供基于向量的智能检索功能
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

from ..storage.sqlite_vector_store import (
    SQLiteVectorStore, 
    SearchResult, 
    get_vector_store
)
from ..embeddings.embedding_models import get_embedding_model

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """检索结果"""
    query: str
    results: List[Dict[str, Any]]
    total_found: int
    search_type: str  # vector, text, hybrid
    
    def to_dict(self) -> Dict:
        return {
            "query": self.query,
            "results": self.results,
            "total_found": self.total_found,
            "search_type": self.search_type
        }


class StockRetriever:
    """
    股票知识检索器
    
    支持：
    1. 向量语义检索
    2. 全文关键词检索
    3. 混合检索（推荐）
    4. 股票特定检索
    """
    
    def __init__(self, db_path: str = "data/stock_vectors.db"):
        self.store = get_vector_store(db_path)
        self.embedding_model = None
        self._init_embedding()
    
    def _init_embedding(self):
        """初始化向量模型"""
        try:
            self.embedding_model = get_embedding_model()
            logger.info("向量模型初始化成功")
        except Exception as e:
            logger.warning(f"向量模型初始化失败，将使用全文检索: {e}")
    
    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        search_type: str = "hybrid",
        filters: Optional[Dict] = None
    ) -> RetrievalResult:
        """
        检索相关文档
        
        Args:
            query: 查询文本
            top_k: 返回数量
            search_type: 检索类型 (vector/text/hybrid)
            filters: 过滤条件
            
        Returns:
            检索结果
        """
        results = []
        
        if search_type == "vector" and self.embedding_model:
            results = self._vector_search(query, top_k, filters)
        elif search_type == "text":
            results = self._text_search(query, top_k, filters)
        elif search_type == "hybrid" and self.embedding_model:
            results = self._hybrid_search(query, top_k, filters)
        else:
            # 降级到全文搜索
            results = self._text_search(query, top_k, filters)
            search_type = "text"
        
        return RetrievalResult(
            query=query,
            results=[self._format_result(r) for r in results],
            total_found=len(results),
            search_type=search_type
        )
    
    def retrieve_for_stock(
        self,
        stock_code: str,
        query: Optional[str] = None,
        doc_types: Optional[List[str]] = None,
        top_k: int = 10
    ) -> RetrievalResult:
        """
        检索特定股票的相关文档
        
        Args:
            stock_code: 股票代码
            query: 可选的查询文本
            doc_types: 文档类型过滤
            top_k: 返回数量
        """
        filters = {"stock_code": stock_code}
        if doc_types:
            filters["doc_type"] = doc_types[0]  # 简化处理
        
        if query:
            return self.retrieve(query, top_k, "hybrid", filters)
        
        # 无查询时返回最新文档
        results = self.store.search_by_text(
            stock_code, top_k, filters
        )
        
        return RetrievalResult(
            query=f"stock:{stock_code}",
            results=[self._format_result(r) for r in results],
            total_found=len(results),
            search_type="stock_filter"
        )
    
    def retrieve_similar_stocks(
        self,
        stock_code: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        检索相似股票
        
        基于股票的向量表示找到相似股票
        """
        # 获取该股票的文档
        stock_docs = self.store.search_by_text(
            stock_code, 1, {"stock_code": stock_code}
        )
        
        if not stock_docs:
            return []
        
        # 使用该股票的内容作为查询
        query = stock_docs[0].content[:500]
        
        if self.embedding_model:
            embedding = self.embedding_model.embed(query)
            results = self.store.search_by_vector(
                embedding, top_k * 3, None
            )
        else:
            results = self.store.search_by_text(query, top_k * 3)
        
        # 去重并排除自身
        seen_stocks = {stock_code}
        similar = []
        
        for r in results:
            if r.stock_code not in seen_stocks:
                seen_stocks.add(r.stock_code)
                similar.append({
                    "stock_code": r.stock_code,
                    "similarity": r.similarity,
                    "reason": r.content[:100]
                })
                if len(similar) >= top_k:
                    break
        
        return similar
    
    def answer_question(
        self,
        question: str,
        stock_code: Optional[str] = None,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        回答股票相关问题
        
        检索相关文档并生成答案上下文
        """
        filters = {"stock_code": stock_code} if stock_code else None
        
        retrieval = self.retrieve(question, top_k, "hybrid", filters)
        
        # 构建上下文
        context_parts = []
        sources = []
        
        for result in retrieval.results:
            context_parts.append(result["content"])
            sources.append({
                "stock_code": result["stock_code"],
                "doc_type": result["doc_type"],
                "date": result["date"],
                "relevance": result["similarity"]
            })
        
        return {
            "question": question,
            "context": "\n\n".join(context_parts),
            "sources": sources,
            "total_sources": retrieval.total_found
        }
    
    def _vector_search(
        self, 
        query: str, 
        top_k: int,
        filters: Optional[Dict]
    ) -> List[SearchResult]:
        """向量搜索"""
        embedding = self.embedding_model.embed(query)
        return self.store.search_by_vector(embedding, top_k, filters)
    
    def _text_search(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict]
    ) -> List[SearchResult]:
        """全文搜索"""
        return self.store.search_by_text(query, top_k, filters)
    
    def _hybrid_search(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict]
    ) -> List[SearchResult]:
        """混合搜索"""
        embedding = self.embedding_model.embed(query)
        return self.store.hybrid_search(
            query, embedding, top_k, 
            vector_weight=0.7, filters=filters
        )
    
    def _format_result(self, result: SearchResult) -> Dict[str, Any]:
        """格式化搜索结果"""
        return {
            "doc_id": result.doc_id,
            "stock_code": result.stock_code,
            "content": result.content,
            "similarity": round(result.similarity, 4),
            "date": result.date,
            "doc_type": result.doc_type,
            "importance": result.importance
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取检索器统计信息"""
        total = self.store.get_document_count()
        
        stats = {
            "total_documents": total,
            "embedding_available": self.embedding_model is not None,
            "doc_types": {}
        }
        
        for doc_type in ["financial_report", "news", "research", "quote_summary"]:
            count = self.store.get_document_count({"doc_type": doc_type})
            stats["doc_types"][doc_type] = count
        
        return stats


# 全局单例
_retriever_instance: Optional[StockRetriever] = None


def get_retriever(db_path: str = "data/stock_vectors.db") -> StockRetriever:
    """获取检索器单例"""
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = StockRetriever(db_path)
    return _retriever_instance
