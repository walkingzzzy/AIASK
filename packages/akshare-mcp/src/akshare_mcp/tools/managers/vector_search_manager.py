"""向量搜索管理器 - 相似K线形态、相似股票"""

from typing import Optional
import time

from ...storage import get_db
from ...utils import normalize_code
from ...services.retrieval_eval import summarize_ranked_results
from ..manager_protocol import (
    fail_with_meta,
    normalize_manager_code,
    normalize_manager_kwargs,
    ok_with_meta,
)


def register_vector_search_manager(mcp):
    """注册向量搜索管理器工具"""

    async def _run_registered_tool(tool_name: str, args: dict) -> dict:
        tool = getattr(getattr(mcp, "_tool_manager", None), "_tools", {}).get(tool_name)
        if tool is None:
            return fail(f"Tool {tool_name} not found")
        result = await tool.run(args or {})
        return result if isinstance(result, dict) else {"success": False, "error": f"Unexpected result type from {tool_name}"}
    
    @mcp.tool()
    async def vector_search_manager(action: str, code: Optional[str] = None, **kwargs):
        """向量搜索管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/similar_patterns/similar_stocks
            code (str, optional): 股票代码
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - similar_patterns: code(str, 目标股票), days(int, optional, K线天数), top_n(int, optional)
                - similar_stocks: code(str, 目标股票), similarity_type(str, optional, "fundamental"/"technical"/"both"), top_n(int, optional)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            vector_search_manager(action="help", kwargs="{}")
            # 搜索相似K线形态
            vector_search_manager(action="similar_patterns", code="600519", kwargs='{"days":20,"top_n":5}')
            # 搜索相似股票
            vector_search_manager(action="similar_stocks", code="600519", kwargs='{"similarity_type":"both","top_n":10}')
        """
        start_time = time.perf_counter()
        try:
            db = get_db()
            kwargs = normalize_manager_kwargs(kwargs)
            code, kwargs = normalize_manager_code(code, kwargs)

            def _ok(data: dict, source_chain=None):
                return ok_with_meta(
                    data,
                    tool_name='vector_search_manager',
                    action=action,
                    started_at=start_time,
                    source_chain=source_chain,
                )

            def _fail(message: str, source_chain=None):
                return fail_with_meta(
                    message,
                    tool_name='vector_search_manager',
                    action=action,
                    started_at=start_time,
                    source_chain=source_chain,
                )
            
            if action == 'help':
                return _ok({
                    'supported_actions': {
                        'similar_patterns': '搜索相似K线形态（需要 code）',
                        'similar_stocks': '搜索相似股票（需要 code）',
                        'help': '显示帮助信息',
                    }
                }, source_chain=['vector_search_manager'])
            
            elif action == 'similar_patterns':
                if not code:
                    return _fail('需要提供股票代码')
                
                code = normalize_code(code)
                top_n = kwargs.get('top_n', 10)
                days = kwargs.get('days', 20)
                
                # 调用真实的 K线形态搜索
                try:
                    result = await _run_registered_tool("search_by_kline", {"code": code, "days": int(days), "top_n": int(top_n)})
                    if result.get('success') and result.get('data'):
                        data = result['data']
                        similar = data.get('results', [])
                        backend_requested = data.get('backend_requested') or data.get('search_backend') or 'python'
                        backend_used = data.get('backend_used') or data.get('actual_backend') or backend_requested
                        retrieval_quality = summarize_ranked_results(
                            similar,
                            score_key='similarity',
                            backend_requested=backend_requested,
                            backend_used=backend_used,
                            fallback_used=bool(data.get('fallback_used', backend_used != backend_requested)),
                            fallback_reason=data.get('fallback_reason'),
                        )
                        return _ok({
                            'code': code,
                            'similar_stocks': similar,
                            'pattern_type': 'kline_similarity',
                            'confidence': similar[0].get('similarity', 0) if similar else 0,
                            'source': data.get('actual_backend') or data.get('search_backend') or 'kline_correlation',
                            'backend_requested': backend_requested,
                            'backend_used': backend_used,
                            'fallback_used': bool(data.get('fallback_used', backend_used != backend_requested)),
                            'fallback_reason': data.get('fallback_reason'),
                            'latency_ms': data.get('latency_ms', 0),
                            'retrieval_quality': retrieval_quality,
                        }, source_chain=['vector_search_manager', 'search_by_kline'])
                except Exception:
                    pass
                
                return _ok({
                    'code': code,
                    'similar_stocks': [],
                    'pattern_type': 'unknown',
                    'confidence': 0,
                    'message': f'暂无 {code} 的相似K线形态数据，请先运行数据预热'
                }, source_chain=['vector_search_manager', 'search_by_kline'])
            
            elif action == 'similar_stocks':
                if not code:
                    return _fail('需要提供股票代码')
                
                code = normalize_code(code)
                top_n = kwargs.get('top_n', 10)
                similarity_type = kwargs.get('similarity_type', 'both')
                
                # 调用真实的相似股票搜索
                try:
                    result = await _run_registered_tool("search_similar_stocks", {"code": code, "top_n": int(top_n), "similarity_type": str(similarity_type)})
                    if result.get('success') and result.get('data'):
                        data = result['data']
                        similar = data.get('similar_stocks', [])
                        retrieval_quality = summarize_ranked_results(
                            similar,
                            score_key='similarity',
                            backend_requested='python',
                            backend_used='python',
                            fallback_used=False,
                            fallback_reason=None,
                        )
                        return _ok({
                            'code': code,
                            'similar_stocks': similar,
                            'source': data.get('candidate_scope', 'similarity_search'),
                            'similarity_type': data.get('similarity_type', similarity_type),
                            'retrieval_quality': retrieval_quality,
                        }, source_chain=['vector_search_manager', 'search_similar_stocks'])
                except Exception:
                    pass
                
                return _ok({
                    'code': code,
                    'similar_stocks': [],
                    'message': f'暂无 {code} 的相似股票数据，请先运行数据预热'
                }, source_chain=['vector_search_manager', 'search_similar_stocks'])
            
            else:
                return _fail(f'Unknown action: {action}. Supported: help, similar_patterns, similar_stocks')
        except Exception as e:
            return fail_with_meta(
                str(e),
                tool_name='vector_search_manager',
                action=action,
                started_at=start_time,
                source_chain=['vector_search_manager'],
            )
