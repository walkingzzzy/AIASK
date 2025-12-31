"""
机会发现引擎
主动发现投资机会，包括买入信号、相似股票、板块轮动等
"""
import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from .models import (
    Opportunity, OpportunityType, Urgency, UserProfile
)

logger = logging.getLogger(__name__)


class OpportunityDetector:
    """
    机会发现引擎
    
    功能：
    1. 检测关注股票的买入信号
    2. 发现相似股票推荐
    3. 检测板块轮动机会
    4. 识别技术形态突破
    """
    
    # 技术指标阈值
    THRESHOLDS = {
        "rsi_oversold": 30,           # RSI超卖
        "rsi_overbought": 70,         # RSI超买
        "macd_golden_cross": True,    # MACD金叉
        "volume_surge": 2.0,          # 成交量放大倍数
        "price_breakout": 0.03,       # 突破幅度
        "fund_inflow_threshold": 0.1, # 资金流入阈值
    }
    
    def __init__(self, 
                 stock_service=None,
                 retriever=None):
        """
        初始化机会发现引擎
        
        Args:
            stock_service: 股票数据服务
            retriever: 向量检索器（用于相似股票）
        """
        self.stock_service = stock_service
        self.retriever = retriever
    
    def detect_for_user(self, profile: UserProfile) -> List[Opportunity]:
        """
        为特定用户检测投资机会
        
        Args:
            profile: 用户画像
            
        Returns:
            机会列表
        """
        opportunities = []
        
        # 1. 检测关注股票的买入信号
        for stock_code in profile.watchlist:
            signals = self._check_buy_signals(stock_code)
            opportunities.extend(signals)
        
        # 2. 发现相似股票
        if profile.watchlist:
            similar = self._find_similar_stocks(
                profile.watchlist[-3:],  # 最近关注的3只
                exclude=profile.watchlist
            )
            opportunities.extend(similar)
        
        # 3. 检测板块轮动机会
        if profile.focus_sectors:
            sector_opps = self._detect_sector_rotation(profile.focus_sectors)
            opportunities.extend(sector_opps)
        
        # 4. 根据用户风险偏好过滤和排序
        opportunities = self._filter_by_risk_tolerance(
            opportunities, 
            profile.risk_tolerance
        )
        
        return self._rank_opportunities(opportunities)[:10]
    
    def detect_for_stock(self, stock_code: str, stock_name: str = "") -> List[Opportunity]:
        """
        检测单只股票的机会
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            
        Returns:
            机会列表
        """
        opportunities = []
        
        # 获取股票数据
        stock_data = self._get_stock_data(stock_code)
        if not stock_data:
            return opportunities
        
        name = stock_name or stock_data.get('name', stock_code)
        
        # 检测各类信号
        opportunities.extend(self._check_technical_signals(stock_code, name, stock_data))
        opportunities.extend(self._check_fund_flow_signals(stock_code, name, stock_data))
        opportunities.extend(self._check_breakout_signals(stock_code, name, stock_data))
        
        return opportunities
    
    def _check_buy_signals(self, stock_code: str) -> List[Opportunity]:
        """检测买入信号"""
        opportunities = []
        stock_data = self._get_stock_data(stock_code)
        
        if not stock_data:
            return opportunities
        
        name = stock_data.get('name', stock_code)
        
        # RSI超卖信号
        rsi = stock_data.get('rsi', 50)
        if rsi < self.THRESHOLDS['rsi_oversold']:
            opportunities.append(Opportunity(
                id=str(uuid.uuid4()),
                type=OpportunityType.OVERSOLD,
                stock_code=stock_code,
                stock_name=name,
                title=f"{name}超卖反弹机会",
                reason=f"RSI指标为{rsi:.1f}，处于超卖区域，可能存在反弹机会",
                confidence=0.65,
                urgency=Urgency.MEDIUM,
                expected_return=0.05,
                supporting_data={"rsi": rsi}
            ))
        
        # MACD金叉信号
        macd_cross = stock_data.get('macd_golden_cross', False)
        if macd_cross:
            opportunities.append(Opportunity(
                id=str(uuid.uuid4()),
                type=OpportunityType.BUY_SIGNAL,
                stock_code=stock_code,
                stock_name=name,
                title=f"{name}MACD金叉",
                reason="MACD指标出现金叉，短期趋势可能转强",
                confidence=0.60,
                urgency=Urgency.MEDIUM,
                supporting_data={"signal": "macd_golden_cross"}
            ))
        
        # 资金流入信号
        fund_flow = stock_data.get('fund_flow_ratio', 0)
        if fund_flow > self.THRESHOLDS['fund_inflow_threshold']:
            opportunities.append(Opportunity(
                id=str(uuid.uuid4()),
                type=OpportunityType.FUND_INFLOW,
                stock_code=stock_code,
                stock_name=name,
                title=f"{name}主力资金流入",
                reason=f"主力资金净流入比例{fund_flow:.1%}，关注度提升",
                confidence=0.70,
                urgency=Urgency.HIGH,
                supporting_data={"fund_flow_ratio": fund_flow}
            ))
        
        return opportunities
    
    def _check_technical_signals(self, stock_code: str, name: str, 
                                  data: Dict) -> List[Opportunity]:
        """检测技术指标信号"""
        opportunities = []
        
        # 均线多头排列
        ma5 = data.get('ma5', 0)
        ma10 = data.get('ma10', 0)
        ma20 = data.get('ma20', 0)
        
        if ma5 > ma10 > ma20 > 0:
            opportunities.append(Opportunity(
                id=str(uuid.uuid4()),
                type=OpportunityType.BUY_SIGNAL,
                stock_code=stock_code,
                stock_name=name,
                title=f"{name}均线多头排列",
                reason="5日、10日、20日均线呈多头排列，趋势向好",
                confidence=0.55,
                urgency=Urgency.LOW,
                supporting_data={"ma5": ma5, "ma10": ma10, "ma20": ma20}
            ))
        
        return opportunities
    
    def _check_fund_flow_signals(self, stock_code: str, name: str,
                                  data: Dict) -> List[Opportunity]:
        """检测资金流向信号"""
        opportunities = []
        
        # 连续资金流入
        consecutive_inflow = data.get('consecutive_inflow_days', 0)
        if consecutive_inflow >= 3:
            opportunities.append(Opportunity(
                id=str(uuid.uuid4()),
                type=OpportunityType.FUND_INFLOW,
                stock_code=stock_code,
                stock_name=name,
                title=f"{name}连续{consecutive_inflow}日资金流入",
                reason=f"主力资金连续{consecutive_inflow}个交易日净流入，机构关注度高",
                confidence=0.65 + consecutive_inflow * 0.05,
                urgency=Urgency.HIGH if consecutive_inflow >= 5 else Urgency.MEDIUM,
                supporting_data={"consecutive_days": consecutive_inflow}
            ))
        
        return opportunities
    
    def _check_breakout_signals(self, stock_code: str, name: str,
                                 data: Dict) -> List[Opportunity]:
        """检测突破信号"""
        opportunities = []
        
        # 突破年线
        price = data.get('close', 0)
        ma250 = data.get('ma250', 0)
        
        if price > 0 and ma250 > 0:
            breakout_pct = (price - ma250) / ma250
            if 0 < breakout_pct < 0.05:  # 刚突破年线
                opportunities.append(Opportunity(
                    id=str(uuid.uuid4()),
                    type=OpportunityType.BREAKOUT,
                    stock_code=stock_code,
                    stock_name=name,
                    title=f"{name}突破年线",
                    reason=f"股价突破250日均线，中长期趋势可能转强",
                    confidence=0.60,
                    urgency=Urgency.MEDIUM,
                    expected_return=0.10,
                    supporting_data={"price": price, "ma250": ma250}
                ))
        
        # 突破前高
        high_52w = data.get('high_52w', 0)
        if price > 0 and high_52w > 0:
            if price > high_52w * 0.98 and price < high_52w * 1.02:
                opportunities.append(Opportunity(
                    id=str(uuid.uuid4()),
                    type=OpportunityType.BREAKOUT,
                    stock_code=stock_code,
                    stock_name=name,
                    title=f"{name}接近52周新高",
                    reason="股价接近52周高点，可能突破创新高",
                    confidence=0.55,
                    urgency=Urgency.LOW,
                    supporting_data={"price": price, "high_52w": high_52w}
                ))
        
        return opportunities
    
    def _find_similar_stocks(self, stock_codes: List[str],
                              exclude: List[str] = None) -> List[Opportunity]:
        """发现相似股票"""
        opportunities = []
        exclude = exclude or []
        
        if not self.retriever:
            return opportunities
        
        try:
            for stock_code in stock_codes:
                similar = self.retriever.retrieve_similar_stocks(stock_code, top_k=3)
                
                for s in similar:
                    if s.get('stock_code') not in exclude:
                        opportunities.append(Opportunity(
                            id=str(uuid.uuid4()),
                            type=OpportunityType.SIMILAR_STOCK,
                            stock_code=s['stock_code'],
                            stock_name=s.get('stock_name', s['stock_code']),
                            title=f"相似股票推荐: {s.get('stock_name', s['stock_code'])}",
                            reason=f"与您关注的股票相似度{s.get('score', 0):.0%}",
                            confidence=s.get('score', 0.5),
                            urgency=Urgency.LOW,
                            supporting_data={"similarity": s.get('score', 0)}
                        ))
        except Exception as e:
            logger.warning(f"相似股票检索失败: {e}")
        
        return opportunities
    
    def _detect_sector_rotation(self, sectors: List[str]) -> List[Opportunity]:
        """检测板块轮动机会"""
        opportunities = []
        
        sector_data = self._get_sector_data(sectors)
        if not sector_data:
            return opportunities
        
        for sector in sector_data:
            if sector.get('momentum', 0) > 0.05:  # 板块动量为正
                opportunities.append(Opportunity(
                    id=str(uuid.uuid4()),
                    type=OpportunityType.SECTOR_ROTATION,
                    stock_code=sector.get('top_stock', ''),
                    stock_name=sector.get('top_stock_name', ''),
                    title=f"{sector['name']}板块走强",
                    reason=f"{sector['name']}板块近期表现强势，龙头股值得关注",
                    confidence=0.55,
                    urgency=Urgency.LOW,
                    supporting_data={"sector": sector['name'], "momentum": sector.get('momentum')}
                ))
        
        return opportunities
    
    def _filter_by_risk_tolerance(self, opportunities: List[Opportunity],
                                   risk_tolerance: int) -> List[Opportunity]:
        """根据风险偏好过滤"""
        if risk_tolerance <= 2:  # 保守型
            # 过滤掉高风险机会
            return [o for o in opportunities if o.confidence >= 0.6]
        elif risk_tolerance >= 4:  # 激进型
            return opportunities
        else:  # 平衡型
            return [o for o in opportunities if o.confidence >= 0.5]
    
    def _rank_opportunities(self, opportunities: List[Opportunity]) -> List[Opportunity]:
        """排序机会"""
        def score(opp: Opportunity) -> float:
            urgency_score = {"high": 3, "medium": 2, "low": 1}
            return opp.confidence * 0.6 + urgency_score.get(opp.urgency.value, 1) * 0.4 / 3
        
        return sorted(opportunities, key=score, reverse=True)
    
    def _get_stock_data(self, stock_code: str) -> Optional[Dict]:
        """获取股票数据"""
        if not self.stock_service:
            logger.error("股票数据服务未初始化")
            return None
            
        try:
            return self.stock_service.get_stock_data(stock_code)
        except Exception as e:
            logger.error(f"获取股票数据失败 {stock_code}: {e}")
            return None
    
    def _get_sector_data(self, sectors: List[str]) -> List[Dict]:
        """获取板块数据"""
        if not self.stock_service:
            logger.error("股票数据服务未初始化")
            return []
        
        try:
            return self.stock_service.get_sector_data(sectors)
        except Exception as e:
            logger.error(f"获取板块数据失败: {e}")
            return []
