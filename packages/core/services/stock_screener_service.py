"""
选股雷达服务
提供多条件股票筛选功能
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ScreeningCondition:
    """筛选条件"""
    metric: str  # 指标名称：pe, pb, roe, ai_score等
    operator: str  # 操作符：>, <, >=, <=, ==, between
    value: Any  # 值或值范围
    weight: float = 1.0  # 权重


@dataclass
class ScreeningStrategy:
    """筛选策略"""
    name: str
    description: str
    conditions: List[ScreeningCondition]
    sort_by: str = "ai_score"  # 排序字段
    sort_desc: bool = True  # 降序


class StockScreenerService:
    """
    选股雷达服务

    提供预设策略和自定义筛选功能
    """

    def __init__(self, data_service=None):
        """
        Args:
            data_service: 数据服务实例
        """
        if data_service is None:
            from services.stock_data_service import get_stock_service
            self.data_service = get_stock_service()
        else:
            self.data_service = data_service

        # 预设策略
        self.preset_strategies = self._init_preset_strategies()

    def _init_preset_strategies(self) -> Dict[str, ScreeningStrategy]:
        """初始化预设策略"""
        return {
            "value_investment": ScreeningStrategy(
                name="价值投资",
                description="低PE+高ROE+高股息",
                conditions=[
                    ScreeningCondition("pe", "<", 20),
                    ScreeningCondition("roe", ">", 15),
                    ScreeningCondition("dividend_yield", ">", 2),
                ]
            ),
            "growth_stock": ScreeningStrategy(
                name="成长优选",
                description="高营收增速+高利润增速",
                conditions=[
                    ScreeningCondition("revenue_growth", ">", 20),
                    ScreeningCondition("profit_growth", ">", 20),
                    ScreeningCondition("roe", ">", 15),
                ]
            ),
            "technical_breakout": ScreeningStrategy(
                name="技术突破",
                description="均线多头+放量突破",
                conditions=[
                    ScreeningCondition("ma_trend", "==", "bullish"),
                    ScreeningCondition("volume_ratio", ">", 1.5),
                    ScreeningCondition("price_change", ">", 0),
                ]
            ),
            "ai_high_score": ScreeningStrategy(
                name="AI高分股",
                description="AI评分大于7分",
                conditions=[
                    ScreeningCondition("ai_score", ">", 7.0),
                ],
                sort_by="ai_score",
                sort_desc=True
            ),
            "north_fund_favorite": ScreeningStrategy(
                name="北向青睐",
                description="北向资金持续流入",
                conditions=[
                    ScreeningCondition("north_fund_flow_5d", ">", 0),
                    ScreeningCondition("north_fund_holding_pct", ">", 1),
                ]
            ),
        }

    def screen_stocks(self,
                     strategy_name: Optional[str] = None,
                     custom_conditions: Optional[List[ScreeningCondition]] = None,
                     limit: int = 20) -> List[Dict[str, Any]]:
        """
        筛选股票

        Args:
            strategy_name: 预设策略名称
            custom_conditions: 自定义筛选条件
            limit: 返回数量限制

        Returns:
            筛选结果列表
        """
        # 确定使用的条件
        if strategy_name and strategy_name in self.preset_strategies:
            strategy = self.preset_strategies[strategy_name]
            conditions = strategy.conditions
            sort_by = strategy.sort_by
            sort_desc = strategy.sort_desc
        elif custom_conditions:
            conditions = custom_conditions
            sort_by = "ai_score"
            sort_desc = True
        else:
            logger.warning("未指定筛选条件，使用默认AI高分策略")
            return self.screen_stocks("ai_high_score", limit=limit)

        # 候选股票池（实际应该从数据库获取）
        candidate_stocks = self._get_candidate_stocks()

        # 执行筛选
        results = []
        for stock_code in candidate_stocks:
            try:
                # 获取股票数据
                stock_data = self._get_stock_screening_data(stock_code)

                # 检查是否满足所有条件
                if self._match_conditions(stock_data, conditions):
                    results.append(stock_data)

                    if len(results) >= limit * 2:  # 多获取一些以便排序后筛选
                        break
            except Exception as e:
                logger.debug(f"筛选股票 {stock_code} 失败: {e}")
                continue

        # 排序
        if sort_by in results[0] if results else {}:
            results.sort(key=lambda x: x.get(sort_by, 0), reverse=sort_desc)

        return results[:limit]

    def _get_candidate_stocks(self) -> List[str]:
        """获取候选股票池"""
        # 实际应该从数据库获取，这里返回常见股票
        return [
            "600519", "000858", "000333", "601318", "600036",
            "600887", "000568", "002594", "300750", "600809",
            "601888", "600276", "000001", "601166", "600030",
            "601398", "601328", "600000", "601288", "600016",
        ]

    def _get_stock_screening_data(self, stock_code: str) -> Dict[str, Any]:
        """获取股票筛选所需数据"""
        data = {
            "stock_code": stock_code,
            "stock_name": stock_code,
        }

        try:
            # 获取AI评分
            score_result = self.data_service.get_ai_score(stock_code, stock_code)
            if score_result:
                data["ai_score"] = score_result.get("综合评分", 0)
                data["signal"] = score_result.get("投资信号", "Hold")

                # 从分项评分中提取数据
                subscores = score_result.get("分项评分", {})
                data["technical_score"] = subscores.get("技术面评分", 0)
                data["fundamental_score"] = subscores.get("基本面评分", 0)
                data["fund_flow_score"] = subscores.get("资金面评分", 0)

            # 获取实时行情（包含PE/PB等）
            quote = self.data_service.get_realtime_quote(stock_code)
            if quote:
                data.update({
                    "price": quote.get("price", 0),
                    "change_pct": quote.get("change_pct", 0),
                    "pe": quote.get("pe", 0),
                    "pb": quote.get("pb", 0),
                    "market_cap": quote.get("market_cap", 0),
                })

        except Exception as e:
            logger.debug(f"获取股票 {stock_code} 数据失败: {e}")

        return data

    def _match_conditions(self, stock_data: Dict, conditions: List[ScreeningCondition]) -> bool:
        """检查股票是否满足筛选条件"""
        for condition in conditions:
            metric = condition.metric
            operator = condition.operator
            value = condition.value

            # 获取股票的指标值
            stock_value = stock_data.get(metric)
            if stock_value is None:
                return False

            # 比较
            try:
                if operator in [">", "大于", "高于"]:
                    if not (stock_value > value):
                        return False
                elif operator in ["<", "小于", "低于"]:
                    if not (stock_value < value):
                        return False
                elif operator in [">=", "大于等于"]:
                    if not (stock_value >= value):
                        return False
                elif operator in ["<=", "小于等于"]:
                    if not (stock_value <= value):
                        return False
                elif operator in ["==", "等于"]:
                    if not (stock_value == value):
                        return False
                elif operator == "between":
                    if isinstance(value, (list, tuple)) and len(value) == 2:
                        if not (value[0] <= stock_value <= value[1]):
                            return False
            except Exception as e:
                logger.debug(f"条件比较失败: {e}")
                return False

        return True

    def get_preset_strategies(self) -> Dict[str, Dict[str, Any]]:
        """获取所有预设策略"""
        return {
            name: {
                "name": strategy.name,
                "description": strategy.description,
                "conditions_count": len(strategy.conditions)
            }
            for name, strategy in self.preset_strategies.items()
        }
