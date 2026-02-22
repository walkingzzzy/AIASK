"""策略工厂 — 每日自动生成、筛选、提交、淘汰策略

组件:
- DataCollector: 汇总每日市场数据快照
- StrategySpawner: 根据数据信号生成候选策略
- BacktestFilter: 回测筛选候选
- Deduplicator: 去除与已有策略重复的候选
- StrategySubmitter: 创建策略记录并提交质检
- EliminationChecker: 淘汰表现差的已上架策略
- StrategyFactoryScheduler: 每日19:00自动运行

Usage:
    from .strategy_factory import get_strategy_factory_scheduler
    scheduler = get_strategy_factory_scheduler()
    scheduler.start()
"""

import asyncio
import json
import logging
import random
import time as _time
from datetime import date, datetime, time, timedelta
from statistics import median
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import numpy as np

logger = logging.getLogger(__name__)

# 回测用代表性股票（大盘/中盘/小盘各覆盖）
REPRESENTATIVE_STOCKS = [
    "600519", "000858", "601318", "600036", "000333",
    "002415", "600276", "601012", "300750", "000001",
]

# 前端分类最低配额
CATEGORY_MINIMUMS = {
    "momentum": 3, "ma_cross": 3, "rsi": 3,
    "value_factor": 3, "quality_factor": 3, "growth_factor": 3,
    "multi_factor": 3, "macro_timing": 3,
}

class DataCollector:
    """汇总每日市场数据快照 — 策略工厂的唯一输入"""

    async def collect(self, db) -> dict:
        snapshot: Dict[str, Any] = {"date": str(date.today())}

        # 1. 恐贪指数
        try:
            from .sentiment import sentiment_analyzer
            index_klines = await db.get_klines("sh000001", limit=60)
            breadth = None
            try:
                breadth = await db.get_limit_up_stats()
            except Exception:
                pass
            fg = sentiment_analyzer.calculate_fear_greed_index(index_klines, breadth)
            snapshot["fear_greed_index"] = fg.get("index", 50)
            snapshot["fg_level"] = fg.get("level", "neutral")
            snapshot["fg_components"] = fg.get("components", {})
        except Exception as e:
            logger.warning("DataCollector: fear_greed failed: %s", e)
            snapshot["fear_greed_index"] = 50
            snapshot["fg_level"] = "neutral"
            snapshot["fg_components"] = {}

        # 2. 因子IC历史
        factor_ic: Dict[str, float] = {}
        factor_ic_trend: Dict[str, str] = {}
        for fname in ["momentum", "value", "quality", "volatility", "reversal"]:
            try:
                rows = await db.get_factor_ic_history(fname, "20", 20)
                ics = [r.get("ic_value", 0) for r in (rows or []) if r.get("ic_value") is not None]
                if ics:
                    factor_ic[fname] = ics[0]
                    if len(ics) >= 10:
                        avg5 = np.mean(ics[:5])
                        avg10 = np.mean(ics[5:10])
                        delta = avg5 - avg10
                        factor_ic_trend[fname] = "rising" if delta > 0.005 else ("falling" if delta < -0.005 else "flat")
                    else:
                        factor_ic_trend[fname] = "flat"
            except Exception:
                pass
        snapshot["factor_ic"] = factor_ic
        snapshot["factor_ic_trend"] = factor_ic_trend

        # 3. 北向资金 / 融资融券 / 板块资金流（直接调用 fund_flow 工具函数）
        snapshot["north_fund_3d_net"] = 0.0
        snapshot["margin_5d_change_pct"] = 0.0
        snapshot["hot_sectors"] = []
        snapshot["cold_sectors"] = []
        try:
            from ..tools.fund_flow import get_north_fund
            nf = await asyncio.to_thread(get_north_fund, 5)
            if nf.get("success") and nf.get("data", {}).get("items"):
                items = nf["data"]["items"][:3]
                total_3d = sum(float(it.get("total") or 0) for it in items)
                snapshot["north_fund_3d_net"] = round(total_3d, 2)
        except Exception as e:
            logger.debug("DataCollector: north_fund failed: %s", e)

        try:
            from ..tools.fund_flow import get_margin_data
            mg = await asyncio.to_thread(get_margin_data, "", 10)
            if mg.get("success") and isinstance(mg.get("data"), list) and len(mg["data"]) >= 6:
                rows = mg["data"]
                recent_bal = float(rows[0].get("marginBalance") or 0)
                older_bal = float(rows[min(5, len(rows) - 1)].get("marginBalance") or 0)
                if older_bal > 0:
                    snapshot["margin_5d_change_pct"] = round(
                        (recent_bal - older_bal) / older_bal * 100, 2
                    )
        except Exception as e:
            logger.debug("DataCollector: margin_data failed: %s", e)

        try:
            from ..tools.fund_flow import get_sector_fund_flow
            sf = await asyncio.to_thread(get_sector_fund_flow, 20)
            if sf.get("success") and isinstance(sf.get("data"), list):
                sectors = sf["data"]
                snapshot["hot_sectors"] = [
                    s.get("name", "") for s in sectors[:5]
                    if float(s.get("mainNetInflow") or 0) > 0
                ]
                snapshot["cold_sectors"] = [
                    s.get("name", "") for s in sectors[-5:]
                    if float(s.get("mainNetInflow") or 0) < 0
                ]
        except Exception as e:
            logger.debug("DataCollector: sector_fund_flow failed: %s", e)

        # 4. 种群状态
        try:
            counts = await db.count_strategies_by_type("listed")
            snapshot["category_counts"] = counts
            snapshot["listed_count"] = sum(counts.values())
            incubating = await db.count_strategies_by_type("incubating")
            snapshot["incubating_count"] = sum(incubating.values())
        except Exception:
            snapshot["category_counts"] = {}
            snapshot["listed_count"] = 0
            snapshot["incubating_count"] = 0

        # 持久化快照
        try:
            await db.save_daily_snapshot(date.today(), snapshot)
        except Exception as e:
            logger.warning("DataCollector: save snapshot failed: %s", e)

        return snapshot

class StrategySpawner:
    """根据每日数据快照生成候选策略"""

    def spawn(self, snapshot: dict) -> List[dict]:
        candidates: List[dict] = []
        candidates += self._from_fear_greed(snapshot)
        candidates += self._from_factor_ic(snapshot)
        candidates += self._from_volatility(snapshot)
        candidates += self._from_fund_flow(snapshot)
        candidates += self._fill_gaps(snapshot)
        return candidates

    def _from_fear_greed(self, s: dict) -> List[dict]:
        out: List[dict] = []
        fg = s.get("fear_greed_index", 50)
        if fg < 30:
            out.append(self._make("rsi", {"rsi_period": 14, "oversold": 25, "overbought": 75},
                                  f"恐贪{fg}，恐惧区RSI抄底"))
            out.append(self._make("rsi", {"rsi_period": 6, "oversold": 20, "overbought": 80},
                                  f"恐贪{fg}，短周期RSI超跌"))
            out.append(self._make("value_factor", {"lookback": 60, "buy_quantile": 0.85, "sell_quantile": 0.15},
                                  f"恐贪{fg}，恐惧期精选价值"))
        elif fg > 70:
            out.append(self._make("momentum", {"lookback": 5, "threshold": 0.01},
                                  f"恐贪{fg}，贪婪期短周期动量"))
            out.append(self._make("momentum", {"lookback": 10, "threshold": 0.02},
                                  f"恐贪{fg}，贪婪期中周期动量"))
            out.append(self._make("growth_factor", {"lookback": 40, "buy_quantile": 0.85, "sell_quantile": 0.15},
                                  f"恐贪{fg}，贪婪期成长加速"))
            out.append(self._make("rsi", {"rsi_period": 14, "oversold": 35, "overbought": 65},
                                  f"恐贪{fg}，贪婪期RSI逃顶"))
        else:
            out.append(self._make("ma_cross", {"short_period": 5, "long_period": 20},
                                  f"恐贪{fg}，中性标准均线"))
            out.append(self._make("momentum", {"lookback": 20, "threshold": 0.02},
                                  f"恐贪{fg}，中性标准动量"))
        return out

    def _from_factor_ic(self, s: dict) -> List[dict]:
        out: List[dict] = []
        factor_ic = s.get("factor_ic", {})
        trend = s.get("factor_ic_trend", {})

        for fname, ic in factor_ic.items():
            t = trend.get(fname, "flat")
            if ic > 0.03 and t == "rising":
                if fname == "momentum":
                    for lb in [5, 10, 20]:
                        out.append(self._make("momentum", {"lookback": lb, "threshold": 0.02},
                                              f"momentum IC={ic:.3f}上升，{lb}日动量"))
                elif fname == "value":
                    out.append(self._make("value_factor", {"lookback": 60, "buy_quantile": 0.8, "sell_quantile": 0.2},
                                          f"value IC={ic:.3f}上升"))
                elif fname == "quality":
                    out.append(self._make("quality_factor", {"lookback": 60, "buy_quantile": 0.8, "sell_quantile": 0.2},
                                          f"quality IC={ic:.3f}上升"))
                elif fname == "reversal":
                    out.append(self._make("rsi", {"rsi_period": 14, "oversold": 30, "overbought": 70},
                                          f"reversal IC={ic:.3f}上升，反转有效"))
            elif ic < -0.02 and t == "falling":
                if fname == "momentum":
                    out.append(self._make("rsi", {"rsi_period": 14, "oversold": 30, "overbought": 70},
                                          f"momentum IC={ic:.3f}下降，转反转"))

        # 多因子策略：根据IC动态分配权重
        weights: Dict[str, float] = {}
        for fname in ["value", "quality", "growth"]:
            ic = factor_ic.get(fname, 0)
            t = trend.get(fname, "flat")
            if t == "rising":
                weights[fname] = max(0.1, 0.33 + ic * 2)
            elif t == "falling":
                weights[fname] = max(0.05, 0.33 - abs(ic) * 2)
            else:
                weights[fname] = 0.33
        total = sum(weights.values()) or 1.0
        weights = {k: round(v / total, 2) for k, v in weights.items()}
        out.append(self._make("multi_factor", {"factor_weights": weights, "lookback": 60},
                              f"IC驱动多因子权重: {weights}"))
        return out

    def _from_volatility(self, s: dict) -> List[dict]:
        out: List[dict] = []
        vol = s.get("fg_components", {}).get("volatility", 50)
        if vol < 35:
            out.append(self._make("ma_cross", {"short_period": 10, "long_period": 60},
                                  f"波动率{vol}，高波动长周期均线"))
            out.append(self._make("macro_timing", {"fear_threshold": 30, "greed_threshold": 70, "lookback": 30},
                                  f"波动率{vol}，高波动宏观择时"))
        elif vol > 65:
            out.append(self._make("ma_cross", {"short_period": 3, "long_period": 15},
                                  f"波动率{vol}，低波动短周期均线"))
        return out

    def _from_fund_flow(self, s: dict) -> List[dict]:
        """根据北向资金、融资融券、板块资金流生成候选"""
        out: List[dict] = []
        north_3d = s.get("north_fund_3d_net", 0)
        margin_5d = s.get("margin_5d_change_pct", 0)

        # 北向资金3日净流入 > 50亿 → 成长+质量策略
        if north_3d > 5_000_000_000:
            out.append(self._make("growth_factor",
                                  {"lookback": self._jitter(40, 30, 60), "buy_quantile": 0.85, "sell_quantile": 0.15},
                                  f"北向3日净流入{north_3d / 1e8:.0f}亿，成长加速"))
            out.append(self._make("quality_factor",
                                  {"lookback": self._jitter(60, 40, 80), "buy_quantile": 0.8, "sell_quantile": 0.2},
                                  f"北向3日净流入{north_3d / 1e8:.0f}亿，质量优选"))
        # 北向资金3日净流出 > 50亿 → 防御策略
        elif north_3d < -5_000_000_000:
            out.append(self._make("value_factor",
                                  {"lookback": self._jitter(60, 40, 80), "buy_quantile": 0.85, "sell_quantile": 0.15},
                                  f"北向3日净流出{abs(north_3d) / 1e8:.0f}亿，价值防御"))
            out.append(self._make("macro_timing",
                                  {"fear_threshold": 30, "greed_threshold": 60, "lookback": self._jitter(25, 15, 35)},
                                  f"北向3日净流出{abs(north_3d) / 1e8:.0f}亿，宏观择时"))

        # 融资余额5日增速 > 2% → 短周期动量
        if margin_5d > 2.0:
            out.append(self._make("momentum",
                                  {"lookback": self._jitter(5, 3, 10), "threshold": 0.01},
                                  f"融资5日增速{margin_5d:.1f}%，短周期动量"))
        # 融资余额5日下降 > 2% → RSI超跌
        elif margin_5d < -2.0:
            out.append(self._make("rsi",
                                  {"rsi_period": self._jitter(6, 4, 10), "oversold": 20, "overbought": 80},
                                  f"融资5日降速{abs(margin_5d):.1f}%，RSI超跌"))

        return out

    def _fill_gaps(self, s: dict) -> List[dict]:
        out: List[dict] = []
        counts = s.get("category_counts", {})
        for stype, minimum in CATEGORY_MINIMUMS.items():
            current = counts.get(stype, 0)
            gap = minimum - current
            if gap > 0:
                for i in range(gap):
                    params = self._varied_defaults(stype, i)
                    out.append(self._make(stype, params, f"{stype}分类不足{minimum}个，补位#{i + 1}"))
        return out

    @staticmethod
    def _jitter(base: int, lo: int, hi: int) -> int:
        """在 [lo, hi] 范围内对 base 添加随机扰动"""
        delta = max(1, int(base * 0.2))
        return max(lo, min(hi, base + random.randint(-delta, delta)))

    @staticmethod
    def _jitter_f(base: float, lo: float, hi: float) -> float:
        """浮点数版本的参数扰动"""
        delta = max(0.01, base * 0.15)
        return round(max(lo, min(hi, base + random.uniform(-delta, delta))), 2)

    def _varied_defaults(self, stype: str, idx: int) -> dict:
        """为补位策略生成差异化参数"""
        if stype == "momentum":
            lbs = [10, 20, 30]
            lb = lbs[idx % len(lbs)]
            return {"lookback": self._jitter(lb, 5, 40), "threshold": self._jitter_f(0.02, 0.005, 0.05)}
        elif stype == "ma_cross":
            pairs = [(5, 20), (10, 30), (5, 60)]
            sp, lp = pairs[idx % len(pairs)]
            sp = self._jitter(sp, 3, 15)
            lp = self._jitter(lp, max(sp + 5, 15), 80)
            return {"short_period": sp, "long_period": lp}
        elif stype == "rsi":
            periods = [6, 14, 21]
            p = periods[idx % len(periods)]
            return {"rsi_period": self._jitter(p, 4, 28),
                    "oversold": self._jitter(30, 20, 40),
                    "overbought": self._jitter(70, 60, 80)}
        elif stype == "value_factor":
            return {"lookback": self._jitter(60, 30, 90),
                    "buy_quantile": self._jitter_f(0.8, 0.7, 0.9),
                    "sell_quantile": self._jitter_f(0.2, 0.1, 0.3)}
        elif stype == "quality_factor":
            return {"lookback": self._jitter(60, 30, 90),
                    "buy_quantile": self._jitter_f(0.8, 0.7, 0.9),
                    "sell_quantile": self._jitter_f(0.2, 0.1, 0.3)}
        elif stype == "growth_factor":
            return {"lookback": self._jitter(40, 25, 70),
                    "buy_quantile": self._jitter_f(0.8, 0.7, 0.9),
                    "sell_quantile": self._jitter_f(0.2, 0.1, 0.3)}
        elif stype == "multi_factor":
            w = {"value": random.uniform(0.2, 0.5),
                 "quality": random.uniform(0.2, 0.5),
                 "growth": random.uniform(0.2, 0.5)}
            total = sum(w.values())
            w = {k: round(v / total, 2) for k, v in w.items()}
            return {"factor_weights": w, "lookback": self._jitter(60, 30, 90)}
        elif stype == "macro_timing":
            return {"fear_threshold": self._jitter(35, 25, 45),
                    "greed_threshold": self._jitter(65, 55, 75),
                    "lookback": self._jitter(20, 10, 35)}
        return {}

    @staticmethod
    def _make(strategy_type: str, params: dict, reason: str = "") -> dict:
        return {"strategy_type": strategy_type, "params": params, "spawn_reason": reason}

class BacktestFilter:
    """回测筛选候选策略"""

    SHARPE_MIN = 0.3
    MDD_MAX = 0.35
    TRADES_MIN = 3

    async def filter(self, candidates: List[dict], db) -> List[dict]:
        from .backtest.engine import BacktestEngine
        passed: List[dict] = []
        for c in candidates:
            metrics = await self._test_one(c, db, BacktestEngine)
            if metrics is not None:
                c["backtest_metrics"] = metrics
                passed.append(c)
        return passed

    async def _test_one(self, candidate: dict, db, engine) -> Optional[dict]:
        results: List[dict] = []
        for code in REPRESENTATIVE_STOCKS:
            try:
                klines = await db.get_klines(code, limit=500)
                if not klines or len(klines) < 100:
                    continue
                # run_backtest 是同步方法，用 to_thread 避免阻塞事件循环
                r = await asyncio.to_thread(
                    engine.run_backtest, code, klines, candidate["strategy_type"],
                    {**candidate["params"], "initial_capital": 100000, "commission": 0.00025}
                )
                if r.get("success"):
                    results.append(r["data"])
            except Exception:
                continue

        if len(results) < 3:
            return None

        avg = {
            "sharpe_ratio": float(median([m["sharpe_ratio"] for m in results])),
            "total_return": float(median([m["total_return"] for m in results])),
            "max_drawdown": float(median([m["max_drawdown"] for m in results])),
            "win_rate": float(median([m.get("win_rate", 0) for m in results])),
            "trades_count": float(median([m["trades_count"] for m in results])),
        }

        if avg["sharpe_ratio"] < self.SHARPE_MIN:
            return None
        if abs(avg["max_drawdown"]) > self.MDD_MAX:
            return None
        if avg["trades_count"] < self.TRADES_MIN:
            return None
        return avg


class Deduplicator:
    """去除与已有策略参数过于相似的候选"""

    THRESHOLD = 0.85

    async def deduplicate(self, candidates: List[dict], db) -> List[dict]:
        existing: List[dict] = []
        for status in ("listed", "incubating"):
            try:
                rows = await db.list_strategies(status, limit=500)
                existing.extend(rows)
            except Exception:
                pass

        unique: List[dict] = []
        seen = list(existing)
        for c in candidates:
            if self._is_dup(c, seen):
                continue
            unique.append(c)
            seen.append(c)
        return unique

    def _is_dup(self, candidate: dict, existing: list) -> bool:
        for e in existing:
            if e.get("strategy_type") != candidate.get("strategy_type"):
                continue
            ep = e.get("params") or {}
            if isinstance(ep, str):
                try:
                    ep = json.loads(ep)
                except Exception:
                    ep = {}
            sim = self._param_sim(candidate.get("params", {}), ep)
            if sim >= self.THRESHOLD:
                return True
        return False

    @staticmethod
    def _param_sim(a: dict, b: dict) -> float:
        keys = set(a.keys()) & set(b.keys())
        if not keys:
            return 0.0
        sims: List[float] = []
        for k in keys:
            va, vb = a[k], b[k]
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                denom = max(abs(va), abs(vb), 1e-9)
                sims.append(1.0 - abs(va - vb) / denom)
            elif va == vb:
                sims.append(1.0)
        return float(np.mean(sims)) if sims else 0.0

def _auto_name(stype: str, params: dict) -> str:
    """从策略类型+参数生成中文名"""
    if stype == "ma_cross":
        return f"均线交叉·快{params.get('short_period', 5)}慢{params.get('long_period', 20)}"
    elif stype == "momentum":
        return f"动量突破·{params.get('lookback', 20)}日{params.get('threshold', 0.02):.0%}"
    elif stype == "rsi":
        return f"RSI反转·{params.get('rsi_period', 14)}日({params.get('oversold', 30)}/{params.get('overbought', 70)})"
    elif stype == "value_factor":
        return f"价值精选·前{int(params.get('buy_quantile', 0.8) * 100)}%"
    elif stype == "quality_factor":
        return f"质量优选·前{int(params.get('buy_quantile', 0.8) * 100)}%"
    elif stype == "growth_factor":
        return f"成长优选·前{int(params.get('buy_quantile', 0.8) * 100)}%"
    elif stype == "multi_factor":
        fw = params.get("factor_weights", {})
        top = max(fw, key=fw.get, default="均衡") if fw else "均衡"
        return f"多因子·{top}主导"
    elif stype == "macro_timing":
        return f"宏观择时·恐贪({params.get('fear_threshold', 35)}/{params.get('greed_threshold', 65)})"
    return f"{stype}策略"


class StrategySubmitter:
    """创建策略记录并提交质检"""

    async def submit(self, candidates: List[dict], snapshot: dict, db) -> dict:
        from ..tools.managers.strategy_manager import _run_quality_gate
        created = 0
        submitted = 0
        passed = 0

        for c in candidates:
            try:
                sid = f"factory_{int(_time.time())}_{uuid4().hex[:8]}"
                name = _auto_name(c["strategy_type"], c["params"])
                metrics = c.get("backtest_metrics", {})
                desc = f"{name}\n生成原因: {c.get('spawn_reason', '')}"
                if metrics:
                    desc += f"\n回测: Sharpe {metrics.get('sharpe_ratio', 0):.2f} | "
                    desc += f"收益 {metrics.get('total_return', 0):.1%} | "
                    desc += f"回撤 {metrics.get('max_drawdown', 0):.1%}"

                data = {
                    "id": sid, "name": name, "description": desc,
                    "author_id": "strategy_factory",
                    "strategy_type": c["strategy_type"],
                    "params": c["params"],
                    "factor_weights": c["params"].get("factor_weights", {}),
                    "status": "draft",
                    "tags": ["auto_generated", "factory", c["strategy_type"]],
                }
                await db.save_strategy(data)
                created += 1

                # 保存回测指标
                if metrics:
                    await db.save_strategy_metrics(sid, "backtest", {
                        "sharpe_ratio": metrics.get("sharpe_ratio"),
                        "total_return": metrics.get("total_return"),
                        "max_drawdown": metrics.get("max_drawdown"),
                        "win_rate": metrics.get("win_rate"),
                        "trade_count": int(metrics.get("trades_count", 0)),
                    })

                # 提交质检
                await db.update_strategy_status(sid, "submitted")
                gate = await _run_quality_gate(db, {**data, "status": "submitted"})
                submitted += 1

                if gate.get("passed"):
                    await db.update_strategy_status(sid, "incubating")
                    passed += 1
                else:
                    await db.update_strategy_status(sid, "rejected")

                # 记录血缘
                try:
                    await db.save_strategy_lineage(sid, None, c.get("spawn_reason", ""), snapshot)
                except Exception:
                    pass

            except Exception as e:
                logger.warning("StrategySubmitter: failed for %s: %s", c.get("strategy_type"), e)

        return {"created": created, "submitted": submitted, "passed_quality_gate": passed}

class EliminationChecker:
    """检查已上架策略是否应该淘汰"""

    # 策略类型 → 适宜的市场环境
    _REGIME_MAP = {
        "momentum": ("greed", "extreme_greed"),
        "growth_factor": ("greed", "extreme_greed", "neutral"),
        "value_factor": ("fear", "extreme_fear", "neutral"),
        "rsi": ("fear", "extreme_fear"),
        "macro_timing": ("fear", "extreme_fear", "neutral"),
    }

    async def check(self, db, current_fg_level: str = "neutral") -> List[dict]:
        eliminated: List[dict] = []
        try:
            listed = await db.list_strategies("listed", limit=500)
        except Exception:
            return eliminated

        for s in listed:
            try:
                red_flags: List[str] = []
                metrics_list = await db.get_strategy_metrics(s["id"])
                m = {}
                for row in metrics_list:
                    if row.get("period") in ("all", "backtest"):
                        m = row
                        break

                mdd = abs(float(m.get("max_drawdown") or 0))
                sharpe = float(m.get("sharpe_ratio") or 0)
                win_rate = float(m.get("win_rate") or 0)

                if mdd > 0.30:
                    red_flags.append(f"回撤{mdd:.1%}>30%")
                if sharpe < 0:
                    red_flags.append(f"Sharpe {sharpe:.2f}<0")
                if 0 < win_rate < 0.30:
                    red_flags.append(f"胜率{win_rate:.1%}<30%")

                # 信号命中率检查（从 signal_forward_returns 获取实际数据）
                try:
                    sig_stats = await db.get_signal_stats(s["id"])
                    hit_rates = sig_stats.get("hit_rate", {})
                    total_signals = sig_stats.get("total_signals", 0)
                    if total_signals >= 10:
                        hr_5d = hit_rates.get(5, hit_rates.get("5", None))
                        if hr_5d is not None and float(hr_5d) < 0.30:
                            red_flags.append(f"5日信号命中率{float(hr_5d):.1%}<30%")
                except Exception:
                    pass

                # 市场环境错配检查
                stype = s.get("strategy_type", "")
                suitable = self._REGIME_MAP.get(stype)
                if suitable and current_fg_level and current_fg_level not in suitable:
                    red_flags.append(f"{stype}策略不适合当前{current_fg_level}环境")

                # 单一致命红旗或多重衰退（≥2个红旗）
                fatal = mdd > 0.30
                should_eliminate = fatal or (len(red_flags) >= 2)

                if should_eliminate and red_flags:
                    reason = "淘汰: " + "; ".join(red_flags)
                    await db.update_strategy_status(s["id"], "deprecated")
                    try:
                        await db.save_elimination_log(s["id"], date.today(), red_flags, reason)
                    except Exception:
                        pass
                    eliminated.append({"id": s["id"], "red_flags": red_flags, "reason": reason})
            except Exception as e:
                logger.debug("EliminationChecker: error checking %s: %s", s.get("id"), e)

        return eliminated

class StrategyFactoryScheduler:
    """每日19:00自动运行策略工厂全流程"""

    def __init__(self, run_time: time = time(19, 0)):
        self.run_time = run_time
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.last_run: Optional[datetime] = None
        self.last_result: Optional[dict] = None

    def start(self):
        if self._running:
            logger.warning("StrategyFactory already running")
            return
        self._running = True
        self._task = asyncio.ensure_future(self._loop())
        logger.info("StrategyFactory started, daily run at %s", self.run_time)

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("StrategyFactory stopped")

    async def _loop(self):
        while self._running:
            try:
                now = datetime.now()
                target = datetime.combine(now.date(), self.run_time)
                if target <= now:
                    target += timedelta(days=1)
                wait = (target - now).total_seconds()
                logger.info("StrategyFactory: next run in %.0fs at %s", wait, target)
                await asyncio.sleep(wait)
                if self._running:
                    await self.run_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("StrategyFactory loop error: %s", e, exc_info=True)
                await asyncio.sleep(60)

    async def run_once(self) -> dict:
        """执行一次完整的策略工厂流程"""
        from ..storage import get_db
        db = get_db()
        start = datetime.now()
        results: Dict[str, Any] = {}

        logger.info("StrategyFactory: starting daily cycle")

        # Step 1: 采集数据快照
        collector = DataCollector()
        snapshot = await collector.collect(db)
        results["fear_greed"] = snapshot.get("fear_greed_index")
        results["listed_count"] = snapshot.get("listed_count", 0)

        # Step 2: 生成候选
        spawner = StrategySpawner()
        candidates = spawner.spawn(snapshot)
        results["candidates_spawned"] = len(candidates)

        # Step 3: 回测筛选
        bt_filter = BacktestFilter()
        passed = await bt_filter.filter(candidates, db)
        results["candidates_passed_backtest"] = len(passed)

        # Step 4: 去重
        dedup = Deduplicator()
        unique = await dedup.deduplicate(passed, db)
        results["candidates_after_dedup"] = len(unique)

        # Step 5: 提交质检
        submitter = StrategySubmitter()
        submit_result = await submitter.submit(unique, snapshot, db)
        results["submitted"] = submit_result

        # Step 6: 淘汰检查（传入当前恐贪环境用于错配检测）
        eliminator = EliminationChecker()
        eliminated = await eliminator.check(db, snapshot.get("fg_level", "neutral"))
        results["eliminated"] = len(eliminated)

        elapsed = (datetime.now() - start).total_seconds()
        results["elapsed_seconds"] = round(elapsed, 1)
        self.last_run = datetime.now()
        self.last_result = results

        logger.info(
            "StrategyFactory: completed in %.1fs — spawned %d, backtest passed %d, "
            "dedup %d, submitted %s, eliminated %d",
            elapsed, results["candidates_spawned"], results["candidates_passed_backtest"],
            results["candidates_after_dedup"], submit_result, results["eliminated"],
        )
        return results

    def status(self) -> dict:
        return {
            "running": self._running,
            "run_time": str(self.run_time),
            "last_run": str(self.last_run) if self.last_run else None,
            "last_result": self.last_result,
        }


_factory_scheduler: Optional[StrategyFactoryScheduler] = None


def get_strategy_factory_scheduler() -> StrategyFactoryScheduler:
    global _factory_scheduler
    if _factory_scheduler is None:
        _factory_scheduler = StrategyFactoryScheduler()
    return _factory_scheduler
