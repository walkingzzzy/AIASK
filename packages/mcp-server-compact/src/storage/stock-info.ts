/**
 * 股票基础信息数据访问层
 */

import { timescaleDB } from './timescaledb.js';

// ========== 类型定义 ==========

export interface StockInfo {
    code: string;
    name: string;
    market: string;
    sector: string;
    industry: string | null;
    listDate: string;
}

// ========== 查询函数 ==========

export function getStockInfo(code: string): Promise<StockInfo | null> {
    return timescaleDB.getStockInfo(code);
}

export function searchStocks(keyword: string, limit: number = 20): Promise<StockInfo[]> {
    return timescaleDB.searchStocks(keyword, limit);
}

export function getStocksBySector(sector: string, limit: number = 50): Promise<StockInfo[]> {
    return timescaleDB.getStocksBySector(sector, limit);
}

export function getSectorList(): Promise<string[]> {
    return timescaleDB.getSectorList();
}

export function getAllStockCodes(limit: number = 1000): Promise<string[]> {
    return timescaleDB.getAllStockCodes(limit);
}

// ========== 写入函数 ==========

export async function upsertStock(stock: {
    code: string;
    name: string;
    market?: string;
    sector?: string;
    industry?: string;
    listDate?: string;
}): Promise<boolean> {
    try {
        await timescaleDB.upsertStock(stock);
        return true;
    } catch (e) {
        console.error('upsertStock failed', e);
        return false;
    }
}

export async function batchUpsertStocks(stocks: Array<{
    code: string;
    name: string;
    market?: string;
    sector?: string;
    industry?: string;
    listDate?: string;
}>): Promise<{ success: number; failed: number }> {
    let success = 0;
    let failed = 0;
    for (const s of stocks) {
        if (await upsertStock(s)) success++; else failed++;
    }
    return { success, failed };
}

