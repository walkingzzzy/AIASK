"""
估值分析工具 - CrewAI Tool

提供多模型估值分析功能，包括：
- 综合估值分析
- 多模型对比
- 估值报告生成
- 合理价值区间计算
"""
from crewai.tools import BaseTool
from typing import Any, Optional, Type
from pydantic import BaseModel, Field
import logging

from ..valuation import ValuationSummary

logger = logging.getLogger(__name__)


class ValuationToolSchema(BaseModel):
    """估值工具输入参数"""
    stock_code: str = Field(..., description="股票代码，如：000001.SZ或600519.SH")
    analysis_type: str = Field(
        default="comprehensive",
        description="分析类型：comprehensive（综合估值）、compare（模型对比）、report（估值报告）、range（价值区间）"
    )


class ValuationTool(BaseTool):
    """
    估值分析工具

    整合多种估值模型（DDM、PEG、EV/EBITDA）提供综合估值分析
    """
    name: str = "估值分析工具"
    description: str = "对A股公司进行多模型估值分析，包括DDM、PEG、EV/EBITDA等模型，提供综合估值建议"
    args_schema: Type[BaseModel] = ValuationToolSchema

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.valuation_summary = ValuationSummary()

    def _run(self, stock_code: str, analysis_type: str = "comprehensive", **kwargs) -> Any:
        """
        执行估值分析

        Args:
            stock_code: 股票代码
            analysis_type: 分析类型

        Returns:
            估值分析结果
        """
        try:
            if analysis_type == "comprehensive":
                return self._comprehensive_valuation(stock_code)
            elif analysis_type == "compare":
                return self._compare_models(stock_code)
            elif analysis_type == "report":
                return self._generate_report(stock_code)
            elif analysis_type == "range":
                return self._get_value_range(stock_code)
            else:
                return f"不支持的分析类型: {analysis_type}"

        except Exception as e:
            logger.error(f"估值分析失败: {stock_code}, 错误: {str(e)}")
            return f"估值分析失败: {str(e)}"

    def _comprehensive_valuation(self, stock_code: str) -> str:
        """综合估值分析"""
        try:
            result = self.valuation_summary.get_comprehensive_valuation(stock_code)

            if 'error' in result:
                return f"估值分析失败: {result['error']}"

            output = []
            output.append(f"=== {result['stock_name']} ({result['stock_code']}) 综合估值分析 ===\n")
            output.append(f"当前价格: ¥{result['current_price']}")
            output.append(f"估值日期: {result['valuation_date']}\n")

            output.append("【合理价值区间】")
            output.append(f"  保守估值: ¥{result['fair_value_low']}")
            output.append(f"  中性估值: ¥{result['fair_value_mid']}")
            output.append(f"  乐观估值: ¥{result['fair_value_high']}")
            output.append(f"  安全边际: {result['margin_of_safety']}%\n")

            output.append("【投资建议】")
            output.append(f"  综合建议: {result['overall_recommendation']}")
            output.append(f"  置信水平: {result['confidence_level']}")
            output.append(f"  有效模型: {', '.join(result['valid_models'])}\n")

            # 添加各模型详情
            valuation_results = result.get('valuation_results', {})

            if 'ddm' in valuation_results and 'error' not in valuation_results['ddm']:
                ddm = valuation_results['ddm']
                output.append("【DDM模型 - 股利折现】")
                output.append(f"  内在价值: ¥{ddm.get('intrinsic_value', 0)}")
                output.append(f"  股息增长率: {ddm.get('dividend_growth_rate', 0)}%")
                output.append(f"  建议: {ddm.get('recommendation', '')}\n")

            if 'peg' in valuation_results and 'error' not in valuation_results['peg']:
                peg = valuation_results['peg']
                output.append("【PEG模型 - 市盈增长比】")
                output.append(f"  合理价格: ¥{peg.get('fair_price', 0)}")
                output.append(f"  PEG值: {peg.get('peg', 0)}")
                output.append(f"  估值状态: {peg.get('valuation_status', '')}\n")

            if 'ev_ebitda' in valuation_results and 'error' not in valuation_results['ev_ebitda']:
                ev = valuation_results['ev_ebitda']
                output.append("【EV/EBITDA模型 - 企业价值倍数】")
                output.append(f"  隐含价格: ¥{ev.get('implied_price', 0)}")
                output.append(f"  EV/EBITDA: {ev.get('ev_ebitda', 0)}")
                output.append(f"  建议: {ev.get('recommendation', '')}\n")

            return "\n".join(output)

        except Exception as e:
            logger.error(f"综合估值分析失败: {stock_code}, 错误: {str(e)}")
            return f"综合估值分析失败: {str(e)}"

    def _compare_models(self, stock_code: str) -> str:
        """模型对比分析"""
        try:
            df = self.valuation_summary.compare_valuation_models(stock_code)

            if df.empty:
                return "无法获取模型对比数据"

            output = []
            output.append(f"=== {stock_code} 估值模型对比 ===\n")

            for _, row in df.iterrows():
                output.append(f"【{row['model']}】")
                output.append(f"  合理价值: ¥{row['fair_value']}")
                output.append(f"  当前价格: ¥{row['current_price']}")
                output.append(f"  上涨空间: {row['upside']}%")
                output.append(f"  建议: {row['recommendation']}")
                output.append(f"  适用场景: {row['applicable']}\n")

            return "\n".join(output)

        except Exception as e:
            logger.error(f"模型对比失败: {stock_code}, 错误: {str(e)}")
            return f"模型对比失败: {str(e)}"

    def _generate_report(self, stock_code: str) -> str:
        """生成估值报告"""
        try:
            report = self.valuation_summary.get_valuation_report(stock_code)
            return report

        except Exception as e:
            logger.error(f"生成估值报告失败: {stock_code}, 错误: {str(e)}")
            return f"生成估值报告失败: {str(e)}"

    def _get_value_range(self, stock_code: str) -> str:
        """获取价值区间"""
        try:
            range_data = self.valuation_summary.get_fair_value_range(stock_code)

            if range_data['mid'] == 0:
                return "无法计算价值区间"

            output = []
            output.append(f"=== {stock_code} 合理价值区间 ===\n")
            output.append(f"保守估值: ¥{range_data['low']:.2f}")
            output.append(f"中性估值: ¥{range_data['mid']:.2f}")
            output.append(f"乐观估值: ¥{range_data['high']:.2f}")

            return "\n".join(output)

        except Exception as e:
            logger.error(f"获取价值区间失败: {stock_code}, 错误: {str(e)}")
            return f"获取价值区间失败: {str(e)}"

