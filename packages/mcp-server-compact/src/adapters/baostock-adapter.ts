/**
 * Baostock 适配器
 * 通过可选的本地代理服务获取数据
 */

import axios, { type AxiosInstance } from 'axios';
import { config } from '../config/index.js';
import { BAOSTOCK_CONFIG, CACHE_TTL } from '../config/constants.js';
import { cache, CacheAdapter } from './cache-adapter.js';
import { rateLimiter } from './rate-limiter.js';
import type { QuoteAdapter } from '../types/adapters.js';
import type { KlineData, KlinePeriod, RealtimeQuote } from '../types/stock.js';

const SOURCE: 'baostock' = 'baostock';

export class BaostockAdapter implements QuoteAdapter {
    readonly name: 'baostock' = 'baostock';
    private client: AxiosInstance;
    private baseUrl: string | undefined;

    constructor() {
        this.client = axios.create({
            timeout: config.timeout,
            headers: { 'Content-Type': 'application/json' },
        });
        this.baseUrl = BAOSTOCK_CONFIG.PROXY_URL || undefined;
    }

    async isAvailable(): Promise<boolean> {
        const baseUrl = this.resolveBaseUrl();
        if (!baseUrl) return false;
        try {
            const response = await this.client.get(`${baseUrl}/health`);
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

    private async post<T>(path: string, payload: Record<string, unknown>): Promise<T> {
        const baseUrl = this.resolveBaseUrl();
        if (!baseUrl) {
            throw new Error('Baostock 代理未配置，请设置 BAOSTOCK_PROXY_URL');
        }

        const response = await this.client.post(`${baseUrl}${path}`, payload);
        const data = response.data;

        if (data && typeof data === 'object') {
            if (data.success === false) {
                throw new Error(data.error || 'Baostock 代理返回错误');
            }
            if ('data' in data) {
                return data.data as T;
            }
        }

        return data as T;
    }

    private resolveBaseUrl(): string | undefined {
        const envUrl = String(process.env.BAOSTOCK_PROXY_URL || '').trim();
        if (envUrl) {
            this.baseUrl = envUrl;
        }
        return this.baseUrl;
    }
}

export const baostockAdapter = new BaostockAdapter();
