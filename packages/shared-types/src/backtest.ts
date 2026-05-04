export type BacktestMetricSnapshot = {
    totalReturn: number | null;
    sharpe: number | null;
    maxDrawdown: number | null;
    winRate: number | null;
    totalTrades: number | null;
    profitFactor: number | null;
};

export type BacktestTrade = {
    date?: string;
    entry_date?: string;
    trade_date?: string;
    type?: string;
    direction?: string;
    side?: string;
    price?: number;
    entry_price?: number;
    exit_price?: number;
    shares?: number;
    quantity?: number;
    amount?: number;
    profit?: number;
    pnl?: number;
    holding_days?: number;
};

export type BacktestFailureMetric = {
    field?: string;
    operator?: string;
    expected?: number | string | null;
    actual?: number | string | null;
    label?: string;
};

export type BacktestFailureReason = {
    reasonCode: string;
    reason: string;
    failedMetric?: BacktestFailureMetric | null;
};

export type BacktestRunResponse = {
    artifactId?: string;
    backtestId?: string | null;
    sourceTool?: 'backtest_manager';
    argsMatched?: Record<string, unknown>;
    result?: unknown;
    metrics?: BacktestMetricSnapshot;
    equity_curve?: number[];
    dates?: string[];
    trades?: BacktestTrade[];
    profit_factor?: number | null;
    initial_capital?: number | null;
    final_capital?: number | null;
    failureReason?: BacktestFailureReason | null;
    degraded?: boolean;
    fallbackReason?: string;
};

export type BacktestMetricsResponse = {
    artifactId?: string;
    sourceTool?: 'performance_manager';
    argsMatched?: Record<string, unknown>;
    result?: unknown;
    metrics?: BacktestMetricSnapshot;
};

export type BacktestHistoryItem = {
    code?: string;
    strategy?: string;
    total_return?: number;
    sharpe_ratio?: number;
    max_drawdown?: number;
    win_rate?: number;
    created_at?: string;
};

export type BacktestListResponse = {
    sourceTool?: 'backtest_manager';
    argsMatched?: Record<string, unknown>;
    result?: unknown;
    items?: BacktestHistoryItem[];
    degraded?: boolean;
    fallbackReason?: string;
};

export type BacktestBatchResultItem = {
    code?: string;
    total_return?: number | null;
    sharpe_ratio?: number | null;
    max_drawdown?: number | null;
    win_rate?: number | null;
    trades_count?: number | null;
    success?: boolean;
    reasonCode?: string | null;
    reason?: string | null;
    failedMetric?: BacktestFailureMetric | null;
};

export type BacktestBatchFailure = {
    code: string;
    reasonCode: string;
    reason: string;
    failedMetric?: BacktestFailureMetric | null;
};

export type BacktestBatchResponse = {
    sourceTool?: 'run_batch_backtest';
    argsMatched?: Record<string, unknown>;
    result?: unknown;
    results?: BacktestBatchResultItem[];
    failed?: BacktestBatchFailure[];
    summary?: Record<string, unknown>;
};

export type BacktestOptimizationCandidate = {
    candidateId?: string;
    success?: boolean;
    error?: string | null;
    score?: number | null;
    params?: Record<string, unknown>;
    artifactId?: string | null;
    metrics?: BacktestMetricSnapshot;
};

export type BacktestOptimizationResponse = {
    sourceTool?: 'backtest_manager';
    code?: string;
    strategy?: string;
    objective?: string;
    evaluatedCount?: number;
    parameterSpace?: Record<string, number[]>;
    candidates?: BacktestOptimizationCandidate[];
    bestCandidate?: BacktestOptimizationCandidate | null;
    recommendedParams?: Record<string, unknown>;
};

export type BacktestWalkForwardFold = {
    fold?: number;
    trainStart?: string;
    trainEnd?: string;
    testStart?: string;
    testEnd?: string;
    trainArtifactId?: string | null;
    testArtifactId?: string | null;
    trainMetrics?: BacktestMetricSnapshot;
    testMetrics?: BacktestMetricSnapshot;
    score?: number | null;
    passed?: boolean;
    error?: string | null;
};

export type BacktestWalkForwardSummary = {
    foldCount?: number;
    positiveFoldRatio?: number;
    avgTestSharpe?: number | null;
    avgTestReturn?: number | null;
    worstDrawdown?: number | null;
    passed?: boolean;
    stability?: string;
    recommendation?: string;
};

export type BacktestWalkForwardResponse = {
    sourceTool?: 'backtest_manager';
    code?: string;
    strategy?: string;
    objective?: string;
    trainDays?: number;
    testDays?: number;
    stepDays?: number;
    folds?: BacktestWalkForwardFold[];
    summary?: BacktestWalkForwardSummary;
};
