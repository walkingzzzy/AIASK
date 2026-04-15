from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd


for proxy_key in (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
):
    os.environ.pop(proxy_key, None)
os.environ.setdefault("NO_PROXY", "*")
os.environ.setdefault("no_proxy", "*")


REPO_ROOT = Path(__file__).resolve().parents[1]
for package_src in (
    REPO_ROOT / "packages" / "strategy-factory" / "src",
    REPO_ROOT / "packages" / "akshare-mcp" / "src",
):
    if str(package_src) not in sys.path:
        sys.path.insert(0, str(package_src))


import akshare as ak  # noqa: E402
from strategy_factory.api.contracts import FactoryBacktestAssumptions  # noqa: E402


ETF_SYMBOL = "sh510300"
ETF_CODE = "510300"
ETF_NAME = "华泰柏瑞沪深300ETF"
ETF_INCEPTION_DATE = pd.Timestamp("2012-05-04")
BACKTEST_END_DATE = pd.Timestamp("2026-04-10")
MONTHLY_CONTRIBUTION = 10_000.0
REPORT_DIR = REPO_ROOT / "reports" / "backtests"


@dataclass
class Lot:
    lot_id: int
    buy_date: pd.Timestamp
    shares: int
    entry_price_with_cost: float
    gross_invested_cash: float
    source: str
    scheduled_for_sell: bool = False
    exit_date: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None

    @property
    def is_open(self) -> bool:
        return self.exit_date is None and self.shares > 0


@dataclass
class BacktestMetrics:
    total_capital_injected: float
    total_investment_months: int
    buy_trade_count: int
    sell_trade_count: int
    total_trade_count: int
    final_total_asset: float
    total_return: float
    cagr: float
    max_drawdown: float
    average_exposure: float
    max_exposure: float
    dividend_event_count: int
    dividend_reinvest_buy_count: int
    carry_funded_months: int = 0
    zero_external_months: int = 0


@dataclass
class StrategyRun:
    name: str
    description: str
    metrics: BacktestMetrics
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    monthly_funding: pd.DataFrame
    extra: dict[str, Any]


@dataclass
class OptimizationCandidate:
    ma_window: int
    rsi_floor: int
    rsi_cap: int
    sell_rsi: int
    use_slope: bool
    metrics: BacktestMetrics


def _round_down_lot(shares: float, lot_size: int) -> int:
    return int(math.floor(shares / lot_size) * lot_size)


def _calc_buy_order(cash_amount: float, price: float, assumptions: FactoryBacktestAssumptions) -> tuple[int, float, float, float]:
    if cash_amount <= 0 or price <= 0:
        return 0, 0.0, 0.0, 0.0
    slippage_rate = float(assumptions.slippage_bps) / 10000.0
    execution_price = price * (1.0 + slippage_rate)
    cost_per_share = execution_price * (1.0 + assumptions.commission_rate)
    shares = _round_down_lot(cash_amount / cost_per_share, assumptions.min_trade_lot)
    if shares <= 0:
        return 0, 0.0, execution_price, 0.0
    gross_notional = shares * execution_price
    commission = gross_notional * assumptions.commission_rate
    total_cost = gross_notional + commission
    return shares, total_cost, execution_price, commission


def _calc_sell_order(
    shares: int,
    price: float,
    assumptions: FactoryBacktestAssumptions,
    *,
    sell_tax_rate: float,
) -> tuple[float, float, float]:
    if shares <= 0 or price <= 0:
        return 0.0, 0.0, 0.0
    slippage_rate = float(assumptions.slippage_bps) / 10000.0
    execution_price = price * (1.0 - slippage_rate)
    gross_notional = shares * execution_price
    commission = gross_notional * assumptions.commission_rate
    tax = gross_notional * sell_tax_rate
    net_proceeds = gross_notional - commission - tax
    return net_proceeds, execution_price, commission + tax


def _compute_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean().replace(0.0, np.nan)
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def load_market_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    price_df = ak.fund_etf_hist_sina(symbol=ETF_SYMBOL).copy()
    price_df["date"] = pd.to_datetime(price_df["date"])
    price_df = (
        price_df.loc[price_df["date"] <= BACKTEST_END_DATE, ["date", "open", "high", "low", "close", "volume", "amount"]]
        .sort_values("date")
        .reset_index(drop=True)
    )
    dividend_df = ak.fund_etf_dividend_sina(symbol=ETF_SYMBOL).copy()
    dividend_df["ex_date"] = pd.to_datetime(dividend_df["日期"])
    dividend_df = dividend_df.loc[dividend_df["ex_date"] <= BACKTEST_END_DATE, ["ex_date", "累计分红"]].sort_values("ex_date").reset_index(drop=True)
    dividend_df["per_share_dividend"] = dividend_df["累计分红"].diff().fillna(dividend_df["累计分红"])
    return price_df, dividend_df


def build_trading_calendar(price_df: pd.DataFrame, dividend_df: pd.DataFrame) -> tuple[pd.Index, set[pd.Timestamp], dict[pd.Timestamp, pd.Timestamp | None]]:
    trade_dates = pd.Index(price_df["date"])
    monthly_schedule: set[pd.Timestamp] = set()
    for month in pd.period_range(trade_dates.min().to_period("M"), BACKTEST_END_DATE.to_period("M"), freq="M"):
        target_date = pd.Timestamp(year=month.year, month=month.month, day=26)
        idx = trade_dates.searchsorted(target_date)
        if idx < len(trade_dates):
            scheduled_date = pd.Timestamp(trade_dates[idx])
            if scheduled_date <= BACKTEST_END_DATE:
                monthly_schedule.add(scheduled_date)

    next_trade_after_ex: dict[pd.Timestamp, pd.Timestamp | None] = {}
    for ex_date in dividend_df["ex_date"]:
        idx = trade_dates.searchsorted(ex_date)
        if idx < len(trade_dates) and pd.Timestamp(trade_dates[idx]) == pd.Timestamp(ex_date):
            idx += 1
        next_trade_after_ex[pd.Timestamp(ex_date)] = pd.Timestamp(trade_dates[idx]) if idx < len(trade_dates) else None
    return trade_dates, monthly_schedule, next_trade_after_ex


def build_indicator_frame(price_df: pd.DataFrame) -> pd.DataFrame:
    indicators = price_df[["date", "close"]].copy()
    indicators["rsi14"] = _compute_rsi(indicators["close"], window=14)
    indicators["ma80"] = indicators["close"].rolling(80).mean()
    indicators["ma80_slope20"] = indicators["ma80"].diff(20)
    indicators["ma150"] = indicators["close"].rolling(150).mean()
    indicators["ma150_slope40"] = indicators["ma150"].diff(40)
    return indicators.set_index("date")


def _build_next_trade_map(trade_dates: pd.Index) -> dict[pd.Timestamp, pd.Timestamp | None]:
    return {
        pd.Timestamp(trade_dates[idx]): pd.Timestamp(trade_dates[idx + 1]) if idx + 1 < len(trade_dates) else None
        for idx in range(len(trade_dates))
    }


def _compute_metrics(
    equity_curve: pd.DataFrame,
    trades: pd.DataFrame,
    monthly_funding: pd.DataFrame,
    *,
    dividend_event_count: int,
) -> BacktestMetrics:
    total_capital_injected = float(monthly_funding["external_injection"].sum()) if not monthly_funding.empty else 0.0
    buy_trade_count = int((trades["side"] == "buy").sum()) if not trades.empty else 0
    sell_trade_count = int((trades["side"] == "sell").sum()) if not trades.empty else 0
    dividend_reinvest_buy_count = int((trades["reason"] == "dividend_reinvest").sum()) if not trades.empty else 0
    total_investment_months = int(monthly_funding["schedule_hit"].sum()) if not monthly_funding.empty else 0
    final_total_asset = float(equity_curve["total_asset"].iloc[-1]) if not equity_curve.empty else 0.0
    total_return = (final_total_asset / total_capital_injected - 1.0) if total_capital_injected > 0 else 0.0
    nav = equity_curve["tw_nav"].astype(float)
    running_max = nav.cummax()
    max_drawdown = abs(float((nav / running_max - 1.0).min())) if not nav.empty else 0.0
    start_date = pd.Timestamp(equity_curve["date"].iloc[0]) if not equity_curve.empty else BACKTEST_END_DATE
    end_date = pd.Timestamp(equity_curve["date"].iloc[-1]) if not equity_curve.empty else BACKTEST_END_DATE
    years = max((end_date - start_date).days / 365.2425, 0.0)
    cagr = float(nav.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 and nav.iloc[-1] > 0 else 0.0
    average_exposure = float(equity_curve["exposure"].mean()) if not equity_curve.empty else 0.0
    max_exposure = float(equity_curve["exposure"].max()) if not equity_curve.empty else 0.0
    carry_funded_months = int((monthly_funding["carry_used"] > 0).sum()) if not monthly_funding.empty else 0
    zero_external_months = int((monthly_funding["external_injection"] == 0).sum()) if not monthly_funding.empty else 0

    return BacktestMetrics(
        total_capital_injected=total_capital_injected,
        total_investment_months=total_investment_months,
        buy_trade_count=buy_trade_count,
        sell_trade_count=sell_trade_count,
        total_trade_count=buy_trade_count + sell_trade_count,
        final_total_asset=final_total_asset,
        total_return=total_return,
        cagr=cagr,
        max_drawdown=max_drawdown,
        average_exposure=average_exposure,
        max_exposure=max_exposure,
        dividend_event_count=int(dividend_event_count),
        dividend_reinvest_buy_count=dividend_reinvest_buy_count,
        carry_funded_months=carry_funded_months,
        zero_external_months=zero_external_months,
    )


def simulate_monthly_dca(
    price_df: pd.DataFrame,
    dividend_df: pd.DataFrame,
    monthly_schedule: set[pd.Timestamp],
    next_trade_after_ex: dict[pd.Timestamp, pd.Timestamp | None],
    assumptions: FactoryBacktestAssumptions,
    *,
    name: str,
    description: str,
    fixed_external_injection: bool,
    take_profit_pct: float | None,
) -> StrategyRun:
    trade_dates = pd.Index(price_df["date"])
    next_trade_map = _build_next_trade_map(trade_dates)
    dividend_dates = set(dividend_df["ex_date"])

    cash_pool = 0.0
    dividend_carry = 0.0
    pending_dividend_reinvest: dict[pd.Timestamp, float] = {}
    pending_sell_lot_ids: dict[pd.Timestamp, set[int]] = {}
    open_lots: list[Lot] = []
    trade_rows: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    monthly_rows: list[dict[str, Any]] = []
    tw_nav = 1.0
    previous_total_asset: float | None = None
    next_lot_id = 0

    for row in price_df.itertuples(index=False):
        trade_date = pd.Timestamp(row.date)
        day_open = float(row.open)
        day_close = float(row.close)
        external_flow = 0.0

        eligible_dividend_shares = sum(lot.shares for lot in open_lots if lot.is_open)
        if trade_date in dividend_dates:
            per_share_dividend = float(dividend_df.loc[dividend_df["ex_date"] == trade_date, "per_share_dividend"].sum())
            dividend_cash = eligible_dividend_shares * per_share_dividend
            next_trade = next_trade_after_ex.get(trade_date)
            if next_trade is not None and dividend_cash > 0:
                pending_dividend_reinvest[next_trade] = pending_dividend_reinvest.get(next_trade, 0.0) + dividend_cash

        if trade_date in pending_sell_lot_ids:
            for lot_id in sorted(pending_sell_lot_ids.pop(trade_date)):
                for lot in open_lots:
                    if lot.lot_id != lot_id or not lot.is_open:
                        continue
                    net_proceeds, execution_price, sell_cost = _calc_sell_order(
                        lot.shares,
                        day_open,
                        assumptions,
                        sell_tax_rate=0.0,
                    )
                    cash_pool += net_proceeds
                    trade_rows.append(
                        {
                            "date": trade_date.strftime("%Y-%m-%d"),
                            "side": "sell",
                            "shares": lot.shares,
                            "price": execution_price,
                            "cash_amount": net_proceeds,
                            "commission_and_tax": sell_cost,
                            "reason": "take_profit",
                            "lot_id": lot.lot_id,
                            "source": lot.source,
                        }
                    )
                    lot.exit_date = trade_date
                    lot.exit_price = execution_price
                    break

        schedule_hit = trade_date in monthly_schedule
        carry_used = 0.0
        external_injection = 0.0
        scheduled_budget = MONTHLY_CONTRIBUTION if schedule_hit else 0.0
        monthly_order_cash = 0.0
        if schedule_hit:
            if fixed_external_injection:
                external_injection = MONTHLY_CONTRIBUTION
                external_flow += external_injection
                cash_pool += external_injection
                monthly_order_cash = cash_pool
            else:
                carry_used = min(cash_pool, MONTHLY_CONTRIBUTION)
                external_injection = MONTHLY_CONTRIBUTION - carry_used
                external_flow += external_injection
                cash_pool -= carry_used
                monthly_order_cash = carry_used + external_injection

            monthly_buy_shares, monthly_buy_cost, monthly_exec_price, monthly_buy_commission = _calc_buy_order(
                monthly_order_cash,
                day_close,
                assumptions,
            )
            monthly_residual_cash = monthly_order_cash - monthly_buy_cost
            if monthly_buy_shares > 0:
                if fixed_external_injection:
                    cash_pool = monthly_residual_cash
                else:
                    cash_pool += monthly_residual_cash
                open_lots.append(
                    Lot(
                        lot_id=next_lot_id,
                        buy_date=trade_date,
                        shares=monthly_buy_shares,
                        entry_price_with_cost=monthly_exec_price * (1.0 + assumptions.commission_rate),
                        gross_invested_cash=monthly_buy_cost,
                        source="monthly",
                    )
                )
                trade_rows.append(
                    {
                        "date": trade_date.strftime("%Y-%m-%d"),
                        "side": "buy",
                        "shares": monthly_buy_shares,
                        "price": monthly_exec_price,
                        "cash_amount": monthly_buy_cost,
                        "commission_and_tax": monthly_buy_commission,
                        "reason": "monthly_dca",
                        "lot_id": next_lot_id,
                        "source": "monthly",
                    }
                )
                next_lot_id += 1
            else:
                if fixed_external_injection:
                    cash_pool = monthly_order_cash
                else:
                    cash_pool += monthly_order_cash

        if trade_date in pending_dividend_reinvest:
            dividend_carry += pending_dividend_reinvest.pop(trade_date)
            dividend_buy_shares, dividend_buy_cost, dividend_exec_price, dividend_buy_commission = _calc_buy_order(
                dividend_carry,
                day_close,
                assumptions,
            )
            if dividend_buy_shares > 0:
                dividend_residual_cash = dividend_carry - dividend_buy_cost
                open_lots.append(
                    Lot(
                        lot_id=next_lot_id,
                        buy_date=trade_date,
                        shares=dividend_buy_shares,
                        entry_price_with_cost=dividend_exec_price * (1.0 + assumptions.commission_rate),
                        gross_invested_cash=dividend_buy_cost,
                        source="dividend",
                    )
                )
                trade_rows.append(
                    {
                        "date": trade_date.strftime("%Y-%m-%d"),
                        "side": "buy",
                        "shares": dividend_buy_shares,
                        "price": dividend_exec_price,
                        "cash_amount": dividend_buy_cost,
                        "commission_and_tax": dividend_buy_commission,
                        "reason": "dividend_reinvest",
                        "lot_id": next_lot_id,
                        "source": "dividend",
                    }
                )
                next_lot_id += 1
                dividend_carry = dividend_residual_cash

        if take_profit_pct is not None:
            next_trade = next_trade_map.get(trade_date)
            if next_trade is not None:
                for lot in open_lots:
                    if not lot.is_open or lot.scheduled_for_sell or lot.buy_date >= trade_date:
                        continue
                    if day_close >= lot.entry_price_with_cost * (1.0 + take_profit_pct):
                        pending_sell_lot_ids.setdefault(next_trade, set()).add(lot.lot_id)
                        lot.scheduled_for_sell = True

        live_lots = [lot for lot in open_lots if lot.is_open]
        market_value = sum(lot.shares for lot in live_lots) * day_close
        pending_dividend_cash = float(sum(pending_dividend_reinvest.values()))
        total_asset = market_value + cash_pool + dividend_carry + pending_dividend_cash
        exposure = (market_value / total_asset) if total_asset > 0 else 0.0
        if previous_total_asset is not None and previous_total_asset > 0:
            daily_return = (total_asset - external_flow) / previous_total_asset - 1.0
            tw_nav *= 1.0 + daily_return
        previous_total_asset = total_asset

        equity_rows.append(
            {
                "date": trade_date.strftime("%Y-%m-%d"),
                "total_asset": total_asset,
                "market_value": market_value,
                "cash_pool": cash_pool,
                "dividend_carry": dividend_carry,
                "pending_dividend_cash": pending_dividend_cash,
                "external_flow": external_flow,
                "exposure": exposure,
                "tw_nav": tw_nav,
                "open_lot_count": len(live_lots),
            }
        )
        monthly_rows.append(
            {
                "date": trade_date.strftime("%Y-%m-%d"),
                "schedule_hit": schedule_hit,
                "carry_used": carry_used,
                "external_injection": external_injection,
                "scheduled_budget": scheduled_budget,
            }
        )

    equity_curve = pd.DataFrame(equity_rows)
    trades = pd.DataFrame(trade_rows)
    monthly_funding = pd.DataFrame(monthly_rows)
    metrics = _compute_metrics(
        equity_curve,
        trades,
        monthly_funding,
        dividend_event_count=len(dividend_df),
    )
    return StrategyRun(
        name=name,
        description=description,
        metrics=metrics,
        equity_curve=equity_curve,
        trades=trades,
        monthly_funding=monthly_funding,
        extra={
            "take_profit_pct": take_profit_pct,
            "fixed_external_injection": fixed_external_injection,
        },
    )


def simulate_regime_strategy(
    price_df: pd.DataFrame,
    dividend_df: pd.DataFrame,
    monthly_schedule: set[pd.Timestamp],
    next_trade_after_ex: dict[pd.Timestamp, pd.Timestamp | None],
    assumptions: FactoryBacktestAssumptions,
    indicators: pd.DataFrame,
    *,
    ma_window: int,
    rsi_floor: int,
    rsi_cap: int,
    sell_rsi: int,
    use_slope: bool,
) -> StrategyRun:
    trade_dates = pd.Index(price_df["date"])
    next_trade_map = _build_next_trade_map(trade_dates)
    dividend_dates = set(dividend_df["ex_date"])
    ma_column = f"ma{ma_window}"
    slope_column = f"{ma_column}_slope20" if ma_window == 80 else f"{ma_column}_slope40"

    shares_held = 0
    cash_pool = 0.0
    dividend_carry = 0.0
    pending_dividend_reinvest: dict[pd.Timestamp, float] = {}
    pending_full_sell = False
    trade_rows: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    monthly_rows: list[dict[str, Any]] = []
    tw_nav = 1.0
    previous_total_asset: float | None = None

    for row in price_df.itertuples(index=False):
        trade_date = pd.Timestamp(row.date)
        day_open = float(row.open)
        day_close = float(row.close)
        external_flow = 0.0

        if trade_date in dividend_dates:
            per_share_dividend = float(dividend_df.loc[dividend_df["ex_date"] == trade_date, "per_share_dividend"].sum())
            dividend_cash = shares_held * per_share_dividend
            next_trade = next_trade_after_ex.get(trade_date)
            if next_trade is not None and dividend_cash > 0:
                pending_dividend_reinvest[next_trade] = pending_dividend_reinvest.get(next_trade, 0.0) + dividend_cash

        if pending_full_sell and shares_held > 0:
            net_proceeds, execution_price, sell_cost = _calc_sell_order(
                shares_held,
                day_open,
                assumptions,
                sell_tax_rate=0.0,
            )
            cash_pool += net_proceeds
            trade_rows.append(
                {
                    "date": trade_date.strftime("%Y-%m-%d"),
                    "side": "sell",
                    "shares": shares_held,
                    "price": execution_price,
                    "cash_amount": net_proceeds,
                    "commission_and_tax": sell_cost,
                    "reason": "regime_exit",
                    "lot_id": None,
                    "source": "position",
                }
            )
            shares_held = 0
        pending_full_sell = False

        schedule_hit = trade_date in monthly_schedule
        if schedule_hit:
            cash_pool += MONTHLY_CONTRIBUTION
            external_flow += MONTHLY_CONTRIBUTION

        if trade_date in pending_dividend_reinvest:
            dividend_carry += pending_dividend_reinvest.pop(trade_date)

        rsi_value = float(indicators.at[trade_date, "rsi14"]) if pd.notna(indicators.at[trade_date, "rsi14"]) else np.nan
        ma_value = float(indicators.at[trade_date, ma_column]) if pd.notna(indicators.at[trade_date, ma_column]) else np.nan
        slope_value = float(indicators.at[trade_date, slope_column]) if pd.notna(indicators.at[trade_date, slope_column]) else np.nan

        bullish = (
            not np.isnan(ma_value)
            and day_close > ma_value
            and (not use_slope or np.isnan(slope_value) or slope_value > 0)
            and (np.isnan(rsi_value) or rsi_value >= rsi_floor)
            and (np.isnan(rsi_value) or rsi_value <= rsi_cap)
        )
        bearish = (
            not np.isnan(ma_value)
            and day_close < ma_value
            and (not use_slope or (not np.isnan(slope_value) and slope_value < 0))
            and (np.isnan(rsi_value) or rsi_value <= sell_rsi)
        )

        if bullish:
            # Keep dividend reinvestment independent from regime cash deployment so
            # the optimized strategy follows the same reinvestment semantics as
            # the monthly DCA strategies.
            available_cash = cash_pool
            buy_shares, buy_cost, execution_price, buy_commission = _calc_buy_order(
                available_cash,
                day_close,
                assumptions,
            )
            if buy_shares > 0:
                cash_pool -= buy_cost
                shares_held += buy_shares
                trade_rows.append(
                    {
                        "date": trade_date.strftime("%Y-%m-%d"),
                        "side": "buy",
                        "shares": buy_shares,
                        "price": execution_price,
                        "cash_amount": buy_cost,
                        "commission_and_tax": buy_commission,
                        "reason": "regime_entry",
                        "lot_id": None,
                        "source": "position",
                    }
                )
        elif bearish and shares_held > 0:
            next_trade = next_trade_map.get(trade_date)
            if next_trade is not None:
                pending_full_sell = True

        # Dividend reinvestment should happen on the first trade after ex-date
        # regardless of whether the regime is currently bullish or bearish.
        dividend_buy_shares, dividend_buy_cost, dividend_exec_price, dividend_buy_commission = _calc_buy_order(
            dividend_carry,
            day_close,
            assumptions,
        )
        if dividend_buy_shares > 0:
            shares_held += dividend_buy_shares
            dividend_carry -= dividend_buy_cost
            trade_rows.append(
                {
                    "date": trade_date.strftime("%Y-%m-%d"),
                    "side": "buy",
                    "shares": dividend_buy_shares,
                    "price": dividend_exec_price,
                    "cash_amount": dividend_buy_cost,
                    "commission_and_tax": dividend_buy_commission,
                    "reason": "dividend_reinvest",
                    "lot_id": None,
                    "source": "dividend",
                }
            )

        pending_dividend_cash = float(sum(pending_dividend_reinvest.values()))
        market_value = shares_held * day_close
        total_asset = market_value + cash_pool + dividend_carry + pending_dividend_cash
        exposure = (market_value / total_asset) if total_asset > 0 else 0.0
        if previous_total_asset is not None and previous_total_asset > 0:
            daily_return = (total_asset - external_flow) / previous_total_asset - 1.0
            tw_nav *= 1.0 + daily_return
        previous_total_asset = total_asset

        equity_rows.append(
            {
                "date": trade_date.strftime("%Y-%m-%d"),
                "total_asset": total_asset,
                "market_value": market_value,
                "cash_pool": cash_pool,
                "dividend_carry": dividend_carry,
                "pending_dividend_cash": pending_dividend_cash,
                "external_flow": external_flow,
                "exposure": exposure,
                "tw_nav": tw_nav,
                "open_lot_count": 1 if shares_held > 0 else 0,
            }
        )
        monthly_rows.append(
            {
                "date": trade_date.strftime("%Y-%m-%d"),
                "schedule_hit": schedule_hit,
                "carry_used": 0.0,
                "external_injection": MONTHLY_CONTRIBUTION if schedule_hit else 0.0,
                "scheduled_budget": MONTHLY_CONTRIBUTION if schedule_hit else 0.0,
            }
        )

    equity_curve = pd.DataFrame(equity_rows)
    trades = pd.DataFrame(trade_rows)
    monthly_funding = pd.DataFrame(monthly_rows)
    metrics = _compute_metrics(
        equity_curve,
        trades,
        monthly_funding,
        dividend_event_count=len(dividend_df),
    )
    return StrategyRun(
        name="optimized_regime",
        description="MA/RSI 动态仓位：月度入金入现金池，满足趋势条件时集中投入，跌破阈值后次日开盘清仓。",
        metrics=metrics,
        equity_curve=equity_curve,
        trades=trades,
        monthly_funding=monthly_funding,
        extra={
            "ma_window": ma_window,
            "rsi_floor": rsi_floor,
            "rsi_cap": rsi_cap,
            "sell_rsi": sell_rsi,
            "use_slope": use_slope,
        },
    )


def search_optimization_candidates(
    price_df: pd.DataFrame,
    dividend_df: pd.DataFrame,
    monthly_schedule: set[pd.Timestamp],
    next_trade_after_ex: dict[pd.Timestamp, pd.Timestamp | None],
    assumptions: FactoryBacktestAssumptions,
    indicators: pd.DataFrame,
) -> list[OptimizationCandidate]:
    candidates: list[OptimizationCandidate] = []
    grid = [
        (80, 40, 95, 55, False),
        (80, 45, 95, 55, False),
        (80, 55, 95, 55, False),
        (80, 40, 85, 55, False),
        (80, 40, 95, 50, False),
        (150, 45, 90, 45, True),
        (150, 45, 90, 40, True),
        (150, 45, 90, 40, False),
    ]
    for ma_window, rsi_floor, rsi_cap, sell_rsi, use_slope in grid:
        result = simulate_regime_strategy(
            price_df,
            dividend_df,
            monthly_schedule,
            next_trade_after_ex,
            assumptions,
            indicators,
            ma_window=ma_window,
            rsi_floor=rsi_floor,
            rsi_cap=rsi_cap,
            sell_rsi=sell_rsi,
            use_slope=use_slope,
        )
        candidates.append(
            OptimizationCandidate(
                ma_window=ma_window,
                rsi_floor=rsi_floor,
                rsi_cap=rsi_cap,
                sell_rsi=sell_rsi,
                use_slope=use_slope,
                metrics=result.metrics,
            )
        )
    candidates.sort(key=lambda item: (item.metrics.cagr, -item.metrics.max_drawdown), reverse=True)
    return candidates


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _currency(value: float) -> str:
    return f"{value:,.2f}"


def _save_strategy_artifacts(strategy: StrategyRun) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    strategy.equity_curve.to_csv(REPORT_DIR / f"{strategy.name}_equity_curve.csv", index=False)
    strategy.trades.to_csv(REPORT_DIR / f"{strategy.name}_trades.csv", index=False)


def render_markdown_report(
    price_df: pd.DataFrame,
    dividend_df: pd.DataFrame,
    assumptions: FactoryBacktestAssumptions,
    scheme1: StrategyRun,
    scheme2: StrategyRun,
    optimized: StrategyRun,
    candidates: list[OptimizationCandidate],
) -> str:
    doubled_threshold = scheme1.metrics.cagr * 2.0
    best_candidate = candidates[0]
    doubling_feasible = best_candidate.metrics.cagr >= doubled_threshold and best_candidate.metrics.max_drawdown <= scheme1.metrics.max_drawdown

    lines = [
        f"# {ETF_NAME}（{ETF_CODE}.SH）回测对比报告",
        "",
        f"- 回测区间：{price_df['date'].iloc[0].strftime('%Y-%m-%d')} 至 {BACKTEST_END_DATE.strftime('%Y-%m-%d')}",
        f"- 基金成立日：{ETF_INCEPTION_DATE.strftime('%Y-%m-%d')}；首个可交易日：{price_df['date'].iloc[0].strftime('%Y-%m-%d')}",
        f"- 日线样本数：{len(price_df)}",
        f"- 分红事件数：{len(dividend_df)}",
        f"- 成本口径：commission_rate={assumptions.commission_rate:.5f}，slippage_bps={assumptions.slippage_bps:.1f}，ETF 卖出印花税按 0 处理",
        f"- 分红复投：按除息日后的首个交易日收盘价，按整手（{assumptions.min_trade_lot} 份）自动复投，剩余现金滚存",
        f"- 方案二现金池规则：后续每月定投先用回笼现金，不足部分再补新钱；单月计划投入上限保持 10,000 元，不把回笼资金放大成加仓杠杆",
        "",
        "## 核心结果",
        "",
        "| 策略 | 累计总投入 | 定投次数 | 买入笔数 | 卖出笔数 | 期末总资产 | 总收益率 | CAGR | 最大回撤 | 平均仓位 | 最高仓位 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for strategy in (scheme1, scheme2, optimized):
        metrics = strategy.metrics
        lines.append(
            "| "
            + " | ".join(
                [
                    strategy.name,
                    _currency(metrics.total_capital_injected),
                    str(metrics.total_investment_months),
                    str(metrics.buy_trade_count),
                    str(metrics.sell_trade_count),
                    _currency(metrics.final_total_asset),
                    _pct(metrics.total_return),
                    _pct(metrics.cagr),
                    _pct(metrics.max_drawdown),
                    _pct(metrics.average_exposure),
                    _pct(metrics.max_exposure),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 方案说明",
            "",
            f"- `{scheme1.name}`：每月 26 日顺延到下一交易日，固定新增外部资金 10,000 元，并在当日收盘买入；不做止盈卖出。",
            f"- `{scheme2.name}`：每月计划投入 10,000 元；若现金池足够则优先使用回笼资金；单 lot 收盘浮盈达到 20% 后，于下一交易日开盘卖出。",
            f"- `{optimized.name}`：固定每月新增 10,000 元，但先进入现金池；当日收盘满足 `close > MA{optimized.extra['ma_window']}` 且 RSI14 处于 [{optimized.extra['rsi_floor']}, {optimized.extra['rsi_cap']}] 区间时，立刻把现金池打满；若跌破阈值且 RSI14 <= {optimized.extra['sell_rsi']}，下一交易日开盘清仓。",
            "",
            "## 优化搜索结论",
            "",
            f"- 基准方案一 CAGR 为 {_pct(scheme1.metrics.cagr)}，要实现“提升 1 倍以上”，优化方案至少要达到 {_pct(doubled_threshold)}。",
            f"- 本次搜索里 CAGR 最高的候选参数是 `MA{best_candidate.ma_window} / RSI floor {best_candidate.rsi_floor} / cap {best_candidate.rsi_cap} / sell RSI {best_candidate.sell_rsi} / use_slope={best_candidate.use_slope}`，对应 CAGR {_pct(best_candidate.metrics.cagr)}、最大回撤 {_pct(best_candidate.metrics.max_drawdown)}、平均仓位 {_pct(best_candidate.metrics.average_exposure)}。",
            f"- 是否达到“年化翻倍且风险可控”：{'是' if doubling_feasible else '否'}。在当前 510300 的现货 long-only、无杠杆约束下，已测试的 RSI / 均线 / 动态仓位组合没有把 CAGR 提升到基准的 2 倍，同时还维持在不高于基准回撤的水平。",
            "",
            "## 观察与结论",
            "",
            f"- 方案一的优势是仓位长期接近满仓，最终资产最高；缺点是资金占用和回撤都最大，最大回撤达到 {_pct(scheme1.metrics.max_drawdown)}。",
            f"- 方案二显著降低了新资金需求，总外部投入只有 {_currency(scheme2.metrics.total_capital_injected)}，最大回撤压到 {_pct(scheme2.metrics.max_drawdown)}；但因为大量时间停留在现金池，平均仓位只有 {_pct(scheme2.metrics.average_exposure)}，CAGR 与方案一接近，没有被明显抬升。",
            f"- 优化策略把最大回撤进一步压到 {_pct(optimized.metrics.max_drawdown)} 左右，平均仓位约 {_pct(optimized.metrics.average_exposure)}，但年化仍只比方案一略高，说明 510300 更适合做风险收缩，而不是靠轻量技术指标把 long-only 年化直接翻倍。",
            "",
            "## 文件输出",
            "",
            "- `scheme1_equity_curve.csv` / `scheme2_equity_curve.csv` / `optimized_regime_equity_curve.csv`：每日资产、仓位和 TWR NAV。",
            "- `scheme1_trades.csv` / `scheme2_trades.csv` / `optimized_regime_trades.csv`：逐笔交易明细。",
        ]
    )
    return "\n".join(lines)


def build_summary_payload(
    price_df: pd.DataFrame,
    dividend_df: pd.DataFrame,
    assumptions: FactoryBacktestAssumptions,
    scheme1: StrategyRun,
    scheme2: StrategyRun,
    optimized: StrategyRun,
    candidates: list[OptimizationCandidate],
) -> dict[str, Any]:
    return {
        "instrument": {
            "code": f"{ETF_CODE}.SH",
            "name": ETF_NAME,
            "inception_date": ETF_INCEPTION_DATE.strftime("%Y-%m-%d"),
            "first_trade_date": price_df["date"].iloc[0].strftime("%Y-%m-%d"),
            "end_date": BACKTEST_END_DATE.strftime("%Y-%m-%d"),
            "price_rows": int(len(price_df)),
            "dividend_rows": int(len(dividend_df)),
        },
        "assumptions": {
            "commission_rate": assumptions.commission_rate,
            "slippage_bps": assumptions.slippage_bps,
            "slippage_model": assumptions.slippage_model,
            "min_trade_lot": assumptions.min_trade_lot,
            "sell_tax_rate": 0.0,
            "monthly_contribution": MONTHLY_CONTRIBUTION,
            "dividend_reinvest_policy": "reinvest_on_next_trade_close_with_lot_rounding",
            "scheme2_cash_pool_rule": "use_recycled_cash_first_then_inject_shortfall_only",
        },
        "strategies": {
            strategy.name: {
                "description": strategy.description,
                "metrics": asdict(strategy.metrics),
                "extra": strategy.extra,
            }
            for strategy in (scheme1, scheme2, optimized)
        },
        "optimization_candidates": [
            {
                "ma_window": candidate.ma_window,
                "rsi_floor": candidate.rsi_floor,
                "rsi_cap": candidate.rsi_cap,
                "sell_rsi": candidate.sell_rsi,
                "use_slope": candidate.use_slope,
                "metrics": asdict(candidate.metrics),
            }
            for candidate in candidates
        ],
        "dividend_events": [
            {
                "ex_date": row.ex_date.strftime("%Y-%m-%d"),
                "per_share_dividend": float(row.per_share_dividend),
            }
            for row in dividend_df.itertuples(index=False)
        ],
    }


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    price_df, dividend_df = load_market_data()
    trade_dates, monthly_schedule, next_trade_after_ex = build_trading_calendar(price_df, dividend_df)
    indicators = build_indicator_frame(price_df)

    assumptions = FactoryBacktestAssumptions(
        commission_rate=0.00025,
        slippage_bps=0.0,
        slippage_model="fixed",
        min_trade_lot=100,
        sell_tax_rate=0.0,
        market_ruleset="cn_equity",
    )

    scheme1 = simulate_monthly_dca(
        price_df,
        dividend_df,
        monthly_schedule,
        next_trade_after_ex,
        assumptions,
        name="scheme1",
        description="每月 26 日顺延收盘买入，固定新增外部资金 10,000 元，只买不卖。",
        fixed_external_injection=True,
        take_profit_pct=None,
    )
    scheme2 = simulate_monthly_dca(
        price_df,
        dividend_df,
        monthly_schedule,
        next_trade_after_ex,
        assumptions,
        name="scheme2",
        description="每月计划投入 10,000 元，优先使用现金池；单 lot 收盘浮盈达到 20% 后次日开盘止盈。",
        fixed_external_injection=False,
        take_profit_pct=0.20,
    )
    candidates = search_optimization_candidates(
        price_df,
        dividend_df,
        monthly_schedule,
        next_trade_after_ex,
        assumptions,
        indicators,
    )
    best = candidates[0]
    optimized = simulate_regime_strategy(
        price_df,
        dividend_df,
        monthly_schedule,
        next_trade_after_ex,
        assumptions,
        indicators,
        ma_window=best.ma_window,
        rsi_floor=best.rsi_floor,
        rsi_cap=best.rsi_cap,
        sell_rsi=best.sell_rsi,
        use_slope=best.use_slope,
    )

    for strategy in (scheme1, scheme2, optimized):
        _save_strategy_artifacts(strategy)

    summary_payload = build_summary_payload(
        price_df,
        dividend_df,
        assumptions,
        scheme1,
        scheme2,
        optimized,
        candidates,
    )
    json_path = REPORT_DIR / "510300_backtest_summary_20260410.json"
    json_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown_report = render_markdown_report(
        price_df,
        dividend_df,
        assumptions,
        scheme1,
        scheme2,
        optimized,
        candidates,
    )
    markdown_path = REPORT_DIR / "510300_backtest_report_20260410.md"
    markdown_path.write_text(markdown_report, encoding="utf-8")

    print(markdown_report)
    print()
    print(f"[saved] {json_path}")
    print(f"[saved] {markdown_path}")
    print(f"[saved] {REPORT_DIR / 'scheme1_equity_curve.csv'}")
    print(f"[saved] {REPORT_DIR / 'scheme1_trades.csv'}")
    print(f"[saved] {REPORT_DIR / 'scheme2_equity_curve.csv'}")
    print(f"[saved] {REPORT_DIR / 'scheme2_trades.csv'}")
    print(f"[saved] {REPORT_DIR / 'optimized_regime_equity_curve.csv'}")
    print(f"[saved] {REPORT_DIR / 'optimized_regime_trades.csv'}")


if __name__ == "__main__":
    main()
