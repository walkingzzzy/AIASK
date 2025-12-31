"""
文档数据库
基于SQLite的JSON文档存储
"""
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
import sqlite3
import json
import logging
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DocumentDB:
    """
    文档数据库
    
    用于存储非结构化/半结构化数据，如：
    - 财务报告
    - 研报摘要
    - 新闻公告
    - 分析结果
    """
    
    def __init__(self, db_path: str = "data/documents.db"):
        """
        初始化文档数据库
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 文档表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    doc_type TEXT,
                    stock_code TEXT,
                    title TEXT,
                    content TEXT,
                    metadata TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(collection, doc_id)
                )
            """)
            
            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_doc_collection 
                ON documents(collection)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_doc_stock 
                ON documents(stock_code)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_doc_type 
                ON documents(doc_type)
            """)
            
            # 全文搜索表
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts 
                USING fts5(title, content, content=documents, content_rowid=id)
            """)
            
            # 触发器：同步FTS
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                    INSERT INTO documents_fts(rowid, title, content) 
                    VALUES (new.id, new.title, new.content);
                END
            """)
            
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                    INSERT INTO documents_fts(documents_fts, rowid, title, content) 
                    VALUES('delete', old.id, old.title, old.content);
                END
            """)
            
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                    INSERT INTO documents_fts(documents_fts, rowid, title, content) 
                    VALUES('delete', old.id, old.title, old.content);
                    INSERT INTO documents_fts(rowid, title, content) 
                    VALUES (new.id, new.title, new.content);
                END
            """)
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def insert(self, collection: str, doc_id: str, document: Dict,
               stock_code: Optional[str] = None,
               doc_type: Optional[str] = None) -> bool:
        """
        插入文档
        
        Args:
            collection: 集合名称
            doc_id: 文档ID
            document: 文档内容
            stock_code: 关联股票代码
            doc_type: 文档类型
            
        Returns:
            是否成功
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            try:
                title = document.get('title', '')
                content = document.get('content', '')
                if isinstance(content, dict):
                    content = json.dumps(content, ensure_ascii=False)
                
                metadata = {k: v for k, v in document.items() 
                           if k not in ['title', 'content']}
                
                cursor.execute("""
                    INSERT OR REPLACE INTO documents 
                    (collection, doc_id, doc_type, stock_code, title, content, metadata, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    collection,
                    doc_id,
                    doc_type,
                    stock_code,
                    title,
                    content,
                    json.dumps(metadata, ensure_ascii=False),
                    datetime.now().isoformat()
                ))
                
                conn.commit()
                return True
                
            except Exception as e:
                logger.error(f"插入文档失败: {e}")
                return False
    
    def get(self, collection: str, doc_id: str) -> Optional[Dict]:
        """
        获取文档
        
        Args:
            collection: 集合名称
            doc_id: 文档ID
            
        Returns:
            文档内容
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM documents 
                WHERE collection = ? AND doc_id = ?
            """, (collection, doc_id))
            
            row = cursor.fetchone()
            if row:
                return self._row_to_doc(row)
            return None
    
    def find(self, collection: str,
             stock_code: Optional[str] = None,
             doc_type: Optional[str] = None,
             limit: int = 100,
             offset: int = 0) -> List[Dict]:
        """
        查询文档
        
        Args:
            collection: 集合名称
            stock_code: 股票代码过滤
            doc_type: 文档类型过滤
            limit: 返回数量限制
            offset: 偏移量
            
        Returns:
            文档列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM documents WHERE collection = ?"
            params = [collection]
            
            if stock_code:
                query += " AND stock_code = ?"
                params.append(stock_code)
            
            if doc_type:
                query += " AND doc_type = ?"
                params.append(doc_type)
            
            query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            return [self._row_to_doc(row) for row in cursor.fetchall()]
    
    def search(self, query: str, 
               collection: Optional[str] = None,
               limit: int = 50) -> List[Dict]:
        """
        全文搜索
        
        Args:
            query: 搜索关键词
            collection: 集合名称过滤
            limit: 返回数量限制
            
        Returns:
            匹配的文档列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if collection:
                cursor.execute("""
                    SELECT d.*, bm25(documents_fts) as score
                    FROM documents d
                    JOIN documents_fts fts ON d.id = fts.rowid
                    WHERE documents_fts MATCH ? AND d.collection = ?
                    ORDER BY score
                    LIMIT ?
                """, (query, collection, limit))
            else:
                cursor.execute("""
                    SELECT d.*, bm25(documents_fts) as score
                    FROM documents d
                    JOIN documents_fts fts ON d.id = fts.rowid
                    WHERE documents_fts MATCH ?
                    ORDER BY score
                    LIMIT ?
                """, (query, limit))
            
            return [self._row_to_doc(row) for row in cursor.fetchall()]
    
    def delete(self, collection: str, doc_id: str) -> bool:
        """删除文档"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM documents 
                WHERE collection = ? AND doc_id = ?
            """, (collection, doc_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_collection(self, collection: str) -> int:
        """删除整个集合"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM documents WHERE collection = ?", (collection,))
            deleted = cursor.rowcount
            conn.commit()
            return deleted
    
    def _row_to_doc(self, row: sqlite3.Row) -> Dict:
        """将数据库行转换为文档"""
        doc = dict(row)
        
        # 解析metadata
        if doc.get('metadata'):
            try:
                metadata = json.loads(doc['metadata'])
                doc.update(metadata)
            except:
                pass
        
        # 尝试解析content为JSON
        if doc.get('content'):
            try:
                doc['content'] = json.loads(doc['content'])
            except:
                pass
        
        return doc
    
    def get_collections(self) -> List[str]:
        """获取所有集合名称"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT collection FROM documents")
            return [row[0] for row in cursor.fetchall()]
    
    def count(self, collection: Optional[str] = None) -> int:
        """统计文档数量"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if collection:
                cursor.execute(
                    "SELECT COUNT(*) FROM documents WHERE collection = ?",
                    (collection,)
                )
            else:
                cursor.execute("SELECT COUNT(*) FROM documents")
            
            return cursor.fetchone()[0]
    
    def get_stats(self) -> Dict:
        """获取数据库统计信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM documents")
            total_docs = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT collection, COUNT(*) as count 
                FROM documents 
                GROUP BY collection
            """)
            collections = {row[0]: row[1] for row in cursor.fetchall()}
            
            return {
                'total_documents': total_docs,
                'collections': collections,
                'db_path': self.db_path
            }
