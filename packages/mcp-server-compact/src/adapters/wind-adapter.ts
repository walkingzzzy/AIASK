/**
 * Wind 适配器
 * 通过可选的本地代理服务获取数据
 */

import axios, { type AxiosInstance } from 'axios';
import { config } from '../config/index.js';
import { CACHE_TTL, WIND_CONFIG } from '../config/constants.js';
import { cache, CacheAdapter } from './cache-adapter.js';
import { rateLimiter } from './rate-limiter.js';
import type { QuoteAdapter, FundamentalAdapter } from '../types/adapters.js';
import type { FinancialData, KlineData, KlinePeriod, RealtimeQuote, StockInfo } from '../types/stock.js';

const SOURCE: 'wind' = 'wind';

export class WindAdapter implements QuoteAdapter, FundamentalAdapter {
    readonly name: 'wind' = 'wind';
    private client: AxiosInstance;
    private baseUrl: string | undefined;

    constructor() {
        this.client = axios.create({
            timeout: config.timeout,
            headers: { 'Content-Type': 'application/json' },
        });
        this.baseUrl = WIND_CONFIG.BASE_URL || undefined;
    }

    async isAvailable(): Promise<boolean> {
        if (!this.baseUrl) return false;
        try {
            const response = await this.client.get(`${this.baseUrl}/health`);
            return Boolean(response.data?.ok || response.data?.success || response.status === 200);
        } catch {
            return false;
        }
    }

    async getRealtimeQuote(code: string): Promise<RealtimeQuote> {
        const cacheKey = CacheAdapter.generateKey('quote', SOURCE, code);
        const cached = cache.get<RealtimeQuote>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            return this.post<RealtimeQuote>('/quote', { code });
        });

        cache.set(cacheKey, result, CACHE_TTL.REALTIME_QUOTE);
        return result;
    }

    async getBatchQuotes(codes: string[]): Promise<RealtimeQuote[]> {
        const result = await rateLimiter.schedule(SOURCE, async () => {
            return this.post<RealtimeQuote[]>('/batch-quote', { codes });
        });

        return Array.isArray(result) ? result : [];
    }

    async getKline(code: string, period: KlinePeriod, limit: number): Promise<KlineData[]> {
        const cacheKey = CacheAdapter.generateKey('kline', SOURCE, code, period, limit.toString());
        const cached = cache.get<KlineData[]>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            return this.post<KlineData[]>('/kline', { code, period, limit });
        });

        cache.set(cacheKey, result, CACHE_TTL.KLINE);
        return result;
    }

    async getStockInfo(code: string): Promise<StockInfo> {
        return this.post<StockInfo>('/stock-info', { code });
    }

    async getFinancials(code: string): Promise<FinancialData> {
        return this.post<FinancialData>('/financials', { code });
    }

    private async post<T>(path: string, payload: Record<string, unknown>): Promise<T> {
        if (!this.baseUrl) {
            throw new Error('Wind 服务未配置，请设置 WIND_BASE_URL');
        }

        const response = await this.client.post(`${this.baseUrl}${path}`, payload);
        const data = response.data;

        if (data && typeof data === 'object') {
            if (data.success === false) {
                throw new Error(data.error || 'Wind 服务返回错误');
            }
            if ('data' in data) {
                return data.data as T;
            }
        }

        return data as T;
    }
}

export const windAdapter = new WindAdapter();
