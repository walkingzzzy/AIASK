/**
 * 选股筛选数据访问层
 */

import { timescaleDB } from './timescaledb.js';

// ========== 类型定义 ==========

export interface ScreeningCriteria {
    peMin?: number;
    peMax?: number;
    pbMin?: number;
    pbMax?: number;
    roeMin?: number;
    roeMax?: number;
    grossMarginMin?: number;
    netMarginMin?: number;
    revenueGrowthMin?: number;
    profitGrowthMin?: number;
    marketCapMin?: number;
    marketCapMax?: number;
    sector?: string;
}

export interface ScreeningResult {
    code: string;
    name: string;
    sector: string;
    pe: number | null;
    pb: number | null;
    roe: number | null;
    grossMargin: number | null;
    netMargin: number | null;
    revenueGrowth: number | null;
    profitGrowth: number | null;
    marketCap: number | null;
}

// ========== 查询函数 ==========

/**
 * 多条件选股筛选
 */
export async function screenStocks(criteria: ScreeningCriteria, limit: number = 50): Promise<ScreeningResult[]> {
    const rows = await timescaleDB.screenStocks(criteria, limit);
    return rows.map(row => ({
        code: row.code,
        name: row.name,
        sector: row.sector,
        pe: row.pe,
        pb: row.pb,
        roe: row.roe,
        grossMargin: row.gross_margin,
        netMargin: row.net_margin,
        revenueGrowth: row.revenue_growth,
        profitGrowth: row.profit_growth,
        marketCap: row.market_cap,
    }));
}
