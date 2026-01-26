/**
 * AKShare 适配器
 * 用于基本面数据、财务报表等
 * AKShare 是 Python 库，这里通过其 HTTP API 接口访问
 */

import axios, { type AxiosInstance, type AxiosError } from 'axios';
import { config } from '../config/index.js';
import { cache, CacheAdapter } from './cache-adapter.js';
import { rateLimiter } from './rate-limiter.js';
import { CACHE_TTL, AKSHARE_CONFIG } from '../config/constants.js';
import type { FinancialData, RealtimeQuote, KlineData, KlinePeriod, NorthFund } from '../types/stock.js';
import type { QuoteAdapter } from '../types/adapters.js';

const SOURCE = 'akshare';

export class AKShareAdapter implements QuoteAdapter {
    readonly name: 'akshare' = 'akshare';
    private client: AxiosInstance;

    constructor(baseUrl?: string) {
        const proxyUrl = baseUrl || AKSHARE_CONFIG.PROXY_URL;

        this.client = axios.create({
            baseURL: proxyUrl,
            timeout: config.timeout || 10000,
            headers: {
                'Accept': '*/*',
            },
        });

        this.client.interceptors.response.use(
            response => response,
            (error: AxiosError) => {
                if (error.code === 'ECONNREFUSED') {
                    console.warn(`[AKShare] Connection refused to ${proxyUrl} - service may not be running`);
                } else if (error.code === 'ETIMEDOUT') {
                    console.warn(`[AKShare] Request timeout to ${proxyUrl}`);
                }
                throw error;
            }
        );
    }

    async isAvailable(): Promise<boolean> {
        try {
            // 尝试简单请求检测服务是否可用
            await this.client.get('/health', { timeout: 2000 });
            return true;
        } catch {
            // 服务不可用
            return false;
        }
    }

    async refreshHealth(): Promise<boolean> {
        return false;
    }

    async getServiceStatus(): Promise<{
        available: boolean;
        url: string;
        consecutiveFailures: number;
        lastCheck: Date | null;
    }> {
        return {
            available: false,
            url: this.client.defaults.baseURL || AKSHARE_CONFIG.PROXY_URL,
            consecutiveFailures: 0,
            lastCheck: null,
        };
    }

    private sleep(ms: number): Promise<void> {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    async requestWithRetry<T>(
        path: string,
        params?: Record<string, unknown>,
        retries: number = 3
    ): Promise<T> {
        let lastError: Error | null = null;

        for (let attempt = 0; attempt <= retries; attempt++) {
            try {
                const response = await this.client.get(path, { params });
                return response.data as T;
            } catch (error) {
                lastError = error as Error;
                if (attempt < retries) {
                    const backoff = Math.min(1000 * Math.pow(2, attempt), 8000);
                    const jitter = Math.floor(Math.random() * 200);
                    await this.sleep(backoff + jitter);
                }
            }
        }

        throw lastError;
    }

    async getRealtimeQuote(code: string): Promise<RealtimeQuote> {
        const cacheKey = CacheAdapter.generateKey('quote', SOURCE, code);
        const cached = cache.get<RealtimeQuote>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const response = await this.client.get('/api/public/stock_zh_a_spot_em', {
                params: { symbol: code },
            });

            const data = response.data;
            return this.parseQuote(code, data);
        });

        cache.set(cacheKey, result, CACHE_TTL.REALTIME_QUOTE);
        return result;
    }

    async getBatchQuotes(codes: string[]): Promise<RealtimeQuote[]> {
        const results: RealtimeQuote[] = [];

        for (const code of codes) {
            try {
                const quote = await this.getRealtimeQuote(code);
                results.push(quote);
            } catch {
                // 跳过失败的
            }
        }

        return results;
    }

    async getKline(code: string, period: KlinePeriod, limit: number): Promise<KlineData[]> {
        const cacheKey = CacheAdapter.generateKey('kline', SOURCE, code, period, limit.toString());
        const cached = cache.get<KlineData[]>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const periodMap: Record<KlinePeriod, string> = {
                '1m': '1',
                '5m': '5',
                '15m': '15',
                '30m': '30',
                '60m': '60',
                'daily': 'daily',
                'weekly': 'weekly',
                'monthly': 'monthly',
                '101': 'daily',
                '102': 'weekly',
                '103': 'monthly',
            };

            const response = await this.client.get('/api/public/stock_zh_a_hist', {
                params: {
                    symbol: code,
                    period: periodMap[period] || 'daily',
                    adjust: 'qfq',
                },
            });

            const klines: KlineData[] = [];
            const data = response.data || [];

            for (const row of data.slice(-limit)) {
                klines.push({
                    date: row['日期'] || row.date,
                    open: parseFloat(row['开盘'] || row.open),
                    close: parseFloat(row['收盘'] || row.close),
                    high: parseFloat(row['最高'] || row.high),
                    low: parseFloat(row['最低'] || row.low),
                    volume: parseInt(row['成交量'] || row.volume, 10),
                    amount: parseFloat(row['成交额'] || row.amount || 0),
                });
            }

            return klines;
        });

        const ttl = period.includes('m') ? CACHE_TTL.KLINE_INTRADAY : CACHE_TTL.KLINE;
        cache.set(cacheKey, result, ttl);
        return result;
    }

    async getFinancials(code: string): Promise<FinancialData> {
        const cacheKey = CacheAdapter.generateKey('financials', SOURCE, code);
        const cached = cache.get<FinancialData>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const response = await this.client.get('/api/public/stock_financial_analysis_indicator', {
                params: { symbol: code },
            });

            const data = response.data?.[0] || {};

            return {
                code,
                reportDate: data['报告期'] || '',
                revenue: parseFloat(data['营业总收入'] || 0),
                netProfit: parseFloat(data['净利润'] || 0),
                grossProfitMargin: parseFloat(data['销售毛利率'] || 0),
                netProfitMargin: parseFloat(data['销售净利率'] || 0),
                roe: parseFloat(data['净资产收益率'] || 0),
                roa: parseFloat(data['总资产收益率'] || 0),
                debtRatio: parseFloat(data['资产负债率'] || 0),
                currentRatio: parseFloat(data['流动比率'] || 0),
                eps: parseFloat(data['基本每股收益'] || 0),
                bvps: parseFloat(data['每股净资产'] || 0),
            };
        });

        cache.set(cacheKey, result, CACHE_TTL.FINANCIAL);
        return result;
    }

    async getNorthFund(days: number): Promise<NorthFund[]> {
        const cacheKey = CacheAdapter.generateKey('northfund', SOURCE, days.toString());
        const cached = cache.get<NorthFund[]>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            try {
                const response = await this.client.get('/api/public/stock_hsgt_hist_em', {
                    params: { symbol: '沪股通' },
                });

                const shData = response.data || [];

                const szResponse = await this.client.get('/api/public/stock_hsgt_hist_em', {
                    params: { symbol: '深股通' },
                });
                const szData = szResponse.data || [];

                const dateMap = new Map<string, { sh: number; sz: number; total: number; cumulative: number }>();

                for (const row of shData) {
                    const dateStr = row['日期'] || row.date || '';
                    const date = dateStr.split('T')[0];
                    if (!date) continue;

                    const netBuy = parseFloat(row['当日成交净买额'] || row['当日资金流入'] || 0);
                    const cumulative = parseFloat(row['历史累计净买额'] || 0);

                    if (!dateMap.has(date)) {
                        dateMap.set(date, { sh: 0, sz: 0, total: 0, cumulative: 0 });
                    }
                    const entry = dateMap.get(date)!;
                    entry.sh = netBuy * 100000000;
                    entry.cumulative = cumulative * 100000000;
                }

                for (const row of szData) {
                    const dateStr = row['日期'] || row.date || '';
                    const date = dateStr.split('T')[0];
                    if (!date) continue;

                    const netBuy = parseFloat(row['当日成交净买额'] || row['当日资金流入'] || 0);

                    if (!dateMap.has(date)) {
                        dateMap.set(date, { sh: 0, sz: 0, total: 0, cumulative: 0 });
                    }
                    const entry = dateMap.get(date)!;
                    entry.sz = netBuy * 100000000;
                    entry.total = entry.sh + entry.sz;
                }

                const results: NorthFund[] = [];
                const sortedDates = Array.from(dateMap.keys()).sort().slice(-days);

                for (const date of sortedDates) {
                    const entry = dateMap.get(date)!;
                    results.push({
                        date,
                        shConnect: entry.sh,
                        szConnect: entry.sz,
                        total: entry.total,
                        cumulative: entry.cumulative,
                    });
                }

                return results;
            } catch (error) {
                console.warn('[AKShare] North fund API failed:', error);
                return [];
            }
        });

        if (result.length > 0) {
            cache.set(cacheKey, result, CACHE_TTL.NORTH_FUND);
        }
        return result;
    }

    async getStockList(): Promise<Array<{ code: string; name: string }>> {
        const cacheKey = CacheAdapter.generateKey('stocklist', SOURCE);
        const cached = cache.get<Array<{ code: string; name: string }>>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const response = await this.client.get('/api/public/stock_info_a_code_name');

            return (response.data || []).map((item: { code: string; name: string }) => ({
                code: item.code,
                name: item.name,
            }));
        });

        cache.set(cacheKey, result, CACHE_TTL.FINANCIAL);
        return result;
    }

    private parseQuote(code: string, data: Record<string, unknown>): RealtimeQuote {
        return {
            code,
            name: String(data['名称'] || data.name || ''),
            price: parseFloat(String(data['最新价'] || data.price || 0)),
            change: parseFloat(String(data['涨跌额'] || data.change || 0)),
            changePercent: parseFloat(String(data['涨跌幅'] || data.changePercent || 0)),
            open: parseFloat(String(data['今开'] || data.open || 0)),
            high: parseFloat(String(data['最高'] || data.high || 0)),
            low: parseFloat(String(data['最低'] || data.low || 0)),
            preClose: parseFloat(String(data['昨收'] || data.preClose || 0)),
            volume: parseInt(String(data['成交量'] || data.volume || 0), 10),
            amount: parseFloat(String(data['成交额'] || data.amount || 0)),
            turnoverRate: parseFloat(String(data['换手率'] || data.turnoverRate || 0)),
            timestamp: Date.now(),
        };
    }
}

export const akShareAdapter = new AKShareAdapter();
