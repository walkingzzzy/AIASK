"""
风险预警引擎
主动检测持仓和关注股票的风险
"""
import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from .models import (
    RiskAlert, RiskType, Severity, UserProfile
)

logger = logging.getLogger(__name__)


class RiskDetector:
    """
    风险预警引擎
    
    功能：
    1. 价格风险检测（跌幅预警）
    2. 成交量异常检测
    3. 技术破位检测
    4. 资金流出检测
    5. 负面舆情检测
    """
    
    # 风险阈值
    THRESHOLDS = {
        "price_drop_warning": -3.0,     # 跌幅预警 -3%
        "price_drop_critical": -5.0,    # 跌幅严重 -5%
        "volume_anomaly": 3.0,          # 成交量异常倍数
        "fund_outflow_warning": -0.05,  # 资金流出预警
        "fund_outflow_critical": -0.10, # 资金流出严重
        "support_breakdown": 0.02,      # 支撑位破位幅度
    }
    
    def __init__(self, 
                 stock_service=None,
                 sentiment_analyzer=None):
        """
        初始化风险检测引擎
        
        Args:
            stock_service: 股票数据服务
            sentiment_analyzer: 情绪分析器
        """
        self.stock_service = stock_service
        self.sentiment_analyzer = sentiment_analyzer
    
    def detect_for_user(self, profile: UserProfile) -> List[RiskAlert]:
        """
        为特定用户检测风险
        
        Args:
            profile: 用户画像
            
        Returns:
            风险预警列表
        """
        alerts = []
        
        # 检测持仓风险（优先级更高）
        for stock_code in profile.holdings:
            stock_alerts = self._detect_stock_risks(stock_code, is_holding=True)
            alerts.extend(stock_alerts)
        
        # 检测关注股票风险
        for stock_code in profile.watchlist:
            if stock_code not in profile.holdings:
                stock_alerts = self._detect_stock_risks(stock_code, is_holding=False)
                alerts.extend(stock_alerts)
        
        # 按严重程度排序
        return self._prioritize_alerts(alerts)
    
    def detect_for_stock(self, stock_code: str, stock_name: str = "",
                         is_holding: bool = False) -> List[RiskAlert]:
        """
        检测单只股票的风险
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            is_holding: 是否为持仓
            
        Returns:
            风险预警列表
        """
        return self._detect_stock_risks(stock_code, stock_name, is_holding)
    
    def _detect_stock_risks(self, stock_code: str, stock_name: str = "",
                            is_holding: bool = False) -> List[RiskAlert]:
        """检测股票风险"""
        alerts = []
        
        # 获取股票数据
        stock_data = self._get_stock_data(stock_code)
        if not stock_data:
            return alerts
        
        name = stock_name or stock_data.get('name', stock_code)
        
        # 1. 价格风险
        price_alerts = self._check_price_risk(stock_code, name, stock_data, is_holding)
        alerts.extend(price_alerts)
        
        # 2. 成交量异常
        volume_alerts = self._check_volume_anomaly(stock_code, name, stock_data)
        alerts.extend(volume_alerts)
        
        # 3. 技术破位
        breakdown_alerts = self._check_technical_breakdown(stock_code, name, stock_data)
        alerts.extend(breakdown_alerts)
        
        # 4. 资金流出
        fund_alerts = self._check_fund_outflow(stock_code, name, stock_data)
        alerts.extend(fund_alerts)
        
        # 5. 负面舆情
        sentiment_alerts = self._check_negative_sentiment(stock_code, name)
        alerts.extend(sentiment_alerts)
        
        return alerts
    
    def _check_price_risk(self, stock_code: str, name: str,
                          data: Dict, is_holding: bool) -> List[RiskAlert]:
        """检测价格风险"""
        alerts = []
        
        change_pct = data.get('change_percent', 0)
        
        # 严重跌幅
        if change_pct <= self.THRESHOLDS['price_drop_critical']:
            alerts.append(RiskAlert(
                id=str(uuid.uuid4()),
                type=RiskType.PRICE_DROP,
                stock_code=stock_code,
                stock_name=name,
                title=f"{'持仓' if is_holding else ''}{name}大幅下跌",
                description=f"今日跌幅{change_pct:.2f}%，超过预警阈值",
                severity=Severity.CRITICAL,
                suggested_action="建议密切关注，考虑是否需要止损" if is_holding else "建议暂时观望",
                current_value=change_pct,
                threshold_value=self.THRESHOLDS['price_drop_critical'],
                supporting_data={"change_percent": change_pct}
            ))
        # 预警跌幅
        elif change_pct <= self.THRESHOLDS['price_drop_warning']:
            alerts.append(RiskAlert(
                id=str(uuid.uuid4()),
                type=RiskType.PRICE_DROP,
                stock_code=stock_code,
                stock_name=name,
                title=f"{name}下跌预警",
                description=f"今日跌幅{change_pct:.2f}%，需要关注",
                severity=Severity.WARNING,
                suggested_action="建议关注后续走势",
                current_value=change_pct,
                threshold_value=self.THRESHOLDS['price_drop_warning'],
                supporting_data={"change_percent": change_pct}
            ))
        
        return alerts
    
    def _check_volume_anomaly(self, stock_code: str, name: str,
                               data: Dict) -> List[RiskAlert]:
        """检测成交量异常"""
        alerts = []
        
        volume_ratio = data.get('volume_ratio', 1.0)  # 量比
        change_pct = data.get('change_percent', 0)
        
        # 放量下跌
        if volume_ratio >= self.THRESHOLDS['volume_anomaly'] and change_pct < -2:
            alerts.append(RiskAlert(
                id=str(uuid.uuid4()),
                type=RiskType.VOLUME_ANOMALY,
                stock_code=stock_code,
                stock_name=name,
                title=f"{name}放量下跌",
                description=f"成交量是平均的{volume_ratio:.1f}倍，同时下跌{change_pct:.2f}%",
                severity=Severity.WARNING,
                suggested_action="放量下跌可能意味着主力出货，建议谨慎",
                current_value=volume_ratio,
                threshold_value=self.THRESHOLDS['volume_anomaly'],
                supporting_data={"volume_ratio": volume_ratio, "change_percent": change_pct}
            ))
        
        return alerts
    
    def _check_technical_breakdown(self, stock_code: str, name: str,
                                    data: Dict) -> List[RiskAlert]:
        """检测技术破位"""
        alerts = []
        
        price = data.get('close', 0)
        ma20 = data.get('ma20', 0)
        ma60 = data.get('ma60', 0)
        
        # 跌破20日均线
        if price > 0 and ma20 > 0:
            breakdown_pct = (price - ma20) / ma20
            if breakdown_pct < -self.THRESHOLDS['support_breakdown']:
                alerts.append(RiskAlert(
                    id=str(uuid.uuid4()),
                    type=RiskType.TECHNICAL_BREAKDOWN,
                    stock_code=stock_code,
                    stock_name=name,
                    title=f"{name}跌破20日均线",
                    description=f"股价跌破20日均线{abs(breakdown_pct):.1%}，短期趋势转弱",
                    severity=Severity.WARNING,
                    suggested_action="短期支撑失守，建议关注能否快速收复",
                    current_value=price,
                    threshold_value=ma20,
                    supporting_data={"price": price, "ma20": ma20}
                ))
        
        # 跌破60日均线
        if price > 0 and ma60 > 0:
            breakdown_pct = (price - ma60) / ma60
            if breakdown_pct < -self.THRESHOLDS['support_breakdown']:
                alerts.append(RiskAlert(
                    id=str(uuid.uuid4()),
                    type=RiskType.TECHNICAL_BREAKDOWN,
                    stock_code=stock_code,
                    stock_name=name,
                    title=f"{name}跌破60日均线",
                    description=f"股价跌破60日均线{abs(breakdown_pct):.1%}，中期趋势转弱",
                    severity=Severity.CRITICAL if breakdown_pct < -0.05 else Severity.WARNING,
                    suggested_action="中期支撑失守，建议考虑减仓",
                    current_value=price,
                    threshold_value=ma60,
                    supporting_data={"price": price, "ma60": ma60}
                ))
        
        # MACD死叉
        if data.get('macd_death_cross', False):
            alerts.append(RiskAlert(
                id=str(uuid.uuid4()),
                type=RiskType.TECHNICAL_BREAKDOWN,
                stock_code=stock_code,
                stock_name=name,
                title=f"{name}MACD死叉",
                description="MACD指标出现死叉，短期可能继续调整",
                severity=Severity.INFO,
                suggested_action="技术指标转弱，建议谨慎操作",
                supporting_data={"signal": "macd_death_cross"}
            ))
        
        return alerts
    
    def _check_fund_outflow(self, stock_code: str, name: str,
                             data: Dict) -> List[RiskAlert]:
        """检测资金流出"""
        alerts = []
        
        fund_flow = data.get('fund_flow_ratio', 0)
        consecutive_outflow = data.get('consecutive_outflow_days', 0)
        
        # 大幅资金流出
        if fund_flow <= self.THRESHOLDS['fund_outflow_critical']:
            alerts.append(RiskAlert(
                id=str(uuid.uuid4()),
                type=RiskType.FUND_OUTFLOW,
                stock_code=stock_code,
                stock_name=name,
                title=f"{name}主力资金大幅流出",
                description=f"主力资金净流出比例{abs(fund_flow):.1%}",
                severity=Severity.CRITICAL,
                suggested_action="主力资金大幅撤离，建议高度警惕",
                current_value=fund_flow,
                threshold_value=self.THRESHOLDS['fund_outflow_critical'],
                supporting_data={"fund_flow_ratio": fund_flow}
            ))
        elif fund_flow <= self.THRESHOLDS['fund_outflow_warning']:
            alerts.append(RiskAlert(
                id=str(uuid.uuid4()),
                type=RiskType.FUND_OUTFLOW,
                stock_code=stock_code,
                stock_name=name,
                title=f"{name}资金流出预警",
                description=f"主力资金净流出比例{abs(fund_flow):.1%}",
                severity=Severity.WARNING,
                suggested_action="资金有流出迹象，建议关注",
                current_value=fund_flow,
                threshold_value=self.THRESHOLDS['fund_outflow_warning'],
                supporting_data={"fund_flow_ratio": fund_flow}
            ))
        
        # 连续资金流出
        if consecutive_outflow >= 3:
            alerts.append(RiskAlert(
                id=str(uuid.uuid4()),
                type=RiskType.FUND_OUTFLOW,
                stock_code=stock_code,
                stock_name=name,
                title=f"{name}连续{consecutive_outflow}日资金流出",
                description=f"主力资金连续{consecutive_outflow}个交易日净流出",
                severity=Severity.WARNING if consecutive_outflow < 5 else Severity.CRITICAL,
                suggested_action="持续资金流出，机构可能在减仓",
                supporting_data={"consecutive_days": consecutive_outflow}
            ))
        
        return alerts
    
    def _check_negative_sentiment(self, stock_code: str, name: str) -> List[RiskAlert]:
        """检测负面舆情"""
        alerts = []
        
        if not self.sentiment_analyzer:
            return alerts
        
        try:
            sentiment = self.sentiment_analyzer.analyze_stock(stock_code)
            
            if sentiment and sentiment.get('overall_score', 0) < -0.5:
                key_event = sentiment.get('key_events', [{}])[0]
                alerts.append(RiskAlert(
                    id=str(uuid.uuid4()),
                    type=RiskType.NEWS_NEGATIVE,
                    stock_code=stock_code,
                    stock_name=name,
                    title=f"{name}出现负面舆情",
                    description=key_event.get('event', '检测到负面新闻或公告'),
                    severity=Severity.WARNING,
                    suggested_action="建议关注相关新闻，评估影响",
                    supporting_data={"sentiment_score": sentiment.get('overall_score')}
                ))
        except Exception as e:
            logger.warning(f"情绪分析失败 {stock_code}: {e}")
        
        return alerts
    
    def _prioritize_alerts(self, alerts: List[RiskAlert]) -> List[RiskAlert]:
        """按优先级排序预警"""
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.WARNING: 1,
            Severity.INFO: 2
        }
        
        return sorted(alerts, key=lambda a: severity_order.get(a.severity, 3))
    
    def _get_stock_data(self, stock_code: str) -> Optional[Dict]:
        """获取股票数据"""
        if self.stock_service:
            try:
                return self.stock_service.get_stock_data(stock_code)
            except Exception as e:
                logger.warning(f"获取股票数据失败 {stock_code}: {e}")
        
        # 返回模拟数据用于演示
        return self._get_mock_stock_data(stock_code)
    
    def _get_mock_stock_data(self, stock_code: str) -> Dict:
        """获取模拟股票数据"""
        import random
        return {
            "code": stock_code,
            "name": f"股票{stock_code}",
            "close": 100 + random.uniform(-20, 20),
            "change_percent": random.uniform(-8, 5),
            "volume_ratio": random.uniform(0.5, 4),
            "ma20": 100 + random.uniform(-5, 5),
            "ma60": 100 + random.uniform(-10, 10),
            "macd_death_cross": random.random() > 0.8,
            "fund_flow_ratio": random.uniform(-0.15, 0.1),
            "consecutive_outflow_days": random.randint(0, 5),
        }


# 导出
__all__ = ['RiskDetector', 'RiskAlert']
