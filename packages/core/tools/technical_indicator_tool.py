"""
技术指标工具
为CrewAI Agent提供技术指标计算能力
"""
from typing import Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

from packages.core.services.stock_data_service import get_stock_service


class TechnicalIndicatorInput(BaseModel):
    """技术指标工具输入"""
    stock_code: str = Field(..., description="股票代码，如600519")


class TechnicalIndicatorTool(BaseTool):
    """
    技术指标工具
    
    功能：
    - 计算均线（MA5/10/20/60）
    - 计算MACD（DIF/DEA/柱状图）
    - 计算RSI
    - 计算KDJ
    - 计算布林带
    - 计算ATR
    """
    
    name: str = "technical_indicator_tool"
    description: str = """
    计算股票的技术指标。
    
    支持的指标：
    - 均线：MA5、MA10、MA20、MA60
    - MACD：DIF、DEA、柱状图
    - RSI：14日RSI
    - KDJ：K、D、J值
    - 布林带：上轨、中轨、下轨
    - ATR：平均真实波幅
    
    返回所有指标的最新值和技术面分析。
    """
    args_schema: Type[BaseModel] = TechnicalIndicatorInput
    
    def _run(self, stock_code: str) -> str:
        """计算技术指标"""
        try:
            service = get_stock_service()
            
            # 获取技术指标
            indicators = service.calculate_indicators(stock_code)
            if not indicators:
                return f"无法计算{stock_code}的技术指标，请检查股票代码"
            
            # 构建输出
            output = [f"=== {stock_code} 技术指标 ==="]
            
            # 当前价格
            close = indicators.get('close', 0)
            change = indicators.get('price_change', 0)
            output.append(f"当前价格：{close:.2f}（{change*100:+.2f}%）")
            
            # 均线
            output.append("\n【均线系统】")
            for period in [5, 10, 20, 60]:
                ma = indicators.get(f'ma{period}')
                if ma:
                    diff = (close - ma) / ma * 100
                    output.append(f"MA{period}：{ma:.2f}（{diff:+.2f}%）")
            
            # 判断均线趋势
            ma5 = indicators.get('ma5', close)
            ma10 = indicators.get('ma10', close)
            ma20 = indicators.get('ma20', close)
            if close > ma5 > ma10 > ma20:
                output.append("趋势：多头排列 ↑")
            elif close < ma5 < ma10 < ma20:
                output.append("趋势：空头排列 ↓")
            else:
                output.append("趋势：震荡整理 →")
            
            # MACD
            output.append("\n【MACD】")
            dif = indicators.get('macd_dif', 0)
            dea = indicators.get('macd_dea', 0)
            hist = indicators.get('macd_hist', 0)
            output.append(f"DIF：{dif:.3f}")
            output.append(f"DEA：{dea:.3f}")
            output.append(f"柱状图：{hist:.3f}")
            if dif > dea:
                output.append("信号：金叉/多头")
            else:
                output.append("信号：死叉/空头")
            
            # RSI
            output.append("\n【RSI】")
            rsi = indicators.get('rsi', 50)
            output.append(f"RSI(14)：{rsi:.1f}")
            if rsi > 70:
                output.append("状态：超买区域，注意回调风险")
            elif rsi < 30:
                output.append("状态：超卖区域，可能反弹")
            else:
                output.append("状态：中性区域")
            
            # KDJ
            output.append("\n【KDJ】")
            k = indicators.get('kdj_k', 50)
            d = indicators.get('kdj_d', 50)
            j = indicators.get('kdj_j', 50)
            output.append(f"K：{k:.1f}  D：{d:.1f}  J：{j:.1f}")
            if k > d and j > 80:
                output.append("信号：高位金叉，注意风险")
            elif k < d and j < 20:
                output.append("信号：低位死叉，可能见底")
            
            # 布林带
            output.append("\n【布林带】")
            upper = indicators.get('boll_upper', 0)
            middle = indicators.get('boll_middle', 0)
            lower = indicators.get('boll_lower', 0)
            output.append(f"上轨：{upper:.2f}")
            output.append(f"中轨：{middle:.2f}")
            output.append(f"下轨：{lower:.2f}")
            if close > upper:
                output.append("位置：突破上轨，强势")
            elif close < lower:
                output.append("位置：跌破下轨，弱势")
            else:
                output.append(f"位置：轨道内运行")
            
            # ATR
            atr = indicators.get('atr', 0)
            if atr > 0:
                output.append(f"\n【波动率】ATR：{atr:.2f}（{atr/close*100:.2f}%）")
            
            # 成交量
            vol_ratio = indicators.get('volume_ratio', 1.0)
            output.append(f"\n【成交量】量比：{vol_ratio:.2f}")
            if vol_ratio > 2:
                output.append("状态：显著放量")
            elif vol_ratio > 1.5:
                output.append("状态：温和放量")
            elif vol_ratio < 0.5:
                output.append("状态：明显缩量")
            
            return "\n".join(output)
            
        except Exception as e:
            return f"技术指标计算失败：{str(e)}"
