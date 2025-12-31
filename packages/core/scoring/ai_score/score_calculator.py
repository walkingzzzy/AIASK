"""
AI评分计算器
综合各维度评分，生成最终AI评分
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

from .score_components import (
    TechnicalScore, FundamentalScore, FundFlowScore,
    SentimentScore, RiskScore, ScoreResult
)
from .enhanced_components import (
    EnhancedTechnicalScore, EnhancedFundamentalScore, EnhancedFundFlowScore
)

logger = logging.getLogger(__name__)


@dataclass
class DataCompleteness:
    """数据完整性信息"""
    completeness_percent: float        # 完整度百分比
    status: str                        # complete/partial/incomplete
    message: str                       # 状态消息
    missing_fields: List[str]          # 缺失字段
    default_value_fields: List[str]    # 使用默认值的字段
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class AIScoreResult:
    """AI评分结果"""
    stock_code: str
    stock_name: str
    ai_score: float                    # 综合评分 1-10
    beat_market_probability: float     # 跑赢市场概率
    signal: str                        # Strong Buy/Buy/Hold/Sell/Strong Sell
    confidence: float                  # 置信度
    
    # 分项评分
    subscores: Dict[str, Dict]
    
    # 关键影响因子
    top_factors: List[Dict]
    
    # 风险提示
    risks: List[str]
    
    # 更新时间
    updated_at: str
    
    # 数据完整性
    data_completeness: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


class AIScoreCalculator:
    """
    AI评分计算器
    
    评分维度和权重：
    - 技术面 25%
    - 基本面 30%
    - 资金面 25%
    - 情绪面 10%
    - 风险 10%
    """
    
    # 信号定义
    SIGNAL_THRESHOLDS = {
        'Strong Buy': (8.5, 10),
        'Buy': (7.0, 8.5),
        'Hold': (5.0, 7.0),
        'Sell': (3.0, 5.0),
        'Strong Sell': (1.0, 3.0)
    }
    
    def __init__(self, use_enhanced: bool = True):
        """
        初始化评分计算器

        Args:
            use_enhanced: 是否使用增强版评分组件（100+指标）
        """
        if use_enhanced:
            self.components = [
                EnhancedTechnicalScore(weight=0.25),
                EnhancedFundamentalScore(weight=0.30),
                EnhancedFundFlowScore(weight=0.25),
                SentimentScore(weight=0.10),
                RiskScore(weight=0.10)
            ]
        else:
            self.components = [
                TechnicalScore(weight=0.25),
                FundamentalScore(weight=0.30),
                FundFlowScore(weight=0.25),
                SentimentScore(weight=0.10),
                RiskScore(weight=0.10)
            ]
    
    def calculate(self, stock_code: str, stock_name: str,
                  data: Dict[str, Any]) -> AIScoreResult:
        """
        计算AI综合评分
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            data: 包含各维度数据的字典（可能包含_data_completeness字段）
            
        Returns:
            AIScoreResult
        """
        subscores = {}
        all_factors = []
        total_score = 0.0
        
        # 提取数据完整性信息（由_collect_score_data添加）
        data_completeness = data.pop('_data_completeness', None)
        
        # 计算各维度评分
        for component in self.components:
            try:
                result = component.calculate(data)
                subscores[component.name] = {
                    "score": round(result.score, 1),
                    "weight": result.weight,
                    "details": result.details
                }
                total_score += result.score * result.weight
                all_factors.extend(result.factors)
            except Exception as e:
                logger.warning(f"计算{component.name}评分失败: {e}")
                subscores[component.name] = {
                    "score": 5.0,
                    "weight": component.weight,
                    "details": {"error": str(e)}
                }
                total_score += 5.0 * component.weight
        
        # 归一化到1-10
        ai_score = max(1.0, min(10.0, total_score))
        
        # 计算跑赢市场概率
        beat_probability = self._calculate_beat_probability(ai_score)
        
        # 生成信号
        signal = self._get_signal(ai_score)
        
        # 计算置信度（考虑数据完整性）
        confidence = self._calculate_confidence(subscores, data_completeness)
        
        # 获取Top因子
        top_factors = self._get_top_factors(all_factors, top_n=3)
        
        # 生成风险提示
        risks = self._generate_risks(data, subscores, data_completeness)
        
        return AIScoreResult(
            stock_code=stock_code,
            stock_name=stock_name,
            ai_score=round(ai_score, 1),
            beat_market_probability=round(beat_probability, 2),
            signal=signal,
            confidence=round(confidence, 2),
            subscores=subscores,
            top_factors=top_factors,
            risks=risks,
            updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            data_completeness=data_completeness
        )
    
    def _calculate_beat_probability(self, score: float) -> float:
        """
        计算跑赢市场概率
        
        基于历史回测数据的经验公式
        """
        # 简化模型：评分与概率的映射
        # 8分以上：70%+
        # 7分：60%
        # 6分：55%
        # 5分：50%
        # 4分以下：40%-
        
        if score >= 9:
            return 0.75
        elif score >= 8:
            return 0.70
        elif score >= 7:
            return 0.62
        elif score >= 6:
            return 0.55
        elif score >= 5:
            return 0.50
        elif score >= 4:
            return 0.42
        else:
            return 0.35
    
    def _get_signal(self, score: float) -> str:
        """根据评分获取信号"""
        for signal, (low, high) in self.SIGNAL_THRESHOLDS.items():
            if low <= score < high:
                return signal
        return 'Hold'
    
    def _calculate_confidence(self, subscores: Dict, data_completeness: Optional[Dict] = None) -> float:
        """
        计算置信度
        
        基于各维度评分的一致性和数据完整性
        """
        scores = [s['score'] for s in subscores.values()]
        if not scores:
            return 0.5
        
        # 计算标准差，标准差越小置信度越高
        mean_score = sum(scores) / len(scores)
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
        std_dev = variance ** 0.5
        
        # 标准差转换为置信度
        # std_dev = 0 -> confidence = 1.0
        # std_dev = 3 -> confidence = 0.5
        confidence = max(0.5, 1.0 - std_dev / 6)
        
        # 根据数据完整性调整置信度
        if data_completeness:
            completeness_percent = data_completeness.get('completeness_percent', 100)
            # 数据完整度低于50%时，置信度打折
            if completeness_percent < 50:
                confidence *= 0.7
            elif completeness_percent < 80:
                confidence *= 0.85
        
        return confidence
    
    def _get_top_factors(self, factors: List[Dict], top_n: int = 3) -> List[Dict]:
        """获取影响最大的因子"""
        # 按影响力排序
        sorted_factors = sorted(
            factors,
            key=lambda x: abs(float(x.get('impact', '0').replace('+', ''))),
            reverse=True
        )
        return sorted_factors[:top_n]
    
    def _generate_risks(self, data: Dict, subscores: Dict,
                        data_completeness: Optional[Dict] = None) -> List[str]:
        """生成风险提示"""
        risks = []
        
        # 数据完整性风险
        if data_completeness:
            status = data_completeness.get('status', 'complete')
            if status == 'incomplete':
                risks.append(f"⚠️ 数据不完整（{data_completeness.get('completeness_percent', 0):.0f}%），评分仅供参考")
            elif status == 'partial':
                default_fields = data_completeness.get('default_value_fields', [])
                if len(default_fields) > 3:
                    risks.append(f"⚠️ {len(default_fields)}项指标使用默认值，评分可能有偏差")
        
        # 估值风险
        pe_percentile = data.get('pe_percentile', 50)
        if pe_percentile > 80:
            risks.append(f"估值处于历史高位（PE分位数{pe_percentile}%）")
        
        # 技术风险
        tech_score = subscores.get('technical', {}).get('score', 5)
        if tech_score < 4:
            risks.append("技术面偏弱，短期可能承压")
        
        # 资金风险
        fund_score = subscores.get('fund_flow', {}).get('score', 5)
        if fund_score < 4:
            risks.append("资金面偏空，注意资金流出风险")
        
        # 波动风险
        risk_details = subscores.get('risk', {}).get('details', {})
        if risk_details.get('risk_level') == '高':
            risks.append("波动率较高，注意控制仓位")
        
        # 市场风险
        market_breadth = data.get('market_breadth', 0.5)
        if market_breadth < 0.3:
            risks.append("大盘弱势，注意系统性风险")
        
        return risks[:4]  # 最多返回4条（增加数据完整性警告）


def calculate_ai_score(stock_code: str, stock_name: str, 
                       data: Dict[str, Any]) -> AIScoreResult:
    """便捷函数：计算AI评分"""
    calculator = AIScoreCalculator()
    return calculator.calculate(stock_code, stock_name, data)
