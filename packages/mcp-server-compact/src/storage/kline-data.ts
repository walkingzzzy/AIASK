/**
 * K线数据访问层
 */

import { timescaleDB } from './timescaledb.js';

// ========== 类型定义 ==========

export interface DailyBar {
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    amount: number;
    changePercent: number;
    turnover: number;
}

// ========== 查询函数 ==========

export async function getDailyBars(code: string, limit: number = 100): Promise<DailyBar[]> {
    // TimescaleDB adapter doesn't have getDailyBars with limit + desc sort easily access directly?
    // Actually we can add it or just use getKlineHistory with recent dates.
    // BUT adapter getKlineHistory is range based (start, end).
    // Let's assume we fetch last 100 days.
    const end = new Date();
    const start = new Date(Date.now() - limit * 2 * 24 * 60 * 60 * 1000); // rough estimate
    const data = await timescaleDB.getKlineHistory(code, start, end);
    // data is ASC order.
    // We want DESC for "getDailyBars" usually? 
    // The original `getDailyBars` in SQLite implementation returned `ORDER BY date DESC` then `.reverse()`!
    // So it returned ASCENDING order in the end.
    // My adapter `getKlineHistory` returns ASC. So we are good.
    // Limit is partial issue if we fetch by date range.
    return data.slice(-limit).map((r: any) => ({
        date: r.date instanceof Date ? r.date.toISOString().split('T')[0] : r.date as string,
        open: r.open,
        high: r.high,
        low: r.low,
        close: r.close,
        volume: Number(r.volume),
        amount: r.amount,
        changePercent: r.change_percent || 0,
        turnover: r.turnover || 0
    }));
}

export async function getDailyBarsByDateRange(code: string, startDate: string, endDate: string): Promise<DailyBar[]> {
    const data = await timescaleDB.getKlineHistory(code, new Date(startDate), new Date(endDate));
    return data.map((r: any) => ({
        date: r.date instanceof Date ? r.date.toISOString().split('T')[0] : r.date as string,
        open: r.open,
        high: r.high,
        low: r.low,
        close: r.close,
        volume: Number(r.volume),
        amount: r.amount,
        changePercent: r.change_percent || 0,
        turnover: r.turnover || 0
    }));
}

export async function getStocksNeedingKlineUpdate(daysOld: number = 1, limit: number = 100): Promise<string[]> {
    return timescaleDB.getStocksNeedingKlineUpdate(limit);
}

export async function markKlineSyncAttempted(stockCodes: string[]): Promise<void> {
    return timescaleDB.markKlineSyncAttempted(stockCodes);
}

// ========== 写入函数 ==========

export async function upsertDailyBar(bar: {
    code: string;
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number;
    amount?: number;
    changePercent?: number;
    turnover?: number;
    sourceTimestamp?: string | null;
}): Promise<boolean> {
    try {
        await timescaleDB.upsertDailyBar(bar);
        return true;
    } catch (e) {
        console.error('upsertDailyBar failed', e);
        return false;
    }
}

export async function batchUpsertDailyBars(bars: Array<{
    code: string;
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number;
    amount?: number;
    changePercent?: number;
    turnover?: number;
    sourceTimestamp?: string | null;
}>): Promise<{ success: number; failed: number }> {
    const mapped = bars.map((b: any) => ({
        code: b.code,
        date: b.date,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
        volume: b.volume || 0,
        amount: b.amount || 0,
        turnover: b.turnover,
        change_percent: b.changePercent
    }));
    try {
        const res = await timescaleDB.batchUpsertKline(mapped);
        return { success: res.inserted, failed: bars.length - res.inserted };
    } catch (e) {
        return { success: 0, failed: bars.length };
    }
}
