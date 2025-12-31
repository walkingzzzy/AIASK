"""
估值汇总模块 - 整合多种估值模型

本模块整合了以下估值模型：
1. DCF (现金流折现模型) - 适用于现金流稳定的公司
2. DDM (股利折现模型) - 适用于稳定分红的成熟公司
3. PEG (市盈率增长比) - 适用于成长型公司
4. EV/EBITDA (企业价值倍数) - 适用于资本密集型行业

提供一站式估值分析服务，包括：
- 综合估值分析
- 多模型对比
- 估值报告生成
- 合理价值区间计算
- 数据缺失时的降级处理
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from enum import Enum

# 导入各估值模型
from .dcf_model import DCFValuation
from .ddm_model import DDMValuation
from .peg_model import PEGValuation
from .ev_ebitda_model import EVEBITDAValuation

logger = logging.getLogger(__name__)


class ValuationMode(Enum):
    """估值模式"""
    FULL = "full"                  # 完整估值（需要全部数据）
    DEGRADED = "degraded"          # 降级估值（使用默认值填充）
    SIMPLE = "simple"              # 简化估值（仅PE/PB估值）


@dataclass
class ValuationDataStatus:
    """估值数据状态"""
    has_dividend_data: bool = False        # 是否有分红数据（DDM需要）
    has_growth_data: bool = False          # 是否有增长率数据（PEG需要）
    has_cashflow_data: bool = False        # 是否有现金流数据（DCF需要）
    has_ebitda_data: bool = False          # 是否有EBITDA数据
    has_price_data: bool = False           # 是否有当前价格
    has_pe_data: bool = False              # 是否有PE数据
    has_pb_data: bool = False              # 是否有PB数据
    missing_fields: List[str] = field(default_factory=list)
    available_models: List[str] = field(default_factory=list)
    mode: ValuationMode = ValuationMode.SIMPLE
    message: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "has_dividend_data": self.has_dividend_data,
            "has_growth_data": self.has_growth_data,
            "has_cashflow_data": self.has_cashflow_data,
            "has_ebitda_data": self.has_ebitda_data,
            "has_price_data": self.has_price_data,
            "has_pe_data": self.has_pe_data,
            "has_pb_data": self.has_pb_data,
            "missing_fields": self.missing_fields,
            "available_models": self.available_models,
            "mode": self.mode.value,
            "message": self.message
        }


@dataclass
class ValuationSummaryResult:
    """估值汇总结果"""
    stock_code: str
    stock_name: str
    current_price: float
    valuation_date: str

    # 各模型估值结果
    dcf_value: Optional[float]
    ddm_value: Optional[float]
    peg_fair_price: Optional[float]
    ev_ebitda_implied_price: Optional[float]

    # 综合估值
    fair_value_low: float
    fair_value_mid: float
    fair_value_high: float

    # 投资建议
    overall_recommendation: str
    confidence_level: str
    margin_of_safety: float

    # 详细结果
    model_details: Dict[str, Any]


class ValuationSummary:
    """
    估值汇总类

    整合多种估值模型，提供综合估值分析服务
    支持数据缺失时的降级处理
    """
    
    # 行业平均PE/PB估值参数（用于降级估值）
    INDUSTRY_DEFAULTS = {
        'default': {'pe': 15, 'pb': 1.5, 'growth_rate': 0.10},
        '银行': {'pe': 6, 'pb': 0.7, 'growth_rate': 0.05},
        '保险': {'pe': 10, 'pb': 1.2, 'growth_rate': 0.08},
        '证券': {'pe': 20, 'pb': 1.5, 'growth_rate': 0.15},
        '房地产': {'pe': 8, 'pb': 0.8, 'growth_rate': 0.03},
        '医药': {'pe': 30, 'pb': 4.0, 'growth_rate': 0.20},
        '科技': {'pe': 40, 'pb': 5.0, 'growth_rate': 0.25},
        '消费': {'pe': 25, 'pb': 3.5, 'growth_rate': 0.15},
        '制造': {'pe': 15, 'pb': 2.0, 'growth_rate': 0.10},
    }

    def __init__(self):
        """初始化估值汇总模块"""
        self.dcf_model = DCFValuation()
        self.ddm_model = DDMValuation()
        self.peg_model = PEGValuation()
        self.ev_ebitda_model = EVEBITDAValuation()

        logger.info("估值汇总模块初始化完成")

    def get_comprehensive_valuation(self, stock_code: str,
                                     allow_degraded: bool = True) -> Dict[str, Any]:
        """
        获取综合估值分析

        对股票进行全方位估值分析，整合多个模型的结果
        支持数据缺失时的降级处理

        Args:
            stock_code: 股票代码，如 600519.SH 或 000001.SZ
            allow_degraded: 是否允许降级模式（数据不足时使用默认值估算）

        Returns:
            综合估值结果字典
        """
        try:
            logger.info(f"开始综合估值分析: {stock_code}")

            # 初始化结果容器
            valuation_results = {}
            valid_valuations = []
            data_status = ValuationDataStatus()

            # 1. DCF估值 (暂时跳过，需要完善)
            # dcf_result = self._calculate_dcf_valuation(stock_code)
            # valuation_results['dcf'] = dcf_result

            # 2. DDM估值
            ddm_result = self._calculate_ddm_valuation(stock_code)
            valuation_results['ddm'] = ddm_result
            if ddm_result.get('intrinsic_value', 0) > 0:
                valid_valuations.append(('ddm', ddm_result['intrinsic_value']))
                data_status.has_dividend_data = True
                data_status.available_models.append('ddm')
            elif 'error' in ddm_result:
                data_status.missing_fields.append('dividend_data')

            # 3. PEG估值
            peg_result = self._calculate_peg_valuation(stock_code)
            valuation_results['peg'] = peg_result
            if peg_result.get('fair_price', 0) > 0:
                valid_valuations.append(('peg', peg_result['fair_price']))
                data_status.has_growth_data = True
                data_status.available_models.append('peg')
            elif 'error' in peg_result:
                data_status.missing_fields.append('growth_data')

            # 4. EV/EBITDA估值
            ev_ebitda_result = self._calculate_ev_ebitda_valuation(stock_code)
            valuation_results['ev_ebitda'] = ev_ebitda_result
            if ev_ebitda_result.get('implied_price', 0) > 0:
                valid_valuations.append(('ev_ebitda', ev_ebitda_result['implied_price']))
                data_status.has_ebitda_data = True
                data_status.available_models.append('ev_ebitda')
            elif 'error' in ev_ebitda_result:
                data_status.missing_fields.append('ebitda_data')

            # 如果没有有效估值，尝试降级处理
            if not valid_valuations:
                if allow_degraded:
                    logger.info(f"标准估值模型均失败，尝试降级估值: {stock_code}")
                    degraded_result = self._get_degraded_valuation(stock_code, data_status)
                    if degraded_result:
                        valuation_results['simple_valuation'] = degraded_result
                        if degraded_result.get('pe_fair_value', 0) > 0:
                            valid_valuations.append(('simple_pe', degraded_result['pe_fair_value']))
                        if degraded_result.get('pb_fair_value', 0) > 0:
                            valid_valuations.append(('simple_pb', degraded_result['pb_fair_value']))
                        data_status.mode = ValuationMode.DEGRADED
                        data_status.message = "使用简化估值模式（PE/PB行业对比）"
                
                # 如果仍然没有有效估值，返回友好的错误信息
                if not valid_valuations:
                    data_status.mode = ValuationMode.SIMPLE
                    data_status.message = self._generate_missing_data_message(data_status)
                    return {
                        'stock_code': stock_code,
                        'error': '无法获取有效估值结果',
                        'error_type': 'data_missing',
                        'friendly_message': data_status.message,
                        'missing_data': data_status.missing_fields,
                        'data_status': data_status.to_dict(),
                        'valuation_results': valuation_results,
                        'suggestions': self._get_data_suggestions(data_status)
                    }
            else:
                data_status.mode = ValuationMode.FULL
                data_status.message = "完整估值模式"

            # 计算合理价值区间
            fair_value_range = self._calculate_fair_value_range(valid_valuations)

            # 获取当前价格
            current_price = self._get_current_price(stock_code, valuation_results)
            data_status.has_price_data = current_price > 0

            # 生成综合投资建议
            recommendation = self._generate_overall_recommendation(
                current_price,
                fair_value_range,
                valuation_results
            )

            return {
                'stock_code': stock_code,
                'stock_name': self._get_stock_name(valuation_results),
                'current_price': round(current_price, 2),
                'valuation_date': datetime.now().strftime('%Y-%m-%d'),
                'fair_value_low': round(fair_value_range['low'], 2),
                'fair_value_mid': round(fair_value_range['mid'], 2),
                'fair_value_high': round(fair_value_range['high'], 2),
                'margin_of_safety': round(fair_value_range['margin_of_safety'], 2),
                'overall_recommendation': recommendation['recommendation'],
                'confidence_level': recommendation['confidence'],
                'valuation_results': valuation_results,
                'valid_models': [model for model, _ in valid_valuations],
                'data_status': data_status.to_dict()
            }

        except Exception as e:
            logger.error(f"综合估值分析失败: {stock_code}, 错误: {str(e)}")
            return {
                'stock_code': stock_code,
                'error': str(e),
                'error_type': 'exception',
                'friendly_message': f"估值分析过程中发生错误: {str(e)}",
                'suggestions': ['请检查股票代码是否正确', '稍后重试', '联系技术支持']
            }

    def _get_degraded_valuation(self, stock_code: str,
                                 data_status: ValuationDataStatus) -> Optional[Dict[str, Any]]:
        """
        获取降级估值（简化PE/PB估值）
        
        当详细财务数据不可用时，使用行业平均值进行估算
        """
        try:
            # 尝试获取基础数据
            from packages.core.services.stock_data_service import get_stock_service
            service = get_stock_service()
            
            quote = service.get_realtime_quote(stock_code)
            financial = service.get_financial_data(stock_code)
            
            if not quote:
                return None
            
            current_price = quote.get('price', 0)
            if current_price <= 0:
                return None
            
            data_status.has_price_data = True
            
            # 获取PE和PB
            pe = None
            pb = None
            eps = None
            bps = None
            
            if financial:
                pe = financial.get('pe')
                pb = financial.get('pb')
                eps = financial.get('eps')  # 每股收益
                bps = financial.get('bps')  # 每股净资产
                
                if pe and pe > 0:
                    data_status.has_pe_data = True
                if pb and pb > 0:
                    data_status.has_pb_data = True
            
            # 获取行业默认值
            industry = financial.get('industry', 'default') if financial else 'default'
            defaults = self.INDUSTRY_DEFAULTS.get(industry, self.INDUSTRY_DEFAULTS['default'])
            
            result = {
                'mode': 'degraded',
                'industry': industry,
                'current_price': current_price,
                'pe_fair_value': 0,
                'pb_fair_value': 0,
                'warnings': []
            }
            
            # PE估值
            if eps and eps > 0:
                target_pe = defaults['pe']
                result['pe_fair_value'] = round(eps * target_pe, 2)
                result['current_pe'] = round(current_price / eps, 2) if eps > 0 else None
                result['target_pe'] = target_pe
            elif pe and pe > 0:
                # 使用当前PE和行业对比
                result['current_pe'] = pe
                result['target_pe'] = defaults['pe']
                result['warnings'].append('使用当前PE进行对比，未计算PE公允价值')
            else:
                result['warnings'].append('PE数据不可用')
            
            # PB估值
            if bps and bps > 0:
                target_pb = defaults['pb']
                result['pb_fair_value'] = round(bps * target_pb, 2)
                result['current_pb'] = round(current_price / bps, 2) if bps > 0 else None
                result['target_pb'] = target_pb
            elif pb and pb > 0:
                result['current_pb'] = pb
                result['target_pb'] = defaults['pb']
                result['warnings'].append('使用当前PB进行对比，未计算PB公允价值')
            else:
                result['warnings'].append('PB数据不可用')
            
            # 如果两个估值都无效，返回None
            if result['pe_fair_value'] <= 0 and result['pb_fair_value'] <= 0:
                return None
            
            # 计算综合公允价值
            values = [v for v in [result['pe_fair_value'], result['pb_fair_value']] if v > 0]
            if values:
                result['fair_value'] = round(np.mean(values), 2)
                result['upside_potential'] = round((result['fair_value'] - current_price) / current_price * 100, 2)
            
            return result
            
        except Exception as e:
            logger.warning(f"降级估值失败: {stock_code}, {str(e)}")
            return None

    def _generate_missing_data_message(self, data_status: ValuationDataStatus) -> str:
        """生成缺失数据的友好提示消息"""
        missing = data_status.missing_fields
        
        if not missing:
            return "数据正常"
        
        messages = []
        if 'dividend_data' in missing:
            messages.append("分红数据缺失（DDM估值不可用）")
        if 'growth_data' in missing:
            messages.append("增长率数据缺失（PEG估值不可用）")
        if 'ebitda_data' in missing:
            messages.append("EBITDA数据缺失（EV/EBITDA估值不可用）")
        if 'cashflow_data' in missing:
            messages.append("现金流数据缺失（DCF估值不可用）")
        
        return "估值数据不完整: " + "; ".join(messages)

    def _get_data_suggestions(self, data_status: ValuationDataStatus) -> List[str]:
        """根据缺失数据生成建议"""
        suggestions = []
        
        if 'dividend_data' in data_status.missing_fields:
            suggestions.append("该股票可能未分红，DDM模型不适用，建议关注PEG或EV/EBITDA估值")
        if 'growth_data' in data_status.missing_fields:
            suggestions.append("增长率数据需要多期财报，新上市公司可能暂无足够数据")
        if not data_status.has_price_data:
            suggestions.append("请检查股票代码是否正确，或市场是否正常交易")
        
        if not suggestions:
            suggestions.append("建议稍后重试或查看其他估值指标")
        
        return suggestions

    def compare_valuation_models(self, stock_code: str) -> pd.DataFrame:
        """
        多模型对比分析

        Args:
            stock_code: 股票代码

        Returns:
            模型对比结果DataFrame
        """
        try:
            comprehensive_result = self.get_comprehensive_valuation(stock_code)

            if 'error' in comprehensive_result:
                return pd.DataFrame()

            current_price = comprehensive_result['current_price']
            valuation_results = comprehensive_result['valuation_results']

            comparison_data = []

            # DDM模型
            if 'ddm' in valuation_results and 'error' not in valuation_results['ddm']:
                ddm = valuation_results['ddm']
                comparison_data.append({
                    'model': 'DDM (股利折现)',
                    'fair_value': ddm.get('intrinsic_value', 0),
                    'current_price': current_price,
                    'upside': ((ddm.get('intrinsic_value', 0) - current_price) / current_price * 100) if current_price > 0 else 0,
                    'recommendation': ddm.get('recommendation', ''),
                    'applicable': '稳定分红公司'
                })

            # PEG模型
            if 'peg' in valuation_results and 'error' not in valuation_results['peg']:
                peg = valuation_results['peg']
                comparison_data.append({
                    'model': 'PEG (市盈增长比)',
                    'fair_value': peg.get('fair_price', 0),
                    'current_price': current_price,
                    'upside': peg.get('upside_potential', 0),
                    'recommendation': peg.get('valuation_status', ''),
                    'applicable': '成长型公司'
                })

            # EV/EBITDA模型
            if 'ev_ebitda' in valuation_results and 'error' not in valuation_results['ev_ebitda']:
                ev = valuation_results['ev_ebitda']
                comparison_data.append({
                    'model': 'EV/EBITDA (企业价值倍数)',
                    'fair_value': ev.get('implied_price', 0),
                    'current_price': current_price,
                    'upside': ev.get('upside_potential', 0),
                    'recommendation': ev.get('recommendation', ''),
                    'applicable': '资本密集型行业'
                })

            if not comparison_data:
                return pd.DataFrame()

            df = pd.DataFrame(comparison_data)
            df['fair_value'] = df['fair_value'].round(2)
            df['upside'] = df['upside'].round(2)

            return df

        except Exception as e:
            logger.error(f"模型对比失败: {stock_code}, 错误: {str(e)}")
            return pd.DataFrame()

    def get_valuation_report(self, stock_code: str) -> str:
        """
        生成估值报告

        Args:
            stock_code: 股票代码

        Returns:
            格式化的估值报告文本
        """
        try:
            result = self.get_comprehensive_valuation(stock_code)

            if 'error' in result:
                return f"估值报告生成失败: {result['error']}"

            report = []
            report.append("=" * 60)
            report.append(f"股票估值报告")
            report.append("=" * 60)
            report.append(f"股票代码: {result['stock_code']}")
            report.append(f"股票名称: {result['stock_name']}")
            report.append(f"当前价格: ¥{result['current_price']}")
            report.append(f"估值日期: {result['valuation_date']}")
            report.append("")
            report.append("-" * 60)
            report.append("合理价值区间")
            report.append("-" * 60)
            report.append(f"保守估值: ¥{result['fair_value_low']}")
            report.append(f"中性估值: ¥{result['fair_value_mid']}")
            report.append(f"乐观估值: ¥{result['fair_value_high']}")
            report.append(f"安全边际: {result['margin_of_safety']}%")
            report.append("")
            report.append("-" * 60)
            report.append("投资建议")
            report.append("-" * 60)
            report.append(f"综合建议: {result['overall_recommendation']}")
            report.append(f"置信水平: {result['confidence_level']}")
            report.append(f"有效模型: {', '.join(result['valid_models'])}")
            report.append("")
            report.append("=" * 60)

            return "\n".join(report)

        except Exception as e:
            logger.error(f"生成估值报告失败: {stock_code}, 错误: {str(e)}")
            return f"估值报告生成失败: {str(e)}"

    def get_fair_value_range(self, stock_code: str) -> Dict[str, float]:
        """
        计算合理价值区间

        Args:
            stock_code: 股票代码

        Returns:
            包含low, mid, high的价值区间字典
        """
        try:
            result = self.get_comprehensive_valuation(stock_code)

            if 'error' in result:
                return {'low': 0, 'mid': 0, 'high': 0}

            return {
                'low': result['fair_value_low'],
                'mid': result['fair_value_mid'],
                'high': result['fair_value_high']
            }

        except Exception as e:
            logger.error(f"计算价值区间失败: {stock_code}, 错误: {str(e)}")
            return {'low': 0, 'mid': 0, 'high': 0}

    # ========== 私有辅助方法 ==========

    def _calculate_ddm_valuation(self, stock_code: str) -> Dict[str, Any]:
        """计算DDM估值"""
        try:
            result = self.ddm_model.gordon_growth_model(stock_code)
            return result
        except Exception as e:
            logger.warning(f"DDM估值失败: {stock_code}, {str(e)}")
            return {'error': str(e)}

    def _calculate_peg_valuation(self, stock_code: str) -> Dict[str, Any]:
        """计算PEG估值"""
        try:
            result = self.peg_model.calculate_peg(stock_code)
            return result
        except Exception as e:
            logger.warning(f"PEG估值失败: {stock_code}, {str(e)}")
            return {'error': str(e)}

    def _calculate_ev_ebitda_valuation(self, stock_code: str) -> Dict[str, Any]:
        """计算EV/EBITDA估值"""
        try:
            result = self.ev_ebitda_model.calculate_ev_ebitda(stock_code)
            return result
        except Exception as e:
            logger.warning(f"EV/EBITDA估值失败: {stock_code}, {str(e)}")
            return {'error': str(e)}

    def _calculate_fair_value_range(self, valid_valuations: List[tuple]) -> Dict[str, float]:
        """
        计算合理价值区间

        Args:
            valid_valuations: [(model_name, value), ...] 有效估值列表

        Returns:
            包含low, mid, high, margin_of_safety的字典
        """
        if not valid_valuations:
            return {'low': 0, 'mid': 0, 'high': 0, 'margin_of_safety': 0}

        values = [v for _, v in valid_valuations]

        # 计算统计值
        mean_value = np.mean(values)
        median_value = np.median(values)
        std_value = np.std(values)

        # 保守估值：均值 - 0.5倍标准差
        low = max(0, mean_value - 0.5 * std_value)

        # 中性估值：中位数
        mid = median_value

        # 乐观估值：均值 + 0.5倍标准差
        high = mean_value + 0.5 * std_value

        return {
            'low': low,
            'mid': mid,
            'high': high,
            'margin_of_safety': 0  # 将在后续计算
        }

    def _get_current_price(self, stock_code: str, valuation_results: Dict[str, Any]) -> float:
        """从估值结果中提取当前价格"""
        for model_result in valuation_results.values():
            if isinstance(model_result, dict) and 'current_price' in model_result:
                price = model_result.get('current_price', 0)
                if price > 0:
                    return price
        return 0

    def _get_stock_name(self, valuation_results: Dict[str, Any]) -> str:
        """从估值结果中提取股票名称"""
        for model_result in valuation_results.values():
            if isinstance(model_result, dict) and 'stock_name' in model_result:
                name = model_result.get('stock_name', '')
                if name:
                    return name
        return ''

    def _generate_overall_recommendation(
        self,
        current_price: float,
        fair_value_range: Dict[str, float],
        valuation_results: Dict[str, Any]
    ) -> Dict[str, str]:
        """生成综合投资建议"""
        if current_price <= 0:
            return {'recommendation': '数据不足', 'confidence': '低'}

        mid_value = fair_value_range['mid']

        # 计算安全边际
        margin_of_safety = ((mid_value - current_price) / current_price * 100) if current_price > 0 else 0
        fair_value_range['margin_of_safety'] = margin_of_safety

        # 根据安全边际生成建议
        if margin_of_safety >= 30:
            recommendation = '强烈买入'
        elif margin_of_safety >= 15:
            recommendation = '买入'
        elif margin_of_safety >= 0:
            recommendation = '持有'
        elif margin_of_safety >= -15:
            recommendation = '观望'
        else:
            recommendation = '卖出'

        # 评估置信度
        valid_models_count = sum(1 for v in valuation_results.values() if isinstance(v, dict) and 'error' not in v)

        if valid_models_count >= 3:
            confidence = '高'
        elif valid_models_count >= 2:
            confidence = '中'
        else:
            confidence = '低'

        return {
            'recommendation': recommendation,
            'confidence': confidence
        }

