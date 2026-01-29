/**
 * AKShare 适配器
 * 通过 akshare-mcp 获取行情/财务/北向资金数据
 */

import { cache, CacheAdapter } from './cache-adapter.js';
import { rateLimiter } from './rate-limiter.js';
import { CACHE_TTL } from '../config/constants.js';
import { callAkshareMcpTool } from './akshare-mcp-client.js';
import { toFriendlyError } from '../services/error-mapper.js';
import type {
    FinancialData,
    RealtimeQuote,
    KlineData,
    KlinePeriod,
    NorthFund,
    DragonTiger,
    MarginData,
    BlockTrade,
    StockInfo,
    SectorData,
    FundFlow,
    OrderBook,
    TradeDetail,
    LimitUpStock,
    LimitUpStatistics,
} from '../types/stock.js';
import type { QuoteAdapter, FundamentalAdapter, MarketAdapter } from '../types/adapters.js';

const SOURCE = 'akshare';

export class AKShareAdapter implements QuoteAdapter, FundamentalAdapter, MarketAdapter {
    readonly name: 'akshare' = 'akshare';
    private healthCheckedAt = 0;
    private healthOk = false;

    async isAvailable(): Promise<boolean> {
        const now = Date.now();
        if (now - this.healthCheckedAt < 10000) {
            return this.healthOk;
        }

        try {
            const res = await callAkshareMcpTool('get_index_quote', { index_code: '000001' });
            this.healthOk = res.success === true;
            this.healthCheckedAt = now;
            return this.healthOk;
        } catch {
            this.healthOk = false;
            this.healthCheckedAt = now;
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
            available: await this.isAvailable(),
            url: 'akshare-mcp',
            consecutiveFailures: 0,
            lastCheck: this.healthCheckedAt ? new Date(this.healthCheckedAt) : null,
        };
    }

    private parseNumber(value: unknown, fallback: number = 0): number {
        const num = Number(value);
        return Number.isFinite(num) ? num : fallback;
    }

    private parseNullableNumber(value: unknown): number | null {
        if (value === null || value === undefined || value === '') return null;
        const num = Number(value);
        return Number.isFinite(num) ? num : null;
    }

    private async callTool<T>(name: string, args: Record<string, unknown>): Promise<T> {
        const res = await callAkshareMcpTool<T>(name, args);
        if (!res.success || res.data === undefined || res.data === null) {
            throw new Error(toFriendlyError('akshare', res.error || `akshare-mcp ${name} 返回空数据`));
        }
        return res.data;
    }

    async getRealtimeQuote(code: string): Promise<RealtimeQuote> {
        const cacheKey = CacheAdapter.generateKey('quote', SOURCE, code);
        const cached = cache.get<RealtimeQuote>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const quotes = await this.getBatchQuotes([code]);
            if (quotes.length === 0) {
                throw new Error(`akshare-mcp 无法获取 ${code} 的实时行情`);
            }
            return quotes[0];
        });

        cache.set(cacheKey, result, CACHE_TTL.REALTIME_QUOTE);
        return result;
    }

    async getBatchQuotes(codes: string[]): Promise<RealtimeQuote[]> {
        if (codes.length === 0) return [];

        const raw = await this.callTool<any>('get_batch_quotes', { stock_codes: codes });
        const items = Array.isArray(raw) ? raw : (raw as any).quotes || (raw as any).items || [];

        return items.map((item: any) => ({
            code: String(item.code || ''),
            name: String(item.name || ''),
            price: this.parseNumber(item.price),
            change: this.parseNumber(item.change),
            changePercent: this.parseNumber(item.changePercent ?? item.change_pct ?? item.pct),
            open: this.parseNumber(item.open ?? item.openPrice ?? item.open_price ?? item.price),
            high: this.parseNumber(item.high ?? item.highPrice ?? item.high_price ?? item.price),
            low: this.parseNumber(item.low ?? item.lowPrice ?? item.low_price ?? item.price),
            preClose: this.parseNumber(item.preClose ?? item.prevClose ?? item.prev_close ?? item.pre_close),
            volume: this.parseNumber(item.volume),
            amount: this.parseNumber(item.amount),
            turnoverRate: this.parseNumber(item.turnoverRate ?? item.turnover_rate ?? 0),
            timestamp: Date.now(),
            pe: this.parseNullableNumber(item.pe ?? item.pe_ttm),
            pb: this.parseNullableNumber(item.pb),
            marketCap: this.parseNullableNumber(item.marketCap ?? item.market_cap),
            floatMarketCap: this.parseNullableNumber(item.floatMarketCap ?? item.float_market_cap),
        }));
    }

    async getKline(code: string, period: KlinePeriod, limit: number): Promise<KlineData[]> {
        const cacheKey = CacheAdapter.generateKey('kline', SOURCE, code, period, limit.toString());
        const cached = cache.get<KlineData[]>(cacheKey);
        if (cached) return cached;

        const result = await rateLimiter.schedule(SOURCE, async () => {
            const periodMap: Record<KlinePeriod, string> = {
                '1m': '1m',
                '5m': '5m',
                '15m': '15m',
                '30m': '30m',
                '60m': '60m',
                'daily': 'daily',
                'weekly': 'weekly',
                'monthly': 'monthly',
                '101': 'daily',
                '102': 'weekly',
                '103': 'monthly',
            };

            const normalizedPeriod = periodMap[period] || 'daily';
            const toolName = normalizedPeriod.endsWith('m') ? 'get_minute_kline' : 'get_kline';
            const raw = await this.callTool<any>(toolName, {
                stock_code: code,
                period: normalizedPeriod,
                limit,
            });

            const items = Array.isArray(raw) ? raw : (raw as any).items || [];
            return items.map((row: any) => ({
                date: String(row.date || row.time || ''),
                open: this.parseNumber(row.open),
                close: this.parseNumber(row.close),
                high: this.parseNumber(row.high),
                low: this.parseNumber(row.low),
                volume: this.parseNumber(row.volume),
                amount: this.parseNullableNumber(row.amount ?? row.turnover ?? 0) ?? 0,
            }));
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
            const data = await this.callTool<any>('get_financials', { stock_code: code });

            return {
                code: String(data.code || code),
                reportDate: String(data.reportDate || data.report_date || ''),
                revenue: this.parseNullableNumber(data.revenue),
                netProfit: this.parseNullableNumber(data.netProfit),
                grossProfitMargin: this.parseNullableNumber(data.grossProfitMargin),
                netProfitMargin: this.parseNullableNumber(data.netProfitMargin),
                roe: this.parseNullableNumber(data.roe),
                roa: this.parseNullableNumber(data.roa),
                debtRatio: this.parseNullableNumber(data.debtRatio),
                currentRatio: this.parseNullableNumber(data.currentRatio),
                eps: this.parseNullableNumber(data.eps),
                bvps: this.parseNullableNumber(data.bvps),
                revenueGrowth: this.parseNullableNumber(data.revenueGrowth),
                netProfitGrowth: this.parseNullableNumber(data.netProfitGrowth ?? data.profitGrowth),
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
            const data = await this.callTool<any>('get_north_fund', { days });
            const items = Array.isArray(data) ? data : data.items || [];

            return items.map((item: any) => ({
                date: String(item.date || ''),
                shConnect: this.parseNumber(item.shConnect),
                szConnect: this.parseNumber(item.szConnect),
                total: this.parseNumber(item.total),
                cumulative: this.parseNullableNumber(item.cumulative) ?? 0,
            }));
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
            const data = await this.callTool<any>('get_stock_list', {});
            const items = Array.isArray(data) ? data : data.items || [];
            return items.map((item: { code?: string; name?: string }) => ({
                code: String(item.code || ''),
                name: String(item.name || ''),
            }));
        });

        cache.set(cacheKey, result, CACHE_TTL.FINANCIAL);
        return result;
    }

    async getStockInfo(code: string): Promise<StockInfo> {
        const data = await this.callTool<any>('get_stock_info', { stock_code: code });
        const marketRaw = String(data.market || '').toUpperCase();
        const market = marketRaw === 'SZ' || marketRaw === 'SZSE'
            ? 'SZSE'
            : 'SSE';
        return {
            code: String(data.code || code),
            name: String(data.name || ''),
            market,
            industry: String(data.industry || ''),
            sector: String(data.sector || data.industry || ''),
            listDate: String(data.listDate || ''),
            totalShares: this.parseNumber(data.totalShares ?? data.total_shares ?? 0),
            floatShares: this.parseNumber(data.floatShares ?? data.float_shares ?? 0),
            marketCap: this.parseNumber(data.totalMarketCap ?? data.total_market_cap ?? 0),
            floatMarketCap: this.parseNumber(data.floatMarketCap ?? data.float_market_cap ?? 0),
        };
    }

    async getDragonTiger(date?: string): Promise<DragonTiger[]> {
        const data = await this.callTool<any>('get_dragon_tiger', { date: date || '' });
        const items = Array.isArray(data) ? data : data.items || [];
        const fallbackDate = date || new Date().toISOString().slice(0, 10);
        return items.map((item: any) => ({
            code: String(item.code || ''),
            name: String(item.name || ''),
            date: String(item.date || fallbackDate),
            reason: String(item.reason || ''),
            buyAmount: this.parseNumber(item.buyAmount ?? item.buy_amount ?? 0),
            sellAmount: this.parseNumber(item.sellAmount ?? item.sell_amount ?? 0),
            netAmount: this.parseNumber(item.netAmount ?? item.net_amount ?? 0),
            buyers: [],
            sellers: [],
        }));
    }

    async getMarginData(code?: string): Promise<MarginData[]> {
        const raw = await this.callTool<any>('get_margin_data', {
            stock_code: code || '',
            days: 90,
        });
        const items = Array.isArray(raw) ? raw : raw.items || [];
        return items.map((item: any) => ({
            date: String(item.date || ''),
            code: String(item.code || code || ''),
            name: String(item.name || ''),
            marginBalance: this.parseNumber(item.marginBalance ?? item.margin_balance ?? 0),
            marginBuy: this.parseNumber(item.marginBuy ?? item.margin_buy ?? 0),
            marginRepay: this.parseNumber(item.marginRepay ?? item.margin_repay ?? 0),
            shortBalance: this.parseNumber(item.shortBalance ?? item.short_balance ?? 0),
            shortSell: this.parseNumber(item.shortSell ?? item.short_sell ?? 0),
            shortRepay: this.parseNumber(item.shortRepay ?? item.short_repay ?? 0),
            totalBalance: this.parseNumber(item.totalBalance ?? item.total_balance ?? 0),
        }));
    }

    async getMarginRanking(topN: number, sortBy: 'balance' | 'buy' | 'sell') {
        const raw = await this.callTool<any>('get_margin_ranking', {
            top_n: topN,
            sort_by: sortBy,
        });
        const items = Array.isArray(raw) ? raw : raw.items || [];
        return items.map((item: any) => ({
            date: String(item.date || ''),
            code: String(item.code || ''),
            name: String(item.name || ''),
            marginBalance: this.parseNumber(item.marginBalance ?? 0),
            marginBuy: this.parseNumber(item.marginBuy ?? 0),
            shortSell: this.parseNumber(item.shortSell ?? 0),
            totalBalance: this.parseNumber(item.totalBalance ?? 0),
        }));
    }

    async getBlockTrades(date?: string, code?: string): Promise<BlockTrade[]> {
        const raw = await this.callTool<any>('get_block_trades', {
            date: date || '',
            stock_code: code || '',
        });
        const items = Array.isArray(raw) ? raw : raw.items || [];
        return items.map((item: any) => ({
            date: String(item.date || ''),
            code: String(item.code || ''),
            name: String(item.name || ''),
            price: this.parseNumber(item.price ?? 0),
            volume: this.parseNumber(item.volume ?? 0),
            amount: this.parseNumber(item.amount ?? 0),
            premium: this.parseNumber(item.premium ?? item.premium_rate ?? 0),
            buyer: String(item.buyer || ''),
            seller: String(item.seller || ''),
        }));
    }

    async getStockNews(code: string, limit: number = 10) {
        const raw = await this.callTool<any>('get_stock_news', { stock_code: code, limit });
        const items = Array.isArray(raw) ? raw : raw.items || [];
        return items.map((item: any) => ({
            title: String(item.title || ''),
            time: String(item.time || ''),
            source: String(item.source || ''),
            url: String(item.url || ''),
        }));
    }

    async getMarketNews(limit: number = 20) {
        const raw = await this.callTool<any>('get_market_news', { limit });
        const items = Array.isArray(raw) ? raw : raw.items || [];
        return items.map((item: any) => ({
            title: String(item.title || ''),
            time: String(item.time || ''),
            content: String(item.content || ''),
        }));
    }

    async getSectorFlow(topN: number): Promise<SectorData[]> {
        const raw = await this.callTool<any>('get_sector_fund_flow', { top_n: topN });
        const items = Array.isArray(raw) ? raw : raw.items || [];
        return items.map((item: any, idx: number) => ({
            code: String(item.code || item.name || idx),
            name: String(item.name || ''),
            change: this.parseNumber(item.changePercent ?? item.change ?? 0),
            changePercent: this.parseNumber(item.changePercent ?? 0),
            leadingStock: '',
            amount: this.parseNumber(item.mainNetInflow ?? item.netInflow ?? 0),
            netInflow: this.parseNumber(item.mainNetInflow ?? item.netInflow ?? 0),
        }));
    }

    async getFundFlow(code: string): Promise<FundFlow> {
        const data = await this.callTool<any>('get_stock_fund_flow', { stock_code: code });
        return {
            code: String(data.code || code),
            mainNetInflow: this.parseNumber(data.mainNetInflow ?? 0),
            mainInflowPercent: this.parseNumber(data.mainInflowPercent ?? 0),
            superLargeNetInflow: this.parseNumber(data.superLargeNetInflow ?? 0),
            largeNetInflow: this.parseNumber(data.largeNetInflow ?? 0),
            middleNetInflow: this.parseNumber(data.middleNetInflow ?? 0),
            smallNetInflow: this.parseNumber(data.smallNetInflow ?? 0),
        };
    }

    async getOrderBook(code: string): Promise<OrderBook> {
        const data = await this.callTool<any>('get_order_book', { stock_code: code });
        return {
            code: String(data.code || code),
            bids: Array.isArray(data.bids) ? data.bids : [],
            asks: Array.isArray(data.asks) ? data.asks : [],
            timestamp: Number(data.timestamp || Date.now()),
        };
    }

    async getTradeDetails(code: string, limit: number = 20): Promise<TradeDetail[]> {
        const raw = await this.callTool<any>('get_trade_details', { stock_code: code, limit });
        const items = Array.isArray(raw) ? raw : raw.items || [];
        return items.map((item: any) => ({
            time: String(item.time || ''),
            price: this.parseNumber(item.price ?? 0),
            volume: this.parseNumber(item.volume ?? 0),
            amount: this.parseNumber(item.amount ?? 0),
            direction: (item.direction || 'neutral') as TradeDetail['direction'],
        }));
    }

    async getLimitUpStocks(date?: string): Promise<LimitUpStock[]> {
        const raw = await this.callTool<any>('get_limit_up_stocks', { date: date || '' });
        const items = Array.isArray(raw) ? raw : raw.items || [];
        return items.map((item: any) => ({
            code: String(item.code || ''),
            name: String(item.name || ''),
            price: this.parseNumber(item.price ?? 0),
            changePercent: this.parseNumber(item.changePercent ?? 0),
            limitUpPrice: this.parseNumber(item.limitUpPrice ?? 0),
            firstLimitTime: String(item.firstLimitTime || ''),
            lastLimitTime: String(item.lastLimitTime || ''),
            openTimes: this.parseNumber(item.openTimes ?? 0),
            continuousDays: this.parseNumber(item.continuousDays ?? 0),
            turnoverRate: this.parseNumber(item.turnoverRate ?? 0),
            marketCap: this.parseNumber(item.marketCap ?? 0),
            industry: String(item.industry || ''),
            concept: String(item.concept || ''),
        }));
    }

    async getLimitUpStatistics(date?: string): Promise<LimitUpStatistics> {
        const data = await this.callTool<any>('get_limit_up_statistics', { date: date || '' });
        return {
            date: String(data.date || new Date().toISOString().slice(0, 10)),
            totalLimitUp: this.parseNumber(data.totalLimitUp ?? 0),
            firstBoard: this.parseNumber(data.firstBoard ?? 0),
            secondBoard: this.parseNumber(data.secondBoard ?? 0),
            thirdBoard: this.parseNumber(data.thirdBoard ?? 0),
            higherBoard: this.parseNumber(data.higherBoard ?? 0),
            failedBoard: this.parseNumber(data.failedBoard ?? 0),
            limitDown: this.parseNumber(data.limitDown ?? 0),
            successRate: this.parseNumber(data.successRate ?? 0),
        };
    }

    async getNorthFundHolding(code: string) {
        return this.callTool<any>('get_north_fund_holding', { stock_code: code });
    }

    async getNorthFundTop(topN: number) {
        const raw = await this.callTool<any>('get_north_fund_top', { top_n: topN });
        return Array.isArray(raw) ? raw : raw.items || [];
    }
}

export const akShareAdapter = new AKShareAdapter();
