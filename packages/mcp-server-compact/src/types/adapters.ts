/**
 * 适配器相关类型定义
 */

import type { RealtimeQuote, KlineData, StockInfo, FinancialData, DragonTiger, NorthFund, SectorData, KlinePeriod } from './stock.js';

/**
 * 数据源类型
 */
export type DataSource = 'akshare' | 'eastmoney' | 'sina' | 'xueqiu' | 'tushare' | 'baostock' | 'wind' | 'tencent' | 'database';

/**
 * 适配器基础接口
 */
export interface DataAdapter {
    name: DataSource;
    isAvailable(): Promise<boolean>;
}

/**
 * 行情适配器接口
 */
export interface QuoteAdapter extends DataAdapter {
    getRealtimeQuote(code: string): Promise<RealtimeQuote>;
    getBatchQuotes(codes: string[]): Promise<RealtimeQuote[]>;
    getKline(code: string, period: KlinePeriod, limit: number): Promise<KlineData[]>;
}

/**
 * 基本面适配器接口
 */
export interface FundamentalAdapter extends DataAdapter {
    getStockInfo(code: string): Promise<StockInfo>;
    getFinancials(code: string): Promise<FinancialData>;
}

/**
 * 市场数据适配器接口
 */
export interface MarketAdapter extends DataAdapter {
    getDragonTiger(date?: string): Promise<DragonTiger[]>;
    getNorthFund(days: number): Promise<NorthFund[]>;
    getSectorFlow(topN: number): Promise<SectorData[]>;
}

/**
 * 缓存项
 */
export interface CacheItem<T> {
    data: T;
    expireAt: number;
}

/**
 * 缓存适配器接口
 */
export interface CacheAdapter {
    get<T>(key: string): T | undefined;
    set<T>(key: string, value: T, ttl?: number): void;
    has(key: string): boolean;
    delete(key: string): void;
    clear(): void;
}

/**
 * 限流配置
 */
export interface RateLimiterConfig {
    maxConcurrent: number;
    minTime: number; // ms between requests
    reservoir?: number;
    reservoirRefreshAmount?: number;
    reservoirRefreshInterval?: number; // ms
}

/**
 * API 请求选项
 */
export interface RequestOptions {
    timeout?: number;
    retries?: number;
    retryDelay?: number;
}

/**
 * API 响应
 */
export interface ApiResponse<T> {
    success: boolean;
    data?: T;
    error?: string;
    source?: DataSource;
    cached?: boolean;
    /** 数据质量信息 */
    quality?: {
        /** 是否通过校验 */
        valid: boolean;
        /** 校验警告 */
        warnings?: string[];
        /** 数据获取时间 */
        asOf?: string;
        /** 是否经过降级处理 */
        degraded?: boolean;
        /** 降级原因 */
        degradeReason?: string;
    };
}
