"""
NLP查询和RAG检索路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["NLP查询"])


class QueryRequest(BaseModel):
    query: str


def _get_nlp_modules():
    try:
        from packages.core.nlp_query.intent_parser import IntentParser
        from packages.core.nlp_query.query_executor import QueryExecutor
        return IntentParser(), QueryExecutor()
    except ImportError:
        return None, None


def _get_stock_service():
    try:
        from packages.core.services.stock_data_service import StockDataService
        return StockDataService()
    except ImportError:
        return None


@router.post("/query")
async def natural_language_query(request: QueryRequest):
    """自然语言查询"""
    try:
        parser, executor = _get_nlp_modules()
        if parser and executor:
            parsed = parser.parse(request.query)
            result = executor.execute(parsed)
            return {"success": True, "data": result}
        
        return {
            "success": True,
            "data": {
                "query": request.query,
                "intent": "unknown",
                "response": "NLP模块未加载，请检查依赖"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/query")
async def rag_query(request: QueryRequest):
    """RAG向量检索查询"""
    try:
        service = _get_stock_service()
        if service:
            context = service.get_context_for_analysis("", request.query)
            results = service.search_knowledge_base(request.query, top_k=5)
            return {
                "success": True,
                "data": {
                    "query": request.query,
                    "context": context,
                    "results": results
                }
            }
        return {
            "success": True,
            "data": {
                "query": request.query,
                "context": "",
                "results": [],
                "message": "RAG模块未加载"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
