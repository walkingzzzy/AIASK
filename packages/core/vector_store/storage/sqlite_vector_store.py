"""
SQLite向量存储
轻量级向量数据库实现，无外部依赖
"""
import sqlite3
import json
import os
import threading
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import numpy as np
import logging

logger = logging.getLogger(__name__)

# 常量定义
MAX_BATCH_SIZE = 10000  # 向量搜索单次最大文档数


@dataclass
class StockDocument:
    """股票向量化文档"""
    stock_code: str
    doc_type: str  # financial_report, news, research, quote_summary
    content: str
    date: str
    period: str = "daily"  # daily, weekly, monthly, quarterly
    source: str = "system"
    importance: float = 0.5
    metadata: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SearchResult:
    """搜索结果"""
    doc_id: int
    stock_code: str
    content: str
    similarity: float
    date: str
    doc_type: str
    importance: float


class SQLiteVectorStore:
    """
    SQLite向量存储
    
    特点：
    1. 零外部依赖，使用纯SQLite
    2. 支持向量相似度搜索
    3. 支持全文搜索（FTS5）
    4. 支持元数据过滤
    """
    
    def __init__(self, db_path: str = "stock_vectors.db"):
        self.db_path = db_path
        self.conn = None
        self._lock = threading.Lock()  # 线程锁保护数据库操作
        self._init_db()
    
    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
        return self.conn
    
    def _init_db(self):
        """初始化数据库表"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # 股票基础信息表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_code TEXT UNIQUE NOT NULL,
                stock_name TEXT,
                market TEXT,
                sector TEXT,
                list_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 向量文档表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vector_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_code TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding BLOB,
                date TEXT,
                period TEXT DEFAULT 'daily',
                source TEXT DEFAULT 'system',
                importance REAL DEFAULT 0.5,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_doc_stock 
            ON vector_documents(stock_code)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_doc_type 
            ON vector_documents(doc_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_doc_date 
            ON vector_documents(date)
        """)
        
        # FTS5全文搜索表
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                content,
                stock_code,
                doc_type,
                content='vector_documents',
                content_rowid='id'
            )
        """)
        
        # 创建触发器保持FTS同步
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS vector_documents_ai 
            AFTER INSERT ON vector_documents BEGIN
                INSERT INTO documents_fts(rowid, content, stock_code, doc_type)
                VALUES (new.id, new.content, new.stock_code, new.doc_type);
            END
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS vector_documents_ad 
            AFTER DELETE ON vector_documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, content, stock_code, doc_type)
                VALUES ('delete', old.id, old.content, old.stock_code, old.doc_type);
            END
        """)
        
        conn.commit()
        logger.info(f"向量数据库初始化完成: {self.db_path}")
    
    def add_document(self, doc: StockDocument,
                     embedding: List[float]) -> int:
        """
        添加文档
        
        Args:
            doc: 文档对象
            embedding: 向量
            
        Returns:
            文档ID
        """
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            # 序列化向量
            embedding_blob = np.array(embedding, dtype=np.float32).tobytes()
            metadata_json = json.dumps(doc.metadata) if doc.metadata else None
            
            cursor.execute("""
                INSERT INTO vector_documents
                (stock_code, doc_type, content, embedding, date, period, source, importance, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc.stock_code, doc.doc_type, doc.content, embedding_blob,
                doc.date, doc.period, doc.source, doc.importance, metadata_json
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def add_documents_batch(self, docs: List[Tuple[StockDocument, List[float]]]) -> List[int]:
        """批量添加文档"""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            ids = []
            for doc, embedding in docs:
                embedding_blob = np.array(embedding, dtype=np.float32).tobytes()
                metadata_json = json.dumps(doc.metadata) if doc.metadata else None
                
                cursor.execute("""
                    INSERT INTO vector_documents
                    (stock_code, doc_type, content, embedding, date, period, source, importance, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    doc.stock_code, doc.doc_type, doc.content, embedding_blob,
                    doc.date, doc.period, doc.source, doc.importance, metadata_json
                ))
                ids.append(cursor.lastrowid)
            
            conn.commit()
            return ids
    
    def search_by_vector(self, query_embedding: List[float],
                         top_k: int = 10,
                         filters: Optional[Dict] = None) -> List[SearchResult]:
        """
        向量相似度搜索
        
        Args:
            query_embedding: 查询向量
            top_k: 返回数量
            filters: 过滤条件 {stock_code, doc_type, date_from, date_to}
        """
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            query_vec = np.array(query_embedding, dtype=np.float32)
            
            # 构建过滤条件
            where_clauses = ["embedding IS NOT NULL"]
            params: List[Any] = []
            
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
            
            # 分批处理，限制单次查询的最大文档数
            results = []
            offset = 0
            
            while True:
                cursor.execute(f"""
                    SELECT id, stock_code, content, embedding, date, doc_type, importance
                    FROM vector_documents
                    WHERE {where_sql}
                    ORDER BY id
                    LIMIT ? OFFSET ?
                """, params + [MAX_BATCH_SIZE, offset])
                
                rows = cursor.fetchall()
                if not rows:
                    break
                
                # 计算相似度
                for row in rows:
                    doc_vec = np.frombuffer(row["embedding"], dtype=np.float32)
                    similarity = self._cosine_similarity(query_vec, doc_vec)
                    
                    results.append(SearchResult(
                        doc_id=row["id"],
                        stock_code=row["stock_code"],
                        content=row["content"],
                        similarity=float(similarity),
                        date=row["date"],
                        doc_type=row["doc_type"],
                        importance=row["importance"]
                    ))
                
                # 如果结果已经足够多，提前排序并保留top结果
                if len(results) > top_k * 10:
                    results.sort(key=lambda x: x.similarity, reverse=True)
                    results = results[:top_k * 5]
                
                offset += MAX_BATCH_SIZE
                
                # 如果获取的行数少于批次大小，说明已经没有更多数据
                if len(rows) < MAX_BATCH_SIZE:
                    break
            
            # 按相似度排序
            results.sort(key=lambda x: x.similarity, reverse=True)
            return results[:top_k]
    
    def search_by_text(self, query: str,
                       top_k: int = 10,
                       filters: Optional[Dict] = None) -> List[SearchResult]:
        """
        全文搜索
        
        Args:
            query: 搜索关键词
            top_k: 返回数量
            filters: 过滤条件
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # FTS搜索
        cursor.execute("""
            SELECT rowid, rank
            FROM documents_fts
            WHERE documents_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, top_k * 2))
        
        fts_results = {row["rowid"]: -row["rank"] for row in cursor.fetchall()}
        
        if not fts_results:
            return []
        
        # 获取文档详情
        placeholders = ",".join("?" * len(fts_results))
        cursor.execute(f"""
            SELECT id, stock_code, content, date, doc_type, importance
            FROM vector_documents
            WHERE id IN ({placeholders})
        """, list(fts_results.keys()))
        
        results = []
        for row in cursor.fetchall():
            results.append(SearchResult(
                doc_id=row["id"],
                stock_code=row["stock_code"],
                content=row["content"],
                similarity=fts_results.get(row["id"], 0),
                date=row["date"],
                doc_type=row["doc_type"],
                importance=row["importance"]
            ))
        
        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:top_k]
    
    def hybrid_search(self, query: str,
                      query_embedding: List[float],
                      top_k: int = 10,
                      vector_weight: float = 0.7,
                      filters: Optional[Dict] = None) -> List[SearchResult]:
        """
        混合搜索（向量 + 全文）
        
        Args:
            query: 搜索文本
            query_embedding: 查询向量
            top_k: 返回数量
            vector_weight: 向量搜索权重
            filters: 过滤条件
        """
        # 向量搜索
        vector_results = self.search_by_vector(
            query_embedding, top_k * 2, filters
        )
        
        # 全文搜索
        text_results = self.search_by_text(query, top_k * 2, filters)
        
        # RRF融合
        return self._rrf_fusion(
            vector_results, text_results, 
            top_k, vector_weight
        )
    
    def _cosine_similarity(self, vec1: np.ndarray, 
                           vec2: np.ndarray) -> float:
        """计算余弦相似度"""
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(vec1, vec2) / (norm1 * norm2))
    
    def _rrf_fusion(self, results1: List[SearchResult],
                    results2: List[SearchResult],
                    top_k: int,
                    weight1: float = 0.7) -> List[SearchResult]:
        """
        Reciprocal Rank Fusion
        融合两个搜索结果列表
        """
        k = 60  # RRF常数
        scores = {}
        doc_map = {}
        
        # 处理第一个结果列表
        for rank, result in enumerate(results1):
            doc_id = result.doc_id
            scores[doc_id] = scores.get(doc_id, 0) + weight1 / (k + rank + 1)
            doc_map[doc_id] = result
        
        # 处理第二个结果列表
        weight2 = 1 - weight1
        for rank, result in enumerate(results2):
            doc_id = result.doc_id
            scores[doc_id] = scores.get(doc_id, 0) + weight2 / (k + rank + 1)
            if doc_id not in doc_map:
                doc_map[doc_id] = result
        
        # 按融合分数排序
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        results = []
        for doc_id in sorted_ids[:top_k]:
            result = doc_map[doc_id]
            result.similarity = scores[doc_id]
            results.append(result)
        
        return results
    
    def get_document_count(self, filters: Optional[Dict] = None) -> int:
        """获取文档数量"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        where_clauses = ["1=1"]
        params = []
        
        if filters:
            if filters.get("stock_code"):
                where_clauses.append("stock_code = ?")
                params.append(filters["stock_code"])
            if filters.get("doc_type"):
                where_clauses.append("doc_type = ?")
                params.append(filters["doc_type"])
        
        where_sql = " AND ".join(where_clauses)
        cursor.execute(f"SELECT COUNT(*) FROM vector_documents WHERE {where_sql}", params)
        
        return cursor.fetchone()[0]
    
    def delete_documents(self, filters: Dict) -> int:
        """删除文档"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        where_clauses = []
        params = []
        
        if filters.get("stock_code"):
            where_clauses.append("stock_code = ?")
            params.append(filters["stock_code"])
        if filters.get("doc_type"):
            where_clauses.append("doc_type = ?")
            params.append(filters["doc_type"])
        if filters.get("date_before"):
            where_clauses.append("date < ?")
            params.append(filters["date_before"])
        
        if not where_clauses:
            return 0
        
        where_sql = " AND ".join(where_clauses)
        cursor.execute(f"DELETE FROM vector_documents WHERE {where_sql}", params)
        conn.commit()
        
        return cursor.rowcount
    
    def close(self):
        """关闭连接"""
        if self.conn:
            self.conn.close()
            self.conn = None


# 全局单例
_store_instance: Optional[SQLiteVectorStore] = None


def get_vector_store(db_path: str = "stock_vectors.db") -> SQLiteVectorStore:
    """获取向量存储单例"""
    global _store_instance
    if _store_instance is None:
        _store_instance = SQLiteVectorStore(db_path)
    return _store_instance
