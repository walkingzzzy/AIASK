/**
 * 适配器管理器
 * 统一管理多个数据源适配器，实现故障转移
 * 
 * 修复 2026-01-13:
 * - 集成 DataValidator 进行数据校验
 * - 校验失败时自动换源/降级
 * - 返回结果附加质量信息
 */

import { eastMoneyAdapter, EastMoneyAdapter } from './eastmoney-adapter.js';
import { sinaAdapter, SinaAdapter } from './sina-adapter.js';
import { akShareAdapter, AKShareAdapter } from './akshare-adapter.js';
import { tushareAdapter, TushareAdapter } from './tushare-adapter.js';
import { baostockAdapter, BaostockAdapter } from './baostock-adapter.js';
import { windAdapter, WindAdapter } from './wind-adapter.js';
import { callAkshareMcpTool } from './akshare-mcp-client.js';
import { cache, CacheAdapter } from './cache-adapter.js';
import { rateLimiter } from './rate-limiter.js';
import { sinaAPI } from './sina/sina-api.js';
import { tencentAPI } from './tencent/tencent-api.js';
import { dataValidator } from '../services/data-validator.js';
import { toFriendlyError } from '../services/error-mapper.js';
import { CACHE_TTL, DATA_SOURCE_PRIORITY } from '../config/constants.js';
import type {
    RealtimeQuote, KlineData, DragonTiger, NorthFund, SectorData, KlinePeriod, FinancialData,
    OrderBook, TradeDetail, LimitUpStock, LimitUpStatistics, MarginData, BlockTrade,
    StockInfo, ValuationData, FundFlow
} from '../types/stock.js';
import type { DataSource, ApiResponse, QuoteAdapter, FundamentalAdapter, MarketAdapter } from '../types/adapters.js';

type AnyAdapter = EastMoneyAdapter | SinaAdapter | AKShareAdapter | TushareAdapter | BaostockAdapter | WindAdapter;
type CachedPayload<T> = { data: T; source: DataSource; asOf: string };

const AKSHARE_MCP_HEALTH_TTL_MS = 30_000;
let akshareMcpHealthCache: { value: boolean; checkedAt: number } | null = null;

async function checkAkshareMcpHealth(): Promise<boolean> {
    const now = Date.now();
    if (akshareMcpHealthCache && now - akshareMcpHealthCache.checkedAt < AKSHARE_MCP_HEALTH_TTL_MS) {
        return akshareMcpHealthCache.value;
    }

    try {
        const result = await callAkshareMcpTool('get_index_quote', { index_code: '000001' });
        const ok = result.success === true;
        akshareMcpHealthCache = { value: ok, checkedAt: now };
        return ok;
    } catch {
        akshareMcpHealthCache = { value: false, checkedAt: now };
        return false;
    }
}

/**
 * 适配器管理器
 */
export class AdapterManager {
    private adapters: Map<DataSource, AnyAdapter>;

    constructor() {
        this.adapters = new Map();
        // 注册适配器
        this.adapters.set('eastmoney', eastMoneyAdapter);
        this.adapters.set('sina', sinaAdapter);
        this.adapters.set('akshare', akShareAdapter);
        this.adapters.set('tushare', tushareAdapter);
        this.adapters.set('baostock', baostockAdapter);
        this.adapters.set('wind', windAdapter);
    }

    /**
     * 获取适配器
     */
    getAdapter(source: DataSource): AnyAdapter | undefined {
        return this.adapters.get(source);
    }

    /**
     * 按优先级尝试获取实时行情（带数据校验）
     */
    async getRealtimeQuote(code: string): Promise<ApiResponse<RealtimeQuote>> {
        const sources = DATA_SOURCE_PRIORITY.REALTIME;
        let lastError: string | undefined;
        let degraded = false;
        let degradeReason: string | undefined;

        for (const source of sources) {
            const adapter = this.adapters.get(source as DataSource) as QuoteAdapter | undefined;
            if (!adapter) continue;

            try {
                const isAvailable = await adapter.isAvailable();
                if (!isAvailable) continue;

                const data = await adapter.getRealtimeQuote(code);

                // 数据校验
                const validation = dataValidator.validateQuote(data);

                if (!validation.valid) {
                    // 校验失败，尝试下一个数据源
                    console.warn(`[${source}] Quote validation failed for ${code}:`, validation.errors);
                    degraded = true;
                    degradeReason = `${source}: ${validation.errors.join('; ')}`;
                    continue;
                }

                return {
                    success: true,
                    data,
                    source: source as DataSource,
                    quality: {
                        valid: true,
                        warnings: validation.warnings.length > 0 ? validation.warnings : undefined,
                        asOf: new Date().toISOString(),
                        degraded,
                        degradeReason: degraded ? degradeReason : undefined,
                    },
                };
            } catch (error) {
                console.warn(`[${source}] Failed to get quote for ${code}:`, error);
                lastError = String(error);
                continue;
            }
        }

        // Tier 3: Direct HTTP Fallback (Sina/Tencent)
        try {
            console.warn(`[AdapterManager] All primary sources failed for ${code}, trying Sina fallback...`);
            const sinaRes = await sinaAPI.getQuote(code);
            if (sinaRes) {
                // Adapt to RealtimeQuote
                // Sina API returns simplified data
                return {
                    success: true,
                    data: {
                        code: sinaRes.code,
                        name: sinaRes.name,
                        price: sinaRes.price,
                        change: sinaRes.price - (sinaRes.open > 0 ? sinaRes.open : sinaRes.price), // Approx
                        changePercent: 0, // Calc if needed
                        open: sinaRes.open,
                        high: sinaRes.high,
                        low: sinaRes.low,
                        preClose: 0, // Sina API may lack this in simple parsing
                        volume: sinaRes.volume,
                        amount: sinaRes.amount,
                        turnoverRate: 0,
                        timestamp: Date.now(),
                        // time: sinaRes.time || new Date().toISOString() // RealtimeQuote usually uses timestamp number
                    } as RealtimeQuote,
                    source: 'sina'
                };
            }
        } catch (e) {
            console.warn('Sina fallback failed:', e);
        }

        try {
            console.warn(`[AdapterManager] Trying Tencent fallback...`);
            const tencentRes = await tencentAPI.getQuote(code);
            if (tencentRes) {
                return {
                    success: true,
                    data: {
                        code: tencentRes.code,
                        name: tencentRes.name,
                        price: tencentRes.price,
                        change: tencentRes.change,
                        changePercent: tencentRes.changePercent,
                        open: tencentRes.open,
                        high: tencentRes.high,
                        low: tencentRes.low,
                        preClose: tencentRes.prevClose,
                        volume: tencentRes.volume,
                        amount: tencentRes.amount,
                        turnoverRate: 0,
                        timestamp: Date.now(), // Parse tencentRes.time '20230517150000' if needed
                    } as RealtimeQuote,
                    source: 'tencent'
                };
            }
        } catch (e) {
            console.warn('Tencent fallback failed:', e);
        }

        return { success: false, error: lastError || `无法从所有数据源获取 ${code} 的行情数据，请检查网络连接或稍后重试` };
    }

    /**
     * 按优先级尝试获取批量行情（带数据校验）
     */
    async getBatchQuotes(codes: string[]): Promise<ApiResponse<RealtimeQuote[]>> {
        const sources = DATA_SOURCE_PRIORITY.REALTIME;
        let lastError: string | undefined;
        const allWarnings: string[] = [];

        for (const source of sources) {
            const adapter = this.adapters.get(source as DataSource) as QuoteAdapter | undefined;
            if (!adapter) continue;

            try {
                const isAvailable = await adapter.isAvailable();
                if (!isAvailable) continue;

                const data = await adapter.getBatchQuotes(codes);

                // 批量校验
                let hasErrors = false;
                let invalidCount = 0;
                for (const quote of data) {
                    const validation = dataValidator.validateQuote(quote);
                    if (!validation.valid) {
                        hasErrors = true;
                        invalidCount++;
                        if (process.env.LOG_LEVEL === 'debug') {
                            console.warn(`[${source}] Quote validation failed for ${quote.code}:`, validation.errors);
                        }
                    }
                    if (validation.warnings.length > 0) {
                        allWarnings.push(...validation.warnings.map((w: any) => `${quote.code}: ${w}`));
                    }
                }
                // 批量输出无效数据统计
                if (invalidCount > 0 && invalidCount <= 10) {
                    const invalidCodes = data.filter((q: any) => !dataValidator.validateQuote(q).valid).map((q: any) => q.code);
                    console.warn(`[${source}] ${invalidCount} 只股票数据验证失败（可能是停牌/退市）:`, invalidCodes.join(', '));
                } else if (invalidCount > 10) {
                    console.warn(`[${source}] ${invalidCount}/${data.length} 只股票数据验证失败`);
                }

                // 即使有部分错误，只要有有效数据就返回
                const validData = data.filter((q: any) => dataValidator.validateQuote(q).valid);

                if (validData.length === 0 && hasErrors) {
                    continue;
                }

                return {
                    success: true,
                    data: validData.length > 0 ? validData : data,
                    source: source as DataSource,
                    quality: {
                        valid: !hasErrors,
                        warnings: allWarnings.length > 0 ? allWarnings.slice(0, 10) : undefined,
                        asOf: new Date().toISOString(),
                        degraded: validData.length < data.length,
                        degradeReason: validData.length < data.length
                            ? `${data.length - validData.length}/${data.length} 条数据校验失败`
                            : undefined,
                    },
                };
            } catch (error) {
                console.warn(`[${source}] Failed to get batch quotes:`, error);
                lastError = String(error);
                continue;
            }
        }

        return { success: false, error: lastError || '无法从所有数据源批量获取行情数据，请检查网络连接或稍后重试' };
    }

    /**
     * 按优先级尝试获取K线数据（带数据校验）
     */
    async getKline(code: string, period: KlinePeriod, limit: number): Promise<ApiResponse<KlineData[]>> {
        const sources = DATA_SOURCE_PRIORITY.KLINE;
        let lastError: string | undefined;
        let degraded = false;
        let degradeReason: string | undefined;

        for (const source of sources) {
            const adapter = this.adapters.get(source as DataSource) as QuoteAdapter | undefined;
            if (!adapter) continue;

            try {
                const isAvailable = await adapter.isAvailable();
                if (!isAvailable) continue;

                const data = await adapter.getKline(code, period, limit);

                // K线数据校验
                const validation = dataValidator.validateKline(data);

                if (!validation.valid) {
                    console.warn(`[${source}] Kline validation failed for ${code}:`, validation.errors);
                    degraded = true;
                    degradeReason = `${source}: ${validation.errors.join('; ')}`;
                    continue;
                }

                return {
                    success: true,
                    data,
                    source: source as DataSource,
                    quality: {
                        valid: true,
                        warnings: validation.warnings.length > 0 ? validation.warnings : undefined,
                        asOf: new Date().toISOString(),
                        degraded,
                        degradeReason: degraded ? degradeReason : undefined,
                    },
                };
            } catch (error) {
                console.warn(`[${source}] Failed to get kline for ${code}:`, error);
                lastError = toFriendlyError(source as DataSource, error, `K线数据暂不可用，请稍后重试`);
                continue;
            }
        }

        return { success: false, error: lastError || `无法从所有数据源获取 ${code} 的K线数据，请检查网络连接或稍后重试` };
    }

    /**
     * 获取历史K线（别名 getKline）
     */
    async getKlineHistory(code: string, period: KlinePeriod, limit: number): Promise<ApiResponse<KlineData[]>> {
        return this.getKline(code, period, limit);
    }

    /**
     * 搜索股票
     */
    async searchStocks(keyword: string): Promise<ApiResponse<StockInfo[]>> {
        const adapter = this.adapters.get('eastmoney') as EastMoneyAdapter | undefined;
        if (!adapter || !('searchStocks' in adapter)) {
            // Fallback to minimal search if adapter doesn't support it directly
            // For now return empty or error
            return { success: false, error: '搜索功能暂不可用' };
        }
        try {
            const data = await adapter.searchStocks(keyword);
            return { success: true, data, source: 'eastmoney' };
        } catch (error) {
            return { success: false, error: toFriendlyError('eastmoney', error, '搜索功能暂不可用，请稍后重试') };
        }
    }

    /**
     * 获取财务数据 (优先使用 EastMoney/Tushare)
     */
    async getFinancials(code: string): Promise<ApiResponse<FinancialData>> {
        const sources = DATA_SOURCE_PRIORITY.FINANCIAL;

        for (const source of sources) {
            const adapter = this.adapters.get(source as DataSource) as FundamentalAdapter | undefined;
            if (!adapter || !('getFinancials' in adapter)) continue;

            try {
                const isAvailable = await adapter.isAvailable();
                if (!isAvailable) continue;

                const data = await adapter.getFinancials(code);
                return { success: true, data, source: source as DataSource };
            } catch (error) {
                console.warn(`[${source}] Failed to get financials for ${code}:`, error);
                continue;
            }
        }

        return { success: false, error: `无法从所有数据源获取 ${code} 的财务数据，请检查网络连接或稍后重试` };
    }

    /**
     * 获取财务历史（别名 getFinancials）
     */
    async getFinancialHistory(code: string): Promise<ApiResponse<FinancialData>> {
        return this.getFinancials(code);
    }

    /**
     * 获取估值指标（从实时行情和财务数据计算或获取）
     */
    async getValuationMetrics(code: string): Promise<ApiResponse<ValuationData>> {
        // 简单实现：尝试从 Tushare 获取，或者组合 RealtimeQuote + Financials
        // 这里暂时返回未实现，或者如果有 adapter 支持则调用
        const adapter = this.adapters.get('tushare') as TushareAdapter | undefined;
        if (adapter && await adapter.isAvailable()) {
            try {
                const data = await adapter.getValuationMetrics(code);
                return { success: true, data, source: 'tushare' };
            } catch (e) {
                console.warn('Tushare valuation failed:', e);
            }
        }
        return { success: false, error: '估值指标暂不可用' };
    }

    /**
     * 获取个股资金流向
     */
    async getFundFlow(code: string): Promise<ApiResponse<FundFlow>> {
        const adapter = this.adapters.get('eastmoney') as EastMoneyAdapter | undefined;
        if (adapter && 'getFundFlow' in adapter) {
            try {
                const data = await adapter.getFundFlow(code);
                if (!data) {
                    return { success: false, error: '未找到该股票的资金流向数据' };
                }
                // 使用 as FundFlow 断言，因为 data 非空且结构匹配（虽然多了些字段）
                // 实际上 stockFundFlow 包含 FundFlow 所需字段吗？
                // FundFlow 类型定义在 types/stock.ts
                return { success: true, data: data as FundFlow, source: 'eastmoney' };
            } catch (e) {
                return { success: false, error: toFriendlyError('eastmoney', e, '资金流向暂不可用，请稍后重试') };
            }
        }
        return { success: false, error: '资金流向暂不可用' };
    }

    /**
     * 获取龙虎榜数据
     */
    async getDragonTiger(date?: string): Promise<ApiResponse<DragonTiger[]>> {
        const sources = DATA_SOURCE_PRIORITY.DRAGON_TIGER;

        for (const source of sources) {
            const adapter = this.adapters.get(source as DataSource) as EastMoneyAdapter | undefined;
            if (!adapter || !('getDragonTiger' in adapter)) continue;

            try {
                const data = await adapter.getDragonTiger(date);
                return { success: true, data, source: source as DataSource };
            } catch (error) {
                console.warn(`[${source}] Failed to get dragon tiger:`, error);
                continue;
            }
        }

        return { success: false, error: '无法获取龙虎榜数据，请检查网络连接或稍后重试' };
    }

    /**
     * 获取北向资金数据（带数据校验）
     */
    async getNorthFund(days: number): Promise<ApiResponse<NorthFund[]>> {
        const sources = DATA_SOURCE_PRIORITY.NORTH_FUND;
        const warnings: string[] = [];
        const cacheKey = CacheAdapter.generateKey('northfund', 'aggregate', days.toString());
        const staleKey = CacheAdapter.generateKey('northfund', 'aggregate', 'stale', days.toString());
        const cached = cache.get<CachedPayload<NorthFund[]>>(cacheKey);
        if (cached?.data?.length) {
            const validation = dataValidator.validateNorthFund(cached.data);
            if (validation.valid) {
                return {
                    success: true,
                    data: cached.data,
                    source: cached.source,
                    cached: true,
                    quality: {
                        valid: true,
                        warnings: validation.warnings.length > 0 ? validation.warnings : undefined,
                        asOf: cached.asOf,
                        degraded: false,
                    },
                };
            }
        }

        for (const source of sources) {
            const adapter = this.adapters.get(source as DataSource) as MarketAdapter | undefined;
            if (!adapter || !('getNorthFund' in adapter)) continue;

            try {
                const data = await adapter.getNorthFund(days);

                // 北向资金数据校验
                const validation = dataValidator.validateNorthFund(data);

                if (validation.valid) {
                    const payload: CachedPayload<NorthFund[]> = {
                        data,
                        source: source as DataSource,
                        asOf: new Date().toISOString(),
                    };
                    cache.set(cacheKey, payload, CACHE_TTL.NORTH_FUND);
                    cache.set(staleKey, payload, CACHE_TTL.NORTH_FUND_STALE);
                    return {
                        success: true,
                        data,
                        source: source as DataSource,
                        quality: {
                            valid: true,
                            warnings: warnings.length > 0
                                ? [...warnings, ...validation.warnings]
                                : (validation.warnings.length > 0 ? validation.warnings : undefined),
                            asOf: new Date().toISOString(),
                            degraded: false,
                        },
                    };
                }

                warnings.push(`${source} 数据校验未通过：${validation.errors.join('; ')}`);
            } catch (error) {
                warnings.push(`${source} 调用异常：${String(error)}`);
            }
        }

        const stale = cache.get<CachedPayload<NorthFund[]>>(staleKey);
        if (stale?.data?.length) {
            const validation = dataValidator.validateNorthFund(stale.data);
            if (validation.valid) {
                return {
                    success: true,
                    data: stale.data,
                    source: stale.source,
                    cached: true,
                    quality: {
                        valid: true,
                        warnings: warnings.length > 0 ? warnings : undefined,
                        asOf: stale.asOf,
                        degraded: true,
                        degradeReason: 'stale-if-error',
                    },
                };
            }
        }

        if (warnings.length > 0) {
            console.warn(`[north_fund] 所有数据源失败: ${warnings.join('；')}`);
        }

        return {
            success: false,
            error: toFriendlyError('eastmoney', warnings.join('; '), '北向资金暂不可用，请稍后重试。'),
        };
    }

    /**
     * 获取板块资金流向
     */
    async getSectorFlow(topN: number): Promise<ApiResponse<SectorData[]>> {
        const sources = DATA_SOURCE_PRIORITY.SECTOR_FLOW ?? ['eastmoney'];
        const warnings: string[] = [];
        const cacheKey = CacheAdapter.generateKey('sectorflow', 'aggregate', topN.toString());
        const staleKey = CacheAdapter.generateKey('sectorflow', 'aggregate', 'stale', topN.toString());
        const cached = cache.get<CachedPayload<SectorData[]>>(cacheKey);
        if (cached?.data?.length) {
            const validation = dataValidator.validateSectorFlow(cached.data);
            if (validation.valid) {
                return {
                    success: true,
                    data: cached.data,
                    source: cached.source,
                    cached: true,
                    quality: {
                        valid: true,
                        warnings: validation.warnings.length > 0 ? validation.warnings : undefined,
                        asOf: cached.asOf,
                        degraded: false,
                    },
                };
            }
        }

        for (const source of sources) {
            const adapter = this.adapters.get(source as DataSource) as EastMoneyAdapter | undefined;
            if (!adapter || !('getSectorFlow' in adapter)) continue;

            try {
                const data = await adapter.getSectorFlow(topN);
                const validation = dataValidator.validateSectorFlow(data);
                if (validation.valid) {
                    const payload: CachedPayload<SectorData[]> = {
                        data,
                        source: source as DataSource,
                        asOf: new Date().toISOString(),
                    };
                    cache.set(cacheKey, payload, CACHE_TTL.SECTOR_FLOW);
                    cache.set(staleKey, payload, CACHE_TTL.SECTOR_FLOW_STALE);
                    return {
                        success: true,
                        data,
                        source: source as DataSource,
                        quality: {
                            valid: true,
                            warnings: validation.warnings.length > 0 ? validation.warnings : undefined,
                            asOf: payload.asOf,
                            degraded: false,
                        },
                    };
                }
                warnings.push(`${source} 数据校验未通过：${validation.errors.join('; ')}`);
            } catch (error) {
                warnings.push(`${source} 调用异常：${String(error)}`);
            }
        }

        const stale = cache.get<CachedPayload<SectorData[]>>(staleKey);
        if (stale?.data?.length) {
            const validation = dataValidator.validateSectorFlow(stale.data);
            if (validation.valid) {
                return {
                    success: true,
                    data: stale.data,
                    source: stale.source,
                    cached: true,
                    quality: {
                        valid: true,
                        warnings: warnings.length > 0 ? warnings : undefined,
                        asOf: stale.asOf,
                        degraded: true,
                        degradeReason: 'stale-if-error',
                    },
                };
            }
        }

        return {
            success: false,
            error: `板块资金流向功能暂不可用：${warnings.join('；') || '未找到可用的数据适配器'}`,
        };
    }

    /**
     * 获取五档盘口数据
     */
    async getOrderBook(code: string): Promise<ApiResponse<OrderBook>> {
        const adapter = this.adapters.get('eastmoney') as EastMoneyAdapter | undefined;
        if (!adapter) {
            return { success: false, error: '盘口数据功能暂不可用：未找到可用的数据适配器' };
        }

        try {
            const data = await adapter.getOrderBook(code);
            return { success: true, data, source: 'eastmoney' };
        } catch (error) {
            return { success: false, error: toFriendlyError('eastmoney', error, '盘口数据暂不可用，请稍后重试') };
        }
    }

    /**
     * 获取成交明细
     */
    async getTradeDetails(code: string, limit: number = 20): Promise<ApiResponse<TradeDetail[]>> {
        const adapter = this.adapters.get('eastmoney') as EastMoneyAdapter | undefined;
        if (!adapter) {
            return { success: false, error: '成交明细功能暂不可用：未找到可用的数据适配器' };
        }

        try {
            const data = await adapter.getTradeDetails(code, limit);
            return { success: true, data, source: 'eastmoney' };
        } catch (error) {
            return { success: false, error: toFriendlyError('eastmoney', error, '成交明细暂不可用，请稍后重试') };
        }
    }

    /**
     * 获取涨停板数据
     */
    async getLimitUpStocks(date?: string): Promise<ApiResponse<LimitUpStock[]>> {
        const adapter = this.adapters.get('eastmoney') as EastMoneyAdapter | undefined;
        if (!adapter) {
            return { success: false, error: '涨停板数据功能暂不可用：未找到可用的数据适配器' };
        }

        try {
            const data = await adapter.getLimitUpStocks(date);
            return { success: true, data, source: 'eastmoney' };
        } catch (error) {
            return { success: false, error: toFriendlyError('eastmoney', error, '涨停板数据暂不可用，请稍后重试') };
        }
    }

    /**
     * 获取涨停统计
     */
    async getLimitUpStatistics(date?: string): Promise<ApiResponse<LimitUpStatistics>> {
        const adapter = this.adapters.get('eastmoney') as EastMoneyAdapter | undefined;
        if (!adapter) {
            return { success: false, error: '涨停统计功能暂不可用：未找到可用的数据适配器' };
        }

        try {
            const data = await adapter.getLimitUpStatistics(date);
            return { success: true, data, source: 'eastmoney' };
        } catch (error) {
            return { success: false, error: toFriendlyError('eastmoney', error, '涨停统计暂不可用，请稍后重试') };
        }
    }

    /**
     * 获取两融数据
     */
    async getMarginData(code?: string): Promise<ApiResponse<MarginData[]>> {
        const adapter = this.adapters.get('eastmoney') as EastMoneyAdapter | undefined;
        if (!adapter) {
            return { success: false, error: '两融数据功能暂不可用：未找到可用的数据适配器' };
        }

        try {
            const data = await adapter.getMarginData(code);
            return { success: true, data, source: 'eastmoney' };
        } catch (error) {
            return { success: false, error: toFriendlyError('eastmoney', error, '两融数据暂不可用，请稍后重试') };
        }
    }

    /**
     * 获取融资融券排行
     */
    async getMarginRanking(
        topN: number,
        sortBy: 'balance' | 'buy' | 'sell'
    ): Promise<ApiResponse<Array<{
        date: string;
        code: string;
        name: string;
        marginBalance: number;
        marginBuy: number;
        shortSell: number;
        totalBalance: number;
    }>>> {
        const adapter = this.adapters.get('eastmoney') as EastMoneyAdapter | undefined;
        if (!adapter || !('getMarginRanking' in adapter)) {
            return { success: false, error: '融资融券排行功能暂不可用：未找到可用的数据适配器' };
        }

        try {
            const data = await adapter.getMarginRanking(topN, sortBy);
            return { success: true, data, source: 'eastmoney' };
        } catch (error) {
            return { success: false, error: toFriendlyError('eastmoney', error, '融资融券排行暂不可用，请稍后重试') };
        }
    }

    /**
     * 获取大宗交易数据
     */
    async getBlockTrades(date?: string, code?: string): Promise<ApiResponse<BlockTrade[]>> {
        const adapter = this.adapters.get('eastmoney') as EastMoneyAdapter | undefined;
        if (!adapter) {
            return { success: false, error: '大宗交易数据功能暂不可用：未找到可用的数据适配器' };
        }

        try {
            const data = await adapter.getBlockTrades(date, code);
            return { success: true, data, source: 'eastmoney' };
        } catch (error) {
            return { success: false, error: toFriendlyError('eastmoney', error, '大宗交易数据暂不可用，请稍后重试') };
        }
    }

    /**
     * 获取北向资金持股
     */
    async getNorthFundHolding(code: string): Promise<ApiResponse<{ shares: number; ratio: number; change: number }>> {
        const adapter = this.adapters.get('eastmoney') as EastMoneyAdapter | undefined;
        if (!adapter) {
            return { success: false, error: '北向资金持股功能暂不可用：未找到可用的数据适配器' };
        }

        try {
            const data = await adapter.getNorthFundHolding(code);
            return { success: true, data, source: 'eastmoney' };
        } catch (error) {
            return { success: false, error: toFriendlyError('eastmoney', error, '北向资金持股暂不可用，请稍后重试') };
        }
    }

    /**
     * 获取北向资金持股排名
     */
    async getNorthFundTop(topN: number): Promise<ApiResponse<Array<{ code: string; name: string; shares: number; ratio: number; marketCap: number }>>> {
        const adapter = this.adapters.get('eastmoney') as EastMoneyAdapter | undefined;
        if (!adapter) {
            return { success: false, error: '北向资金排名功能暂不可用：未找到可用的数据适配器' };
        }

        try {
            const data = await adapter.getNorthFundTop(topN);
            return { success: true, data, source: 'eastmoney' };
        } catch (error) {
            return { success: false, error: toFriendlyError('eastmoney', error, '北向资金排名暂不可用，请稍后重试') };
        }
    }

    /**
     * 获取股票新闻
     */
    async getStockNews(code: string, limit: number = 10): Promise<ApiResponse<Array<{ title: string; time: string; source: string; url: string }>>> {
        const adapter = this.adapters.get('eastmoney') as EastMoneyAdapter | undefined;
        if (!adapter) {
            return { success: false, error: '股票新闻功能暂不可用：未找到可用的数据适配器' };
        }

        try {
            const data = await adapter.getStockNews(code, limit);
            return { success: true, data, source: 'eastmoney' };
        } catch (error) {
            return { success: false, error: toFriendlyError('eastmoney', error, '股票新闻暂不可用，请稍后重试') };
        }
    }

    /**
     * 获取市场快讯
     */
    async getMarketNews(limit: number = 20): Promise<ApiResponse<Array<{ title: string; time: string; content: string }>>> {
        const adapter = this.adapters.get('eastmoney') as EastMoneyAdapter | undefined;
        if (!adapter) {
            return { success: false, error: '市场快讯功能暂不可用：未找到可用的数据适配器' };
        }

        try {
            const data = await adapter.getMarketNews(limit);
            return { success: true, data, source: 'eastmoney' };
        } catch (error) {
            return { success: false, error: toFriendlyError('eastmoney', error, '市场快讯暂不可用，请稍后重试') };
        }
    }

    /**
     * 检查所有适配器的可用性
     */
    async checkHealth(): Promise<Record<DataSource, boolean>> {
        const results: Record<string, boolean> = {};

        for (const [source, adapter] of this.adapters) {
            if (source === 'akshare') {
                results[source] = await checkAkshareMcpHealth();
                continue;
            }
            try {
                results[source] = await adapter.isAvailable();
            } catch {
                results[source] = false;
            }
        }

        return results as Record<DataSource, boolean>;
    }

    /**
     * 获取缓存统计
     */
    getCacheStats() {
        return cache.getStats();
    }

    /**
     * 获取限流统计
     */
    getRateLimiterStats() {
        return rateLimiter.getStats();
    }
}

// 导出默认实例
export const adapterManager = new AdapterManager();

// 重新导出
export { cache, CacheAdapter } from './cache-adapter.js';
export { rateLimiter, createRateLimiter, RateLimiterManager } from './rate-limiter.js';
export { eastMoneyAdapter, EastMoneyAdapter } from './eastmoney-adapter.js';
export { sinaAdapter, SinaAdapter } from './sina-adapter.js';
export { akShareAdapter, AKShareAdapter } from './akshare-adapter.js';
export { tushareAdapter, TushareAdapter } from './tushare-adapter.js';
export { baostockAdapter, BaostockAdapter } from './baostock-adapter.js';
export { windAdapter, WindAdapter } from './wind-adapter.js';
