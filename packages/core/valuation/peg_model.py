"""
PEG估值模型 - 市盈率相对盈利增长比率

PEG = PE / EPS增长率

PEG估值标准：
- PEG < 0.5: 严重低估
- 0.5 <= PEG < 1: 低估
- 1 <= PEG< 1.5: 合理
- 1.5 <= PEG < 2: 偏高
- PEG >= 2: 高估
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging
import pandas as pd
import numpy as np

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class PEGResult:
    """PEG估值结果"""
    stock_code: str
    stock_name: str
    pe_ttm: float
    eps_growth_rate: float
    peg: float
    valuation_status: str
    current_price: float
    fair_price: float
    upside_potential: float
    confidence: str


class PEGValuation:
    """
    PEG估值模型 - 市盈率相对盈利增长比率
    
    PEG是一种结合市盈率(PE)和盈利增长率的估值指标，
    能够更全面地评估成长型股票的估值水平。
    
    公式: PEG = PE / EPS增长率(%)
    
    使用场景:
    - 评估成长型股票的估值合理性
    -筛选具有良好性价比的成长股
    - 行业内公司估值比较
    """
    
    # PEG估值阈值
    PEG_THRESHOLDS = {
        'severely_undervalued': 0.5,
        'undervalued': 1.0,
        'fairly_valued': 1.5,
        'overvalued': 2.0
    }
    
    def __init__(self, cache_enabled: bool = True):
        """
        初始化PEG估值模型
        
        Args:
            cache_enabled: 是否启用缓存
        """
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, Any] = {}
        if not AKSHARE_AVAILABLE:
            logger.warning("akshare库未安装，部分功能可能不可用")
    
    def calculate_peg(self, stock_code: str, periods: int = 3) -> Dict[str, Any]:
        """
        计算PEG值
        
        PEG = PE(TTM) / EPS增长率(%)
        
        Args:
            stock_code: 股票代码，如 600519.SH或 000001.SZ
            periods: 计算EPS增长率的年数，默认3年
            
        Returns:
            {
                'stock_code': str,        # 股票代码
                'stock_name': str,        # 股票名称
                'pe_ttm': float,          # 滚动市盈率
                'eps_growth_rate': float, # EPS增长率（%）
                'peg': float,             # PEG值
                'valuation_status': str,  # 估值状态：严重低估/低估/合理/偏高/高估
                'current_price': float,   # 当前价格
                'fair_price': float,      # 合理价格（基于PEG=1计算）
                'upside_potential': float,# 上涨空间（%）
                'confidence': str,        # 置信度：高/中/低'details': dict,# 详细计算数据
            }
        """
        try:
            # 解析股票代码
            code = self._parse_stock_code(stock_code)
            
            # 获取实时行情数据
            quote_data = self._get_quote_data(code)
            if quote_data is None:
                return self._create_error_result(stock_code, "无法获取行情数据")
            
            # 获取财务数据
            financial_data = self._get_financial_data(code, periods)
            if financial_data is None:
                return self._create_error_result(stock_code, "无法获取财务数据")
            
            # 获取PE-TTM
            pe_ttm = quote_data.get('pe_ttm', 0)
            if pe_ttm <= 0:
                return self._create_error_result(stock_code, "PE为负或零，不适用PEG估值")
            
            # 计算EPS增长率
            eps_growth_rate = financial_data.get('eps_growth_rate', 0)
            if eps_growth_rate <= 0:
                return self._create_error_result(stock_code, "EPS增长率为负或零，不适用PEG估值")
            
            # 计算PEG
            peg = pe_ttm / eps_growth_rate
            
            # 获取估值状态
            valuation_status = self.get_valuation_signal(peg)
            
            # 计算合理价格（假设PEG=1为合理）
            current_price = quote_data.get('current_price', 0)
            fair_price = current_price * (1 / peg) if peg > 0 else current_price
            
            # 计算上涨空间
            upside_potential = ((fair_price - current_price) / current_price * 100) if current_price > 0 else 0
            
            # 评估置信度
            confidence = self._assess_confidence(financial_data, periods)
            
            return {
                'stock_code': stock_code,
                'stock_name': quote_data.get('stock_name', ''),
                'pe_ttm': round(pe_ttm, 2),
                'eps_growth_rate': round(eps_growth_rate, 2),
                'peg': round(peg, 2),
                'valuation_status': valuation_status,
                'current_price': round(current_price, 2),
                'fair_price': round(fair_price, 2),
                'upside_potential': round(upside_potential, 2),
                'confidence': confidence,
                'details': {
                    'eps_history': financial_data.get('eps_history', []),
                    'growth_years': periods,
                    'calculation_method': 'CAGR' if periods > 1 else 'YoY'
                }
            }
            
        except Exception as e:
            logger.error(f"计算PEG失败: {stock_code},错误: {str(e)}")
            return self._create_error_result(stock_code, str(e))
    
    def compare_industry_peg(self, stock_code: str) -> Dict[str, Any]:
        """
        与行业PEG比较
        
        Args:
            stock_code: 股票代码
            
        Returns:
            {
                'stock_peg': float,       # 个股PEG
                'industry_avg_peg': float, # 行业平均PEG
                'industry_median_peg': float, # 行业中位数PEG
                'percentile': float,      # 在行业中的百分位
                'relative_valuation': str, # 相对估值：低于行业/持平/高于行业
                'industry_name': str,     # 行业名称'peer_comparison': list,  # 同行业公司PEG对比列表
            }
        """
        try:
            # 获取个股PEG
            stock_peg_result = self.calculate_peg(stock_code)
            if 'error' in stock_peg_result:
                return stock_peg_result
            
            stock_peg = stock_peg_result['peg']
            
            # 获取行业信息
            industry_info = self._get_industry_info(stock_code)
            industry_name = industry_info.get('industry_name', '未知行业')
            peer_codes = industry_info.get('peer_codes', [])
            
            # 计算行业内各公司PEG
            peer_pegs = []
            peer_comparison = []
            
            for peer_code in peer_codes[:20]:  # 限制最多20家同行公司
                try:
                    peer_result = self.calculate_peg(peer_code)
                    if 'error' not in peer_result and peer_result['peg'] > 0:
                        peer_pegs.append(peer_result['peg'])
                        peer_comparison.append({
                            'stock_code': peer_code,
                            'stock_name': peer_result['stock_name'],
                            'peg': peer_result['peg'],
                            'pe_ttm': peer_result['pe_ttm'],
                            'eps_growth_rate': peer_result['eps_growth_rate']
                        })
                except Exception:
                    continue
            
            if not peer_pegs:
                # 如果没有同行数据，使用默认行业平均值
                return {
                    'stock_peg': round(stock_peg, 2),
                    'industry_avg_peg':1.0,
                    'industry_median_peg': 1.0,
                    'percentile': 50.0,
                    'relative_valuation': '数据不足',
                    'industry_name': industry_name,
                    'peer_comparison': []
                }
            
            # 计算行业统计数据
            industry_avg_peg = np.mean(peer_pegs)
            industry_median_peg = np.median(peer_pegs)
            
            # 计算百分位
            percentile = (np.sum(np.array(peer_pegs) > stock_peg) / len(peer_pegs)) * 100
            
            # 判断相对估值
            if stock_peg < industry_avg_peg * 0.8:
                relative_valuation = '明显低于行业'
            elif stock_peg < industry_avg_peg:
                relative_valuation = '略低于行业'
            elif stock_peg <= industry_avg_peg * 1.2:
                relative_valuation = '与行业持平'
            else:
                relative_valuation = '高于行业'
            
            # 按PEG排序
            peer_comparison.sort(key=lambda x: x['peg'])
            
            return {
                'stock_peg': round(stock_peg, 2),
                'industry_avg_peg': round(industry_avg_peg, 2),
                'industry_median_peg': round(industry_median_peg, 2),
                'percentile': round(percentile, 1),
                'relative_valuation': relative_valuation,
                'industry_name': industry_name,
                'peer_comparison': peer_comparison[:10]  # 只返回前10家
            }
            
        except Exception as e:
            logger.error(f"行业PEG比较失败: {stock_code}, 错误: {str(e)}")
            return {'error': str(e)}
    
    def peg_ranking(self, stock_list: List[str]) -> pd.DataFrame:
        """
        多股票PEG排名
        
        Args:
            stock_list: 股票代码列表
            
        Returns:
            包含PEG排名的DataFrame，列包括：
            - stock_code: 股票代码
            - stock_name: 股票名称
            - pe_ttm: 滚动市盈率
            - eps_growth_rate: EPS增长率
            - peg: PEG值
            - valuation_status: 估值状态
            - upside_potential: 上涨空间
            - rank: 排名（PEG从低到高）
        """
        results = []
        
        for stock_code in stock_list:
            try:
                peg_result = self.calculate_peg(stock_code)
                if 'error' not in peg_result and peg_result['peg'] > 0:
                    results.append({
                        'stock_code': peg_result['stock_code'],
                        'stock_name': peg_result['stock_name'],
                        'pe_ttm': peg_result['pe_ttm'],
                        'eps_growth_rate': peg_result['eps_growth_rate'],
                        'peg': peg_result['peg'],
                        'valuation_status': peg_result['valuation_status'],
                        'current_price': peg_result['current_price'],
                        'fair_price': peg_result['fair_price'],
                        'upside_potential': peg_result['upside_potential'],
                        'confidence': peg_result['confidence']
                    })
            except Exception as e:
                logger.warning(f"计算{stock_code} PEG失败: {str(e)}")
                continue
        
        if not results:
            return pd.DataFrame()
        
        # 创建DataFrame并排序
        df = pd.DataFrame(results)
        df = df.sort_values('peg', ascending=True)
        df['rank'] = range(1, len(df) + 1)
        
        return df.reset_index(drop=True)
    
    def get_valuation_signal(self, peg: float) -> str:
        """
        获取估值信号
        
        PEG估值标准：
        - PEG < 0.5: 严重低估
        - 0.5 <= PEG < 1: 低估
        - 1 <= PEG < 1.5: 合理
        - 1.5 <= PEG < 2: 偏高
        - PEG >= 2: 高估
        
        Args:
            peg: PEG值
            
        Returns:
            估值状态字符串
        """
        if peg < 0:
            return '不适用'
        elif peg < self.PEG_THRESHOLDS['severely_undervalued']:
            return '严重低估'
        elif peg < self.PEG_THRESHOLDS['undervalued']:
            return '低估'
        elif peg < self.PEG_THRESHOLDS['fairly_valued']:
            return '合理'
        elif peg < self.PEG_THRESHOLDS['overvalued']:
            return '偏高'
        else:
            return '高估'
    
    def screen_undervalued_stocks(self, stock_list: List[str], max_peg: float = 1.0,
                                  min_growth: float = 10.0) -> pd.DataFrame:
        """
        筛选低估成长股
        
        Args:
            stock_list: 股票代码列表
            max_peg: 最大PEG阈值，默认1.0
            min_growth: 最小EPS增长率，默认10%
            
        Returns:
            符合条件的股票DataFrame
        """
        df = self.peg_ranking(stock_list)
        
        if df.empty:
            return df
        
        # 筛选条件
        mask = (df['peg'] <= max_peg) & (df['eps_growth_rate'] >= min_growth)
        
        return df[mask].reset_index(drop=True)
    
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
            #尝试获取A股实时行情
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return None
            
            stock_data = df[df['代码'] == code]
            if stock_data.empty:
                return None
            
            row = stock_data.iloc[0]
            
            # 安全获取数值
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
                'pb': safe_float(row.get('市净率')),
                'market_cap': safe_float(row.get('总市值')),
                'change_percent': safe_float(row.get('涨跌幅'))
            }
            
        except Exception as e:
            logger.error(f"获取行情数据失败: {code}, 错误: {str(e)}")
            return None
    
    def _get_financial_data(self, code: str, periods: int = 3) -> Optional[Dict[str, Any]]:
        """获取财务数据并计算EPS增长率"""
        if not AKSHARE_AVAILABLE:
            return None
        
        try:
            # 获取财务分析指标
            df = ak.stock_financial_analysis_indicator(symbol=code)
            
            if df is None or df.empty:
                return None
            
            # 获取EPS历史数据
            eps_history = []
            if '每股收益' in df.columns:
                eps_values = df['每股收益'].dropna().values
                # 取最近periods+1年的数据（需要计算增长率）
                eps_history = [float(x) for x in eps_values[-(periods+1):] if pd.notna(x)]
            
            if len(eps_history) < 2:
                return None
            
            # 计算EPS增长率（CAGR复合年增长率）
            if len(eps_history) >= periods + 1:
                start_eps = eps_history[0]
                end_eps = eps_history[-1]
                
                if start_eps > 0 and end_eps > 0:
                    # CAGR = (终值/初值)^(1/年数) - 1
                    cagr = ((end_eps / start_eps) ** (1 / periods) - 1) * 100
                    eps_growth_rate = cagr
                else:
                    # 如果有负值，使用简单平均增长率
                    growth_rates = []
                    for i in range(1, len(eps_history)):
                        if eps_history[i-1] != 0:
                            growth = ((eps_history[i] - eps_history[i-1]) / abs(eps_history[i-1])) * 100
                            growth_rates.append(growth)
                    eps_growth_rate = np.mean(growth_rates) if growth_rates else 0
            else:
                # 计算同比增长率
                start_eps = eps_history[0]
                end_eps = eps_history[-1]
                if start_eps != 0:
                    eps_growth_rate = ((end_eps - start_eps) / abs(start_eps)) * 100
                else:
                    eps_growth_rate = 0
            
            # 获取其他财务数据
            latest = df.iloc[-1]
            
            def safe_float(val, default=0.0):
                try:
                    if pd.isna(val):
                        return default
                    return float(val)
                except (ValueError, TypeError):
                    return default
            
            return {
                'eps_growth_rate': eps_growth_rate,
                'eps_history': eps_history,
                'eps_current': safe_float(latest.get('每股收益')),
                'roe': safe_float(latest.get('净资产收益率')),
                'revenue_growth': safe_float(latest.get('营业收入同比增长率')),
                'profit_growth': safe_float(latest.get('净利润同比增长率')),
                'data_quality': 'good' if len(eps_history) >= periods + 1 else 'limited'
            }
            
        except Exception as e:
            logger.error(f"获取财务数据失败: {code}, 错误: {str(e)}")
            return None
    
    def _get_industry_info(self, stock_code: str) -> Dict[str, Any]:
        """获取行业信息和同行公司列表"""
        try:
            code = self._parse_stock_code(stock_code)
            
            # 尝试获取行业分类
            try:
                # 获取申万行业分类
                industry_df = ak.stock_board_industry_name_em()
                if industry_df is not None and not industry_df.empty:
                    # 这里简化处理，返回行业信息
                    return {
                        'industry_name': '行业',
                        'peer_codes': []# 实际应该获取同行业股票
                    }
            except Exception:
                pass
            
            return {
                'industry_name': '未知行业',
                'peer_codes': []
            }
            
        except Exception as e:
            logger.error(f"获取行业信息失败: {stock_code}, 错误: {str(e)}")
            return {
                'industry_name': '未知行业',
                'peer_codes': []
            }
    
    def _assess_confidence(self, financial_data: Dict[str, Any], periods: int) -> str:
        """评估计算结果的置信度"""
        eps_history = financial_data.get('eps_history', [])
        data_quality = financial_data.get('data_quality', 'limited')
        
        # 根据数据完整性评估置信度
        if len(eps_history) >= periods + 1 and data_quality == 'good':
            # 检查EPS稳定性
            eps_std = np.std(eps_history) if eps_history else 0
            eps_mean = np.mean(eps_history) if eps_history else 1
            cv = eps_std / abs(eps_mean) if eps_mean != 0 else float('inf')
            
            if cv < 0.3:
                return '高'
            elif cv < 0.6:
                return '中'
            else:
                return '低'
        elif len(eps_history) >= 2:
            return '中'
        else:
            return '低'
    
    def _create_error_result(self, stock_code: str, error_msg: str) -> Dict[str, Any]:
        """创建错误结果"""
        return {
            'stock_code': stock_code,
            'error': error_msg,
            'pe_ttm': 0,
            'eps_growth_rate': 0,
            'peg': 0,
            'valuation_status': '不适用',
            'current_price': 0,
            'fair_price': 0,
            'upside_potential': 0,
            'confidence': '低'
        }