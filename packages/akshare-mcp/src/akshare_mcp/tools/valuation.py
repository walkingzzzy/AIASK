"""估值工具"""

from typing import Optional, List
from ..storage import get_db
from ..utils import ok, fail
import statistics


def register(mcp):
    """注册估值工具"""
    
    @mcp.tool()
    async def get_valuation_metrics(code: str):
        """
        获取估值指标
        
        Args:
            code: 股票代码
        """
        try:
            db = get_db()
            
            # 从stocks表获取估值指标
            async with db.acquire() as conn:
                row = await conn.fetchrow(
                    """SELECT stock_code, stock_name, pe_ratio, pb_ratio, market_cap
                       FROM stocks
                       WHERE stock_code = $1""",
                    code
                )
                
                if not row:
                    return fail('Stock not found')
                
                return ok({
                    'code': row['stock_code'],
                    'name': row['stock_name'],
                    'pe_ratio': float(row['pe_ratio']) if row['pe_ratio'] else None,
                    'pb_ratio': float(row['pb_ratio']) if row['pb_ratio'] else None,
                    'market_cap': float(row['market_cap']) if row['market_cap'] else None,
                })
        
        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    async def dcf_valuation(
        code: str,
        discount_rate: float = 0.10,
        growth_rate: float = 0.05,
        years: int = 5
    ):
        """
        DCF估值（现金流折现）
        
        Args:
            code: 股票代码
            discount_rate: 折现率
            growth_rate: 增长率
            years: 预测年数
        """
        try:
            db = get_db()
            
            # 使用stock_code字段查询财务数据
            async with db.acquire() as conn:
                row = await conn.fetchrow(
                    """SELECT net_profit FROM financials
                       WHERE stock_code = $1
                       ORDER BY report_date DESC
                       LIMIT 1""",
                    code
                )
                
                if not row or not row['net_profit']:
                    return fail('No financial data or invalid net profit')
                
                net_profit = float(row['net_profit'])
                
                if net_profit <= 0:
                    return fail('Invalid net profit (must be positive)')
            
            # 简化DCF计算
            fcf = net_profit * 0.8  # 假设自由现金流为净利润的80%
            
            pv_sum = 0
            for year in range(1, years + 1):
                future_fcf = fcf * ((1 + growth_rate) ** year)
                pv = future_fcf / ((1 + discount_rate) ** year)
                pv_sum += pv
            
            # 终值
            terminal_fcf = fcf * ((1 + growth_rate) ** years) * (1 + growth_rate)
            terminal_value = terminal_fcf / (discount_rate - growth_rate)
            pv_terminal = terminal_value / ((1 + discount_rate) ** years)
            
            intrinsic_value = pv_sum + pv_terminal
            
            return ok({
                'code': code,
                'intrinsic_value': float(intrinsic_value),
                'discount_rate': discount_rate,
                'growth_rate': growth_rate,
                'years': years,
            })
        
        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    async def ddm_valuation(
        code: str,
        dividend: Optional[float] = None,
        growth_rate: float = 0.05,
        required_return: float = 0.10
    ):
        """
        DDM估值（股息折现模型）
        
        Args:
            code: 股票代码
            dividend: 每股股息（不填则从数据估算）
            growth_rate: 股息增长率
            required_return: 要求回报率
        """
        try:
            if growth_rate >= required_return:
                return fail('增长率必须小于要求回报率')
            
            db = get_db()
            
            # 获取股息数据（如果没有提供）
            if not dividend:
                # 尝试从财务数据估算股息
                async with db.acquire() as conn:
                    row = await conn.fetchrow(
                        """SELECT eps FROM financials
                           WHERE stock_code = $1
                           ORDER BY report_date DESC
                           LIMIT 1""",
                        code
                    )
                    
                    if row and row['eps']:
                        # 假设分红率为30%
                        dividend = float(row['eps']) * 0.3
            
            if not dividend or dividend <= 0:
                return fail(f'股票 {code} 无股息数据，DDM模型不适用')
            
            # Gordon Growth Model: P = D1 / (r - g)
            next_dividend = dividend * (1 + growth_rate)
            intrinsic_value = next_dividend / (required_return - growth_rate)
            
            return ok({
                'code': code,
                'model': 'Gordon Growth Model (DDM)',
                'intrinsic_value': float(intrinsic_value),
                'current_dividend': dividend,
                'next_dividend': float(next_dividend),
                'growth_rate': growth_rate,
                'required_return': required_return,
            })
        
        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    async def relative_valuation(
        code: str,
        metrics: Optional[List[str]] = None,
        peers: Optional[List[str]] = None
    ):
        """
        相对估值分析
        
        Args:
            code: 目标股票代码
            metrics: 估值指标列表，如['pe_ratio', 'pb_ratio', 'ps_ratio']
            peers: 可比公司列表（不填则自动查找同行业公司）
        """
        try:
            db = get_db()
            
            # 默认估值指标
            if not metrics:
                metrics = ['pe_ratio', 'pb_ratio']
            
            # 获取目标股票信息
            target_info = await db.get_stock_info(code)
            if not target_info:
                return fail(f'Stock {code} not found')
            
            target_industry = target_info.get('industry', '')
            
            # 获取目标股票估值指标
            target_metrics = {}
            for metric in metrics:
                value = target_info.get(metric)
                if value and value > 0:
                    target_metrics[metric] = float(value)
            
            if not target_metrics:
                return fail(f'No valid valuation metrics for {code}')
            
            # 查找可比公司
            if not peers:
                # 自动查找同行业公司
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        """SELECT stock_code FROM stocks 
                           WHERE industry = $1 AND stock_code != $2 
                           LIMIT 20""",
                        target_industry, code
                    )
                    peers = [row['stock_code'] for row in rows]
            
            if not peers:
                return fail(f'No peer companies found for industry: {target_industry}')
            
            # 获取可比公司估值指标
            peer_data = []
            for peer_code in peers:
                peer_info = await db.get_stock_info(peer_code)
                if not peer_info:
                    continue
                
                peer_metrics = {'code': peer_code, 'name': peer_info.get('name', '')}
                valid = False
                for metric in metrics:
                    value = peer_info.get(metric)
                    if value and value > 0:
                        peer_metrics[metric] = float(value)
                        valid = True
                
                if valid:
                    peer_data.append(peer_metrics)
            
            if not peer_data:
                return fail('No valid peer data found')
            
            # 计算行业统计
            industry_stats = {}
            for metric in metrics:
                values = [p[metric] for p in peer_data if metric in p]
                if values:
                    industry_stats[metric] = {
                        'mean': float(statistics.mean(values)),
                        'median': float(statistics.median(values)),
                        'min': float(min(values)),
                        'max': float(max(values)),
                        'count': len(values)
                    }
            
            # 计算相对估值
            comparison = {}
            for metric in target_metrics:
                if metric in industry_stats:
                    target_value = target_metrics[metric]
                    industry_mean = industry_stats[metric]['mean']
                    industry_median = industry_stats[metric]['median']
                    
                    comparison[metric] = {
                        'target': target_value,
                        'industry_mean': industry_mean,
                        'industry_median': industry_median,
                        'premium_to_mean': float((target_value - industry_mean) / industry_mean * 100),
                        'premium_to_median': float((target_value - industry_median) / industry_median * 100),
                        'percentile': float(sum(1 for p in peer_data if p.get(metric, float('inf')) < target_value) / len(peer_data) * 100)
                    }
            
            return ok({
                'code': code,
                'name': target_info.get('name', ''),
                'industry': target_industry,
                'target_metrics': target_metrics,
                'industry_stats': industry_stats,
                'comparison': comparison,
                'peer_count': len(peer_data),
                'peers': peer_data[:10]  # 只返回前10个可比公司
            })
        
        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    async def get_historical_valuation(
        code: str,
        days: int = 30
    ):
        """
        获取历史估值数据
        
        Args:
            code: 股票代码
            days: 查询天数
        """
        try:
            db = get_db()
            
            async with db.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT time, pe, pb, mkt_cap, price
                       FROM stock_quotes
                       WHERE code = $1 
                       AND time >= NOW() - INTERVAL '1 day' * $2
                       ORDER BY time DESC""",
                    code, days
                )
                
                if not rows:
                    return fail(f'No historical valuation data for {code}')
                
                history = []
                for row in rows:
                    history.append({
                        'date': row['time'].strftime('%Y-%m-%d') if row['time'] else None,
                        'pe_ratio': float(row['pe']) if row['pe'] else None,
                        'pb_ratio': float(row['pb']) if row['pb'] else None,
                        'market_cap': float(row['mkt_cap']) if row['mkt_cap'] else None,
                        'price': float(row['price']) if row['price'] else None
                    })
                
                # 计算统计信息
                pe_values = [h['pe_ratio'] for h in history if h['pe_ratio']]
                pb_values = [h['pb_ratio'] for h in history if h['pb_ratio']]
                
                stats = {}
                if pe_values:
                    stats['pe'] = {
                        'current': pe_values[0],
                        'mean': float(statistics.mean(pe_values)),
                        'median': float(statistics.median(pe_values)),
                        'min': float(min(pe_values)),
                        'max': float(max(pe_values))
                    }
                
                if pb_values:
                    stats['pb'] = {
                        'current': pb_values[0],
                        'mean': float(statistics.mean(pb_values)),
                        'median': float(statistics.median(pb_values)),
                        'min': float(min(pb_values)),
                        'max': float(max(pb_values))
                    }
                
                return ok({
                    'code': code,
                    'days': days,
                    'history': history,
                    'stats': stats,
                    'count': len(history)
                })
        
        except Exception as e:
            return fail(str(e))
