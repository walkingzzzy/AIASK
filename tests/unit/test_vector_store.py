"""
向量知识库测试
"""
import pytest
import tempfile
import shutil

from packages.core.vector_store.embeddings.embedding_models import (
    BaseEmbedding,
    OpenAIEmbedding,
    LocalEmbedding,
    get_embedding_model,
)
from packages.core.vector_store.storage.sqlite_vector_store import (
    SQLiteVectorStore,
    StockDocument,
    SearchResult,
)
from packages.core.vector_store.retrieval.retriever import (
    StockRetriever,
    RetrievalResult,
)


class TestEmbeddingModels:
    """测试向量化模型"""

    def test_openai_embedding_mock(self):
        """测试OpenAI向量化（模拟模式）"""
        model = OpenAIEmbedding()
        embedding = model.embed("测试文本")

        assert isinstance(embedding, list)
        assert len(embedding) == 1536  # OpenAI维度
        assert all(isinstance(x, float) for x in embedding)

    def test_embedding_deterministic(self):
        """测试向量化确定性"""
        model = OpenAIEmbedding()
        text = "贵州茅台财务分析"

        emb1 = model.embed(text)
        emb2 = model.embed(text)

        # 相同文本应该产生相同向量
        assert emb1 == emb2

    def test_embedding_different_texts(self):
        """测试不同文本产生不同向量"""
        model = OpenAIEmbedding()

        emb1 = model.embed("贵州茅台")
        emb2 = model.embed("五粮液")

        # 不同文本应该产生不同向量
        assert emb1 != emb2

    def test_batch_embedding(self):
        """测试批量向量化"""
        model = OpenAIEmbedding()
        texts = ["文本1", "文本2", "文本3"]

        embeddings = model.embed_batch(texts)

        assert len(embeddings) == 3
        assert all(len(e) == 1536 for e in embeddings)

    def test_embedding_cache(self):
        """测试向量缓存"""
        model = OpenAIEmbedding()
        text = "缓存测试"

        # 第一次调用
        model.embed(text)
        # 第二次应该从缓存获取
        cached = model._get_cached(text)

        assert cached is not None

    def test_local_embedding_mock(self):
        """测试本地向量化（模拟模式）"""
        model = LocalEmbedding()
        embedding = model.embed("测试文本")

        assert isinstance(embedding, list)
        assert len(embedding) == 512  # small模型维度


class TestSQLiteVectorStore:
    """测试SQLite向量存储"""

    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_vectors.db")
        yield db_path
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def store(self, temp_db):
        """创建存储实例"""
        return SQLiteVectorStore(temp_db)

    @pytest.fixture
    def sample_doc(self):
        """示例文档"""
        return StockDocument(
            stock_code="600519",
            doc_type="quote_summary",
            content="贵州茅台今日收盘价1850元，涨幅1.5%，成交量放大",
            date="2024-12-09",
            period="daily",
            source="system",
            importance=0.8,
        )

    @pytest.fixture
    def sample_embedding(self):
        """示例向量"""
        model = OpenAIEmbedding()
        return model.embed("贵州茅台今日收盘价1850元")

    def test_add_document(self, store, sample_doc, sample_embedding):
        """测试添加文档"""
        doc_id = store.add_document(sample_doc, sample_embedding)

        assert doc_id > 0

    def test_add_documents_batch(self, store, sample_embedding):
        """测试批量添加文档"""
        docs = [
            (
                StockDocument(
                    stock_code="600519",
                    doc_type="quote_summary",
                    content=f"文档{i}",
                    date="2024-12-09",
                ),
                sample_embedding,
            )
            for i in range(3)
        ]

        ids = store.add_documents_batch(docs)

        assert len(ids) == 3
        assert all(id > 0 for id in ids)

    def test_search_by_vector(self, store, sample_doc, sample_embedding):
        """测试向量搜索"""
        store.add_document(sample_doc, sample_embedding)

        results = store.search_by_vector(sample_embedding, top_k=5)

        assert len(results) > 0
        assert isinstance(results[0], SearchResult)
        assert results[0].stock_code == "600519"

    def test_search_by_text(self, store, sample_doc, sample_embedding):
        """测试全文搜索"""
        store.add_document(sample_doc, sample_embedding)

        results = store.search_by_text("茅台", top_k=5)

        assert len(results) > 0
        assert "茅台" in results[0].content

    def test_hybrid_search(self, store, sample_doc, sample_embedding):
        """测试混合搜索"""
        store.add_document(sample_doc, sample_embedding)

        results = store.hybrid_search("茅台收盘价", sample_embedding, top_k=5)

        assert len(results) > 0

    def test_search_with_filters(self, store, sample_embedding):
        """测试带过滤的搜索"""
        # 添加多个文档
        doc1 = StockDocument(
            stock_code="600519",
            doc_type="quote_summary",
            content="茅台文档",
            date="2024-12-09",
        )
        doc2 = StockDocument(
            stock_code="000858",
            doc_type="quote_summary",
            content="五粮液文档",
            date="2024-12-09",
        )

        store.add_document(doc1, sample_embedding)
        store.add_document(doc2, sample_embedding)

        # 按股票代码过滤
        results = store.search_by_vector(
            sample_embedding, top_k=5, filters={"stock_code": "600519"}
        )

        assert all(r.stock_code == "600519" for r in results)

    def test_get_document_count(self, store, sample_doc, sample_embedding):
        """测试获取文档数量"""
        store.add_document(sample_doc, sample_embedding)

        count = store.get_document_count()

        assert count >= 1

    def test_delete_documents(self, store, sample_doc, sample_embedding):
        """测试删除文档"""
        store.add_document(sample_doc, sample_embedding)

        deleted = store.delete_documents({"stock_code": "600519"})

        assert deleted >= 1
        assert store.get_document_count({"stock_code": "600519"}) == 0


class TestStockRetriever:
    """测试股票检索器"""

    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_vectors.db")
        yield db_path
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def retriever(self, temp_db):
        """创建检索器"""
        store = SQLiteVectorStore(temp_db)
        embedding = OpenAIEmbedding()
        return StockRetriever(store, embedding)

    @pytest.fixture
    def populated_retriever(self, retriever):
        """填充数据的检索器"""
        embedding = retriever.embedding

        docs = [
            StockDocument(
                stock_code="600519",
                doc_type="quote_summary",
                content="贵州茅台今日收盘价1850元，涨幅1.5%",
                date="2024-12-09",
            ),
            StockDocument(
                stock_code="600519",
                doc_type="financial_report",
                content="贵州茅台2024年三季报，营收增长15%",
                date="2024-10-30",
            ),
            StockDocument(
                stock_code="000858",
                doc_type="quote_summary",
                content="五粮液今日收盘价150元，涨幅0.8%",
                date="2024-12-09",
            ),
        ]

        for doc in docs:
            emb = embedding.embed(doc.content)
            retriever.store.add_document(doc, emb)

        return retriever

    def test_retrieve_vector(self, populated_retriever):
        """测试向量检索"""
        result = populated_retriever.retrieve(
            "茅台股价", top_k=5, search_type="vector"
        )

        assert isinstance(result, RetrievalResult)
        assert result.search_type == "vector"
        assert len(result.results) > 0

    def test_retrieve_text(self, populated_retriever):
        """测试文本检索"""
        result = populated_retriever.retrieve("茅台", top_k=5, search_type="text")

        assert result.search_type == "text"
        assert len(result.results) > 0

    def test_retrieve_hybrid(self, populated_retriever):
        """测试混合检索"""
        result = populated_retriever.retrieve("茅台收盘价", top_k=5, search_type="hybrid")

        assert result.search_type == "hybrid"
        assert len(result.results) > 0

    def test_retrieve_for_stock(self, populated_retriever):
        """测试特定股票检索"""
        result = populated_retriever.retrieve_for_stock("600519", "财报", top_k=5)

        assert len(result.results) > 0
        assert all(r["stock_code"] == "600519" for r in result.results)

    def test_time_decay(self, populated_retriever):
        """测试时间衰减"""
        result = populated_retriever.retrieve(
            "茅台", top_k=5, apply_time_decay=True
        )

        # 检查是否应用了时间衰减
        for r in result.results:
            assert "time_decay" in r
            assert 0 < r["time_decay"] <= 1

    def test_build_context(self, populated_retriever):
        """测试构建RAG上下文"""
        context = populated_retriever.build_context("茅台分析", stock_code="600519")

        assert isinstance(context, str)
        assert len(context) > 0

    def test_result_to_dict(self, populated_retriever):
        """测试结果转换为字典"""
        result = populated_retriever.retrieve("茅台", top_k=5)
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "query" in result_dict
        assert "results" in result_dict
        assert "total_found" in result_dict


class TestIntegration:
    """集成测试"""

    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_vectors.db")
        yield db_path
        shutil.rmtree(temp_dir)

    def test_full_pipeline(self, temp_db):
        """测试完整流程"""
        # 1. 创建组件
        store = SQLiteVectorStore(temp_db)
        embedding = OpenAIEmbedding()
        retriever = StockRetriever(store, embedding)

        # 2. 添加文档
        doc = StockDocument(
            stock_code="600519",
            doc_type="quote_summary",
            content="贵州茅台今日收盘价1850元，涨幅1.5%，成交量放大，北向资金净买入",
            date="2024-12-09",
            importance=0.9,
        )
        emb = embedding.embed(doc.content)
        store.add_document(doc, emb)

        # 3. 检索
        result = retriever.retrieve("茅台北向资金", top_k=5)

        # 4. 验证
        assert result.total_found > 0
        assert "北向资金" in result.results[0]["content"]

        # 5. 构建上下文
        context = retriever.build_context("茅台分析")
        assert len(context) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
