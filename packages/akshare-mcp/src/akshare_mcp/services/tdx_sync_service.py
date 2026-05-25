"""TDX sync service — Phase 2 of TDX migration.

Provides 13 incremental sync tasks for the 8 TDX-specific tables and the
``stocks`` / ``market_blocks`` / ``block_stocks`` shared tables. Each task is
idempotent; a failure of one task should not block the others.

The service is invoked from ``data_sync_scheduler.run_once`` after the
existing K-line / financial phases (so we keep the legacy pipeline as a
fallback during the cut-over).

Tasks:
- sync_stock_basic              全 A 股票名称 → ``stocks``
- sync_sector_basic             板块列表 + 成分 → ``market_blocks`` / ``block_stocks``
- sync_relation                 板块归属 → ``tdx_relation``
- sync_more_info                88 字段每日快照 → ``tdx_stock_extra``
- sync_consensus                GO 一致预期 → ``tdx_consensus``
- sync_gpjy_daily               个股 GP 字段（按 _by_date 取最新）→ ``tdx_gpjy_daily``
- sync_bkjy_daily               板块 BK 字段 → ``tdx_bkjy_daily``
- sync_scjy_daily               市场 SC 字段 → ``tdx_scjy_daily``
- sync_kzz_basic                可转债基础数据 → ``tdx_kzz_basic``
- sync_ipo_events               新股新债申购 → ``events`` 表
- sync_divid_events             分红配股 → ``events`` 表（增量）
- sync_financial_pro            专业财务 (FN) → ``tdx_financial_pro``
- sync_trading_dates            交易日历 → ``trading_dates``
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, date
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)


# 默认 GP/BK/SC/FN 字段集合（取信号最强、字段最稳定的子集；
# 全字段同步可通过 .env 覆盖）
#
# 注意：通达信"股票数据包"是付费功能。免费版本下 GP/BK/SC 仅以下子集
# 实测能返回真值（probe_tdx_all + probe_shapes 实测）。其他字段（龙虎榜、
# 融资融券明细、陆股通、大宗交易等）需购买股票数据包。
# 用 ``TDX_SYNC_GP_FIELDS / TDX_SYNC_BK_FIELDS / TDX_SYNC_SC_FIELDS``
# 环境变量覆盖；或通过 ``TDX_SYNC_FREE_TIER=0`` 关闭"仅免费字段"过滤。
FREE_GP_FIELDS = ["GP03", "GP11", "GP12", "GP13", "GP25", "GP36"]
FULL_GP_FIELDS = [
    "GP01", "GP02", "GP03", "GP04", "GP06", "GP07", "GP11", "GP12", "GP13",
    "GP14", "GP15", "GP16", "GP21", "GP24", "GP25", "GP31", "GP42",
]

FREE_BK_FIELDS = ["BK9", "BK12", "BK13", "BK17"]   # 涨跌家数 / 涨停家数 / 跌停家数 / 开盘成交
FULL_BK_FIELDS = [
    "BK5", "BK6", "BK7", "BK9", "BK10", "BK11", "BK12",
    "BK15", "BK16", "BK17", "BK18", "BK19",
]

FREE_SC_FIELDS = ["SC01", "SC02", "SC20", "SC25", "SC36"]
FULL_SC_FIELDS = [
    "SC01", "SC02", "SC03", "SC04", "SC11", "SC15", "SC16", "SC17",
    "SC20", "SC23", "SC25", "SC27", "SC28", "SC30", "SC31", "SC34",
    "SC38", "SC42",
]


def _resolve_field_set(env_key: str, free: list, full: list) -> list:
    """根据 env 选择字段集合：``TDX_SYNC_<KIND>_FIELDS`` 优先，
    否则 ``TDX_SYNC_FREE_TIER=1``（默认）= 免费集；``=0`` = 完整集。"""
    explicit = os.getenv(env_key, "").strip()
    if explicit:
        return [t.strip() for t in explicit.split(",") if t.strip()]
    if os.getenv("TDX_SYNC_FREE_TIER", "1") in ("0", "false", "no"):
        return list(full)
    return list(free)


DEFAULT_GP_FIELDS = _resolve_field_set("TDX_SYNC_GP_FIELDS", FREE_GP_FIELDS, FULL_GP_FIELDS)
DEFAULT_BK_FIELDS = _resolve_field_set("TDX_SYNC_BK_FIELDS", FREE_BK_FIELDS, FULL_BK_FIELDS)
DEFAULT_SC_FIELDS = _resolve_field_set("TDX_SYNC_SC_FIELDS", FREE_SC_FIELDS, FULL_SC_FIELDS)

# 项目内常用的 FN 字段（参照 TDX_DATA_SOURCE_MIGRATION_PLAN.md 附录 A）
DEFAULT_FN_FIELDS = [
    "FN1",    # 基本每股收益
    "FN4",    # 每股净资产
    "FN6",    # 净资产收益率
    "FN40",   # 资产总计
    "FN63",   # 负债合计
    "FN72",   # 所有者权益合计
    "FN107",  # 经营现金流净额
    "FN159",  # 流动比率
    "FN160",  # 速动比率
    "FN183",  # 营收增长率
    "FN184",  # 净利润增长率
    "FN197",  # 净资产收益率
    "FN199",  # 销售净利率
    "FN202",  # 销售毛利率
    "FN206",  # 扣非净利润
    "FN210",  # 资产负债率
    "FN230",  # 营业收入
    "FN232",  # 归母净利润
    "FN238",  # 总股本
    "FN239",  # 流通A股
    "FN308",  # 近一年归母净利润
    "FN319",  # TTM 营业总收入
]

# GO 字段：完整 47 项（一次性单点查询，开销小）
DEFAULT_GO_FIELDS = [f"GO{i}" for i in range(1, 48)]


def _split_value_pairs(payload: Any) -> Tuple[Optional[float], Optional[float]]:
    """tqcenter 的 GP/BK/SC ``Value`` 通常是长度 2 的字符串列表。"""
    if isinstance(payload, list):
        if len(payload) == 0:
            return None, None
        a = payload[0] if len(payload) >= 1 else None
        b = payload[1] if len(payload) >= 2 else None
        return _to_float(a), _to_float(b)
    if isinstance(payload, dict):
        return _to_float(payload.get("Value")), None
    return _to_float(payload), None


def _to_float(val: Any) -> Optional[float]:
    if val is None or val == "" or val == "--":
        return None
    try:
        v = float(val)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


class TdxSyncService:
    """13 个 TDX sync 任务的协调器。

    设计原则：
    - 每个任务独立 try/except，单任务失败不影响其它
    - 任务返回 ``{"task": str, "ok": bool, "stats": dict, "error": Optional[str]}``
    - 支持选择性跳过（``TDX_SYNC_DISABLE=task1,task2``）
    """

    def __init__(self,
                 universe: Optional[List[str]] = None,
                 limit_consensus: int = 200,
                 limit_more_info: int = 500,
                 limit_gpjy: int = 200,
                 limit_financial: int = 50,
                 limit_kzz: int = 200,
                 limit_relation: int = 200):
        self.universe = list(universe or [])
        self.limit_consensus = limit_consensus
        self.limit_more_info = limit_more_info
        self.limit_gpjy = limit_gpjy
        self.limit_financial = limit_financial
        self.limit_kzz = limit_kzz
        self.limit_relation = limit_relation
        # ``sync_financial_pro`` 依赖通达信"专业财务数据"包（付费功能）。
        # 默认禁用以免每次同步都报错；用户购买并下载完毕后通过设置
        # ``TDX_SYNC_ENABLE_PRO_FIN=1`` 主动启用。
        default_disabled = set()
        if os.getenv("TDX_SYNC_ENABLE_PRO_FIN", "0") not in ("1", "true", "yes"):
            default_disabled.add("sync_financial_pro")
        env_disabled = {
            t.strip() for t in os.getenv("TDX_SYNC_DISABLE", "").split(",") if t.strip()
        }
        self.disabled = default_disabled | env_disabled

    # ------------------------------------------------------------------
    # 调度入口
    # ------------------------------------------------------------------

    async def run_all(self) -> Dict[str, Any]:
        from ..storage import get_db
        db = get_db()

        results: List[Dict[str, Any]] = []
        tasks = [
            ("sync_trading_dates", self._sync_trading_dates),
            ("sync_stock_basic", self._sync_stock_basic),
            ("sync_quote_snapshots", self._sync_quote_snapshots),
            ("sync_index_klines", self._sync_index_klines),
            ("sync_sector_basic", self._sync_sector_basic),
            ("sync_more_info", self._sync_more_info),
            ("sync_consensus", self._sync_consensus),
            ("sync_relation", self._sync_relation),
            ("sync_gpjy_daily", self._sync_gpjy_daily),
            ("sync_bkjy_daily", self._sync_bkjy_daily),
            ("sync_scjy_daily", self._sync_scjy_daily),
            ("sync_kzz_basic", self._sync_kzz_basic),
            ("sync_ipo_events", self._sync_ipo_events),
            ("sync_divid_events", self._sync_divid_events),
            ("sync_financial_pro", self._sync_financial_pro),
            ("sync_basic_financial", self._sync_basic_financial),
            ("sync_stock_fund_flow", self._sync_stock_fund_flow),
            ("sync_derived_factory_market_data", self._sync_derived_factory_market_data),
            ("sync_external_gap_data", self._sync_external_gap_data),
            ("record_tdx_data_completeness", self._record_tdx_data_completeness),
        ]
        for name, fn in tasks:
            if name in self.disabled:
                results.append({"task": name, "ok": True, "skipped": True})
                continue
            started = datetime.now()
            try:
                stats = await fn(db)
                results.append({
                    "task": name, "ok": True,
                    "stats": stats or {},
                    "elapsed_sec": round((datetime.now() - started).total_seconds(), 2),
                })
            except Exception as exc:
                logger.exception("[TdxSync] %s failed", name)
                results.append({
                    "task": name, "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "elapsed_sec": round((datetime.now() - started).total_seconds(), 2),
                })

        ok = sum(1 for r in results if r.get("ok") and not r.get("skipped"))
        skipped = sum(1 for r in results if r.get("skipped"))
        failed = sum(1 for r in results if not r.get("ok"))
        return {
            "summary": {"ok": ok, "skipped": skipped, "failed": failed,
                         "total": len(tasks)},
            "tasks": results,
        }

    # ------------------------------------------------------------------
    # 1. trading_dates
    # ------------------------------------------------------------------

    async def _sync_trading_dates(self, db) -> Dict[str, Any]:
        from ..data_source import data_source

        start = (datetime.now().replace(month=1, day=1)).strftime("%Y%m%d")
        end = datetime.now().strftime("%Y%m%d")
        result = await asyncio.to_thread(
            data_source.get_trading_dates,
            "SH", start, end, -1,
        )
        if not result.get("success"):
            return {"inserted": 0, "reason": result.get("message", "")}
        dates: List[str] = result.get("data") or []
        inserted = 0
        async with db.acquire() as conn:
            for d in dates:
                if not d or len(d) != 8 or not d.isdigit():
                    continue
                await conn.execute(
                    """
                    INSERT INTO trading_dates (trade_date, exchange, is_open)
                    VALUES ($1, 'SSE', 1)
                    ON CONFLICT (trade_date) DO UPDATE SET is_open = 1
                    """,
                    d,
                )
                inserted += 1
        return {"inserted": inserted, "first": dates[0] if dates else None,
                "last": dates[-1] if dates else None}

    # ------------------------------------------------------------------
    # 2. stock_basic
    # ------------------------------------------------------------------

    async def _sync_stock_basic(self, db) -> Dict[str, Any]:
        from ..data_source import data_source

        rows = await asyncio.to_thread(data_source.get_tdx_stock_list, "5", 1)
        if not rows:
            return {"inserted": 0}
        inserted = 0
        async with db.acquire() as conn:
            for item in rows:
                code = item.get("full_code") or item.get("code") or ""
                name = item.get("name") or ""
                if not code or not name:
                    continue
                # 兼容 stocks 表中的 stock_code / market 列
                # market: 后缀 -> 'SH' / 'SZ' / 'BJ'
                market = code.split(".")[-1] if "." in code else ""
                bare = code.split(".")[0] if "." in code else code
                await conn.execute(
                    """
                    INSERT INTO stocks (stock_code, stock_name, market, updated_at)
                    VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                    ON CONFLICT (stock_code) DO UPDATE SET
                        stock_name = EXCLUDED.stock_name,
                        market = EXCLUDED.market,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    bare, name, market,
                )
                inserted += 1
        return {"inserted": inserted}

    # ------------------------------------------------------------------
    # 3. quote snapshots
    # ------------------------------------------------------------------

    async def _sync_quote_snapshots(self, db) -> Dict[str, Any]:
        """Sync latest quote snapshots into stock_quotes from TDX only."""
        from ..data_source import data_source

        limit = int(os.getenv("TDX_SYNC_QUOTE_LIMIT", str(self.limit_more_info)))
        codes = await self._resolve_universe(db, limit)
        updated = 0
        tried = 0
        for code in codes:
            tried += 1
            try:
                raw = await asyncio.to_thread(data_source.get_realtime_quote, code)
                quote = raw.get("data") if isinstance(raw, dict) and raw.get("success") else raw
                if not isinstance(quote, dict) or not quote:
                    continue
                bare = str(code or quote.get("code") or "").split(".", 1)[0]
                payload = {
                    "code": bare,
                    "name": quote.get("name") or quote.get("stock_name"),
                    "price": _to_float(quote.get("price") or quote.get("last") or quote.get("close")),
                    "change_amt": _to_float(quote.get("change_amt") or quote.get("change")),
                    "change_pct": _to_float(quote.get("change_pct") or quote.get("pct_chg")),
                    "open": _to_float(quote.get("open")),
                    "high": _to_float(quote.get("high")),
                    "low": _to_float(quote.get("low")),
                    "prev_close": _to_float(quote.get("prev_close") or quote.get("pre_close")),
                    "volume": int(_to_float(quote.get("volume")) or 0),
                    "amount": _to_float(quote.get("amount")),
                    "pe": _to_float(quote.get("pe") or quote.get("pe_ttm")),
                    "pb": _to_float(quote.get("pb")),
                    "mkt_cap": _to_float(quote.get("mkt_cap") or quote.get("market_cap")),
                }
                if payload["price"] is None:
                    continue
                await db.save_quote(payload)
                updated += 1
            except Exception as exc:
                logger.debug("[TdxSync] quote %s: %s", code, exc)
        return {"updated": updated, "tried": tried}

    # ------------------------------------------------------------------
    # 4. index klines
    # ------------------------------------------------------------------

    async def _sync_index_klines(self, db) -> Dict[str, Any]:
        """Sync common index daily bars into kline_1d using prefixed codes."""
        from ..data_source import data_source

        index_map = {
            "sh000001": "000001.SH",
            "sh000300": "399300.SZ",
            "sz399001": "399001.SZ",
            "sz399006": "399006.SZ",
        }
        limit = int(os.getenv("TDX_SYNC_INDEX_KLINE_LIMIT", "500"))
        updated = 0
        rejected = 0
        for stored_code, tdx_code in index_map.items():
            try:
                raw_rows = await asyncio.to_thread(data_source.get_kline, tdx_code, "daily", limit)
            except Exception as exc:
                logger.debug("[TdxSync] index kline %s: %s", stored_code, exc)
                continue
            rows: list[dict] = []
            for item in list(raw_rows or []):
                if not isinstance(item, dict):
                    continue
                row = dict(item)
                row["code"] = stored_code
                rows.append(row)
            if not rows:
                continue
            try:
                report = await db.save_klines(stored_code, rows)
                updated += int(report.get("accepted_count") or 0)
                rejected += int(report.get("rejected_count") or 0)
            except Exception as exc:
                logger.debug("[TdxSync] save index kline %s: %s", stored_code, exc)
        return {"updated": updated, "rejected": rejected, "index_count": len(index_map)}

    # ------------------------------------------------------------------
    # 5. sector_basic
    # ------------------------------------------------------------------

    async def _sync_sector_basic(self, db) -> Dict[str, Any]:
        from ..data_source import data_source

        sectors = await asyncio.to_thread(data_source.get_sector_list, 1)
        if not sectors:
            return {"sectors": 0, "members": 0}

        # 行业一级用 list 16；其他自定义板块来自 880xxx
        # 这里把所有 880xxx 板块同步到 market_blocks，成份股同步到 block_stocks
        wrote_blocks = 0
        wrote_members = 0
        async with db.acquire() as conn:
            for sec in sectors:
                bcode = sec.get("block_code") or ""
                bname = sec.get("block_name") or ""
                if not bcode:
                    continue
                # block_type 这里用 "tdx" 占位（具体 type 由 tdx_relation 给）
                await conn.execute(
                    """
                    INSERT INTO market_blocks (block_code, block_name, block_type, updated_at)
                    VALUES ($1, $2, 'tdx', CURRENT_TIMESTAMP)
                    ON CONFLICT (block_code, block_type) DO UPDATE SET
                        block_name = EXCLUDED.block_name,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    bcode, bname,
                )
                wrote_blocks += 1

            # 拉前 N 个板块的成分（避免一次性几千次调用）
            limit = int(os.getenv("TDX_SYNC_SECTOR_LIMIT", "60"))
            for sec in sectors[:limit]:
                bcode = sec.get("block_code") or ""
                if not bcode:
                    continue
                try:
                    members = await asyncio.to_thread(
                        data_source.get_stock_list_in_sector, bcode, 0, 0
                    )
                except Exception:
                    members = []
                for m in members or []:
                    code = m if isinstance(m, str) else (m.get("Code") if isinstance(m, dict) else "")
                    if not code:
                        continue
                    bare = code.split(".")[0] if "." in code else code
                    await conn.execute(
                        """
                        INSERT INTO block_stocks (block_code, stock_code, updated_at)
                        VALUES ($1, $2, CURRENT_TIMESTAMP)
                        ON CONFLICT (block_code, stock_code) DO UPDATE SET
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        bcode, bare,
                    )
                    wrote_members += 1
        return {"sectors": wrote_blocks, "members": wrote_members}

    # ------------------------------------------------------------------
    # 4. more_info → tdx_stock_extra
    # ------------------------------------------------------------------

    async def _sync_more_info(self, db) -> Dict[str, Any]:
        """每日 88 字段快照同步 → tdx_stock_extra；同时把 PE/PB/市值/换手率/股息率
        回写到 ``stocks`` 表，让工厂的 ``list_stock_universe`` 直接命中。"""
        from ..data_source import data_source

        codes = await self._resolve_universe(db, self.limit_more_info)
        ok_count = 0
        for code in codes:
            try:
                info = await asyncio.to_thread(data_source.get_more_info, code)
                if not info:
                    continue
                await db.save_tdx_stock_extra(code, info)
                # 同步 stocks 表（PE/PB/市值/换手率/股息率/行业代理）
                bare = code.split(".")[0] if "." in code else code
                pe_ttm = _to_float(info.get("StaticPE_TTM"))
                pb_mrq = _to_float(info.get("PB_MRQ"))
                zsz = _to_float(info.get("Zsz"))         # 总市值（亿元）
                turnover = _to_float(info.get("fHSL"))   # 换手率
                div_yield = _to_float(info.get("DYRatio"))  # 股息率
                async with db.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE stocks SET
                            pe_ratio = COALESCE($2, pe_ratio),
                            pb_ratio = COALESCE($3, pb_ratio),
                            market_cap = COALESCE($4, market_cap),
                            turnover_rate = COALESCE($5, turnover_rate),
                            dividend_yield = COALESCE($6, dividend_yield),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE stock_code = $1
                        """,
                        bare, pe_ttm, pb_mrq,
                        # 把"亿元"转成"元"以匹配 stocks.market_cap 的项目约定
                        zsz * 1e8 if zsz is not None else None,
                        turnover, div_yield,
                    )
                ok_count += 1
            except Exception as exc:
                logger.debug("[TdxSync] more_info %s: %s", code, exc)
        return {"updated": ok_count, "tried": len(codes)}

    # ------------------------------------------------------------------
    # 5. consensus → tdx_consensus
    # ------------------------------------------------------------------

    async def _sync_consensus(self, db) -> Dict[str, Any]:
        from ..data_source import data_source

        codes = await self._resolve_universe(db, self.limit_consensus)
        if not codes:
            return {"updated": 0}
        # 一次性多股查询；失败时分小批
        chunk = 50
        ok_count = 0
        snapshot_date = datetime.now().strftime("%Y-%m-%d")
        for i in range(0, len(codes), chunk):
            batch = codes[i:i + chunk]
            try:
                data = await asyncio.to_thread(
                    data_source.get_gp_one_data, batch, DEFAULT_GO_FIELDS
                )
            except Exception as exc:
                logger.debug("[TdxSync] consensus batch %s: %s", i, exc)
                continue
            for code, payload in (data or {}).items():
                if code == "ErrorId":
                    continue
                try:
                    await db.save_tdx_consensus(code, payload, snapshot_date=snapshot_date)
                    ok_count += 1
                except Exception:
                    continue
        return {"updated": ok_count}

    # ------------------------------------------------------------------
    # 6. relation → tdx_relation
    # ------------------------------------------------------------------

    async def _sync_relation(self, db) -> Dict[str, Any]:
        from ..data_source import data_source

        codes = await self._resolve_universe(db, self.limit_relation)
        ok_count = 0
        for code in codes:
            try:
                rel = await asyncio.to_thread(data_source.get_relation, code)
                if not rel:
                    continue
                await db.save_tdx_relation(code, rel)
                # ── 把"行业"板块名作为 stocks.industry 兜底（rs_hyname 缺失时保命） ──
                bare = code.split(".")[0] if "." in code else code
                first_industry = next(
                    (r.get("block_name") for r in rel
                     if r.get("block_type") == "行业" and r.get("block_name")),
                    None,
                )
                first_concept = next(
                    (r.get("block_name") for r in rel
                     if r.get("block_type") == "概念" and r.get("block_name")),
                    None,
                )
                first_region = next(
                    (r.get("block_name") for r in rel
                     if r.get("block_type") == "地区" and r.get("block_name")),
                    None,
                )
                if first_industry or first_concept or first_region:
                    async with db.acquire() as conn:
                        await conn.execute(
                            """
                            UPDATE stocks SET
                                industry = COALESCE(NULLIF(industry, ''), $2),
                                sector = COALESCE(NULLIF(sector, ''), $3),
                                tdx_industry = COALESCE(NULLIF(tdx_industry, ''), $2),
                                tdx_region = COALESCE(NULLIF(tdx_region, ''), $4),
                                updated_at = CURRENT_TIMESTAMP
                            WHERE stock_code = $1
                            """,
                            bare,
                            first_industry, first_industry, first_region,
                        )
                ok_count += 1
            except Exception as exc:
                logger.debug("[TdxSync] relation %s: %s", code, exc)
        return {"updated": ok_count}

    # ------------------------------------------------------------------
    # 7. gpjy_daily → tdx_gpjy_daily
    # ------------------------------------------------------------------

    async def _sync_gpjy_daily(self, db) -> Dict[str, Any]:
        from ..data_source import data_source

        codes = await self._resolve_universe(db, self.limit_gpjy)
        if not codes or not DEFAULT_GP_FIELDS:
            return {"updated": 0}
        # 实测：``get_gpjy_value_by_date(0,0)`` 全部返 ``--``；
        # 用 ``get_gpjy_value`` + 历史范围（最近 30 天）才能拿到真值。
        from datetime import datetime as _dt, timedelta as _td
        end = _dt.now().strftime("%Y%m%d")
        start = (_dt.now() - _td(days=30)).strftime("%Y%m%d")

        chunk = 30
        ok_codes = 0
        for i in range(0, len(codes), chunk):
            batch = codes[i:i + chunk]
            try:
                data = await asyncio.to_thread(
                    data_source.get_gpjy_value,
                    batch, DEFAULT_GP_FIELDS, start, end,
                )
            except Exception as exc:
                logger.debug("[TdxSync] gpjy batch %s: %s", i, exc)
                continue
            for code, payload in (data or {}).items():
                if code == "ErrorId" or not isinstance(payload, dict):
                    continue
                rows: list[dict] = []
                for gp_code, items in payload.items():
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        date_val = item.get("Date")
                        a, b = _split_value_pairs(item.get("Value"))
                        if a is None and b is None:
                            continue
                        rows.append({
                            "trade_date": date_val,
                            "gp_code": gp_code,
                            "value_a": a, "value_b": b,
                        })
                if rows:
                    try:
                        await db.save_tdx_gpjy_daily(code, rows)
                        ok_codes += 1
                    except Exception:
                        continue
        return {"updated": ok_codes}

    # ------------------------------------------------------------------
    # 8. bkjy_daily → tdx_bkjy_daily
    # ------------------------------------------------------------------

    async def _sync_bkjy_daily(self, db) -> Dict[str, Any]:
        from ..data_source import data_source

        # 拉所有 880xxx 板块代码；限制并发量
        sectors = await asyncio.to_thread(data_source.get_sector_list, 0)
        block_codes = [s.get("block_code") for s in sectors if s.get("block_code", "").startswith("88")]
        block_codes = block_codes[:int(os.getenv("TDX_SYNC_BKJY_LIMIT", "600"))]
        if not block_codes or not DEFAULT_BK_FIELDS:
            return {"updated": 0}
        # 实测：``_by_date(0,0)`` 全 ``--``，需用历史范围调用
        from datetime import datetime as _dt, timedelta as _td
        end = _dt.now().strftime("%Y%m%d")
        start = (_dt.now() - _td(days=30)).strftime("%Y%m%d")

        chunk = 20
        ok_blocks = 0
        for i in range(0, len(block_codes), chunk):
            batch = block_codes[i:i + chunk]
            try:
                data = await asyncio.to_thread(
                    data_source.get_bkjy_value,
                    batch, DEFAULT_BK_FIELDS, start, end,
                )
            except Exception as exc:
                logger.debug("[TdxSync] bkjy batch %s: %s", i, exc)
                continue
            for bcode, payload in (data or {}).items():
                if bcode == "ErrorId" or not isinstance(payload, dict):
                    continue
                rows: list[dict] = []
                for bk_code, items in payload.items():
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        date_val = item.get("Date")
                        a, b = _split_value_pairs(item.get("Value"))
                        if a is None and b is None:
                            continue
                        rows.append({
                            "trade_date": date_val,
                            "bk_code": bk_code,
                            "value_a": a, "value_b": b,
                        })
                if rows:
                    try:
                        await db.save_tdx_bkjy_daily(bcode, rows)
                        ok_blocks += 1
                    except Exception:
                        continue
        return {"updated": ok_blocks, "tried": len(block_codes)}

    # ------------------------------------------------------------------
    # 9. scjy_daily → tdx_scjy_daily
    # ------------------------------------------------------------------

    async def _sync_scjy_daily(self, db) -> Dict[str, Any]:
        from ..data_source import data_source

        if not DEFAULT_SC_FIELDS:
            return {"updated": 0}
        # 实测：``_by_date(0,0)`` 返 ``--``，用历史范围（最近 30 天）
        from datetime import datetime as _dt, timedelta as _td
        end = _dt.now().strftime("%Y%m%d")
        start = (_dt.now() - _td(days=30)).strftime("%Y%m%d")

        try:
            data = await asyncio.to_thread(
                data_source.get_scjy_value,
                DEFAULT_SC_FIELDS, start, end,
            )
        except Exception as exc:
            return {"updated": 0, "error": str(exc)}
        if not isinstance(data, dict):
            return {"updated": 0}
        rows: list[dict] = []
        for sc_code, items in data.items():
            if sc_code == "ErrorId" or not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                date_val = item.get("Date")
                a, b = _split_value_pairs(item.get("Value"))
                if a is None and b is None:
                    continue
                rows.append({"trade_date": date_val, "sc_code": sc_code,
                             "value_a": a, "value_b": b})
        if rows:
            await db.save_tdx_scjy_daily(rows)
        return {"updated": len(rows)}

    # ------------------------------------------------------------------
    # 10. kzz_basic → tdx_kzz_basic
    # ------------------------------------------------------------------

    async def _sync_kzz_basic(self, db) -> Dict[str, Any]:
        from ..data_source import data_source

        listings = await asyncio.to_thread(data_source.get_tdx_stock_list, "32", 1)
        listings = listings[:self.limit_kzz]
        ok_count = 0
        for item in listings:
            code = item.get("full_code") or item.get("code") or ""
            if not code:
                continue
            try:
                cb = await asyncio.to_thread(data_source.get_cb_info, code)
                payload = (cb or {}).get("data") or {}
                if not payload:
                    continue
                # 把 market_data.get_cb_info 返回的契约形式转回 tdx_storage 期望
                # （tdx_storage 期望与 tdx_tqcenter.get_kzz_info 同构）
                kz_payload = {
                    "kzz_code": payload.get("KZZCode") or item.get("code") or code.split(".")[0],
                    "stock_code": payload.get("HSCode"),
                    "set_code": payload.get("set_code"),
                    "convert_price": payload.get("ZGPrice"),
                    "current_rate": payload.get("CurRate"),
                    "remain_size_wan": payload.get("RestScope"),
                    "putback_price": payload.get("PutBack"),
                    "force_redeem_price": payload.get("ForceRedeem"),
                    "convert_date": payload.get("ZGDate"),
                    "end_price": payload.get("EndPrice"),
                    "end_date": payload.get("EndDate"),
                    "convert_rate": payload.get("ZGRate"),
                    "real_value": payload.get("RealValue"),
                    "expire_yield": payload.get("ExpireYield"),
                    "kzz_score": payload.get("KZZScore"),
                    "stock_score": payload.get("HSScore"),
                    "redeem_date": payload.get("RedeemDate"),
                    "redeem_price": payload.get("RedeemPrice"),
                    "put_date": payload.get("PutDate"),
                    "put_price": payload.get("PutPrice"),
                    "convert_code": payload.get("ZGCode"),
                    "stock_price": payload.get("AGPrice"),
                    "kzz_price": payload.get("KZZPrice"),
                    "premium_rate": payload.get("KZZYj"),
                    "convert_value": payload.get("ZGValue"),
                }
                await db.save_tdx_kzz(kz_payload)
                ok_count += 1
            except Exception as exc:
                logger.debug("[TdxSync] kzz %s: %s", code, exc)
        return {"updated": ok_count, "tried": len(listings)}

    # ------------------------------------------------------------------
    # 11. ipo_events
    # ------------------------------------------------------------------

    async def _sync_ipo_events(self, db) -> Dict[str, Any]:
        from ..data_source import data_source

        try:
            res = await asyncio.to_thread(data_source.get_ipo_info, 2, 1)
        except Exception as exc:
            return {"inserted": 0, "error": str(exc)}
        if not res.get("success"):
            return {"inserted": 0, "reason": res.get("message")}
        items = res.get("data") or []
        inserted = 0
        async with db.acquire() as conn:
            for it in items:
                sg_date = (it.get("SGDate") or "").replace("-", "")
                code = it.get("code") or it.get("SGCode") or ""
                if not sg_date or not code:
                    continue
                title = f"{it.get('type', '')}申购：{it.get('name', '')} ({code})"
                desc = (
                    f"sg_code={it.get('SGCode')}  sg_price={it.get('SGPrice')}  "
                    f"max_sg={it.get('MaxSG')}  pe_issue={it.get('PE_Issue')}"
                )
                try:
                    # events 表实际 schema: (code, event_type, event_date, title, description)
                    # 用 code+event_type+event_date 作为软主键去重
                    existing = await conn.fetchval(
                        "SELECT 1 FROM events WHERE code=$1 AND event_type='tdx_ipo' AND event_date=$2",
                        code, sg_date,
                    )
                    if existing:
                        continue
                    await conn.execute(
                        """
                        INSERT INTO events (code, event_type, event_date, title, description)
                        VALUES ($1, 'tdx_ipo', $2, $3, $4)
                        """,
                        code, sg_date, title, desc,
                    )
                    inserted += 1
                except Exception as exc:
                    logger.debug("[TdxSync] events upsert ipo %s: %s", code, exc)
        return {"inserted": inserted}

    # ------------------------------------------------------------------
    # 12. divid_events — 增量分红
    # ------------------------------------------------------------------

    async def _sync_divid_events(self, db) -> Dict[str, Any]:
        from ..data_source import data_source

        codes = await self._resolve_universe(db, self.limit_relation)
        # 仅同步今年的分红
        year_start = datetime.now().strftime("%Y0101")
        year_end = datetime.now().strftime("%Y%m%d")
        inserted = 0
        async with db.acquire() as conn:
            for code in codes:
                try:
                    rows = await asyncio.to_thread(
                        data_source.get_divid_factors,
                        code, year_start, year_end,
                    )
                except Exception:
                    continue
                bare = code.split(".")[0] if "." in code else code
                for r in rows or []:
                    d = (r.get("date") or "").replace("-", "")
                    if not d:
                        continue
                    title = f"分红/送配：{bare}"
                    desc = (
                        f"type={r.get('type')}  bonus={r.get('bonus')}  "
                        f"share_bonus={r.get('share_bonus')}  allotment={r.get('allotment')}  "
                        f"allot_price={r.get('allot_price')}"
                    )
                    try:
                        exists = await conn.fetchval(
                            "SELECT 1 FROM events WHERE code=$1 AND event_type='tdx_dividend' AND event_date=$2",
                            bare, d,
                        )
                        if exists:
                            continue
                        await conn.execute(
                            """
                            INSERT INTO events (code, event_type, event_date, title, description)
                            VALUES ($1, 'tdx_dividend', $2, $3, $4)
                            """,
                            bare, d, title, desc,
                        )
                        inserted += 1
                    except Exception as exc:
                        logger.debug("[TdxSync] events upsert divid %s: %s", code, exc)
        return {"inserted": inserted}

    # ------------------------------------------------------------------
    # 13. financial_pro → tdx_financial_pro
    # ------------------------------------------------------------------

    async def _sync_financial_pro(self, db) -> Dict[str, Any]:
        from ..data_source import data_source

        codes = await self._resolve_universe(db, self.limit_financial)
        # 只取最近一年
        year_start = (datetime.now().replace(month=1, day=1)).strftime("%Y0101")
        ok_codes = 0
        chunk = 5
        for i in range(0, len(codes), chunk):
            batch = codes[i:i + chunk]
            try:
                data = await asyncio.to_thread(
                    data_source.get_financial_data,
                    batch, DEFAULT_FN_FIELDS,
                    year_start, "",
                    "announce_time",
                )
            except Exception as exc:
                logger.debug("[TdxSync] financial batch %s: %s", i, exc)
                continue
            # data: {code: DataFrame} 或 {code: list[dict]}
            for code, df_or_rows in (data or {}).items():
                if code == "ErrorId":
                    continue
                rows = self._extract_fn_rows(df_or_rows)
                if not rows:
                    continue
                try:
                    await db.save_tdx_financial(code, rows)
                    ok_codes += 1
                except Exception:
                    continue
        return {"updated": ok_codes, "tried": len(codes)}

    # ------------------------------------------------------------------
    # 14. basic_financial → 通过 get_stock_info 把基础财务写入 ``financials`` 表
    #
    # tqcenter 的 ``get_financial_data`` 需要客户端单独下载"专业财务数据
    # 包"。在该数据包未下载时所有 FN 字段返回 ``"--"``。本任务用 always-on
    # 的 ``get_stock_info`` 接口拿基础财务（营收、净利润、ROE、EPS、BVPS、
    # 资产负债等），覆盖大多数业务需求；专业财务包到位后，
    # ``_sync_financial_pro`` 会自动给出更细粒度的 FN 字段。
    # ------------------------------------------------------------------

    async def _sync_basic_financial(self, db) -> Dict[str, Any]:
        from ..data_source import tdx_tqcenter as _tq

        codes = await self._resolve_universe(db, self.limit_financial)
        if not codes:
            return {"updated": 0}

        from datetime import datetime as _dt

        def _report_date(half_year_flag: Any) -> str:
            """根据 J_HalfYearFlag 与当前年份推断报告期 YYYY-MM-DD。"""
            try:
                m = int(half_year_flag) if half_year_flag is not None else 12
            except (TypeError, ValueError):
                m = 12
            year = _dt.now().year
            if m == 3:
                return f"{year}-03-31"
            if m == 6:
                return f"{year}-06-30"
            if m == 9:
                return f"{year}-09-30"
            return f"{year - 1}-12-31"

        ok_count = 0
        async with db.acquire() as conn:
            for code in codes:
                try:
                    info = await asyncio.to_thread(_tq.get_stock_info, code)
                except Exception as exc:
                    logger.debug("[TdxSync] basic_financial %s: %s", code, exc)
                    continue
                if not info or not isinstance(info, dict):
                    continue

                bare = code.split(".")[0] if "." in code else code

                # ── 1. 把行业 / 地区 / 上市日 / 股本回写到 stocks 表 ──
                industry = (info.get("rs_hyname") or "").strip() or None
                region = (info.get("tdx_dyname") or "").strip() or None
                # J_start 是 'YYYYMMDD' 整数字符串
                list_date_raw = (info.get("J_start") or "").strip()
                list_date = None
                if list_date_raw and list_date_raw.isdigit() and len(list_date_raw) == 8:
                    list_date = f"{list_date_raw[:4]}-{list_date_raw[4:6]}-{list_date_raw[6:]}"
                total_shares_wan = _to_float(info.get("J_zgb"))
                float_shares_wan = _to_float(info.get("ActiveCapital"))
                # 万股 → 股
                total_shares = total_shares_wan * 10000 if total_shares_wan else None
                float_shares = float_shares_wan * 10000 if float_shares_wan else None

                await conn.execute(
                    """
                    UPDATE stocks SET
                        industry = COALESCE($2, industry),
                        sector = COALESCE($2, sector),
                        list_date = COALESCE($3, list_date),
                        tdx_industry = COALESCE($2, tdx_industry),
                        tdx_region = COALESCE($4, tdx_region),
                        tdx_listed_date = COALESCE($3, tdx_listed_date),
                        tdx_total_shares = COALESCE($5, tdx_total_shares),
                        tdx_float_shares = COALESCE($6, tdx_float_shares),
                        list_status = COALESCE(list_status, 'L'),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE stock_code = $1
                    """,
                    bare, industry, list_date, region,
                    total_shares, float_shares,
                )

                # ── 2. 计算并写 financials（原逻辑） ──

                # 量纲：J_yysy/J_jly/J_zzc 等单位为"万元"，转回元
                revenue = _to_float(info.get("J_yysy"))
                if revenue is not None:
                    revenue *= 10000
                net_profit = _to_float(info.get("J_jly"))
                if net_profit is not None:
                    net_profit *= 10000
                total_assets = _to_float(info.get("J_zzc"))  # 万元
                total_liab = _to_float(info.get("J_zzc")) and _to_float(info.get("J_jzc"))
                # 实际：负债 = 总资产 - 净资产
                if total_assets is not None:
                    jzc = _to_float(info.get("J_jzc"))
                    debt_ratio = (1 - jzc / total_assets) * 100 if jzc is not None and total_assets > 0 else None
                else:
                    debt_ratio = None

                gross_margin = None
                yyly = _to_float(info.get("J_yyly"))   # 营业利润
                yysy_raw = _to_float(info.get("J_yysy"))  # 万元
                yycb = _to_float(info.get("J_yycb"))   # 营业成本
                if yysy_raw and yysy_raw > 0 and yycb is not None:
                    gross_margin = (yysy_raw - yycb) / yysy_raw * 100
                net_margin = None
                if yysy_raw and yysy_raw > 0 and _to_float(info.get("J_jly")) is not None:
                    net_margin = _to_float(info.get("J_jly")) / yysy_raw * 100

                payload = {
                    "stock_code": bare,
                    "report_date": _report_date(info.get("J_HalfYearFlag")),
                    "revenue": revenue,
                    "net_profit": net_profit,
                    "gross_margin": gross_margin,
                    "net_margin": net_margin,
                    "debt_ratio": debt_ratio,
                    "current_ratio": None,
                    "eps": _to_float(info.get("J_mgsy")),
                    "roe": _to_float(info.get("J_jyl")),
                    "bvps": _to_float(info.get("J_mgjzc")),
                    "roa": None,
                    "revenue_growth": None,
                    "profit_growth": None,
                }
                try:
                    await conn.execute(
                        """
                        INSERT INTO financials (
                            stock_code, report_date, revenue, net_profit,
                            gross_margin, net_margin, debt_ratio, current_ratio,
                            eps, roe, bvps, roa, revenue_growth, profit_growth,
                            updated_at
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                            CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (stock_code, report_date) DO UPDATE SET
                            revenue=EXCLUDED.revenue,
                            net_profit=EXCLUDED.net_profit,
                            gross_margin=EXCLUDED.gross_margin,
                            net_margin=EXCLUDED.net_margin,
                            debt_ratio=EXCLUDED.debt_ratio,
                            current_ratio=EXCLUDED.current_ratio,
                            eps=EXCLUDED.eps,
                            roe=EXCLUDED.roe,
                            bvps=EXCLUDED.bvps,
                            roa=EXCLUDED.roa,
                            revenue_growth=EXCLUDED.revenue_growth,
                            profit_growth=EXCLUDED.profit_growth,
                            updated_at=CURRENT_TIMESTAMP
                        """,
                        payload["stock_code"], payload["report_date"],
                        payload["revenue"], payload["net_profit"],
                        payload["gross_margin"], payload["net_margin"],
                        payload["debt_ratio"], payload["current_ratio"],
                        payload["eps"], payload["roe"], payload["bvps"],
                        payload["roa"], payload["revenue_growth"], payload["profit_growth"],
                    )
                    ok_count += 1
                except Exception as exc:
                    logger.debug("[TdxSync] financials upsert %s: %s", code, exc)
        return {"updated": ok_count, "tried": len(codes)}

    # ------------------------------------------------------------------
    # 15. stock_fund_flow → 个股资金流
    #
    # 来源：tdx_stock_extra 的 Zjl_HB (主力净流入,万元) + Zjl (主买净额,万元)
    # 设计：避免重复调 SDK，直接从 sync_more_info 已入库的快照衍生写入
    # stock_fund_flow 表，工厂层 (factor_prompt_builder /
    # decision_quant_builder) 的 db-first 路径就能命中。
    #
    # **重要**：免费版通达信在收盘后 Zjl/Zjl_HB 字段返回 0；盘中调才有真值。
    # L2 逐笔成交（TotalBVol/TotalSVol/L2TicNum）需要 L2 行情授权才能拿。
    # 因此本任务在盘后跑出来全是 0，工厂只在盘中跑同步时才有有效数据。
    # ------------------------------------------------------------------

    async def _sync_stock_fund_flow(self, db) -> Dict[str, Any]:
        """从 tdx_stock_extra 的当日主力净流入字段衍生 stock_fund_flow。"""
        from datetime import datetime as _dt

        snapshot_date = _dt.now().strftime("%Y-%m-%d")
        ok_count = 0
        async with db.acquire() as conn:
            # 拉当日 tdx_stock_extra（含 zjl_hb 主力净流入）
            rows = await conn.fetch(
                """
                SELECT t.code, t.zjl_hb, s.stock_name AS name
                FROM tdx_stock_extra t
                LEFT JOIN stocks s ON s.stock_code = t.code
                WHERE t.trade_date = $1
                  AND t.zjl_hb IS NOT NULL
                """,
                snapshot_date,
            )
            for row in rows:
                row = dict(row)
                code_full = row.get("code") or ""
                if not code_full:
                    continue
                bare = code_full.split(".")[0] if "." in code_full else code_full
                main_net_inflow_yuan = (row.get("zjl_hb") or 0.0) * 10000  # 万元 → 元
                try:
                    await conn.execute(
                        """
                        INSERT INTO stock_fund_flow (
                            code, trade_date, name,
                            main_net_inflow, main_inflow_percent,
                            super_large_net_inflow, large_net_inflow,
                            middle_net_inflow, small_net_inflow,
                            source, updated_at
                        ) VALUES (
                            $1, $2, $3, $4, NULL,
                            NULL, NULL, NULL, NULL,
                            'tqcenter.more_info', CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (code, trade_date) DO UPDATE SET
                            name = EXCLUDED.name,
                            main_net_inflow = EXCLUDED.main_net_inflow,
                            source = EXCLUDED.source,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        bare, snapshot_date, row.get("name") or "",
                        float(main_net_inflow_yuan),
                    )
                    ok_count += 1
                except Exception as exc:
                    logger.debug("[TdxSync] stock_fund_flow %s: %s", bare, exc)
        return {"updated": ok_count}

    # ------------------------------------------------------------------
    # 辅助：解析 universe + 解析 FN payload
    # ------------------------------------------------------------------

    async def _sync_derived_factory_market_data(self, db) -> Dict[str, Any]:
        """Derive factory-facing DB tables from TDX raw tables."""
        north = await self._derive_north_fund_flow(db)
        margin_market = await self._derive_margin_market_flow(db)
        margin_detail = await self._derive_margin_detail(db)
        internals = await self._derive_factory_market_internals(db)
        return {
            "north_fund_flow": north,
            "margin_market_flow": margin_market,
            "margin_detail": margin_detail,
            "strategy_factory_market_internals": internals,
        }

    async def _derive_north_fund_flow(self, db) -> Dict[str, Any]:
        inserted = 0
        async with db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    trade_date,
                    MAX(CASE WHEN sc_code = 'SC02' THEN value_a END) AS hgt,
                    MAX(CASE WHEN sc_code = 'SC20' THEN value_a END) AS sgt
                FROM tdx_scjy_daily
                WHERE sc_code IN ('SC02', 'SC20')
                GROUP BY trade_date
                ORDER BY trade_date DESC
                LIMIT 120
                """
            )
            for row in rows:
                hgt = _to_float(row.get("hgt"))
                sgt = _to_float(row.get("sgt"))
                if hgt is None and sgt is None:
                    continue
                north_money = (hgt or 0.0) + (sgt or 0.0)
                await conn.execute(
                    """
                    INSERT INTO north_fund_flow (
                        trade_date, north_money, south_money, net_amount,
                        hgt, sgt, updated_at
                    ) VALUES ($1, $2, NULL, $2, $3, $4, CURRENT_TIMESTAMP)
                    ON CONFLICT (trade_date) DO UPDATE SET
                        north_money = EXCLUDED.north_money,
                        net_amount = EXCLUDED.net_amount,
                        hgt = EXCLUDED.hgt,
                        sgt = EXCLUDED.sgt,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    row.get("trade_date"),
                    north_money,
                    hgt,
                    sgt,
                )
                inserted += 1
        if hasattr(db, "save_tdx_data_completeness"):
            await db.save_tdx_data_completeness(
                "north_fund_flow",
                "ok" if inserted else "missing",
                row_count=inserted,
                detail={"source": "tdx_scjy_daily", "fields": ["SC02", "SC20"]},
            )
        return {"updated": inserted}

    async def _derive_margin_market_flow(self, db) -> Dict[str, Any]:
        inserted = 0
        async with db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    trade_date,
                    MAX(CASE WHEN sc_code = 'SC01' THEN value_a END) AS rzye,
                    MAX(CASE WHEN sc_code = 'SC25' THEN value_a END) AS rzmre,
                    MAX(CASE WHEN sc_code = 'SC25' THEN value_b END) AS rqmcl
                FROM tdx_scjy_daily
                WHERE sc_code IN ('SC01', 'SC25')
                GROUP BY trade_date
                ORDER BY trade_date DESC
                LIMIT 120
                """
            )
            for row in rows:
                rzye = _to_float(row.get("rzye"))
                rzmre = _to_float(row.get("rzmre"))
                rqmcl = _to_float(row.get("rqmcl"))
                if rzye is None and rzmre is None and rqmcl is None:
                    continue
                await conn.execute(
                    """
                    INSERT INTO margin_market_flow (
                        trade_date, exchange_id, rzye, rzmre, rzche,
                        rqye, rqmcl, rqyl, rzrqye, updated_at
                    ) VALUES ($1, 'TDX', $2, $3, NULL, NULL, $4, NULL, $2, CURRENT_TIMESTAMP)
                    ON CONFLICT (trade_date, exchange_id) DO UPDATE SET
                        rzye = EXCLUDED.rzye,
                        rzmre = EXCLUDED.rzmre,
                        rqmcl = EXCLUDED.rqmcl,
                        rzrqye = EXCLUDED.rzrqye,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    row.get("trade_date"),
                    rzye,
                    rzmre,
                    rqmcl,
                )
                inserted += 1
        if hasattr(db, "save_tdx_data_completeness"):
            await db.save_tdx_data_completeness(
                "margin_market_flow",
                "ok" if inserted else "missing",
                row_count=inserted,
                detail={"source": "tdx_scjy_daily", "fields": ["SC01", "SC25"]},
            )
        return {"updated": inserted}

    async def _derive_margin_detail(self, db) -> Dict[str, Any]:
        inserted = 0
        async with db.acquire() as conn:
            latest_date = await conn.fetchval("SELECT MAX(trade_date) FROM tdx_gpjy_daily")
            if latest_date is None:
                if hasattr(db, "save_tdx_data_completeness"):
                    await db.save_tdx_data_completeness(
                        "margin_detail",
                        "missing",
                        row_count=0,
                        detail={"source": "tdx_gpjy_daily", "reason": "no_rows"},
                    )
                return {"updated": 0}
            rows = await conn.fetch(
                """
                SELECT
                    code,
                    MAX(CASE WHEN gp_code = 'GP03' THEN value_a END) AS rzye,
                    MAX(CASE WHEN gp_code = 'GP11' THEN value_a END) AS rzmre,
                    MAX(CASE WHEN gp_code = 'GP11' THEN value_b END) AS rzche,
                    MAX(CASE WHEN gp_code = 'GP12' THEN value_a END) AS rqye,
                    MAX(CASE WHEN gp_code = 'GP12' THEN value_b END) AS rqmcl,
                    MAX(CASE WHEN gp_code = 'GP13' THEN value_a END) AS rzrqye
                FROM tdx_gpjy_daily
                WHERE trade_date = $1
                  AND gp_code IN ('GP03', 'GP11', 'GP12', 'GP13')
                GROUP BY code
                """,
                latest_date,
            )
            for row in rows:
                values = {
                    "rzye": _to_float(row.get("rzye")),
                    "rzmre": _to_float(row.get("rzmre")),
                    "rzche": _to_float(row.get("rzche")),
                    "rqye": _to_float(row.get("rqye")),
                    "rqmcl": _to_float(row.get("rqmcl")),
                    "rzrqye": _to_float(row.get("rzrqye")),
                }
                if all(v is None for v in values.values()):
                    continue
                code = str(row.get("code") or "")
                ts_code = code if "." in code else f"{code}.TDX"
                await conn.execute(
                    """
                    INSERT INTO margin_detail (
                        trade_date, ts_code, rzye, rqye, rzmre,
                        rqyl, rzche, rqchl, rqmcl, rzrqye, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, NULL, $6, NULL, $7, $8, CURRENT_TIMESTAMP)
                    ON CONFLICT (trade_date, ts_code) DO UPDATE SET
                        rzye = EXCLUDED.rzye,
                        rqye = EXCLUDED.rqye,
                        rzmre = EXCLUDED.rzmre,
                        rzche = EXCLUDED.rzche,
                        rqmcl = EXCLUDED.rqmcl,
                        rzrqye = EXCLUDED.rzrqye,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    latest_date,
                    ts_code,
                    values["rzye"],
                    values["rqye"],
                    values["rzmre"],
                    values["rzche"],
                    values["rqmcl"],
                    values["rzrqye"],
                )
                inserted += 1
        if hasattr(db, "save_tdx_data_completeness"):
            await db.save_tdx_data_completeness(
                "margin_detail",
                "ok" if inserted else "missing",
                as_of_date=latest_date,
                row_count=inserted,
                detail={"source": "tdx_gpjy_daily", "fields": ["GP03", "GP11", "GP12", "GP13"]},
            )
        return {"updated": inserted}

    async def _derive_factory_market_internals(self, db) -> Dict[str, Any]:
        snapshot_date = datetime.now().strftime("%Y-%m-%d")
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """
                WITH ranked AS (
                    SELECT
                        code, time, close, volume,
                        ROW_NUMBER() OVER (PARTITION BY code ORDER BY time DESC) AS rn
                    FROM kline_1d
                    WHERE code NOT LIKE 'sh%' AND code NOT LIKE 'sz399%'
                ),
                pivoted AS (
                    SELECT
                        code,
                        MAX(CASE WHEN rn = 1 THEN close END) AS c1,
                        MAX(CASE WHEN rn = 1 THEN volume END) AS v1,
                        MAX(CASE WHEN rn = 5 THEN close END) AS c5,
                        MAX(CASE WHEN rn = 20 THEN close END) AS c20,
                        AVG(CASE WHEN rn BETWEEN 2 AND 20 THEN volume END) AS vavg
                    FROM ranked
                    WHERE rn <= 20
                    GROUP BY code
                )
                SELECT
                    COUNT(*) AS symbol_count,
                    SUM(CASE WHEN c5 IS NOT NULL AND c1 > c5 THEN 1 ELSE 0 END) AS trend_up_count,
                    SUM(CASE WHEN c5 IS NOT NULL AND c1 < c5 THEN 1 ELSE 0 END) AS trend_down_count,
                    AVG(CASE WHEN c5 > 0 THEN (c1 - c5) / c5 * 100 END) AS avg_return_5d,
                    AVG(CASE WHEN c20 > 0 THEN (c1 - c20) / c20 * 100 END) AS avg_return_20d,
                    AVG(CASE WHEN vavg > 0 THEN v1 / vavg END) AS avg_volume_ratio
                FROM pivoted
                WHERE c1 IS NOT NULL
                """
            )
        payload = dict(row or {})
        symbol_count = int(payload.get("symbol_count") or 0)
        trend_up = int(payload.get("trend_up_count") or 0)
        trend_down = int(payload.get("trend_down_count") or 0)
        breadth_score = ((trend_up - trend_down) / symbol_count) if symbol_count else 0.0
        sector_summary = {}
        if hasattr(db, "get_sector_rotation_summary"):
            try:
                sector_summary = await db.get_sector_rotation_summary(limit=5)
            except Exception:
                sector_summary = {}
        margin_summary = {}
        if hasattr(db, "get_recent_margin_summary"):
            try:
                margin_summary = await db.get_recent_margin_summary(days=10, sample_limit=10)
            except Exception:
                margin_summary = {}
        item = {
            "snapshot_date": snapshot_date,
            "engine": "tdx_db_derived_v1",
            "symbol_count": symbol_count,
            "trend_up_count": trend_up,
            "trend_down_count": trend_down,
            "avg_return_5d": round(float(payload.get("avg_return_5d") or 0.0), 4),
            "avg_return_20d": round(float(payload.get("avg_return_20d") or 0.0), 4),
            "avg_volume_ratio": round(float(payload.get("avg_volume_ratio") or 1.0), 4),
            "breadth_score": round(float(breadth_score), 6),
            "margin_proxy_5d_change_pct": (margin_summary or {}).get("margin_balance_change_5d") or 0.0,
            "hot_sectors": list((sector_summary or {}).get("hot_sectors") or []),
            "cold_sectors": list((sector_summary or {}).get("cold_sectors") or []),
            "metadata": {
                "source": "tdx_sync_service",
                "sector_source": (sector_summary or {}).get("source"),
                "margin_source": (margin_summary or {}).get("source"),
            },
        }
        saved = {}
        if hasattr(db, "save_factory_market_internal_snapshot"):
            saved = await db.save_factory_market_internal_snapshot(item)
        if hasattr(db, "save_tdx_data_completeness"):
            await db.save_tdx_data_completeness(
                "strategy_factory_market_internals",
                "ok" if symbol_count else "missing",
                as_of_date=snapshot_date,
                row_count=1 if symbol_count else 0,
                detail={"source": "kline_1d+tdx_bkjy_daily+margin_market_flow"},
            )
        return {"updated": 1 if saved else 0, "symbol_count": symbol_count}

    async def _sync_external_gap_data(self, db) -> Dict[str, Any]:
        from .external_gap_sync_service import ExternalGapSyncService

        svc = ExternalGapSyncService(universe=self.universe)
        return await svc.run_all(db)

    async def _record_tdx_data_completeness(self, db) -> Dict[str, Any]:
        if not hasattr(db, "save_tdx_data_completeness"):
            return {"updated": 0, "reason": "adapter_missing_method"}
        specs = [
            ("stock_quotes", [("stock_quotes", "time", "")]),
            ("index_klines", [("kline_1d", "time", "WHERE code IN ('sh000001','sh000300','sz399001','sz399006')")]),
            ("north_fund_flow", [("north_fund_flow", "trade_date", "")]),
            ("margin_market_flow", [("margin_market_flow", "trade_date", "")]),
            ("margin_detail", [("margin_detail", "trade_date", "")]),
            ("stock_fund_flow", [("stock_fund_flow", "trade_date", "")]),
            ("strategy_factory_market_internals", [("strategy_factory_market_internals", "snapshot_date", "")]),
            ("sync_sector_basic", [
                ("market_blocks", "updated_at", ""),
                ("block_stocks", "updated_at", ""),
            ]),
            ("sync_relation", [("tdx_relation", "updated_at", "")]),
        ]
        stale_after_days = {
            "stock_quotes": 5,
            "index_klines": 10,
            "north_fund_flow": 10,
            "margin_market_flow": 10,
            "margin_detail": 10,
            "stock_fund_flow": 10,
            "strategy_factory_market_internals": 10,
            "sync_sector_basic": 10,
            "sync_relation": 10,
        }
        updated = 0
        snapshots: list[tuple[str, list[dict], int, Any, dict, list[dict]]] = []
        async with db.acquire() as conn:
            for key, table_specs in specs:
                total_rows = 0
                latest_as_of = None
                table_details: list[dict] = []
                source_rows: list[dict] = []
                for table, date_col, where_clause in table_specs:
                    row = await conn.fetchrow(
                        f"SELECT COUNT(*) AS row_count, MAX({date_col}) AS as_of_date FROM {table} {where_clause}"
                    )
                    row_count = int((row or {}).get("row_count") or 0)
                    as_of_date = (row or {}).get("as_of_date")
                    total_rows += row_count
                    if as_of_date and (latest_as_of is None or str(as_of_date) > str(latest_as_of)):
                        latest_as_of = as_of_date
                    table_details.append({
                        "table": table,
                        "date_column": date_col,
                        "where": where_clause,
                        "row_count": row_count,
                        "as_of_date": as_of_date,
                    })
                    columns = await conn.fetch("SELECT name FROM pragma_table_info($1)", table)
                    column_names = {str(item.get("name") or "") for item in columns}
                    if "source" in column_names:
                        source_priority_expr = (
                            "COALESCE(source_priority, 'unknown')"
                            if "source_priority" in column_names
                            else "'unknown'"
                        )
                        group_by_expr = "source, source_priority" if "source_priority" in column_names else "source"
                        source_rows.extend(
                            dict(item, table=table)
                            for item in await conn.fetch(
                                f"""
                                SELECT
                                    COALESCE(source, 'unknown') AS source,
                                    {source_priority_expr} AS source_priority,
                                    COUNT(*) AS row_count,
                                    MAX({date_col}) AS as_of_date
                                FROM {table}
                                {where_clause}
                                GROUP BY {group_by_expr}
                                ORDER BY row_count DESC
                                """
                            )
                        )
                previous = {}
                if total_rows == 0 and hasattr(db, "get_tdx_data_completeness"):
                    try:
                        previous = await db.get_tdx_data_completeness(key)
                    except Exception:
                        previous = {}
                snapshots.append((key, table_details, total_rows, latest_as_of, previous, source_rows))
        for key, table_details, row_count, as_of_date, previous, source_rows in snapshots:
            status = "ok" if row_count else "missing"
            if len(table_details) == 1:
                only = table_details[0]
                detail = {
                    "table": only["table"],
                    "date_column": only["date_column"],
                    "where": only["where"],
                }
            else:
                detail = {"tables": table_details}
            if source_rows:
                detail["sources"] = source_rows
            if row_count and as_of_date and key in stale_after_days:
                try:
                    as_of = datetime.strptime(str(as_of_date)[:10], "%Y-%m-%d").date()
                    age_days = (datetime.now().date() - as_of).days
                    if age_days > int(stale_after_days[key]):
                        status = "stale"
                        detail["age_days"] = age_days
                        detail["stale_after_days"] = int(stale_after_days[key])
                except Exception:
                    pass
            previous_detail = previous.get("detail") if isinstance(previous, dict) else {}
            if row_count == 0 and isinstance(previous, dict) and previous.get("status") == "source_unavailable":
                status = "source_unavailable"
                if isinstance(previous_detail, dict) and previous_detail:
                    detail["previous"] = previous_detail
            await db.save_tdx_data_completeness(
                key,
                status,
                as_of_date=as_of_date,
                row_count=row_count,
                detail=detail,
            )
            updated += 1
        return {"updated": updated}

    async def _resolve_universe(self, db, limit: int) -> List[str]:
        if self.universe:
            return self.universe[:limit]
        from ..data_source import data_source

        # 优先用 stocks 表；没有就 HS300
        try:
            async with db.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT stock_code FROM stocks ORDER BY stock_code LIMIT $1",
                    int(limit),
                )
            if rows:
                out: List[str] = []
                for row in rows:
                    code = row.get("stock_code") or ""
                    # 加后缀：用 tdx_tqcenter.normalize 规则
                    from ..data_source.tdx_tqcenter import _normalize_code
                    out.append(_normalize_code(code))
                return out
        except Exception:
            pass

        # fallback: HS300 list
        hs300 = await asyncio.to_thread(data_source.get_tdx_stock_list, "23", 1)
        return [item.get("full_code") or item.get("code") for item in hs300[:limit]]

    @staticmethod
    def _extract_fn_rows(payload: Any) -> List[dict]:
        """将 ``get_financial_data`` 返回的单只 stock 的子结构拆成 long-format。"""
        rows: List[dict] = []
        if payload is None:
            return rows
        # DataFrame: 列含 announce_time / tag_time + FN 列
        if hasattr(payload, "to_dict") and hasattr(payload, "columns"):
            try:
                df = payload
                cols = list(df.columns)
                fn_cols = [c for c in cols if isinstance(c, str) and c.upper().startswith("FN")]
                for _, row in df.iterrows():
                    report_date = row.get("tag_time") or row.get("announce_time")
                    announce_date = row.get("announce_time")
                    for fn in fn_cols:
                        v = _to_float(row.get(fn))
                        if v is None:
                            continue
                        rows.append({
                            "report_date": report_date,
                            "announce_date": announce_date,
                            "fn_code": fn.upper(),
                            "value": v,
                        })
            except Exception:
                pass
            return rows
        # dict 兜底
        if isinstance(payload, dict):
            for fn, v in payload.items():
                if not isinstance(fn, str) or not fn.upper().startswith("FN"):
                    continue
                vv = _to_float(v)
                if vv is None:
                    continue
                rows.append({
                    "report_date": datetime.now().strftime("%Y%m%d"),
                    "announce_date": datetime.now().strftime("%Y%m%d"),
                    "fn_code": fn.upper(),
                    "value": vv,
                })
        return rows


# 模块级辅助：便于 scheduler 一行接入
async def run_tdx_sync(universe: Optional[List[str]] = None) -> Dict[str, Any]:
    svc = TdxSyncService(universe=universe)
    return await svc.run_all()
