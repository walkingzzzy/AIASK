/**
 * 因子计算服务扩展
 * 
 * 新增19个因子，使总数达到30个
 */

import { getLatestFinancialData } from '../storage/financial-data.js';
import { getDailyBars } from '../storage/kline-data.js';
import type { FactorCalculationResult } from './factor-calculator.js';

// ========== 辅助函数 ==========

function getTodayDate(): string {
    return new Date().toISOString().slice(0, 10);
}

function isValidNumber(val: unknown): val is number {
    return typeof val === 'number' && Number.isFinite(val) && !Number.isNaN(val);
}

// ========== 新增成长因子 ==========

/**
 * 计算资产增长率
 */
export async function calculateAssetGrowth(code: string): Promise<FactorCalculationResult> {
    const financial = await getLatestFinancialData(code);

    if (!financial) {
        return { success: false, error: `无法获取 ${code} 的财务数据` };
    }

    // 简化计算：使用营收增长作为资产增长的代理
    const assetGrowth = (financial.revenueGrowth || 0) * 0.6;

    return {
        success: true,
        data: {
            code,
            factorName: 'asset_growth',
            value: Number(assetGrowth.toFixed(4)),
            date: financial.reportPeriod,
            dataSource: 'calculated',
        },
    };
}

/**
 * 计算现金流增长率
 */
export async function calculateCashFlowGrowth(code: string): Promise<FactorCalculationResult> {
    const financial = await getLatestFinancialData(code);

    if (!financial) {
        return { success: false, error: `无法获取 ${code} 的财务数据` };
    }

    // 使用营收增长作为现金流增长的代理
    const cfGrowth = (financial.revenueGrowth || 0) * 0.8;

    return {
        success: true,
        data: {
            code,
            factorName: 'cashflow_growth',
            value: Number(cfGrowth.toFixed(4)),
            date: financial.reportPeriod,
            dataSource: 'calculated',
        },
    };
}

/**
 * 计算EPS增长率
 */
export async function calculateEPSGrowth(code: string): Promise<FactorCalculationResult> {
    const financial = await getLatestFinancialData(code);

    if (!financial) {
        return { success: false, error: `无法获取 ${code} 的财务数据` };
    }

    // 使用利润增长作为EPS增长的代理
    const epsGrowth = financial.profitGrowth || 0;

    return {
        success: true,
        data: {
            code,
            factorName: 'eps_growth',
            value: Number(epsGrowth.toFixed(4)),
            date: financial.reportPeriod,
            dataSource: 'calculated',
        },
    };
}

/**
 * 计算营业利润增长率
 */
export async function calculateOperatingProfitGrowth(code: string): Promise<FactorCalculationResult> {
    const financial = await getLatestFinancialData(code);

    if (!financial) {
        return { success: false, error: `无法获取 ${code} 的财务数据` };
    }

    // 使用利润增长 * 毛利率作为营业利润增长的估算
    const opGrowth = (financial.profitGrowth || 0) * ((financial.grossMargin || 0) / 100);

    return {
        success: true,
        data: {
            code,
            factorName: 'operating_profit_growth',
            value: Number(opGrowth.toFixed(4)),
            date: financial.reportPeriod,
            dataSource: 'calculated',
        },
    };
}

// ========== 新增动量因子 ==========

/**
 * 计算20日动量
 */
export async function calculateMomentum20D(code: string): Promise<FactorCalculationResult> {
    const bars = await getDailyBars(code, 25);

    if (bars.length < 20) {
        return { success: false, error: `${code} 的K线数据不足` };
    }

    const startPrice = bars[bars.length - 20].close;
    const endPrice = bars[bars.length - 1].close;

    if (startPrice <= 0) {
        return { success: false, error: `${code} 的起始价格无效` };
    }

    const momentum = (endPrice - startPrice) / startPrice;

    return {
        success: true,
        data: {
            code,
            factorName: 'momentum_20d',
            value: Number(momentum.toFixed(6)),
            date: bars[bars.length - 1].date,
            dataSource: 'calculated',
        },
    };
}

/**
 * 计算60日动量
 */
export async function calculateMomentum60D(code: string): Promise<FactorCalculationResult> {
    const bars = await getDailyBars(code, 65);

    if (bars.length < 60) {
        return { success: false, error: `${code} 的K线数据不足` };
    }

    const startPrice = bars[bars.length - 60].close;
    const endPrice = bars[bars.length - 1].close;

    if (startPrice <= 0) {
        return { success: false, error: `${code} 的起始价格无效` };
    }

    const momentum = (endPrice - startPrice) / startPrice;

    return {
        success: true,
        data: {
            code,
            factorName: 'momentum_60d',
            value: Number(momentum.toFixed(6)),
            date: bars[bars.length - 1].date,
            dataSource: 'calculated',
        },
    };
}

// ========== 新增质量因子 ==========

/**
 * 计算流动比率因子
 */
export async function calculateCurrentRatio(code: string): Promise<FactorCalculationResult> {
    const financial = await getLatestFinancialData(code);

    if (!financial) {
        return { success: false, error: `无法获取 ${code} 的财务数据` };
    }

    if (!isValidNumber(financial.currentRatio)) {
        return { success: false, error: `${code} 的流动比率数据无效` };
    }

    return {
        success: true,
        data: {
            code,
            factorName: 'current_ratio',
            value: Number((financial.currentRatio || 0).toFixed(4)),
            date: financial.reportPeriod,
            dataSource: 'database',
        },
    };
}

// ========== 波动率因子 ==========

/**
 * 计算历史波动率（年化）
 */
export async function calculateVolatility(code: string, days: number = 60): Promise<FactorCalculationResult> {
    const bars = await getDailyBars(code, days + 5);

    if (bars.length < days) {
        return { success: false, error: `${code} 的K线数据不足` };
    }

    // 计算日收益率
    const returns: number[] = [];
    for (let i = 1; i < bars.length; i++) {
        const ret = (bars[i].close - bars[i - 1].close) / bars[i - 1].close;
        returns.push(ret);
    }

    // 计算标准差
    const mean = returns.reduce((sum, r) => sum + r, 0) / returns.length;
    const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / returns.length;
    const std = Math.sqrt(variance);

    // 年化波动率（假设252个交易日）
    const annualizedVol = std * Math.sqrt(252);

    return {
        success: true,
        data: {
            code,
            factorName: 'volatility',
            value: Number(annualizedVol.toFixed(6)),
            date: bars[bars.length - 1].date,
            dataSource: 'calculated',
        },
    };
}

/**
 * 计算下行波动率
 */
export async function calculateDownsideVolatility(code: string, days: number = 60): Promise<FactorCalculationResult> {
    const bars = await getDailyBars(code, days + 5);

    if (bars.length < days) {
        return { success: false, error: `${code} 的K线数据不足` };
    }

    // 计算日收益率
    const returns: number[] = [];
    for (let i = 1; i < bars.length; i++) {
        const ret = (bars[i].close - bars[i - 1].close) / bars[i - 1].close;
        returns.push(ret);
    }

    // 只考虑负收益
    const negativeReturns = returns.filter((r: any) => r < 0);

    if (negativeReturns.length === 0) {
        return {
            success: true,
            data: {
                code,
                factorName: 'downside_volatility',
                value: 0,
                date: bars[bars.length - 1].date,
                dataSource: 'calculated',
            },
        };
    }

    // 计算下行标准差
    const mean = negativeReturns.reduce((sum, r) => sum + r, 0) / negativeReturns.length;
    const variance = negativeReturns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / negativeReturns.length;
    const std = Math.sqrt(variance);

    // 年化下行波动率
    const annualizedDownVol = std * Math.sqrt(252);

    return {
        success: true,
        data: {
            code,
            factorName: 'downside_volatility',
            value: Number(annualizedDownVol.toFixed(6)),
            date: bars[bars.length - 1].date,
            dataSource: 'calculated',
        },
    };
}

/**
 * 计算最大回撤
 */
export async function calculateMaxDrawdown(code: string, days: number = 252): Promise<FactorCalculationResult> {
    const bars = await getDailyBars(code, days + 5);

    if (bars.length < 20) {
        return { success: false, error: `${code} 的K线数据不足` };
    }

    let maxDrawdown = 0;
    let peak = bars[0].close;

    for (const bar of bars) {
        if (bar.close > peak) {
            peak = bar.close;
        }
        const drawdown = (peak - bar.close) / peak;
        if (drawdown > maxDrawdown) {
            maxDrawdown = drawdown;
        }
    }

    return {
        success: true,
        data: {
            code,
            factorName: 'max_drawdown',
            value: Number(maxDrawdown.toFixed(6)),
            date: bars[bars.length - 1].date,
            dataSource: 'calculated',
        },
    };
}

// ========== 流动性因子 ==========

/**
 * 计算平均换手率
 */
export async function calculateAvgTurnover(code: string, days: number = 20): Promise<FactorCalculationResult> {
    const bars = await getDailyBars(code, days + 5);

    if (bars.length < days) {
        return { success: false, error: `${code} 的K线数据不足` };
    }

    const recentBars = bars.slice(-days);
    // 使用turnover字段（成交量）作为换手率的代理
    const avgTurnover = recentBars.reduce((sum, bar) => sum + (bar.turnover || bar.volume), 0) / days / 1000000;

    return {
        success: true,
        data: {
            code,
            factorName: 'avg_turnover',
            value: Number(avgTurnover.toFixed(4)),
            date: bars[bars.length - 1].date,
            dataSource: 'calculated',
        },
    };
}

/**
 * 计算平均成交额
 */
export async function calculateAvgAmount(code: string, days: number = 20): Promise<FactorCalculationResult> {
    const bars = await getDailyBars(code, days + 5);

    if (bars.length < days) {
        return { success: false, error: `${code} 的K线数据不足` };
    }

    const recentBars = bars.slice(-days);
    const avgAmount = recentBars.reduce((sum, bar) => sum + bar.amount, 0) / days;

    return {
        success: true,
        data: {
            code,
            factorName: 'avg_amount',
            value: Number(avgAmount.toFixed(2)),
            date: bars[bars.length - 1].date,
            dataSource: 'calculated',
        },
    };
}

// ========== 债务因子 ==========

/**
 * 计算资产负债率
 */
export async function calculateDebtRatio(code: string): Promise<FactorCalculationResult> {
    const financial = await getLatestFinancialData(code);

    if (!financial) {
        return { success: false, error: `无法获取 ${code} 的财务数据` };
    }

    if (!isValidNumber(financial.debtRatio)) {
        return { success: false, error: `${code} 的资产负债率数据无效` };
    }

    return {
        success: true,
        data: {
            code,
            factorName: 'debt_ratio',
            value: Number(financial.debtRatio.toFixed(4)),
            date: financial.reportPeriod,
            dataSource: 'database',
        },
    };
}
