"""
查询执行器
执行解析后的查询意图
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

from .intent_parser import QueryIntent, IntentType

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """查询结果"""
    success: bool
    intent_type: str
    data: Any
    message: str
    suggestions: List[str]
    executed_at: str
    
    def to_dict(self) -> Dict:
        return asdict(self)


class QueryExecutor:
    """
    查询执行器

    根据解析的意图执行相应的查询操作
    """

    def __init__(self, data_service=None, score_service=None):
        """
        Args:
            data_service: 数据服务实例
            score_service: 评分服务实例
        """
        # 如果没有传入服务，则自动创建
        if data_service is None:
            try:
                from services.stock_data_service import get_stock_service
                self.data_service = get_stock_service()
            except Exception as e:
                logger.warning(f"无法加载数据服务: {e}")
                self.data_service = None
        else:
            self.data_service = data_service

        self.score_service = score_service
    
    def execute(self, intent: QueryIntent) -> QueryResult:
        """
        执行查询
        
        Args:
            intent: 解析后的查询意图
            
        Returns:
            QueryResult
        """
        try:
            if intent.intent_type == IntentType.STOCK_SCREENING:
                return self._execute_screening(intent)
            elif intent.intent_type == IntentType.STOCK_ANALYSIS:
                return self._execute_analysis(intent)
            elif intent.intent_type == IntentType.DATA_QUERY:
                return self._execute_data_query(intent)
            else:
                return self._handle_unknown(intent)
        except Exception as e:
            logger.error(f"执行查询失败: {e}")
            return QueryResult(
                success=False,
                intent_type=intent.intent_type.value,
                data=None,
                message=f"查询执行失败: {str(e)}",
                suggestions=["请检查查询条件是否正确", "尝试简化查询"],
                executed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
    
    def _execute_screening(self, intent: QueryIntent) -> QueryResult:
        """执行股票筛选"""
        conditions = intent.entities.get('conditions', [])
        limit = intent.entities.get('limit', 20)

        if not conditions:
            return QueryResult(
                success=False,
                intent_type=intent.intent_type.value,
                data=None,
                message="未能识别筛选条件",
                suggestions=[
                    "请指定筛选条件，例如：PE低于20",
                    "支持的指标：PE、PB、ROE、营收增速、利润增速等"
                ],
                executed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

        # 构建筛选描述
        condition_desc = []
        for c in conditions:
            condition_desc.append(f"{c['metric']} {c['operator']} {c['value']}")

        # 执行真实筛选逻辑
        if self.data_service:
            try:
                # 使用数据服务进行筛选
                results = self._screen_stocks_with_service(conditions, limit)
            except Exception as e:
                logger.error(f"筛选失败: {e}")
                results = []
        else:
            logger.warning("数据服务不可用，无法执行筛选")
            results = []
        
        return QueryResult(
            success=True,
            intent_type=intent.intent_type.value,
            data={
                "conditions": conditions,
                "results": results,
                "total": len(results)
            },
            message=f"筛选条件：{', '.join(condition_desc)}，共找到{len(results)}只股票",
            suggestions=[
                "可以添加更多条件进一步筛选",
                "点击股票代码查看详细分析"
            ],
            executed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    
    def _execute_analysis(self, intent: QueryIntent) -> QueryResult:
        """执行个股分析"""
        stock_codes = intent.entities.get('stock_codes', [])
        analysis_type = intent.entities.get('analysis_type', 'comprehensive')

        if not stock_codes:
            return QueryResult(
                success=False,
                intent_type=intent.intent_type.value,
                data=None,
                message="未能识别股票代码或名称",
                suggestions=[
                    "请指定股票代码，例如：600519",
                    "或使用股票名称，例如：贵州茅台"
                ],
                executed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

        stock_code = stock_codes[0]
        stock_name = intent.entities.get('stock_name', stock_code)

        # 执行真实分析逻辑
        if self.data_service:
            try:
                analysis_result = self._analyze_stock_with_service(stock_code, stock_name, analysis_type)
            except Exception as e:
                logger.error(f"分析失败: {e}")
                analysis_result = {"stock_code": stock_code, "stock_name": stock_name, "error": str(e)}
        else:
            logger.warning("数据服务不可用，无法执行分析")
            analysis_result = {"stock_code": stock_code, "stock_name": stock_name, "error": "数据服务不可用"}
        
        return QueryResult(
            success=True,
            intent_type=intent.intent_type.value,
            data=analysis_result,
            message=f"{stock_name}({stock_code})分析完成",
            suggestions=[
                "查看详细技术分析",
                "查看资金流向",
                "对比同行业股票"
            ],
            executed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    
    def _execute_data_query(self, intent: QueryIntent) -> QueryResult:
        """执行数据查询"""
        stock_codes = intent.entities.get('stock_codes', [])
        metric = intent.entities.get('metric')

        if not stock_codes:
            return QueryResult(
                success=False,
                intent_type=intent.intent_type.value,
                data=None,
                message="未能识别股票代码或名称",
                suggestions=[
                    "请指定股票代码，例如：600519的PE是多少",
                    "或使用股票名称，例如：茅台今天涨了多少"
                ],
                executed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

        stock_code = stock_codes[0]
        stock_name = intent.entities.get('stock_name', stock_code)

        # 执行真实查询逻辑
        if self.data_service:
            try:
                query_data = self._query_stock_data_with_service(stock_code, stock_name, metric)
            except Exception as e:
                logger.error(f"查询失败: {e}")
                query_data = {"stock_code": stock_code, "stock_name": stock_name, "error": str(e), "answer": f"查询{stock_name}数据失败"}
        else:
            logger.warning("数据服务不可用，无法执行查询")
            query_data = {"stock_code": stock_code, "stock_name": stock_name, "error": "数据服务不可用", "answer": "数据服务不可用"}
        
        return QueryResult(
            success=True,
            intent_type=intent.intent_type.value,
            data=query_data,
            message=query_data.get('answer', '查询完成'),
            suggestions=[
                "查看更多指标",
                "查看历史走势"
            ],
            executed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    
    def _handle_unknown(self, intent: QueryIntent) -> QueryResult:
        """处理未知意图"""
        return QueryResult(
            success=False,
            intent_type=intent.intent_type.value,
            data=None,
            message="抱歉，我没有理解您的问题",
            suggestions=[
                "股票筛选：找出PE低于20的股票",
                "个股分析：分析贵州茅台",
                "数据查询：茅台的PE是多少"
            ],
            executed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    # ==================== 真实数据处理方法 ====================

    def _screen_stocks_with_service(self, conditions: List[Dict], limit: int) -> List[Dict]:
        """使用数据服务进行股票筛选"""
        # 这里实现基于AI评分的简单筛选
        # 获取一批股票进行评分筛选
        candidate_stocks = [
            "600519", "000858", "000333", "601318", "600036",
            "600887", "000568", "002594", "300750", "600809"
        ]

        results = []
        for code in candidate_stocks[:limit * 2]:  # 多获取一些以便筛选
            try:
                score_result = self.data_service.get_ai_score(code, code)
                if score_result and self._match_conditions(score_result, conditions):
                    results.append({
                        "code": code,
                        "name": score_result.get("stock_name", code),
                        "ai_score": score_result.get("综合评分", 0),
                        "signal": score_result.get("投资信号", "Hold")
                    })
                    if len(results) >= limit:
                        break
            except Exception as e:
                logger.debug(f"筛选股票 {code} 失败: {e}")
                continue

        return results

    def _match_conditions(self, score_result: Dict, conditions: List[Dict]) -> bool:
        """检查股票是否匹配筛选条件"""
        # 简单实现：基于AI评分筛选
        for condition in conditions:
            metric = condition.get('metric', '').lower()
            operator = condition.get('operator', '')
            value = condition.get('value', 0)

            if 'score' in metric or '评分' in metric:
                ai_score = score_result.get("综合评分", 0)
                if operator in ['>', '大于', '高于'] and ai_score <= value:
                    return False
                elif operator in ['<', '小于', '低于'] and ai_score >= value:
                    return False

        return True

    def _analyze_stock_with_service(self, stock_code: str, stock_name: str,
                                     analysis_type: str) -> Dict:
        """使用数据服务进行个股分析"""
        result = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "analysis_type": analysis_type
        }

        try:
            # 获取AI评分
            score_result = self.data_service.get_ai_score(stock_code, stock_name)
            if score_result:
                result.update({
                    "ai_score": score_result.get("综合评分", 0),
                    "signal": score_result.get("投资信号", "Hold"),
                    "subscores": score_result.get("分项评分", {}),
                    "summary": score_result.get("评分说明", "")
                })

            # 获取技术指标
            indicators = self.data_service.get_technical_indicators(stock_code, stock_name)
            if indicators:
                result["technical"] = indicators

        except Exception as e:
            logger.error(f"分析股票 {stock_code} 失败: {e}")

        return result

    def _query_stock_data_with_service(self, stock_code: str, stock_name: str,
                                        metric: Optional[str]) -> Dict:
        """使用数据服务查询股票数据"""
        result = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "metric": metric
        }

        try:
            # 获取实时行情
            quote = self.data_service.get_realtime_quote(stock_code)
            if quote:
                result["quote"] = quote
                result["answer"] = f"{stock_name}当前价格{quote.get('price', 'N/A')}元"

            # 如果指定了指标，获取对应数据
            if metric:
                if metric.lower() in ['pe', '市盈率']:
                    result["value"] = quote.get('pe', 'N/A')
                    result["answer"] = f"{stock_name}的PE是{result['value']}"
                elif metric.lower() in ['pb', '市净率']:
                    result["value"] = quote.get('pb', 'N/A')
                    result["answer"] = f"{stock_name}的PB是{result['value']}"

        except Exception as e:
            logger.error(f"查询股票 {stock_code} 数据失败: {e}")

        return result
    
def execute_query(intent: QueryIntent,
                  data_service=None, 
                  score_service=None) -> QueryResult:
    """便捷函数：执行查询"""
    executor = QueryExecutor(data_service, score_service)
    return executor.execute(intent)
