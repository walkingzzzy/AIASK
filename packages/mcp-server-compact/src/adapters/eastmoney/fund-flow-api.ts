/**
 * 东方财富资金流向 API (北向资金、两融、大宗交易)
 */

import { EastMoneyBase, SOURCE, cache, CacheAdapter, rateLimiter, CACHE_TTL } from './base.js';
import { akShareAdapter } from '../akshare-adapter.js';
import { tushareAdapter } from '../tushare-adapter.js';
import type { NorthFund, MarginData, BlockTrade } from '../../types/stock.js';

export class FundFlowAPI extends EastMoneyBase {
    /**
     * 获取北向资金流向
     */
    async getNorthFund(days: number): Promise<NorthFund[]> {
        const cacheKey = CacheAdapter.generateKey('northfund', SOURCE, days.toString());
        const cached = cache.get<NorthFund[]>(cacheKey);
        if (cached && cached.length > 0 && this.validateNorthFundData(cached)) {
            return cached;
        }

        const result = await rateLimiter.schedule(SOURCE, async () => {
            console.error('[FundFlowAPI] Trying HsgtHistory API...');
            let results = await this.fetchNorthFundFromHsgtHistory(days);

            if (!this.validateNorthFundData(results)) {
                console.error('[FundFlowAPI] HsgtHistory returned invalid data, trying DataCenter API...');
                results = await this.fetchNorthFundFromDataCenter(days);
            }

            if (!this.validateNorthFundData(results)) {
                console.error('[FundFlowAPI] DataCenter returned invalid data, trying Push2 API...');
                results = await this.fetchNorthFundFromPush2(days);
            }

            if (!this.validateNorthFundData(results)) {
                console.error('[FundFlowAPI] Push2 returned invalid data, trying HSGT API...');
                results = await this.fetchNorthFundFromHsgt(days);
            }

            if (!this.validateNorthFundData(results)) {
                console.error('[FundFlowAPI] HSGT returned invalid data, trying Choice API...');
                results = await this.fetchNorthFundFromChoice(days);
            }

            if (!this.validateNorthFundData(results)) {
                console.error('[FundFlowAPI] Choice returned invalid data, trying AKShare...');
                try {
                    const akshareAvailable = await akShareAdapter.isAvailable();
                    // Even if isAvailable returns false, we might try if we want, but here we follow original logic
                    // Original logic checks isAvailable()
                    // But in our ported akshare implementation, isAvailable returns false. 
                    // So let's skip checking isAvailable and try calling if we really need it? 
                    // No, let's respect the logic: if !available, it prints log.
                    // But wait, the new implementation of akShareAdapter explicitly returns false for isAvailable.
                    // So this block will effectively be skipped unless we change akShareAdapter behavior.
                    if (akshareAvailable) {
                        results = await akShareAdapter.getNorthFund(days);
                        if (this.validateNorthFundData(results)) {
                            console.error('[FundFlowAPI] Successfully got data from AKShare');
                        }
                    } else {
                        // Fallback attempt directly if configured? 
                        // For now we stick to original logic.
                        console.error('[FundFlowAPI] AKShare service not available');
                    }
                } catch (error) {
                    console.warn('[FundFlowAPI] AKShare API failed:', error);
                }

            }

            // Try Tushare Pro as final fallback
            if (!this.validateNorthFundData(results)) {
                console.error('[FundFlowAPI] Trying Tushare Pro API...');
                try {
                    const tushareAvailable = await tushareAdapter.isAvailable();
                    if (tushareAvailable) {
                        const tushareData = await tushareAdapter.getNorthFund(days);
                        if (tushareData && tushareData.length > 0) {
                            results = tushareData.map((d: any) => ({
                                date: d.date,
                                shConnect: d.shConnect,
                                szConnect: d.szConnect,
                                total: d.total,
                                cumulative: d.cumulative,
                            }));
                            if (this.validateNorthFundData(results)) {
                                console.error('[FundFlowAPI] Successfully got data from Tushare Pro');
                            }
                        }
                    } else {
                        console.error('[FundFlowAPI] Tushare Pro not available (check TUSHARE_TOKEN env)');
                    }
                } catch (error) {
                    console.warn('[FundFlowAPI] Tushare Pro API failed:', error);
                }
            }

            if (!this.validateNorthFundData(results)) {
                console.warn('[FundFlowAPI] WARNING: All north fund APIs returned invalid data (all zeros or nulls).');
            }

            return results;
        });

        if (result.length > 0 && this.validateNorthFundData(result)) {
            cache.set(cacheKey, result, CACHE_TTL.NORTH_FUND);
        }
        return result;
    }

    /**
     * 校验北向资金数据有效性
     */
    private validateNorthFundData(data: NorthFund[]): boolean {
        if (!data || data.length === 0) return false;

        const hasValidData = data.some(item =>
            item.total !== 0 || item.shConnect !== 0 || item.szConnect !== 0
        );

        if (!hasValidData) {
            console.warn('[FundFlowAPI] All north fund data is zero, data invalid');
            return false;
        }

        return true;
    }

    private async fetchNorthFundFromHsgtHistory(days: number): Promise<NorthFund[]> {
        try {
            const url = `https://datacenter-web.eastmoney.com/api/data/v1/get`;

            const response = await this.client.get(url, {
                params: {
                    sortColumns: 'TRADE_DATE',
                    sortTypes: -1,
                    pageSize: days * 2,
                    pageNumber: 1,
                    reportName: 'RPT_MUTUAL_DEAL_HISTORY',
                    columns: 'TRADE_DATE,MUTUAL_TYPE,NET_DEAL_AMT,BUY_AMT,SELL_AMT,ACCUM_DEAL_AMT',
                    filter: '(MUTUAL_TYPE in ("001","003"))',
                    source: 'WEB',
                    client: 'WEB',
                },
            });

            const items = response.data?.result?.data || [];
            if (items.length === 0) return [];

            const dateMap = new Map<string, { sh: number; sz: number; total: number }>();

            for (const item of items) {
                const date = String(item.TRADE_DATE || '').split(' ')[0];
                if (!date) continue;

                let netInflow = Number(item.NET_DEAL_AMT || 0);
                if (netInflow === 0) {
                    const buyAmt = Number(item.BUY_AMT || 0);
                    const sellAmt = Number(item.SELL_AMT || 0);
                    netInflow = buyAmt - sellAmt;
                }

                const mutualType = String(item.MUTUAL_TYPE || '');

                if (!dateMap.has(date)) {
                    dateMap.set(date, { sh: 0, sz: 0, total: 0 });
                }

                const entry = dateMap.get(date)!;
                if (mutualType === '001') {
                    entry.sh = netInflow;
                } else if (mutualType === '003') {
                    entry.sz = netInflow;
                }
                entry.total = entry.sh + entry.sz;
            }

            return this.buildNorthFundResults(dateMap);
        } catch (error) {
            console.warn('[FundFlowAPI] HsgtHistory API failed:', error);
            return [];
        }
    }

    private async fetchNorthFundFromDataCenter(days: number): Promise<NorthFund[]> {
        try {
            const url = `https://datacenter-web.eastmoney.com/api/data/v1/get`;

            const response = await this.client.get(url, {
                params: {
                    sortColumns: 'TRADE_DATE',
                    sortTypes: -1,
                    pageSize: days,
                    pageNumber: 1,
                    reportName: 'RPT_HMUTUAL_DEAL_HISTORY',
                    columns: 'TRADE_DATE,BOARD_TYPE,NET_DEAL_AMT,BUY_AMT,SELL_AMT',
                    filter: '(BOARD_TYPE in ("1","3"))',
                },
            });

            const items = response.data?.result?.data || [];
            if (items.length === 0) return [];

            const dateMap = new Map<string, { sh: number; sz: number; total: number }>();

            for (const item of items) {
                const date = String(item.TRADE_DATE || '').split(' ')[0];
                const boardType = String(item.BOARD_TYPE || '');

                let netInflow = Number(item.NET_DEAL_AMT || 0);
                if (netInflow === 0) {
                    const buyAmt = Number(item.BUY_AMT || 0);
                    const sellAmt = Number(item.SELL_AMT || 0);
                    netInflow = buyAmt - sellAmt;
                }

                if (!dateMap.has(date)) {
                    dateMap.set(date, { sh: 0, sz: 0, total: 0 });
                }

                const entry = dateMap.get(date)!;
                if (boardType === '1') {
                    entry.sh = netInflow;
                } else if (boardType === '3') {
                    entry.sz = netInflow;
                }
                entry.total = entry.sh + entry.sz;
            }

            return this.buildNorthFundResults(dateMap);
        } catch (error) {
            console.warn('[FundFlowAPI] DataCenter API failed:', error);
            return [];
        }
    }

    private async fetchNorthFundFromChoice(_days: number): Promise<NorthFund[]> {
        try {
            const url = `https://push2.eastmoney.com/api/qt/kamtbs.rtmin/get`;

            const response = await this.client.get(url, {
                params: {
                    fields1: 'f1,f2,f3,f4',
                    fields2: 'f51,f52,f53,f54,f55,f56,f57,f58',
                },
            });

            const data = response.data?.data;
            if (!data) return [];

            const s2n = data.s2n || [];
            const s2s = data.s2s || [];

            if (s2n.length === 0 && s2s.length === 0) return [];

            const results: NorthFund[] = [];
            const today = this.getTodayStr();

            let shInflow = 0;
            let szInflow = 0;

            if (s2n.length > 0) {
                const lastSh = s2n[s2n.length - 1].split(',');
                shInflow = parseFloat(lastSh[1]) || 0;
            }
            if (s2s.length > 0) {
                const lastSz = s2s[s2s.length - 1].split(',');
                szInflow = parseFloat(lastSz[1]) || 0;
            }

            results.push({
                date: today,
                shConnect: shInflow * 10000,
                szConnect: szInflow * 10000,
                total: (shInflow + szInflow) * 10000,
                cumulative: 0,
            });

            return results;
        } catch (error) {
            console.warn('[FundFlowAPI] Choice API failed:', error);
            return [];
        }
    }

    private buildNorthFundResults(dateMap: Map<string, { sh: number; sz: number; total: number }>): NorthFund[] {
        const results: NorthFund[] = [];
        let cumulative = 0;

        const sortedDates = Array.from(dateMap.keys()).sort();
        for (const date of sortedDates) {
            const entry = dateMap.get(date)!;
            cumulative += entry.total;
            results.push({
                date,
                shConnect: entry.sh,
                szConnect: entry.sz,
                total: entry.total,
                cumulative,
            });
        }

        return results;
    }

    private async fetchNorthFundFromPush2(days: number): Promise<NorthFund[]> {
        try {
            const url = `https://push2his.eastmoney.com/api/qt/kamt.kline/get`;

            const response = await this.client.get(url, {
                params: {
                    fields1: 'f1,f2,f3,f4',
                    fields2: 'f51,f52,f53,f54,f55,f56',
                    klt: 101,
                    lmt: days,
                },
            });

            const data = response.data?.data;
            if (!data) return [];

            const hk2sh = data.hk2sh || [];
            const hk2sz = data.hk2sz || [];

            if (hk2sh.length === 0 && hk2sz.length === 0) return [];

            const results: NorthFund[] = [];
            for (let i = 0; i < Math.min(hk2sh.length, hk2sz.length); i++) {
                const shParts = hk2sh[i].split(',');
                const szParts = hk2sz[i].split(',');

                const date = shParts[0];
                const shInflow = parseFloat(shParts[1]) || 0;
                const szInflow = parseFloat(szParts[1]) || 0;
                const shCumulative = parseFloat(shParts[3]) || 0;
                const szCumulative = parseFloat(szParts[3]) || 0;

                results.push({
                    date,
                    shConnect: shInflow * 10000,
                    szConnect: szInflow * 10000,
                    total: (shInflow + szInflow) * 10000,
                    cumulative: (shCumulative + szCumulative) * 10000,
                });
            }

            return results.reverse();
        } catch (error) {
            console.warn('[FundFlowAPI] Push2 API failed:', error);
            return [];
        }
    }

    private async fetchNorthFundFromHsgt(days: number): Promise<NorthFund[]> {
        try {
            const url = `https://datacenter-web.eastmoney.com/api/data/v1/get`;

            const response = await this.client.get(url, {
                params: {
                    sortColumns: 'TRADE_DATE',
                    sortTypes: -1,
                    pageSize: days,
                    pageNumber: 1,
                    reportName: 'RPT_MUTUAL_QUOTA',
                    columns: 'TRADE_DATE,MUTUAL_TYPE,BOARD_CODE,BOARD_NAME,QUOTA,QUOTA_BALANCE,BUY_AMT,SELL_AMT,NET_BUY_AMT',
                },
            });

            const items = response.data?.result?.data || [];
            if (items.length === 0) return [];

            const dateMap = new Map<string, { sh: number; sz: number; total: number }>();

            for (const item of items) {
                const date = String(item.TRADE_DATE || '').split(' ')[0];
                const boardName = String(item.BOARD_NAME || '');
                const netBuy = Number(item.NET_BUY_AMT || 0);

                if (!dateMap.has(date)) {
                    dateMap.set(date, { sh: 0, sz: 0, total: 0 });
                }

                const entry = dateMap.get(date)!;
                if (boardName.includes('沪股通')) {
                    entry.sh = netBuy;
                } else if (boardName.includes('深股通')) {
                    entry.sz = netBuy;
                }
                entry.total = entry.sh + entry.sz;
            }

            return this.buildNorthFundResults(dateMap);
        } catch (error) {
            console.warn('[FundFlowAPI] HSGT API failed:', error);
            return [];
        }
    }

    async getNorthFundHolding(code: string): Promise<{ shares: number; ratio: number; change: number }> {
        const cacheKey = CacheAdapter.generateKey('northholding', SOURCE, code);
        const cached = cache.get<{ shares: number; ratio: number; change: number }>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const url = `https://datacenter-web.eastmoney.com/api/data/v1/get`;

            const response = await this.client.get(url, {
                params: {
                    sortColumns: 'TRADE_DATE',
                    sortTypes: -1,
                    pageSize: 2,
                    pageNumber: 1,
                    reportName: 'RPT_MUTUAL_HOLDSTOCKNORTH_STA',
                    columns: 'TRADE_DATE,SECURITY_CODE,SECURITY_NAME,HOLD_SHARES,HOLD_MARKET_CAP,HOLD_SHARES_RATIO',
                    filter: `(SECURITY_CODE="${code}")`,
                },
            });

            const items = response.data?.result?.data || [];
            if (items.length === 0) {
                return { shares: 0, ratio: 0, change: 0 };
            }

            const latest = items[0];
            const previous = items[1];

            return {
                shares: Number(latest.HOLD_SHARES || 0),
                ratio: Number(latest.HOLD_SHARES_RATIO || 0),
                change: previous ? Number(latest.HOLD_SHARES || 0) - Number(previous.HOLD_SHARES || 0) : 0,
            };
        });

        cache.set(cacheKey, result, CACHE_TTL.DEFAULT);
        return result;
    }

    async getNorthFundTop(topN: number): Promise<Array<{ code: string; name: string; shares: number; ratio: number; marketCap: number }>> {
        const cacheKey = CacheAdapter.generateKey('northtop', SOURCE, topN.toString());
        const cached = cache.get<Array<{ code: string; name: string; shares: number; ratio: number; marketCap: number }>>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const url = `https://datacenter-web.eastmoney.com/api/data/v1/get`;

            const response = await this.client.get(url, {
                params: {
                    sortColumns: 'HOLD_MARKET_CAP',
                    sortTypes: -1,
                    pageSize: topN,
                    pageNumber: 1,
                    reportName: 'RPT_MUTUAL_HOLDSTOCKNORTH_STA',
                    columns: 'SECURITY_CODE,SECURITY_NAME,HOLD_SHARES,HOLD_MARKET_CAP,HOLD_SHARES_RATIO',
                },
            });

            const items = response.data?.result?.data || [];
            return items.map((item: Record<string, unknown>) => ({
                code: String(item.SECURITY_CODE || ''),
                name: String(item.SECURITY_NAME || ''),
                shares: Number(item.HOLD_SHARES || 0),
                ratio: Number(item.HOLD_SHARES_RATIO || 0),
                marketCap: Number(item.HOLD_MARKET_CAP || 0),
            }));
        });

        cache.set(cacheKey, result, CACHE_TTL.DEFAULT);
        return result;
    }

    async getMarginData(code?: string): Promise<MarginData[]> {
        const cacheKey = CacheAdapter.generateKey('margin', SOURCE, code || 'market');
        const cached = cache.get<MarginData[]>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const url = `https://datacenter-web.eastmoney.com/api/data/v1/get`;

            const params: Record<string, unknown> = {
                sortColumns: 'DATE',
                sortTypes: -1,
                pageSize: 30,
                pageNumber: 1,
                reportName: 'RPTA_WEB_RZRQ_GGMX',
                columns: 'DATE,SCODE,SECNAME,RZYE,RZMRE,RZCHE,RQYE,RQMCL,RQCHL,RZRQYE',
            };

            if (code) {
                params.filter = `(SCODE="${code}")`;
            }

            const response = await this.client.get(url, { params });
            const items = response.data?.result?.data || [];
            return items.map((item: Record<string, unknown>) => ({
                date: String(item.DATE || '').split(' ')[0],
                code: String(item.SCODE || ''),
                name: String(item.SECNAME || ''),
                marginBalance: Number(item.RZYE || 0),
                marginBuy: Number(item.RZMRE || 0),
                marginRepay: Number(item.RZCHE || 0),
                shortBalance: Number(item.RQYE || 0),
                shortSell: Number(item.RQMCL || 0),
                shortRepay: Number(item.RQCHL || 0),
                totalBalance: Number(item.RZRQYE || 0),
            }));
        });

        cache.set(cacheKey, result, CACHE_TTL.DEFAULT);
        return result;
    }

    async getMarginRanking(
        topN: number,
        sortBy: 'balance' | 'buy' | 'sell'
    ): Promise<Array<{
        date: string;
        code: string;
        name: string;
        marginBalance: number;
        marginBuy: number;
        shortSell: number;
        totalBalance: number;
    }>> {
        const cacheKey = CacheAdapter.generateKey('marginranking', SOURCE, sortBy, topN.toString());
        const cached = cache.get<Array<{
            date: string;
            code: string;
            name: string;
            marginBalance: number;
            marginBuy: number;
            shortSell: number;
            totalBalance: number;
        }>>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const url = `https://datacenter-web.eastmoney.com/api/data/v1/get`;

            const latestResp = await this.client.get(url, {
                params: {
                    sortColumns: 'DATE',
                    sortTypes: -1,
                    pageSize: 1,
                    pageNumber: 1,
                    reportName: 'RPTA_WEB_RZRQ_GGMX',
                    columns: 'DATE',
                },
            });

            const latestItem = latestResp.data?.result?.data?.[0];
            const latestDate = latestItem?.DATE;
            if (!latestDate) return [];

            const sortColumnMap: Record<'balance' | 'buy' | 'sell', string> = {
                balance: 'RZRQYE',
                buy: 'RZMRE',
                sell: 'RQMCL',
            };

            const response = await this.client.get(url, {
                params: {
                    sortColumns: sortColumnMap[sortBy],
                    sortTypes: -1,
                    pageSize: topN,
                    pageNumber: 1,
                    reportName: 'RPTA_WEB_RZRQ_GGMX',
                    columns: 'DATE,SCODE,SECNAME,RZYE,RZMRE,RQMCL,RZRQYE',
                    filter: `(DATE='${latestDate}')`,
                },
            });

            const items = response.data?.result?.data || [];
            return items.map((item: Record<string, unknown>) => ({
                date: String(item.DATE || '').split(' ')[0],
                code: String(item.SCODE || ''),
                name: String(item.SECNAME || ''),
                marginBalance: Number(item.RZYE || 0),
                marginBuy: Number(item.RZMRE || 0),
                shortSell: Number(item.RQMCL || 0),
                totalBalance: Number(item.RZRQYE || 0),
            }));
        });

        cache.set(cacheKey, result, CACHE_TTL.DEFAULT);
        return result;
    }

    /**
     * 获取个股资金流向
     */
    async getStockFundFlow(code: string): Promise<{
        code: string;
        name: string;
        mainNetInflow: number;
        mainInflowPercent: number;
        superLargeNetInflow: number;
        largeNetInflow: number;
        middleNetInflow: number;
        smallNetInflow: number;
    } | null> {
        const normalizedCode = code.replace(/^(sh|sz)/i, '');
        const cacheKey = CacheAdapter.generateKey('stockfundflow', SOURCE, normalizedCode);
        const cached = cache.get<{
            code: string;
            name: string;
            mainNetInflow: number;
            mainInflowPercent: number;
            superLargeNetInflow: number;
            largeNetInflow: number;
            middleNetInflow: number;
            smallNetInflow: number;
        }>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            // 确定市场前缀
            const market = normalizedCode.startsWith('6') ? '1' : '0';
            const secid = `${market}.${normalizedCode}`;

            const url = `https://push2.eastmoney.com/api/qt/stock/fflow/kline/get`;
            const response = await this.client.get(url, {
                params: {
                    secid,
                    klt: 101, // 日K
                    fields1: 'f1,f2,f3',
                    fields2: 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62',
                    lmt: 1, // 只取最新一天
                },
            });

            const data = response.data?.data;
            if (!data || !data.klines || data.klines.length === 0) {
                // 尝试使用另一个接口获取实时资金流向
                return await this.fetchStockFundFlowRealtime(normalizedCode, market);
            }

            const latest = data.klines[data.klines.length - 1];
            const parts = latest.split(',');
            // 格式: 日期,主力净流入,小单净流入,中单净流入,大单净流入,超大单净流入
            const mainInflow = parseFloat(parts[1]) || 0;
            const smallInflow = parseFloat(parts[2]) || 0;
            const mediumInflow = parseFloat(parts[3]) || 0;
            const largeInflow = parseFloat(parts[4]) || 0;
            const superlargeInflow = parseFloat(parts[5]) || 0;

            return {
                code: normalizedCode,
                name: data.name || '',
                mainNetInflow: mainInflow,
                mainInflowPercent: 0, // 需从其他接口获取
                superLargeNetInflow: superlargeInflow,
                largeNetInflow: largeInflow,
                middleNetInflow: mediumInflow,
                smallNetInflow: smallInflow,
            };
        });

        if (result) {
            cache.set(cacheKey, result, CACHE_TTL.REALTIME_QUOTE); // 短期缓存
        }
        return result;
    }

    private async fetchStockFundFlowRealtime(code: string, market: string): Promise<{
        code: string;
        name: string;
        mainNetInflow: number;
        mainInflowPercent: number;
        superLargeNetInflow: number;
        largeNetInflow: number;
        middleNetInflow: number;
        smallNetInflow: number;
    } | null> {
        try {
            const secid = `${market}.${code}`;
            const url = `https://push2.eastmoney.com/api/qt/ulist.np/get`;
            const response = await this.client.get(url, {
                params: {
                    fltt: 2,
                    secids: secid,
                    fields: 'f12,f14,f62,f66,f69,f72,f75,f78,f81,f84',
                },
            });

            const data = response.data?.data?.diff;
            if (!data || data.length === 0) return null;

            const item = data[0];
            return {
                code,
                name: String(item.f14 || ''),
                mainNetInflow: Number(item.f62 || 0),
                mainInflowPercent: Number(item.f69 || 0) + Number(item.f75 || 0),
                superLargeNetInflow: Number(item.f66 || 0),
                largeNetInflow: Number(item.f72 || 0),
                middleNetInflow: Number(item.f78 || 0),
                smallNetInflow: Number(item.f84 || 0),
            };
        } catch (error) {
            console.warn('[FundFlowAPI] Realtime fund flow failed:', error);
            return null;
        }
    }

    async getBlockTrades(date?: string, code?: string): Promise<BlockTrade[]> {
        const targetDate = date || this.getTodayStr();
        const cacheKey = CacheAdapter.generateKey('blocktrade', SOURCE, targetDate, code || 'all');
        const cached = cache.get<BlockTrade[]>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const url = `https://datacenter-web.eastmoney.com/api/data/v1/get`;

            const params: Record<string, unknown> = {
                sortColumns: 'TRADE_DATE,SECURITY_CODE',
                sortTypes: '-1,1',
                pageSize: 100,
                pageNumber: 1,
                reportName: 'RPT_BLOCKTRADE_DETAILSNEW',
                columns: 'TRADE_DATE,SECURITY_CODE,SECUCODE,SECURITY_NAME_ABBR,DEAL_PRICE,DEAL_AMOUNT,DEAL_AMT,PREMIUM_RATIO,BUYER_NAME,SELLER_NAME',
                filter: `(TRADE_DATE='${targetDate}')`,
            };

            if (code) {
                params.filter = `(TRADE_DATE='${targetDate}')(SECURITY_CODE="${code}")`;
            }

            const response = await this.client.get(url, { params });
            const items = response.data?.result?.data || [];
            return items.map((item: Record<string, unknown>) => this.parseBlockTrade(item));
        });

        cache.set(cacheKey, result, CACHE_TTL.DEFAULT);
        return result;
    }

    private parseBlockTrade(item: Record<string, unknown>): BlockTrade {
        return {
            date: String(item.TRADE_DATE || '').split(' ')[0],
            code: String(item.SECURITY_CODE || ''),
            name: String(item.SECURITY_NAME_ABBR || ''),
            price: Number(item.DEAL_PRICE || 0),
            volume: Number(item.DEAL_AMOUNT || 0),
            amount: Number(item.DEAL_AMT || 0),
            premium: Number(item.PREMIUM_RATIO || 0),
            buyer: String(item.BUYER_NAME || ''),
            seller: String(item.SELLER_NAME || ''),
        };
    }
}

export const fundFlowAPI = new FundFlowAPI();
