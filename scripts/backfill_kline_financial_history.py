#!/usr/bin/env python3
"""Targeted K-line + financial history backfill with resumable progress."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import akshare as ak
except ImportError:
    ak = None


ROOT = Path(__file__).resolve().parents[1]
AKSHARE_MCP_SRC = ROOT / "packages" / "akshare-mcp" / "src"
STRATEGY_FACTORY_SRC = ROOT / "packages" / "strategy-factory" / "src"

for path in (str(AKSHARE_MCP_SRC), str(STRATEGY_FACTORY_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

from akshare_mcp.data_source import data_source  # noqa: E402
from akshare_mcp.env_loader import load_mcp_env  # noqa: E402
from akshare_mcp.storage import get_db, run_with_db_cleanup  # noqa: E402


DEFAULT_STATE_PATH = ROOT / "output" / "backfill" / "kline_financial_state.json"
IP_LIMIT_HINTS = ("IP数量超限", "最大数量为2个")


def _to_ts_code(code: str) -> str:
    code = str(code).strip()
    if code.startswith("6"):
        return f"{code}.SH"
    if code.startswith(("0", "3")):
        return f"{code}.SZ"
    return f"{code}.BJ"


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip().replace(",", "")
            if not text or text.lower() in {"nan", "none", "null", "--"}:
                return None
            if text.endswith("%"):
                text = text[:-1].strip()
            value = text
        number = float(value)
        if number != number:
            return None
        return number
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    number = _safe_float(value)
    return int(number) if number is not None else None


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _is_ip_limit_error(error: Exception | str) -> bool:
    text = str(error or "").strip()
    return bool(text) and any(hint in text for hint in IP_LIMIT_HINTS)


def _to_tx_symbol(code: str) -> str | None:
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("0", "3")):
        return f"sz{code}"
    return None


def _quarter_end(dt: date) -> date:
    month = ((dt.month - 1) // 3 + 1) * 3
    if month == 3:
        return date(dt.year, 3, 31)
    if month == 6:
        return date(dt.year, 6, 30)
    if month == 9:
        return date(dt.year, 9, 30)
    return date(dt.year, 12, 31)


def _previous_stable_financial_cutoff(today: date) -> date:
    # Respect A-share disclosure windows so we only require quarters that
    # should be broadly available across the market.
    if today < date(today.year, 5, 1):
        return date(today.year - 1, 9, 30)
    if today < date(today.year, 9, 1):
        return date(today.year - 1, 12, 31)
    if today < date(today.year, 11, 1):
        return date(today.year, 6, 30)
    return date(today.year, 9, 30)


def _estimated_trading_rows(start_dt: date, end_dt: date) -> int:
    if end_dt <= start_dt:
        return 1
    return max(1, int((end_dt - start_dt).days * 0.69))


def _estimated_quarters(start_dt: date, end_dt: date) -> int:
    if end_dt < start_dt:
        return 0
    start_key = start_dt.year * 4 + ((start_dt.month - 1) // 3)
    end_key = end_dt.year * 4 + ((end_dt.month - 1) // 3)
    return max(1, end_key - start_key + 1)


@dataclass
class Candidate:
    code: str
    list_date: date | None
    kline_rows: int
    kline_min_date: date | None
    kline_max_date: date | None
    financial_rows: int
    financial_min_date: date | None
    financial_max_date: date | None
    need_kline: bool
    need_financial: bool
    kline_reason: str | None
    financial_reason: str | None


class HistoryBackfill:
    def __init__(
        self,
        *,
        years: int,
        limit: int | None,
        start_code: str | None,
        include_codes: list[str] | None,
        sleep_ms: int,
        state_path: Path,
        dry_run: bool,
    ) -> None:
        self.years = max(int(years), 1)
        self.limit = limit if limit and limit > 0 else None
        self.start_code = start_code.strip() if start_code else None
        self.include_codes = [code.strip() for code in (include_codes or []) if code.strip()]
        self.sleep_ms = max(int(sleep_ms), 0)
        self.state_path = state_path
        self.dry_run = dry_run
        self.db = get_db()
        self.ts_pro = None
        self.start_dt = datetime.now()
        self.kline_start = (self.start_dt.date() - timedelta(days=self.years * 365))
        self.kline_recent_cutoff = self.start_dt.date() - timedelta(days=2)
        self.financial_cutoff = _previous_stable_financial_cutoff(self.start_dt.date())
        self.summary: dict[str, Any] = {
            "started_at": self.start_dt.isoformat(),
            "years": self.years,
            "kline_start": self.kline_start.isoformat(),
            "kline_recent_cutoff": self.kline_recent_cutoff.isoformat(),
            "financial_cutoff": self.financial_cutoff.isoformat(),
            "processed": 0,
            "kline_success": 0,
            "kline_skipped": 0,
            "kline_fail": 0,
            "financial_success": 0,
            "financial_skipped": 0,
            "financial_fail": 0,
            "last_code": None,
            "failures": [],
        }

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{stamp}] {message}", flush=True)

    async def initialize(self) -> None:
        load_mcp_env(override=False)
        await self.db.initialize()
        self.ts_pro = data_source.get_tushare_pro()
        if self.ts_pro is None:
            raise RuntimeError("Tushare Pro unavailable; cannot backfill history")
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def _expected_kline_start(self, list_date_val: date | None) -> date:
        if list_date_val and list_date_val > self.kline_start:
            return list_date_val
        return self.kline_start

    def _needs_kline(self, row: dict[str, Any]) -> tuple[bool, str | None]:
        list_date_val = _parse_date(row.get("list_date"))
        current_min = _parse_date(row.get("kline_min_date"))
        current_max = _parse_date(row.get("kline_max_date"))
        current_rows = int(row.get("kline_rows") or 0)
        expected_start = self._expected_kline_start(list_date_val)
        expected_rows = _estimated_trading_rows(expected_start, self.kline_recent_cutoff)
        minimum_rows = max(40, int(expected_rows * 0.65))

        if current_rows <= 0:
            return True, "missing_kline_rows"
        if current_max is None or current_max < self.kline_recent_cutoff:
            return True, "stale_kline_tail"
        if current_min is None or current_min > expected_start + timedelta(days=45):
            return True, "missing_kline_head"
        if current_rows < minimum_rows:
            return True, "insufficient_kline_density"
        return False, None

    def _needs_financial(self, row: dict[str, Any]) -> tuple[bool, str | None]:
        list_date_val = _parse_date(row.get("list_date"))
        current_max = _parse_date(row.get("financial_max_date"))
        current_rows = int(row.get("financial_rows") or 0)
        effective_start = self.kline_start
        if list_date_val and list_date_val > effective_start:
            effective_start = list_date_val
        expected_quarters = _estimated_quarters(effective_start, self.financial_cutoff)
        minimum_rows = max(1, int(expected_quarters * 0.55))

        if current_rows <= 0:
            return True, "missing_financial_rows"
        if current_max is None or current_max < self.financial_cutoff:
            return True, "stale_financial_tail"
        if current_rows < minimum_rows:
            return True, "insufficient_financial_density"
        return False, None

    async def load_candidates(self) -> list[Candidate]:
        query = """
            WITH stock_base AS (
                SELECT
                    COALESCE(NULLIF(stock_code, ''), code) AS code,
                    list_date
                FROM stocks
                WHERE COALESCE(NULLIF(stock_code, ''), code) ~ '^[0-9]{6}$'
            ),
            kline_stats AS (
                SELECT
                    code,
                    COUNT(*) AS kline_rows,
                    MIN(time::date) AS kline_min_date,
                    MAX(time::date) AS kline_max_date
                FROM kline_1d
                WHERE code ~ '^[0-9]{6}$'
                GROUP BY code
            ),
            financial_stats AS (
                SELECT
                    COALESCE(NULLIF(stock_code, ''), code) AS code,
                    COUNT(*) AS financial_rows,
                    MIN(report_date::date) AS financial_min_date,
                    MAX(report_date::date) AS financial_max_date
                FROM financials
                GROUP BY COALESCE(NULLIF(stock_code, ''), code)
            )
            SELECT
                stock_base.code,
                stock_base.list_date,
                COALESCE(kline_stats.kline_rows, 0) AS kline_rows,
                kline_stats.kline_min_date,
                kline_stats.kline_max_date,
                COALESCE(financial_stats.financial_rows, 0) AS financial_rows,
                financial_stats.financial_min_date,
                financial_stats.financial_max_date
            FROM stock_base
            LEFT JOIN kline_stats ON kline_stats.code = stock_base.code
            LEFT JOIN financial_stats ON financial_stats.code = stock_base.code
            ORDER BY
                COALESCE(kline_stats.kline_rows, 0) ASC,
                COALESCE(financial_stats.financial_rows, 0) ASC,
                stock_base.list_date ASC NULLS FIRST,
                stock_base.code ASC
        """
        async with self.db.acquire() as conn:
            rows = await conn.fetch(query)

        candidates: list[Candidate] = []
        include_set = set(self.include_codes)
        for row in rows:
            item = dict(row)
            code = str(item.get("code") or "").strip()
            if not code:
                continue
            if self.start_code and code < self.start_code:
                continue
            if include_set and code not in include_set:
                continue
            need_kline, kline_reason = self._needs_kline(item)
            need_financial, financial_reason = self._needs_financial(item)
            if not need_kline and not need_financial:
                continue
            candidates.append(
                Candidate(
                    code=code,
                    list_date=_parse_date(item.get("list_date")),
                    kline_rows=int(item.get("kline_rows") or 0),
                    kline_min_date=_parse_date(item.get("kline_min_date")),
                    kline_max_date=_parse_date(item.get("kline_max_date")),
                    financial_rows=int(item.get("financial_rows") or 0),
                    financial_min_date=_parse_date(item.get("financial_min_date")),
                    financial_max_date=_parse_date(item.get("financial_max_date")),
                    need_kline=need_kline,
                    need_financial=need_financial,
                    kline_reason=kline_reason,
                    financial_reason=financial_reason,
                )
            )
            if self.limit and len(candidates) >= self.limit:
                break
        return candidates

    async def backfill_kline(self, candidate: Candidate) -> dict[str, Any]:
        start_dt = self._expected_kline_start(candidate.list_date)
        end_dt = self.start_dt.date()
        ts_code = _to_ts_code(candidate.code)
        last_reason = None
        try:
            df = self.ts_pro.daily(
                ts_code=ts_code,
                start_date=start_dt.strftime("%Y%m%d"),
                end_date=end_dt.strftime("%Y%m%d"),
            )
        except Exception as exc:
            df = None
            last_reason = str(exc)

        payload = []
        if df is not None and not df.empty:
            df = df.iloc[::-1]
            for _, row in df.iterrows():
                trade_date = str(row.get("trade_date") or "")
                if len(trade_date) < 8:
                    continue
                payload.append(
                    {
                        "date": f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}",
                        "code": candidate.code,
                        "open": _safe_float(row.get("open")),
                        "high": _safe_float(row.get("high")),
                        "low": _safe_float(row.get("low")),
                        "close": _safe_float(row.get("close")),
                        "volume": _safe_int(float(row.get("vol") or 0.0) * 100) or 0,
                        "amount": (_safe_float(row.get("amount")) or 0.0) * 1000,
                        "change_pct": _safe_float(row.get("pct_chg")),
                    }
                )

        if not payload and ak is not None:
            tx_symbol = _to_tx_symbol(candidate.code)
            if tx_symbol:
                try:
                    df_tx = ak.stock_zh_a_hist_tx(
                        symbol=tx_symbol,
                        start_date=start_dt.strftime("%Y%m%d"),
                        end_date=end_dt.strftime("%Y%m%d"),
                        adjust="",
                    )
                    if df_tx is not None and not df_tx.empty:
                        for _, row in df_tx.iterrows():
                            trade_date = str(row.get("date") or "")[:10]
                            if len(trade_date) < 10:
                                continue
                            payload.append(
                                {
                                    "date": trade_date,
                                    "code": candidate.code,
                                    "open": _safe_float(row.get("open")),
                                    "high": _safe_float(row.get("high")),
                                    "low": _safe_float(row.get("low")),
                                    "close": _safe_float(row.get("close")),
                                    "volume": _safe_int(row.get("volume")) or 0,
                                    "amount": _safe_float(row.get("amount")) or 0.0,
                                    "change_pct": _safe_float(row.get("pct_chg")),
                                }
                            )
                except Exception as exc:
                    last_reason = str(exc)

        if not payload:
            reason = last_reason or "no_valid_kline_rows"
            return {"status": "skipped", "reason": reason, "rows": 0}

        result = await self.db.save_klines(candidate.code, payload)
        accepted = int(result.get("accepted_count") or 0)
        return {
            "status": "success",
            "reason": None,
            "rows": len(payload),
            "accepted": accepted,
            "rejected": int(result.get("rejected_count") or 0),
        }

    async def backfill_financial(self, candidate: Candidate) -> dict[str, Any]:
        start_dt = self._expected_kline_start(candidate.list_date)
        ts_code = _to_ts_code(candidate.code)
        financial_rows: list[dict[str, Any]] = []
        last_reason = None
        try:
            df = self.ts_pro.fina_indicator(
                ts_code=ts_code,
                start_date=start_dt.strftime("%Y%m%d"),
                end_date=self.start_dt.strftime("%Y%m%d"),
            )
        except Exception as exc:
            df = None
            last_reason = str(exc)

        if df is not None and not df.empty:
            for _, row in df.iterrows():
                report_date = _parse_date(row.get("end_date"))
                if not report_date:
                    continue
                financial_rows.append(
                    {
                        "report_date": report_date,
                        "revenue": _safe_float(row.get("revenue")),
                        "net_profit": _safe_float(row.get("n_income")),
                        "roe": _safe_float(row.get("roe")),
                        "debt_ratio": _safe_float(row.get("debt_to_assets")),
                        "eps": _safe_float(row.get("eps")),
                        "revenue_growth": _safe_float(row.get("or_yoy")),
                        "profit_growth": _safe_float(row.get("q_profit_yoy")),
                    }
                )

        if not financial_rows and ak is not None:
            try:
                df_ak = ak.stock_financial_abstract_ths(symbol=candidate.code, indicator="按报告期")
                if df_ak is not None and not df_ak.empty:
                    for _, row in df_ak.iterrows():
                        report_date = _parse_date(str(row.get("报告期") or "").replace("-", ""))
                        if not report_date:
                            continue
                        financial_rows.append(
                            {
                                "report_date": report_date,
                                "revenue": None,
                                "net_profit": None,
                                "roe": _safe_float(row.get("净资产收益率")) or _safe_float(row.get("净资产收益率-摊薄")),
                                "debt_ratio": _safe_float(row.get("资产负债率")),
                                "eps": _safe_float(row.get("基本每股收益")),
                                "revenue_growth": None,
                                "profit_growth": None,
                            }
                        )
            except Exception as exc:
                last_reason = str(exc)

        rows_written = 0
        async with self.db.acquire() as conn:
            for item in financial_rows:
                await conn.execute(
                    """
                    INSERT INTO financials (
                        stock_code, code, report_date, revenue, net_profit, roe,
                        debt_ratio, eps, revenue_growth, profit_growth, updated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                    ON CONFLICT (stock_code, report_date) DO UPDATE SET
                        code = EXCLUDED.code,
                        revenue = EXCLUDED.revenue,
                        net_profit = EXCLUDED.net_profit,
                        roe = EXCLUDED.roe,
                        debt_ratio = EXCLUDED.debt_ratio,
                        eps = EXCLUDED.eps,
                        revenue_growth = EXCLUDED.revenue_growth,
                        profit_growth = EXCLUDED.profit_growth,
                        updated_at = NOW()
                    """,
                    candidate.code,
                    candidate.code,
                    item["report_date"],
                    item["revenue"],
                    item["net_profit"],
                    item["roe"],
                    item["debt_ratio"],
                    item["eps"],
                    item["revenue_growth"],
                    item["profit_growth"],
                )
                rows_written += 1
        if rows_written <= 0:
            reason = last_reason or "no_valid_financial_rows"
            return {"status": "skipped", "reason": reason, "rows": 0}
        return {"status": "success", "reason": None, "rows": rows_written}

    def _record_failure(self, code: str, section: str, reason: str | None) -> None:
        failures = list(self.summary.get("failures") or [])
        failures.append({"code": code, "section": section, "reason": reason})
        self.summary["failures"] = failures[:50]

    def write_state(self) -> None:
        self.state_path.write_text(
            json.dumps(self.summary, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )

    async def run(self) -> int:
        await self.initialize()
        self.log(
            f"历史回填启动: years={self.years}, kline_start={self.kline_start}, "
            f"financial_cutoff={self.financial_cutoff}, limit={self.limit or 'ALL'}"
        )
        candidates = await self.load_candidates()
        self.summary["candidate_count"] = len(candidates)

        preview = [asdict(item) for item in candidates[:10]]
        self.log(f"发现待回填代码 {len(candidates)} 只")
        if self.dry_run:
            print(json.dumps({"candidate_count": len(candidates), "preview": preview}, ensure_ascii=False, indent=2, default=_json_default))
            return 0

        for idx, candidate in enumerate(candidates, start=1):
            self.summary["processed"] = idx
            self.summary["last_code"] = candidate.code
            parts = [f"{idx}/{len(candidates)}", candidate.code]
            if candidate.need_kline:
                kline_result = await self.backfill_kline(candidate)
                parts.append(f"kline={kline_result['status']}")
                if kline_result["status"] == "success":
                    self.summary["kline_success"] += 1
                elif kline_result["status"] == "skipped":
                    self.summary["kline_skipped"] += 1
                else:
                    self.summary["kline_fail"] += 1
                    self._record_failure(candidate.code, "kline", kline_result.get("reason"))

            if candidate.need_financial:
                financial_result = await self.backfill_financial(candidate)
                parts.append(f"financial={financial_result['status']}")
                if financial_result["status"] == "success":
                    self.summary["financial_success"] += 1
                elif financial_result["status"] == "skipped":
                    self.summary["financial_skipped"] += 1
                else:
                    self.summary["financial_fail"] += 1
                    self._record_failure(candidate.code, "financial", financial_result.get("reason"))

            if idx <= 5 or idx % 25 == 0:
                self.log(" | ".join(parts))
            self.write_state()

            if self.sleep_ms > 0:
                await asyncio.sleep(self.sleep_ms / 1000)

        self.summary["finished_at"] = datetime.now().isoformat()
        self.write_state()
        self.log(
            "回填完成: "
            f"kline success/skipped/fail={self.summary['kline_success']}/{self.summary['kline_skipped']}/{self.summary['kline_fail']}, "
            f"financial success/skipped/fail={self.summary['financial_success']}/{self.summary['financial_skipped']}/{self.summary['financial_fail']}"
        )
        return 0


async def _async_main(args: argparse.Namespace) -> int:
    include_codes = []
    if args.codes:
        include_codes = [item.strip() for item in str(args.codes).replace(";", ",").split(",") if item.strip()]

    runner = HistoryBackfill(
        years=args.years,
        limit=args.limit,
        start_code=args.start_code,
        include_codes=include_codes,
        sleep_ms=args.sleep_ms,
        state_path=Path(args.state_path).expanduser().resolve(),
        dry_run=args.dry_run,
    )
    return await runner.run()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill local K-line + financial history")
    parser.add_argument("--years", type=int, default=5, help="history years to target")
    parser.add_argument("--limit", type=int, default=None, help="maximum codes to process in this round")
    parser.add_argument("--start-code", type=str, default=None, help="resume from this stock code")
    parser.add_argument("--codes", type=str, default=None, help="comma-separated stock codes to process explicitly")
    parser.add_argument("--sleep-ms", type=int, default=150, help="delay between codes in milliseconds")
    parser.add_argument("--state-path", type=str, default=str(DEFAULT_STATE_PATH), help="path to save progress JSON")
    parser.add_argument("--dry-run", action="store_true", help="only show candidate summary")
    args = parser.parse_args()
    return run_with_db_cleanup(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
