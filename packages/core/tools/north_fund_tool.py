"""
北向资金追踪工具
提供北向资金流向、持仓分析等功能
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import logging

try:
    import akshare as ak
except ImportError:
    ak = None

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


@dataclass
class NorthFundFlow:
    """北向资金流向数据"""
    date: str
    north_money: float  # 北向资金净流入（亿元）
    sh_money: float     # 沪股通净流入
    sz_money: float     # 深股通净流入
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class NorthFundHolding:
    """北向资金持仓数据"""
    stock_code: str
    stock_name: str
    holding_shares: int      # 持股数量
    holding_value: float     # 持仓市值（亿元）
    holding_ratio: float     # 占流通股比例%
    change_shares: int       # 持股变动
    change_ratio: float      # 变动比例%
    
    def to_dict(self) -> Dict:
        return asdict(self)


class NorthFundTracker:
    """
    北向资金追踪器
    
    功能：
    1. 获取北向资金每日流向
    2. 获取个股北向资金持仓
    3. 获取北向资金持仓排名
    4. 分析北向资金流向趋势
    """
    
    def __init__(self):
        if ak is None:
            logger.warning("akshare未安装，北向资金功能不可用")
    
    def get_daily_flow(self, days: int = 30) -> List[NorthFundFlow]:
        """
        获取北向资金每日流向
        
        Args:
            days: 获取天数
            
        Returns:
            北向资金流向列表
        """
        if ak is None:
            logger.error("akshare未安装，无法获取北向资金数据")
            return []
        
        try:
            # 获取北向资金历史数据
            df = ak.stock_hsgt_north_net_flow_in_em()
            
            flows = []
            for _, row in df.tail(days).iterrows():
                flows.append(NorthFundFlow(
                    date=str(row.get('日期', '')),
                    north_money=float(row.get('北向资金', 0)) / 100000000,  # 转为亿元
                    sh_money=float(row.get('沪股通', 0)) / 100000000,
                    sz_money=float(row.get('深股通', 0)) / 100000000
                ))
            
            return flows
        except Exception as e:
            logger.error(f"获取北向资金流向失败: {e}")
            return []
    
    def get_stock_holding(self, stock_code: str) -> Optional[NorthFundHolding]:
        """
        获取个股北向资金持仓
        
        Args:
            stock_code: 股票代码
            
        Returns:
            持仓数据
        """
        if ak is None:
            logger.error("akshare未安装，无法获取北向资金持仓数据")
            return None
        
        try:
            # 获取北向资金持股数据
            # 根据股票代码判断是沪股通还是深股通
            if stock_code.startswith('6'):
                df = ak.stock_hsgt_hold_stock_em(market="沪股通")
            else:
                df = ak.stock_hsgt_hold_stock_em(market="深股通")
            
            # 查找对应股票
            stock_df = df[df['代码'] == stock_code]
            if stock_df.empty:
                return None
            
            row = stock_df.iloc[0]
            return NorthFundHolding(
                stock_code=stock_code,
                stock_name=str(row.get('名称', '')),
                holding_shares=int(row.get('持股数量', 0)),
                holding_value=float(row.get('持股市值', 0)) / 100000000,
                holding_ratio=float(row.get('持股占比', 0)),
                change_shares=int(row.get('持股变动', 0)),
                change_ratio=float(row.get('持股变动比例', 0))
            )
        except Exception as e:
            logger.error(f"获取个股北向持仓失败: {e}")
            return None
    
    def get_top_holdings(self, top_n: int = 20, 
                         market: str = "all") -> List[NorthFundHolding]:
        """
        获取北向资金持仓排名
        
        Args:
            top_n: 返回数量
            market: 市场 "sh"/"sz"/"all"
            
        Returns:
            持仓排名列表
        """
        if ak is None:
            logger.error("akshare未安装，无法获取北向资金持仓排名")
            return []
        
        try:
            holdings = []
            
            if market in ["sh", "all"]:
                df_sh = ak.stock_hsgt_hold_stock_em(market="沪股通")
                for _, row in df_sh.head(top_n).iterrows():
                    holdings.append(self._row_to_holding(row))
            
            if market in ["sz", "all"]:
                df_sz = ak.stock_hsgt_hold_stock_em(market="深股通")
                for _, row in df_sz.head(top_n).iterrows():
                    holdings.append(self._row_to_holding(row))
            
            # 按持仓市值排序
            holdings.sort(key=lambda x: x.holding_value, reverse=True)
            return holdings[:top_n]
            
        except Exception as e:
            logger.error(f"获取北向持仓排名失败: {e}")
            return []
    
    def get_flow_trend(self, days: int = 20) -> Dict[str, Any]:
        """
        分析北向资金流向趋势
        
        Args:
            days: 分析天数
            
        Returns:
            趋势分析结果
        """
        flows = self.get_daily_flow(days)
        
        if not flows:
            return {"error": "无法获取数据"}
        
        # 计算统计指标
        total_flow = sum(f.north_money for f in flows)
        avg_flow = total_flow / len(flows)
        
        # 连续流入/流出天数
        consecutive_in = 0
        consecutive_out = 0
        for f in reversed(flows):
            if f.north_money > 0:
                consecutive_in += 1
                if consecutive_out > 0:
                    break
            else:
                consecutive_out += 1
                if consecutive_in > 0:
                    break
        
        # 最近5日流向
        recent_5d = sum(f.north_money for f in flows[-5:]) if len(flows) >= 5 else total_flow
        
        # 判断趋势
        if recent_5d > 50:
            trend = "大幅流入"
            signal = "看多"
        elif recent_5d > 0:
            trend = "小幅流入"
            signal = "偏多"
        elif recent_5d > -50:
            trend = "小幅流出"
            signal = "偏空"
        else:
            trend = "大幅流出"
            signal = "看空"
        
        return {
            "period_days": days,
            "total_flow": round(total_flow, 2),
            "avg_daily_flow": round(avg_flow, 2),
            "recent_5d_flow": round(recent_5d, 2),
            "consecutive_inflow_days": consecutive_in,
            "consecutive_outflow_days": consecutive_out,
            "trend": trend,
            "signal": signal,
            "latest_date": flows[-1].date if flows else None
        }
    
    def _row_to_holding(self, row) -> NorthFundHolding:
        """将DataFrame行转换为持仓对象"""
        return NorthFundHolding(
            stock_code=str(row.get('代码', '')),
            stock_name=str(row.get('名称', '')),
            holding_shares=int(row.get('持股数量', 0)),
            holding_value=float(row.get('持股市值', 0)) / 100000000,
            holding_ratio=float(row.get('持股占比', 0)),
            change_shares=int(row.get('持股变动', 0)),
            change_ratio=float(row.get('持股变动比例', 0))
        )


# CrewAI工具定义
class NorthFundFlowInput(BaseModel):
    """北向资金流向查询输入"""
    days: int = Field(default=20, description="查询天数")


class NorthFundFlowTool(BaseTool):
    """北向资金流向工具"""
    name: str = "north_fund_flow"
    description: str = "获取北向资金每日流向数据和趋势分析"
    args_schema: type[BaseModel] = NorthFundFlowInput
    
    def _run(self, days: int = 20) -> str:
        tracker = NorthFundTracker()
        trend = tracker.get_flow_trend(days)
        
        result = f"""
北向资金流向分析（近{days}日）：
- 累计净流入：{trend['total_flow']}亿元
- 日均净流入：{trend['avg_daily_flow']}亿元
- 近5日净流入：{trend['recent_5d_flow']}亿元
- 连续流入天数：{trend['consecutive_inflow_days']}天
- 连续流出天数：{trend['consecutive_outflow_days']}天
- 趋势判断：{trend['trend']}
- 信号：{trend['signal']}
"""
        return result


class NorthFundHoldingInput(BaseModel):
    """北向资金持仓查询输入"""
    stock_code: str = Field(description="股票代码")


class NorthFundHoldingTool(BaseTool):
    """北向资金持仓工具"""
    name: str = "north_fund_holding"
    description: str = "获取个股北向资金持仓情况"
    args_schema: type[BaseModel] = NorthFundHoldingInput
    
    def _run(self, stock_code: str) -> str:
        tracker = NorthFundTracker()
        holding = tracker.get_stock_holding(stock_code)
        
        if not holding:
            return f"未找到{stock_code}的北向资金持仓数据"
        
        result = f"""
{holding.stock_name}({holding.stock_code})北向资金持仓：
- 持股数量：{holding.holding_shares:,}股
- 持仓市值：{holding.holding_value:.2f}亿元
- 占流通股比例：{holding.holding_ratio:.2f}%
- 持股变动：{holding.change_shares:+,}股
- 变动比例：{holding.change_ratio:+.2f}%
"""
        return result


class NorthFundTopInput(BaseModel):
    """北向资金持仓排名输入"""
    top_n: int = Field(default=10, description="返回数量")


class NorthFundTopTool(BaseTool):
    """北向资金持仓排名工具"""
    name: str = "north_fund_top"
    description: str = "获取北向资金持仓市值排名前N的股票"
    args_schema: type[BaseModel] = NorthFundTopInput
    
    def _run(self, top_n: int = 10) -> str:
        tracker = NorthFundTracker()
        holdings = tracker.get_top_holdings(top_n)
        
        result = f"北向资金持仓市值Top{top_n}：\n"
        for i, h in enumerate(holdings, 1):
            result += f"{i}. {h.stock_name}({h.stock_code}) - 市值{h.holding_value:.1f}亿 占比{h.holding_ratio:.1f}%\n"
        
        return result


# 便捷函数
def get_north_fund_tracker() -> NorthFundTracker:
    """获取北向资金追踪器"""
    return NorthFundTracker()
