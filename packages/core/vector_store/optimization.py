"""
向量存储性能优化
"""
import sqlite3
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class VectorStoreOptimizer:
    """向量存储优化器"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def create_indexes(self):
        """创建索引优化查询性能"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 1. 股票代码索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_vector_docs_stock_code
                ON vector_documents(stock_code)
            """)

            # 2. 文档类型索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_vector_docs_doc_type
                ON vector_documents(doc_type)
            """)

            # 3. 日期索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_vector_docs_date
                ON vector_documents(date DESC)
            """)

            # 4. 复合索引：股票代码+日期
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_vector_docs_code_date
                ON vector_documents(stock_code, date DESC)
            """)

            # 5. 重要性索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_vector_docs_importance
                ON vector_documents(importance DESC)
            """)

            conn.commit()
            logger.info("向量存储索引创建成功")

        except Exception as e:
            logger.error(f"创建索引失败: {e}")
            conn.rollback()
        finally:
            conn.close()

    def optimize_database(self):
        """优化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 1. 分析表统计信息
            cursor.execute("ANALYZE")

            # 2. 清理碎片
            cursor.execute("VACUUM")

            # 3. 优化查询计划
            cursor.execute("PRAGMA optimize")

            conn.commit()
            logger.info("数据库优化完成")

        except Exception as e:
            logger.error(f"数据库优化失败: {e}")
        finally:
            conn.close()

    def add_cache_layer(self):
        """添加缓存层配置"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 增加缓存大小 (10MB)
            cursor.execute("PRAGMA cache_size = -10000")

            # 使用WAL模式提升并发性能
            cursor.execute("PRAGMA journal_mode = WAL")

            # 同步模式设置为NORMAL提升写入性能
            cursor.execute("PRAGMA synchronous = NORMAL")

            # 临时文件存储在内存
            cursor.execute("PRAGMA temp_store = MEMORY")

            conn.commit()
            logger.info("缓存层配置完成")

        except Exception as e:
            logger.error(f"缓存配置失败: {e}")
        finally:
            conn.close()

    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        stats = {}

        try:
            # 表大小
            cursor.execute("""
                SELECT
                    COUNT(*) as total_docs,
                    COUNT(DISTINCT stock_code) as total_stocks
                FROM vector_documents
            """)
            row = cursor.fetchone()
            stats['total_documents'] = row[0]
            stats['total_stocks'] = row[1]

            # 索引信息
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='index' AND tbl_name='vector_documents'
            """)
            stats['indexes'] = [row[0] for row in cursor.fetchall()]

            # 数据库大小
            cursor.execute("PRAGMA page_count")
            page_count = cursor.fetchone()[0]
            cursor.execute("PRAGMA page_size")
            page_size = cursor.fetchone()[0]
            stats['db_size_mb'] = (page_count * page_size) / (1024 * 1024)

            return stats

        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}
        finally:
            conn.close()


class QueryOptimizer:
    """查询优化器"""

    @staticmethod
    def optimize_similarity_search(
        stock_code: str,
        doc_type: str = None,
        limit: int = 10,
        date_range: tuple = None
    ) -> str:
        """
        优化相似度搜索SQL

        Args:
            stock_code: 股票代码
            doc_type: 文档类型
            limit: 返回数量
            date_range: 日期范围 (start_date, end_date)

        Returns:
            优化后的SQL
        """
        # 使用索引的查询
        sql = """
            SELECT
                id, stock_code, content, date, doc_type, importance
            FROM vector_documents
            WHERE stock_code = ?
        """

        params = [stock_code]

        if doc_type:
            sql += " AND doc_type = ?"
            params.append(doc_type)

        if date_range:
            sql += " AND date BETWEEN ? AND ?"
            params.extend(date_range)

        # 按重要性和日期排序
        sql += " ORDER BY importance DESC, date DESC"
        sql += f" LIMIT {limit}"

        return sql, params

    @staticmethod
    def batch_insert_optimization(documents: List[Dict[str, Any]]) -> str:
        """
        批量插入优化

        Args:
            documents: 文档列表

        Returns:
            批量插入SQL
        """
        # 使用事务批量插入
        sql = """
            INSERT INTO vector_documents
            (stock_code, doc_type, content, embedding, date, period, source, importance, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        return sql