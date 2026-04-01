import type { NormalizedKlinePoint, NormalizedOrderBook, NormalizedQuote } from './market';

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

export type DashboardQuoteSnapshot = Partial<
    Pick<NormalizedQuote, 'code' | 'name' | 'price' | 'change' | 'changePercent' | 'change_pct'>
>;

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
