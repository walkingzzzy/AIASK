/**
 * 东方财富行情 API
 */

import { EastMoneyBase, SOURCE, cache, CacheAdapter, rateLimiter, CACHE_TTL } from './base.js';
import type { RealtimeQuote, OrderBook, TradeDetail } from '../../types/stock.js';

export class QuoteAPI extends EastMoneyBase {
    /**
     * 获取实时行情
     */
    async getRealtimeQuote(code: string): Promise<RealtimeQuote> {
        const cacheKey = CacheAdapter.generateKey('quote', SOURCE, code);
        const cached = cache.get<RealtimeQuote>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const secId = this.convertToSecId(code);
            const url = `https://push2.eastmoney.com/api/qt/stock/get`;

            const response = await this.client.get(url, {
                params: {
                    secid: secId,
                    fields: 'f43,f44,f45,f46,f47,f48,f50,f51,f52,f57,f58,f60,f168,f169,f170,f171',
                },
            });

            const data = response.data?.data;
            if (!data) {
                throw new Error(`无法获取 ${code} 的行情数据：API 返回为空`);
            }

            return this.parseQuote(code, data);
        });

        cache.set(cacheKey, result, CACHE_TTL.REALTIME_QUOTE);
        return result;
    }

    /**
     * 获取股票基本信息
     */
    async getStockInfo(code: string): Promise<import('../../types/stock.js').StockInfo> {
        const quote = await this.getRealtimeQuote(code);
        return {
            code: quote.code,
            name: quote.name,
            market: quote.code.startsWith('6') ? 'SSE' : 'SZSE', // Simple inference
            industry: '未知',
            listDate: '',
            sector: '未知',
            totalShares: 0,
            floatShares: 0,
            marketCap: (quote.marketCap || 0),
            floatMarketCap: (quote.floatMarketCap || 0),
        };
    }

    /**
     * 批量获取行情
     */
    async getBatchQuotes(codes: string[]): Promise<RealtimeQuote[]> {
        const results: RealtimeQuote[] = [];
        const uncached: string[] = [];

        for (const code of codes) {
            const cacheKey = CacheAdapter.generateKey('quote', SOURCE, code);
            const cached = cache.get<RealtimeQuote>(cacheKey);
            if (cached) {
                results.push(cached);
            } else {
                uncached.push(code);
            }
        }

        if (uncached.length === 0) {
            return results;
        }

        const BATCH_SIZE = 80;
        const batches: string[][] = [];
        for (let i = 0; i < uncached.length; i += BATCH_SIZE) {
            batches.push(uncached.slice(i, i + BATCH_SIZE));
        }

        for (const batch of batches) {
            try {
                const secIdList = batch.map((c: any) => this.convertToSecId(c));
                const secIds = secIdList.join(',');
                const secIdToOriginalCode = new Map<string, string>();
                for (let i = 0; i < batch.length; i++) {
                    secIdToOriginalCode.set(secIdList[i] || '', batch[i] || '');
                }

                const batchResults = await rateLimiter.schedule(SOURCE, async () => {
                    const url = `https://push2.eastmoney.com/api/qt/ulist.np/get`;

                    const response = await this.client.get(url, {
                        params: {
                            secids: secIds,
                            fields: 'f12,f13,f14,f2,f3,f4,f5,f6,f7,f9,f15,f16,f17,f18,f20,f21,f23',
                        },
                    });

                    return response.data?.data?.diff || [];
                });

                for (const item of batchResults) {
                    const pureCode = String(item.f12 || '');
                    const market = item.f13;
                    const secId = (market !== undefined && market !== null && pureCode)
                        ? `${String(market)}.${pureCode}`
                        : '';
                    const originalCode = secId ? secIdToOriginalCode.get(secId) : undefined;
                    const code = originalCode || pureCode;

                    if (code) {
                        const quote: RealtimeQuote = {
                            code,
                            name: String(item.f14 || ''),
                            price: (item.f2 || 0) / 100,
                            change: (item.f4 || 0) / 100,
                            changePercent: (item.f3 || 0) / 100,
                            open: (item.f17 || 0) / 100,
                            high: (item.f15 || 0) / 100,
                            low: (item.f16 || 0) / 100,
                            preClose: (item.f18 || 0) / 100,
                            volume: item.f5 || 0,
                            amount: item.f6 || 0,
                            turnoverRate: (item.f7 || 0) / 100,
                            timestamp: Date.now(),
                            pe: item.f9 && item.f9 > 0 ? (item.f9 / 100) : undefined,
                            pb: item.f23 && item.f23 > 0 ? (item.f23 / 100) : undefined,
                            marketCap: item.f20 || undefined,
                            floatMarketCap: item.f21 || undefined,
                        };
                        const cacheKey = CacheAdapter.generateKey('quote', SOURCE, code);
                        cache.set(cacheKey, quote, CACHE_TTL.REALTIME_QUOTE);
                        results.push(quote);
                    }
                }

                if (batches.length > 1) {
                    await new Promise(resolve => setTimeout(resolve, 100));
                }
            } catch (error) {
                console.warn(`[${SOURCE}] Batch request failed for ${batch.length} stocks:`, error);
            }
        }

        return results;
    }

    /**
     * 获取五档盘口数据
     */
    async getOrderBook(code: string): Promise<OrderBook> {
        const cacheKey = CacheAdapter.generateKey('orderbook', SOURCE, code);
        const cached = cache.get<OrderBook>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const secId = this.convertToSecId(code);
            const url = `https://push2.eastmoney.com/api/qt/stock/get`;

            const response = await this.client.get(url, {
                params: {
                    secid: secId,
                    fields: 'f31,f32,f33,f34,f35,f36,f37,f38,f39,f40,f19,f20,f17,f18,f15,f16,f13,f14,f11,f12',
                },
            });

            const data = response.data?.data;
            if (!data) {
                throw new Error(`Failed to get orderbook for ${code}`);
            }

            return this.parseOrderBook(code, data);
        });

        cache.set(cacheKey, result, 3);
        return result;
    }

    /**
     * 获取成交明细
     */
    async getTradeDetails(code: string, limit: number = 20): Promise<TradeDetail[]> {
        const cacheKey = CacheAdapter.generateKey('trades', SOURCE, code, limit.toString());
        const cached = cache.get<TradeDetail[]>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const secId = this.convertToSecId(code);
            const url = `https://push2.eastmoney.com/api/qt/stock/details/get`;

            const response = await this.client.get(url, {
                params: {
                    secid: secId,
                    fields1: 'f1,f2,f3,f4',
                    fields2: 'f51,f52,f53,f54,f55',
                    pos: -limit,
                },
            });

            const details = response.data?.data?.details || [];
            return details.map((d: string) => this.parseTradeDetail(d));
        });

        cache.set(cacheKey, result, 5);
        return result;
    }

    // ========== 解析方法 ==========

    private parseQuote(code: string, data: Record<string, number>): RealtimeQuote {
        return {
            code,
            name: String(data.f58 || ''),
            price: (data.f43 || 0) / 100,
            change: (data.f169 || 0) / 100,
            changePercent: (data.f170 || 0) / 100,
            open: (data.f46 || 0) / 100,
            high: (data.f44 || 0) / 100,
            low: (data.f45 || 0) / 100,
            preClose: (data.f60 || 0) / 100,
            volume: data.f47 || 0,
            amount: data.f48 || 0,
            turnoverRate: (data.f168 || 0) / 100,
            timestamp: Date.now(),
        };
    }

    private parseOrderBook(code: string, data: Record<string, number>): OrderBook {
        return {
            code,
            timestamp: Date.now(),
            bids: [
                { price: (data.f19 || 0) / 100, volume: data.f20 || 0 },
                { price: (data.f17 || 0) / 100, volume: data.f18 || 0 },
                { price: (data.f15 || 0) / 100, volume: data.f16 || 0 },
                { price: (data.f13 || 0) / 100, volume: data.f14 || 0 },
                { price: (data.f11 || 0) / 100, volume: data.f12 || 0 },
            ],
            asks: [
                { price: (data.f31 || 0) / 100, volume: data.f32 || 0 },
                { price: (data.f33 || 0) / 100, volume: data.f34 || 0 },
                { price: (data.f35 || 0) / 100, volume: data.f36 || 0 },
                { price: (data.f37 || 0) / 100, volume: data.f38 || 0 },
                { price: (data.f39 || 0) / 100, volume: data.f40 || 0 },
            ],
        };
    }

    private parseTradeDetail(detailStr: string): TradeDetail {
        const parts = detailStr.split(',');
        return {
            time: parts[0] || '',
            price: parseFloat(parts[1]) || 0,
            volume: parseInt(parts[2], 10) || 0,
            amount: parseFloat(parts[3]) || 0,
            direction: parseInt(parts[4], 10) === 1 ? 'buy' : parseInt(parts[4], 10) === 2 ? 'sell' : 'neutral',
        };
    }
}

export const quoteAPI = new QuoteAPI();
