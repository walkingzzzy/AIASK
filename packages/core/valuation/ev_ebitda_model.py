"""
企业价值倍数估值模型 (EV/EBITDA)

EV/EBITDA是一种企业价值倍数估值指标，常用于评估资本密集型行业的公司价值。

核心公式：
- EV (Enterprise Value) = 市值 + 总债务 - 现金及现金等价物
- EBITDA = 营业利润 + 折旧 + 摊销
- EV/EBITDA倍数 = EV / EBITDA

EV/EBITDA估值标准（因行业而异）：
- EV/EBITDA < 6: 可能被低估
- 6 <= EV/EBITDA < 10: 合理估值区间
- 10 <= EV/EBITDA < 15: 估值偏高
- EV/EBITDA >= 15: 高估

优点：
- 剔除了资本结构（负债/权益比例）的影响
- 消除了折旧和摊销政策差异的影响
- 适合跨国公司比较（排除税收差异）
- 适用于并购估值

适用行业：
- 资本密集型行业：电信、公用事业、制造业
- 周期性行业
- 高负债行业
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging
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
class EVEBITDAResult:
    """EV/EBITDA估值结果"""
    stock_code: str
    stock_name: str
    enterprise_value: float
    ebitda: float
    ev_ebitda: float
    market_cap: float
    total_debt: float
    cash: float
    valuation_status: str
    industry_avg_ev_ebitda: float
    margin_of_safety: float
    recommendation: str


class EVEBITDAValuation:
    """
    企业价值倍数估值模型
    
    EV/EBITDA是一种常用的企业价值倍数指标，特别适用于：
    - 资本密集型行业（电信、公用事业、能源等）
    - 高负债公司的估值
    - 并购交易的估值
    -跨国公司比较（排除税收差异）
    
    公式：
    - EV = 市值 + 总债务 - 现金及现金等价物
    - EBITDA = 营业利润 + 折旧 + 摊销（或：净利润 + 利息+ 税费 + 折旧 + 摊销）
    - EV/EBITDA = EV / EBITDA
    """
    
    # 行业EV/EBITDA参考值
    INDUSTRY_EV_EBITDA = {
        '银行': 8.0,
        '保险': 7.0,
        '证券': 10.0,
        '房地产': 12.0,
        '能源': 6.0,
        '电力': 7.0,
        '公用事业': 8.0,
        '电信': 6.5,
        '制造业': 8.0,
        '医药': 12.0,
        '消费': 10.0,
        '科技': 15.0,
        '零售': 8.0,
        '交通运输': 7.0,
        '材料': 6.0,
        '默认': 10.0
    }
    
    # EV/EBITDA估值阈值
    EV_EBITDA_THRESHOLDS = {
        'undervalued': 6.0,
        'fairly_valued_low': 10.0,
        'fairly_valued_high': 15.0,
        'overvalued': 15.0
    }
    
    def __init__(self, cache_enabled: bool = True):
        """
        初始化EV/EBITDA估值模型
        
        Args:
            cache_enabled: 是否启用缓存
        """
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, Any] = {}
        if not AKSHARE_AVAILABLE:
            logger.warning("akshare库未安装，部分功能可能不可用")
    
    def calculate_ev(self, stock_code: str) -> Dict[str, Any]:
        """
        计算企业价值(Enterprise Value)
        
        EV = 市值 + 总债务 - 现金及现金等价物
        
        其中：
        - 市值 = 股价 × 总股本
        - 总债务 = 短期借款 + 长期借款 + 应付债券 + 其他有息负债
        - 现金 = 货币资金 + 交易性金融资产
        
        Args:
            stock_code: 股票代码，如600519.SH或 000001.SZ
            
        Returns:
            {
                'stock_code': str,# 股票代码
                'stock_name': str,          # 股票名称
                'market_cap': float,        # 市值（亿元）
                'total_debt': float,        # 总债务（亿元）
                'cash': float,              # 现金及等价物（亿元）
                'enterprise_value': float,  # 企业价值（亿元）
                'ev_breakdown': dict,       # EV分解详情
            }
        """
        try:
            code = self._parse_stock_code(stock_code)
            
            # 获取市值数据
            quote_data = self._get_quote_data(code)
            if quote_data is None:
                return self._create_error_result(stock_code, "无法获取行情数据")
            
            market_cap = quote_data.get('market_cap', 0) / 100000000  # 转为亿元
            stock_name = quote_data.get('stock_name', '')
            # 获取资产负债表数据
            balance_data = self._get_balance_sheet_data(code)
            if balance_data is None:
                return self._create_error_result(stock_code, "无法获取资产负债表数据")
            
            # 计算总债务
            short_term_debt = balance_data.get('short_term_debt', 0) / 100000000
            long_term_debt = balance_data.get('long_term_debt', 0) / 100000000
            bonds_payable = balance_data.get('bonds_payable', 0) / 100000000
            other_debt = balance_data.get('other_interest_bearing_debt', 0) / 100000000
            total_debt = short_term_debt + long_term_debt + bonds_payable + other_debt
            
            # 计算现金及等价物
            cash = balance_data.get('cash', 0) / 100000000
            tradable_financial_assets = balance_data.get('tradable_financial_assets', 0) / 100000000
            total_cash = cash + tradable_financial_assets
            
            # 计算企业价值
            enterprise_value = market_cap + total_debt - total_cash
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'market_cap': round(market_cap, 2),
                'total_debt': round(total_debt, 2),
                'cash': round(total_cash, 2),
                'enterprise_value': round(enterprise_value, 2),
                'ev_breakdown': {
                    'short_term_debt': round(short_term_debt, 2),
                    'long_term_debt': round(long_term_debt, 2),
                    'bonds_payable': round(bonds_payable, 2),
                    'other_debt': round(other_debt, 2),
                    'cash_and_equivalents': round(cash, 2),
                    'tradable_financial_assets': round(tradable_financial_assets, 2)
                }
            }
            
        except Exception as e:
            logger.error(f"计算EV失败: {stock_code},错误: {str(e)}")
            return self._create_error_result(stock_code, str(e))
    
    def calculate_ebitda(self, stock_code: str) -> Dict[str, Any]:
        """
        计算EBITDA
        EBITDA = 营业利润 + 折旧 + 摊销
        或者
        EBITDA = 净利润 + 利息费用 + 所得税 + 折旧 + 摊销
        
        Args:
            stock_code: 股票代码
            
        Returns:
            {
                'stock_code': str,          # 股票代码
                'stock_name': str,          # 股票名称
                'ebitda': float,            # EBITDA（亿元）
                'operating_profit': float,  # 营业利润（亿元）
                'depreciation': float,      # 折旧（亿元）
                'amortization': float,      # 摊销（亿元）
                'ebitda_margin': float,     # EBITDA利润率（%）
                'components': dict,         # EBITDA组成
            }
        """
        try:
            code = self._parse_stock_code(stock_code)
            
            # 获取股票名称
            quote_data = self._get_quote_data(code)
            stock_name = quote_data.get('stock_name', '') if quote_data else ''
            
            # 获取利润表数据
            income_data = self._get_income_statement_data(code)
            if income_data is None:
                return self._create_error_result(stock_code, "无法获取利润表数据")
            
            # 获取现金流量表数据（用于获取折旧和摊销）
            cash_flow_data = self._get_cash_flow_data(code)
            
            # 营业利润
            operating_profit = income_data.get('operating_profit', 0) / 100000000
            
            # 营业收入（用于计算EBITDA margin）
            revenue = income_data.get('revenue', 0) / 100000000
            
            # 折旧和摊销（从现金流量表获取）
            if cash_flow_data:
                depreciation = cash_flow_data.get('depreciation', 0) / 100000000
                amortization = cash_flow_data.get('amortization', 0) / 100000000
            else:
                # 如果无法获取现金流量表数据，估算折旧和摊销
                depreciation = operating_profit * 0.1  # 估算为营业利润的10%
                amortization = operating_profit * 0.02  # 估算为营业利润的2%
            
            # 计算EBITDA
            ebitda = operating_profit + depreciation + amortization
            
            # 计算EBITDA利润率
            ebitda_margin = (ebitda / revenue * 100) if revenue > 0 else 0
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'ebitda': round(ebitda, 2),
                'operating_profit': round(operating_profit, 2),
                'depreciation': round(depreciation, 2),
                'amortization': round(amortization, 2),
                'revenue': round(revenue, 2),
                'ebitda_margin': round(ebitda_margin, 2),
                'components': {
                    'operating_profit': round(operating_profit, 2),
                    'depreciation': round(depreciation, 2),
                    'amortization': round(amortization, 2)
                }
            }
            
        except Exception as e:
            logger.error(f"计算EBITDA失败: {stock_code}, 错误: {str(e)}")
            return self._create_error_result(stock_code, str(e))
    
    def calculate_ev_ebitda(self, stock_code: str) -> Dict[str, Any]:
        """
        计算EV/EBITDA倍数
        
        Args:
            stock_code: 股票代码
            
        Returns:
            {
                'stock_code': str,# 股票代码
                'stock_name': str,              # 股票名称
                'enterprise_value': float,# 企业价值（亿元）
                'ebitda': float,                # EBITDA（亿元）
                'ev_ebitda': float,             # EV/EBITDA倍数
                'market_cap': float,            # 市值（亿元）
                'total_debt': float,            # 总债务（亿元）
                'cash': float,                  # 现金（亿元）
                'valuation_status': str,        # 估值状态
                'current_price': float,         # 当前价格
                'implied_price': float,         # 隐含价格（基于行业平均）
                'upside_potential': float,      # 上涨空间（%）
                'industry_avg_ev_ebitda': float,# 行业平均EV/EBITDA
                'margin_of_safety': float,      # 安全边际（%）
                'recommendation': str,          # 投资建议
            }
        """
        try:
            code = self._parse_stock_code(stock_code)
            
            # 计算EV
            ev_result = self.calculate_ev(stock_code)
            if'error' in ev_result:
                return ev_result
            
            # 计算EBITDA
            ebitda_result = self.calculate_ebitda(stock_code)
            if 'error' in ebitda_result:
                return ebitda_result
            
            enterprise_value = ev_result['enterprise_value']
            ebitda = ebitda_result['ebitda']
            stock_name = ev_result['stock_name']
            
            # 验证EBITDA
            if ebitda <= 0:
                return self._create_error_result(
                    stock_code, 
                    "EBITDA为负或零，不适用EV/EBITDA估值"
                )
            
            # 计算EV/EBITDA
            ev_ebitda = enterprise_value / ebitda
            
            # 获取行业平均EV/EBITDA
            industry_info = self._get_industry_info(stock_code)
            industry_name = industry_info.get('industry_name', '默认')
            industry_avg_ev_ebitda = self.INDUSTRY_EV_EBITDA.get(
                industry_name, 
                self.INDUSTRY_EV_EBITDA['默认']
            )
            
            # 获取估值状态
            valuation_status = self._get_valuation_status(ev_ebitda, industry_avg_ev_ebitda)
            
            # 计算隐含价格
            quote_data = self._get_quote_data(code)
            current_price = quote_data.get('current_price', 0) if quote_data else 0
            market_cap = ev_result['market_cap']
            total_debt = ev_result['total_debt']
            cash = ev_result['cash']
            
            # 基于行业平均EV/EBITDA计算合理EV
            fair_ev = ebitda * industry_avg_ev_ebitda
            fair_market_cap = fair_ev - total_debt + cash
            
            # 计算隐含价格
            if market_cap > 0 and current_price > 0:
                implied_price = current_price * (fair_market_cap / market_cap)
            else:
                implied_price = 0
            
            # 计算上涨空间
            upside_potential = ((implied_price - current_price) / current_price * 100) if current_price > 0 else 0
            
            # 计算安全边际
            margin_of_safety = ((fair_ev - enterprise_value) / enterprise_value * 100) if enterprise_value > 0 else 0
            
            # 生成投资建议
            recommendation = self._generate_recommendation(ev_ebitda, industry_avg_ev_ebitda, margin_of_safety)
            
            return {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'enterprise_value': round(enterprise_value, 2),
                'ebitda': round(ebitda, 2),
                'ev_ebitda': round(ev_ebitda, 2),
                'market_cap': round(market_cap, 2),
                'total_debt': round(total_debt, 2),
                'cash': round(cash, 2),
                'valuation_status': valuation_status,
                'current_price': round(current_price, 2),
                'implied_price': round(implied_price, 2),
                'upside_potential': round(upside_potential, 2),
                'industry_name': industry_name,
                'industry_avg_ev_ebitda': round(industry_avg_ev_ebitda, 2),
                'margin_of_safety': round(margin_of_safety, 2),
                'recommendation': recommendation,'ebitda_margin': ebitda_result.get('ebitda_margin', 0),
                'ev_breakdown': ev_result.get('ev_breakdown', {}),
                'ebitda_components': ebitda_result.get('components', {})
            }
            
        except Exception as e:
            logger.error(f"计算EV/EBITDA失败: {stock_code}, 错误: {str(e)}")
            return self._create_error_result(stock_code, str(e))
    
    def industry_comparison(self, stock_code: str) -> pd.DataFrame:
        """
        与行业内公司比较
        
        Args:
            stock_code: 股票代码
            
        Returns:
            行业内公司EV/EBITDA比较的DataFrame
        """
        try:
            # 获取个股EV/EBITDA
            stock_result = self.calculate_ev_ebitda(stock_code)
            if 'error' in stock_result:
                return pd.DataFrame()
            
            # 获取行业内公司列表
            industry_info = self._get_industry_info(stock_code)
            peer_codes = industry_info.get('peer_codes', [])
            
            results = [{
                'stock_code': stock_code,
                'stock_name': stock_result['stock_name'],
                'ev_ebitda': stock_result['ev_ebitda'],
                'enterprise_value': stock_result['enterprise_value'],
                'ebitda': stock_result['ebitda'],
                'ebitda_margin': stock_result.get('ebitda_margin', 0),
                'market_cap': stock_result['market_cap'],
                'valuation_status': stock_result['valuation_status'],
                'is_target': True
            }]
            
            # 计算同行公司的EV/EBITDA
            for peer_code in peer_codes[:15]:  # 限制最多15家公司
                try:
                    peer_result = self.calculate_ev_ebitda(peer_code)
                    if 'error' not in peer_result and peer_result['ev_ebitda'] > 0:
                        results.append({
                            'stock_code': peer_code,
                            'stock_name': peer_result['stock_name'],
                            'ev_ebitda': peer_result['ev_ebitda'],
                            'enterprise_value': peer_result['enterprise_value'],
                            'ebitda': peer_result['ebitda'],
                            'ebitda_margin': peer_result.get('ebitda_margin', 0),
                            'market_cap': peer_result['market_cap'],
                            'valuation_status': peer_result['valuation_status'],
                            'is_target': False
                        })
                except Exception:
                    continue
            
            if not results:
                return pd.DataFrame()
            
            # 创建DataFrame并排序
            df = pd.DataFrame(results)
            df = df.sort_values('ev_ebitda', ascending=True)
            df['rank'] = range(1, len(df) + 1)
            
            # 计算行业统计
            peer_ev_ebitda = df[~df['is_target']]['ev_ebitda'].tolist()
            if peer_ev_ebitda:
                df.attrs['industry_avg'] = np.mean(peer_ev_ebitda)
                df.attrs['industry_median'] = np.median(peer_ev_ebitda)
                df.attrs['percentile'] = (np.sum(np.array(peer_ev_ebitda) > stock_result['ev_ebitda']) / len(peer_ev_ebitda)) * 100
            
            return df.reset_index(drop=True)
            
        except Exception as e:
            logger.error(f"行业比较失败: {stock_code}, 错误: {str(e)}")
            return pd.DataFrame()
    
    def historical_ev_ebitda(self, stock_code: str, years: int = 5) -> pd.DataFrame:
        """
        历史EV/EBITDA趋势
        
        Args:
            stock_code: 股票代码
            years: 历史年数，默认5年
            
        Returns:
            历史EV/EBITDA数据的DataFrame
        """
        try:
            code = self._parse_stock_code(stock_code)
            
            # 获取历史财务数据
            historical_data = self._get_historical_financial_data(code, years)
            if not historical_data:
                return pd.DataFrame()
            
            results = []
            for data in historical_data:
                year = data.get('year')
                ev = data.get('enterprise_value', 0)
                ebitda = data.get('ebitda', 0)
                
                if ebitda > 0:
                    ev_ebitda = ev / ebitda
                else:
                    ev_ebitda = None
                
                results.append({
                    'year': year,
                    'enterprise_value': round(ev, 2),
                    'ebitda': round(ebitda, 2),
                    'ev_ebitda': round(ev_ebitda, 2) if ev_ebitda else None,
                    'market_cap': round(data.get('market_cap', 0), 2),
                    'total_debt': round(data.get('total_debt', 0), 2),
                    'cash': round(data.get('cash', 0), 2),
                    'ebitda_margin': round(data.get('ebitda_margin', 0), 2)
                })
            
            if not results:
                return pd.DataFrame()
            
            df = pd.DataFrame(results)
            df = df.sort_values('year', ascending=True)
            
            # 计算统计指标
            ev_ebitda_values = df['ev_ebitda'].dropna().tolist()
            if ev_ebitda_values:
                df.attrs['avg_ev_ebitda'] = np.mean(ev_ebitda_values)
                df.attrs['min_ev_ebitda'] = np.min(ev_ebitda_values)
                df.attrs['max_ev_ebitda'] = np.max(ev_ebitda_values)
                df.attrs['std_ev_ebitda'] = np.std(ev_ebitda_values)
            
            return df.reset_index(drop=True)
            
        except Exception as e:
            logger.error(f"获取历史EV/EBITDA失败: {stock_code}, 错误: {str(e)}")
            return pd.DataFrame()
    
    def ev_ebitda_ranking(self, stock_list: List[str]) -> pd.DataFrame:
        """
        多股票EV/EBITDA排名
        
        Args:
            stock_list: 股票代码列表
            
        Returns:
            包含EV/EBITDA排名的DataFrame
        """
        results = []
        
        for stock_code in stock_list:
            try:
                result = self.calculate_ev_ebitda(stock_code)
                if 'error' not in result and result['ev_ebitda'] > 0:
                    results.append({
                        'stock_code': result['stock_code'],
                        'stock_name': result['stock_name'],
                        'ev_ebitda': result['ev_ebitda'],
                        'enterprise_value': result['enterprise_value'],
                        'ebitda': result['ebitda'],
                        'ebitda_margin': result.get('ebitda_margin', 0),
                        'market_cap': result['market_cap'],
                        'valuation_status': result['valuation_status'],
                        'upside_potential': result['upside_potential'],
                        'recommendation': result['recommendation']
                    })
            except Exception as e:
                logger.warning(f"计算{stock_code} EV/EBITDA失败: {str(e)}")
                continue
        
        if not results:
            return pd.DataFrame()
        
        # 创建DataFrame并排序
        df = pd.DataFrame(results)
        df = df.sort_values('ev_ebitda', ascending=True)
        df['rank'] = range(1, len(df) + 1)
        
        return df.reset_index(drop=True)
    
    def screen_undervalued_stocks(self, stock_list: List[str],max_ev_ebitda: float = 10.0,
                                   min_ebitda_margin: float = 10.0) -> pd.DataFrame:
        """
        筛选低估值股票
        
        Args:
            stock_list: 股票代码列表
            max_ev_ebitda: 最大EV/EBITDA阈值，默认10.0
            min_ebitda_margin: 最小EBITDA利润率，默认10%
            
        Returns:
            符合条件的股票DataFrame
        """
        df = self.ev_ebitda_ranking(stock_list)
        
        if df.empty:
            return df
        
        #筛选条件
        mask = (df['ev_ebitda'] <= max_ev_ebitda) & (df['ebitda_margin'] >= min_ebitda_margin)
        
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
                'market_cap': safe_float(row.get('总市值')),
                'pe_ttm': safe_float(row.get('市盈率-动态')),
                'pb': safe_float(row.get('市净率'))
            }
            
        except Exception as e:
            logger.error(f"获取行情数据失败: {code}, 错误: {str(e)}")
            return None
    
    def _get_balance_sheet_data(self, code: str) -> Optional[Dict[str, Any]]:
        """获取资产负债表数据"""
        if not AKSHARE_AVAILABLE:
            return None
        
        try:
            #尝试获取资产负债表
            df = ak.stock_balance_sheet_by_report_em(symbol=code)
            if df is None or df.empty:
                return None
            
            # 获取最新一期数据
            latest = df.iloc[0] if len(df) > 0 else df.iloc[-1]
            
            def safe_float(val, default=0.0):
                try:
                

                    if pd.isna(val):
                        return default
                    return float(val)
                except (ValueError, TypeError):
                    return default
            
            # 获取负债数据
            total_debt = 0
            for col in ['短期借款', '长期借款', '应付债券', '一年内到期的非流动负债']:
                if col in latest.index and pd.notna(latest[col]):
                    total_debt += safe_float(latest[col])
            
            # 获取现金数据
            cash = 0
            for col in ['货币资金', '交易性金融资产']:
                if col in latest.index and pd.notna(latest[col]):
                    cash += safe_float(latest[col])
            
            return {
                'total_debt': total_debt,
                'cash': cash,
                'total_assets': safe_float(latest.get('资产总计', 0)),
                'total_liabilities': safe_float(latest.get('负债合计', 0))
            }
            
        except Exception as e:
            logger.error(f"获取资产负债表数据失败: {code}, 错误: {str(e)}")
            return None
    
    def _get_income_statement_data(self, code: str) -> Optional[Dict[str, Any]]:
        """获取利润表数据"""
        if not AKSHARE_AVAILABLE:
            return None
        
        try:
            df = ak.stock_profit_sheet_by_report_em(symbol=code)
            if df is None or df.empty:
                return None
            
            latest = df.iloc[0] if len(df) > 0 else df.iloc[-1]
            
            def safe_float(val, default=0.0):
                try:
                    if pd.isna(val):
                        return default
                    return float(val)
                except (ValueError, TypeError):
                    return default
            
            return {
                'revenue': safe_float(latest.get('营业总收入', 0)),
                'operating_profit': safe_float(latest.get('营业利润', 0)),
                'net_profit': safe_float(latest.get('净利润', 0)),
                'depreciation': safe_float(latest.get('资产减值损失', 0))
            }
            
        except Exception as e:
            logger.error(f"获取利润表数据失败: {code}, 错误: {str(e)}")
            return None
    
    def _get_industry_info(self, stock_code: str) -> Dict[str, Any]:
        """获取行业信息"""
        return {
            'industry_name': '未知行业',
            'industry_avg_ev_ebitda': 10.0,
            'peer_codes': []
        }
    
    def _get_historical_financial_data(self, code: str, years: int) -> List[Dict[str, Any]]:
        """获取历史财务数据"""
        return []
    
    def _generate_recommendation(self, ev_ebitda: float, industry_avg: float, margin_of_safety: float) -> str:
        """生成投资建议"""
        if ev_ebitda < industry_avg * 0.7 and margin_of_safety > 20:
            return '强烈买入'
        elif ev_ebitda < industry_avg * 0.85 and margin_of_safety > 10:
            return '买入'
        elif ev_ebitda < industry_avg * 1.15:
            return '持有'
        elif ev_ebitda < industry_avg * 1.3:
            return '观望'
        else:
            return '卖出'
    
    def _create_error_result(self, stock_code: str, error_msg: str) -> Dict[str, Any]:
        """创建错误结果"""
        return {
            'stock_code': stock_code,
            'error': error_msg,
            'enterprise_value': 0,
            'ebitda': 0,
            'ev_ebitda': 0,
            'market_cap': 0,
            'total_debt': 0,
            'cash': 0,
            'valuation_status': '计算失败',
            'current_price': 0,
            'implied_price': 0,
            'upside_potential': 0,
            'industry_name': '',
            'industry_avg_ev_ebitda': 0,
            'margin_of_safety': 0,
            'recommendation': '无法评估'
        }
