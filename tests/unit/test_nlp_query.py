"""
NLP查询系统测试
"""
import pytest

from packages.core.nlp_query.intent_parser import (
    IntentParser,
    IntentType,
    QueryIntent,
    parse_query,
)
from packages.core.nlp_query.query_executor import (
    QueryExecutor,
    QueryResult,
    execute_query,
)


class TestIntentParser:
    """测试意图解析器"""

    @pytest.fixture
    def parser(self):
        return IntentParser()

    # ==================== 股票筛选意图测试 ====================

    def test_screening_intent_pe(self, parser):
        """测试PE筛选意图"""
        query = "找出PE低于20的股票"
        result = parser.parse(query)

        assert result.intent_type == IntentType.STOCK_SCREENING
        assert result.confidence > 0.5
        assert "conditions" in result.entities

    def test_screening_intent_roe(self, parser):
        """测试ROE筛选意图"""
        query = "筛选ROE大于15%的股票"
        result = parser.parse(query)

        assert result.intent_type == IntentType.STOCK_SCREENING
        assert "conditions" in result.entities

    def test_screening_intent_multiple_conditions(self, parser):
        """测试多条件筛选"""
        query = "找出PE低于20且ROE大于15的股票"
        result = parser.parse(query)

        assert result.intent_type == IntentType.STOCK_SCREENING

    def test_screening_intent_top_n(self, parser):
        """测试排名筛选"""
        query = "市值前10的股票"
        result = parser.parse(query)

        assert result.intent_type == IntentType.STOCK_SCREENING
        assert result.entities.get("limit") == 10

    # ==================== 个股分析意图测试 ====================

    def test_analysis_intent_by_name(self, parser):
        """测试按名称分析"""
        query = "分析贵州茅台"
        result = parser.parse(query)

        assert result.intent_type == IntentType.STOCK_ANALYSIS
        assert "600519" in result.entities.get("stock_codes", [])

    def test_analysis_intent_by_code(self, parser):
        """测试按代码分析"""
        query = "600519怎么样"
        result = parser.parse(query)

        assert result.intent_type == IntentType.STOCK_ANALYSIS
        assert "600519" in result.entities.get("stock_codes", [])

    def test_analysis_intent_technical(self, parser):
        """测试技术分析意图"""
        query = "茅台的技术分析"
        result = parser.parse(query)

        assert result.intent_type == IntentType.STOCK_ANALYSIS
        assert result.entities.get("analysis_type") == "technical"

    def test_analysis_intent_fundamental(self, parser):
        """测试基本面分析意图"""
        query = "茅台的基本面分析"
        result = parser.parse(query)

        assert result.intent_type == IntentType.STOCK_ANALYSIS
        assert result.entities.get("analysis_type") == "fundamental"

    def test_analysis_intent_buy_question(self, parser):
        """测试买入问题"""
        query = "茅台能买吗"
        result = parser.parse(query)

        assert result.intent_type == IntentType.STOCK_ANALYSIS

    # ==================== 数据查询意图测试 ====================

    def test_data_query_pe(self, parser):
        """测试PE查询"""
        query = "茅台的PE是多少"
        result = parser.parse(query)

        assert result.intent_type == IntentType.DATA_QUERY
        assert result.entities.get("metric") == "pe"

    def test_data_query_price(self, parser):
        """测试价格查询"""
        query = "茅台现在多少钱"
        result = parser.parse(query)

        assert result.intent_type == IntentType.DATA_QUERY
        assert result.entities.get("metric") == "price"

    def test_data_query_change(self, parser):
        """测试涨跌查询"""
        query = "茅台今天涨了多少"
        result = parser.parse(query)

        assert result.intent_type == IntentType.DATA_QUERY
        assert result.entities.get("time") == "today"

    # ==================== 实体提取测试 ====================

    def test_extract_stock_code(self, parser):
        """测试股票代码提取"""
        query = "分析600519"
        result = parser.parse(query)

        assert "600519" in result.entities.get("stock_codes", [])

    def test_extract_stock_name(self, parser):
        """测试股票名称提取"""
        query = "分析贵州茅台"
        result = parser.parse(query)

        assert result.entities.get("stock_name") == "贵州茅台"
        assert "600519" in result.entities.get("stock_codes", [])

    def test_extract_numbers(self, parser):
        """测试数值提取"""
        query = "PE低于20的股票"
        result = parser.parse(query)

        assert 20.0 in result.entities.get("numbers", [])

    def test_extract_metric(self, parser):
        """测试指标提取"""
        query = "ROE大于15%"
        result = parser.parse(query)

        assert result.entities.get("metric") == "roe"

    # ==================== 边界情况测试 ====================

    def test_unknown_intent(self, parser):
        """测试未知意图"""
        query = "今天天气怎么样"
        result = parser.parse(query)

        assert result.intent_type == IntentType.UNKNOWN
        assert result.confidence == 0.0

    def test_empty_query(self, parser):
        """测试空查询"""
        query = ""
        result = parser.parse(query)

        assert result.intent_type == IntentType.UNKNOWN

    def test_to_dict(self, parser):
        """测试转换为字典"""
        query = "分析茅台"
        result = parser.parse(query)
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "intent_type" in result_dict
        assert "confidence" in result_dict
        assert "entities" in result_dict


class TestQueryExecutor:
    """测试查询执行器"""

    @pytest.fixture
    def executor(self):
        return QueryExecutor()

    @pytest.fixture
    def parser(self):
        return IntentParser()

    # ==================== 筛选执行测试 ====================

    def test_execute_screening(self, executor, parser):
        """测试执行筛选"""
        intent = parser.parse("找出PE低于20的股票")
        result = executor.execute(intent)

        assert isinstance(result, QueryResult)
        assert result.intent_type == "stock_screening"

    def test_execute_screening_no_conditions(self, executor, parser):
        """测试无条件筛选"""
        intent = parser.parse("找出股票")
        result = executor.execute(intent)

        # 应该返回失败或提示
        assert isinstance(result, QueryResult)

    # ==================== 分析执行测试 ====================

    def test_execute_analysis(self, executor, parser):
        """测试执行分析"""
        intent = parser.parse("分析贵州茅台")
        result = executor.execute(intent)

        assert isinstance(result, QueryResult)
        assert result.success is True
        assert result.intent_type == "stock_analysis"
        assert result.data is not None

    def test_execute_analysis_no_stock(self, executor, parser):
        """测试无股票分析"""
        intent = parser.parse("分析一下")
        result = executor.execute(intent)

        assert result.success is False

    # ==================== 数据查询执行测试 ====================

    def test_execute_data_query(self, executor, parser):
        """测试执行数据查询"""
        intent = parser.parse("茅台的PE是多少")
        result = executor.execute(intent)

        assert isinstance(result, QueryResult)
        assert result.success is True
        assert result.data is not None
        assert "answer" in result.data

    def test_execute_data_query_no_stock(self, executor, parser):
        """测试无股票数据查询"""
        intent = parser.parse("PE是多少")
        result = executor.execute(intent)

        assert result.success is False

    # ==================== 未知意图执行测试 ====================

    def test_execute_unknown(self, executor, parser):
        """测试执行未知意图"""
        intent = parser.parse("今天天气怎么样")
        result = executor.execute(intent)

        assert result.success is False
        assert len(result.suggestions) > 0

    # ==================== 结果格式测试 ====================

    def test_result_to_dict(self, executor, parser):
        """测试结果转换为字典"""
        intent = parser.parse("分析茅台")
        result = executor.execute(intent)
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "success" in result_dict
        assert "intent_type" in result_dict
        assert "data" in result_dict
        assert "message" in result_dict
        assert "suggestions" in result_dict
        assert "executed_at" in result_dict


class TestConvenienceFunctions:
    """测试便捷函数"""

    def test_parse_query(self):
        """测试parse_query函数"""
        result = parse_query("分析茅台")

        assert isinstance(result, QueryIntent)
        assert result.intent_type == IntentType.STOCK_ANALYSIS

    def test_execute_query(self):
        """测试execute_query函数"""
        intent = parse_query("分析茅台")
        result = execute_query(intent)

        assert isinstance(result, QueryResult)
        assert result.success is True


class TestIntegration:
    """集成测试"""

    def test_full_screening_flow(self):
        """测试完整筛选流程"""
        # 解析
        intent = parse_query("找出PE低于20且ROE大于15的股票")
        assert intent.intent_type == IntentType.STOCK_SCREENING

        # 执行
        result = execute_query(intent)
        assert isinstance(result, QueryResult)

    def test_full_analysis_flow(self):
        """测试完整分析流程"""
        # 解析
        intent = parse_query("分析贵州茅台的技术面")
        assert intent.intent_type == IntentType.STOCK_ANALYSIS
        assert intent.entities.get("analysis_type") == "technical"

        # 执行
        result = execute_query(intent)
        assert result.success is True
        assert result.data is not None

    def test_full_query_flow(self):
        """测试完整查询流程"""
        # 解析
        intent = parse_query("茅台今天涨了多少")
        assert intent.intent_type == IntentType.DATA_QUERY

        # 执行
        result = execute_query(intent)
        assert result.success is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
