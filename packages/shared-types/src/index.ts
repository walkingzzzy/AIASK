/* ── @aiask/shared-types ── */

// API 响应信封
export type Envelope<T = unknown> = {
    ok: boolean;
    success?: boolean;
    data?: T;
    error?: string;
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

// 标准化行情快照
export type NormalizedQuote = {
    symbol: string;
    code?: string;           // alias used by frontend
    name: string;
    last: number;
    change: number;
    pct_change: number;
    changePercent?: number;  // alias used by frontend
    change_pct?: number;     // alias used by frontend
    volume: number;
    turnover: number;
    amount?: number;         // alias for turnover
    market_cap?: number;
    timestamp?: string;
    open?: number;
    close?: number;
    high?: number;
    low?: number;
    price?: number;
    prevClose?: number;
    pe?: number;
    pb?: number;
    eps?: number;
    amp?: number;
};

// 标准化 K 线点
export type NormalizedKlinePoint = {
    timestamp?: string;
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    turnover?: number;
};

// 标准化订单簿
export type NormalizedOrderBook = {
    symbol: string;
    bids: Array<{ price: number; volume: number }>;
    asks: Array<{ price: number; volume: number }>;
    timestamp: string;
};
