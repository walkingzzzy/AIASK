/**
 * 估值数据访问层
 */

import { timescaleDB } from './timescaledb.js';
import { dataValidator } from '../services/data-validator.js';
import { recordDataQualityIssue } from './data-quality.js';
import type { RealtimeQuote } from '../types/stock.js';

function buildQuoteForValidation(quote: {
    code: string;
    name?: string;
    price: number;
    changePercent?: number;
    changeAmount?: number;
    open?: number;
    high?: number;
    low?: number;
    prevClose?: number;
    volume?: number;
    amount?: number;
    pe?: number;
    pb?: number;
    marketCap?: number;
}): RealtimeQuote {
    return {
        code: quote.code,
        name: quote.name || '',
        price: quote.price,
        change: quote.changeAmount ?? 0,
        changePercent: quote.changePercent ?? 0,
        open: quote.open ?? quote.price,
        high: quote.high ?? quote.price,
        low: quote.low ?? quote.price,
        preClose: quote.prevClose ?? quote.price,
        volume: quote.volume ?? 0,
        amount: quote.amount ?? 0,
        turnoverRate: 0,
        timestamp: Date.now(),
        pe: quote.pe,
        pb: quote.pb,
        marketCap: quote.marketCap,
    };
}

// ========== 类型定义 ==========

export interface ValuationData {
    code: string;
    name: string;
    price: number;
    changePercent?: number | null;
    changeAmount?: number | null;
    open?: number | null;
    high?: number | null;
    low?: number | null;
    prevClose?: number | null;
    volume?: number | null;
    amount?: number | null;
    pe: number | null;
    pb: number | null;
    marketCap: number | null;
    timestamp: string;
    sourceTimestamp?: string | null;
    ingestedAt?: string | null;
}

export interface ValuationHistoryItem {
    date: string;
    pe: number | null;
    pb: number | null;
    price: number;
}

// ========== 查询函数 ==========

export async function getValuationData(code: string): Promise<ValuationData | null> {
    const row = await timescaleDB.getValuationData(code);
    if (!row) return null;
    return mapRowToValuation(row);
}

export async function getValuationHistory(code: string, limit: number = 252): Promise<ValuationHistoryItem[]> {
    const rows = await timescaleDB.getValuationHistory(code, limit);
    return rows.map(row => ({
        date: row.time instanceof Date ? row.time.toISOString() : row.time,
        pe: row.pe,
        pb: row.pb,
        price: row.price
    })).reverse();
}

export async function getBatchValuationData(codes: string[]): Promise<ValuationData[]> {
    const rows = await timescaleDB.getBatchValuationData(codes);
    return rows.map(mapRowToValuation);
}

export async function getStocksNeedingUpdate(hoursOld: number = 24, limit: number = 100): Promise<string[]> {
    return timescaleDB.getStocksNeedingQuoteUpdate(hoursOld, limit);
}

function mapRowToValuation(row: any): ValuationData {
    return {
        code: row.code,
        name: row.name,
        price: row.price,
        changePercent: row.change_pct,
        changeAmount: row.change_amt,
        open: row.open,
        high: row.high,
        low: row.low,
        prevClose: row.prev_close,
        volume: Number(row.volume),
        amount: row.amount,
        pe: row.pe,
        pb: row.pb,
        marketCap: row.mkt_cap,
        timestamp: row.time instanceof Date ? row.time.toISOString() : row.time,
        sourceTimestamp: null,
        ingestedAt: row.updated_at instanceof Date ? row.updated_at.toISOString() : row.updated_at
    };
}

// ========== 写入函数 ==========

export async function upsertQuote(quote: {
    code: string;
    name?: string;
    price: number;
    changePercent?: number;
    changeAmount?: number;
    open?: number;
    high?: number;
    low?: number;
    prevClose?: number;
    volume?: number;
    amount?: number;
    pe?: number;
    pb?: number;
    marketCap?: number;
    sourceTimestamp?: string | null;
}): Promise<boolean> {
    const validation = dataValidator.validateQuote(buildQuoteForValidation(quote));
    if (!validation.valid) {
        recordDataQualityIssue({
            dataset: 'realtime_quote',
            code: quote.code,
            reason: validation.errors.join('; '),
            source: 'storage',
            payload: quote,
        });
        return false;
    }

    try {
        await timescaleDB.upsertQuote({
            code: quote.code,
            name: quote.name,
            price: quote.price,
            changePercent: quote.changePercent,
            changeAmount: quote.changeAmount,
            open: quote.open,
            high: quote.high,
            low: quote.low,
            prevClose: quote.prevClose,
            volume: quote.volume,
            amount: quote.amount,
            pe: quote.pe,
            pb: quote.pb,
            marketCap: quote.marketCap,
            timestamp: quote.sourceTimestamp || new Date().toISOString()
        });
        return true;
    } catch (error) {
        console.error(`[ValuationData] 更新行情失败:`, error);
        return false;
    }
}

export async function batchUpsertQuotes(quotes: Array<{
    code: string;
    name?: string;
    price: number;
    changePercent?: number;
    changeAmount?: number;
    open?: number;
    high?: number;
    low?: number;
    prevClose?: number;
    volume?: number;
    amount?: number;
    pe?: number;
    pb?: number;
    marketCap?: number;
    sourceTimestamp?: string | null;
}>): Promise<{ success: number; failed: number }> {
    let success = 0;
    let failed = 0;
    for (const q of quotes) {
        if (await upsertQuote(q)) success++; else failed++;
    }
    return { success, failed };
}
