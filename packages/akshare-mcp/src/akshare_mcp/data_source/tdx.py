"""
数据源管理 - TDX (TdxQuant) 相关方法

包含 TdxQuant 初始化、行情快照、K线、股票信息、除权因子、板块、订阅等。
"""

import os
import sys
import time
import logging
import threading
import importlib.util
import contextlib
import importlib
from typing import Optional

from ..utils import normalize_code, safe_float, safe_int, safe_stderr_print

logger = logging.getLogger(__name__)


class TdxMixin:
    """TdxQuant 数据源 Mixin"""

    # ---- 初始化 ----

    def _init_tdx_config(self):
        """初始化 TDX 配置（由 DataSourceManager._init 调用）"""
        self.tdx_plugin_path = os.getenv("TDX_PLUGIN_PATH", "").strip()
        self.tdx_init_path = os.getenv("TDX_INIT_PATH", "").strip()
        _tdx_unique_init = os.getenv("TDX_INIT_USE_UNIQUE", "1").strip().lower()
        self.tdx_init_use_unique = _tdx_unique_init not in ("0", "false", "no")
        _tdx_env = os.getenv("TDX_ENABLED", "").strip().lower()
        if _tdx_env in ("false", "0", "no"):
            self.tdx_enabled = False
        elif _tdx_env in ("true", "1", "yes"):
            self.tdx_enabled = True
        else:
            self.tdx_enabled = bool(self.tdx_plugin_path)
        self.tdx_timeout = float(os.getenv("TDX_TIMEOUT", "5"))
        self.tq = None
        self._tdx_initialized = False
        self._tdx_init_failed = False
        self._tdx_fail_time = 0.0
        self._tdx_last_init_stage = "not_started"
        self._tdx_last_init_error = ""
        self._tdx_module_path = ""
        self._tdx_lock = threading.Lock()

        if self.tdx_enabled:
            self._init_tdxquant()


    def _init_tdxquant(self):
        """初始化 TdxQuant 模块"""
        self._tdx_last_init_stage = "module_loading"
        self._tdx_last_init_error = ""
        self._tdx_module_path = ""

        if not self.tdx_enabled:
            self._tdx_last_init_stage = "disabled"
            self._tdx_last_init_error = "TDX is disabled by TDX_ENABLED"
            self.tq = None
            return

        try:
            safe_stderr_print(f"[DataSource] TDX_PLUGIN_PATH={self.tdx_plugin_path}")
            safe_stderr_print(f"[DataSource] TDX_ENABLED={self.tdx_enabled}")

            plugin_path_valid = bool(self.tdx_plugin_path) and os.path.isdir(self.tdx_plugin_path)
            tqcenter_path = os.path.join(self.tdx_plugin_path, "tqcenter.py") if self.tdx_plugin_path else ""
            tqcenter_exists = bool(tqcenter_path) and os.path.isfile(tqcenter_path)

            if plugin_path_valid:
                pyplugins_dir = os.path.dirname(self.tdx_plugin_path)
                tpythclient_path = os.path.join(pyplugins_dir, "TPythClient.dll")
                tdxrpc_path = os.path.join(pyplugins_dir, "tdxrpcx64.dll")
                tpythclient_exists = os.path.isfile(tpythclient_path)
                tdxrpc_exists = os.path.isfile(tdxrpc_path)

                safe_stderr_print(f"[DataSource] tqcenter.py path={tqcenter_path}, exists={tqcenter_exists}")
                safe_stderr_print(f"[DataSource] TPythClient.dll path={tpythclient_path}, exists={tpythclient_exists}")
                safe_stderr_print(f"[DataSource] tdxrpcx64.dll path={tdxrpc_path}, exists={tdxrpc_exists}")

                if tqcenter_exists and self.tdx_plugin_path not in sys.path:
                    sys.path.insert(0, self.tdx_plugin_path)
            else:
                self._tdx_last_init_stage = "plugin_path_check"
                self._tdx_last_init_error = f"TDX plugin path does not exist: {self.tdx_plugin_path}"
                safe_stderr_print(f"[DataSource] {self._tdx_last_init_error}")
                self.tq = None
                return

            if self.tdx_plugin_path and not tqcenter_exists:
                self._tdx_last_init_stage = "plugin_path_check"
                self._tdx_last_init_error = f"tqcenter.py not found under TDX_PLUGIN_PATH: {self.tdx_plugin_path}"
                safe_stderr_print(f"[DataSource] {self._tdx_last_init_error}")
                self.tq = None
                return

            # 优先使用显式插件目录导入 tqcenter，避免加载到错误版本模块
            self._tdx_last_init_stage = "import_tqcenter"
            tqcenter = importlib.import_module("tqcenter")
            module_path = getattr(tqcenter, "__file__", "") or ""
            if self.tdx_plugin_path:
                expected = os.path.abspath(self.tdx_plugin_path).lower()
                loaded_from = os.path.abspath(module_path).lower() if module_path else ""
                if loaded_from and not loaded_from.startswith(expected):
                    self._tdx_last_init_stage = "module_path_mismatch"
                    self._tdx_last_init_error = (
                        f"tqcenter loaded from unexpected path: {module_path}, expected under {self.tdx_plugin_path}"
                    )
                    safe_stderr_print(f"[DataSource] {self._tdx_last_init_error}")
                    self.tq = None
                    return

            tq = getattr(tqcenter, "tq", None)
            if tq is None:
                self._tdx_last_init_stage = "module_load_failed"
                self._tdx_last_init_error = "tqcenter.tq is missing"
                safe_stderr_print(f"[DataSource] {self._tdx_last_init_error}")
                self.tq = None
                return

            if not callable(getattr(tq, "initialize", None)):
                self._tdx_last_init_stage = "module_load_failed"
                self._tdx_last_init_error = "tq.initialize is missing or not callable"
                safe_stderr_print(f"[DataSource] {self._tdx_last_init_error}")
                self.tq = None
                return

            self.tq = tq
            self._tdx_module_path = module_path
            self._tdx_last_init_stage = "module_loaded"
            safe_stderr_print("[DataSource] TdxQuant module loaded successfully")
        except UnicodeDecodeError as e:
            self._tdx_last_init_stage = "module_load_failed"
            self._tdx_last_init_error = f"UnicodeDecodeError: {e}"
            safe_stderr_print(f"[DataSource] TdxQuant init failed (encoding error, check plugin files are UTF-8): {e}")
            self.tq = None
        except Exception as e:
            self._tdx_last_init_stage = "module_load_failed"
            self._tdx_last_init_error = f"{type(e).__name__}: {e}"
            safe_stderr_print(f"[DataSource] TdxQuant init failed: {type(e).__name__}: {e}")
            self.tq = None

    def _build_tdx_init_candidates(self) -> list[str]:
        """Build ordered initialize path candidates to avoid fixed-name strategy conflicts."""
        paths: list[str] = []

        if self.tdx_init_path:
            paths.append(self.tdx_init_path)

        if self.tdx_plugin_path and os.path.isdir(self.tdx_plugin_path):
            if self.tdx_init_use_unique:
                paths.append(os.path.join(self.tdx_plugin_path, f"mcp_strategy_{os.getpid()}.py"))
            paths.append(os.path.join(self.tdx_plugin_path, "mcp_strategy.py"))

        paths.append(__file__)

        deduped: list[str] = []
        seen: set[str] = set()
        for p in paths:
            key = str(p).strip()
            if not key:
                continue
            k = key.lower()
            if k in seen:
                continue
            seen.add(k)
            deduped.append(key)
        return deduped

    def _ensure_tdx_initialized(self) -> bool:
        """确保 TdxQuant 已初始化（懒加载），失败后间隔 60 秒可重试"""
        if self.tq is None:
            if not self.tdx_enabled:
                self._tdx_last_init_stage = "disabled"
                self._tdx_last_init_error = "TDX is disabled by TDX_ENABLED"
                return False

            self._init_tdxquant()
            if self.tq is None:
                self._tdx_last_init_stage = "module_not_loaded"
                if not self._tdx_last_init_error:
                    self._tdx_last_init_error = "tq is None (module not loaded)"
                safe_stderr_print(f"[DataSource] _ensure_tdx_initialized: {self._tdx_last_init_error}")
                return False

        if self._tdx_init_failed:
            elapsed = time.time() - self._tdx_fail_time if self._tdx_fail_time else 0
            if elapsed < 60:
                remain = int(60 - elapsed)
                safe_stderr_print(
                    f"[DataSource] TdxQuant cooldown active: {remain}s remaining, "
                    f"last_stage={self._tdx_last_init_stage}, last_error={self._tdx_last_init_error}",
                )
                return False
            safe_stderr_print("[DataSource] Retrying TdxQuant initialization after cooldown...")
            self._tdx_init_failed = False

        if not self._tdx_initialized:
            init_candidates = self._build_tdx_init_candidates()
            max_retries = 3

            for init_path in init_candidates:
                safe_stderr_print(f"[DataSource] Calling tq.initialize({init_path})")
                for attempt in range(1, max_retries + 1):
                    try:
                        self._tdx_last_init_stage = "initializing"
                        # Redirect any third-party stdout output to stderr to protect MCP stdio protocol.
                        with contextlib.redirect_stdout(sys.stderr):
                            self.tq.initialize(init_path)
                        self._tdx_initialized = True
                        self._tdx_last_init_stage = "initialized"
                        self._tdx_last_init_error = ""
                        safe_stderr_print(
                            f"[DataSource] TdxQuant initialized successfully (attempt {attempt}, path={init_path})"
                        )
                        return True
                    except Exception as e:
                        self._tdx_last_init_stage = "initialize_failed"
                        self._tdx_last_init_error = f"{type(e).__name__}: {e}"
                        if attempt < max_retries:
                            wait = 0.5 * attempt
                            safe_stderr_print(
                                f"[DataSource] TdxQuant init attempt {attempt} failed on {init_path}: "
                                f"{self._tdx_last_init_error}, retrying in {wait}s...",
                            )
                            time.sleep(wait)
                        else:
                            safe_stderr_print(
                                f"[DataSource] TdxQuant init path failed after {max_retries} attempts: "
                                f"{init_path}, error: {self._tdx_last_init_error}",
                            )

            self._tdx_init_failed = True
            self._tdx_fail_time = time.time()
            safe_stderr_print(
                f"[DataSource] TdxQuant initialize failed for all candidate paths {init_candidates} "
                f"(will retry after 60s): {self._tdx_last_init_error}",
            )
            return False
        return True

    def is_tdx_available(self) -> bool:
        """检查 TdxQuant 是否可用"""
        if not self.tdx_enabled:
            return False
        return self.get_tdxquant() is not None

    def get_tdx_init_diagnostics(self) -> dict:
        """返回 TDX 初始化诊断信息，供工具层输出更准确错误提示。"""
        plugin_path_valid = bool(self.tdx_plugin_path) and os.path.isdir(self.tdx_plugin_path)
        tqcenter_exists = bool(self.tdx_plugin_path) and os.path.isfile(
            os.path.join(self.tdx_plugin_path, "tqcenter.py")
        )
        pyplugins_dir = os.path.dirname(self.tdx_plugin_path) if self.tdx_plugin_path else ""
        tpythclient_path = os.path.join(pyplugins_dir, "TPythClient.dll") if pyplugins_dir else ""
        tdxrpc_path = os.path.join(pyplugins_dir, "tdxrpcx64.dll") if pyplugins_dir else ""

        return {
            "tdx_enabled": self.tdx_enabled,
            "tdx_plugin_path": self.tdx_plugin_path,
            "plugin_path_valid": plugin_path_valid,
            "tqcenter_exists": tqcenter_exists,
            "module_loaded": self.tq is not None,
            "initialized": self._tdx_initialized,
            "last_stage": self._tdx_last_init_stage,
            "last_error": self._tdx_last_init_error,
            "module_path": self._tdx_module_path,
            "dll_checks": {
                "TPythClient.dll": bool(tpythclient_path) and os.path.isfile(tpythclient_path),
                "tdxrpcx64.dll": bool(tdxrpc_path) and os.path.isfile(tdxrpc_path),
            },
        }

    def get_tdxquant(self):
        """获取 TdxQuant 实例"""
        if self._ensure_tdx_initialized():
            return self.tq
        return None

    def _convert_to_tdx_code(self, code: str) -> str:
        """转换股票代码为 TdxQuant 格式: 600519 → 600519.SH"""
        code = normalize_code(code)
        if code.startswith(("6", "5")):
            return f"{code}.SH"
        elif code.startswith(("0", "3", "1")):
            return f"{code}.SZ"
        else:
            return f"{code}.BJ"

    # ---- 行情快照 ----

    def _get_quote_tdxquant(self, code: str) -> Optional[dict]:
        """从 TdxQuant 获取实时行情（线程安全）"""
        tq = self.get_tdxquant()
        if tq is None:
            return None

        if not self._tdx_lock.acquire(timeout=5):
            logger.warning("TDX lock acquire timeout for quote %s, skip to fallback", code)
            return None
        try:
            tdx_code = self._convert_to_tdx_code(code)
            snapshot = tq.get_market_snapshot(stock_code=tdx_code)

            if not snapshot or snapshot.get("ErrorId") != "0":
                return None

            price = safe_float(snapshot.get("Now", 0))
            pre_close = safe_float(snapshot.get("LastClose", 0))
            change = price - pre_close if price and pre_close else None
            change_pct = (change / pre_close * 100) if change and pre_close else None

            buyp = snapshot.get("Buyp", [])
            buyv = snapshot.get("Buyv", [])
            sellp = snapshot.get("Sellp", [])
            sellv = snapshot.get("Sellv", [])

            return {
                "code": code,
                "name": "",
                "price": price,
                "change": change,
                "changePercent": change_pct,
                "open": safe_float(snapshot.get("Open", 0)),
                "high": safe_float(snapshot.get("High", 0)) or safe_float(snapshot.get("Max", 0)),
                "low": safe_float(snapshot.get("Low", 0)) or safe_float(snapshot.get("Min", 0)),
                "preClose": pre_close,
                "volume": safe_int(snapshot.get("Volume", 0)),
                "amount": safe_float(snapshot.get("Amount", 0)),
                "turnoverRate": None,
                "bid1": safe_float(buyp[0]) if buyp else None,
                "bid1Vol": safe_int(buyv[0]) if buyv else None,
                "ask1": safe_float(sellp[0]) if sellp else None,
                "ask1Vol": safe_int(sellv[0]) if sellv else None,
                "bids": [{"price": safe_float(buyp[i]), "volume": safe_int(buyv[i])} for i in range(min(len(buyp), len(buyv), 5))],
                "asks": [{"price": safe_float(sellp[i]), "volume": safe_int(sellv[i])} for i in range(min(len(sellp), len(sellv), 5))],
                "source": "tdxquant",
            }
        except Exception as e:
            logger.error("TdxQuant quote failed for %s: %s", code, e)
            return None
        finally:
            self._tdx_lock.release()

    # ---- K线 ----

    def _get_kline_tdxquant(self, code: str, period: str, limit: int) -> list[dict]:
        """从 TdxQuant 获取K线数据（线程安全）"""
        tq = self.get_tdxquant()
        if tq is None:
            return []

        if not self._tdx_lock.acquire(timeout=5):
            logger.warning("TDX lock acquire timeout for kline %s, skip to fallback", code)
            return []
        try:
            period_map = {
                "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                "60m": "1h", "1h": "1h", "daily": "1d", "weekly": "1w",
                "1d": "1d", "1w": "1w", "1M": "1M", "monthly": "1M"
            }
            tdx_period = period_map.get(period, "1d")
            tdx_code = self._convert_to_tdx_code(code)

            data = tq.get_market_data(
                stock_list=[tdx_code],
                period=tdx_period,
                count=limit,
                dividend_type='none',
                fill_data=True
            )

            if not data or "Close" not in data:
                return []

            close_df = data.get("Close")
            if close_df is None or close_df.empty:
                return []

            results = []
            for idx in close_df.index:
                results.append({
                    "date": str(idx)[:10],
                    "open": safe_float(data["Open"].loc[idx, tdx_code]) if "Open" in data else None,
                    "close": safe_float(data["Close"].loc[idx, tdx_code]) if "Close" in data else None,
                    "high": safe_float(data["High"].loc[idx, tdx_code]) if "High" in data else None,
                    "low": safe_float(data["Low"].loc[idx, tdx_code]) if "Low" in data else None,
                    "volume": safe_int(data["Volume"].loc[idx, tdx_code]) if "Volume" in data else None,
                    "amount": safe_float(data["Amount"].loc[idx, tdx_code]) if "Amount" in data else None,
                    "source": "tdxquant",
                })
            return results
        except Exception as e:
            logger.error("TdxQuant kline failed for %s: %s", code, e)
            return []
        finally:
            self._tdx_lock.release()

    # ---- 股票信息 ----

    def get_stock_info_tdxquant(self, code: str, field_list: list = None) -> Optional[dict]:
        """从 TdxQuant 获取股票基本信息"""
        tq = self.get_tdxquant()
        if tq is None:
            return None
        try:
            tdx_code = self._convert_to_tdx_code(code)
            fields = field_list if field_list else []
            result = tq.get_stock_info(stock_code=tdx_code, field_list=fields)
            if not result or result.get("ErrorId") != "0":
                return None
            return {
                "code": code,
                "name": result.get("Name", ""),
                "industry": result.get("J_hy", ""),
                "listDate": result.get("J_start", ""),
                "totalShares": result.get("J_zgb", ""),
                "floatShares": result.get("ActiveCapital", ""),
                "province": result.get("J_addr", ""),
                "totalAssets": result.get("J_zzc", ""),
                "netAssets": result.get("J_jzc", ""),
                "eps": result.get("J_mgsy", ""),
                "bvps": result.get("J_mgjzc", ""),
                "belongHS300": result.get("BelongHS300", "") == "1",
                "belongHSGT": result.get("BelongHSGT", "") == "1",
                "isIndex": result.get("IsZS", "") == "1",
                "raw": result,
                "source": "tdxquant",
            }
        except Exception as e:
            safe_stderr_print(f"[DataSource] TdxQuant get_stock_info failed: {e}")
            return None

    def get_stock_info_priority_tdx(self, code: str) -> Optional[dict]:
        """优先从 TDX 获取股票信息，返回标准化格式"""
        info = self.get_stock_info_tdxquant(code)
        if not info:
            return None
        quote = self.get_realtime_quote(code)
        price = safe_float(quote.get("price")) if quote else None
        eps = safe_float(info.get("eps"))
        bvps = safe_float(info.get("bvps"))
        total_shares = safe_float(info.get("totalShares"))
        pe_ratio = (price / eps) if (price and eps and eps > 0) else None
        pb_ratio = (price / bvps) if (price and bvps and bvps > 0) else None
        market_cap = (price * total_shares * 10000) if (price and total_shares) else None
        list_date = info.get("listDate") or ""
        if list_date and len(list_date) >= 8:
            list_date = f"{list_date[:4]}-{list_date[4:6]}-{list_date[6:8]}"
        return {
            "code": code,
            "name": info.get("name") or "",
            "industry": info.get("industry") or "",
            "pe_ratio": pe_ratio,
            "pb_ratio": pb_ratio,
            "market_cap": market_cap,
            "list_date": list_date or None,
        }

    # ---- 除权因子 ----

    def get_divid_factors_tdxquant(self, code: str, start_time: str = "", end_time: str = "") -> list:
        """从 TdxQuant 获取除权除息因子数据"""
        tq = self.get_tdxquant()
        if tq is None:
            return []
        try:
            tdx_code = self._convert_to_tdx_code(code)
            df = tq.get_divid_factors(stock_code=tdx_code, start_time=start_time, end_time=end_time)
            if df is None or df.empty:
                return []
            results = []
            for idx, row in df.iterrows():
                results.append({
                    "date": str(idx)[:10] if hasattr(idx, '__str__') else str(idx),
                    "type": safe_int(row.get("Type")),
                    "bonus": safe_float(row.get("Bonus")),
                    "allotPrice": safe_float(row.get("AllotPrice")),
                    "shareBonus": safe_float(row.get("ShareBonus")),
                    "allotment": safe_float(row.get("Allotment")),
                    "source": "tdxquant",
                })
            return results
        except Exception as e:
            safe_stderr_print(f"[DataSource] TdxQuant get_divid_factors failed: {e}")
            return []

    # ---- 板块 ----

    def get_sector_list_tdxquant(self) -> list:
        """从 TdxQuant 获取A股板块代码列表"""
        tq = self.get_tdxquant()
        if tq is None:
            return []
        try:
            result = tq.get_sector_list()
            if result is None:
                return []
            return result
        except Exception as e:
            safe_stderr_print(f"[DataSource] TdxQuant get_sector_list failed: {e}")
            return []

    def get_stock_list_in_sector_tdxquant(self, block_code: str, block_type: int = 0) -> list:
        """从 TdxQuant 获取板块成分股"""
        tq = self.get_tdxquant()
        if tq is None:
            return []
        try:
            result = tq.get_stock_list_in_sector(block_code, block_type=block_type)
            if result is None:
                return []
            return result
        except Exception as e:
            safe_stderr_print(f"[DataSource] TdxQuant get_stock_list_in_sector failed: {e}")
            return []

    # ---- 订阅 ----

    def subscribe_hq_tdxquant(self, stock_list: list, callback=None) -> dict:
        """订阅行情更新 (TdxQuant)"""
        tq = self.get_tdxquant()
        if tq is None:
            return {"success": False, "message": "TdxQuant 不可用"}
        try:
            tdx_codes = [self._convert_to_tdx_code(code) for code in stock_list[:100]]
            result = tq.subscribe_hq(stock_list=tdx_codes, callback=callback)
            if result and result.get("ErrorId") == "0":
                return {
                    "success": True,
                    "message": result.get("Error", "订阅成功"),
                    "run_id": result.get("run_id"),
                    "source": "tdxquant",
                }
            else:
                return {
                    "success": False,
                    "message": result.get("Error", "订阅失败") if result else "订阅失败",
                }
        except Exception as e:
            safe_stderr_print(f"[DataSource] TdxQuant subscribe_hq failed: {e}")
            return {"success": False, "message": str(e)}
