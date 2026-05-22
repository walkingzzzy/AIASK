#!/usr/bin/env python3
"""统一数据同步脚本（唯一入口）。

数据源策略与 ``data_source`` 单例保持一致：
    1. **本地 TDX vipdoc**（默认，零网络）— 通过 ``akshare_mcp.data_source.tdx_local``
    2. **Tushare Pro**（可选回退）— 仅在 ``--source tushare`` 或 ``TDX_LOCAL_ONLY=0`` 且配置了
       ``TUSHARE_TOKEN`` 时启用，覆盖 TDX 不提供的"北向资金 / 融资融券 / 龙虎榜 / 财务"。

用法：
    python scripts/db_sync.py --full                 # 全量同步（首次使用，默认 TDX）
    python scripts/db_sync.py --incremental          # 增量同步（日常，默认 TDX）
    python scripts/db_sync.py --type kline           # 仅同步 K 线
    python scripts/db_sync.py --type stocks          # 仅同步股票列表
    python scripts/db_sync.py --type calendar        # 仅同步交易日历
    python scripts/db_sync.py --type north_fund      # 仅同步北向资金（需 Tushare）
    python scripts/db_sync.py --type margin          # 仅同步融资融券（需 Tushare）
    python scripts/db_sync.py --type financial       # 仅同步财务数据（需 Tushare）
    python scripts/db_sync.py --source tdx --full    # 显式仅用 TDX 离线源
    python scripts/db_sync.py --source tushare --full# 显式仅用 Tushare（恢复旧行为）
    python scripts/db_sync.py --source auto --full   # 默认：TDX 优先 + Tushare 补齐 TDX 不提供的项
    python scripts/db_sync.py --status               # 查看同步状态

历史脚本 ``scripts/db_sync_tdx.py`` 已合并到本文件，仅作过渡期保留。
"""

import argparse
import asyncio
import os
import sys
import time
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# 设置项目路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "akshare-mcp" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "strategy-factory" / "src"))

# 设置数据库路径
DB_PATH = PROJECT_ROOT / "data" / "db" / "akshare_mcp.sqlite3"
os.environ["AKSHARE_MCP_SQLITE_PATH"] = str(DB_PATH)
os.environ["AIASK_SQLITE_PATH"] = str(DB_PATH)
os.environ["STRATEGY_FACTORY_TASK_BOARD_PATH"] = str(PROJECT_ROOT / "data" / "db" / "strategy_factory_task_board.sqlite3")

# 加载 .env
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and not os.environ.get(key):
                    os.environ[key] = val


# ─────────────────────────────────────────────────────────────────────
# 数据源初始化（TDX 必备，Tushare 可选）
# ─────────────────────────────────────────────────────────────────────

# TDX 本地源（必备）
from akshare_mcp.data_source.tdx_local import get_tdx_local_source

tdx_local = get_tdx_local_source()

# Tushare Pro（可选）
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "").strip()
TDX_LOCAL_ONLY = os.environ.get("TDX_LOCAL_ONLY", "0") == "1"

pro = None
if TUSHARE_TOKEN and not TDX_LOCAL_ONLY:
    try:
        import tushare as ts

        ts.set_token(TUSHARE_TOKEN)
        pro = ts.pro_api(TUSHARE_TOKEN)
    except Exception as exc:  # pragma: no cover - 离线环境兼容
        print(f"⚠️ Tushare 初始化失败，将仅使用 TDX 本地源: {exc}")
        pro = None


def _require_tushare(action: str) -> bool:
    if pro is not None:
        return True
    print(f"⚠️ 跳过 {action}：需要配置 TUSHARE_TOKEN（或将 TDX_LOCAL_ONLY 设为 0）")
    return False


# ─────────────────────────────────────────────────────────────────────
# 同步任务定义
# ─────────────────────────────────────────────────────────────────────

# 代表性股票（策略工厂核心依赖）
REPRESENTATIVE_STOCKS = [
    "600519", "000858", "601318", "600036", "000333",
    "002415", "600276", "601012", "300750", "000001",
]

# 全量同步的股票池（沪深300核心成分）
FULL_UNIVERSE = REPRESENTATIVE_STOCKS + [
    "601166", "600030", "601398", "600900", "000651",
    "601888", "600809", "000568", "002304", "600887",
    "601668", "600585", "000725", "002142", "600031",
    "601601", "000002", "600048", "601818", "600000",
]


def _get_all_stocks() -> list[str]:
    """获取全量 A 股代码列表。优先级：本地 SQLite → 本地 TDX vipdoc → Tushare → 默认池。"""
    # 优先从 DB 读取
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            rows = conn.execute("SELECT stock_code FROM stocks WHERE stock_code IS NOT NULL").fetchall()
            conn.close()
            if rows and len(rows) > 100:
                return [r[0] for r in rows]
        except Exception:
            pass
    # 从本地 TDX vipdoc 列出（已内置过滤，只返回 A 股个股）
    if tdx_local.has_local:
        rows = tdx_local.list_local_stocks()
        codes = [r["code"] for r in rows]
        if codes:
            return codes
    # 从 Tushare 获取
    if pro is not None:
        try:
            df = pro.stock_basic(exchange='', list_status='L', fields='symbol')
            if df is not None and not df.empty:
                return df['symbol'].tolist()
        except Exception:
            pass
    return list(FULL_UNIVERSE)


def _to_ts_code(code: str) -> str:
    """将纯数字代码转为 Tushare ts_code 格式。"""
    code = code.strip()
    if code.startswith(("6", "5", "9")):
        return f"{code}.SH"
    elif code.startswith(("4", "8")):
        return f"{code}.BJ"
    return f"{code}.SZ"


# ─────────────────────────────────────────────────────────────────────
# TDX 本地源同步函数（首选）
# ─────────────────────────────────────────────────────────────────────

async def sync_stocks_tdx() -> dict[str, Any]:
    """从 TDX 本地 vipdoc 列举股票代码并写入 stocks 表。"""
    print("  [TDX] 同步股票列表...")
    if not tdx_local.has_local:
        return {"success": False, "error": "TDX 本地目录未配置"}
    rows = tdx_local.list_local_stocks()
    if not rows:
        return {"success": False, "error": "TDX vipdoc 无可用股票"}
    market_label = {"sh": "上海", "sz": "深圳", "bj": "北京"}
    conn = sqlite3.connect(str(DB_PATH))
    n = 0
    for r in rows:
        code = r["code"]
        market = market_label.get(r["market"], r["market"])
        try:
            conn.execute(
                "INSERT OR IGNORE INTO stocks (stock_code, stock_name, market, updated_at) "
                "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (code, "", market),
            )
            n += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return {"success": True, "count": n, "source": "tdx"}


async def sync_calendar_tdx() -> dict[str, Any]:
    """通过本地上证日线日期反推交易日历。"""
    print("  [TDX] 同步交易日历...")
    dates = tdx_local.get_trading_dates()
    if not dates:
        return {"success": False, "error": "TDX 本地无交易日历数据"}
    conn = sqlite3.connect(str(DB_PATH))
    n = 0
    for d in dates:
        if len(d) != 8:
            continue
        try:
            conn.execute(
                "INSERT OR IGNORE INTO trading_dates (trade_date) VALUES (?)",
                (f"{d[:4]}-{d[4:6]}-{d[6:8]}",),
            )
            n += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return {"success": True, "count": n, "source": "tdx"}


async def sync_klines_tdx(db, codes: list[str], days: int = 2000) -> dict[str, Any]:
    """从 TDX 本地 vipdoc 灌入日线数据。"""
    print(f"  [TDX] 同步 K 线 ({len(codes)} 只股票, 每只最多 {days} 天)...")
    success = 0
    failed = 0
    failures: list[str] = []
    for code in codes:
        try:
            rows = tdx_local.get_kline(code, period="daily", limit=days)
            if not rows:
                failed += 1
                continue
            await db.save_klines(code, rows)
            success += 1
        except Exception as exc:
            failed += 1
            if len(failures) < 5:
                failures.append(f"{code}: {exc}")
    if failures:
        for f in failures:
            print(f"    ⚠️ {f}")
    return {"success": True, "synced": success, "failed": failed, "total": len(codes), "source": "tdx"}


# ─────────────────────────────────────────────────────────────────────
# Tushare 源同步函数（覆盖 TDX 不提供的项）
# ─────────────────────────────────────────────────────────────────────

async def sync_stocks(db) -> dict[str, Any]:
    """同步股票列表到 DB（Tushare Pro stock_basic）。"""
    if not _require_tushare("sync_stocks"):
        return {"success": False, "error": "tushare unavailable"}
    print("  同步股票列表...")
    try:
        df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,list_status,list_date,industry,market')
        if df is None or df.empty:
            return {"success": False, "error": "Tushare stock_basic 返回空"}

        conn = sqlite3.connect(str(DB_PATH))
        count = 0
        for _, row in df.iterrows():
            code = str(row.get("symbol") or "").strip()
            name = str(row.get("name") or "").strip()
            industry = str(row.get("industry") or "").strip()
            market = str(row.get("market") or "").strip()
            list_date = str(row.get("list_date") or "").strip()
            if code and name:
                conn.execute(
                    "INSERT OR REPLACE INTO stocks (stock_code, stock_name, market, industry, list_date, updated_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                    (code, name, market, industry, list_date),
                )
                count += 1
        conn.commit()
        conn.close()
        return {"success": True, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def sync_calendar(db) -> dict[str, Any]:
    """同步交易日历（Tushare Pro trade_cal）。"""
    if not _require_tushare("sync_calendar"):
        return {"success": False, "error": "tushare unavailable"}
    print("  同步交易日历...")
    try:
        # 同步 2000-2027 年的交易日历
        df = pro.trade_cal(exchange='SSE', start_date='20000101', end_date='20271231', is_open='1')
        if df is None or df.empty:
            return {"success": False, "error": "Tushare trade_cal 返回空"}

        conn = sqlite3.connect(str(DB_PATH))
        count = 0
        for _, row in df.iterrows():
            cal_date = str(row.get("cal_date") or "").strip()
            if cal_date and len(cal_date) == 8:
                # 转为 YYYY-MM-DD 格式
                trade_date = f"{cal_date[:4]}-{cal_date[4:6]}-{cal_date[6:8]}"
                conn.execute(
                    "INSERT OR IGNORE INTO trading_dates (trade_date) VALUES (?)",
                    (trade_date,),
                )
                count += 1
        conn.commit()
        conn.close()
        return {"success": True, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def sync_klines(db, codes: list[str], days: int = 250) -> dict[str, Any]:
    """同步 K 线数据（Tushare Pro daily）。"""
    if not _require_tushare("sync_klines"):
        return {"success": False, "synced": 0, "failed": len(codes), "error": "tushare unavailable"}
    print(f"  同步 K 线 ({len(codes)} 只股票, {days} 天)...")

    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=days * 2)).strftime('%Y%m%d')

    success = 0
    failed = 0
    for code in codes:
        try:
            ts_code = _to_ts_code(code)
            df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            if df is not None and not df.empty:
                df = df.sort_values("trade_date")
                klines = []
                for _, row in df.tail(days).iterrows():
                    td = str(row["trade_date"])
                    klines.append({
                        "date": f"{td[:4]}-{td[4:6]}-{td[6:8]}",
                        "open": float(row["open"]),
                        "close": float(row["close"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "volume": float(row.get("vol") or 0),
                        "amount": float(row.get("amount") or 0) * 1000,
                        "change_pct": float(row.get("pct_chg") or 0),
                    })
                if klines:
                    await db.save_klines(code, klines)
                    success += 1
                else:
                    failed += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            if failed <= 3:
                print(f"    ⚠️ {code}: {type(e).__name__}: {e}")
        # Tushare 限流：每分钟 200 次
        await asyncio.sleep(0.35)

    return {"success": True, "synced": success, "failed": failed}


async def sync_north_fund(db) -> dict[str, Any]:
    """同步北向资金数据（Tushare Pro moneyflow_hsgt）。"""
    if not _require_tushare("sync_north_fund"):
        return {"success": False, "error": "tushare unavailable"}
    print("  同步北向资金...")
    try:
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')

        df = pro.moneyflow_hsgt(start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return {"success": False, "error": "Tushare moneyflow_hsgt 返回空"}

        conn = sqlite3.connect(str(DB_PATH))
        count = 0
        for _, row in df.iterrows():
            trade_date_raw = str(row.get("trade_date") or "").strip()
            if not trade_date_raw or len(trade_date_raw) < 8:
                continue
            trade_date = f"{trade_date_raw[:4]}-{trade_date_raw[4:6]}-{trade_date_raw[6:8]}"
            # hgt=沪股通净买入, sgt=深股通净买入, north_money=北向合计
            hgt = float(row.get("hgt") or 0)
            sgt = float(row.get("sgt") or 0)
            north_money = float(row.get("north_money") or (hgt + sgt))

            conn.execute(
                "INSERT OR REPLACE INTO north_fund_flow (trade_date, north_money, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (trade_date, north_money),
            )
            count += 1

        conn.commit()
        conn.close()
        return {"success": True, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def sync_margin(db) -> dict[str, Any]:
    """同步融资融券数据（Tushare Pro margin）。"""
    if not _require_tushare("sync_margin"):
        return {"success": False, "error": "tushare unavailable"}
    print("  同步融资融券...")
    try:
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')

        # 获取沪市融资融券汇总
        df = pro.margin(exchange_id='SSE', start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            # 尝试深市
            df = pro.margin(exchange_id='SZSE', start_date=start_date, end_date=end_date)

        if df is None or df.empty:
            return {"success": False, "error": "Tushare margin 返回空"}

        conn = sqlite3.connect(str(DB_PATH))
        count = 0
        for _, row in df.iterrows():
            trade_date_raw = str(row.get("trade_date") or "").strip()
            if not trade_date_raw or len(trade_date_raw) < 8:
                continue
            trade_date = f"{trade_date_raw[:4]}-{trade_date_raw[4:6]}-{trade_date_raw[6:8]}"
            exchange_id = str(row.get("exchange_id") or "SSE")
            rzye = float(row.get("rzye") or 0)
            rzmre = float(row.get("rzmre") or 0)
            rzche = float(row.get("rzche") or 0)

            conn.execute(
                "INSERT OR REPLACE INTO margin_market_flow (trade_date, exchange_id, rzye, rzmre, rzche, updated_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (trade_date, exchange_id, rzye, rzmre, rzche),
            )
            count += 1

        conn.commit()
        conn.close()
        return {"success": True, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def sync_sector_flow(db) -> dict[str, Any]:
    """计算行业板块数据（从本地 stocks.industry + kline_1d 聚合）。"""
    print("  计算行业板块数据...")
    try:
        conn = sqlite3.connect(str(DB_PATH))

        # 获取最新交易日
        latest_date = conn.execute('SELECT MAX(time) FROM kline_1d').fetchone()[0]
        if not latest_date:
            conn.close()
            return {"success": False, "error": "无K线数据"}

        # 获取行业映射
        stocks = conn.execute('SELECT stock_code, industry FROM stocks WHERE industry IS NOT NULL AND industry != ""').fetchall()
        industry_map = {code: ind for code, ind in stocks}

        # 获取最新日涨跌幅
        klines = conn.execute('''
            SELECT code, change_pct, amount FROM kline_1d 
            WHERE time = ? AND change_pct IS NOT NULL
        ''', (latest_date,)).fetchall()

        from collections import defaultdict
        industry_stats = defaultdict(lambda: {'changes': [], 'amounts': [], 'count': 0})
        for code, pct, amount in klines:
            ind = industry_map.get(code)
            if ind:
                industry_stats[ind]['changes'].append(pct)
                industry_stats[ind]['amounts'].append(amount or 0)
                industry_stats[ind]['count'] += 1

        # 写入 market_blocks 表
        count = 0
        for ind, data in industry_stats.items():
            if data['changes']:
                avg_change = sum(data['changes']) / len(data['changes'])
                total_amount = sum(data['amounts'])
                # block_code 用行业名的拼音首字母或直接用名称作为唯一标识
                block_code = f"ind_{ind}"
                conn.execute(
                    """INSERT OR REPLACE INTO market_blocks 
                    (block_code, block_name, block_type, avg_change_pct, total_amount, stock_count, updated_at) 
                    VALUES (?, ?, 'industry', ?, ?, ?, CURRENT_TIMESTAMP)""",
                    (block_code, ind, avg_change, total_amount, data['count']),
                )
                count += 1

        conn.commit()
        conn.close()
        return {"success": True, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def sync_daily_basic(db, codes: list[str]) -> dict[str, Any]:
    """同步估值数据 PE/PB/市值（Tushare Pro daily_basic）→ stock_quotes 表。
    
    优化：按日期批量获取全市场数据（1 次请求 = 全市场），而非逐只股票请求。
    """
    if not _require_tushare("sync_daily_basic"):
        return {"success": False, "error": "tushare unavailable"}
    print(f"  同步估值数据（按日期批量）...")
    try:
        conn = sqlite3.connect(str(DB_PATH))
        count = 0

        # 获取最近 30 个交易日
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=45)).strftime('%Y%m%d')
        cal_df = pro.trade_cal(exchange='SSE', start_date=start_date, end_date=end_date, is_open='1')
        if cal_df is None or cal_df.empty:
            conn.close()
            return {"success": False, "error": "无法获取交易日历"}

        trade_dates = sorted(cal_df['cal_date'].tolist(), reverse=True)[:30]
        print(f"    获取 {len(trade_dates)} 个交易日的全市场估值...")

        for td in trade_dates:
            try:
                df = pro.daily_basic(trade_date=td, 
                                     fields='ts_code,trade_date,close,pe_ttm,pb,total_mv,circ_mv,turnover_rate')
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        ts_code = str(row.get("ts_code") or "")
                        code = ts_code.split(".")[0] if "." in ts_code else ts_code
                        if not code:
                            continue
                        td_str = str(row.get("trade_date") or "")
                        if len(td_str) == 8:
                            time_str = f"{td_str[:4]}-{td_str[4:6]}-{td_str[6:8]}"
                        else:
                            time_str = td_str
                        conn.execute(
                            """INSERT OR REPLACE INTO stock_quotes 
                            (time, code, name, price, pe, pb, mkt_cap, volume, amount, updated_at) 
                            VALUES (?, ?, NULL, ?, ?, ?, ?, NULL, NULL, CURRENT_TIMESTAMP)""",
                            (time_str, code, 
                             float(row.get("close") or 0) or None,
                             float(row.get("pe_ttm") or 0) or None,
                             float(row.get("pb") or 0) or None,
                             float(row.get("total_mv") or 0) or None),
                        )
                        count += 1
                    conn.commit()
            except Exception as e:
                if count == 0:
                    print(f"    ⚠️ {td}: {e}")
            await asyncio.sleep(0.5)

        conn.close()
        return {"success": True, "count": count, "dates": len(trade_dates)}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def sync_stock_fund_flow(db, codes: list[str]) -> dict[str, Any]:
    """同步个股资金流（Tushare Pro moneyflow）→ stock_fund_flow 表。"""
    if not _require_tushare("sync_stock_fund_flow"):
        return {"success": False, "error": "tushare unavailable"}
    print(f"  同步个股资金流 ({len(codes)} 只)...")
    try:
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')

        conn = sqlite3.connect(str(DB_PATH))
        count = 0

        for code in codes:
            try:
                ts_code = _to_ts_code(code)
                df = pro.moneyflow(ts_code=ts_code, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        td = str(row.get("trade_date") or "")
                        if not td or len(td) < 8:
                            continue
                        trade_date = f"{td[:4]}-{td[4:6]}-{td[6:8]}"
                        buy_lg = float(row.get("buy_lg_amount") or 0)
                        sell_lg = float(row.get("sell_lg_amount") or 0)
                        buy_elg = float(row.get("buy_elg_amount") or 0)
                        sell_elg = float(row.get("sell_elg_amount") or 0)
                        buy_sm = float(row.get("buy_sm_amount") or 0)
                        sell_sm = float(row.get("sell_sm_amount") or 0)
                        buy_md = float(row.get("buy_md_amount") or 0)
                        sell_md = float(row.get("sell_md_amount") or 0)
                        main_net = (buy_lg + buy_elg) - (sell_lg + sell_elg)

                        conn.execute(
                            """INSERT OR REPLACE INTO stock_fund_flow 
                            (code, trade_date, main_net_inflow, super_large_net_inflow, large_net_inflow, 
                             middle_net_inflow, small_net_inflow, source, updated_at) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, 'tushare_pro', CURRENT_TIMESTAMP)""",
                            (code, trade_date, main_net,
                             buy_elg - sell_elg, buy_lg - sell_lg,
                             buy_md - sell_md, buy_sm - sell_sm),
                        )
                        count += 1
            except Exception:
                pass
            await asyncio.sleep(0.35)

        conn.commit()
        conn.close()
        return {"success": True, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def sync_dragon_tiger(db) -> dict[str, Any]:
    """同步龙虎榜数据（Tushare Pro top_list）。"""
    if not _require_tushare("sync_dragon_tiger"):
        return {"success": False, "error": "tushare unavailable"}
    print("  同步龙虎榜...")
    try:
        conn = sqlite3.connect(str(DB_PATH))
        count = 0

        for days_back in range(5):
            check_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
            try:
                df = pro.top_list(trade_date=check_date)
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        ts_code = str(row.get("ts_code") or "")
                        code = ts_code.split(".")[0] if "." in ts_code else ts_code
                        td = str(row.get("trade_date") or "")
                        if not td or not code:
                            continue
                        trade_date = f"{td[:4]}-{td[4:6]}-{td[6:8]}" if len(td) == 8 else td
                        reason = str(row.get("reason") or "")
                        conn.execute(
                            """INSERT OR REPLACE INTO dragon_tiger 
                            (code, trade_date, reason, buy_amount, sell_amount, net_buy, created_at) 
                            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                            (code, trade_date, reason,
                             float(row.get("l_buy") or 0),
                             float(row.get("l_sell") or 0),
                             float(row.get("net_amount") or 0)),
                        )
                        count += 1
            except Exception:
                pass
            await asyncio.sleep(0.5)

        conn.commit()
        conn.close()
        return {"success": True, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def sync_block_stocks(db) -> dict[str, Any]:
    """同步板块成分股（从 stocks.industry 聚合）。"""
    print("  同步板块成分股...")
    try:
        conn = sqlite3.connect(str(DB_PATH))
        stocks = conn.execute('SELECT stock_code, stock_name, industry FROM stocks WHERE industry IS NOT NULL AND industry != ""').fetchall()
        count = 0
        for code, name, industry in stocks:
            block_code = f"ind_{industry}"
            conn.execute(
                """INSERT OR REPLACE INTO block_stocks 
                (block_code, stock_code, stock_name, updated_at) 
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)""",
                (block_code, code, name),
            )
            count += 1
        conn.commit()
        conn.close()
        return {"success": True, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def sync_margin_detail(db, codes: list[str]) -> dict[str, Any]:
    """同步个股融资融券明细（Tushare Pro margin_detail）。"""
    if not _require_tushare("sync_margin_detail"):
        return {"success": False, "error": "tushare unavailable"}
    print(f"  同步个股融资融券明细 ({len(codes)} 只)...")
    try:
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')

        conn = sqlite3.connect(str(DB_PATH))
        count = 0

        # 按批次获取（Tushare 限制每次最多 1000 条）
        for code in codes:
            try:
                ts_code = _to_ts_code(code)
                df = pro.margin_detail(ts_code=ts_code, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        trade_date_raw = str(row.get("trade_date") or "").strip()
                        if not trade_date_raw or len(trade_date_raw) < 8:
                            continue
                        conn.execute(
                            """INSERT OR REPLACE INTO margin_detail 
                            (trade_date, ts_code, rzye, rqye, rzmre, rqyl, rzche, rqchl, rqmcl, rzrqye, updated_at) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                            (
                                trade_date_raw,
                                ts_code,
                                float(row.get("rzye") or 0),
                                float(row.get("rqye") or 0),
                                float(row.get("rzmre") or 0),
                                float(row.get("rqyl") or 0),
                                float(row.get("rzche") or 0),
                                float(row.get("rqchl") or 0),
                                float(row.get("rqmcl") or 0),
                                float(row.get("rzrqye") or 0),
                            ),
                        )
                        count += 1
            except Exception:
                pass
            await asyncio.sleep(0.4)

        conn.commit()
        conn.close()
        return {"success": True, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def sync_financial(db, codes: list[str]) -> dict[str, Any]:
    """同步财务数据（Tushare Pro income + fina_indicator）。"""
    if not _require_tushare("sync_financial"):
        return {"success": False, "synced": 0, "failed": len(codes), "error": "tushare unavailable"}
    print(f"  同步财务数据 ({len(codes)} 只)...")

    success = 0
    failed = 0
    for code in codes:
        try:
            ts_code = _to_ts_code(code)
            conn = sqlite3.connect(str(DB_PATH))

            # 获取利润表
            income_df = pro.income(ts_code=ts_code, fields='ts_code,end_date,revenue,n_income,total_profit')
            # 获取财务指标
            indicator_df = pro.fina_indicator(ts_code=ts_code, fields='ts_code,end_date,grossprofit_margin,netprofit_margin,debt_to_assets,current_ratio,eps,roe,roa,tr_yoy,netprofit_yoy')

            if income_df is not None and not income_df.empty:
                for _, row in income_df.head(4).iterrows():
                    end_date_raw = str(row.get("end_date") or "")
                    revenue = float(row.get("revenue") or 0)
                    net_income = float(row.get("n_income") or 0)

                    # 尝试从 indicator 获取更多字段
                    gross_margin = None
                    net_margin = None
                    debt_ratio = None
                    current_ratio_val = None
                    eps = None
                    roe = None
                    roa = None
                    revenue_growth = None
                    profit_growth = None

                    if indicator_df is not None and not indicator_df.empty:
                        ind_match = indicator_df[indicator_df["end_date"] == end_date_raw]
                        if not ind_match.empty:
                            ind_row = ind_match.iloc[0]
                            gross_margin = float(ind_row.get("grossprofit_margin") or 0) or None
                            net_margin = float(ind_row.get("netprofit_margin") or 0) or None
                            debt_ratio = float(ind_row.get("debt_to_assets") or 0) or None
                            current_ratio_val = float(ind_row.get("current_ratio") or 0) or None
                            eps = float(ind_row.get("eps") or 0) or None
                            roe = float(ind_row.get("roe") or 0) or None
                            roa = float(ind_row.get("roa") or 0) or None
                            revenue_growth = float(ind_row.get("tr_yoy") or 0) or None
                            profit_growth = float(ind_row.get("netprofit_yoy") or 0) or None

                    conn.execute(
                        """INSERT OR REPLACE INTO financials 
                        (stock_code, report_date, revenue, net_profit, gross_margin, net_margin, 
                         debt_ratio, current_ratio, eps, roe, bvps, roa, revenue_growth, profit_growth, updated_at) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, CURRENT_TIMESTAMP)""",
                        (code, end_date_raw, revenue, net_income, gross_margin, net_margin,
                         debt_ratio, current_ratio_val, eps, roe, roa, revenue_growth, profit_growth),
                    )
                conn.commit()
                conn.close()
                success += 1
            else:
                conn.close()
                failed += 1
        except Exception as e:
            failed += 1
            if failed <= 3:
                print(f"    ⚠️ {code}: {type(e).__name__}: {e}")
        await asyncio.sleep(0.5)

    return {"success": True, "synced": success, "failed": failed}


async def show_status(db):
    """显示数据库同步状态。"""
    print("数据库同步状态")
    print("=" * 50)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # K 线
    try:
        row = conn.execute("SELECT COUNT(DISTINCT code) as cnt, MAX(time) as latest FROM kline_1d").fetchone()
        print(f"  K 线: {row['cnt']} 只股票, 最新: {row['latest']}")
    except Exception:
        print("  K 线: 无数据")

    # 北向资金
    try:
        row = conn.execute("SELECT COUNT(*) as cnt, MAX(trade_date) as latest FROM north_fund_flow").fetchone()
        print(f"  北向资金: {row['cnt']} 条, 最新: {row['latest']}")
    except Exception:
        print("  北向资金: 无数据")

    # 融资融券
    try:
        row = conn.execute("SELECT COUNT(*) as cnt, MAX(trade_date) as latest FROM margin_market_flow").fetchone()
        print(f"  融资融券(市场): {row['cnt']} 条, 最新: {row['latest']}")
    except Exception:
        print("  融资融券(市场): 无数据")

    # 融资融券明细
    try:
        row = conn.execute("SELECT COUNT(*) as cnt, COUNT(DISTINCT ts_code) as stocks, MAX(trade_date) as latest FROM margin_detail").fetchone()
        print(f"  融资融券(个股): {row['cnt']} 条, {row['stocks']} 只, 最新: {row['latest']}")
    except Exception:
        print("  融资融券(个股): 无数据")

    # 股票列表
    try:
        row = conn.execute("SELECT COUNT(*) as cnt FROM stocks").fetchone()
        print(f"  股票列表: {row['cnt']} 只")
    except Exception:
        print("  股票列表: 无数据")

    # 交易日历
    try:
        row = conn.execute("SELECT COUNT(*) as cnt, MAX(trade_date) as latest FROM trading_dates").fetchone()
        print(f"  交易日历: {row['cnt']} 天, 最新: {row['latest']}")
    except Exception:
        print("  交易日历: 无数据")

    # 财务数据
    try:
        row = conn.execute("SELECT COUNT(DISTINCT stock_code) as cnt, MAX(updated_at) as latest FROM financials").fetchone()
        print(f"  财务数据: {row['cnt']} 只股票, 最新更新: {row['latest']}")
    except Exception:
        print("  财务数据: 无数据")

    # 板块资金
    try:
        row = conn.execute("SELECT COUNT(*) as cnt, MAX(updated_at) as latest FROM market_blocks").fetchone()
        print(f"  板块数据: {row['cnt']} 条, 最新: {row['latest']}")
    except Exception:
        print("  板块数据: 无数据")

    conn.close()

    # 数据库大小
    if DB_PATH.exists():
        size_mb = DB_PATH.stat().st_size / 1024 / 1024
        print(f"\n  数据库大小: {size_mb:.1f} MB")
        print(f"  数据库路径: {DB_PATH}")
    print(f"\n  数据源: Tushare Pro (token: {TUSHARE_TOKEN[:8]}...)")


# ─────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(
        description="统一数据同步脚本（默认 TDX 本地 + Tushare 补齐）"
    )
    parser.add_argument("--full", action="store_true", help="全量同步（首次使用）")
    parser.add_argument("--incremental", action="store_true", help="增量同步（日常）")
    parser.add_argument(
        "--type",
        choices=[
            "kline",
            "north_fund",
            "margin",
            "margin_detail",
            "financial",
            "stocks",
            "calendar",
            "sector_flow",
            "daily_basic",
            "stock_fund_flow",
            "dragon_tiger",
            "block_stocks",
        ],
        help="同步特定类型",
    )
    parser.add_argument(
        "--source",
        choices=["auto", "tdx", "tushare"],
        default="auto",
        help="数据源：auto(默认，TDX 优先 + Tushare 补齐) / tdx(纯本地) / tushare(纯网络)",
    )
    parser.add_argument("--codes", type=str, default="", help="指定股票代码（逗号分隔）")
    parser.add_argument("--days", type=int, default=2000, help="K线天数（默认 2000，覆盖 8 年）")
    parser.add_argument("--status", action="store_true", help="查看同步状态")
    args = parser.parse_args()

    # 数据源解析
    use_tdx = args.source in ("auto", "tdx") and tdx_local.has_local
    use_tushare = args.source in ("auto", "tushare") and pro is not None

    if args.source == "tushare" and pro is None:
        print("❌ 错误: --source tushare 需要 TUSHARE_TOKEN 配置")
        sys.exit(1)
    if args.source == "tdx" and not tdx_local.has_local:
        print("❌ 错误: --source tdx 需要 TDX_INSTALL_DIR 指向通达信安装目录")
        sys.exit(1)
    if not use_tdx and not use_tushare:
        print("❌ 错误: 没有可用的数据源（TDX 与 Tushare 都未配置）")
        sys.exit(1)

    # 确保数据库已初始化
    if not DB_PATH.exists():
        print("数据库不存在，先运行初始化...")
        os.system(f"{sys.executable} {PROJECT_ROOT / 'scripts' / 'db_init.py'}")
        print()

    from akshare_mcp.storage.sqlite import get_db
    db = get_db()
    await db.initialize()

    if args.status:
        await show_status(db)
        return

    if not (args.full or args.incremental or args.type):
        parser.print_help()
        return

    start = time.time()
    results: dict[str, Any] = {}
    codes = [c.strip() for c in args.codes.split(",") if c.strip()] if args.codes else REPRESENTATIVE_STOCKS

    label = "[全量]" if args.full else ("[增量]" if args.incremental else f"[{args.type}]")
    src_label = []
    if use_tdx:
        src_label.append(f"TDX({tdx_local.install_dir})")
    if use_tushare:
        src_label.append("Tushare Pro")
    print("=" * 60)
    print(f"数据同步 {label}")
    print(f"数据库: {DB_PATH}")
    print(f"数据源: {' + '.join(src_label) or 'none'}")
    print("=" * 60)
    print()

    # ── stocks（TDX 优先） ──
    async def _do_stocks() -> None:
        if use_tdx:
            r = await sync_stocks_tdx()
            results["stocks_tdx"] = r
            print(f"    → 股票列表(TDX): {r.get('count', 0)} 只")
        if use_tushare:
            r = await sync_stocks(db)
            results["stocks"] = r
            print(f"    → 股票列表(Tushare): {r.get('count', 0)} 只 名称/行业补齐")

    # ── calendar（TDX 优先） ──
    async def _do_calendar() -> None:
        if use_tdx:
            r = await sync_calendar_tdx()
            results["calendar_tdx"] = r
            print(f"    → 交易日历(TDX): {r.get('count', 0)} 天")
        if use_tushare and not (use_tdx and results.get("calendar_tdx", {}).get("count", 0) > 0):
            r = await sync_calendar(db)
            results["calendar"] = r
            print(f"    → 交易日历(Tushare): {r.get('count', 0)} 天")

    # ── kline（TDX 优先；Tushare 仅在 use_tushare && !use_tdx 时回灌） ──
    async def _do_klines(target_codes: list[str], days: int) -> None:
        if use_tdx:
            r = await sync_klines_tdx(db, target_codes, days=days)
            results["kline_tdx"] = r
            print(
                f"    → K 线(TDX): 成功 {r.get('synced', 0)}, 失败 {r.get('failed', 0)}, 总数 {r.get('total', 0)}"
            )
        elif use_tushare:
            r = await sync_klines(db, target_codes, days=min(days, 250))
            results["kline"] = r
            print(f"    → K 线(Tushare): 成功 {r.get('synced', 0)}, 失败 {r.get('failed', 0)}")

    if args.full:
        await _do_stocks()
        await asyncio.sleep(0.2)
        await _do_calendar()

        all_stocks = _get_all_stocks()
        print(f"    → 全量股票池: {len(all_stocks)} 只")
        await _do_klines(all_stocks, args.days)

        if use_tushare:
            await asyncio.sleep(1)
            results["north_fund"] = await sync_north_fund(db)
            print(f"    → 北向资金: {results['north_fund'].get('count', 0)} 条")

            await asyncio.sleep(1)
            results["margin"] = await sync_margin(db)
            print(f"    → 融资融券: {results['margin'].get('count', 0)} 条")

            await asyncio.sleep(1)
            results["margin_detail"] = await sync_margin_detail(db, REPRESENTATIVE_STOCKS)
            print(f"    → 融资融券明细: {results['margin_detail'].get('count', 0)} 条")

            await asyncio.sleep(1)
            results["daily_basic"] = await sync_daily_basic(db, REPRESENTATIVE_STOCKS)
            print(f"    → 估值数据: {results['daily_basic'].get('count', 0)} 条")

            await asyncio.sleep(1)
            results["stock_fund_flow"] = await sync_stock_fund_flow(db, REPRESENTATIVE_STOCKS)
            print(f"    → 个股资金流: {results['stock_fund_flow'].get('count', 0)} 条")

            await asyncio.sleep(1)
            results["dragon_tiger"] = await sync_dragon_tiger(db)
            print(f"    → 龙虎榜: {results['dragon_tiger'].get('count', 0)} 条")

            await asyncio.sleep(1)
            results["financial"] = await sync_financial(db, all_stocks)
            print(
                f"    → 财务数据: 成功 {results['financial'].get('synced', 0)}, 失败 {results['financial'].get('failed', 0)}"
            )

        # 板块从 stocks.industry 聚合（无须网络），始终执行
        await asyncio.sleep(0.5)
        results["sector_flow"] = await sync_sector_flow(db)
        print(f"    → 板块资金: {results['sector_flow'].get('count', 0)} 条")

        await asyncio.sleep(0.5)
        results["block_stocks"] = await sync_block_stocks(db)
        print(f"    → 板块成分股: {results['block_stocks'].get('count', 0)} 条")

    elif args.incremental:
        await _do_klines(codes, days=10 if use_tdx else 5)
        if use_tushare:
            await asyncio.sleep(0.5)
            results["north_fund"] = await sync_north_fund(db)
            print(f"    → 北向资金: {results['north_fund'].get('count', 0)} 条")

            await asyncio.sleep(0.5)
            results["margin"] = await sync_margin(db)
            print(f"    → 融资融券: {results['margin'].get('count', 0)} 条")

    elif args.type:
        if args.type == "kline":
            # 不传 --codes 时走全量 A 股
            kline_codes = codes if args.codes else _get_all_stocks()
            await _do_klines(kline_codes, args.days)
        elif args.type == "stocks":
            await _do_stocks()
        elif args.type == "calendar":
            await _do_calendar()
        elif args.type == "sector_flow":
            results["sector_flow"] = await sync_sector_flow(db)
        elif args.type == "block_stocks":
            results["block_stocks"] = await sync_block_stocks(db)
        elif args.type == "north_fund":
            results["north_fund"] = await sync_north_fund(db)
        elif args.type == "margin":
            results["margin"] = await sync_margin(db)
        elif args.type == "margin_detail":
            results["margin_detail"] = await sync_margin_detail(db, codes)
        elif args.type == "financial":
            results["financial"] = await sync_financial(db, codes)
        elif args.type == "daily_basic":
            results["daily_basic"] = await sync_daily_basic(db, codes)
        elif args.type == "stock_fund_flow":
            results["stock_fund_flow"] = await sync_stock_fund_flow(db, codes)
        elif args.type == "dragon_tiger":
            results["dragon_tiger"] = await sync_dragon_tiger(db)

        for name, result in results.items():
            status = "✅" if result.get("success") else "❌"
            print(f"    {status} {name}: {result}")

    elapsed = time.time() - start
    print()
    print(f"完成，耗时 {elapsed:.1f}s")

    # 显示最终状态
    print()
    await show_status(db)


if __name__ == "__main__":
    asyncio.run(main())
