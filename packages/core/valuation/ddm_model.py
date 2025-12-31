"""
股利折现模型(Dividend Discount Model, DDM)

DDM是一种基于股息现金流的股票估值方法，适用于稳定分红的成熟公司。

包含的模型：
1. Gordon Growth Model (单阶段DDM) - 适用于稳定增长的成熟公司
2. 两阶段DDM - 适用于当前高增长但未来会稳定的公司
3. 三阶段DDM - 高增长期-> 过渡期 -> 稳定期

核心公式：
- Gordon模型: V = D1 / (r - g)
- 其中 D1 = D0 * (1 + g), r为要求回报率, g为股息增长率

要求回报率计算（CAPM）:
r = Rf + β * (Rm - Rf)
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class DDMResult:
    """DDM估值结果"""
    stock_code: str
    stock_name: str
    current_dividend: float
    dividend_growth_rate: float
    required_return: float
    intrinsic_value: float
    current_price: float
    margin_of_safety: float
    recommendation: str
    model_type: str


class DDMValuation:
    """
    股利折现模型- Gordon Growth Model 和多阶段DDM
    适用于：
    - 有稳定分红历史的成熟公司
    - 公用事业、银行、消费品等行业
    
    不适用于：
    - 不分红的成长型公司
    - 分红不稳定的公司
    """
    
    # 默认参数（可通过环境变量覆盖）
    DEFAULT_RISK_FREE_RATE = float(os.environ.get('DDM_RISK_FREE_RATE', '0.03'))
    DEFAULT_MARKET_PREMIUM = float(os.environ.get('DDM_MARKET_PREMIUM', '0.06'))
    DEFAULT_STABLE_GROWTH = float(os.environ.get('DDM_STABLE_GROWTH', '0.03'))
    
    def __init__(self, risk_free_rate: float = None, market_premium: float = None):
        """
        初始化DDM估值模型
        
        Args:
            risk_free_rate: 无风险利率（默认从环境变量或3%）
            market_premium: 市场风险溢价（默认从环境变量或6%）
        """
        self.risk_free_rate = risk_free_rate if risk_free_rate is not None else self.DEFAULT_RISK_FREE_RATE
        self.market_premium = market_premium if market_premium is not None else self.DEFAULT_MARKET_PREMIUM
        self._cache: Dict[str, Any] = {}
        if not AKSHARE_AVAILABLE:
            logger.warning("akshare库未安装，部分功能可能不可用")
    
    def gordon_growth_model(self, stock_code: str) -> Dict[str, Any]:
        """
        戈登增长模型（单阶段DDM）
        适用于稳定增长的成熟公司
        
        公式: V = D1 / (r - g)
        其中 D1 = D0 * (1 + g)
        Args:
            stock_code: 股票代码
            
        Returns:
            {
                'stock_code': str,          # 股票代码
                'stock_name': str,          # 股票名称
                'current_dividend': float,  # 当前每股股息(D0)
                'next_dividend': float,# 下一期股息 (D1)
                'dividend_growth_rate': float,  # 股息增长率(g)
                'required_return': float,   # 要求回报率 (r) - CAPM计算
                'intrinsic_value': float,   # 内在价值
                'current_price': float,     # 当前价格
                'margin_of_safety': float,  # 安全边际（%）
                'recommendation': str,      # 投资建议
                'dividend_yield': float,# 股息率
                'payout_ratio': float,      # 股息支付率
                'model_validity': str,      # 模型适用性
            }
        """
        try:
            code = self._parse_stock_code(stock_code)
            
            # 获取股息历史
            dividend_data = self.get_dividend_history(stock_code, years=5)
            if dividend_data is None or dividend_data.empty:
                return self._create_error_result(stock_code, "无法获取股息历史数据，该股票可能不分红")
            
            # 获取当前股息
            current_dividend = dividend_data['dividend'].iloc[-1] if len(dividend_data) > 0 else 0
            if current_dividend <= 0:
                return self._create_error_result(stock_code, "当前股息为零或负，不适用DDM模型")
            
            # 估算股息增长率
            dividend_growth_rate = self.estimate_dividend_growth(stock_code)
            
            # 计算要求回报率
            required_return = self.calculate_required_return(stock_code)
            
            # 验证模型条件: r > g
            if required_return <= dividend_growth_rate:
                return self._create_error_result(
                    stock_code, 
                    f"要求回报率({required_return:.2%})必须大于增长率({dividend_growth_rate:.2%})"
                )
            
            # 计算下一期股息
            next_dividend = current_dividend * (1 + dividend_growth_rate)
            
            # Gordon模型计算内在价值
            intrinsic_value = next_dividend / (required_return - dividend_growth_rate)
            
            # 获取当前价格
            quote_data = self._get_quote_data(code)
            current_price = quote_data.get('current_price', 0) if quote_data else 0
            stock_name = quote_data.get('stock_name', '') if quote_data else ''
            
            # 计算安全边际
            if current_price > 0:
                margin_of_safety = ((intrinsic_value - current_price) / current_price) * 100
            else:
                margin_of_safety = 0
            
            # 生成投资建议
            recommendation = self._generate_recommendation(margin_of_safety)
            
            # 计算股息率
            dividend_yield = (current_dividend / current_price * 100) if current_price > 0 else 0
            
            # 获取股息支付率
            payout_ratio = self._get_payout_ratio(code)
            
            # 评估模型适用性
            model_validity = self._assess_model_validity(dividend_data, dividend_growth_rate)
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'current_dividend': round(current_dividend, 4),
                'next_dividend': round(next_dividend, 4),
                'dividend_growth_rate': round(dividend_growth_rate * 100, 2),  # 转为百分比
                'required_return': round(required_return * 100, 2),  # 转为百分比
                'intrinsic_value': round(intrinsic_value, 2),
                'current_price': round(current_price, 2),
                'margin_of_safety': round(margin_of_safety, 2),
                'recommendation': recommendation,
                'dividend_yield': round(dividend_yield, 2),
                'payout_ratio': round(payout_ratio, 2),
                'model_validity': model_validity,'model_type': 'Gordon Growth Model'
            }
            
        except Exception as e:
            logger.error(f"Gordon模型计算失败: {stock_code},错误: {str(e)}")
            return self._create_error_result(stock_code, str(e))
    
    def two_stage_ddm(self, stock_code: str,
                      high_growth_years: int = 5,
                      high_growth_rate: float = None,
                      stable_growth_rate: float = 0.03) -> Dict[str, Any]:
        """
        两阶段DDM
        适用于当前高增长但未来会稳定的公司
        阶段1：高增长期（n年）
        阶段2：稳定增长期（永续）
        
        公式:
        V = Σ[D0*(1+g1)^t / (1+r)^t] + [Dn*(1+g2)/(r-g2)] / (1+r)^n
        
        Args:
            stock_code: 股票代码
            high_growth_years: 高增长期年数，默认5年
            high_growth_rate: 高增长期增长率，None则自动估算
            stable_growth_rate: 稳定期增长率，默认3%
            
        Returns:
            两阶段DDM估值结果
        """
        try:
            code = self._parse_stock_code(stock_code)
            
            # 获取股息历史
            dividend_data = self.get_dividend_history(stock_code, years=5)
            if dividend_data is None or dividend_data.empty:
                return self._create_error_result(stock_code, "无法获取股息历史数据")
            
            # 当前股息
            current_dividend = dividend_data['dividend'].iloc[-1] if len(dividend_data) > 0 else 0
            if current_dividend <= 0:
                return self._create_error_result(stock_code, "当前股息为零，不适用DDM模型")
            
            # 确定高增长率
            if high_growth_rate is None:
                high_growth_rate = self.estimate_dividend_growth(stock_code)
            
            # 计算要求回报率
            required_return = self.calculate_required_return(stock_code)
            
            # 验证: r > g2
            if required_return <= stable_growth_rate:
                return self._create_error_result(
                    stock_code,
                    f"要求回报率({required_return:.2%})必须大于永续增长率({stable_growth_rate:.2%})"
                )
            
            # 阶段1：计算高增长期股息现值
            pv_stage1 =0
            dividend = current_dividend
            for year in range(1, high_growth_years + 1):
                dividend = dividend * (1 + high_growth_rate)
                pv_stage1 += dividend / ((1 + required_return) ** year)
            
            # 阶段1结束时的股息
            dividend_n = dividend
            
            # 阶段2：计算终值（Gordon模型）
            terminal_dividend = dividend_n * (1 + stable_growth_rate)
            terminal_value = terminal_dividend / (required_return - stable_growth_rate)
            pv_terminal = terminal_value / ((1 + required_return) ** high_growth_years)
            
            # 总内在价值
            intrinsic_value = pv_stage1 + pv_terminal
            
            # 获取当前价格
            quote_data = self._get_quote_data(code)
            current_price = quote_data.get('current_price', 0) if quote_data else 0
            stock_name = quote_data.get('stock_name', '') if quote_data else ''
            
            # 计算安全边际
            if current_price > 0:
                margin_of_safety = ((intrinsic_value - current_price) / current_price) * 100
            else:
                margin_of_safety = 0
            
            # 生成投资建议
            recommendation = self._generate_recommendation(margin_of_safety)
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'current_dividend': round(current_dividend, 4),
                'high_growth_rate': round(high_growth_rate * 100, 2),
                'high_growth_years': high_growth_years,
                'stable_growth_rate': round(stable_growth_rate * 100, 2),
                'required_return': round(required_return * 100, 2),
                'pv_stage1': round(pv_stage1, 2),
                'pv_terminal': round(pv_terminal, 2),
                'intrinsic_value': round(intrinsic_value, 2),
                'current_price': round(current_price, 2),
                'margin_of_safety': round(margin_of_safety, 2),
                'recommendation': recommendation,
                'model_type': 'Two-Stage DDM'
            }
            
        except Exception as e:
            logger.error(f"两阶段DDM计算失败: {stock_code}, 错误: {str(e)}")
            return self._create_error_result(stock_code, str(e))
    
    def three_stage_ddm(self, stock_code: str,
                        high_growth_years: int = 5,
                        transition_years: int = 5,
                        high_growth_rate: float = None,
                        stable_growth_rate: float = 0.03) -> Dict[str, Any]:
        """
        三阶段DDM
        高增长期 -> 过渡期 -> 稳定期
        阶段1：高增长期（n1年）- 保持高增长率
        阶段2：过渡期（n2年）- 增长率线性递减
        阶段3：稳定期（永续）- 保持稳定增长率
        
        Args:
            stock_code: 股票代码
            high_growth_years: 高增长期年数，默认5年
            transition_years: 过渡期年数，默认5年
            high_growth_rate: 高增长期增长率，None则自动估算
            stable_growth_rate: 稳定期增长率，默认3%
            
        Returns:
            三阶段DDM估值结果
        """
        try:
            code = self._parse_stock_code(stock_code)
            
            # 获取股息历史
            dividend_data = self.get_dividend_history(stock_code, years=5)
            if dividend_data is None or dividend_data.empty:
                return self._create_error_result(stock_code, "无法获取股息历史数据")
            
            # 当前股息
            current_dividend = dividend_data['dividend'].iloc[-1] if len(dividend_data) > 0 else 0
            if current_dividend <= 0:
                return self._create_error_result(stock_code, "当前股息为零，不适用DDM模型")
            
            # 确定高增长率
            if high_growth_rate is None:
                high_growth_rate = self.estimate_dividend_growth(stock_code)
            
            # 计算要求回报率
            required_return = self.calculate_required_return(stock_code)
            
            # 验证条件
            if required_return <= stable_growth_rate:
                return self._create_error_result(
                    stock_code,
                    f"要求回报率({required_return:.2%})必须大于永续增长率({stable_growth_rate:.2%})"
                )
            
            # 阶段1：高增长期
            pv_stage1 = 0
            dividend = current_dividend
            for year in range(1, high_growth_years + 1):
                dividend = dividend * (1 + high_growth_rate)
                pv_stage1 += dividend / ((1 + required_return) ** year)
            
            # 阶段2：过渡期（增长率线性递减）
            pv_stage2 = 0
            growth_decrement = (high_growth_rate - stable_growth_rate) / transition_years
            
            current_growth = high_growth_rate
            for year in range(1, transition_years + 1):
                current_growth = current_growth - growth_decrement
                dividend = dividend * (1 + current_growth)
                discount_year = high_growth_years + year
                pv_stage2 += dividend / ((1 + required_return) ** discount_year)
            
            # 阶段3：稳定期（Gordon模型）
            terminal_dividend = dividend * (1 + stable_growth_rate)
            terminal_value = terminal_dividend / (required_return - stable_growth_rate)
            total_years = high_growth_years + transition_years
            pv_terminal = terminal_value / ((1 + required_return) ** total_years)
            
            # 总内在价值
            intrinsic_value = pv_stage1 + pv_stage2 + pv_terminal
            
            # 获取当前价格
            quote_data = self._get_quote_data(code)
            current_price = quote_data.get('current_price', 0) if quote_data else 0
            stock_name = quote_data.get('stock_name', '') if quote_data else ''
            
            # 计算安全边际
            if current_price > 0:
                margin_of_safety = ((intrinsic_value - current_price) / current_price) * 100
            else:
                margin_of_safety = 0
            
            # 生成投资建议
            recommendation = self._generate_recommendation(margin_of_safety)
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'current_dividend': round(current_dividend, 4),
                'high_growth_rate': round(high_growth_rate * 100, 2),
                'high_growth_years': high_growth_years,
                'transition_years': transition_years,
                'stable_growth_rate': round(stable_growth_rate * 100, 2),
                'required_return': round(required_return * 100, 2),
                'pv_stage1': round(pv_stage1, 2),
                'pv_stage2': round(pv_stage2, 2),
                'pv_terminal': round(pv_terminal, 2),
                'intrinsic_value': round(intrinsic_value, 2),
                'current_price': round(current_price, 2),
                'margin_of_safety': round(margin_of_safety, 2),
                'recommendation': recommendation,
                'model_type': 'Three-Stage DDM'
            }
            
        except Exception as e:
            logger.error(f"三阶段DDM计算失败: {stock_code}, 错误: {str(e)}")
            return self._create_error_result(stock_code, str(e))
    
    def calculate_required_return(self, stock_code: str) -> float:
        """
        使用CAPM计算要求回报率
        
        公式: r = Rf + β * (Rm - Rf)
        
        其中:
        - Rf: 无风险利率
        - β: 股票Beta系数
        - Rm - Rf: 市场风险溢价
        
        Args:
            stock_code: 股票代码
            
        Returns:
            要求回报率（小数形式，如0.12表示12%）
        """
        try:
            code = self._parse_stock_code(stock_code)
            
            # 获取Beta值
            beta = self._get_beta(code)
            
            # CAPM公式
            required_return = self.risk_free_rate + beta * self.market_premium
            
            # 确保要求回报率在合理范围内
            required_return = max(0.05, min(0.25, required_return))
            
            return required_return
            
        except Exception as e:
            logger.warning(f"计算要求回报率失败: {stock_code}, 使用默认值")
            return self.risk_free_rate +1.0 * self.market_premium  # 默认Beta=1
    
    def get_dividend_history(self, stock_code: str, years: int = 5) -> Optional[pd.DataFrame]:
        """
        获取股息历史
        
        Args:
            stock_code: 股票代码
            years: 历史年数
            
        Returns:
            DataFrame with columns: ['year', 'dividend', 'ex_date']
        """
        if not AKSHARE_AVAILABLE:
            return None
        
        try:
            code = self._parse_stock_code(stock_code)
            
            # 获取分红数据
            try:
                # 尝试使用东方财富分红数据
                df = ak.stock_fhps_em(symbol=code)
                if df is not None and not df.empty:
                    # 处理分红数据
                    result = self._parse_dividend_data_em(df, years)
                    if result is not None and not result.empty:
                        return result
            except Exception:
                pass
            
            # 备用方案：使用其他数据源
            try:
                df = ak.stock_history_dividend(symbol=code)
                if df is not None and not df.empty:
                    return self._parse_dividend_data(df, years)
            except Exception:
                pass
            
            return None
            
        except Exception as e:
            logger.error(f"获取股息历史失败: {stock_code}, 错误: {str(e)}")
            return None
    
    def estimate_dividend_growth(self, stock_code: str) -> float:
        """
        估算股息增长率
        
        使用方法：
        1. 历史股息增长率的几何平均
        2. 可持续增长率 = ROE * (1 - 派息率)
        3. 结合两者给出估算
        
        Args:
            stock_code: 股票代码
            
        Returns:
            股息增长率（小数形式）
        """
        try:
            code = self._parse_stock_code(stock_code)
            
            # 方法1：历史股息增长率
            historical_growth = self._calculate_historical_dividend_growth(code)
            
            # 方法2：可持续增长率
            sustainable_growth = self._calculate_sustainable_growth(code)
            
            # 综合两个估算
            if historical_growth is not None and sustainable_growth is not None:
                # 加权平均，给予历史数据更高权重
                growth_rate = 0.6 * historical_growth + 0.4 * sustainable_growth
            elif historical_growth is not None:
                growth_rate = historical_growth
            elif sustainable_growth is not None:
                growth_rate = sustainable_growth
            else:
                # 使用保守估计
                growth_rate = 0.03
            
            # 限制增长率范围（不应超过长期GDP增速）
            growth_rate = max(0.0, min(0.15, growth_rate))
            
            return growth_rate
            
        except Exception as e:
            logger.warning(f"估算股息增长率失败: {stock_code}, 使用默认值")
            return 0.03
    
    def sensitivity_analysis(self, stock_code: str, 
                            growth_range: tuple = (-0.02, 0.02),
                            return_range: tuple = (-0.02, 0.02)) -> pd.DataFrame:
        """
        敏感性分析
        
        分析内在价值对增长率和要求回报率的敏感度
        
        Args:
            stock_code: 股票代码
            growth_range: 增长率变动范围
            return_range: 要求回报率变动范围
            
        Returns:
            敏感性矩阵DataFrame
        """
        try:
            # 获取基础数据
            base_result = self.gordon_growth_model(stock_code)
            if 'error' in base_result:
                return pd.DataFrame()
            
            base_growth = base_result['dividend_growth_rate'] / 100
            base_return = base_result['required_return'] / 100
            current_dividend = base_result['current_dividend']
            
            # 生成变动序列
            growth_steps = np.linspace(growth_range[0], growth_range[1], 5)
            return_steps = np.linspace(return_range[0], return_range[1], 5)
            
            # 构建敏感性矩阵
            results = []
            for g_delta in growth_steps:
                row = []
                for r_delta in return_steps:
                    g = base_growth + g_delta
                    r = base_return + r_delta
                    
                    if r > g and r > 0 and g >= 0:
                        d1 = current_dividend * (1 + g)
                        value = d1 / (r - g)
                    else:
                        value = np.nan
                    
                    row.append(round(value, 2) if not np.isnan(value) else 'N/A')
                results.append(row)
            
            # 创建DataFrame
            columns = [f"r{r_delta*100:+.1f}%" for r_delta in return_steps]
            index = [f"g{g_delta*100:+.1f}%" for g_delta in growth_steps]
            
            df = pd.DataFrame(results, index=index, columns=columns)
            return df
            
        except Exception as e:
            logger.error(f"敏感性分析失败: {stock_code}, 错误: {str(e)}")
            return pd.DataFrame()
    
    def _parse_stock_code(self, stock_code: str) -> str:
        """解析股票代码，返回纯数字代码"""
        if '.' in stock_code:
            return stock_code.split('.')[0]
        return stock_code
    
    def _get_quote_data(self, code: str) -> Optional[Dict[str, Any]]:
        """获取实时行情数据"""
        if not AKSHARE_AVAILABLE:
            return None
        
        try:
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return None
            
            stock_data = df[df['代码'] == code]
            if stock_data.empty:
                return None
            
            row = stock_data.iloc[0]
            def safe_float(val, default=0.0):
                try:
                    if pd.isna(val):
                        return default
                    return float(val)
                except (ValueError, TypeError):
                    return default
            
            return {
                'stock_name': str(row.get('名称', '')),
                'current_price': safe_float(row.get('最新价')),
                'pe_ttm': safe_float(row.get('市盈率-动态')),
                'market_cap': safe_float(row.get('总市值'))
            }
            
        except Exception as e:
            logger.error(f"获取行情数据失败: {code}, 错误: {str(e)}")
            return None
    
    def _get_beta(self, code: str) -> float:
        """获取股票Beta值"""
        try:
            # 尝试获取Beta值
            # 如果无法获取，返回默认值1.0
            # 实际应用中可以从专业数据源获取
            return 1.0
        except Exception:
            return 1.0
    
    def _get_payout_ratio(self, code: str) -> float:
        """获取股息支付率"""
        if not AKSHARE_AVAILABLE:
            return 0
        
        try:
            # 获取财务数据
            df = ak.stock_financial_analysis_indicator(symbol=code)
            if df is None or df.empty:
                return 0
            
            latest = df.iloc[-1]
            
            # 尝试获取股息支付率相关数据
            eps = float(latest.get('每股收益', 0)) if pd.notna(latest.get('每股收益')) else 0
            
            # 获取每股股息
            dividend_data = self.get_dividend_history(code + '.SH', years=1)
            if dividend_data is not None and not dividend_data.empty:
                dps = dividend_data['dividend'].iloc[-1]
                if eps > 0:
                    return (dps / eps) * 100
            
            return 0
            
        except Exception:
            return 0
    
    def _calculate_historical_dividend_growth(self, code: str) -> Optional[float]:
        """计算历史股息增长率"""
        try:
            dividend_data = self.get_dividend_history(code + '.SH', years=5)
            if dividend_data is None or len(dividend_data) < 2:
                return None
            
            dividends = dividend_data['dividend'].values
            if len(dividends) >= 2 and dividends[0] > 0 and dividends[-1] > 0:
                years = len(dividends) - 1
                cagr = (dividends[-1] / dividends[0]) ** (1 / years) - 1
                return cagr
            
            return None
            
        except Exception:
            return None
    
    def _calculate_sustainable_growth(self, code: str) -> Optional[float]:
        """计算可持续增长率 = ROE * (1 - 派息率)"""
        if not AKSHARE_AVAILABLE:
            return None
        
        try:
            df = ak.stock_financial_analysis_indicator(symbol=code)
            if df is None or df.empty:
                return None
            latest = df.iloc[-1]
            
            # 获取ROE
            roe = float(latest.get('净资产收益率', 0)) if pd.notna(latest.get('净资产收益率')) else 0
            
            # 获取派息率
            payout_ratio = self._get_payout_ratio(code) / 100  # 转为小数
            
            if roe > 0:
                # 可持续增长率 = ROE * (1 - 派息率)
                sustainable_growth = (roe / 100) * (1 - payout_ratio)
                return sustainable_growth
            return None
            
        except Exception:
            return None
    def _parse_dividend_data_em(self, df: pd.DataFrame, years: int) -> Optional[pd.DataFrame]:
        """解析东方财富分红数据"""
        try:
            # 东方财富分红数据格式处理
            result = []
            current_year = datetime.now().year
            
            for _, row in df.iterrows():
                try:
                    # 尝试解析年份
                    report_date = row.get('报告期', row.get('公告日期', ''))
                    if isinstance(report_date, str) and len(report_date) >= 4:
                        year = int(report_date[:4])
                    elif hasattr(report_date, 'year'):
                        year = report_date.year
                    else:
                        continue
            
                    
                    # 只取最近n年的数据
                    if year < current_year - years:
                        continue
            
                    
                    # 获取每股股息
                    dividend = 0
                    for col in ['派息', '现金分红', '每股股利', '每股派息']:
                        if col in df.columns and pd.notna(row.get(col)):
                            dividend = float(row[col])
                            break
                    
                    if dividend > 0:
                        result.append({
                            'year': year,
                            'dividend': dividend,
                            'ex_date': str(report_date)
                        })
                except Exception:
                    continue
            
            if result:
                result_df = pd.DataFrame(result)
                result_df = result_df.sort_values('year')
                return result_df
            
            return None
            
        except Exception:
            return None
    
    def _parse_dividend_data(self, df: pd.DataFrame, years: int) -> Optional[pd.DataFrame]:
        """解析通用分红数据"""
        try:
            result = []
            current_year = datetime.now().year
            
            for _, row in df.iterrows():
                try:
                    # 获取年份
                    year = None
                    for col in ['年度', '年份', 'year']:
                        if col in df.columns and pd.notna(row.get(col)):
                            val = row[col]
                            if isinstance(val, (int, float)):
                                year = int(val)
                            elif isinstance(val, str) and len(val) >= 4:
                                year = int(val[:4])
                            break
                    
                    if year is None or year < current_year - years:
                        continue
            
                    
                    # 获取股息
                    dividend = 0
                    for col in ['每股股利', '派息', '现金分红', 'dividend']:
                        if col in df.columns and pd.notna(row.get(col)):
                            dividend = float(row[col])
                            break
                    
                    if dividend > 0:
                        result.append({
                            'year': year,
                            'dividend': dividend,
                            'ex_date': ''
                        })
                except Exception:
                    continue
            
            if result:
                result_df = pd.DataFrame(result)
                result_df = result_df.sort_values('year')
                return result_df
            
            return None
            
        except Exception:
            return None
    
    def _generate_recommendation(self, margin_of_safety: float) -> str:
        """根据安全边际生成投资建议"""
        if margin_of_safety >= 30:
            return '强烈买入'
        elif margin_of_safety >= 15:
            return '买入'
        elif margin_of_safety >= 0:
            return '持有'
        elif margin_of_safety >= -15:
            return '观望'
        elif margin_of_safety >= -30:
            return '卖出'
        else:
            return '强烈卖出'
    
    def _assess_model_validity(self, dividend_data: pd.DataFrame, growth_rate: float) -> str:
        """评估DDM模型的适用性"""
        if dividend_data is None or len(dividend_data) < 3:
            return '数据不足，模型可靠性低'
        
        # 计算股息稳定性
        dividends = dividend_data['dividend'].values
        if len(dividends) >= 3:
            cv = np.std(dividends) / np.mean(dividends) if np.mean(dividends) > 0 else float('inf')
            
            if cv < 0.1:
                stability = '非常稳定'
            elif cv < 0.25:
                stability = '较稳定'
            elif cv < 0.5:
                stability = '一般'
            else:
                stability = '波动较大'
        else:
            stability = '数据不足'
        
        # 增长率合理性
        if 0 < growth_rate < 0.05:
            growth_assess = '增长率保守合理'
        elif 0.05 <= growth_rate < 0.10:
            growth_assess = '增长率适中'
        elif growth_rate >= 0.10:
            growth_assess = '增长率偏高，需谨慎'
        else:
            growth_assess = '增长率异常'
        
        return f'{stability}，{growth_assess}'
    
    def _create_error_result(self, stock_code: str, error_msg: str) -> Dict[str, Any]:
        """创建错误结果"""
        return {
            'stock_code': stock_code,
            'error': error_msg,
            'current_dividend': 0,
            'dividend_growth_rate': 0,
            'required_return': 0,
            'intrinsic_value': 0,
            'current_price': 0,
            'margin_of_safety': 0,
            'recommendation': '不适用',
            'model_type': 'N/A'
        }