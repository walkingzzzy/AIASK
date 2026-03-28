/* ── @aiask/shared-types ── */

// API 响应信封
export type Envelope<T = unknown> = {
    ok?: boolean;
    success?: boolean;
    data?: T;
    error?: string | {
        code?: string;
        message?: string;
        detail?: unknown;
    };
    meta?: CacheMeta;
    traceId?: string;
};

// 缓存元数据
export type CacheMeta = {
    cachedAt?: string;
    expiresAt?: string;
    stale?: boolean;
    fetchedAt?: string;
    cache?: {
        hit?: boolean;
        backend?: string;
        ttlSeconds?: number;
    };
};

export const STRATEGY_MANAGER_ACTIONS = [
    'help',
    'create',
    'publish',
    'archive',
    'list',
    'detail',
    'review_report',
    'events',
    'update_metrics',
    'review',
    'subscribe',
    'unsubscribe',
    'my_subscriptions',
    'rank',
    'capabilities',
    'daily_snapshot',
    'daily_snapshots',
    'get_signals',
    'get_forward_returns',
    'get_signal_stats',
    'review_report_recheck',
    'submit',
    'lifecycle_scan',
    'incubation_overview',
    'factory_status',
    'factory_run_once',
    'factory_runs',
    'factory_run_detail',
    'incubation_accounts',
    'incubation_metrics',
    'paper_account',
    'paper_orders',
    'paper_nav',
    'incubation_sync_run',
    'incubation_pipeline',
    'incubation_pipeline_run',
    'risk_events',
    'risk_snapshots',
    'risk_scan_run',
    'risk_recovery',
    'resolve_risk_event',
    'runtime_alerts',
    'runtime_alert_dispatch_run',
    'runtime_alert_ack',
    'runtime_control',
    'runtime_control_set',
    'promotion_reviews',
    'promotion_review_run',
    'runtime_cycle_status',
    'runtime_cycle_run',
    'domain_events',
    'domain_projection',
    'domain_projection_snapshot',
    'domain_projection_rebuild',
    'vector_profiles',
    'vector_indexes',
    'vector_index_snapshots',
    'vector_ann_search',
    'vector_reconcile',
    'vector_rebuild',
    'vector_health',
    'vector_cleanup',
    'ai_generate',
    'ai_experiments',
    'task_runs',
] as const;

export type StrategyManagerAction = typeof STRATEGY_MANAGER_ACTIONS[number];

export const STRATEGY_MANAGER_ERROR_CODES = [
    'STRATEGY_MANAGER_INVALID_ACTION',
    'STRATEGY_MANAGER_INVALID_PARAMS',
    'STRATEGY_MANAGER_NOT_FOUND',
    'STRATEGY_MANAGER_GATE_FAILED',
    'STRATEGY_MANAGER_UNSUPPORTED',
    'STRATEGY_MANAGER_BACKEND_ERROR',
] as const;

export type StrategyManagerErrorCode = typeof STRATEGY_MANAGER_ERROR_CODES[number];

export const SKILL_STATUSES = [
    'registered',
    'executable',
    'deprecated',
] as const;

export type SkillStatus = typeof SKILL_STATUSES[number];

export const SKILL_EXECUTION_MODES = [
    'orchestrated',
    'no_handler',
    'deprecated',
] as const;

export type SkillExecutionMode = typeof SKILL_EXECUTION_MODES[number];

export const SKILL_ERROR_CODES = [
    'SKILL_NOT_FOUND',
    'SKILL_NOT_EXECUTABLE',
    'SKILL_DEPRECATED',
    'SKILL_EXECUTION_FAILED',
    'SKILLS_REGISTRY_UNAVAILABLE',
] as const;

export type SkillErrorCode = typeof SKILL_ERROR_CODES[number];

export type SkillSchema = Record<string, unknown>;

export type SkillDescriptor = {
    id: string;
    name?: string;
    category?: string;
    description?: string;
    path?: string;
    status: SkillStatus;
    executable: boolean;
    deprecated?: boolean;
    handler_available?: boolean;
    execution_mode?: SkillExecutionMode;
    input_schema?: SkillSchema;
    output_schema?: SkillSchema;
    supported_tasks?: string[];
};

// 标准化行情快照
export type NormalizedQuote = {
    symbol: string;
    code: string;
    name: string;
    last: number | null;
    price: number | null;
    change: number | null;
    pct_change: number | null;
    changePercent: number | null;
    change_pct?: number | null;
    volume: number | null;
    turnover: number | null;
    amount: number | null;
    market_cap?: number | null;
    timestamp?: string | null;
    open?: number | null;
    close?: number | null;
    high?: number | null;
    low?: number | null;
    prevClose?: number | null;
    pe?: number | null;
    pb?: number | null;
    eps?: number | null;
    amp?: number | null;
};

// 标准化 K 线点
export type NormalizedKlinePoint = {
    timestamp?: string | null;
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    turnover?: number | null;
};

// 标准化订单簿
export type NormalizedOrderBook = {
    symbol: string;
    bids: Array<{ price: number; volume: number }>;
    asks: Array<{ price: number; volume: number }>;
    timestamp: string | null;
};

export type AlertItem = {
    id: string;
    code: string;
    indicator: string;
    condition: string;
    value: number | null;
};

export type AlertsListData = {
    status: string;
    items: AlertItem[];
    sourceTool: 'alerts_manager';
    argsMatched: Record<string, unknown>;
    meta: CacheMeta;
};

export type NotificationType = 'alert' | 'signal' | 'trade' | 'system' | 'news';

export type NotificationLevel = 'info' | 'warn' | 'error';

export type NotificationItem = {
    id: string;
    type: NotificationType;
    level: NotificationLevel;
    title: string;
    body: string;
    read: boolean;
    createdAt: string;
};

export type NotificationsListData = {
    items: NotificationItem[];
    total: number;
    unread: number;
};

export type RiskModuleStatus = {
    ok?: boolean;
    reason?: string | null;
};

export type RiskSourceContext =
    | { mode: 'portfolio'; portfolioId: number }
    | { mode: 'paper-trading'; accountId?: string; codes: string[]; weights: number[]; portfolioValue: number }
    | { mode: 'empty'; reason: string };

export type RiskSummaryData = {
    portfolioId: number | null;
    lookbackDays: number;
    injectedFail: 'var' | 'stress' | 'exposure' | null;
    sourceContext: RiskSourceContext;
    sourceTools: {
        var: 'risk_manager';
        stress: 'risk_manager';
        exposure: 'risk_manager';
    };
    argsMatched: {
        var: Record<string, unknown> | null;
        stress: Record<string, unknown> | null;
        exposure: Record<string, unknown> | null;
    };
    varResult: unknown;
    stressResult: unknown;
    exposureResult: unknown;
    moduleStatus: Record<'var' | 'stress' | 'exposure', RiskModuleStatus>;
    degraded: boolean;
    empty: boolean;
    degradeReasons: string[];
    meta: CacheMeta;
};

export type RiskVarOnlyData = {
    portfolioId: number | null;
    lookbackDays: number;
    sourceContext: RiskSourceContext | null;
    sourceTool: 'risk_manager';
    argsMatched: Record<string, unknown> | null;
    result: unknown;
    degraded: boolean;
    degradedReason: string | null;
    meta: CacheMeta;
};

export type ToolArgs = Record<string, unknown>;

export type ToolCacheBackend = 'redis' | 'memory' | 'none';

export type ToolCacheInfo = {
    hit: boolean;
    backend: ToolCacheBackend;
    key: string;
    ttlSeconds: number;
};

export type ToolMeta = {
    fetchedAt: string;
    cache: ToolCacheInfo;
};

export type MarketKlinePeriod = 'daily' | 'weekly' | 'monthly';

export type MarketKlineQuery = {
    code: string;
    period?: MarketKlinePeriod;
    limit?: number;
};

export type MarketQuoteResponseDto = {
    quote: NormalizedQuote;
    tool: 'get_realtime_quote';
    argsTried: ToolArgs[];
    argsMatched: ToolArgs;
    meta: ToolMeta;
};

export type MarketKlineResponseDto = {
    kline: NormalizedKlinePoint[];
    tool: 'get_kline_data';
    argsTried: ToolArgs[];
    argsMatched: ToolArgs;
    meta: ToolMeta;
};

export type MarketOrderBookResponseDto = {
    orderBook: NormalizedOrderBook;
    tool: 'get_order_book';
    argsTried: ToolArgs[];
    argsMatched: ToolArgs;
    meta: ToolMeta;
};

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
};

export type PaperTradingTrade = {
    id?: string;
    stock_code?: string;
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

export type StrategyTrustedInfo = {
    sample_start_date?: string;
    sample_end_date?: string;
    turnover_rate?: number | null;
    capacity?: number | null;
    capacity_label?: string;
};

export type Strategy = {
    id: string;
    name: string;
    strategy_type?: string;
    description?: string;
    subscriber_count?: number;
    avg_rating?: number;
    review_count?: number;
    metrics?: {
        total_return?: number;
        annual_return?: number;
        sharpe_ratio?: number;
        max_drawdown?: number;
        win_rate?: number;
    };
    nav_series?: number[];
} & StrategyTrustedInfo;

export type RankingResponse = { strategies?: Strategy[] } | Strategy[];

export type FactoryAutonomyTaskBrief = {
    task_id?: string;
    task_source?: string;
    opportunity_type?: string;
    generation_limit?: number;
    generated_count?: number;
};

export type FactoryRunSummary = {
    trace_id?: string;
    stage_status_counts?: Record<string, number>;
    failed_stage_count?: number;
    partial_stage_count?: number;
    skipped_stage_count?: number;
    hard_failure_count?: number;
    degraded_stage_count?: number;
    failed_stages?: string[];
    partial_stages?: string[];
    skipped_stages?: string[];
    skip_reason?: string;
    skip_reasons?: string[];
    persistence_failure_count?: number;
    persistence_failures?: Array<{
        operation?: string;
        stage?: string | null;
        error_type?: string;
        error?: string;
    }>;
    candidates_spawned?: number;
    candidates_passed_backtest?: number;
    candidates_after_dedup?: number;
    passed_quality_gate?: number;
    autonomy_generated?: number;
    autonomy_task_count?: number;
    event_task_count?: number;
    snapshot_task_count?: number;
    snapshot_degraded?: boolean;
    snapshot_completion_ratio?: number;
    snapshot_failure_reason_count?: number;
    task_source_counts?: Record<string, number>;
    scanner_task_types?: Record<string, number>;
    event_snapshot_mixed?: boolean;
    autonomy_task_briefs?: FactoryAutonomyTaskBrief[];
    submitted?: number;
    eliminated?: number;
    elapsed_seconds?: number;
    constraint_violation_count?: number;
    target_symbol_intersection_ratio_avg?: number;
    universe_expansion_count?: number;
    preference_mismatch_warning_count?: number;
    attempt_adjusted_gate_failed?: number;
    attempt_adjusted_score_avg?: number;
    event_window_contamination_warning_count?: number;
    cost_audit_missing_count?: number;
    deflated_sharpe_proxy_avg?: number;
    deflated_sharpe_ratio_avg?: number;
    high_pbo_proxy_count?: number;
    high_pbo_count?: number;
    formal_multiple_testing_count?: number;
    weak_white_reality_check_count?: number;
    weak_hansen_spa_count?: number;
    refresh_metrics_only_count?: number;
    spawn_revision_from_existing_count?: number;
};

export type FactoryStatusResponse = {
    running?: boolean;
    run_time?: string;
    last_run?: string | null;
    last_summary?: FactoryRunSummary;
    last_result?: {
        status?: string;
        error?: string;
    };
};

export type CapabilityResponse = {
    daily_snapshot?: boolean;
    paper_incubation?: boolean;
    incubation_pipeline?: boolean;
    runtime_risk?: boolean;
    risk_snapshots?: boolean;
    risk_recovery?: boolean;
    execution_risk?: boolean;
    runtime_controls?: boolean;
    promotion_pipeline?: boolean;
    projection_snapshots?: boolean;
    event_replay?: boolean;
    vector_platform?: boolean;
    vector_governance?: boolean;
    persistent_vector_index?: boolean;
    ann_vector_search?: boolean;
    ai_generation?: boolean;
    multi_agent_review?: boolean;
    quality_governance?: boolean;
    domain_events?: boolean;
    domain_projection?: boolean;
    runtime_cycle?: boolean;
};

export type DailySnapshotResponse = {
    snapshot_date?: string;
    fear_greed_index?: number;
    degraded?: boolean;
    failure_reasons?: string[];
    missing_fields?: string[];
    hot_sectors?: string[];
    cold_sectors?: string[];
    summary?: {
        listed_count?: number;
    };
    completeness?: {
        completion_ratio?: number;
    };
};

export type FactoryRunsResponse = {
    dto_version?: string;
    latest?: {
        run_id?: string;
        status?: string;
        trace_id?: string | null;
    } | null;
    items?: Array<{
        run_id?: string;
        trace_id?: string | null;
        status?: string;
        started_at?: string;
        completed_at?: string | null;
        elapsed_seconds?: number;
        error?: string | null;
        summary?: FactoryRunSummary;
        stages?: Record<string, Record<string, string | number | boolean | null | undefined>>;
        pipeline?: {
            trace_id?: string | null;
            failed_stage?: string | null;
            partial_stage?: string | null;
            skipped_stage?: string | null;
            stage_order?: string[];
            total_stage_count?: number;
            completed_stage_count?: number;
            partial_stage_count?: number;
            skipped_stage_count?: number;
            failed_stage_count?: number;
            stage_status_counts?: Record<string, number>;
        };
    }>;
    count?: number;
};

export type FactoryRunDetailResponse = {
    dto_version?: string;
    run_id?: string;
    trace_id?: string | null;
    status?: string;
    started_at?: string;
    completed_at?: string | null;
    elapsed_seconds?: number;
    error?: string | null;
    summary?: FactoryRunSummary;
    snapshot_summary?: Record<string, string | number | null | undefined>;
    stages?: Record<string, Record<string, string | number | boolean | null | undefined>>;
    pipeline?: {
        trace_id?: string | null;
        failed_stage?: string | null;
        partial_stage?: string | null;
        skipped_stage?: string | null;
        stage_order?: string[];
        total_stage_count?: number;
        completed_stage_count?: number;
        partial_stage_count?: number;
        skipped_stage_count?: number;
        failed_stage_count?: number;
        stage_status_counts?: Record<string, number>;
    };
};

export type StrategyMetric = {
    period?: string;
    total_return?: number;
    annual_return?: number;
    sharpe_ratio?: number;
    max_drawdown?: number;
    win_rate?: number;
    calmar_ratio?: number;
    trade_count?: number;
};

export type StrategyReview = {
    user_id: string;
    rating: number;
    comment?: string;
    created_at?: string;
};

export type StrategyCore = {
    id: string;
    name: string;
    description?: string;
    strategy_type?: string;
    status?: string;
    author_id?: string;
    subscriber_count?: number;
    avg_rating?: number;
    review_count?: number;
    factor_weights?: Record<string, number>;
    metrics?: StrategyMetric[];
    reviews?: StrategyReview[];
} & StrategyTrustedInfo;

export type SignalStatsResponse = {
    hit_rate?: Record<string, number>;
    forward_ic?: Record<string, number>;
    forward_sharpe?: Record<string, number>;
    total_signals?: number;
};

export type Signal = {
    signal_date?: string;
    code?: string;
    signal?: number;
    score?: number;
};

export type SignalsResponse = {
    signals?: Signal[];
    count?: number;
    subscriber?: boolean;
};

export type ReviewReportResponse = {
    passed?: boolean;
    report_type?: string;
    reports?: Array<{
        report_type?: string;
        updated_at?: string;
        summary?: {
            review_source?: string;
            validation_grade?: string;
        };
    }>;
    summary?: {
        status_after_review?: string;
        validation_grade?: string;
        review_source?: string;
        primary_validation_layer?: string;
        refresh_mode?: string;
    };
    quality_gate?: {
        wf_ic_ir?: number;
        pkf_ic?: number;
        bootstrap_ci_lower?: number;
        param_sensitivity?: number;
        run_correction_mode?: string;
        deflated_sharpe_proxy?: number;
        pbo_proxy?: number;
        reality_check_pvalue_proxy?: number;
        spa_pvalue_proxy?: number;
        multiple_testing_mode?: string;
        deflated_sharpe_ratio?: number;
        deflated_sharpe_reference_sharpe?: number;
        deflated_sharpe_effective_trials?: number;
        pbo?: number;
        white_reality_check_pvalue?: number;
        hansen_spa_pvalue?: number;
        multiple_testing?: Record<string, unknown>;
        reasons?: string[];
        reason_codes?: string[];
    };
    run_correction?: {
        mode?: string;
        raw_sharpe_proxy?: number;
        deflated_sharpe_proxy?: number;
        pbo_proxy?: number;
        reality_check_pvalue_proxy?: number;
        spa_pvalue_proxy?: number;
        multiple_testing_mode?: string;
        deflated_sharpe_ratio?: number;
        deflated_sharpe_reference_sharpe?: number;
        deflated_sharpe_effective_trials?: number;
        pbo?: number;
        white_reality_check_pvalue?: number;
        hansen_spa_pvalue?: number;
        multiple_testing?: Record<string, unknown>;
    };
    constraint_check?: {
        intersection_ratio?: number;
        constraint_violation?: string | null;
        expansion_applied?: boolean;
        expansion_reason?: string | null;
        expansion_source?: string | null;
        target_symbol_policy?: string | null;
    };
    validation_profile?: {
        profile?: string | null;
        validation_focus?: string | null;
        primary_validation_layer?: string | null;
    };
    event_window_config?: Record<string, unknown>;
    position_assumption?: string | null;
    cost_assumptions?: Record<string, unknown>;
    explicit_cost_breakdown?: Record<string, unknown>;
    implicit_cost_breakdown?: Record<string, unknown>;
    backtest_assumptions?: Record<string, unknown>;
    attempt_adjustment?: {
        attempt_count?: number;
        task_attempt_count?: number;
        external_llm_attempt_count?: number;
        selection_ratio?: number;
        penalty?: number;
        factory_attempt_count?: number;
        factory_selected_count?: number;
        task_selected_count?: number;
        external_llm_selected_count?: number;
    };
    task_signature?: string | null;
    refresh_mode?: string | null;
    task_preference?: {
        preferred_strategy_types?: string[];
        preference_strength?: string | null;
        preference_reason?: string | null;
        override_applied?: boolean;
    };
    dedup_report?: {
        duplicate?: boolean;
        match_type?: string | null;
        param_similarity?: number;
        vector_similarity?: number;
        reason?: string;
    };
};

export type StrategyEventsResponse = {
    events?: Array<{
        event_type?: string;
        from_status?: string | null;
        to_status?: string;
        actor_id?: string;
        reason?: string;
        created_at?: string;
        metadata?: Record<string, unknown>;
    }>;
    count?: number;
};

export type IncubationOverviewResponse = {
    status?: string;
    sharpe_ratio?: number;
    max_drawdown?: number;
    total_signals?: number;
    minimum_signal_count?: number;
    hit_rate_5d?: number | null;
    forward_ic_5d?: number | null;
    forward_sharpe_5d?: number | null;
    promotion_ready?: boolean;
    deprecation_risk?: boolean;
    blockers?: string[];
    risk_flags?: string[];
    observed_forward_days?: number[];
    missing_forward_days?: number[];
    forward_returns?: Array<{
        label?: string;
        hit_rate?: number | null;
        forward_ic?: number | null;
        forward_sharpe?: number | null;
    }>;
    blockers_by_period?: Record<string, string[]>;
    risk_flags_by_period?: Record<string, string[]>;
    validation_grade?: string | null;
};

export type IncubationAccount = {
    strategy_id?: string;
    account_id?: string;
    stage?: string;
    status?: string;
    source_run_id?: string;
    metadata?: Record<string, unknown>;
};

export type IncubationMetric = {
    metric_date?: string;
    account_id?: string;
    stage?: string;
    decision?: string;
    nav?: number;
    total_value?: number;
    cash?: number;
    market_value?: number;
    daily_return?: number;
    max_drawdown?: number;
    sharpe_ratio?: number;
    hit_rate_5d?: number;
    forward_ic_5d?: number;
    forward_sharpe_5d?: number;
    total_signals?: number;
    total_orders?: number;
    total_trades?: number;
    turnover_rate?: number;
    exposure_rate?: number;
    alpha_decay?: number;
    drift_score?: number;
};

export type PaperAccount = PaperTradingAccount & {
    id?: string;
    name?: string;
};

export type PaperPosition = PaperTradingPosition;

export type PaperOrder = PaperTradingPendingOrder;

export type PaperNav = PaperTradingNavPoint;

export type PaperAccountResponse = {
    account?: PaperAccount | null;
    binding?: IncubationAccount | null;
    positions?: PaperPosition[];
    latest_nav?: PaperNav | null;
    order_summary?: {
        total_orders?: number;
        total_trades?: number;
        trade_amount?: number;
    };
};

export type IncubationPipelineSnapshot = {
    id?: number;
    strategy_id?: string;
    account_id?: string | null;
    pipeline_stage?: string;
    pipeline_status?: string;
    observed_days?: number;
    promote_streak?: number;
    halt_streak?: number;
    latest_decision?: string;
    readiness_score?: number;
    next_action?: string;
    auto_review?: boolean;
    auto_promoted?: boolean;
    blockers?: string[];
    risk_flags?: string[];
    summary?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
    task_run_id?: number | null;
    source?: string;
    evaluated_at?: string;
};

export type RuntimeRiskSnapshot = {
    id?: number;
    strategy_id?: string;
    account_id?: string | null;
    posture_level?: string;
    escalation_level?: number;
    control_mode?: string;
    open_event_count?: number;
    critical_open_count?: number;
    warning_open_count?: number;
    recommended_action?: string;
    recovery_eligible?: boolean;
    blockers?: string[];
    summary?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
    task_run_id?: number | null;
    source?: string;
    evaluated_at?: string;
};

export type RiskEvent = {
    id?: number;
    severity?: string;
    event_type?: string;
    action?: string;
    status?: string;
    title?: string;
    reason?: string;
    detected_at?: string;
    payload?: Record<string, unknown>;
};

export type RuntimeControl = {
    strategy_id?: string;
    account_id?: string | null;
    control_mode?: string;
    status?: string;
    source?: string;
    trigger_event_type?: string | null;
    reason?: string | null;
    action_summary?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
    activated_at?: string;
    released_at?: string | null;
    updated_at?: string;
};

export type RuntimeAlert = {
    alert_id?: number;
    strategy_id?: string;
    account_id?: string | null;
    alert_key?: string;
    category?: string;
    severity?: string;
    status?: string;
    title?: string;
    message?: string;
    escalation_level?: number;
    channels?: string[];
    related_event_ids?: number[];
    metadata?: Record<string, unknown>;
    source?: string;
    acknowledged_by?: string | null;
    acknowledged_at?: string | null;
    resolved_at?: string | null;
    created_at?: string;
    updated_at?: string;
};

export type PromotionReview = {
    id?: number;
    strategy_id?: string;
    account_id?: string | null;
    review_source?: string;
    stage?: string;
    status?: string;
    recommendation?: string;
    score?: number;
    blockers?: string[];
    risk_flags?: string[];
    summary?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
    reviewed_at?: string;
};

export type DomainProjection = {
    strategy_id?: string;
    current_status?: string;
    aggregate_version?: number;
    status_event_count?: number;
    domain_event_count?: number;
    open_risk_count?: number;
    runtime_control_mode?: string;
    runtime_control_status?: string;
    latest_promotion_status?: string;
    latest_promotion_recommendation?: string;
    latest_incubation_decision?: string;
    ai_cycle_count?: number;
    runtime_cycle_count?: number;
    last_status_event_at?: string;
    last_domain_event_at?: string;
    phases?: Record<string, boolean>;
    timeline?: Array<{
        timestamp?: string;
        event_type?: string;
        source?: string;
        summary?: string;
    }>;
};

export type ProjectionSnapshot = {
    id?: number;
    strategy_id?: string;
    projection_type?: string;
    aggregate_version?: number;
    current_status?: string;
    runtime_control_mode?: string;
    timeline_count?: number;
    projection?: DomainProjection;
    metadata?: Record<string, unknown>;
    task_run_id?: number | null;
    source?: string;
    rebuilt_at?: string;
};

export type VectorProfile = {
    id?: number;
    profile_id?: number;
    strategy_id?: string;
    profile_type?: string;
    vector_method?: string;
    metric?: string;
    vector_dim?: number;
    signature?: string;
    backend?: string;
    index_name?: string;
    index_version?: string;
    similarity?: number;
    coarse_score?: number;
    bucket_id?: string | null;
    query_bucket_id?: string | null;
    candidate_count?: number;
    retrieval_mode?: string;
    metadata?: Record<string, unknown>;
};

export type VectorIndexSnapshot = {
    id?: number;
    index_name?: string;
    index_version?: string;
    status?: string;
    profile_type?: string;
    vector_method?: string;
    metric?: string;
    backend?: string;
    profile_count?: number;
    bucket_count?: number;
    vector_dim?: number;
    centroids?: Array<{
        bucket_id?: string;
        size?: number;
        neighbors?: string[];
        mean_similarity?: number;
    }>;
    metadata?: Record<string, unknown>;
    task_run_id?: number | null;
    source?: string;
    built_at?: string;
    activated_at?: string;
    created_at?: string;
};

export type DomainEvent = {
    id?: number;
    strategy_id?: string | null;
    aggregate_type?: string;
    aggregate_id?: string | null;
    event_type?: string;
    source?: string;
    severity?: string;
    correlation_id?: string | null;
    payload?: Record<string, unknown>;
    created_at?: string;
};

export type AiExperiment = {
    experiment_id?: string;
    strategy_id?: string | null;
    parent_strategy_id?: string | null;
    generated_strategy_id?: string | null;
    task_run_id?: number | null;
    source?: string;
    generator_type?: string;
    optimizer_type?: string;
    status?: string;
    hypothesis?: string;
    evaluation?: {
        committee_review?: {
            final_score?: number;
            decision?: string;
            rank?: number;
            is_champion?: boolean;
            planner_score?: number;
            risk_score?: number;
            feasibility_score?: number;
            execution_score?: number;
            capacity_score?: number;
            task_alignment_score?: number;
            novelty_score?: number;
            planner_context?: Record<string, unknown>;
            task_alignment_context?: Record<string, unknown>;
            alignment_issues?: string[];
            execution_issues?: string[];
            capacity_issues?: string[];
            suggestions?: string[];
        };
    };
    result?: Record<string, unknown>;
    created_at?: string;
    updated_at?: string;
};

export type TaskRun = {
    id?: number;
    strategy_id?: string | null;
    task_name?: string;
    task_scope?: string;
    task_key?: string;
    status?: string;
    trace_id?: string;
    payload?: Record<string, unknown>;
    result?: Record<string, unknown>;
    error?: string | null;
    started_at?: string;
    completed_at?: string | null;
};

export type ListResponse<T> = {
    items?: T[];
    count?: number;
    latest?: T | null;
};

export type StrategyDetailResponse = {
    dto_version?: string;
    strategy?: StrategyCore;
    metrics?: StrategyMetric[];
    reviews?: StrategyReview[];
    nav_series?: number[];
    latest_quality_report?: ReviewReportResponse | null;
    incubation_account?: IncubationAccount | null;
    latest_incubation_metric?: IncubationMetric | null;
    latest_promotion_review?: PromotionReview | null;
    latest_projection_snapshot?: ProjectionSnapshot | null;
    latest_vector_index_snapshot?: VectorIndexSnapshot | null;
    latest_incubation_pipeline_snapshot?: IncubationPipelineSnapshot | null;
    latest_runtime_risk_snapshot?: RuntimeRiskSnapshot | null;
    runtime_control?: RuntimeControl | null;
    runtime_alerts?: RuntimeAlert[];
    open_risk_events?: RiskEvent[];
    vector_profiles?: VectorProfile[];
    similar_vector_profiles?: VectorProfile[];
    domain_events?: DomainEvent[];
    task_runs?: TaskRun[];
    view_model?: {
        quality?: {
            latest_report?: ReviewReportResponse | null;
        };
        incubation?: {
            account?: IncubationAccount | null;
            latest_metric?: IncubationMetric | null;
            latest_pipeline_snapshot?: IncubationPipelineSnapshot | null;
        };
        runtime?: {
            control?: RuntimeControl | null;
            latest_risk_snapshot?: RuntimeRiskSnapshot | null;
            alerts?: RuntimeAlert[];
            risk_events?: RiskEvent[];
        };
        vectors?: {
            profiles?: VectorProfile[];
            similar_profiles?: VectorProfile[];
            latest_index_snapshot?: VectorIndexSnapshot | null;
        };
        domain?: {
            events?: DomainEvent[];
            task_runs?: TaskRun[];
            latest_projection_snapshot?: ProjectionSnapshot | null;
        };
    };
};

export type EventFilters = {
    event_type: string;
    from_status: string;
    to_status: string;
    actor_id: string;
    start_time: string;
    end_time: string;
    limit: string;
};

export type DashboardQuickAction = {
    href: string;
    icon: string;
    title: string;
    description: string;
};

export type DashboardWatchlistItem = {
    code: string;
    name?: string;
};

export type DashboardRecentStock = {
    code: string;
    name?: string;
    ts: number;
};

export type DashboardMarketNewsItem = {
    id?: string | number;
    title?: string;
    name?: string;
    publish_time?: string;
    time?: string;
    date?: string;
};

export type DashboardMarketNewsResponse = {
    items?: DashboardMarketNewsItem[];
};

export type DashboardMarketAnomaly = {
    title: string;
    value: string;
    href: string;
    tone: 'danger' | 'success' | 'info' | 'warning';
};

export type DashboardQuoteSnapshot = Partial<Pick<NormalizedQuote, 'code' | 'name' | 'price' | 'change' | 'changePercent' | 'change_pct'>>;

export type DashboardModuleStatus = 'ok' | 'loading' | 'error';

export type StockSentimentSnapshot = {
    score?: number;
    sentiment_score?: number;
    signal?: string;
    label?: string;
    summary?: string;
};

export type StockFundFlowEntry = {
    date?: string;
    netInflow?: number;
    net_inflow?: number;
    main_net_inflow?: number;
    mainNetInflow?: number;
};

export type StockFundamentalOverview = {
    pe?: number;
    pb?: number;
    eps?: number;
    roe?: number;
    gross_margin?: number;
    net_margin?: number;
};

export type StockNewsItem = {
    id?: string | number;
    title?: string;
    source?: string;
    publish_time?: string;
    summary?: string;
    url?: string;
};

export type StockValuationOverview = {
    pe?: number;
    pe_ttm?: number;
    pb?: number;
    ps?: number;
    pcf?: number;
    market_cap?: number;
    float_market_cap?: number;
    pe_percentile?: number;
    pb_percentile?: number;
    dividend_yield?: number;
    premium_percentile?: number;
};

export type StockDetailActionCard = {
    title: string;
    tone: 'danger' | 'success' | 'warning' | 'info' | 'neutral';
    summary: string;
    reasons: string[];
    links: Array<{ label: string; href: string }>;
};

export type StockDetailAggregateDto = {
    code: string;
    quote?: NormalizedQuote | null;
    kline?: NormalizedKlinePoint[];
    orderBook?: NormalizedOrderBook | null;
    sentiment?: StockSentimentSnapshot | null;
    fundFlow?: StockFundFlowEntry[];
    fundamental?: StockFundamentalOverview | null;
    valuation?: StockValuationOverview | null;
    news?: StockNewsItem[];
    actions?: StockDetailActionCard[];
};

export type EventTimelineDirection = 'past' | 'today' | 'upcoming';

export type EventTimelineScope = 'stock' | 'market';

export type EventTimelineItem = {
    id?: string;
    code?: string | null;
    title: string;
    summary?: string | null;
    type?: string | null;
    eventType?: string | null;
    scope?: EventTimelineScope;
    importance?: 'low' | 'medium' | 'high' | null;
    direction: EventTimelineDirection;
    eventDate?: string | null;
    eventTime?: string | null;
    source?: string | null;
    url?: string | null;
    sourceUrl?: string | null;
    tags?: string[];
    raw?: Record<string, unknown>;
};

export type EventTimelineResponse = {
    scope: EventTimelineScope;
    code?: string;
    count: number;
    limit?: number;
    days?: number;
    type?: string;
    highlights: string[];
    fallbackUsed?: boolean;
    source?: string | null;
    sourceChain?: string[];
    events: EventTimelineItem[];
    sourceTool?: string;
    argsMatched?: Record<string, unknown>;
    result?: unknown;
};

export type EventSubscriptionItem = {
    code: string;
    name?: string | null;
    groupId: string;
    groupName: string;
    addedAt?: string;
};

export type EventSubscriptionsResponse = {
    groupId: string;
    groupName: string;
    count: number;
    items: EventSubscriptionItem[];
    sourceTool?: string;
    argsMatched?: Record<string, unknown>;
    result?: unknown;
};

export type EventSubscriptionMutationResponse = {
    subscribed: boolean;
    alreadySubscribed?: boolean;
    removed?: boolean;
    item: EventSubscriptionItem | null;
    message: string;
};

export type EventImportantItem = EventTimelineItem & {
    rank?: number;
    subscribed: boolean;
    reasons: string[];
};

export type EventImportantResponse = {
    count: number;
    days: number;
    limit: number;
    subscriptionCount?: number;
    highlights?: string[];
    items: EventImportantItem[];
    sourceTool?: string;
    sourceTools?: Record<string, string | undefined>;
    argsMatched?: Record<string, unknown>;
    result?: unknown;
};

export type PerformanceAttributionComponent = {
    return?: number | null;
    contribution?: number | null;
    description?: string | null;
    status?: string | null;
    basis?: string | null;
    alignedDays?: number | null;
    assetsUsed?: number | null;
    staticTotalReturn?: number | null;
    realizedTotalReturn?: number | null;
};

export type PerformanceAttributionStockItem = {
    code?: string;
    sector?: string;
    weight?: number | null;
    weightPct?: number | null;
    stockReturn?: number | null;
    stockReturnPct?: number | null;
    lifetimeReturn?: number | null;
    lifetimeReturnPct?: number | null;
    contribution?: number | null;
    contributionPct?: number | null;
};

export type PerformanceSectorPerformanceItem = {
    sector: string;
    weight?: number | null;
    weightPct?: number | null;
    return?: number | null;
    returnPct?: number | null;
};

export type PerformanceBenchmarkAlignment = {
    benchmark: string;
    benchmarkReturn?: number | null;
    benchmarkReturnPct?: number | null;
    excessReturn?: number | null;
    excessReturnPct?: number | null;
    aligned?: boolean;
    alignmentMethod?: string | null;
};

export type PerformanceAttributionResponse = {
    message?: string | null;
    portfolioId: number | null;
    portfolioName: string | null;
    autoSelectedPortfolio: boolean;
    benchmark: string;
    lookbackDays: number;
    totalReturn?: number | null;
    totalReturnPct?: number | null;
    attribution?: {
        stockSelection?: PerformanceAttributionComponent | null;
        sectorAllocation?: PerformanceAttributionComponent | null;
        timing?: PerformanceAttributionComponent | null;
    };
    attributionByStock: PerformanceAttributionStockItem[];
    sectorPerformance: PerformanceSectorPerformanceItem[];
    benchmarkAlignment?: PerformanceBenchmarkAlignment | null;
    method?: string | null;
    windowAudit?: Record<string, unknown> | null;
    fees?: Record<string, unknown> | null;
    sourceTool?: string;
    argsMatched?: Record<string, unknown>;
    result?: unknown;
};

export type PerformanceBenchmarkComparisonResponse = {
    message?: string | null;
    portfolioId: number | null;
    portfolioName: string | null;
    autoSelectedPortfolio: boolean;
    benchmark: string;
    lookbackDays: number;
    alignedDays?: number | null;
    portfolioReturn?: number | null;
    portfolioReturnPct?: number | null;
    benchmarkReturn?: number | null;
    benchmarkReturnPct?: number | null;
    excessReturn?: number | null;
    excessReturnPct?: number | null;
    trackingError?: number | null;
    trackingErrorPct?: number | null;
    annualizedExcessReturn?: number | null;
    annualizedExcessReturnPct?: number | null;
    informationRatio?: number | null;
    outperformance?: boolean;
    portfolioTotalReturnAccount?: number | null;
    portfolioTotalReturnSeries?: number | null;
    windowAudit?: Record<string, unknown> | null;
    fees?: Record<string, unknown> | null;
    sourceTool?: string;
    argsMatched?: Record<string, unknown>;
    result?: unknown;
};

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

export type WorkspaceLayoutDensity = 'comfortable' | 'compact' | 'dense';

export type WorkspaceLayoutPreset = 'research' | 'trading' | 'focus' | 'custom';

export type WorkspacePagePanelMode = 'single' | 'split';

export type WorkspacePagePanelPlacement = 'left' | 'right';

export type WorkspacePageKey = string;

export type WorkspaceTaskStatus = 'todo' | 'active' | 'done';

export type WorkspaceSharedContext = {
    stockCode?: string;
    eventCode?: string;
    accountId?: string;
    executionId?: string;
    artifactId?: string;
    portfolioId?: string;
    benchmark?: string;
    mode?: 'account' | 'portfolio';
    days?: number;
    lookbackDays?: number;
    strategyId?: string;
    strategyName?: string;
    copilotConversationId?: string;
    screenerQuery?: string;
};

export type WorkspacePagePanelLayout = {
    mode: WorkspacePagePanelMode;
    secondaryPlacement: WorkspacePagePanelPlacement;
    secondarySize: number;
};

export type WorkspaceLayout = {
    preset: WorkspaceLayoutPreset;
    navCollapsed: boolean;
    navWidth: number;
    dockVisible: boolean;
    dockWidth: number;
    density: WorkspaceLayoutDensity;
    pageWidth: 'wide' | 'focused';
    pagePanels?: Record<WorkspacePageKey, WorkspacePagePanelLayout>;
};

export type WorkspaceSavedView = {
    id: string;
    pageKey: WorkspacePageKey;
    name: string;
    snapshot: Record<string, unknown>;
    createdAt: number;
    updatedAt: number;
};

export type WorkspaceTask = {
    id: string;
    pageKey: WorkspacePageKey;
    title: string;
    href?: string;
    kind?: string;
    payload?: Record<string, unknown>;
    status: WorkspaceTaskStatus;
    createdAt: number;
    updatedAt: number;
};

export type WorkspaceRecord = {
    id: string;
    name: string;
    createdAt: number;
    updatedAt: number;
    layout: WorkspaceLayout;
    context: WorkspaceSharedContext;
    savedViews: WorkspaceSavedView[];
    tasks: WorkspaceTask[];
};

export type WorkspaceStateSnapshot = {
    activeWorkspaceId: string;
    workspaces: WorkspaceRecord[];
    updatedAt: string | null;
};
