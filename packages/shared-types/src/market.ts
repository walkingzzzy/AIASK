import type { ToolArgs, ToolMeta } from './common';

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

export type NormalizedOrderBook = {
    symbol: string;
    bids: Array<{ price: number; volume: number }>;
    asks: Array<{ price: number; volume: number }>;
    timestamp: string | null;
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
