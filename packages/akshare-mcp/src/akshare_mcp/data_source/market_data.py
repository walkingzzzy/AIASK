"""
数据源管理 - 市场数据方法

包含 get_trading_dates、get_ipo_info、get_cb_info、get_gb_info 等。
数据源优先级: TDX → Tushare Pro → AKShare
"""

import datetime
import logging

from ..utils import normalize_code, safe_float, safe_int, safe_stderr_print

logger = logging.getLogger(__name__)

try:
    import akshare as ak
except ImportError:
    ak = None


class MarketDataMixin:
    """市场数据 Mixin（交易日历、IPO、可转债、股本）"""

    @staticmethod
    def _build_quality_flags(*, success: bool, fallback_used: bool, fallback_reason: str | None) -> list[str]:
        flags: list[str] = []
        if fallback_used:
            flags.append("fallback")
        if not success:
            flags.append("degraded")
        if fallback_reason == "all_backends_failed":
            flags.append("failed")
        elif str(fallback_reason or "").startswith("invalid_"):
            flags.append("invalid_request")
        return flags

    def _fallback_meta_result(
        self,
        *,
        success: bool,
        data,
        source: str,
        message: str,
        backend_requested: str,
        backend_used: str,
        fallback_used: bool,
        fallback_reason: str | None,
        started_at: datetime.datetime,
    ) -> dict:
        now = datetime.datetime.now()
        latency_ms = round(max((now - started_at).total_seconds() * 1000, 0.0), 3)
        asof_time = now.astimezone().isoformat()
        return {
            "success": success,
            "data": data,
            "source": source,
            "message": message,
            "asof_time": asof_time,
            "freshness_sec": 0.0,
            "quality_flags": self._build_quality_flags(
                success=success,
                fallback_used=bool(fallback_used),
                fallback_reason=fallback_reason,
            ),
            "backend_requested": backend_requested,
            "backend_used": backend_used,
            "fallback_used": bool(fallback_used),
            "fallback_reason": fallback_reason,
            "latency_ms": latency_ms,
        }

    def _result_with_requested_backend(
        self,
        *,
        success: bool,
        data,
        source: str,
        message: str,
        backend_requested: str,
        backend_used: str,
        started_at: datetime.datetime,
    ) -> dict:
        return self._fallback_meta_result(
            success=success,
            data=data,
            source=source,
            message=message,
            backend_requested=backend_requested,
            backend_used=backend_used,
            fallback_used=backend_used != backend_requested,
            fallback_reason=None if success or backend_used == backend_requested else "all_backends_failed",
            started_at=started_at,
        )

    def _failed_fallback_result(
        self,
        *,
        data,
        message: str,
        backend_requested: str,
        backend_used: str = "none",
        fallback_reason: str = "all_backends_failed",
        started_at: datetime.datetime,
    ) -> dict:
        return self._fallback_meta_result(
            success=False,
            data=data,
            source="none",
            message=message,
            backend_requested=backend_requested,
            backend_used=backend_used,
            fallback_used=backend_requested != backend_used,
            fallback_reason=fallback_reason,
            started_at=started_at,
        )


    def get_trading_dates(
        self,
        market: str = "SH",
        start_time: str = "",
        end_time: str = "",
        count: int = -1
    ) -> dict:
        """
        获取交易日历

        Args:
            market: 市场代码 (暂固定为SH)
            start_time: 起始日期 (格式: YYYYMMDD)
            end_time: 结束日期 (格式: YYYYMMDD)
            count: 返回最近的count个交易日，-1表示全部

        Returns:
            dict: {"success": bool, "data": list, "source": str, "message": str}
        """
        started_at = datetime.datetime.now()
        backend_requested = "tdx"

        def _valid_yyyymmdd(value: str) -> bool:
            if not value:
                return True
            if len(value) != 8 or not value.isdigit():
                return False
            try:
                datetime.datetime.strptime(value, "%Y%m%d")
                return True
            except ValueError:
                return False

        # 参数校验
        if not _valid_yyyymmdd(start_time):
            return self._failed_fallback_result(
                data=[],
                message="start_time 格式错误，应为 YYYYMMDD",
                backend_requested=backend_requested,
                fallback_reason="invalid_start_time",
                started_at=started_at,
            )
        if not _valid_yyyymmdd(end_time):
            return self._failed_fallback_result(
                data=[],
                message="end_time 格式错误，应为 YYYYMMDD",
                backend_requested=backend_requested,
                fallback_reason="invalid_end_time",
                started_at=started_at,
            )
        if start_time and end_time and start_time > end_time:
            return self._failed_fallback_result(
                data=[],
                message="start_time 不能晚于 end_time",
                backend_requested=backend_requested,
                fallback_reason="invalid_time_range",
                started_at=started_at,
            )
        if count == 0 or count < -1:
            return self._failed_fallback_result(
                data=[],
                message="count 仅支持 -1 或正整数",
                backend_requested=backend_requested,
                fallback_reason="invalid_count",
                started_at=started_at,
            )

        # 1. 优先使用 TDX
        if self.is_tdx_available():
            try:
                tq = self.get_tdxquant()
                if tq:
                    result = tq.get_trading_dates(
                        market=market,
                        start_time=start_time,
                        end_time=end_time,
                        count=count
                    )
                    if isinstance(result, list):
                        dates = [str(d) for d in result if str(d)]
                        dates = sorted(dates)
                        if count > 0:
                            dates = dates[-count:]
                        return self._result_with_requested_backend(
                            success=True,
                            data=dates,
                            source="tdx",
                            message=f"获取到 {len(dates)} 个交易日",
                            backend_requested=backend_requested,
                            backend_used="tdx",
                            started_at=started_at,
                        )
            except Exception as e:
                safe_stderr_print(f"[DataSource] TDX get_trading_dates failed: {e}")

        # 2. 降级到 Tushare Pro
        if self.ts_pro:
            try:
                start_date = start_time if start_time else None
                end_date = end_time if end_time else None

                df = self.ts_pro.trade_cal(
                    exchange='SSE',
                    start_date=start_date,
                    end_date=end_date,
                    is_open='1'
                )
                if df is not None and not df.empty:
                    dates = [str(d) for d in df['cal_date'].tolist() if d]
                    dates = sorted(dates)
                    if count > 0:
                        dates = dates[-count:]
                    return self._result_with_requested_backend(
                        success=True,
                        data=dates,
                        source="tushare_pro",
                        message=f"获取到 {len(dates)} 个交易日",
                        backend_requested=backend_requested,
                        backend_used="tushare_pro",
                        started_at=started_at,
                    )
            except Exception as e:
                safe_stderr_print(f"[DataSource] Tushare Pro trade_cal failed: {e}")

        # 3. 降级到 AKShare
        if ak is not None:
            try:
                df = ak.tool_trade_date_hist_sina()
                if df is not None and not df.empty:
                    dates = [d.strftime('%Y%m%d') for d in df['trade_date'].tolist()]
                    if start_time:
                        dates = [d for d in dates if d >= start_time]
                    if end_time:
                        dates = [d for d in dates if d <= end_time]
                    dates = sorted(dates)
                    if count > 0:
                        dates = dates[-count:]
                    return self._result_with_requested_backend(
                        success=True,
                        data=dates,
                        source="akshare",
                        message=f"获取到 {len(dates)} 个交易日",
                        backend_requested=backend_requested,
                        backend_used="akshare",
                        started_at=started_at,
                    )
            except Exception as e:
                safe_stderr_print(f"[DataSource] AKShare trade_date failed: {e}")

        return self._failed_fallback_result(
            data=[],
            message="所有数据源均失败",
            backend_requested=backend_requested,
            fallback_reason="all_backends_failed",
            started_at=started_at,
        )

    def get_ipo_info(
        self,
        ipo_type: int = 0,
        ipo_date: int = 1
    ) -> dict:
        """
        获取新股/新债申购信息

        Args:
            ipo_type: 0=新股, 1=新发债, 2=新股和新发债
            ipo_date: 0=只获取今天, 1=今天及以后

        Returns:
            dict: {"success": bool, "data": list, "source": str, "message": str}
        """
        started_at = datetime.datetime.now()
        backend_requested = "tdx"

        # 1. 优先使用 TDX
        if self.is_tdx_available():
            try:
                tq = self.get_tdxquant()
                if tq:
                    result = tq.get_ipo_info(ipo_type=ipo_type, ipo_date=ipo_date)
                    if isinstance(result, list):
                        return self._result_with_requested_backend(
                            success=True,
                            data=result,
                            source="tdx",
                            message=f"获取到 {len(result)} 条申购信息",
                            backend_requested=backend_requested,
                            backend_used="tdx",
                            started_at=started_at,
                        )
            except Exception as e:
                safe_stderr_print(f"[DataSource] TDX get_ipo_info failed: {e}")

        # 2. 降级到 Tushare Pro (新股)
        if self.ts_pro and ipo_type in (0, 2):
            try:
                df = self.ts_pro.new_share(start_date='', end_date='')
                if df is not None and not df.empty:
                    today = datetime.datetime.now().strftime('%Y%m%d')
                    if ipo_date == 0:
                        df = df[df['ipo_date'] == today]
                    else:
                        past_90 = (datetime.datetime.now() - datetime.timedelta(days=90)).strftime('%Y%m%d')
                        df = df[df['ipo_date'] >= past_90]

                    data = df.to_dict('records')
                    return self._result_with_requested_backend(
                        success=True,
                        data=data,
                        source="tushare_pro",
                        message=f"获取到 {len(data)} 条新股申购信息",
                        backend_requested=backend_requested,
                        backend_used="tushare_pro",
                        started_at=started_at,
                    )
            except Exception as e:
                safe_stderr_print(f"[DataSource] Tushare Pro new_share failed: {e}")

        # 3. 降级到 AKShare
        if ak is not None:
            try:
                results = []

                if ipo_type in (0, 2):
                    try:
                        df = ak.stock_xgsglb_em()
                        if df is not None and not df.empty:
                            for _, row in df.iterrows():
                                results.append({
                                    "code": str(row.get("股票代码", "")),
                                    "name": str(row.get("股票简称", "")),
                                    "SGDate": str(row.get("申购日期", "")).replace("-", ""),
                                    "SGPrice": str(row.get("发行价格", "")),
                                    "type": "stock"
                                })
                    except Exception:
                        pass

                if ipo_type in (1, 2):
                    try:
                        df = ak.bond_cb_jsl()
                        if df is not None and not df.empty:
                            today = datetime.datetime.now().strftime('%Y-%m-%d')
                            for _, row in df.iterrows():
                                sg_date = str(row.get("申购日期", ""))
                                if ipo_date == 0 and sg_date != today:
                                    continue
                                if ipo_date == 1 and sg_date < today:
                                    continue
                                results.append({
                                    "code": str(row.get("转债代码", "")),
                                    "name": str(row.get("转债名称", "")),
                                    "SGDate": sg_date.replace("-", ""),
                                    "SGPrice": "100.00",
                                    "type": "bond"
                                })
                    except Exception:
                        pass

                if results:
                    return self._result_with_requested_backend(
                        success=True,
                        data=results,
                        source="akshare",
                        message=f"获取到 {len(results)} 条申购信息",
                        backend_requested=backend_requested,
                        backend_used="akshare",
                        started_at=started_at,
                    )
            except Exception as e:
                safe_stderr_print(f"[DataSource] AKShare IPO info failed: {e}")

        return self._failed_fallback_result(
            data=[],
            message="所有数据源均失败",
            backend_requested=backend_requested,
            fallback_reason="all_backends_failed",
            started_at=started_at,
        )

    def get_cb_info(self, stock_code: str) -> dict:
        """
        获取可转债基础信息

        Args:
            stock_code: 可转债代码 (如 123039.SZ 或 123039)

        Returns:
            dict: {"success": bool, "data": dict, "source": str, "message": str}
        """
        started_at = datetime.datetime.now()
        backend_requested = "tdx"

        if not stock_code:
            return self._failed_fallback_result(
                data={},
                message="股票代码不能为空",
                backend_requested=backend_requested,
                fallback_reason="invalid_stock_code",
                started_at=started_at,
            )

        # 1. 优先使用 TDX
        if self.is_tdx_available():
            try:
                tq = self.get_tdxquant()
                if tq:
                    tdx_code = self._convert_to_tdx_code(stock_code)
                    result = tq.get_cb_info(stock_code=tdx_code)
                    if isinstance(result, dict) and result.get("KZZCode"):
                        return self._result_with_requested_backend(
                            success=True,
                            data=result,
                            source="tdx",
                            message="获取可转债信息成功",
                            backend_requested=backend_requested,
                            backend_used="tdx",
                            started_at=started_at,
                        )
            except Exception as e:
                safe_stderr_print(f"[DataSource] TDX get_cb_info failed: {e}")

        # 2. 降级到 Tushare Pro
        if self.ts_pro:
            try:
                code = stock_code.split('.')[0] if '.' in stock_code else stock_code
                df = self.ts_pro.cb_basic(ts_code=f"{code}.SH") if code.startswith('11') else \
                     self.ts_pro.cb_basic(ts_code=f"{code}.SZ")

                if df is not None and not df.empty:
                    row = df.iloc[0]
                    data = {
                        "KZZCode": code,
                        "HSCode": str(row.get("stk_code", "")),
                        "ZGPrice": str(row.get("conv_price", "")),
                        "ZGDate": str(row.get("conv_start_date", "")),
                        "EndDate": str(row.get("maturity_date", "")),
                        "RestScope": str(row.get("issue_size", ""))
                    }
                    return self._result_with_requested_backend(
                        success=True,
                        data=data,
                        source="tushare_pro",
                        message="获取可转债信息成功",
                        backend_requested=backend_requested,
                        backend_used="tushare_pro",
                        started_at=started_at,
                    )
            except Exception as e:
                safe_stderr_print(f"[DataSource] Tushare Pro cb_basic failed: {e}")

        # 3. 降级到 AKShare
        if ak is not None:
            try:
                df = ak.bond_cb_jsl()
                if df is not None and not df.empty:
                    code = stock_code.split('.')[0] if '.' in stock_code else stock_code
                    row = df[df['转债代码'] == code]
                    if not row.empty:
                        row = row.iloc[0]
                        data = {
                            "KZZCode": code,
                            "HSCode": str(row.get("正股代码", "")),
                            "name": str(row.get("转债名称", "")),
                            "ZGPrice": str(row.get("转股价", "")),
                            "RestScope": str(row.get("剩余规模", ""))
                        }
                        return self._result_with_requested_backend(
                            success=True,
                            data=data,
                            source="akshare",
                            message="获取可转债信息成功",
                            backend_requested=backend_requested,
                            backend_used="akshare",
                            started_at=started_at,
                        )
            except Exception as e:
                safe_stderr_print(f"[DataSource] AKShare cb_info failed: {e}")

        return self._failed_fallback_result(
            data={},
            message="所有数据源均失败",
            backend_requested=backend_requested,
            fallback_reason="all_backends_failed",
            started_at=started_at,
        )

    def get_gb_info(
        self,
        stock_code: str,
        date_list: list = None,
        count: int = 1
    ) -> dict:
        """
        获取股本数据

        Args:
            stock_code: 股票代码 (如 600519 或 600519.SH)
            date_list: 日期数组 (格式: ['YYYYMMDD', ...])，须从小到大排序
            count: 日期有效个数

        Returns:
            dict: {"success": bool, "data": list, "source": str, "message": str}
        """
        started_at = datetime.datetime.now()
        backend_requested = "tdx"

        if not stock_code:
            return self._failed_fallback_result(
                data=[],
                message="股票代码不能为空",
                backend_requested=backend_requested,
                fallback_reason="invalid_stock_code",
                started_at=started_at,
            )

        date_list = date_list or []

        # 1. 优先使用 TDX
        if self.is_tdx_available() and date_list:
            try:
                tq = self.get_tdxquant()
                if tq:
                    tdx_code = self._convert_to_tdx_code(stock_code)
                    result = tq.get_gb_info(
                        stock_code=tdx_code,
                        date_list=date_list,
                        count=count
                    )
                    if isinstance(result, list):
                        return self._result_with_requested_backend(
                            success=True,
                            data=result,
                            source="tdx",
                            message=f"获取到 {len(result)} 条股本数据",
                            backend_requested=backend_requested,
                            backend_used="tdx",
                            started_at=started_at,
                        )
            except Exception as e:
                safe_stderr_print(f"[DataSource] TDX get_gb_info failed: {e}")

        # 2. 降级到 Tushare Pro
        if self.ts_pro:
            try:
                code = normalize_code(stock_code)
                if code.startswith('6'):
                    ts_code = f"{code}.SH"
                else:
                    ts_code = f"{code}.SZ"

                df = self.ts_pro.daily_basic(ts_code=ts_code, fields='ts_code,trade_date,total_share,float_share')
                if df is not None and not df.empty:
                    results = []
                    for _, row in df.head(count).iterrows():
                        results.append({
                            "Date": int(row['trade_date']),
                            "ltgb": float(row['float_share']) * 10000 if row['float_share'] else 0,
                            "zgb": float(row['total_share']) * 10000 if row['total_share'] else 0
                        })
                    return self._result_with_requested_backend(
                        success=True,
                        data=results,
                        source="tushare_pro",
                        message=f"获取到 {len(results)} 条股本数据",
                        backend_requested=backend_requested,
                        backend_used="tushare_pro",
                        started_at=started_at,
                    )
            except Exception as e:
                safe_stderr_print(f"[DataSource] Tushare Pro daily_basic failed: {e}")

        # 3. 降级到 AKShare
        if ak is not None:
            try:
                code = normalize_code(stock_code)
                df = ak.stock_individual_info_em(symbol=code)
                if df is not None and not df.empty:
                    info_dict = dict(zip(df['item'], df['value']))
                    today = datetime.datetime.now().strftime('%Y%m%d')
                    data = [{
                        "Date": int(today),
                        "ltgb": safe_float(info_dict.get("流通股", 0)),
                        "zgb": safe_float(info_dict.get("总股本", 0))
                    }]
                    return self._result_with_requested_backend(
                        success=True,
                        data=data,
                        source="akshare",
                        message="获取到 1 条股本数据",
                        backend_requested=backend_requested,
                        backend_used="akshare",
                        started_at=started_at,
                    )
            except Exception as e:
                safe_stderr_print(f"[DataSource] AKShare stock_info failed: {e}")

        return self._failed_fallback_result(
            data=[],
            message="所有数据源均失败",
            backend_requested=backend_requested,
            fallback_reason="all_backends_failed",
            started_at=started_at,
        )
