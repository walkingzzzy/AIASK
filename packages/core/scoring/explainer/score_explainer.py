"""
评分解释器
生成AI评分的可解释性报告
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class FactorContribution:
    """因子贡献"""
    factor_name: str          # 因子名称
    category: str             # 类别：technical/fundamental/fund_flow/sentiment/risk
    raw_value: Any            # 原始值
    score_contribution: float # 对总分的贡献
    direction: str            # positive/negative/neutral
    description: str          # 描述


@dataclass
class ExplanationResult:
    """解释结果"""
    stock_code: str
    stock_name: str
    ai_score: float
    signal: str
    
    # 评分分解
    score_breakdown: Dict[str, float]
    
    # 因子贡献排名
    top_positive_factors: List[FactorContribution]
    top_negative_factors: List[FactorContribution]
    
    # 文字解释
    summary: str
    detailed_explanation: str
    
    # 建议
    suggestions: List[str]
    
    generated_at: str
    
    def to_dict(self) -> Dict:
        result = asdict(self)
        result['top_positive_factors'] = [asdict(f) for f in self.top_positive_factors]
        result['top_negative_factors'] = [asdict(f) for f in self.top_negative_factors]
        return result


class ScoreExplainer:
    """
    评分解释器
    
    功能：
    1. 分解评分各维度贡献
    2. 识别关键影响因子
    3. 生成自然语言解释
    """
    
    # 因子描述模板
    FACTOR_TEMPLATES = {
        # 技术面
        'ma_trend': {
            'positive': '均线呈多头排列，趋势向好',
            'negative': '均线呈空头排列，趋势偏弱',
            'neutral': '均线走势中性'
        },
        'macd': {
            'positive': 'MACD金叉，动能转强',
            'negative': 'MACD死叉，动能减弱',
            'neutral': 'MACD信号中性'
        },
        'rsi': {
            'positive': 'RSI处于强势区域',
            'negative': 'RSI超买/超卖',
            'neutral': 'RSI处于中性区域'
        },
        'volume': {
            'positive': '成交量配合良好',
            'negative': '量价背离',
            'neutral': '成交量正常'
        },
        # 基本面
        'valuation': {
            'positive': '估值处于历史低位，具有安全边际',
            'negative': '估值处于历史高位，需警惕回调',
            'neutral': '估值处于合理区间'
        },
        'profitability': {
            'positive': 'ROE优秀，盈利能力强',
            'negative': 'ROE偏低，盈利能力待提升',
            'neutral': '盈利能力中等'
        },
        'growth': {
            'positive': '业绩高增长，成长性好',
            'negative': '业绩增速放缓或下滑',
            'neutral': '业绩增速平稳'
        },
        # 资金面
        'north_fund': {
            'positive': '北向资金持续流入',
            'negative': '北向资金流出',
            'neutral': '北向资金变化不大'
        },
        'main_fund': {
            'positive': '主力资金净流入',
            'negative': '主力资金净流出',
            'neutral': '主力资金变化不大'
        },
        # 风险
        'volatility': {
            'positive': '波动率较低，风险可控',
            'negative': '波动率较高，注意风险',
            'neutral': '波动率正常'
        }
    }
    
    # 信号解释
    SIGNAL_EXPLANATIONS = {
        'Strong Buy': '强烈看多，建议积极配置',
        'Buy': '看多，可考虑买入',
        'Hold': '中性，建议持有观望',
        'Sell': '看空，建议减仓',
        'Strong Sell': '强烈看空，建议清仓'
    }
    
    def explain(self, score_result: Dict[str, Any], 
                raw_data: Optional[Dict] = None) -> ExplanationResult:
        """
        生成评分解释
        
        Args:
            score_result: AIScoreResult.to_dict()的结果
            raw_data: 原始数据（可选，用于更详细的解释）
        """
        stock_code = score_result.get('stock_code', '')
        stock_name = score_result.get('stock_name', '')
        ai_score = score_result.get('ai_score', 5.0)
        signal = score_result.get('signal', 'Hold')
        subscores = score_result.get('subscores', {})
        
        # 1. 评分分解
        score_breakdown = self._calculate_breakdown(subscores)
        
        # 2. 提取因子贡献
        positive_factors, negative_factors = self._extract_factors(subscores, raw_data)
        
        # 3. 生成摘要
        summary = self._generate_summary(stock_name, ai_score, signal, 
                                         positive_factors, negative_factors)
        
        # 4. 生成详细解释
        detailed = self._generate_detailed_explanation(
            subscores, positive_factors, negative_factors
        )
        
        # 5. 生成建议
        suggestions = self._generate_suggestions(
            ai_score, signal, subscores, score_result.get('risks', [])
        )
        
        return ExplanationResult(
            stock_code=stock_code,
            stock_name=stock_name,
            ai_score=ai_score,
            signal=signal,
            score_breakdown=score_breakdown,
            top_positive_factors=positive_factors[:3],
            top_negative_factors=negative_factors[:3],
            summary=summary,
            detailed_explanation=detailed,
            suggestions=suggestions,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    
    def _calculate_breakdown(self, subscores: Dict) -> Dict[str, float]:
        """计算各维度对总分的贡献"""
        breakdown = {}
        for name, data in subscores.items():
            score = data.get('score', 5.0)
            weight = data.get('weight', 0.2)
            breakdown[name] = round(score * weight, 2)
        return breakdown
    
    def _extract_factors(self, subscores: Dict, 
                         raw_data: Optional[Dict]) -> tuple:
        """提取正面和负面因子"""
        positive = []
        negative = []
        
        # 技术面因子
        tech = subscores.get('technical', {})
        tech_details = tech.get('details', {})
        self._add_factor(positive, negative, 'ma_trend', 'technical',
                        tech_details.get('ma_score', 5), tech.get('weight', 0.25))
        self._add_factor(positive, negative, 'macd', 'technical',
                        tech_details.get('macd_score', 5), tech.get('weight', 0.25))
        
        # 基本面因子
        fund = subscores.get('fundamental', {})
        fund_details = fund.get('details', {})
        self._add_factor(positive, negative, 'valuation', 'fundamental',
                        fund_details.get('valuation_score', 5), fund.get('weight', 0.30))
        self._add_factor(positive, negative, 'profitability', 'fundamental',
                        fund_details.get('profitability_score', 5), fund.get('weight', 0.30))
        self._add_factor(positive, negative, 'growth', 'fundamental',
                        fund_details.get('growth_score', 5), fund.get('weight', 0.30))
        
        # 资金面因子
        flow = subscores.get('fund_flow', {})
        flow_details = flow.get('details', {})
        self._add_factor(positive, negative, 'north_fund', 'fund_flow',
                        flow_details.get('north_score', 5), flow.get('weight', 0.25))
        self._add_factor(positive, negative, 'main_fund', 'fund_flow',
                        flow_details.get('main_score', 5), flow.get('weight', 0.25))
        
        # 风险因子
        risk = subscores.get('risk', {})
        risk_details = risk.get('details', {})
        volatility_score = 5.0
        if risk_details.get('risk_level') == '低':
            volatility_score = 8.0
        elif risk_details.get('risk_level') == '高':
            volatility_score = 3.0
        self._add_factor(positive, negative, 'volatility', 'risk',
                        volatility_score, risk.get('weight', 0.10))
        
        # 按贡献度排序
        positive.sort(key=lambda x: x.score_contribution, reverse=True)
        negative.sort(key=lambda x: abs(x.score_contribution), reverse=True)
        
        return positive, negative
    
    def _add_factor(self, positive: List, negative: List,
                    factor_name: str, category: str, 
                    score: float, weight: float):
        """添加因子到正面或负面列表"""
        contribution = (score - 5) * weight  # 相对于中性分5的贡献
        
        if score > 6:
            direction = 'positive'
            desc = self.FACTOR_TEMPLATES.get(factor_name, {}).get('positive', '')
        elif score < 4:
            direction = 'negative'
            desc = self.FACTOR_TEMPLATES.get(factor_name, {}).get('negative', '')
        else:
            direction = 'neutral'
            desc = self.FACTOR_TEMPLATES.get(factor_name, {}).get('neutral', '')
        
        factor = FactorContribution(
            factor_name=factor_name,
            category=category,
            raw_value=score,
            score_contribution=round(contribution, 2),
            direction=direction,
            description=desc
        )
        
        if direction == 'positive':
            positive.append(factor)
        elif direction == 'negative':
            negative.append(factor)
    
    def _generate_summary(self, stock_name: str, ai_score: float, 
                          signal: str, positive: List, negative: List) -> str:
        """生成摘要"""
        signal_desc = self.SIGNAL_EXPLANATIONS.get(signal, '')
        
        summary = f"{stock_name}当前AI评分{ai_score}分，{signal_desc}。"
        
        if positive:
            top_pos = positive[0]
            summary += f"主要利好：{top_pos.description}。"
        
        if negative:
            top_neg = negative[0]
            summary += f"主要风险：{top_neg.description}。"
        
        return summary
    
    def _generate_detailed_explanation(self, subscores: Dict,
                                       positive: List, negative: List) -> str:
        """生成详细解释"""
        lines = []
        
        # 各维度评分
        lines.append("【评分详情】")
        dimension_names = {
            'technical': '技术面',
            'fundamental': '基本面', 
            'fund_flow': '资金面',
            'sentiment': '情绪面',
            'risk': '风险'
        }
        for name, data in subscores.items():
            dim_name = dimension_names.get(name, name)
            score = data.get('score', 5.0)
            weight = data.get('weight', 0.2)
            lines.append(f"- {dim_name}：{score}分（权重{int(weight*100)}%）")
        
        # 正面因子
        if positive:
            lines.append("\n【利好因素】")
            for f in positive[:3]:
                lines.append(f"- {f.description}（贡献+{f.score_contribution}分）")
        
        # 负面因子
        if negative:
            lines.append("\n【风险因素】")
            for f in negative[:3]:
                lines.append(f"- {f.description}（影响{f.score_contribution}分）")
        
        return "\n".join(lines)
    
    def _generate_suggestions(self, ai_score: float, signal: str,
                              subscores: Dict, risks: List[str]) -> List[str]:
        """生成建议"""
        suggestions = []
        
        if signal in ['Strong Buy', 'Buy']:
            suggestions.append("可考虑逢低布局，分批建仓")
            if subscores.get('technical', {}).get('score', 5) > 7:
                suggestions.append("技术面走强，可适当追涨")
        elif signal in ['Sell', 'Strong Sell']:
            suggestions.append("建议控制仓位，注意止损")
            if subscores.get('fund_flow', {}).get('score', 5) < 4:
                suggestions.append("资金面偏空，注意资金流出风险")
        else:
            suggestions.append("建议观望，等待更明确的信号")
        
        # 添加风险提示
        for risk in risks[:2]:
            suggestions.append(f"风险提示：{risk}")
        
        return suggestions[:4]


def explain_score(score_result: Dict[str, Any], 
                  raw_data: Optional[Dict] = None) -> ExplanationResult:
    """便捷函数：生成评分解释"""
    explainer = ScoreExplainer()
    return explainer.explain(score_result, raw_data)
