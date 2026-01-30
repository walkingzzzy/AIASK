"""量化因子工具"""
import numpy as np
from scipy import stats
from typing import List, Dict, Any
from ..services.factor_calculator import factor_calculator
from ..storage import get_db
from ..utils import ok, fail

def register(mcp):
    @mcp.tool()
    def get_factor_library(category: str = 'all'):
        factors = [
            {'name': 'momentum', 'category': 'technical', 'description': '动量因子'},
            {'name': 'value', 'category': 'fundamental', 'description': '价值因子'},
            {'name': 'quality', 'category': 'fundamental', 'description': '质量因子'},
            {'name': 'volatility', 'category': 'risk', 'description': '波动率因子'},
        ]
        return ok({'factors': factors})
    
    @mcp.tool()
    async def calculate_factor(code: str, factor: str):
        try:
            db = get_db()
            klines = await db.get_klines(code, limit=100)
            
            if not klines:
                return fail('No data')
            
            closes = [k['close'] for k in klines]
            
            if factor == 'momentum':
                value = factor_calculator.calculate_momentum(closes)
            elif factor == 'volatility':
                value = factor_calculator.calculate_volatility(closes)
            else:
                value = 0.0
            
            return ok({'code': code, 'factor': factor, 'value': float(value)})
        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    async def calculate_factor_ic(codes: list, factor: str, period: int = 20):
        """
        计算因子IC值（信息系数）
        IC = Spearman相关系数(因子值, 未来收益)
        """
        try:
            db = get_db()
            factor_values = []
            future_returns = []
            
            for code in codes:
                # 获取K线数据
                klines = await db.get_klines(code, limit=period + 30)
                if not klines or len(klines) < period + 5:
                    continue
                
                closes = [k['close'] for k in klines]
                
                # 计算因子值
                if factor == 'momentum':
                    factor_value = factor_calculator.calculate_momentum(closes[:period])
                elif factor == 'volatility':
                    factor_value = factor_calculator.calculate_volatility(closes[:period])
                else:
                    continue
                
                # 计算未来收益率
                current_price = closes[period - 1]
                future_price = closes[min(period + period - 1, len(closes) - 1)]
                future_return = (future_price - current_price) / current_price
                
                factor_values.append(factor_value)
                future_returns.append(future_return)
            
            if len(factor_values) < 10:
                return fail('Not enough valid data for IC calculation')
            
            # 计算Spearman相关系数
            ic, p_value = stats.spearmanr(factor_values, future_returns)
            
            return ok({
                'factor': factor,
                'ic': float(ic),
                'p_value': float(p_value),
                'significant': p_value < 0.05,
                'sample_size': len(factor_values),
                'period': period
            })
            
        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    async def backtest_factor(codes: list, factor: str, groups: int = 5, holding_days: int = 20):
        """
        因子分组回测
        将股票按因子值分组，计算各组收益
        """
        try:
            db = get_db()
            stock_data = []
            
            # 1. 计算所有股票的因子值
            for code in codes:
                klines = await db.get_klines(code, limit=holding_days + 30)
                if not klines or len(klines) < holding_days + 5:
                    continue
                
                closes = [k['close'] for k in klines]
                
                # 计算因子值
                if factor == 'momentum':
                    factor_value = factor_calculator.calculate_momentum(closes[:20])
                elif factor == 'volatility':
                    factor_value = factor_calculator.calculate_volatility(closes[:20])
                else:
                    continue
                
                # 计算持有期收益
                entry_price = closes[19]
                exit_price = closes[min(19 + holding_days, len(closes) - 1)]
                holding_return = (exit_price - entry_price) / entry_price
                
                stock_data.append({
                    'code': code,
                    'factor_value': factor_value,
                    'return': holding_return
                })
            
            if len(stock_data) < groups * 2:
                return fail('Not enough stocks for grouping')
            
            # 2. 按因子值排序并分组
            stock_data.sort(key=lambda x: x['factor_value'])
            group_size = len(stock_data) // groups
            
            group_returns = []
            for i in range(groups):
                start_idx = i * group_size
                end_idx = start_idx + group_size if i < groups - 1 else len(stock_data)
                group_stocks = stock_data[start_idx:end_idx]
                
                # 计算组内平均收益
                avg_return = np.mean([s['return'] for s in group_stocks])
                group_returns.append({
                    'group': i + 1,
                    'avg_return': float(avg_return),
                    'stock_count': len(group_stocks)
                })
            
            # 3. 计算多空收益（最高组 - 最低组）
            long_short_return = group_returns[-1]['avg_return'] - group_returns[0]['avg_return']
            
            return ok({
                'factor': factor,
                'groups': groups,
                'holding_days': holding_days,
                'group_returns': group_returns,
                'long_short_return': float(long_short_return),
                'total_stocks': len(stock_data)
            })
            
        except Exception as e:
            return fail(str(e))
