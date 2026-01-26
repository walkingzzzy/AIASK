/**
 * 东方财富 API 适配器
 * 
 * 此文件为向后兼容的重新导出
 * 实际实现已模块化到 ./eastmoney/ 目录
 */

import {
    quoteAPI,
    klineAPI,
    marketAPI,
    fundFlowAPI,
    EastMoneyBase,
    SOURCE,
    cache,
    CacheAdapter,
    rateLimiter,
    CACHE_TTL
} from './eastmoney/index.js';
import { config } from '../config/index.js';
import type { QuoteAdapter, MarketAdapter } from '../types/adapters.js';
import type { RealtimeQuote, KlineData, KlinePeriod, StockInfo, NorthFund, SectorData, DragonTiger, LimitUpStock, LimitUpStatistics, MarginData, BlockTrade } from '../types/stock.js';

export * from './eastmoney/index.js';

export class EastMoneyAdapter implements QuoteAdapter, MarketAdapter {
    readonly name: 'eastmoney' = 'eastmoney';

    async isAvailable(): Promise<boolean> {
        return quoteAPI.isAvailable();
    }

    async getRealtimeQuote(code: string): Promise<RealtimeQuote> {
        return quoteAPI.getRealtimeQuote(code);
    }

    async getBatchQuotes(codes: string[]): Promise<RealtimeQuote[]> {
        return quoteAPI.getBatchQuotes(codes);
    }

    async getKline(code: string, period: KlinePeriod, limit: number): Promise<KlineData[]> {
        return klineAPI.getKline(code, period, limit);
    }

    async getStockInfo(code: string): Promise<StockInfo> {
        return quoteAPI.getStockInfo(code);
    }

    // ========== MarketAdapter / Extra Methods ==========

    async getDragonTiger(date?: string): Promise<DragonTiger[]> {
        return marketAPI.getDragonTiger(date);
    }

    // Alias for getDragonTiger to satisfy previous usage which might have been getDragonTigerList
    // But interface says getDragonTiger. AdapterManager calls getDragonTiger.
    // So getDragonTiger above is sufficient.

    async getLimitUpStocks(date?: string): Promise<LimitUpStock[]> {
        return marketAPI.getLimitUpStocks(date);
    }

    // Alias for getLimitUpStocks if needed as getLimitUpPool?
    async getLimitUpPool(date?: string) {
        return marketAPI.getLimitUpStocks(date);
    }

    async getLimitUpStatistics(date?: string): Promise<LimitUpStatistics> {
        return marketAPI.getLimitUpStatistics(date);
    }

    async getSectorFlow(topN: number): Promise<SectorData[]> {
        return marketAPI.getSectorFlow(topN);
    }

    // ========== FundFlow Integration ==========

    async getNorthFund(days: number): Promise<NorthFund[]> {
        return fundFlowAPI.getNorthFund(days);
    }

    async getNorthFundTop(topN: number) {
        return fundFlowAPI.getNorthFundTop(topN);
    }

    async getNorthFundHolding(code: string) {
        return fundFlowAPI.getNorthFundHolding(code);
    }

    async getMarginData(code?: string): Promise<MarginData[]> {
        return fundFlowAPI.getMarginData(code);
    }

    async getMarginRanking(topN: number, sortBy: 'balance' | 'buy' | 'sell') {
        return fundFlowAPI.getMarginRanking(topN, sortBy);
    }

    async getBlockTrades(date?: string, code?: string): Promise<BlockTrade[]> {
        return fundFlowAPI.getBlockTrades(date, code);
    }

    // ========== Missing / Stubbed Methods ==========

    async searchStocks(keyword: string) {
        // Simple stub or use quoteAPI if possible (quoteAPI doesn't expose search currently)
        // Returning empty array as fallback, relying on storage search
        return [];
    }

    async getFundFlow(code: string) {
        return fundFlowAPI.getStockFundFlow(code);
    }

    async getSectorFundFlow(days: number) {
        return [];
    }

    async getStockFundFlow(code: string) {
        return undefined;
    }

    async getOrderBook(code: string) {
        return undefined; // L2 data not supported
    }

    async getTradeDetails(code: string, limit?: number) {
        return []; // L2 tick data not supported
    }

    async getStockNews(code: string, limit: number) {
        return [];
    }

    async getMarketNews(limit: number) {
        return [];
    }
}

export const eastMoneyAdapter = new EastMoneyAdapter();
