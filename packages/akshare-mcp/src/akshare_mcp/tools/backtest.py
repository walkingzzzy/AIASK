"""回测工具"""

from typing import Optional, Dict, Any, List
from ..services import backtest_engine
from ..storage import get_db
from ..utils import ok, fail, normalize_code, parse_date_input
from .market import get_kline_data

# 检查Ray是否可用
RAY_AVAILABLE = False
try:
    from ..services.backtest import ParallelBacktestEngine
    RAY_AVAILABLE = True
except ImportError:
    pass


def register(mcp):
    """注册回测工具"""

    def _normalize_dates(
        start_date: Optional[str], end_date: Optional[str]
    ) -> tuple[Optional[str], Optional[str]]:
        sd = start_date
        ed = end_date
        if sd and len(sd) == 4:
            sd = f"{sd}-01-01"
        if ed and len(ed) == 4:
            ed = f"{ed}-12-31"
        return sd, ed

    def _estimate_limit(
        start_date: Optional[str], end_date: Optional[str], default: int = 300
    ) -> int:
        start = parse_date_input(start_date) if start_date else None
        end = parse_date_input(end_date) if end_date else None
        if start and end:
            days = abs((end - start).days) + 1
            return min(max(days, 50), 1000)
        return default

    def _normalize_klines(klines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cleaned: List[Dict[str, Any]] = []
        for row in klines or []:
            if not isinstance(row, dict):
                continue
            if row.get("close") is None:
                continue
            date_val = row.get("date") or row.get("time")
            if date_val is not None:
                row = {**row, "date": str(date_val)[:10]}
            cleaned.append(row)
        cleaned.sort(key=lambda x: str(x.get("date") or x.get("time") or ""))
        return cleaned

    async def _fetch_klines(
        db, code: str, start_date: Optional[str], end_date: Optional[str]
    ) -> tuple[List[Dict[str, Any]], str]:
        klines = await db.get_klines(code, start_date, end_date)
        normalized = _normalize_klines(klines)
        if normalized:
            return normalized, "timescaledb"

        limit = _estimate_limit(start_date, end_date)
        fallback = get_kline_data(
            code=code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            adjust="qfq",
        )
        if fallback.get("success"):
            fallback_klines = _normalize_klines(fallback.get("data") or [])
            if fallback_klines:
                return fallback_klines, "market_fallback"

        return [], "none"
    
    @mcp.tool()
    async def run_simple_backtest(
        code: str,
        strategy: str = 'ma_cross',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        initial_capital: float = 100000,
        commission: float = 0.0003,
        short_period: int = 5,
        long_period: int = 20
    ):
        """
        运行简单回测
        
        Args:
            code: 股票代码
            strategy: 策略名称 ('ma_cross', 'buy_and_hold', 'momentum', 'rsi')
            start_date: 开始日期 (YYYY-MM-DD 或 YYYY)
            end_date: 结束日期 (YYYY-MM-DD 或 YYYY)
            initial_capital: 初始资金
            commission: 手续费率
            short_period: 短期均线周期
            long_period: 长期均线周期
        """
        try:
            db = get_db()

            code = normalize_code(code)

            # 日期格式处理：支持 YYYY 或 YYYY-MM-DD
            start_date, end_date = _normalize_dates(start_date, end_date)

            klines, _ = await _fetch_klines(db, code, start_date, end_date)

            if not klines:
                return fail('No kline data found')
            
            params = {
                'initial_capital': initial_capital,
                'commission': commission,
                'short_period': short_period,
                'long_period': long_period,
            }
            
            result = backtest_engine.run_backtest(code, klines, strategy, params)
            
            if result.get('success'):
                return ok(result['data'])
            else:
                return fail(result.get('error', 'Backtest failed'))
        
        except Exception as e:
            return fail(str(e))
    
    
    @mcp.tool()
    async def run_batch_backtest(
        codes: List[str],
        strategy: str = 'ma_cross',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        initial_capital: float = 100000,
        commission: float = 0.0003,
        short_period: int = 5,
        long_period: int = 20,
        use_parallel: bool = True
    ):
        """
        批量回测多只股票（支持Ray并行加速）- 性能优化版
        
        Args:
            codes: 股票代码列表
            strategy: 策略名称 ('ma_cross', 'buy_and_hold', 'momentum', 'rsi')
            start_date: 开始日期 (YYYY-MM-DD 或 YYYY)
            end_date: 结束日期 (YYYY-MM-DD 或 YYYY)
            initial_capital: 初始资金
            commission: 手续费率
            short_period: 短期均线周期
            long_period: 长期均线周期
            use_parallel: 是否使用Ray并行计算（需要安装ray）
        
        Returns:
            批量回测结果，包含每只股票的回测指标
        """
        try:
            import time
            start_time = time.time()

            db = get_db()

            # 日期格式处理：支持 YYYY 或 YYYY-MM-DD
            start_date, end_date = _normalize_dates(start_date, end_date)

            # 批量获取K线数据
            klines_dict = {}
            normalized_codes = [normalize_code(c) for c in (codes or [])]
            for code in normalized_codes:
                klines, _ = await _fetch_klines(db, code, start_date, end_date)
                if klines:
                    klines_dict[code] = klines
            
            if not klines_dict:
                return fail('No kline data found for any code')
            
            params = {
                'initial_capital': initial_capital,
                'commission': commission,
                'short_period': short_period,
                'long_period': long_period,
            }
            
            # 选择执行模式
            if use_parallel and RAY_AVAILABLE:
                # 使用优化的Ray并行回测
                result = ParallelBacktestEngine.batch_backtest(
                    list(klines_dict.keys()),
                    klines_dict,
                    strategy,
                    params
                )
                execution_mode = 'parallel_optimized'
            else:
                # 使用顺序回测
                if use_parallel and not RAY_AVAILABLE:
                    print("Warning: Ray not available, falling back to sequential execution")
                
                result = ParallelBacktestEngine.batch_backtest_sequential(
                    list(klines_dict.keys()),
                    klines_dict,
                    strategy,
                    params
                )
                execution_mode = 'sequential'
            
            elapsed_time = time.time() - start_time
            
            if result.get('success'):
                # 添加性能统计
                result['data']['execution_time'] = f"{elapsed_time:.2f}s"
                result['data']['execution_mode'] = execution_mode
                result['data']['codes_count'] = len(codes)
                result['data']['successful_count'] = len([r for r in result['data']['results'] if r.get('success', False)])
                
                # 计算平均指标
                successful_results = [r for r in result['data']['results'] if r.get('success', False)]
                if successful_results:
                    avg_return = sum(r.get('total_return', 0) for r in successful_results) / len(successful_results)
                    avg_sharpe = sum(r.get('sharpe_ratio', 0) for r in successful_results) / len(successful_results)
                    avg_max_dd = sum(r.get('max_drawdown', 0) for r in successful_results) / len(successful_results)
                    
                    result['data']['summary'] = {
                        'avg_return': float(avg_return),
                        'avg_return_pct': f"{avg_return*100:.2f}%",
                        'avg_sharpe_ratio': float(avg_sharpe),
                        'avg_max_drawdown': float(avg_max_dd),
                        'avg_max_drawdown_pct': f"{avg_max_dd*100:.2f}%",
                    }
                
                return ok(result['data'])
            else:
                return fail(result.get('error', 'Batch backtest failed'))
        
        except Exception as e:
            return fail(str(e))
            
            # 获取所有股票的K线数据
            klines_dict = {}
            for code in codes:
                klines = await db.get_klines(code, start_date, end_date)
                if klines:
                    klines_dict[code] = klines
            
            if not klines_dict:
                return fail('No kline data found for any stock')
            
            params = {
                'initial_capital': initial_capital,
                'commission': commission,
                'short_period': short_period,
                'long_period': long_period,
            }
            
            # 使用Ray并行回测（如果可用且启用）
            if use_parallel and RAY_AVAILABLE:
                result = ParallelBacktestEngine.batch_backtest(
                    codes=list(klines_dict.keys()),
                    klines_dict=klines_dict,
                    strategy=strategy,
                    params=params
                )
                
                if result.get('success'):
                    # 格式化结果
                    results = result['data']['results']
                    formatted_results = []
                    
                    for r in results:
                        if r.get('success'):
                            data = r['data']
                            formatted_results.append({
                                'code': data.get('code'),
                                'total_return': f"{data.get('total_return', 0) * 100:.2f}%",
                                'sharpe_ratio': f"{data.get('sharpe_ratio', 0):.2f}",
                                'max_drawdown': f"{data.get('max_drawdown', 0) * 100:.2f}%",
                                'trades': data.get('trades', 0),
                                'win_rate': f"{data.get('win_rate', 0) * 100:.2f}%",
                            })
                    
                    # 计算汇总统计
                    total_returns = [r['data']['total_return'] for r in results if r.get('success')]
                    avg_return = sum(total_returns) / len(total_returns) if total_returns else 0
                    
                    return ok({
                        'results': formatted_results,
                        'summary': {
                            'total_stocks': len(codes),
                            'successful': len(formatted_results),
                            'failed': len(codes) - len(formatted_results),
                            'average_return': f"{avg_return * 100:.2f}%",
                            'parallel_mode': 'Ray',
                        }
                    })
                else:
                    return fail(result.get('error', 'Batch backtest failed'))
            
            # 串行回测（fallback）
            else:
                results = []
                for code in klines_dict.keys():
                    result = backtest_engine.run_backtest(
                        code, 
                        klines_dict[code], 
                        strategy, 
                        params
                    )
                    
                    if result.get('success'):
                        data = result['data']
                        results.append({
                            'code': data.get('code'),
                            'total_return': f"{data.get('total_return', 0) * 100:.2f}%",
                            'sharpe_ratio': f"{data.get('sharpe_ratio', 0):.2f}",
                            'max_drawdown': f"{data.get('max_drawdown', 0) * 100:.2f}%",
                            'trades': data.get('trades', 0),
                            'win_rate': f"{data.get('win_rate', 0) * 100:.2f}%",
                        })
                
                # 计算汇总统计
                if results:
                    total_returns = [float(r['total_return'].rstrip('%')) / 100 for r in results]
                    avg_return = sum(total_returns) / len(total_returns)
                else:
                    avg_return = 0
                
                return ok({
                    'results': results,
                    'summary': {
                        'total_stocks': len(codes),
                        'successful': len(results),
                        'failed': len(codes) - len(results),
                        'average_return': f"{avg_return * 100:.2f}%",
                        'parallel_mode': 'Sequential (Ray not available)' if not RAY_AVAILABLE else 'Sequential',
                    }
                })
        
        except Exception as e:
            return fail(str(e))
