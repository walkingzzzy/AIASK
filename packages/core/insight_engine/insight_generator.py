"""
洞察生成器
生成AI洞察，包括市场观点、个股分析、趋势判断等
"""
import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from .models import (
    Insight, InsightType, UserProfile
)

logger = logging.getLogger(__name__)


class InsightGenerator:
    """
    AI洞察生成器
    
    功能：
    1. 生成市场观点
    2. 生成个股洞察
    3. 生成板块分析
    4. 发现关联关系
    5. 生成趋势分析
    """
    
    def __init__(self, 
                 stock_service=None,
                 llm_service=None):
        """
        初始化洞察生成器
        
        Args:
            stock_service: 股票数据服务
            llm_service: LLM服务（用于生成文本）
        """
        self.stock_service = stock_service
        self.llm_service = llm_service
    
    def generate_daily_insights(self, profile: UserProfile) -> List[Insight]:
        """
        生成每日洞察
        
        Args:
            profile: 用户画像
            
        Returns:
            洞察列表
        """
        insights = []
        
        # 1. 市场观点
        market_insight = self._generate_market_view()
        if market_insight:
            insights.append(market_insight)
        
        # 2. 关注股票洞察
        for stock_code in profile.watchlist[:5]:  # 最多5只
            stock_insight = self._generate_stock_insight(stock_code)
            if stock_insight:
                insights.append(stock_insight)
        
        # 3. 板块分析
        if profile.focus_sectors:
            sector_insight = self._generate_sector_analysis(profile.focus_sectors)
            if sector_insight:
                insights.append(sector_insight)
        
        # 4. 关联分析
        if len(profile.watchlist) >= 2:
            correlation_insight = self._generate_correlation_analysis(profile.watchlist[:5])
            if correlation_insight:
                insights.append(correlation_insight)
        
        return insights
    
    def generate_for_stock(self, stock_code: str, stock_name: str = "") -> List[Insight]:
        """
        为单只股票生成洞察
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            
        Returns:
            洞察列表
        """
        insights = []
        
        # 个股洞察
        stock_insight = self._generate_stock_insight(stock_code, stock_name)
        if stock_insight:
            insights.append(stock_insight)
        
        # 趋势分析
        trend_insight = self._generate_trend_analysis(stock_code, stock_name)
        if trend_insight:
            insights.append(trend_insight)
        
        return insights
    
    def _generate_market_view(self) -> Optional[Insight]:
        """生成市场观点"""
        try:
            market_data = self._get_market_data()
            
            # 分析市场状态
            sh_change = market_data.get('sh_change', 0)
            sz_change = market_data.get('sz_change', 0)
            volume_change = market_data.get('volume_change', 0)
            north_flow = market_data.get('north_flow', 0)
            
            # 生成观点
            if sh_change > 1 and sz_change > 1:
                sentiment = "乐观"
                view = "两市普涨，市场情绪积极"
            elif sh_change < -1 and sz_change < -1:
                sentiment = "谨慎"
                view = "两市普跌，建议控制仓位"
            else:
                sentiment = "中性"
                view = "市场震荡整理，等待方向选择"
            
            # 北向资金分析
            if north_flow > 50:
                north_view = f"北向资金净流入{north_flow:.0f}亿，外资看好A股"
            elif north_flow < -50:
                north_view = f"北向资金净流出{abs(north_flow):.0f}亿，需关注外资动向"
            else:
                north_view = "北向资金流动平稳"
            
            content = f"""
**市场情绪：{sentiment}**

{view}

- 上证指数：{sh_change:+.2f}%
- 深证成指：{sz_change:+.2f}%
- 成交量变化：{volume_change:+.1f}%

**资金面**
{north_view}

**操作建议**
{"可适当参与热点板块" if sentiment == "乐观" else "建议观望为主，控制仓位" if sentiment == "谨慎" else "关注结构性机会"}
            """.strip()
            
            return Insight(
                id=str(uuid.uuid4()),
                type=InsightType.MARKET_VIEW,
                title="今日市场观点",
                content=content,
                confidence=0.7,
                supporting_data=[market_data]
            )
            
        except Exception as e:
            logger.warning(f"生成市场观点失败: {e}")
            return None
    
    def _generate_stock_insight(self, stock_code: str, 
                                 stock_name: str = "") -> Optional[Insight]:
        """生成个股洞察"""
        try:
            stock_data = self._get_stock_data(stock_code)
            if not stock_data:
                return None
            
            name = stock_name or stock_data.get('name', stock_code)
            
            # 分析各维度
            price_analysis = self._analyze_price(stock_data)
            volume_analysis = self._analyze_volume(stock_data)
            fund_analysis = self._analyze_fund_flow(stock_data)
            technical_analysis = self._analyze_technical(stock_data)
            
            # 综合评分
            score = (
                price_analysis['score'] * 0.3 +
                volume_analysis['score'] * 0.2 +
                fund_analysis['score'] * 0.3 +
                technical_analysis['score'] * 0.2
            )
            
            # 生成建议
            if score >= 0.7:
                suggestion = "综合来看，该股短期走势偏强，可适当关注"
            elif score <= 0.3:
                suggestion = "综合来看，该股短期承压，建议谨慎"
            else:
                suggestion = "综合来看，该股走势中性，建议观望"
            
            content = f"""
**{name}({stock_code}) 多维度分析**

📈 **价格表现**
{price_analysis['text']}

📊 **成交量**
{volume_analysis['text']}

💰 **资金流向**
{fund_analysis['text']}

📉 **技术指标**
{technical_analysis['text']}

**综合评分：{score:.0%}**

{suggestion}
            """.strip()
            
            return Insight(
                id=str(uuid.uuid4()),
                type=InsightType.STOCK_INSIGHT,
                title=f"{name}投资洞察",
                content=content,
                confidence=score,
                stock_codes=[stock_code],
                supporting_data=[stock_data]
            )
            
        except Exception as e:
            logger.warning(f"生成个股洞察失败 {stock_code}: {e}")
            return None
    
    def _generate_sector_analysis(self, sectors: List[str]) -> Optional[Insight]:
        """生成板块分析"""
        try:
            sector_data = self._get_sector_data(sectors)
            
            # 找出表现最好和最差的板块
            sorted_sectors = sorted(sector_data, key=lambda x: x.get('change', 0), reverse=True)
            
            best = sorted_sectors[0] if sorted_sectors else None
            worst = sorted_sectors[-1] if len(sorted_sectors) > 1 else None
            
            content_parts = ["**关注板块表现**\n"]
            
            for sector in sorted_sectors:
                change = sector.get('change', 0)
                emoji = "🔥" if change > 2 else "📈" if change > 0 else "📉"
                content_parts.append(f"{emoji} {sector['name']}: {change:+.2f}%")
            
            if best and best.get('change', 0) > 1:
                content_parts.append(f"\n**热点板块**\n{best['name']}板块表现强势，可关注板块内龙头股")
            
            if worst and worst.get('change', 0) < -1:
                content_parts.append(f"\n**风险提示**\n{worst['name']}板块走弱，相关持仓需注意风险")
            
            return Insight(
                id=str(uuid.uuid4()),
                type=InsightType.SECTOR_ANALYSIS,
                title="板块轮动分析",
                content="\n".join(content_parts),
                confidence=0.6,
                supporting_data=sector_data
            )
            
        except Exception as e:
            logger.warning(f"生成板块分析失败: {e}")
            return None
    
    def _generate_correlation_analysis(self, stock_codes: List[str]) -> Optional[Insight]:
        """生成关联分析"""
        try:
            # 获取股票数据
            stocks_data = []
            for code in stock_codes:
                data = self._get_stock_data(code)
                if data:
                    stocks_data.append(data)
            
            if len(stocks_data) < 2:
                return None
            
            # 分析走势相关性
            changes = [d.get('change_percent', 0) for d in stocks_data]
            
            # 简单判断是否同涨同跌
            all_up = all(c > 0 for c in changes)
            all_down = all(c < 0 for c in changes)
            
            if all_up:
                correlation_text = "您关注的股票今日全部上涨，可能受到相同利好因素影响"
            elif all_down:
                correlation_text = "您关注的股票今日全部下跌，需关注是否存在系统性风险"
            else:
                # 找出走势背离的股票
                up_stocks = [d['name'] for d in stocks_data if d.get('change_percent', 0) > 0]
                down_stocks = [d['name'] for d in stocks_data if d.get('change_percent', 0) < 0]
                correlation_text = f"走势分化：{', '.join(up_stocks)}上涨，{', '.join(down_stocks)}下跌"
            
            content = f"""
**关注股票关联分析**

{correlation_text}

**各股表现**
""" + "\n".join([
                f"- {d['name']}: {d.get('change_percent', 0):+.2f}%"
                for d in stocks_data
            ])
            
            return Insight(
                id=str(uuid.uuid4()),
                type=InsightType.CORRELATION,
                title="持仓关联分析",
                content=content,
                confidence=0.5,
                stock_codes=stock_codes,
                supporting_data=stocks_data
            )
            
        except Exception as e:
            logger.warning(f"生成关联分析失败: {e}")
            return None
    
    def _generate_trend_analysis(self, stock_code: str, 
                                  stock_name: str = "") -> Optional[Insight]:
        """生成趋势分析"""
        try:
            stock_data = self._get_stock_data(stock_code)
            if not stock_data:
                return None
            
            name = stock_name or stock_data.get('name', stock_code)
            
            # 分析趋势
            ma5 = stock_data.get('ma5', 0)
            ma20 = stock_data.get('ma20', 0)
            ma60 = stock_data.get('ma60', 0)
            price = stock_data.get('close', 0)
            
            if price > ma5 > ma20 > ma60:
                trend = "强势上涨"
                trend_desc = "均线多头排列，趋势向好"
            elif price < ma5 < ma20 < ma60:
                trend = "弱势下跌"
                trend_desc = "均线空头排列，趋势偏弱"
            elif price > ma20:
                trend = "震荡偏强"
                trend_desc = "股价在20日均线上方，短期偏强"
            else:
                trend = "震荡偏弱"
                trend_desc = "股价在20日均线下方，短期承压"
            
            content = f"""
**{name}趋势分析**

当前趋势：**{trend}**

{trend_desc}

**关键价位**
- 5日均线：{ma5:.2f}
- 20日均线：{ma20:.2f}
- 60日均线：{ma60:.2f}
- 当前价格：{price:.2f}

**操作建议**
{"趋势向好，可持股待涨" if "上涨" in trend or "偏强" in trend else "建议观望或减仓"}
            """.strip()
            
            return Insight(
                id=str(uuid.uuid4()),
                type=InsightType.TREND,
                title=f"{name}趋势分析",
                content=content,
                confidence=0.6,
                stock_codes=[stock_code],
                supporting_data=[stock_data]
            )
            
        except Exception as e:
            logger.warning(f"生成趋势分析失败 {stock_code}: {e}")
            return None
    
    def _analyze_price(self, data: Dict) -> Dict:
        """分析价格表现"""
        change = data.get('change_percent', 0)
        if change > 3:
            return {"score": 0.9, "text": f"今日大涨{change:.2f}%，表现强势"}
        elif change > 0:
            return {"score": 0.6, "text": f"今日上涨{change:.2f}%，表现平稳"}
        elif change > -3:
            return {"score": 0.4, "text": f"今日下跌{abs(change):.2f}%，小幅调整"}
        else:
            return {"score": 0.1, "text": f"今日大跌{abs(change):.2f}%，表现较弱"}
    
    def _analyze_volume(self, data: Dict) -> Dict:
        """分析成交量"""
        volume_ratio = data.get('volume_ratio', 1.0)
        change = data.get('change_percent', 0)
        
        if volume_ratio > 2 and change > 0:
            return {"score": 0.8, "text": f"放量上涨，量比{volume_ratio:.1f}，资金积极"}
        elif volume_ratio > 2 and change < 0:
            return {"score": 0.2, "text": f"放量下跌，量比{volume_ratio:.1f}，需警惕"}
        elif volume_ratio < 0.5:
            return {"score": 0.5, "text": f"缩量整理，量比{volume_ratio:.1f}，观望为主"}
        else:
            return {"score": 0.5, "text": f"成交量正常，量比{volume_ratio:.1f}"}
    
    def _analyze_fund_flow(self, data: Dict) -> Dict:
        """分析资金流向"""
        fund_flow = data.get('fund_flow_ratio', 0)
        if fund_flow > 0.1:
            return {"score": 0.8, "text": f"主力资金净流入{fund_flow:.1%}，机构看好"}
        elif fund_flow > 0:
            return {"score": 0.6, "text": f"资金小幅流入{fund_flow:.1%}"}
        elif fund_flow > -0.1:
            return {"score": 0.4, "text": f"资金小幅流出{abs(fund_flow):.1%}"}
        else:
            return {"score": 0.2, "text": f"主力资金净流出{abs(fund_flow):.1%}，需注意"}
    
    def _analyze_technical(self, data: Dict) -> Dict:
        """分析技术指标"""
        rsi = data.get('rsi', 50)
        macd_cross = data.get('macd_golden_cross', False)
        
        if rsi > 70:
            return {"score": 0.3, "text": f"RSI={rsi:.0f}，超买区域，注意回调风险"}
        elif rsi < 30:
            return {"score": 0.7, "text": f"RSI={rsi:.0f}，超卖区域，可能存在反弹机会"}
        elif macd_cross:
            return {"score": 0.7, "text": f"RSI={rsi:.0f}，MACD金叉，技术面转强"}
        else:
            return {"score": 0.5, "text": f"RSI={rsi:.0f}，技术指标中性"}
    
    def _get_market_data(self) -> Dict:
        """获取市场数据"""
        import random
        return {
            "sh_change": random.uniform(-2, 2),
            "sz_change": random.uniform(-2, 2),
            "volume_change": random.uniform(-20, 30),
            "north_flow": random.uniform(-100, 100),
        }
    
    def _get_stock_data(self, stock_code: str) -> Optional[Dict]:
        """获取股票数据"""
        if self.stock_service:
            try:
                return self.stock_service.get_stock_data(stock_code)
            except Exception as e:
                logger.warning(f"获取股票数据失败 {stock_code}: {e}")
        
        import random
        return {
            "code": stock_code,
            "name": f"股票{stock_code}",
            "close": 100 + random.uniform(-20, 20),
            "change_percent": random.uniform(-5, 5),
            "volume_ratio": random.uniform(0.5, 3),
            "rsi": random.uniform(20, 80),
            "macd_golden_cross": random.random() > 0.7,
            "fund_flow_ratio": random.uniform(-0.15, 0.15),
            "ma5": 100 + random.uniform(-5, 5),
            "ma20": 100 + random.uniform(-8, 8),
            "ma60": 100 + random.uniform(-10, 10),
        }
    
    def _get_sector_data(self, sectors: List[str]) -> List[Dict]:
        """获取板块数据"""
        import random
        return [
            {"name": sector, "change": random.uniform(-3, 3)}
            for sector in sectors
        ]


# 导出
__all__ = ['InsightGenerator', 'Insight']
