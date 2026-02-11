"""回测工具"""

import asyncio
import time
from typing import Optional, Dict, Any, List, Tuple
from ..services import backtest_engine
from ..services.data_sync import data_sync_service
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

    async def _fetch_klines_batch(
        db,
        codes: List[str],
        start_date: Optional[str],
        end_date: Optional[str],
        fetch_concurrency: int,
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, int]]:
        """优先走DB批量接口，失败/缺失时回退逐只并发拉取。"""
        source_counter: Dict[str, int] = {
            "timescaledb_batch": 0,
            "timescaledb": 0,
            "market_fallback": 0,
            "none": 0,
        }

        # 路径1：优先尝试数据库批量读取
        batch_method = getattr(db, "get_klines_batch", None)
        if callable(batch_method):
            try:
                limit = _estimate_limit(start_date, end_date)
                batch_rows = await batch_method(codes, start_date, end_date, limit)
                klines_dict: Dict[str, List[Dict[str, Any]]] = {}
                for code in codes:
                    normalized = _normalize_klines((batch_rows or {}).get(code, []))
                    if normalized:
                        klines_dict[code] = normalized
                        source_counter["timescaledb_batch"] += 1

                # 对批量接口没命中的 code 做回退补齐
                missing_codes = [c for c in codes if c not in klines_dict]
                if not missing_codes:
                    return klines_dict, source_counter

                concurrency = max(1, min(int(fetch_concurrency or 1), 20))
                semaphore = asyncio.Semaphore(concurrency)

                async def _worker(code: str) -> Tuple[str, List[Dict[str, Any]], str]:
                    async with semaphore:
                        klines, source = await _fetch_klines(db, code, start_date, end_date)
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
            except Exception:
                # 批量读取失败时，自动回退旧路径
                pass

        # 路径2：旧路径（逐只并发拉取）
        concurrency = max(1, min(int(fetch_concurrency or 1), 20))
        semaphore = asyncio.Semaphore(concurrency)

        async def _worker(code: str) -> Tuple[str, List[Dict[str, Any]], str]:
            async with semaphore:
                klines, source = await _fetch_klines(db, code, start_date, end_date)
                return code, klines, source

        tasks = [_worker(code) for code in codes]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        klines_dict: Dict[str, List[Dict[str, Any]]] = {}
        for item in results:
            if isinstance(item, Exception):
                source_counter["none"] += 1
                continue
            code, klines, source = item
            source_counter[source] = source_counter.get(source, 0) + 1
            if klines:
                klines_dict[code] = klines

        return klines_dict, source_counter
    
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

            params = {
                "initial_capital": initial_capital,
                "commission": commission,
                "short_period": short_period,
                "long_period": long_period,
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
