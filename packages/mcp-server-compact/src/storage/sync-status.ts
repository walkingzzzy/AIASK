/**
 * 数据同步状态管理
 */

import { timescaleDB } from './timescaledb.js';

// ========== 类型定义 ==========

export interface SyncStatus {
    totalStocks: number;
    quotesUpdatedToday: number;
    quotesStale: number;
    klineUpdatedToday: number;
    klineStale: number;
    lastQuoteUpdate: string | null;
    lastKlineUpdate: string | null;
}

export interface DatabaseStats {
    stockCount: number;
    financialRecords: number;
    dailyBarRecords: number;
    quoteRecords: number;
}

// ========== 查询函数 ==========

/**
 * 获取同步状态统计
 */
export async function getSyncStatus(): Promise<SyncStatus> {
    return timescaleDB.getSyncStatus();
}

/**
 * 获取数据库统计信息
 */
export async function getDatabaseStats(): Promise<DatabaseStats> {
    return timescaleDB.getDatabaseStats();
}
