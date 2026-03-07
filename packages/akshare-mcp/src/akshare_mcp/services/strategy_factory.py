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

from .backtest.strategy_registry import StrategyRegistry
from .data_pipeline import normalize_klines
from .risk_model import RiskModel
from .validation import FactorValidationPipeline
from .vector_search import VectorSearchEngine

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

# 初筛回测默认阈值与分层阈值
BACKTEST_DEFAULT_THRESHOLDS = {
    "sharpe_min": 0.30,
    "mdd_max": 0.35,
    "trades_min": 3,
    "min_samples": 3,
}

BACKTEST_TYPE_THRESHOLDS = {
    "momentum": {"sharpe_min": 0.35, "mdd_max": 0.32, "trades_min": 4},
    "ma_cross": {"sharpe_min": 0.25, "mdd_max": 0.35, "trades_min": 3},
    "rsi": {"sharpe_min": 0.20, "mdd_max": 0.38, "trades_min": 4},
    "value_factor": {"sharpe_min": 0.25, "mdd_max": 0.30, "trades_min": 3},
    "quality_factor": {"sharpe_min": 0.28, "mdd_max": 0.30, "trades_min": 3},
    "growth_factor": {"sharpe_min": 0.32, "mdd_max": 0.34, "trades_min": 4},
    "multi_factor": {"sharpe_min": 0.30, "mdd_max": 0.30, "trades_min": 4},
    "macro_timing": {"sharpe_min": 0.20, "mdd_max": 0.28, "trades_min": 2},
}

class DataCollector:
    """汇总每日市场数据快照 — 策略工厂的唯一输入"""

    @staticmethod
    def _build_source_status(status: str, fields: List[str], reason: Optional[str] = None, details: Optional[dict] = None) -> dict:
        payload = {
            "status": status,
            "fields": list(fields),
            "degraded": status != "success",
        }
        if reason:
            payload["reason"] = reason
        if details:
            payload["details"] = details
        return payload

    @staticmethod
    def _finalize_snapshot_contract(snapshot: Dict[str, Any], sources: Dict[str, dict], failure_reasons: List[dict], missing_fields: List[str]) -> dict:
        source_status_counts: Dict[str, int] = {}
        degraded_sources: List[str] = []
        missing_sources: List[str] = []
        for name, item in sources.items():
            status = str(item.get("status") or "unknown")
            source_status_counts[status] = source_status_counts.get(status, 0) + 1
            if status != "success":
                degraded_sources.append(name)
            if status == "fallback":
                missing_sources.append(name)

        total_sources = len(sources)
        available_sources = total_sources - len(degraded_sources)
        completion_ratio = round(available_sources / total_sources, 2) if total_sources else 1.0
        degraded = bool(degraded_sources)
        snapshot["summary"] = {
            "date": snapshot.get("date"),
            "fear_greed_index": snapshot.get("fear_greed_index"),
            "fg_level": snapshot.get("fg_level"),
            "listed_count": snapshot.get("listed_count", 0),
            "incubating_count": snapshot.get("incubating_count", 0),
            "hot_sector_count": len(snapshot.get("hot_sectors") or []),
            "cold_sector_count": len(snapshot.get("cold_sectors") or []),
            "source_status_counts": source_status_counts,
            "degraded": degraded,
        }
        snapshot["completeness"] = {
            "is_complete": not degraded and not missing_fields,
            "total_sources": total_sources,
            "available_sources": available_sources,
            "degraded_sources": sorted(degraded_sources),
            "missing_sources": sorted(missing_sources),
            "completion_ratio": completion_ratio,
        }
        snapshot["sources"] = sources
        snapshot["failure_reasons"] = failure_reasons
        snapshot["missing_fields"] = sorted(set(missing_fields))
        snapshot["degraded"] = degraded
        return snapshot

    async def collect(self, db) -> dict:
        snapshot: Dict[str, Any] = {"date": str(date.today())}
        sources: Dict[str, dict] = {}
        failure_reasons: List[dict] = []
        missing_fields: List[str] = []

        def record_source(name: str, status: str, fields: List[str], reason: Optional[str] = None, details: Optional[dict] = None) -> None:
            sources[name] = self._build_source_status(status, fields, reason=reason, details=details)
            if status != "success":
                failure_reasons.append({
                    "source": name,
                    "status": status,
                    "reason": reason or f"{name} degraded",
                    "fallback_used": status == "fallback",
                    "fields": list(fields),
                })
                if status == "fallback":
                    missing_fields.extend(fields)

        # 1. 恐贪指数
        try:
            from .sentiment import sentiment_analyzer
            index_klines = await db.get_klines("sh000001", limit=60)
            if not index_klines:
                raise ValueError("index klines empty")
            breadth = None
            try:
                breadth = await db.get_limit_up_stats()
            except Exception:
                pass
            fg = sentiment_analyzer.calculate_fear_greed_index(index_klines, breadth)
            snapshot["fear_greed_index"] = fg.get("index", 50)
            snapshot["fg_level"] = fg.get("level", "neutral")
            snapshot["fg_components"] = fg.get("components", {})
            record_source("fear_greed", "success", ["fear_greed_index", "fg_level", "fg_components"])
        except Exception as e:
            logger.warning("DataCollector: fear_greed failed: %s", e)
            snapshot["fear_greed_index"] = 50
            snapshot["fg_level"] = "neutral"
            snapshot["fg_components"] = {}
            record_source(
                "fear_greed",
                "fallback",
                ["fear_greed_index", "fg_level", "fg_components"],
                reason=f"fear_greed failed: {e}",
            )

        # 2. 因子IC历史
        factor_ic: Dict[str, float] = {}
        factor_ic_trend: Dict[str, str] = {}
        factor_ic_failures: List[dict] = []
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
            except Exception as exc:
                factor_ic_failures.append({"factor": fname, "reason": str(exc)})
        snapshot["factor_ic"] = factor_ic
        snapshot["factor_ic_trend"] = factor_ic_trend
        factor_ic_fields = ["factor_ic", "factor_ic_trend"]
        if factor_ic_failures and factor_ic:
            record_source(
                "factor_ic",
                "partial",
                factor_ic_fields,
                reason=f"{len(factor_ic_failures)} 个因子 IC 拉取失败",
                details={"failed_factors": factor_ic_failures},
            )
        elif factor_ic_failures:
            record_source(
                "factor_ic",
                "fallback",
                factor_ic_fields,
                reason=f"factor_ic failed: {len(factor_ic_failures)} 个因子拉取失败",
                details={"failed_factors": factor_ic_failures},
            )
        elif factor_ic:
            record_source("factor_ic", "success", factor_ic_fields)
        else:
            record_source(
                "factor_ic",
                "fallback",
                factor_ic_fields,
                reason="factor_ic history empty",
            )

        # 3. 北向资金 / 融资融券 / 板块资金流（直接调用 fund_flow 工具函数）
        snapshot["north_fund_3d_net"] = 0.0
        snapshot["margin_5d_change_pct"] = 0.0
        snapshot["hot_sectors"] = []
        snapshot["cold_sectors"] = []
        north_fund_ok = False
        try:
            from ..tools.fund_flow import get_north_fund
            nf = await asyncio.to_thread(get_north_fund, 5)
            if nf.get("success") and nf.get("data", {}).get("items"):
                items = nf["data"]["items"][:3]
                total_3d = sum(float(it.get("total") or 0) for it in items)
                snapshot["north_fund_3d_net"] = round(total_3d, 2)
                north_fund_ok = True
            else:
                record_source("north_fund", "fallback", ["north_fund_3d_net"], reason="north_fund returned empty items")
        except Exception as e:
            logger.debug("DataCollector: north_fund failed: %s", e)
            record_source("north_fund", "fallback", ["north_fund_3d_net"], reason=f"north_fund failed: {e}")
        if north_fund_ok:
            record_source("north_fund", "success", ["north_fund_3d_net"])

        margin_ok = False
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
                    margin_ok = True
                else:
                    record_source("margin_data", "fallback", ["margin_5d_change_pct"], reason="margin_data older balance is zero")
            else:
                record_source("margin_data", "fallback", ["margin_5d_change_pct"], reason="margin_data insufficient history")
        except Exception as e:
            logger.debug("DataCollector: margin_data failed: %s", e)
            record_source("margin_data", "fallback", ["margin_5d_change_pct"], reason=f"margin_data failed: {e}")
        if margin_ok:
            record_source("margin_data", "success", ["margin_5d_change_pct"])

        sector_flow_ok = False
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
                sector_flow_ok = True
            else:
                record_source("sector_fund_flow", "fallback", ["hot_sectors", "cold_sectors"], reason="sector_fund_flow returned empty data")
        except Exception as e:
            logger.debug("DataCollector: sector_fund_flow failed: %s", e)
            record_source("sector_fund_flow", "fallback", ["hot_sectors", "cold_sectors"], reason=f"sector_fund_flow failed: {e}")
        if sector_flow_ok:
            record_source("sector_fund_flow", "success", ["hot_sectors", "cold_sectors"])

        # 4. 种群状态
        try:
            counts = await db.count_strategies_by_type("listed")
            snapshot["category_counts"] = counts
            snapshot["listed_count"] = sum(counts.values())
            incubating = await db.count_strategies_by_type("incubating")
            snapshot["incubating_count"] = sum(incubating.values())
            record_source("strategy_population", "success", ["category_counts", "listed_count", "incubating_count"])
        except Exception:
            snapshot["category_counts"] = {}
            snapshot["listed_count"] = 0
            snapshot["incubating_count"] = 0
            record_source(
                "strategy_population",
                "fallback",
                ["category_counts", "listed_count", "incubating_count"],
                reason="strategy_population failed",
            )

        self._finalize_snapshot_contract(snapshot, sources, failure_reasons, missing_fields)

        # 持久化快照
        try:
            await db.save_daily_snapshot(date.today(), snapshot)
        except Exception as e:
            logger.warning("DataCollector: save snapshot failed: %s", e)

        return snapshot

class StrategySpawner:
    """根据每日数据快照生成候选策略"""

    def __init__(self):
        self.last_report: dict = {
            "summary": {
                "candidate_count": 0,
                "source_counts": {},
                "strategy_type_counts": {},
                "quota_fill_count": 0,
                "signal_trigger_count": 0,
                "threshold_hit_count": 0,
            }
        }

    def get_last_report(self) -> dict:
        return self.last_report

    @staticmethod
    def _threshold(field: str, operator: str, threshold: Any, actual: Any, label: Optional[str] = None) -> dict:
        item = {
            "field": field,
            "operator": operator,
            "threshold": threshold,
            "actual": actual,
            "matched": True,
        }
        if label:
            item["label"] = label
        return item

    @staticmethod
    def _build_generation_reason(
        source: str,
        reason: str,
        trigger_signal: Optional[dict] = None,
        trigger_thresholds: Optional[List[dict]] = None,
        quota_fill: Optional[dict] = None,
        kind: str = "signal_trigger",
    ) -> dict:
        return {
            "kind": kind,
            "source": source,
            "summary": reason,
            "trigger_signal": trigger_signal or {},
            "trigger_thresholds": list(trigger_thresholds or []),
            "quota_fill": quota_fill,
        }

    @staticmethod
    def _build_spawn_report(candidates: List[dict]) -> dict:
        source_counts: Dict[str, int] = {}
        strategy_type_counts: Dict[str, int] = {}
        quota_fill_count = 0
        signal_trigger_count = 0
        threshold_hit_count = 0
        for candidate in candidates:
            generation_reason = candidate.get("generation_reason") or {}
            source = str(generation_reason.get("source") or "unknown")
            strategy_type = str(candidate.get("strategy_type") or "unknown")
            source_counts[source] = source_counts.get(source, 0) + 1
            strategy_type_counts[strategy_type] = strategy_type_counts.get(strategy_type, 0) + 1
            threshold_hit_count += len(candidate.get("trigger_thresholds") or [])
            if candidate.get("quota_fill"):
                quota_fill_count += 1
            else:
                signal_trigger_count += 1
        return {
            "summary": {
                "candidate_count": len(candidates),
                "source_counts": source_counts,
                "strategy_type_counts": strategy_type_counts,
                "quota_fill_count": quota_fill_count,
                "signal_trigger_count": signal_trigger_count,
                "threshold_hit_count": threshold_hit_count,
            }
        }

    def spawn(self, snapshot: dict) -> List[dict]:
        candidates: List[dict] = []
        candidates += self._from_fear_greed(snapshot)
        candidates += self._from_factor_ic(snapshot)
        candidates += self._from_volatility(snapshot)
        candidates += self._from_fund_flow(snapshot)
        candidates += self._fill_gaps(snapshot)
        self.last_report = self._build_spawn_report(candidates)
        return candidates

    def _from_fear_greed(self, s: dict) -> List[dict]:
        out: List[dict] = []
        fg = s.get("fear_greed_index", 50)
        if fg < 30:
            out.append(self._make("rsi", {"rsi_period": 14, "oversold": 25, "overbought": 75},
                                  f"恐贪{fg}，恐惧区RSI抄底",
                                  source="fear_greed",
                                  trigger_signal={"field": "fear_greed_index", "value": fg, "level": "fear"},
                                  trigger_thresholds=[self._threshold("fear_greed_index", "<", 30, fg, "恐贪阈值")]))
            out.append(self._make("rsi", {"rsi_period": 6, "oversold": 20, "overbought": 80},
                                  f"恐贪{fg}，短周期RSI超跌",
                                  source="fear_greed",
                                  trigger_signal={"field": "fear_greed_index", "value": fg, "level": "fear"},
                                  trigger_thresholds=[self._threshold("fear_greed_index", "<", 30, fg, "恐贪阈值")]))
            out.append(self._make("value_factor", {"lookback": 60, "buy_quantile": 0.85, "sell_quantile": 0.15},
                                  f"恐贪{fg}，恐惧期精选价值",
                                  source="fear_greed",
                                  trigger_signal={"field": "fear_greed_index", "value": fg, "level": "fear"},
                                  trigger_thresholds=[self._threshold("fear_greed_index", "<", 30, fg, "恐贪阈值")]))
        elif fg > 70:
            out.append(self._make("momentum", {"lookback": 5, "threshold": 0.01},
                                  f"恐贪{fg}，贪婪期短周期动量",
                                  source="fear_greed",
                                  trigger_signal={"field": "fear_greed_index", "value": fg, "level": "greed"},
                                  trigger_thresholds=[self._threshold("fear_greed_index", ">", 70, fg, "恐贪阈值")]))
            out.append(self._make("momentum", {"lookback": 10, "threshold": 0.02},
                                  f"恐贪{fg}，贪婪期中周期动量",
                                  source="fear_greed",
                                  trigger_signal={"field": "fear_greed_index", "value": fg, "level": "greed"},
                                  trigger_thresholds=[self._threshold("fear_greed_index", ">", 70, fg, "恐贪阈值")]))
            out.append(self._make("growth_factor", {"lookback": 40, "buy_quantile": 0.85, "sell_quantile": 0.15},
                                  f"恐贪{fg}，贪婪期成长加速",
                                  source="fear_greed",
                                  trigger_signal={"field": "fear_greed_index", "value": fg, "level": "greed"},
                                  trigger_thresholds=[self._threshold("fear_greed_index", ">", 70, fg, "恐贪阈值")]))
            out.append(self._make("rsi", {"rsi_period": 14, "oversold": 35, "overbought": 65},
                                  f"恐贪{fg}，贪婪期RSI逃顶",
                                  source="fear_greed",
                                  trigger_signal={"field": "fear_greed_index", "value": fg, "level": "greed"},
                                  trigger_thresholds=[self._threshold("fear_greed_index", ">", 70, fg, "恐贪阈值")]))
        else:
            out.append(self._make("ma_cross", {"short_period": 5, "long_period": 20},
                                  f"恐贪{fg}，中性标准均线",
                                  source="fear_greed",
                                  trigger_signal={"field": "fear_greed_index", "value": fg, "level": "neutral"},
                                  trigger_thresholds=[
                                      self._threshold("fear_greed_index", ">=", 30, fg, "恐贪下界"),
                                      self._threshold("fear_greed_index", "<=", 70, fg, "恐贪上界"),
                                  ]))
            out.append(self._make("momentum", {"lookback": 20, "threshold": 0.02},
                                  f"恐贪{fg}，中性标准动量",
                                  source="fear_greed",
                                  trigger_signal={"field": "fear_greed_index", "value": fg, "level": "neutral"},
                                  trigger_thresholds=[
                                      self._threshold("fear_greed_index", ">=", 30, fg, "恐贪下界"),
                                      self._threshold("fear_greed_index", "<=", 70, fg, "恐贪上界"),
                                  ]))
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
                                              f"momentum IC={ic:.3f}上升，{lb}日动量",
                                              source="factor_ic",
                                              trigger_signal={"field": "factor_ic", "factor": fname, "value": ic, "trend": t},
                                              trigger_thresholds=[
                                                  self._threshold(f"factor_ic.{fname}", ">", 0.03, ic, "IC阈值"),
                                                  self._threshold(f"factor_ic_trend.{fname}", "==", "rising", t, "趋势阈值"),
                                              ]))
                elif fname == "value":
                    out.append(self._make("value_factor", {"lookback": 60, "buy_quantile": 0.8, "sell_quantile": 0.2},
                                          f"value IC={ic:.3f}上升",
                                          source="factor_ic",
                                          trigger_signal={"field": "factor_ic", "factor": fname, "value": ic, "trend": t},
                                          trigger_thresholds=[
                                              self._threshold(f"factor_ic.{fname}", ">", 0.03, ic, "IC阈值"),
                                              self._threshold(f"factor_ic_trend.{fname}", "==", "rising", t, "趋势阈值"),
                                          ]))
                elif fname == "quality":
                    out.append(self._make("quality_factor", {"lookback": 60, "buy_quantile": 0.8, "sell_quantile": 0.2},
                                          f"quality IC={ic:.3f}上升",
                                          source="factor_ic",
                                          trigger_signal={"field": "factor_ic", "factor": fname, "value": ic, "trend": t},
                                          trigger_thresholds=[
                                              self._threshold(f"factor_ic.{fname}", ">", 0.03, ic, "IC阈值"),
                                              self._threshold(f"factor_ic_trend.{fname}", "==", "rising", t, "趋势阈值"),
                                          ]))
                elif fname == "reversal":
                    out.append(self._make("rsi", {"rsi_period": 14, "oversold": 30, "overbought": 70},
                                          f"reversal IC={ic:.3f}上升，反转有效",
                                          source="factor_ic",
                                          trigger_signal={"field": "factor_ic", "factor": fname, "value": ic, "trend": t},
                                          trigger_thresholds=[
                                              self._threshold(f"factor_ic.{fname}", ">", 0.03, ic, "IC阈值"),
                                              self._threshold(f"factor_ic_trend.{fname}", "==", "rising", t, "趋势阈值"),
                                          ]))
            elif ic < -0.02 and t == "falling":
                if fname == "momentum":
                    out.append(self._make("rsi", {"rsi_period": 14, "oversold": 30, "overbought": 70},
                                          f"momentum IC={ic:.3f}下降，转反转",
                                          source="factor_ic",
                                          trigger_signal={"field": "factor_ic", "factor": fname, "value": ic, "trend": t},
                                          trigger_thresholds=[
                                              self._threshold(f"factor_ic.{fname}", "<", -0.02, ic, "IC阈值"),
                                              self._threshold(f"factor_ic_trend.{fname}", "==", "falling", t, "趋势阈值"),
                                          ]))

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
                              f"IC驱动多因子权重: {weights}",
                              source="factor_ic",
                              trigger_signal={"field": "factor_ic_weights", "value": weights},
                              trigger_thresholds=[
                                  self._threshold(
                                      "factor_ic_weights",
                                      "derived_from",
                                      {"positive_ic": 0.0, "trend_preference": "rising"},
                                      {"factor_ic": factor_ic, "factor_ic_trend": trend, "weights": weights},
                                      "权重派生规则",
                                  )
                              ]))
        return out

    def _from_volatility(self, s: dict) -> List[dict]:
        out: List[dict] = []
        vol = s.get("fg_components", {}).get("volatility", 50)
        if vol < 35:
            out.append(self._make("ma_cross", {"short_period": 10, "long_period": 60},
                                  f"波动率{vol}，高波动长周期均线",
                                  source="volatility",
                                  trigger_signal={"field": "fg_components.volatility", "value": vol},
                                  trigger_thresholds=[self._threshold("fg_components.volatility", "<", 35, vol, "波动率阈值")]))
            out.append(self._make("macro_timing", {"fear_threshold": 30, "greed_threshold": 70, "lookback": 30},
                                  f"波动率{vol}，高波动宏观择时",
                                  source="volatility",
                                  trigger_signal={"field": "fg_components.volatility", "value": vol},
                                  trigger_thresholds=[self._threshold("fg_components.volatility", "<", 35, vol, "波动率阈值")]))
        elif vol > 65:
            out.append(self._make("ma_cross", {"short_period": 3, "long_period": 15},
                                  f"波动率{vol}，低波动短周期均线",
                                  source="volatility",
                                  trigger_signal={"field": "fg_components.volatility", "value": vol},
                                  trigger_thresholds=[self._threshold("fg_components.volatility", ">", 65, vol, "波动率阈值")]))
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
                                  f"北向3日净流入{north_3d / 1e8:.0f}亿，成长加速",
                                  source="fund_flow",
                                  trigger_signal={"field": "north_fund_3d_net", "value": north_3d},
                                  trigger_thresholds=[self._threshold("north_fund_3d_net", ">", 5_000_000_000, north_3d, "北向净流入阈值")]))
            out.append(self._make("quality_factor",
                                  {"lookback": self._jitter(60, 40, 80), "buy_quantile": 0.8, "sell_quantile": 0.2},
                                  f"北向3日净流入{north_3d / 1e8:.0f}亿，质量优选",
                                  source="fund_flow",
                                  trigger_signal={"field": "north_fund_3d_net", "value": north_3d},
                                  trigger_thresholds=[self._threshold("north_fund_3d_net", ">", 5_000_000_000, north_3d, "北向净流入阈值")]))
        # 北向资金3日净流出 > 50亿 → 防御策略
        elif north_3d < -5_000_000_000:
            out.append(self._make("value_factor",
                                  {"lookback": self._jitter(60, 40, 80), "buy_quantile": 0.85, "sell_quantile": 0.15},
                                  f"北向3日净流出{abs(north_3d) / 1e8:.0f}亿，价值防御",
                                  source="fund_flow",
                                  trigger_signal={"field": "north_fund_3d_net", "value": north_3d},
                                  trigger_thresholds=[self._threshold("north_fund_3d_net", "<", -5_000_000_000, north_3d, "北向净流出阈值")]))
            out.append(self._make("macro_timing",
                                  {"fear_threshold": 30, "greed_threshold": 60, "lookback": self._jitter(25, 15, 35)},
                                  f"北向3日净流出{abs(north_3d) / 1e8:.0f}亿，宏观择时",
                                  source="fund_flow",
                                  trigger_signal={"field": "north_fund_3d_net", "value": north_3d},
                                  trigger_thresholds=[self._threshold("north_fund_3d_net", "<", -5_000_000_000, north_3d, "北向净流出阈值")]))

        # 融资余额5日增速 > 2% → 短周期动量
        if margin_5d > 2.0:
            out.append(self._make("momentum",
                                  {"lookback": self._jitter(5, 3, 10), "threshold": 0.01},
                                  f"融资5日增速{margin_5d:.1f}%，短周期动量",
                                  source="fund_flow",
                                  trigger_signal={"field": "margin_5d_change_pct", "value": margin_5d},
                                  trigger_thresholds=[self._threshold("margin_5d_change_pct", ">", 2.0, margin_5d, "融资增速阈值")]))
        # 融资余额5日下降 > 2% → RSI超跌
        elif margin_5d < -2.0:
            out.append(self._make("rsi",
                                  {"rsi_period": self._jitter(6, 4, 10), "oversold": 20, "overbought": 80},
                                  f"融资5日降速{abs(margin_5d):.1f}%，RSI超跌",
                                  source="fund_flow",
                                  trigger_signal={"field": "margin_5d_change_pct", "value": margin_5d},
                                  trigger_thresholds=[self._threshold("margin_5d_change_pct", "<", -2.0, margin_5d, "融资降速阈值")]))

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
                    quota_fill = {
                        "strategy_type": stype,
                        "current_count": current,
                        "minimum_required": minimum,
                        "gap_count": gap,
                        "slot_index": i + 1,
                    }
                    out.append(self._make(
                        stype,
                        params,
                        f"{stype}分类不足{minimum}个，补位#{i + 1}",
                        source="quota_fill",
                        trigger_signal={"field": f"category_counts.{stype}", "value": current},
                        trigger_thresholds=[self._threshold(f"category_counts.{stype}", "<", minimum, current, "分类最低配额")],
                        quota_fill=quota_fill,
                        kind="quota_fill",
                    ))
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
    def _make(
        strategy_type: str,
        params: dict,
        reason: str = "",
        *,
        source: str = "unknown",
        trigger_signal: Optional[dict] = None,
        trigger_thresholds: Optional[List[dict]] = None,
        quota_fill: Optional[dict] = None,
        kind: str = "signal_trigger",
    ) -> dict:
        generation_reason = StrategySpawner._build_generation_reason(
            source=source,
            reason=reason,
            trigger_signal=trigger_signal,
            trigger_thresholds=trigger_thresholds,
            quota_fill=quota_fill,
            kind=kind,
        )
        return {
            "strategy_type": strategy_type,
            "params": params,
            "spawn_reason": reason,
            "generation_reason": generation_reason,
            "trigger_signal": generation_reason["trigger_signal"],
            "trigger_thresholds": generation_reason["trigger_thresholds"],
            "quota_fill": quota_fill,
        }

class BacktestFilter:
    """回测筛选候选策略"""

    SHARPE_MIN = BACKTEST_DEFAULT_THRESHOLDS["sharpe_min"]
    MDD_MAX = BACKTEST_DEFAULT_THRESHOLDS["mdd_max"]
    TRADES_MIN = BACKTEST_DEFAULT_THRESHOLDS["trades_min"]

    def __init__(self):
        self.last_report: dict = {
            "summary": {
                "input_count": 0,
                "passed_count": 0,
                "failed_count": 0,
                "strategy_type_counts": {},
                "passed_strategy_type_counts": {},
                "failed_strategy_type_counts": {},
                "failed_reason_counts": {},
                "thresholds_by_type": {},
            },
            "passed": [],
            "failed": [],
        }

    def get_last_report(self) -> dict:
        return self.last_report

    @staticmethod
    def _count_by_strategy_type(items: List[dict]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in items:
            strategy_type = str(item.get("strategy_type") or "unknown")
            counts[strategy_type] = counts.get(strategy_type, 0) + 1
        return counts

    @staticmethod
    def _build_report_entry(candidate: dict) -> dict:
        return {
            "strategy_type": candidate.get("strategy_type"),
            "params": candidate.get("params"),
            "spawn_reason": candidate.get("spawn_reason"),
            "generation_reason": candidate.get("generation_reason") or {},
            "backtest_result": candidate.get("backtest_result") or {},
            "backtest_metrics": candidate.get("backtest_metrics") or {},
        }

    @staticmethod
    def _build_failed_metric(field: str, operator: str, threshold: Any, actual: Any, label: str) -> dict:
        return {
            "field": field,
            "operator": operator,
            "threshold": threshold,
            "actual": actual,
            "label": label,
        }

    def _get_thresholds(self, strategy_type: str) -> dict:
        return {
            **BACKTEST_DEFAULT_THRESHOLDS,
            **(BACKTEST_TYPE_THRESHOLDS.get(strategy_type) or {}),
        }

    def _build_last_report(self, candidates: List[dict], passed: List[dict], failed: List[dict]) -> dict:
        failed_reason_counts: Dict[str, int] = {}
        thresholds_by_type: Dict[str, dict] = {}
        for item in candidates:
            strategy_type = str(item.get("strategy_type") or "unknown")
            result = item.get("backtest_result") or {}
            thresholds_by_type[strategy_type] = result.get("thresholds") or self._get_thresholds(strategy_type)
        for item in failed:
            reason_code = str((item.get("backtest_result") or {}).get("reason_code") or "unknown")
            failed_reason_counts[reason_code] = failed_reason_counts.get(reason_code, 0) + 1
        return {
            "summary": {
                "input_count": len(candidates),
                "passed_count": len(passed),
                "failed_count": len(failed),
                "strategy_type_counts": self._count_by_strategy_type(candidates),
                "passed_strategy_type_counts": self._count_by_strategy_type(passed),
                "failed_strategy_type_counts": self._count_by_strategy_type(failed),
                "failed_reason_counts": failed_reason_counts,
                "thresholds_by_type": thresholds_by_type,
            },
            "passed": [self._build_report_entry(item) for item in passed],
            "failed": [self._build_report_entry(item) for item in failed],
        }

    async def filter(self, candidates: List[dict], db) -> List[dict]:
        from .backtest.engine import BacktestEngine
        passed: List[dict] = []
        failed: List[dict] = []
        for c in candidates:
            result = await self._test_one(c, db, BacktestEngine)
            c["backtest_result"] = result
            if result.get("passed"):
                c["backtest_metrics"] = result.get("metrics") or {}
                passed.append(c)
            else:
                c.pop("backtest_metrics", None)
                failed.append(c)
        self.last_report = self._build_last_report(candidates, passed, failed)
        return passed

    async def _test_one(self, candidate: dict, db, engine) -> dict:
        strategy_type = str(candidate.get("strategy_type") or "unknown")
        thresholds = self._get_thresholds(strategy_type)
        results: List[dict] = []
        successful_codes: List[str] = []
        skipped_codes: List[dict] = []
        failed_codes: List[dict] = []
        for code in REPRESENTATIVE_STOCKS:
            try:
                klines = await db.get_klines(code, limit=500)
                if not klines or len(klines) < 100:
                    skipped_codes.append({
                        "code": code,
                        "reason": "insufficient_klines",
                        "available": len(klines or []),
                    })
                    continue
                # run_backtest 是同步方法，用 to_thread 避免阻塞事件循环
                r = await asyncio.to_thread(
                    engine.run_backtest, code, klines, candidate["strategy_type"],
                    {**candidate["params"], "initial_capital": 100000, "commission": 0.00025}
                )
                if r.get("success"):
                    results.append(r["data"])
                    successful_codes.append(code)
                else:
                    failed_codes.append({"code": code, "reason": "backtest_failed"})
            except Exception:
                failed_codes.append({"code": code, "reason": "exception"})
                continue

        base_result = {
            "passed": False,
            "reason_code": "unknown",
            "reason": "初筛回测未完成",
            "strategy_type": strategy_type,
            "sample_count": len(results),
            "required_sample_count": thresholds["min_samples"],
            "evaluated_code_count": len(REPRESENTATIVE_STOCKS),
            "successful_codes": successful_codes,
            "skipped_codes": skipped_codes,
            "failed_codes": failed_codes,
            "thresholds": thresholds,
            "metrics": {},
            "failed_metric": None,
        }

        if len(results) < thresholds["min_samples"]:
            return {
                **base_result,
                "reason_code": "insufficient_samples",
                "reason": f"有效样本 {len(results)} 小于要求 {thresholds['min_samples']}",
                "failed_metric": self._build_failed_metric(
                    "sample_count", "<", thresholds["min_samples"], len(results), "有效样本数"
                ),
            }

        avg = {
            "sharpe_ratio": float(median([m["sharpe_ratio"] for m in results])),
            "total_return": float(median([m["total_return"] for m in results])),
            "max_drawdown": float(median([m["max_drawdown"] for m in results])),
            "win_rate": float(median([m.get("win_rate", 0) for m in results])),
            "trades_count": float(median([m["trades_count"] for m in results])),
        }

        if avg["sharpe_ratio"] < thresholds["sharpe_min"]:
            return {
                **base_result,
                "reason_code": "sharpe_below_threshold",
                "reason": f"Sharpe {avg['sharpe_ratio']:.4f} 低于阈值 {thresholds['sharpe_min']:.2f}",
                "metrics": avg,
                "failed_metric": self._build_failed_metric(
                    "sharpe_ratio", "<", thresholds["sharpe_min"], round(avg["sharpe_ratio"], 4), "Sharpe"
                ),
            }
        if abs(avg["max_drawdown"]) > thresholds["mdd_max"]:
            return {
                **base_result,
                "reason_code": "max_drawdown_above_threshold",
                "reason": f"回撤 {abs(avg['max_drawdown']):.4f} 高于阈值 {thresholds['mdd_max']:.2f}",
                "metrics": avg,
                "failed_metric": self._build_failed_metric(
                    "max_drawdown", ">", thresholds["mdd_max"], round(abs(avg["max_drawdown"]), 4), "最大回撤"
                ),
            }
        if avg["trades_count"] < thresholds["trades_min"]:
            return {
                **base_result,
                "reason_code": "trades_below_threshold",
                "reason": f"交易次数 {avg['trades_count']:.1f} 低于阈值 {thresholds['trades_min']}",
                "metrics": avg,
                "failed_metric": self._build_failed_metric(
                    "trades_count", "<", thresholds["trades_min"], round(avg["trades_count"], 4), "交易次数"
                ),
            }
        return {
            **base_result,
            "passed": True,
            "reason_code": "passed",
            "reason": "通过初筛回测",
            "metrics": avg,
        }


class Deduplicator:
    """去除与已有策略参数过于相似的候选"""

    THRESHOLD = 0.85
    VECTOR_TRIGGER_THRESHOLD = 0.65
    VECTOR_THRESHOLD = 0.93

    def __init__(self):
        self.last_report: dict = {
            "summary": {"input_count": 0, "kept_count": 0, "dropped_count": 0, "vector_checks": 0},
            "kept": [],
            "dropped": [],
        }
        self._behavior_cache: Dict[str, Optional[List[dict]]] = {}
        self._vector_engine = VectorSearchEngine(backend="index", allow_fallback=True)

    async def deduplicate(self, candidates: List[dict], db) -> List[dict]:
        existing: List[dict] = []
        for status in ("listed", "incubating"):
            try:
                rows = await db.list_strategies(status, limit=500)
                existing.extend(rows)
            except Exception:
                pass

        unique: List[dict] = []
        dropped: List[dict] = []
        seen = list(existing)
        vector_checks = 0
        for c in candidates:
            detail = await self._find_duplicate(c, seen, db)
            c["dedup_result"] = detail
            if detail.get("vector_checked"):
                vector_checks += 1
            if detail.get("duplicate"):
                dropped.append({**c})
                continue
            unique.append(c)
            seen.append(c)
        self.last_report = {
            "summary": {
                "input_count": len(candidates),
                "existing_count": len(existing),
                "kept_count": len(unique),
                "dropped_count": len(dropped),
                "vector_checks": vector_checks,
                "param_threshold": self.THRESHOLD,
                "vector_threshold": self.VECTOR_THRESHOLD,
            },
            "kept": [{
                "strategy_type": item.get("strategy_type"),
                "params": item.get("params"),
                "spawn_reason": item.get("spawn_reason"),
                "dedup_result": item.get("dedup_result"),
            } for item in unique],
            "dropped": [{
                "strategy_type": item.get("strategy_type"),
                "params": item.get("params"),
                "spawn_reason": item.get("spawn_reason"),
                "dedup_result": item.get("dedup_result"),
            } for item in dropped],
        }
        return unique

    async def _find_duplicate(self, candidate: dict, existing: list, db) -> dict:
        best_match: Optional[dict] = None
        suspicious: List[Tuple[dict, float]] = []
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
            match = {
                "matched_strategy_id": e.get("id"),
                "matched_name": e.get("name") or e.get("strategy_type"),
                "param_similarity": round(sim, 4),
            }
            if best_match is None or sim > best_match.get("param_similarity", 0):
                best_match = match
            if sim >= self.THRESHOLD:
                return {
                    "duplicate": True,
                    "duplicate_level": "parameter",
                    "match_type": "parameter",
                    "reason": f"参数相似度 {sim:.4f} ≥ 阈值 {self.THRESHOLD:.2f}",
                    "threshold": self.THRESHOLD,
                    "vector_threshold": self.VECTOR_THRESHOLD,
                    "vector_checked": False,
                    **match,
                }
            if sim >= self.VECTOR_TRIGGER_THRESHOLD:
                suspicious.append((e, sim))

        vector_detail = await self._vector_check(candidate, suspicious, db) if suspicious else None
        if vector_detail and vector_detail.get("similarity", 0) >= self.VECTOR_THRESHOLD:
            return {
                "duplicate": True,
                "duplicate_level": "vector",
                "match_type": "vector",
                "reason": f"行为向量相似度 {vector_detail['similarity']:.4f} ≥ 阈值 {self.VECTOR_THRESHOLD:.2f}",
                "threshold": self.THRESHOLD,
                "vector_threshold": self.VECTOR_THRESHOLD,
                "vector_checked": True,
                "param_similarity": round(vector_detail.get("param_similarity", 0.0), 4),
                "vector_similarity": round(vector_detail.get("similarity", 0.0), 4),
                "vector_backend": vector_detail.get("backend"),
                "matched_strategy_id": vector_detail.get("matched_strategy_id"),
                "matched_name": vector_detail.get("matched_name"),
            }

        return {
            "duplicate": False,
            "duplicate_level": "unique",
            "match_type": None,
            "reason": "未命中重复策略",
            "threshold": self.THRESHOLD,
            "vector_threshold": self.VECTOR_THRESHOLD,
            "vector_checked": vector_detail is not None,
            "param_similarity": round((best_match or {}).get("param_similarity", 0.0), 4),
            "vector_similarity": round((vector_detail or {}).get("similarity", 0.0), 4),
            "vector_backend": (vector_detail or {}).get("backend"),
            "matched_strategy_id": (vector_detail or best_match or {}).get("matched_strategy_id"),
            "matched_name": (vector_detail or best_match or {}).get("matched_name"),
        }

    async def _vector_check(self, candidate: dict, suspicious: List[Tuple[dict, float]], db) -> Optional[dict]:
        query_klines = await self._build_behavior_klines(candidate.get("strategy_type", ""), candidate.get("params") or {}, db)
        if not query_klines:
            return None

        candidate_klines_dict: Dict[str, List[dict]] = {}
        match_meta: Dict[str, dict] = {}
        for idx, (existing_item, param_similarity) in enumerate(suspicious):
            params = existing_item.get("params") or {}
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except Exception:
                    params = {}
            klines = await self._build_behavior_klines(existing_item.get("strategy_type", ""), params, db)
            if not klines:
                continue
            code = str(existing_item.get("id") or existing_item.get("name") or f"candidate_{idx}")
            candidate_klines_dict[code] = klines
            match_meta[code] = {
                "matched_strategy_id": existing_item.get("id"),
                "matched_name": existing_item.get("name") or existing_item.get("strategy_type"),
                "param_similarity": param_similarity,
            }
        if not candidate_klines_dict:
            return None

        results = self._vector_engine.find_similar_patterns(
            query_klines=query_klines,
            candidate_klines_dict=candidate_klines_dict,
            top_k=1,
            method="returns",
            metric="cosine",
            backend="index",
            allow_fallback=True,
        )
        if not results:
            return None
        top = results[0]
        meta = match_meta.get(str(top.get("code")), {})
        return {
            "similarity": float(top.get("similarity") or 0.0),
            "backend": self._vector_engine.last_backend_used,
            **meta,
        }

    async def _build_behavior_klines(self, strategy_type: str, params: dict, db) -> Optional[List[dict]]:
        cache_key = f"{strategy_type}:{json.dumps(params or {}, sort_keys=True, ensure_ascii=False, default=str)}"
        if cache_key in self._behavior_cache:
            return self._behavior_cache[cache_key]
        panels = await _build_strategy_panels(strategy_type, params, db, sample_size=4)
        series = panels.get("strategy_returns")
        if series is None or len(series) < 30:
            self._behavior_cache[cache_key] = None
            return None
        price = 100.0
        pseudo_klines: List[dict] = []
        for ret in np.asarray(series[-60:], dtype=np.float64):
            open_price = price
            price = open_price * (1 + float(ret))
            pseudo_klines.append({
                "open": round(open_price, 6),
                "high": round(max(open_price, price), 6),
                "low": round(min(open_price, price), 6),
                "close": round(price, 6),
                "volume": 1.0,
            })
        self._behavior_cache[cache_key] = pseudo_klines
        return pseudo_klines

    def get_last_report(self) -> dict:
        return self.last_report

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


async def _update_strategy_status(db, strategy_id: str, status: str, **kwargs) -> None:
    try:
        await db.update_strategy_status(strategy_id, status, **kwargs)
    except TypeError:
        await db.update_strategy_status(strategy_id, status)


async def _build_strategy_panels(strategy_type: str, params: dict, db, sample_size: int = 6) -> dict:
    klass = StrategyRegistry.get(strategy_type)
    if klass is None:
        return {}
    factor_columns: List[np.ndarray] = []
    return_columns: List[np.ndarray] = []
    strategy_series: List[np.ndarray] = []
    holdings: List[dict] = []
    for code in REPRESENTATIVE_STOCKS[:sample_size]:
        try:
            klines = await db.get_klines(code, limit=220)
            ordered = normalize_klines(klines)
            closes = np.array([float(k.get("close", 0) or 0) for k in ordered], dtype=np.float64)
            volumes = np.array([float(k.get("volume", 0) or 0) for k in ordered], dtype=np.float64)
            if len(closes) < 90:
                continue
            instance = klass()
            instance.set_parameters(params or {})
            try:
                signals = np.asarray(instance.generate_signals(closes, volumes), dtype=np.float64)
            except TypeError:
                signals = np.asarray(instance.generate_signals(closes), dtype=np.float64)
            aligned_signals = signals[:-1]
            aligned_returns = np.diff(closes) / np.maximum(closes[:-1], 1e-12)
            if len(aligned_signals) < 60 or len(aligned_signals) != len(aligned_returns):
                continue
            factor_columns.append(aligned_signals[-120:])
            return_columns.append(aligned_returns[-120:])
            strategy_series.append((aligned_signals[-120:] * aligned_returns[-120:]).astype(np.float64))
            latest_signal = float(aligned_signals[-1]) if len(aligned_signals) else 0.0
            if latest_signal != 0:
                holdings.append({"code": code, "weight": abs(latest_signal), "value": 100000.0 * abs(latest_signal)})
        except Exception:
            continue
    if len(factor_columns) < 3:
        return {}
    min_len = min(len(col) for col in factor_columns)
    factor_panel = np.column_stack([col[-min_len:] for col in factor_columns])
    return_panel = np.column_stack([col[-min_len:] for col in return_columns])
    strategy_returns = np.mean(np.column_stack([col[-min_len:] for col in strategy_series]), axis=1)
    total_weight = sum(h["weight"] for h in holdings) or 1.0
    holdings = [{**h, "weight": float(h["weight"] / total_weight)} for h in holdings] or [{"code": "cash", "weight": 1.0, "value": 100000.0}]
    return {
        "factor_panel": factor_panel,
        "return_panel": return_panel,
        "strategy_returns": strategy_returns,
        "holdings": holdings,
    }


async def _run_validation_report(strategy_type: str, params: dict, db) -> dict | None:
    panels = await _build_strategy_panels(strategy_type, params, db)
    factor_panel = panels.get("factor_panel")
    return_panel = panels.get("return_panel")
    if factor_panel is None or return_panel is None:
        return None
    pipeline = FactorValidationPipeline(validation_parallel=False)
    return pipeline.run(factor_panel, return_panel, factor_name=f"strategy:{strategy_type}", validation_parallel=False)


async def _run_risk_report(strategy_type: str, params: dict, db) -> dict | None:
    panels = await _build_strategy_panels(strategy_type, params, db)
    strategy_returns = panels.get("strategy_returns")
    holdings = panels.get("holdings")
    if strategy_returns is None or holdings is None or len(strategy_returns) == 0:
        return None
    var_report = RiskModel.calculate_var(strategy_returns.tolist(), confidence=0.95, portfolio_value=1000000)
    stress_report = RiskModel.stress_test(holdings, scenario="market_crash")
    return {
        "var_percent": round(float(var_report.get("var_percent", 0.0)), 4),
        "cvar_percent": round(float(var_report.get("cvar_percent", 0.0)), 4),
        "stress_loss_percent": round(float(stress_report.get("loss_percent", 0.0)), 4),
        "scenario": stress_report.get("scenario"),
    }


class StrategySubmitter:
    """创建策略记录并提交质检"""

    @staticmethod
    def _build_quality_report(
        strategy_id: str,
        candidate: dict,
        snapshot: dict,
        backtest_metrics: dict,
        quality_gate: dict,
        validation_report: Optional[dict],
        risk_report: Optional[dict],
        final_status: str,
    ) -> dict:
        from ..tools.managers.strategy_manager import _build_quality_report

        return _build_quality_report(
            strategy_id=strategy_id,
            strategy_type=candidate.get("strategy_type"),
            quality_gate=quality_gate,
            validation_report=validation_report,
            risk_report=risk_report,
            dedup_report=candidate.get("dedup_result") or {},
            backtest_metrics=backtest_metrics or {},
            snapshot={
                "date": snapshot.get("date"),
                "fg_level": snapshot.get("fg_level"),
                "fear_greed_index": snapshot.get("fear_greed_index"),
            },
            status_after_review=final_status,
            review_source="strategy_factory_submit",
            report_type="submission",
            spawn_reason=candidate.get("spawn_reason"),
        )

    async def submit(self, candidates: List[dict], snapshot: dict, db) -> dict:
        from ..tools.managers.strategy_manager import _normalize_quality_gate_result, _run_quality_gate
        created = 0
        submitted = 0
        passed = 0
        submitted_items: List[dict] = []

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
                    "tags": list(dict.fromkeys(["auto_generated", "factory", c["strategy_type"], *(c.get("tags") or [])])),
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

                validation_report = await _run_validation_report(c["strategy_type"], c.get("params", {}), db)
                if validation_report:
                    rating = validation_report.get("rating", {})
                    await db.save_strategy_metrics(sid, "validation", {
                        "grade": rating.get("grade"),
                        "total_score": rating.get("total_score"),
                        "oos_rank_ic": validation_report.get("walk_forward", {}).get("oos_rank_ic_mean"),
                        "recommendation": rating.get("recommendation"),
                    })

                risk_report = await _run_risk_report(c["strategy_type"], c.get("params", {}), db)
                if risk_report:
                    await db.save_strategy_metrics(sid, "risk", risk_report)

                # 提交质检
                await _update_strategy_status(
                    db,
                    sid,
                    "submitted",
                    actor_id="strategy_factory",
                    reason="factory_submit",
                    metadata={
                        "spawn_reason": c.get("spawn_reason"),
                        "dedup_result": c.get("dedup_result") or {},
                    },
                )
                gate = await _run_quality_gate(db, {**data, "status": "submitted"})
                if validation_report and validation_report.get("rating", {}).get("grade") == "D":
                    gate = _normalize_quality_gate_result({
                        **gate,
                        "passed": False,
                        "reasons": [*(gate.get("reasons") or []), "validation_grade_d"],
                    })
                submitted += 1

                final_status = "incubating" if gate.get("passed") else "rejected"
                quality_report = self._build_quality_report(
                    strategy_id=sid,
                    candidate=c,
                    snapshot=snapshot,
                    backtest_metrics=metrics,
                    quality_gate=gate,
                    validation_report=validation_report,
                    risk_report=risk_report,
                    final_status=final_status,
                )
                if hasattr(db, "save_strategy_quality_report"):
                    await db.save_strategy_quality_report(sid, "submission", quality_report)

                incubation_binding = None
                vector_profile = None
                if gate.get("passed"):
                    await _update_strategy_status(
                        db,
                        sid,
                        "incubating",
                        actor_id="strategy_factory",
                        reason="quality_gate_passed",
                        metadata={"quality_gate": gate, "validation_grade": quality_report["summary"].get("validation_grade")},
                    )
                    try:
                        from .incubation import get_strategy_incubation_service
                        incubation_binding = await get_strategy_incubation_service().ensure_account(db, {**data, 'id': sid, 'name': name}, source_run_id=snapshot.get('date'))
                    except Exception as exc:
                        logger.warning("StrategyFactory: ensure incubation account failed for %s: %s", sid, exc)
                    try:
                        from .vector_platform import get_strategy_vector_platform
                        vector_profile = await get_strategy_vector_platform().build_strategy_profile(db, {**data, 'id': sid, 'name': name})
                    except Exception as exc:
                        logger.warning("StrategyFactory: build vector profile failed for %s: %s", sid, exc)
                    if c.get('experiment_id') and hasattr(db, 'save_strategy_generation_experiment'):
                        await db.save_strategy_generation_experiment({
                            'experiment_id': c.get('experiment_id'),
                            'strategy_id': sid,
                            'source': c.get('source') or 'strategy_factory',
                            'generator_type': c.get('generator_type') or 'rule',
                            'optimizer_type': c.get('optimizer_type'),
                            'status': 'accepted',
                            'hypothesis': c.get('spawn_reason'),
                            'prompt': str(snapshot.get('date') or ''),
                            'parameters': c.get('params') or {},
                            'strategy_spec': {'strategy_type': c.get('strategy_type'), 'name': name},
                            'evaluation': {'quality_gate': gate, 'validation_report': validation_report or {}, 'risk_report': risk_report or {}},
                            'result': {'strategy_id': sid, 'status': 'incubating'},
                            'parent_experiment_id': None,
                            'artifact_id': None,
                        })
                    passed += 1
                else:
                    await _update_strategy_status(
                        db,
                        sid,
                        "rejected",
                        actor_id="strategy_factory",
                        reason="quality_gate_failed",
                        metadata={"quality_gate": gate, "validation_grade": quality_report["summary"].get("validation_grade")},
                    )
                    if c.get('experiment_id') and hasattr(db, 'save_strategy_generation_experiment'):
                        await db.save_strategy_generation_experiment({
                            'experiment_id': c.get('experiment_id'),
                            'strategy_id': sid,
                            'source': c.get('source') or 'strategy_factory',
                            'generator_type': c.get('generator_type') or 'rule',
                            'optimizer_type': c.get('optimizer_type'),
                            'status': 'rejected',
                            'hypothesis': c.get('spawn_reason'),
                            'prompt': str(snapshot.get('date') or ''),
                            'parameters': c.get('params') or {},
                            'strategy_spec': {'strategy_type': c.get('strategy_type'), 'name': name},
                            'evaluation': {'quality_gate': gate, 'validation_report': validation_report or {}, 'risk_report': risk_report or {}},
                            'result': {'strategy_id': sid, 'status': 'rejected'},
                            'parent_experiment_id': None,
                            'artifact_id': None,
                        })

                submitted_items.append({
                    "strategy_id": sid,
                    "experiment_id": c.get("experiment_id"),
                    "generator_type": c.get("generator_type"),
                    "name": name,
                    "status": final_status,
                    "passed": bool(gate.get("passed")),
                    "reasons": gate.get("reasons") or [],
                    "dedup_result": c.get("dedup_result") or {},
                    "incubation_account_id": ((incubation_binding or {}).get("account") or {}).get("id"),
                    "vector_profile_id": (vector_profile or {}).get("id"),
                })

                # 记录血缘
                try:
                    await db.save_strategy_lineage(sid, None, c.get("spawn_reason", ""), snapshot)
                except Exception:
                    pass

            except Exception as e:
                logger.warning("StrategySubmitter: failed for %s: %s", c.get("strategy_type"), e)

        return {
            "created": created,
            "submitted": submitted,
            "passed_quality_gate": passed,
            "strategies": submitted_items,
        }

class EliminationChecker:
    """检查已上架策略是否应该淘汰"""

    # 策略类型 → 适宜的市场环境
    _REGIME_MAP = {
        "momentum": ("greed", "extreme_greed"),
        "growth_factor": ("greed", "extreme_greed", "neutral"),
        "value_factor": ("fear", "extreme_fear", "neutral"),
        "rsi": ("fear", "extreme_fear"),
        "macro_timing": ("fear", "extreme_fear", "neutral"),
        "ma_cross": ("neutral", "greed", "extreme_greed"),
        "quality_factor": ("neutral", "greed", "extreme_greed"),
        "multi_factor": ("neutral", "fear", "greed", "extreme_fear", "extreme_greed"),
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
                validation_metrics = next((row for row in metrics_list if row.get("period") == "validation"), {})
                risk_metrics = next((row for row in metrics_list if row.get("period") == "risk"), {})
                quality_report = None
                get_quality_report = getattr(db, "get_strategy_quality_report", None)
                if callable(get_quality_report):
                    try:
                        quality_report = await get_quality_report(s["id"])
                    except TypeError:
                        quality_report = None
                if quality_report:
                    validation_metrics = quality_report.get("validation_report") or validation_metrics
                    risk_metrics = quality_report.get("risk_report") or risk_metrics

                mdd = abs(float(m.get("max_drawdown") or 0))
                sharpe = float(m.get("sharpe_ratio") or 0)
                win_rate = float(m.get("win_rate") or 0)
                validation_grade = validation_metrics.get("grade") or validation_metrics.get("rating", {}).get("grade")
                var_percent = float(risk_metrics.get("var_percent") or 0)
                cvar_percent = float(risk_metrics.get("cvar_percent") or 0)
                stress_loss_percent = float(risk_metrics.get("stress_loss_percent") or 0)

                if mdd > 0.30:
                    red_flags.append(f"回撤{mdd:.1%}>30%")
                if sharpe < 0:
                    red_flags.append(f"Sharpe {sharpe:.2f}<0")
                if 0 < win_rate < 0.30:
                    red_flags.append(f"胜率{win_rate:.1%}<30%")
                if validation_grade == "D":
                    red_flags.append("验证评级为D")
                if var_percent > 4.0:
                    red_flags.append(f"VaR {var_percent:.2f}%>4%")
                if cvar_percent > 6.0:
                    red_flags.append(f"CVaR {cvar_percent:.2f}%>6%")
                if stress_loss_percent <= -25.0:
                    red_flags.append(f"压力测试损失{stress_loss_percent:.1f}%")

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
                    await _update_strategy_status(
                        db,
                        s["id"],
                        "deprecated",
                        actor_id="elimination_checker",
                        reason="elimination_checker_triggered",
                        metadata={"red_flags": red_flags, "fg_level": current_fg_level},
                    )
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
        results: Dict[str, Any] = {
            "run_id": f"factory_run_{int(start.timestamp())}_{uuid4().hex[:8]}",
            "started_at": start.isoformat(),
            "status": "running",
            "summary": {},
            "stages": {},
        }

        logger.info("StrategyFactory: starting daily cycle")

        try:
            collector = DataCollector()
            snapshot = await collector.collect(db)
            results["snapshot_summary"] = {
                "date": snapshot.get("date"),
                "fear_greed": snapshot.get("fear_greed_index"),
                "fear_greed_index": snapshot.get("fear_greed_index"),
                "fg_level": snapshot.get("fg_level"),
                "listed_count": snapshot.get("listed_count", 0),
                "incubating_count": snapshot.get("incubating_count", 0),
                "degraded": bool(snapshot.get("degraded")),
                "completion_ratio": (snapshot.get("completeness") or {}).get("completion_ratio", 1.0),
                "missing_sources": (snapshot.get("completeness") or {}).get("missing_sources") or [],
                "failure_reason_count": len(snapshot.get("failure_reasons") or []),
            }
            results["stages"]["collect"] = {
                "ok": True,
                **results["snapshot_summary"],
                "completeness": snapshot.get("completeness") or {},
            }

            spawner = StrategySpawner()
            candidates = spawner.spawn(snapshot)
            spawn_report = spawner.get_last_report() if hasattr(spawner, "get_last_report") else {
                "summary": {"candidate_count": len(candidates)}
            }
            results["stages"]["spawn"] = {"ok": True, "count": len(candidates), **spawn_report}

            ai_cycle = {"generated_count": 0, "candidates": []}
            try:
                from .strategy_autonomy import get_strategy_autonomy_service
                ai_cycle = await get_strategy_autonomy_service().generate_factory_candidates(db, snapshot, limit=3)
                ai_candidates = ai_cycle.get('candidates') or []
                candidates = [*candidates, *ai_candidates]
                results["stages"]["autonomy"] = {
                    "ok": True,
                    "generated_count": ai_cycle.get('generated_count', len(ai_candidates)),
                    "experiment_count": len(ai_cycle.get('experiments') or []),
                    "task_run_id": ai_cycle.get('task_run_id'),
                }
            except Exception as exc:
                logger.warning("StrategyFactory: autonomy cycle failed: %s", exc)
                results["stages"]["autonomy"] = {"ok": False, "error": str(exc), "generated_count": 0}

            bt_filter = BacktestFilter()
            passed = await bt_filter.filter(candidates, db)
            backtest_report = bt_filter.get_last_report() if hasattr(bt_filter, "get_last_report") else {
                "summary": {
                    "input_count": len(candidates),
                    "passed_count": len(passed),
                    "failed_count": max(len(candidates) - len(passed), 0),
                    "failed_reason_counts": {},
                    "thresholds_by_type": {},
                },
                "passed": [],
                "failed": [],
            }
            backtest_summary = backtest_report.get("summary") or {}
            results["stages"]["backtest"] = {
                "ok": True,
                "input_count": backtest_summary.get("input_count", len(candidates)),
                "passed_count": backtest_summary.get("passed_count", len(passed)),
                "failed_count": backtest_summary.get("failed_count", max(len(candidates) - len(passed), 0)),
                **backtest_report,
            }

            dedup = Deduplicator()
            unique = await dedup.deduplicate(passed, db)
            results["stages"]["deduplicate"] = {"ok": True, **dedup.get_last_report()}

            submitter = StrategySubmitter()
            submit_result = await submitter.submit(unique, snapshot, db)
            results["stages"]["submit"] = {"ok": True, **submit_result}

            eliminator = EliminationChecker()
            eliminated = await eliminator.check(db, snapshot.get("fg_level", "neutral"))
            results["stages"]["elimination"] = {"ok": True, "count": len(eliminated), "items": eliminated}

            elapsed = (datetime.now() - start).total_seconds()
            results["status"] = "success"
            results["completed_at"] = datetime.now().isoformat()
            results["elapsed_seconds"] = round(elapsed, 1)
            results["summary"] = {
                "fear_greed": snapshot.get("fear_greed_index"),
                "listed_count": snapshot.get("listed_count", 0),
                "snapshot_degraded": bool(snapshot.get("degraded")),
                "snapshot_completion_ratio": (snapshot.get("completeness") or {}).get("completion_ratio", 1.0),
                "snapshot_failure_reason_count": len(snapshot.get("failure_reasons") or []),
                "candidates_spawned": len(candidates),
                "autonomy_generated": (results.get("stages", {}).get("autonomy") or {}).get("generated_count", 0),
                "quota_fill_candidates": (spawn_report.get("summary") or {}).get("quota_fill_count", 0),
                "signal_trigger_candidates": (spawn_report.get("summary") or {}).get("signal_trigger_count", len(candidates)),
                "candidates_passed_backtest": len(passed),
                "candidates_failed_backtest": backtest_summary.get("failed_count", max(len(candidates) - len(passed), 0)),
                "backtest_failed_reason_counts": backtest_summary.get("failed_reason_counts") or {},
                "candidates_after_dedup": len(unique),
                "submitted": submit_result.get("submitted", 0),
                "passed_quality_gate": submit_result.get("passed_quality_gate", 0),
                "eliminated": len(eliminated),
                "elapsed_seconds": round(elapsed, 1),
            }

            logger.info(
                "StrategyFactory: completed in %.1fs — spawned %d, backtest passed %d, "
                "dedup %d, submitted %s, eliminated %d",
                elapsed,
                len(candidates),
                len(passed),
                len(unique),
                submit_result,
                len(eliminated),
            )
        except Exception as e:
            elapsed = (datetime.now() - start).total_seconds()
            logger.error("StrategyFactory: run_once failed: %s", e, exc_info=True)
            results["status"] = "failed"
            results["completed_at"] = datetime.now().isoformat()
            results["elapsed_seconds"] = round(elapsed, 1)
            results["error"] = str(e)
            results["summary"] = {"elapsed_seconds": round(elapsed, 1), "error": str(e)}

        self.last_run = datetime.now()
        self.last_result = results
        if hasattr(db, "save_strategy_factory_run"):
            try:
                await db.save_strategy_factory_run(results)
            except Exception as exc:
                logger.warning(
                    "StrategyFactory: failed to persist run %s: %s",
                    results.get("run_id"),
                    exc,
                )
        return results

    def status(self) -> dict:
        return {
            "running": self._running,
            "run_time": str(self.run_time),
            "last_run": str(self.last_run) if self.last_run else None,
            "last_result": self.last_result,
            "last_summary": (self.last_result or {}).get("summary") if self.last_result else None,
        }


_factory_scheduler: Optional[StrategyFactoryScheduler] = None


def get_strategy_factory_scheduler() -> StrategyFactoryScheduler:
    global _factory_scheduler
    if _factory_scheduler is None:
        _factory_scheduler = StrategyFactoryScheduler()
    return _factory_scheduler
