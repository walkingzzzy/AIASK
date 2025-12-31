"""
组合管理服务
提供持仓管理、收益统计、风险分析功能
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """持仓"""
    stock_code: str
    stock_name: str
    quantity: int  # 持仓数量
    cost_price: float  # 成本价
    current_price: float = 0.0  # 当前价
    market_value: float = 0.0  # 市值
    profit_loss: float = 0.0  # 盈亏
    profit_loss_pct: float = 0.0  # 盈亏比例
    weight: float = 0.0  # 仓位占比
    add_date: str = ""  # 添加日期

    def to_dict(self) -> Dict:
        data = asdict(self)
        # 添加总成本字段供风险监控使用
        data['cost'] = self.cost_price * self.quantity
        return data


@dataclass
class PortfolioSummary:
    """组合摘要"""
    total_market_value: float  # 总市值
    total_cost: float  # 总成本
    total_profit_loss: float  # 总盈亏
    total_profit_loss_pct: float  # 总盈亏比例
    position_count: int  # 持仓数量
    today_profit_loss: float = 0.0  # 今日盈亏
    today_profit_loss_pct: float = 0.0  # 今日盈亏比例

    def to_dict(self) -> Dict:
        return asdict(self)


class PortfolioService:
    """
    组合管理服务

    提供持仓管理、收益统计、风险分析功能
    """

    def __init__(self, data_service=None, portfolio_file: Optional[str] = None):
        """
        Args:
            data_service: 数据服务实例
            portfolio_file: 组合数据文件路径
        """
        if data_service is None:
            from services.stock_data_service import get_stock_service
            self.data_service = get_stock_service()
        else:
            self.data_service = data_service

        # 组合数据文件
        if portfolio_file is None:
            data_dir = Path(__file__).parent.parent.parent.parent.parent / "data"
            data_dir.mkdir(exist_ok=True)
            portfolio_file = str(data_dir / "portfolio.json")

        self.portfolio_file = portfolio_file
        self.positions: List[Position] = []
        self._load_portfolio()

    def _load_portfolio(self):
        """加载组合数据"""
        try:
            if Path(self.portfolio_file).exists():
                with open(self.portfolio_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.positions = [Position(**p) for p in data.get('positions', [])]
                logger.info(f"加载组合数据成功，共{len(self.positions)}个持仓")
        except Exception as e:
            logger.error(f"加载组合数据失败: {e}")
            self.positions = []

    def _save_portfolio(self):
        """保存组合数据"""
        try:
            data = {
                'positions': [p.to_dict() for p in self.positions],
                'updated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(self.portfolio_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("保存组合数据成功")
        except Exception as e:
            logger.error(f"保存组合数据失败: {e}")

    def add_position(self, stock_code: str, stock_name: str,
                    quantity: int, cost_price: float) -> Position:
        """
        添加持仓

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            quantity: 数量
            cost_price: 成本价

        Returns:
            Position对象
        """
        # 检查是否已存在
        existing = self.get_position(stock_code)
        if existing:
            # 更新持仓（加仓）
            total_cost = existing.cost_price * existing.quantity + cost_price * quantity
            total_quantity = existing.quantity + quantity
            existing.cost_price = total_cost / total_quantity
            existing.quantity = total_quantity
            position = existing
        else:
            # 新建持仓
            position = Position(
                stock_code=stock_code,
                stock_name=stock_name,
                quantity=quantity,
                cost_price=cost_price,
                add_date=datetime.now().strftime("%Y-%m-%d")
            )
            self.positions.append(position)

        self._save_portfolio()
        return position

    def remove_position(self, stock_code: str) -> bool:
        """
        删除持仓

        Args:
            stock_code: 股票代码

        Returns:
            是否成功
        """
        self.positions = [p for p in self.positions if p.stock_code != stock_code]
        self._save_portfolio()
        return True

    def get_position(self, stock_code: str) -> Optional[Position]:
        """获取单个持仓"""
        for position in self.positions:
            if position.stock_code == stock_code:
                return position
        return None

    def get_all_positions(self, update_prices: bool = True) -> List[Position]:
        """
        获取所有持仓

        Args:
            update_prices: 是否更新最新价格

        Returns:
            持仓列表
        """
        if update_prices:
            self._update_positions_prices()

        return self.positions

    def _update_positions_prices(self):
        """更新所有持仓的最新价格"""
        for position in self.positions:
            try:
                quote = self.data_service.get_realtime_quote(position.stock_code)
                if quote:
                    position.current_price = quote.get('price', position.cost_price)
                    position.market_value = position.current_price * position.quantity
                    position.profit_loss = position.market_value - (position.cost_price * position.quantity)
                    if position.cost_price > 0:
                        position.profit_loss_pct = (position.profit_loss / (position.cost_price * position.quantity)) * 100
            except Exception as e:
                logger.debug(f"更新持仓 {position.stock_code} 价格失败: {e}")

    def get_portfolio_summary(self) -> PortfolioSummary:
        """
        获取组合摘要

        Returns:
            PortfolioSummary对象
        """
        self._update_positions_prices()

        total_market_value = sum(p.market_value for p in self.positions)
        total_cost = sum(p.cost_price * p.quantity for p in self.positions)
        total_profit_loss = total_market_value - total_cost
        total_profit_loss_pct = (total_profit_loss / total_cost * 100) if total_cost > 0 else 0

        # 计算仓位占比
        for position in self.positions:
            position.weight = (position.market_value / total_market_value * 100) if total_market_value > 0 else 0

        return PortfolioSummary(
            total_market_value=total_market_value,
            total_cost=total_cost,
            total_profit_loss=total_profit_loss,
            total_profit_loss_pct=total_profit_loss_pct,
            position_count=len(self.positions)
        )

    def get_risk_analysis(self) -> Dict[str, Any]:
        """
        获取风险分析

        Returns:
            风险分析结果
        """
        self._update_positions_prices()

        # 计算集中度
        total_value = sum(p.market_value for p in self.positions)
        max_position_weight = max([p.market_value / total_value for p in self.positions]) * 100 if self.positions else 0

        # 计算行业集中度（简化版）
        # 实际应该从数据服务获取行业信息
        industry_concentration = 0.0

        # 风险等级评估
        risk_level = "低"
        if max_position_weight > 30:
            risk_level = "高"
        elif max_position_weight > 20:
            risk_level = "中"

        return {
            "max_position_weight": round(max_position_weight, 2),
            "industry_concentration": round(industry_concentration, 2),
            "risk_level": risk_level,
            "position_count": len(self.positions),
            "suggestions": self._get_risk_suggestions(max_position_weight)
        }

    def _get_risk_suggestions(self, max_weight: float) -> List[str]:
        """获取风险建议"""
        suggestions = []

        if max_weight > 30:
            suggestions.append("单只股票仓位过高，建议分散投资")
        elif max_weight > 20:
            suggestions.append("注意控制单只股票仓位")

        if len(self.positions) < 3:
            suggestions.append("持仓数量较少，建议增加持仓分散风险")
        elif len(self.positions) > 15:
            suggestions.append("持仓数量较多，建议精简持仓")

        if not suggestions:
            suggestions.append("组合风险控制良好")

        return suggestions
