/**
 * 回测指标面板
 */

import React from 'react';

interface BacktestPanelProps {
    title?: string;
    data: unknown;
}

type BacktestSummary = {
    id?: string;
    strategy?: string;
    stocks?: string[] | string;
    period?: string;
    initialCapital?: number;
    finalCapital?: number;
    totalReturn?: number | string;
    annualReturn?: number | string;
    maxDrawdown?: number | string;
    sharpeRatio?: number | string;
    sortinoRatio?: number | string;
    annualVolatility?: number | string;
    calmarRatio?: number | string;
    winRate?: number | string;
    profitFactor?: number | string;
    avgWin?: number | string;
    avgLoss?: number | string;
    expectancy?: number | string;
    avgHoldingDays?: number | string;
    exposureRate?: number | string;
    maxConsecutiveLoss?: number | string;
    tradesCount?: number | string;
    orderCost?: {
        commissionRate?: number;
        minCommission?: number;
        stampDutyRate?: number;
        slippageRate?: number;
    };
};

const formatNumber = (value: unknown, decimals: number = 2): string => {
    if (typeof value === 'number' && Number.isFinite(value)) {
        return value.toFixed(decimals);
    }
    if (typeof value === 'string' && value.trim().length > 0) {
        return value;
    }
    return '--';
};

const formatPercent = (value: unknown): string => {
    if (typeof value === 'number' && Number.isFinite(value)) {
        return `${value.toFixed(2)}%`;
    }
    if (typeof value === 'string' && value.trim().length > 0) {
        return value.includes('%') ? value : `${value}%`;
    }
    return '--';
};

const resolveSummary = (payload: unknown): BacktestSummary | null => {
    if (!payload || typeof payload !== 'object') return null;
    const data = payload as Record<string, unknown>;
    if (data.summary && typeof data.summary === 'object') {
        return data.summary as BacktestSummary;
    }
    return data as BacktestSummary;
};

const BacktestPanel: React.FC<BacktestPanelProps> = ({ title, data }) => {
    const summary = resolveSummary(data);
    if (!summary) return null;

    const params = (data && typeof data === 'object' ? (data as { params?: Record<string, unknown> }).params : undefined) || {};
    const orderCost = summary.orderCost
        || (params as { order_cost?: Record<string, number> }).order_cost;

    const stocks = Array.isArray(summary.stocks) ? summary.stocks.join(', ') : summary.stocks;

    const metrics = [
        { label: '总收益', value: formatPercent(summary.totalReturn) },
        { label: '年化收益', value: formatPercent(summary.annualReturn) },
        { label: '最大回撤', value: formatPercent(summary.maxDrawdown) },
        { label: '年化波动', value: formatPercent(summary.annualVolatility) },
        { label: 'Sharpe', value: formatNumber(summary.sharpeRatio) },
        { label: 'Sortino', value: formatNumber(summary.sortinoRatio) },
        { label: 'Calmar', value: formatNumber(summary.calmarRatio) },
        { label: '胜率', value: formatPercent(summary.winRate) },
        { label: '盈亏比', value: formatNumber(summary.profitFactor) },
        { label: '期望值', value: formatNumber(summary.expectancy) },
        { label: '平均盈利', value: formatNumber(summary.avgWin) },
        { label: '平均亏损', value: formatNumber(summary.avgLoss) },
        { label: '持仓天数', value: formatNumber(summary.avgHoldingDays) },
        { label: '持仓暴露', value: formatPercent(summary.exposureRate) },
        { label: '最大连亏', value: formatNumber(summary.maxConsecutiveLoss, 0) },
    ];

    const chartSvg = (data && typeof data === 'object' ? (data as { svg?: string }).svg : undefined) || '';

    return (
        <div className="visualization backtest-panel">
            {title && <div className="visualization-title">{title}</div>}
            <div className="backtest-header">
                <div>
                    <div className="backtest-title">回测概览</div>
                    <div className="backtest-subtitle">{summary.strategy || '--'} · {stocks || '--'}</div>
                </div>
                <div className="backtest-period">{summary.period || '--'}</div>
            </div>
            <div className="backtest-summary">
                <div>
                    <span>初始资金</span>
                    <strong>{formatNumber(summary.initialCapital, 2)}</strong>
                </div>
                <div>
                    <span>结束资金</span>
                    <strong>{formatNumber(summary.finalCapital, 2)}</strong>
                </div>
                <div>
                    <span>交易次数</span>
                    <strong>{formatNumber(summary.tradesCount, 0)}</strong>
                </div>
            </div>
            <div className="backtest-metrics">
                {metrics.map(item => (
                    <div key={item.label}>
                        <span>{item.label}</span>
                        <strong>{item.value}</strong>
                    </div>
                ))}
            </div>
            {orderCost && (
                <div className="backtest-cost">
                    <div className="backtest-cost-title">交易成本</div>
                    <div className="backtest-cost-grid">
                        <div>
                            <span>佣金费率</span>
                            <strong>{formatPercent((orderCost as { commissionRate?: number; commission_rate?: number }).commissionRate
                                ?? (orderCost as { commission_rate?: number }).commission_rate)}</strong>
                        </div>
                        <div>
                            <span>最低佣金</span>
                            <strong>{formatNumber((orderCost as { minCommission?: number; min_commission?: number }).minCommission
                                ?? (orderCost as { min_commission?: number }).min_commission, 2)}</strong>
                        </div>
                        <div>
                            <span>印花税</span>
                            <strong>{formatPercent((orderCost as { stampDutyRate?: number; stamp_duty_rate?: number }).stampDutyRate
                                ?? (orderCost as { stamp_duty_rate?: number }).stamp_duty_rate)}</strong>
                        </div>
                        <div>
                            <span>滑点</span>
                            <strong>{formatPercent((orderCost as { slippageRate?: number; slippage_rate?: number }).slippageRate
                                ?? (orderCost as { slippage_rate?: number }).slippage_rate)}</strong>
                        </div>
                    </div>
                </div>
            )}
            {chartSvg && (
                <div className="backtest-chart" dangerouslySetInnerHTML={{ __html: chartSvg }} />
            )}
        </div>
    );
};

export default BacktestPanel;
