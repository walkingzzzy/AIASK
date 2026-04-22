export type PaperTradingDirection = 'buy' | 'sell';

export type PaperTradingOrderType = 'market' | 'limit' | 'stop';

export type PaperTradingActionStatus = 'idle' | 'submitting' | 'success' | 'error';

export type PaperTradingAccount = {
    account_id?: string;
    user_id?: string;
    initial_capital?: number;
    current_capital?: number;
    total_value?: number;
    status?: string;
    strategy_id?: string;
    account_type?: string;
    incubation_stage?: string;
    promotion_candidate?: boolean;
    risk_rules?: Record<string, unknown>;
};

export type PaperTradingSummary = {
    account_id?: string;
    account?: PaperTradingAccount | null;
    positions_count?: number;
    pending_orders_count?: number;
    total_value?: number;
    total_return_pct?: number;
    reconciliation?: PaperTradingReconcileResponse | null;
};

export type PaperTradingAccountsResponse = {
    accounts?: PaperTradingAccount[];
};

export type PaperTradingPosition = {
    account_id?: string;
    stock_code?: string;
    stock_name?: string;
    quantity?: number;
    sellable?: number;
    cost_price?: number;
    current_price?: number;
    market_value?: number;
    profit_rate?: number;
};

export type PaperTradingPositionsResponse = {
    positions?: PaperTradingPosition[];
    reconciliation?: PaperTradingReconcileResponse | null;
};

export type PaperTradingTrade = {
    id?: string;
    account_id?: string;
    strategy_id?: string;
    source_order_id?: string;
    signal_id?: string;
    position_id?: string;
    stock_code?: string;
    stock_name?: string;
    trade_type?: string;
    price?: number;
    quantity?: number;
    amount?: number;
    commission?: number;
    trade_time?: string;
};

export type PaperTradingOrdersResponse = {
    orders?: PaperTradingTrade[];
};

export type PaperTradingPendingOrder = {
    id?: number;
    account_id?: string;
    strategy_id?: string;
    signal_id?: string;
    position_id?: string;
    signal_date?: string;
    source?: string;
    code?: string;
    direction?: PaperTradingDirection;
    shares?: number;
    price?: number;
    order_type?: PaperTradingOrderType | string;
    stop_price?: number | null;
    status?: string;
    commission?: number;
    reason?: string | null;
    filled_at?: string | null;
    created_at?: string;
    updated_at?: string;
};

export type PaperTradingPendingOrdersResponse = {
    orders?: PaperTradingPendingOrder[];
};

export type PaperTradingNavPoint = {
    id?: number;
    account_id?: string;
    nav_date?: string;
    total_value?: number;
    cash?: number;
    market_value?: number;
    daily_return?: number;
    created_at?: string;
};

export type PaperTradingNavHistoryResponse = {
    nav?: PaperTradingNavPoint[];
};

export type PaperTradingPerformancePoint = {
    date?: string;
    totalValue?: number;
    dailyReturn?: number;
};

export type PaperTradingPerformanceMetrics = {
    totalReturn?: number;
    sharpe?: number;
    maxDrawdown?: number;
    winRate?: number;
    avgHoldDays?: number;
};

export type PaperTradingPerformanceResponse = {
    dailyReturns?: PaperTradingPerformancePoint[];
    metrics?: PaperTradingPerformanceMetrics;
};

export type PaperTradingPlaceOrderInput = {
    code: string;
    direction: PaperTradingDirection;
    quantity: number;
    price?: number;
    order_type?: PaperTradingOrderType | string;
    stop_price?: number;
    account_id?: string;
    idempotency_key?: string;
};

export type PaperTradingCancelOrderInput = {
    order_id: string;
    idempotency_key?: string;
};

export type PaperTradingRouteExecutionInput = {
    code: string;
    direction: PaperTradingDirection;
    quantity: number;
    price?: number;
    urgency?: string;
    order_type?: PaperTradingOrderType | string;
    stop_price?: number;
    account_id?: string;
    artifact_id?: string;
    output_artifact_id?: string;
    idempotency_key?: string;
};

export type PaperTradingComplianceResult = {
    status?: 'blocked' | 'passed';
    reason?: string | null;
    passed?: boolean;
    blocked?: boolean;
    checks?: Record<string, unknown>;
    violations?: string[];
    warnings?: string[];
};

export type PaperTradingStatusProbe = {
    status?: string;
    running?: boolean;
    ok?: boolean;
};

export type PaperTradingReconcileResponse = {
    account_id?: string;
    drift_detected?: boolean;
    reconciled?: boolean;
    refresh_prices?: boolean;
    reasons?: string[];
    positions_before_count?: number;
    positions_after_count?: number;
    cash_before?: number;
    cash_after?: number;
    total_value_before?: number;
    total_value_after?: number;
    positions?: PaperTradingPosition[];
};
