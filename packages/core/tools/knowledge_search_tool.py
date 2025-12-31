"""
知识库检索工具
为CrewAI Agent提供RAG检索能力
"""
from typing import Type, Optional, List, Dict
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

from packages.core.services.stock_data_service import get_stock_service


class KnowledgeSearchInput(BaseModel):
    """知识库检索输入"""
    query: str = Field(..., description="搜索查询，如'高ROE低估值股票'或'茅台财务分析'")
    stock_code: str = Field(default="", description="限定股票代码，可选")
    top_k: int = Field(default=5, description="返回结果数量")


class KnowledgeSearchTool(BaseTool):
    """
    知识库检索工具
    
    功能：
    - 语义搜索股票相关信息
    - 检索历史行情摘要
    - 检索财报分析
    - 检索相关新闻
    """
    
    name: str = "knowledge_search_tool"
    description: str = """
    从知识库中检索股票相关信息。
    
    使用场景：
    1. 查找特定股票的历史分析记录
    2. 搜索符合特定条件的股票信息
    3. 获取股票的财务摘要和技术分析
    4. 查找相关新闻和研报
    """
    args_schema: Type[BaseModel] = KnowledgeSearchInput

    def _run(self, query: str, stock_code: str = "", top_k: int = 5) -> str:
        """执行知识库检索"""
        try:
            service = get_stock_service()
            
            results = service.search_knowledge_base(
                query=query,
                stock_code=stock_code if stock_code else None,
                top_k=top_k
            )
            
            if not results:
                return f"未找到与'{query}'相关的信息"
            
            output = [f"=== 知识库检索结果 ({len(results)}条) ==="]
            
            for i, doc in enumerate(results, 1):
                output.append(f"\n【结果{i}】")
                output.append(f"股票: {doc.get('stock_code', 'N/A')}")
                output.append(f"类型: {doc.get('doc_type', 'N/A')}")
                output.append(f"日期: {doc.get('date', 'N/A')}")
                output.append(f"相关度: {doc.get('score', 0):.2f}")
                content = doc.get('content', '')
                output.append(f"内容:\n{content[:500]}{'...' if len(content) > 500 else ''}")
            
            return "\n".join(output)
            
        except Exception as e:
            return f"知识库检索失败：{str(e)}"


class SimilarStocksInput(BaseModel):
    """相似股票查询输入"""
    stock_code: str = Field(..., description="基准股票代码，如600519")
    top_k: int = Field(default=5, description="返回相似股票数量")


class SimilarStocksTool(BaseTool):
    """
    相似股票查询工具
    基于向量相似度查找特征相似的股票
    """
    
    name: str = "similar_stocks_tool"
    description: str = """
    查找与指定股票特征相似的其他股票。
    基于股票的行情特征、技术指标、财务数据等维度，
    使用向量相似度算法找出最相似的股票。
    """
    args_schema: Type[BaseModel] = SimilarStocksInput
    
    def _run(self, stock_code: str, top_k: int = 5) -> str:
        """查找相似股票"""
        try:
            service = get_stock_service()
            results = service.find_similar_stocks(stock_code, top_k)
            
            if not results:
                return f"未找到与{stock_code}相似的股票"
            
            output = [f"=== 与{stock_code}相似的股票 ==="]
            
            for i, stock in enumerate(results, 1):
                output.append(
                    f"{i}. {stock.get('stock_code', 'N/A')} "
                    f"相似度: {stock.get('score', 0):.2f}"
                )
            
            return "\n".join(output)
            
        except Exception as e:
            return f"查找相似股票失败：{str(e)}"


class RAGContextInput(BaseModel):
    """RAG上下文输入"""
    stock_code: str = Field(..., description="股票代码")
    query: str = Field(default="", description="分析问题，可选")


class RAGContextTool(BaseTool):
    """
    RAG上下文构建工具
    为AI分析构建相关上下文信息
    """
    
    name: str = "rag_context_tool"
    description: str = """
    为股票分析构建RAG上下文。
    从知识库中检索与股票相关的所有信息，
    包括历史行情、财务数据、新闻等，
    构建成结构化的上下文供AI分析使用。
    """
    args_schema: Type[BaseModel] = RAGContextInput
    
    def _run(self, stock_code: str, query: str = "") -> str:
        """构建RAG上下文"""
        try:
            service = get_stock_service()
            
            context = service.get_context_for_analysis(
                stock_code=stock_code,
                query=query,
                max_tokens=3000
            )
            
            if not context:
                return f"未找到{stock_code}的相关上下文信息"
            
            return f"=== {stock_code} 分析上下文 ===\n\n{context}"
            
        except Exception as e:
            return f"构建上下文失败：{str(e)}"
