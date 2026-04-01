export type ExecutionWorkbenchSeverity = 'high' | 'medium' | 'low' | 'unknown';

export type ExecutionWorkbenchWarning = {
    id: string;
    severity: ExecutionWorkbenchSeverity;
    title: string;
    message?: string | null;
    metric?: string | null;
    actual?: number | null;
    threshold?: number | null;
    suggestedAction?: string | null;
};

export type ExecutionWorkbenchCost = {
    estimatedTotal?: number | null;
    commission?: number | null;
    marketImpact?: number | null;
    slippage?: number | null;
    participationRate?: number | null;
    riskBudgetProfile?: string | null;
};

export type ExecutionWorkbenchOrderItem = {
    id: string;
    code?: string | null;
    direction?: string | null;
    quantity?: number | null;
    price?: number | null;
    status?: string | null;
    createdAt?: string | null;
};

export type ExecutionWorkbenchOrderContext = {
    accountId?: string | null;
    pendingOrderCount: number;
    positionsCount: number;
    totalValue?: number | null;
    totalReturnPct?: number | null;
    recentOrders: ExecutionWorkbenchOrderItem[];
};

export type ExecutionWorkbenchNextAction = {
    id: string;
    label: string;
    reason: string;
    targetPage: string;
    payload?: Record<string, unknown>;
};

export type ExecutionTaskListItem = {
    taskId: string;
    artifactId?: string | null;
    algorithm?: string | null;
    code?: string | null;
    status?: string | null;
    createdAt?: string | null;
    totalShares?: number | null;
    durationMinutes?: number | null;
    softGateProfile?: string | null;
    warningCount?: number;
    hasHighSeverity?: boolean;
    executionFeasible?: boolean;
    executionBlocking?: boolean;
};

export type ExecutionWorkbenchResponse = {
    message: string;
    empty: boolean;
    executionId?: string | null;
    accountId?: string | null;
    overview?: {
        executionId?: string | null;
        artifactId?: string | null;
        accountId?: string | null;
        code?: string | null;
        status?: string | null;
        algorithm?: string | null;
        createdAt?: string | null;
        totalShares?: number | null;
        durationMinutes?: number | null;
        slices?: number | null;
        lifecycleCount?: number | null;
        softGateProfile?: string | null;
        warningCount: number;
        hasHighSeverity: boolean;
        executionFeasible?: boolean;
        executionBlocking?: boolean;
    } | null;
    warnings: ExecutionWorkbenchWarning[];
    cost?: ExecutionWorkbenchCost | null;
    orderContext?: ExecutionWorkbenchOrderContext | null;
    nextActions: ExecutionWorkbenchNextAction[];
    sourceTools?: Record<string, string | undefined>;
    argsMatched?: Record<string, unknown>;
    result?: unknown;
};

export type ExecutionTasksResponse = {
    count: number;
    status: string | null;
    tasks: ExecutionTaskListItem[];
    pendingOrders: ExecutionTaskListItem[];
    completedOrders: ExecutionTaskListItem[];
    sourceTool?: string;
    argsMatched?: Record<string, unknown>;
    result?: unknown;
};

export type ExecutionTaskDetailResponse = ExecutionWorkbenchResponse & {
    taskId: string;
    artifactId?: string | null;
    task: ExecutionTaskListItem;
};

export type ExecutionArtifactResponse = {
    artifactId: string;
    count: number;
    latestTaskId?: string | null;
    latestTask?: ExecutionTaskListItem | null;
    taskIds: string[];
    detail?: ExecutionTaskDetailResponse | null;
    sourceTools?: Record<string, string | undefined>;
    argsMatched?: Record<string, unknown>;
    result?: unknown;
};

export type LiveTradingGatewayStatusResponse = {
    configured?: boolean;
    connected?: boolean;
    status?: string;
    message?: string;
    provider?: string;
    mode?: string;
    account?: {
        account_id?: string;
        status?: string | null;
        cash?: number | null;
        portfolio_value?: number | null;
        [key: string]: unknown;
    } | null;
    read_only?: boolean;
    base_url?: string;
    paper?: boolean;
    error?: string | null;
    raw?: unknown;
};

export type LiveTradingAccountResponse = {
    account?: {
        account_id?: string;
        status?: string | null;
        cash?: number | null;
        portfolio_value?: number | null;
        buying_power?: number | null;
        equity?: number | null;
        [key: string]: unknown;
    } | null;
    equity?: number | null;
    cash?: number | null;
    buying_power?: number | null;
    status?: string | null;
    raw?: Record<string, unknown>;
};

export type LiveTradingPositionItem = {
    symbol?: string;
    qty?: number | null;
    avg_entry_price?: number | null;
    market_value?: number | null;
    cost_basis?: number | null;
    unrealized_pl?: number | null;
    side?: string | null;
};

export type LiveTradingPositionsResponse = {
    positions?: LiveTradingPositionItem[];
    count?: number;
    raw?: unknown;
};

export type LiveTradingOrderItem = {
    order_id?: string;
    symbol?: string;
    side?: string;
    type?: string;
    qty?: number | null;
    filled_qty?: number | null;
    status?: string | null;
    submitted_at?: string | null;
    limit_price?: number | null;
    stop_price?: number | null;
};

export type LiveTradingOrdersResponse = {
    orders?: LiveTradingOrderItem[];
    count?: number;
    raw?: unknown;
};

export type LiveTradingOrderStatusResponse = {
    order?: LiveTradingOrderItem | null;
    raw?: unknown;
};

export type LiveTradingOrderEventItem = {
    id?: string;
    type?: string;
    event_type?: string;
    event_category?: string | null;
    event_status?: string | null;
    status?: string;
    message?: string;
    created_at?: string | null;
    occurred_at?: string | null;
    state_transition?: {
        from_status?: string | null;
        to_status?: string | null;
        [key: string]: unknown;
    } | null;
    fill_event?: {
        qty?: number | null;
        shares?: number | null;
        price?: number | null;
        [key: string]: unknown;
    } | null;
    brokerage_event?: {
        reason?: string | null;
        [key: string]: unknown;
    } | null;
    payload?: Record<string, unknown>;
};

export type LiveTradingOrderEventsResponse = {
    order_id?: string;
    events?: LiveTradingOrderEventItem[];
    state_machine?: {
        current_status?: string | null;
        [key: string]: unknown;
    } | null;
    count?: number;
    raw?: unknown;
};

export type LiveTradingFillItem = {
    id?: string;
    fill_id?: string;
    order_id?: string;
    symbol?: string;
    qty?: number | null;
    shares?: number | null;
    price?: number | null;
    amount?: number | null;
    commission?: number | null;
    source?: string | null;
    side?: string;
    filled_at?: string | null;
    occurred_at?: string | null;
};

export type LiveTradingFillsResponse = {
    fills?: LiveTradingFillItem[];
    count?: number;
    raw?: unknown;
};

export type LiveTradingBrokerReceiptResponse = {
    receipt?: {
        message_type?: string | null;
        status?: string | null;
        reason?: string | null;
        [key: string]: unknown;
    } | null;
    order_id?: string;
    raw?: unknown;
};

export type LiveTradingSubmitOrderResponse = {
    accepted?: boolean;
    submitted?: boolean;
    message?: string;
    mode?: string | null;
    order?: LiveTradingOrderItem | null;
    raw?: unknown;
};

export type LiveTradingCancelOrderResponse = {
    cancelled?: boolean;
    message?: string;
    order?: LiveTradingOrderItem | Record<string, unknown> | null;
    raw?: unknown;
};

export type LiveTradingMirrorToPaperResponse = {
    mirrored?: boolean;
    executed?: boolean;
    paper_account_id?: string | null;
    mirrorable_count?: number | null;
    placed_order_count?: number | null;
    message?: string;
    raw?: unknown;
};

export type LiveTradingSyncOrderEventsResponse = {
    synced?: boolean;
    count?: number;
    artifact_id?: string | null;
    collection?: {
        count?: number | null;
        [key: string]: unknown;
    } | null;
    message?: string;
    raw?: unknown;
};
