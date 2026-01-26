/**
 * 东方财富市场数据 API (龙虎榜、涨停板等)
 */

import { EastMoneyBase, SOURCE, cache, CacheAdapter, rateLimiter, CACHE_TTL } from './base.js';
import type { DragonTiger, LimitUpStock, LimitUpStatistics, SectorData } from '../../types/stock.js';
import { checkIsST, getLimitThreshold } from '../../utils/limit-rules.js';

export class MarketAPI extends EastMoneyBase {
    /**
     * 获取龙虎榜数据
     */
    async getDragonTiger(date?: string): Promise<DragonTiger[]> {
        const targetDate = date || this.getTodayStr();
        const cacheKey = CacheAdapter.generateKey('dragon', SOURCE, targetDate);
        const cached = cache.get<DragonTiger[]>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const url = `https://datacenter-web.eastmoney.com/api/data/v1/get`;

            const response = await this.client.get(url, {
                params: {
                    sortColumns: 'SECURITY_CODE',
                    sortTypes: 1,
                    pageSize: 50,
                    pageNumber: 1,
                    reportName: 'RPT_DAILYBILLBOARD_DETAILSNEW',
                    columns: 'SECURITY_CODE,SECUCODE,SECURITY_NAME_ABBR,TRADE_DATE,EXPLAIN,CLOSE_PRICE,CHANGE_RATE,BILLBOARD_NET_AMT,BILLBOARD_BUY_AMT,BILLBOARD_SELL_AMT',
                    filter: `(TRADE_DATE='${targetDate}')`,
                },
            });

            const items = response.data?.result?.data || [];
            return items.map((item: Record<string, unknown>) => this.parseDragonTiger(item));
        });

        cache.set(cacheKey, result, CACHE_TTL.SECTOR_FLOW);
        return result;
    }

    /**
     * 获取涨停板数据
     */
    async getLimitUpStocks(date?: string): Promise<LimitUpStock[]> {
        const cacheKey = CacheAdapter.generateKey('limitup', SOURCE, date || 'latest');
        const cached = cache.get<LimitUpStock[]>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const url = `https://data.eastmoney.com/dataapi/xuangu/list`;

            const response = await this.client.get(url, {
                params: {
                    st: 'CHANGE_RATE',
                    sr: -1,
                    ps: 200,
                    p: 1,
                    sty: 'SECUCODE,SECURITY_CODE,SECURITY_NAME_ABBR,CHANGE_RATE,CLOSE_PRICE,HIGH_PRICE,LOW_PRICE,OPEN_PRICE,VOLUME_RATIO,TURNOVERRATE,FREE_MARKET_CAP,INDUSTRY',
                    filter: '(CHANGE_RATE>=4.9)',
                },
            });

            const items = (response.data?.result?.data || []) as Array<Record<string, unknown>>;

            type ParsedLimitUpStock = LimitUpStock & { is20Percent?: boolean; _isLimitUp: boolean };

            const parsed: ParsedLimitUpStock[] = items.map((item) => {
                const changeRate = Number(item.CHANGE_RATE || 0);
                const code = String(item.SECURITY_CODE || '');
                const name = String(item.SECURITY_NAME_ABBR || '');
                const isST = checkIsST(name);
                const threshold = getLimitThreshold(code, isST);
                const isLimitUp = threshold !== null && changeRate >= threshold - 0.1;

                return {
                    code,
                    name,
                    price: Number(item.CLOSE_PRICE || item.HIGH_PRICE || 0),
                    changePercent: changeRate,
                    limitUpPrice: Number(item.HIGH_PRICE || 0),
                    firstLimitTime: '',
                    lastLimitTime: '',
                    openTimes: 0,
                    continuousDays: 1,
                    turnoverRate: Number(item.TURNOVERRATE || 0),
                    marketCap: Number(item.FREE_MARKET_CAP || 0),
                    industry: String(item.INDUSTRY || ''),
                    concept: '',
                    is20Percent: threshold === 20,
                    _isLimitUp: isLimitUp,
                };
            });

            return parsed
                .filter((s) => s._isLimitUp)
                .map(({ _isLimitUp: _ignored, ...rest }) => rest);
        });

        cache.set(cacheKey, result, CACHE_TTL.DEFAULT);
        return result;
    }

    /**
     * 获取涨停统计数据
     */
    async getLimitUpStatistics(date?: string): Promise<LimitUpStatistics> {
        const cacheKey = CacheAdapter.generateKey('limitupstats', SOURCE, date || 'latest');
        const cached = cache.get<LimitUpStatistics>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const limitUpStocks = await this.getLimitUpStocks(date);

            const total = limitUpStocks.length;
            const is20PercentCount = limitUpStocks.filter((s: any) => (s as unknown as { is20Percent?: boolean }).is20Percent).length;

            return {
                date: date || this.getTodayStr(),
                totalLimitUp: total,
                firstBoard: total,
                secondBoard: 0,
                thirdBoard: 0,
                higherBoard: 0,
                failedBoard: 0,
                limitDown: 0,
                successRate: 100,
                note: `其中20%涨停: ${is20PercentCount}只`,
            };
        });

        cache.set(cacheKey, result, CACHE_TTL.DEFAULT);
        return result;
    }

    /**
     * 获取市场板块列表（行业、概念、地域）
     */
    async getMarketBlocks(type: 'industry' | 'concept' | 'region'): Promise<Array<{
        code: string;
        name: string;
        changePercent: number;
        leadingStock?: string;
        stockCount?: number;
    }>> {
        const cacheKey = CacheAdapter.generateKey('marketblocks', SOURCE, type);
        const cached = cache.get<Array<{
            code: string;
            name: string;
            changePercent: number;
            leadingStock?: string;
            stockCount?: number;
        }>>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const url = `https://push2.eastmoney.com/api/qt/clist/get`;

            // 板块类型对应的 fs 参数
            // t:2 = 行业板块, t:3 = 概念板块, t:1 = 地域板块
            const typeMap: Record<'industry' | 'concept' | 'region', string> = {
                industry: 'm:90+t:2',
                concept: 'm:90+t:3',
                region: 'm:90+t:1',
            };

            let lastError: unknown = null;
            // 增加重试次数和指数退避来处理 socket hang up 问题
            for (let attempt = 0; attempt < 4; attempt += 1) {
                try {
                    const response = await this.client.get(url, {
                        params: {
                            pn: 1,
                            pz: 100,
                            po: 1,
                            np: 1,
                            fltt: 2,
                            invt: 2,
                            fs: typeMap[type],
                            fields: 'f12,f14,f3,f104,f128',
                        },
                        timeout: 15000, // 15秒超时
                    });

                    const items = response.data?.data?.diff || [];
                    return items.map((item: Record<string, unknown>) => ({
                        code: String(item.f12 || ''),
                        name: String(item.f14 || ''),
                        changePercent: Number(item.f3 || 0) / 100,
                        leadingStock: String(item.f128 || ''),
                        stockCount: Number(item.f104 || 0),
                    }));
                } catch (error) {
                    lastError = error;
                    // 指数退避: 500ms, 1000ms, 2000ms, 4000ms
                    await new Promise(resolve => setTimeout(resolve, 500 * Math.pow(2, attempt)));
                }
            }

            console.error(`[Eastmoney] getMarketBlocks failed: ${lastError}`);
            // Fallback: Return static major sectors to prevent workflow blocking
            if (type === 'industry') {
                return [
                    { code: 'BK0428', name: '银行', changePercent: 0, leadingStock: '600036', stockCount: 42 },
                    { code: 'BK0475', name: '证券', changePercent: 0, leadingStock: '600030', stockCount: 50 },
                    { code: 'BK0459', name: '酿酒行业', changePercent: 0, leadingStock: '600519', stockCount: 38 },
                    { code: 'BK0473', name: '保险', changePercent: 0, leadingStock: '601318', stockCount: 7 },
                    { code: 'BK0447', name: '半导体', changePercent: 0, leadingStock: '688981', stockCount: 153 },
                    { code: 'BK0493', name: '互联网服务', changePercent: 0, leadingStock: '300059', stockCount: 147 },
                    { code: 'BK0450', name: '光伏设备', changePercent: 0, leadingStock: '601012', stockCount: 68 },
                    { code: 'BK0448', name: '通信设备', changePercent: 0, leadingStock: '000063', stockCount: 120 },
                ];
            } else if (type === 'concept') {
                return [
                    { code: 'BK0984', name: 'AI语料', changePercent: 0, leadingStock: '300418', stockCount: 36 },
                    { code: 'BK0989', name: '算力概念', changePercent: 0, leadingStock: '000977', stockCount: 75 },
                    { code: 'BK0891', name: '信创', changePercent: 0, leadingStock: '600536', stockCount: 220 },
                ];
            }

            throw lastError;
        });

        cache.set(cacheKey, result, CACHE_TTL.SECTOR_FLOW);
        return result;
    }

    /**
     * 获取板块资金流向
     */
    async getSectorFlow(topN: number): Promise<SectorData[]> {
        const cacheKey = CacheAdapter.generateKey('sectorflow', SOURCE, topN.toString());
        const cached = cache.get<SectorData[]>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const url = `https://push2.eastmoney.com/api/qt/clist/get`;

            let lastError: unknown = null;
            for (let attempt = 0; attempt < 3; attempt += 1) {
                try {
                    const response = await this.client.get(url, {
                        params: {
                            pn: 1,
                            pz: topN,
                            po: 1,
                            np: 1,
                            fs: 'm:90+t:2',
                            fields: 'f12,f14,f3,f62,f184,f66',
                        },
                        timeout: 10000,
                    });

                    const items = response.data?.data?.diff || [];
                    return items.map((item: Record<string, number>) => this.parseSectorFlow(item));
                } catch (error) {
                    lastError = error;
                    await new Promise(resolve => setTimeout(resolve, 500 * Math.pow(2, attempt)));
                }
            }

            console.error(`[Eastmoney] getSectorFlow failed: ${lastError}`);
            // Fallback: Return empty list or static list with 0 flow to avoid crash
            return [];
        });

        cache.set(cacheKey, result, CACHE_TTL.DEFAULT);
        return result;
    }

    // ========== 解析方法 ==========

    private parseDragonTiger(item: Record<string, unknown>): DragonTiger {
        return {
            code: String(item.SECURITY_CODE || ''),
            name: String(item.SECURITY_NAME_ABBR || ''),
            date: String(item.TRADE_DATE || '').split(' ')[0],
            reason: String(item.EXPLAIN || ''),
            buyAmount: Number(item.BILLBOARD_BUY_AMT || 0),
            sellAmount: Number(item.BILLBOARD_SELL_AMT || 0),
            netAmount: Number(item.BILLBOARD_NET_AMT || 0),
            buyers: [],
            sellers: [],
        };
    }

    private parseSectorFlow(item: Record<string, number>): SectorData {
        return {
            code: String(item.f12 || ''),
            name: String(item.f14 || ''),
            change: 0,
            changePercent: item.f3 / 100,
            leadingStock: '',
            amount: item.f62,
            netInflow: item.f62 - item.f66,
        };
    }
}

export const marketAPI = new MarketAPI();
