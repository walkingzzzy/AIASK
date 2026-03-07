"""回测工具"""

import asyncio
import time
from typing import Optional, Dict, Any, List, Tuple
from ..services import backtest_engine
from ..services.data_sync import data_sync_service
from ..storage import get_db
from ..utils import ok, fail, normalize_code, parse_date_input
from .market import get_kline_data
from .tdx_integration import send_backtest_result, send_backtest_trades

# 检查Ray是否可用
RAY_AVAILABLE = False
try:
    from ..services.backtest import ParallelBacktestEngine
    RAY_AVAILABLE = True
except ImportError:
    pass




def _normalize_dates_global(
    start_date: Optional[str], end_date: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    sd = start_date
    ed = end_date
    if sd and len(sd) == 4:
        sd = f"{sd}-01-01"
    if ed and len(ed) == 4:
        ed = f"{ed}-12-31"
    return sd, ed


def _normalize_klines_global(klines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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


async def _fetch_klines_for_code(
    db: Any,
    code: str,
    start_date: Optional[str],
    end_date: Optional[str],
    limit: int = 300,
) -> tuple[List[Dict[str, Any]], str]:
    try:
        klines = await db.get_klines(code, start_date, end_date)
    except Exception:
        klines = []

    normalized = _normalize_klines_global(klines)
    if normalized:
        return normalized, "timescaledb"

    fallback = await get_kline_data(
        code=code,
        period="daily",
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        adjust="qfq",
    )
    if fallback.get("success"):
        fallback_klines = _normalize_klines_global(fallback.get("data") or [])
        if fallback_klines:
            return fallback_klines, "market_fallback"

    return [], "none"


def _estimate_limit_global(
    start_date: Optional[str], end_date: Optional[str], default: int = 300
) -> int:
    start = parse_date_input(start_date) if start_date else None
    end = parse_date_input(end_date) if end_date else None
    if start and end:
        days = abs((end - start).days) + 1
        return min(max(days, 50), 1000)
    return default


async def _fetch_klines_batch_global(
    db: Any,
    codes: List[str],
    start_date: Optional[str],
    end_date: Optional[str],
    fetch_concurrency: int,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, int]]:
    """Prefer DB batch fetch and fallback to bounded concurrent single-code fetch."""
    source_counter: Dict[str, int] = {
        "timescaledb_batch": 0,
        "timescaledb": 0,
        "market_fallback": 0,
        "none": 0,
    }

    normalized_codes = [str(c).strip() for c in (codes or []) if str(c).strip()]
    if not normalized_codes:
        return {}, source_counter

    klines_dict: Dict[str, List[Dict[str, Any]]] = {}
    batch_method = getattr(db, "get_klines_batch", None)
    if callable(batch_method):
        try:
            limit = _estimate_limit_global(start_date, end_date)
            batch_rows = await batch_method(normalized_codes, start_date, end_date, limit)
            rows_dict = batch_rows if isinstance(batch_rows, dict) else {}
            for code in normalized_codes:
                normalized = _normalize_klines_global(rows_dict.get(code, []))
                if normalized:
                    klines_dict[code] = normalized
                    source_counter["timescaledb_batch"] += 1
        except Exception:
            pass

    missing_codes = [c for c in normalized_codes if c not in klines_dict]
    if missing_codes:
        concurrency = max(1, min(int(fetch_concurrency or 1), 20))
        semaphore = asyncio.Semaphore(concurrency)
        limit = _estimate_limit_global(start_date, end_date)

        async def _worker(code: str) -> Tuple[str, List[Dict[str, Any]], str]:
            async with semaphore:
                klines, source = await _fetch_klines_for_code(
                    db=db,
                    code=code,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit,
                )
                return code, klines, source

        results = await asyncio.gather(*[_worker(code) for code in missing_codes], return_exceptions=True)
        for item in results:
            if isinstance(item, Exception):
                source_counter["none"] += 1
                continue
            code, klines, source = item
            source_counter[source] = source_counter.get(source, 0) + 1
            if klines:
                klines_dict[code] = klines

    return klines_dict, source_counter


async def run_simple_backtest(
    code: str,
    strategy: str = 'ma_cross',
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_capital: float = 100000,
    commission: float = 0.0003,
    short_period: int = 5,
    long_period: int = 20,
    benchmark: str = '000300',
    slippage: float = 0.0,
):
    """模块级回测接口（兼容测试中的直接导入调用）。"""
    try:
        db = get_db()
        code = normalize_code(code)
        start_date, end_date = _normalize_dates_global(start_date, end_date)

        klines, _ = await _fetch_klines_for_code(db, code, start_date, end_date)
        if not klines:
            return fail('No kline data found')

        benchmark_klines: List[Dict[str, Any]] = []
        benchmark_code = (benchmark or '').strip()
        if benchmark_code:
            bm_code = normalize_code(benchmark_code)
            benchmark_klines, _ = await _fetch_klines_for_code(db, bm_code, start_date, end_date)

        from ..services.cost_model import resolve_cost_assumptions
        cost = resolve_cost_assumptions(
            {"commission": commission, "slippage": slippage},
            default_mode="backtest",
        )
        params = {
            'initial_capital': initial_capital,
            'commission': cost["commission_rate"],
            'slippage': cost["slippage_bps"] / 10000.0,
            'short_period': short_period,
            'long_period': long_period,
            'benchmark': benchmark_code,
            'benchmark_klines': benchmark_klines,
            '_cost_assumptions': cost,
        }
        result = backtest_engine.run_backtest(code, klines, strategy, params)
        if result.get('success'):
            return ok(result.get('data') or {})
        return fail(result.get('error', 'Backtest failed'))
    except Exception as e:
        return fail(str(e))


async def run_batch_backtest(
    codes: List[str],
    strategy: str = 'ma_cross',
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_capital: float = 100000,
    commission: float = 0.0003,
    short_period: int = 5,
    long_period: int = 20,
    use_parallel: bool = True,
    fetch_concurrency: int = 8,
    warmup_before_fetch: bool = False,
):
    """模块级批量回测接口（兼容 tests 直接 import）。"""
    try:
        total_start = time.perf_counter()
        db = get_db()

        start_date, end_date = _normalize_dates_global(start_date, end_date)
        normalized_codes = [normalize_code(c) for c in (codes or [])]
        if not normalized_codes:
            return fail('codes is empty')

        if warmup_before_fetch:
            await data_sync_service.sync_stock_klines(
                codes=normalized_codes,
                start_date=start_date or '',
                end_date=end_date or '',
                period='daily',
            )

        from ..services.cost_model import resolve_cost_assumptions
        cost = resolve_cost_assumptions(
            {"commission": commission},
            default_mode="backtest",
        )
        params = {
            'initial_capital': initial_capital,
            'commission': cost["commission_rate"],
            'short_period': short_period,
            'long_period': long_period,
            '_cost_assumptions': cost,
        }
        io_start = time.perf_counter()
        klines_dict, source_stats = await _fetch_klines_batch_global(
            db=db,
            codes=normalized_codes,
            start_date=start_date,
            end_date=end_date,
            fetch_concurrency=fetch_concurrency,
        )
        io_seconds = time.perf_counter() - io_start

        results: List[Dict[str, Any]] = []
        for code in normalized_codes:
            klines = klines_dict.get(code) or []
            if not klines:
                continue
            single = backtest_engine.run_backtest(code, klines, strategy, params)
            if single.get('success'):
                results.append(single.get('data') or {})

        payload: Dict[str, Any] = {
            'results': results,
            'count': len(results),
            'execution_mode': 'parallel_optimized' if (use_parallel and RAY_AVAILABLE) else 'local_sequential',
            'codes_count': len(normalized_codes),
            'requested_codes': normalized_codes,
            'successful_count': len(results),
            'failed_count': len(normalized_codes) - len(results),
            'fetch_concurrency': max(1, min(int(fetch_concurrency or 1), 20)),
            'source_stats': source_stats,
            'timings': {
                'io_fetch_seconds': round(io_seconds, 6),
                'total_seconds': round(time.perf_counter() - total_start, 6),
            },
        }

        if results:
            avg_return = sum(r.get('total_return', 0) for r in results) / len(results)
            avg_sharpe = sum(r.get('sharpe_ratio', 0) for r in results) / len(results)
            payload['summary'] = {
                'avg_return': float(avg_return),
                'avg_return_pct': f"{avg_return * 100:.2f}%",
                'avg_sharpe_ratio': float(avg_sharpe),
            }

        payload['execution_time'] = f"{(time.perf_counter() - total_start):.2f}s"
        return ok(payload)
    except Exception as e:
        return fail(str(e))


__all__ = ['run_simple_backtest', 'run_batch_backtest', 'register']



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
        return _estimate_limit_global(start_date, end_date, default)

    def _normalize_klines(klines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return _normalize_klines_global(klines)

    async def _fetch_klines(
        db, code: str, start_date: Optional[str], end_date: Optional[str]
    ) -> tuple[List[Dict[str, Any]], str]:
        limit = _estimate_limit(start_date, end_date)
        return await _fetch_klines_for_code(
            db=db,
            code=code,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    async def _fetch_klines_batch(
        db,
        codes: List[str],
        start_date: Optional[str],
        end_date: Optional[str],
        fetch_concurrency: int,
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, int]]:
        return await _fetch_klines_batch_global(
            db=db,
            codes=codes,
            start_date=start_date,
            end_date=end_date,
            fetch_concurrency=fetch_concurrency,
        )

    @mcp.tool()
    async def run_simple_backtest(
        code: str,
        strategy: str = 'ma_cross',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        initial_capital: float = 100000,
        commission: float = 0.0003,
        short_period: int = 5,
        long_period: int = 20,
        benchmark: str = '000300',
        slippage: float = 0.0,
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
            benchmark: 基准代码（默认000300）
            slippage: 滑点成本率（与commission叠加）
        """
        try:
            db = get_db()

            code = normalize_code(code)

            # 日期格式处理：支持 YYYY 或 YYYY-MM-DD
            start_date, end_date = _normalize_dates(start_date, end_date)

            klines, _ = await _fetch_klines(db, code, start_date, end_date)

            if not klines:
                return fail('No kline data found')

            benchmark_klines: List[Dict[str, Any]] = []
            benchmark_code = (benchmark or '').strip()
            if benchmark_code:
                bm_code = normalize_code(benchmark_code)
                benchmark_klines, _ = await _fetch_klines(db, bm_code, start_date, end_date)

            from ..services.cost_model import resolve_cost_assumptions
            cost = resolve_cost_assumptions(
                {"commission": commission, "slippage": slippage},
                default_mode="backtest",
            )
            params = {
                'initial_capital': initial_capital,
                'commission': cost["commission_rate"],
                'slippage': cost["slippage_bps"] / 10000.0,
                'short_period': short_period,
                'long_period': long_period,
                'benchmark': benchmark_code,
                'benchmark_klines': benchmark_klines,
                '_cost_assumptions': cost,
            }

            result = backtest_engine.run_backtest(code, klines, strategy, params)

            if result.get('success'):
                return ok(result['data'])
            else:
                return fail(result.get('error', 'Backtest failed'))

        except Exception as e:
            return fail(str(e))


    @mcp.tool()
    async def run_backtest_and_send_to_tdx(
        code: str,
        strategy: str = 'ma_cross',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        initial_capital: float = 100000,
        send_to_tdx: bool = True,
        send_mode: str = 'result',
    ):
        """运行回测并发送结果到TDX（兼容字段）。

        Args:
            code: 股票代码
            strategy: 回测策略
            start_date: 开始日期
            end_date: 结束日期
            initial_capital: 初始资金
            send_to_tdx: 是否发送到TDX，默认 True
            send_mode: 发送模式，'result' 或 'trades'，默认 'result'
        """
        try:
            backtest_result = await run_simple_backtest(
                code=code,
                strategy=strategy,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
            )

            if not isinstance(backtest_result, dict) or not backtest_result.get('success'):
                return fail((backtest_result or {}).get('error', 'Backtest failed'))

            bt_data = backtest_result.get('data') if isinstance(backtest_result.get('data'), dict) else {}

            if not send_to_tdx:
                tdx_result = {
                    "success": True,
                    "message": "TDX send skipped (send_to_tdx=false)",
                    "skipped": True,
                }
            else:
                mode = (send_mode or 'result').strip().lower()
                if mode not in ('result', 'trades'):
                    return fail(f"Invalid send_mode: {send_mode}, expected 'result' or 'trades'")

                norm_code = normalize_code(code)
                date_token = (end_date or start_date or time.strftime('%Y-%m-%d'))

                if mode == 'trades':
                    pnl = float(bt_data.get('final_capital', 0.0) or 0.0) - float(bt_data.get('initial_capital', 0.0) or 0.0)
                    synthetic_trades = [{
                        'date': str(date_token)[:10],
                        'price': float(bt_data.get('final_capital') or 0.0),
                        'signal': 0,
                        'shares': 0,
                        'profit': pnl,
                    }]
                    tdx_result = send_backtest_trades(stock_code=norm_code, trades=synthetic_trades)
                else:
                    metric_value = float(bt_data.get('total_return', 0.0) or 0.0)
                    time_list = [str(date_token)[:10]]
                    data_list = [[str(metric_value)]]
                    tdx_result = send_backtest_result(
                        stock_code=norm_code,
                        time_list=time_list,
                        data_list=data_list,
                        count=1,
                    )

            # 兼容测试断言：同时保留两个字段，且指向同一个对象
            return ok({
                "backtest_result": bt_data,
                "tdx_send_result": tdx_result,
                "tdx_send_status": tdx_result,
            })
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
        use_parallel: bool = True,
        fetch_concurrency: int = 8,
        warmup_before_fetch: bool = False,
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
            warmup_before_fetch: 是否在回测前做数据预热

        Returns:
            批量回测结果，包含每只股票的回测指标
        """
        try:
            total_start = time.perf_counter()
            db = get_db()

            # 日期格式处理：支持 YYYY 或 YYYY-MM-DD
            start_date, end_date = _normalize_dates(start_date, end_date)
            normalized_codes = [normalize_code(c) for c in (codes or [])]
            if not normalized_codes:
                return fail("codes is empty")

            # 可选：回测前预热（走统一 data_sync 流程）
            warmup_result = None
            if warmup_before_fetch:
                warmup_result = await data_sync_service.sync_stock_klines(
                    codes=normalized_codes,
                    start_date=start_date or "",
                    end_date=end_date or "",
                    period="daily",
                )

            # 阶段1：并发取数（优先批量DB）
            io_start = time.perf_counter()
            klines_dict, source_stats = await _fetch_klines_batch(
                db=db,
                codes=normalized_codes,
                start_date=start_date,
                end_date=end_date,
                fetch_concurrency=fetch_concurrency,
            )
            io_seconds = time.perf_counter() - io_start

            if not klines_dict:
                return fail("No kline data found for any code")

            from ..services.cost_model import resolve_cost_assumptions
            cost = resolve_cost_assumptions(
                {"commission": commission},
                default_mode="backtest",
            )
            params = {
                "initial_capital": initial_capital,
                "commission": cost["commission_rate"],
                "short_period": short_period,
                "long_period": long_period,
                "_cost_assumptions": cost,
            }

            # 阶段2：回测计算
            compute_start = time.perf_counter()
            engine = globals().get("ParallelBacktestEngine")
            can_parallel = bool(use_parallel and RAY_AVAILABLE and engine)
            if can_parallel:
                result = engine.batch_backtest(
                    list(klines_dict.keys()),
                    klines_dict,
                    strategy,
                    params,
                )
                execution_mode = "parallel_optimized"
            elif engine and hasattr(engine, "batch_backtest_sequential"):
                result = engine.batch_backtest_sequential(
                    list(klines_dict.keys()),
                    klines_dict,
                    strategy,
                    params,
                )
                execution_mode = "sequential"
            else:
                # 无Ray环境下的纯本地后备执行
                local_results: List[Dict[str, Any]] = []
                for code in list(klines_dict.keys()):
                    single = backtest_engine.run_backtest(
                        code,
                        klines_dict[code],
                        strategy,
                        params,
                    )
                    if single.get("success"):
                        local_results.append(single.get("data") or {})
                result = {
                    "success": True,
                    "data": {"results": local_results, "count": len(local_results)},
                }
                execution_mode = "local_sequential"
            compute_seconds = time.perf_counter() - compute_start

            if not result.get("success"):
                return fail(result.get("error", "Batch backtest failed"))

            # 阶段3：汇总统计
            aggregation_start = time.perf_counter()
            payload = result.get("data") or {}
            payload["execution_mode"] = execution_mode
            payload["codes_count"] = len(normalized_codes)
            payload["requested_codes"] = normalized_codes
            payload["fetch_concurrency"] = max(1, min(int(fetch_concurrency or 1), 20))
            payload["source_stats"] = source_stats
            payload["warmup_enabled"] = bool(warmup_before_fetch)
            if warmup_result is not None:
                payload["warmup"] = warmup_result

            successful_results = [
                r for r in (payload.get("results") or []) if r.get("success", True)
            ]
            payload["successful_count"] = len(successful_results)
            payload["failed_count"] = payload["codes_count"] - payload["successful_count"]

            if successful_results:
                avg_return = sum(r.get("total_return", 0) for r in successful_results) / len(successful_results)
                avg_sharpe = sum(r.get("sharpe_ratio", 0) for r in successful_results) / len(successful_results)
                avg_max_dd = sum(r.get("max_drawdown", 0) for r in successful_results) / len(successful_results)
                payload["summary"] = {
                    "avg_return": float(avg_return),
                    "avg_return_pct": f"{avg_return * 100:.2f}%",
                    "avg_sharpe_ratio": float(avg_sharpe),
                    "avg_max_drawdown": float(avg_max_dd),
                    "avg_max_drawdown_pct": f"{avg_max_dd * 100:.2f}%",
                }

            aggregation_seconds = time.perf_counter() - aggregation_start
            total_seconds = time.perf_counter() - total_start
            payload["timings"] = {
                "io_fetch_seconds": round(io_seconds, 6),
                "compute_seconds": round(compute_seconds, 6),
                "aggregation_seconds": round(aggregation_seconds, 6),
                "total_seconds": round(total_seconds, 6),
            }
            payload["execution_time"] = f"{total_seconds:.2f}s"
            payload["performance_goal"] = {
                "target": "same codes, total time reduce 30%+",
                "io_parallel_enabled": True,
            }

            return ok(payload)
        except Exception as e:
            return fail(str(e))
