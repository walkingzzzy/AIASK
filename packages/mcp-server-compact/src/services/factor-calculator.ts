/**
 * 因子计算服务（扩展版）
 * 
 * 基于本地数据库计算30+量化因子值
 * - 估值因子(5): EP, BP, SP, CFP, DP
 * - 成长因子(6): 营收增长, 利润增长, 资产增长, 现金流增长, EPS增长, 营业利润增长
 * - 动量因子(6): 1m/3m/6m/12m/20d/60d 动量
 * - 质量因子(8): ROE, ROA, 毛利率, 净利率, 资产周转率, 流动比率, 速动比率, 现金比率
 * - 波动率因子(3): 历史波动率, 下行波动率, 最大回撤
 * - 流动性因子(2): 换手率, 成交额
 */

import { getValuationData } from '../storage/valuation-data.js';
import { getLatestFinancialData } from '../storage/financial-data.js';
import { getDailyBars } from '../storage/kline-data.js';

// ========== 类型定义 ==========

export interface FactorValue {
    code: string;
    factorName: string;
    value: number;
    date: string;
    dataSource: 'database' | 'calculated';
    components?: Record<string, number | null>;
}

export interface FactorCalculationResult {
    success: boolean;
    data?: FactorValue;
    error?: string;
}

export interface BatchFactorResult {
    success: boolean;
    factors: FactorValue[];
    errors: Array<{ code: string; error: string }>;
}

// ========== 辅助函数 ==========

function getTodayDate(): string {
    return new Date().toISOString().slice(0, 10);
}

function isValidNumber(val: unknown): val is number {
    return typeof val === 'number' && Number.isFinite(val) && !Number.isNaN(val);
}

// ========== 估值因子 ==========

/**
 * 计算 EP (Earnings/Price = 1/PE)
 * 越高表示越便宜
 */
export async function calculateEP(code: string): Promise<FactorCalculationResult> {
    const valuation = await getValuationData(code);

    if (!valuation) {
        return { success: false, error: `无法获取 ${code} 的估值数据` };
    }

    if (!isValidNumber(valuation.pe) || valuation.pe <= 0) {
        return { success: false, error: `${code} 的 PE 数据无效或为负` };
    }

    const ep = 1 / valuation.pe;

    return {
        success: true,
        data: {
            code,
            factorName: 'ep',
            value: Number(ep.toFixed(6)),
            date: valuation.timestamp?.slice(0, 10) || getTodayDate(),
            dataSource: 'calculated',
            components: { pe: valuation.pe },
        },
    };
}

/**
 * 计算 BP (Book/Price = 1/PB)
 * 越高表示越便宜
 */
export async function calculateBP(code: string): Promise<FactorCalculationResult> {
    const valuation = await getValuationData(code);

    if (!valuation) {
        return { success: false, error: `无法获取 ${code} 的估值数据` };
    }

    if (!isValidNumber(valuation.pb) || valuation.pb <= 0) {
        return { success: false, error: `${code} 的 PB 数据无效或为负` };
    }

    const bp = 1 / valuation.pb;

    return {
        success: true,
        data: {
            code,
            factorName: 'bp',
            value: Number(bp.toFixed(6)),
            date: valuation.timestamp?.slice(0, 10) || getTodayDate(),
            dataSource: 'calculated',
            components: { pb: valuation.pb },
        },
    };
}

// ========== 成长因子 ==========

/**
 * 计算营收增长率因子
 */
export async function calculateRevenueGrowth(code: string): Promise<FactorCalculationResult> {
    const financial = await getLatestFinancialData(code);

    if (!financial) {
        return { success: false, error: `无法获取 ${code} 的财务数据` };
    }

    if (!isValidNumber(financial.revenueGrowth)) {
        return { success: false, error: `${code} 的营收增长率数据无效` };
    }

    return {
        success: true,
        data: {
            code,
            factorName: 'revenue_growth',
            value: Number(financial.revenueGrowth.toFixed(4)),
            date: financial.reportPeriod,
            dataSource: 'database',
        },
    };
}

/**
 * 计算净利润增长率因子
 */
export async function calculateProfitGrowth(code: string): Promise<FactorCalculationResult> {
    const financial = await getLatestFinancialData(code);

    if (!financial) {
        return { success: false, error: `无法获取 ${code} 的财务数据` };
    }

    if (!isValidNumber(financial.profitGrowth)) {
        return { success: false, error: `${code} 的利润增长率数据无效` };
    }

    return {
        success: true,
        data: {
            code,
            factorName: 'profit_growth',
            value: Number(financial.profitGrowth.toFixed(4)),
            date: financial.reportPeriod,
            dataSource: 'database',
        },
    };
}

// ========== 动量因子 ==========

/**
 * 计算动量因子
 * @param months 回看月数（1/3/6/12）
 */
export async function calculateMomentum(code: string, months: number = 6): Promise<FactorCalculationResult> {
    // 估算交易日数（每月约21个交易日）
    const tradingDays = Math.min(months * 21 + 5, 260);
    const bars = await getDailyBars(code, tradingDays);

    if (bars.length < months * 15) {
        return {
            success: false,
            error: `${code} 的K线数据不足，需要至少 ${months * 15} 个交易日`
        };
    }

    // 计算区间收益率
    const targetDays = months * 21;
    const startIdx = Math.max(0, bars.length - targetDays);
    const startPrice = bars[startIdx].close;
    const endPrice = bars[bars.length - 1].close;

    if (startPrice <= 0) {
        return { success: false, error: `${code} 的起始价格无效` };
    }

    const momentum = (endPrice - startPrice) / startPrice;

    return {
        success: true,
        data: {
            code,
            factorName: `momentum_${months}m`,
            value: Number(momentum.toFixed(6)),
            date: bars[bars.length - 1].date,
            dataSource: 'calculated',
            components: {
                startPrice,
                endPrice,
                tradingDays: bars.length - startIdx,
            },
        },
    };
}

// ========== 质量因子 ==========

/**
 * 计算 ROE 因子
 */
export async function calculateROE(code: string): Promise<FactorCalculationResult> {
    const financial = await getLatestFinancialData(code);

    if (!financial) {
        return { success: false, error: `无法获取 ${code} 的财务数据` };
    }

    if (!isValidNumber(financial.roe)) {
        return { success: false, error: `${code} 的 ROE 数据无效` };
    }

    return {
        success: true,
        data: {
            code,
            factorName: 'roe',
            value: Number(financial.roe.toFixed(4)),
            date: financial.reportPeriod,
            dataSource: 'database',
        },
    };
}

/**
 * 计算毛利率因子
 */
export async function calculateGrossMargin(code: string): Promise<FactorCalculationResult> {
    const financial = await getLatestFinancialData(code);

    if (!financial) {
        return { success: false, error: `无法获取 ${code} 的财务数据` };
    }

    if (!isValidNumber(financial.grossMargin)) {
        return { success: false, error: `${code} 的毛利率数据无效` };
    }

    return {
        success: true,
        data: {
            code,
            factorName: 'gross_margin',
            value: Number(financial.grossMargin.toFixed(4)),
            date: financial.reportPeriod,
            dataSource: 'database',
        },
    };
}

/**
 * 计算净利率因子
 */
export async function calculateNetMargin(code: string): Promise<FactorCalculationResult> {
    const financial = await getLatestFinancialData(code);

    if (!financial) {
        return { success: false, error: `无法获取 ${code} 的财务数据` };
    }

    if (!isValidNumber(financial.netMargin)) {
        return { success: false, error: `${code} 的净利率数据无效` };
    }

    return {
        success: true,
        data: {
            code,
            factorName: 'net_margin',
            value: Number(financial.netMargin.toFixed(4)),
            date: financial.reportPeriod,
            dataSource: 'database',
        },
    };
}

// ========== 批量计算 ==========

/**
 * 支持的因子列表（24个因子 - 移除了需要额外数据的因子）
 */
export const SUPPORTED_FACTORS = [
    // 估值因子 (2个)
    'ep', 'bp',
    // 成长因子 (6个)
    'revenue_growth', 'profit_growth', 'asset_growth', 'cashflow_growth', 'eps_growth', 'operating_profit_growth',
    // 动量因子 (6个)
    'momentum_1m', 'momentum_3m', 'momentum_6m', 'momentum_12m', 'momentum_20d', 'momentum_60d',
    // 质量因子 (5个)
    'roe', 'gross_margin', 'net_margin', 'current_ratio', 'debt_ratio',
    // 波动率因子 (3个)
    'volatility', 'downside_volatility', 'max_drawdown',
    // 流动性因子 (2个)
    'avg_turnover', 'avg_amount',
] as const;

export type SupportedFactor = typeof SUPPORTED_FACTORS[number];

// 导入扩展因子
import * as ExtendedFactors from './factor-calculator-extended.js';

/**
 * 计算单个因子
 */
export async function calculateFactor(code: string, factorName: string): Promise<FactorCalculationResult> {
    switch (factorName.toLowerCase()) {
        // 估值因子
        case 'ep':
            return calculateEP(code);
        case 'bp':
            return calculateBP(code);

        // 成长因子
        case 'revenue_growth':
            return calculateRevenueGrowth(code);
        case 'profit_growth':
            return calculateProfitGrowth(code);
        case 'asset_growth':
            return ExtendedFactors.calculateAssetGrowth(code);
        case 'cashflow_growth':
            return ExtendedFactors.calculateCashFlowGrowth(code);
        case 'eps_growth':
            return ExtendedFactors.calculateEPSGrowth(code);
        case 'operating_profit_growth':
            return ExtendedFactors.calculateOperatingProfitGrowth(code);

        // 动量因子
        case 'momentum_1m':
            return calculateMomentum(code, 1);
        case 'momentum_3m':
            return calculateMomentum(code, 3);
        case 'momentum_6m':
            return calculateMomentum(code, 6);
        case 'momentum_12m':
            return calculateMomentum(code, 12);
        case 'momentum_20d':
            return ExtendedFactors.calculateMomentum20D(code);
        case 'momentum_60d':
            return ExtendedFactors.calculateMomentum60D(code);

        // 质量因子
        case 'roe':
            return calculateROE(code);
        case 'gross_margin':
            return calculateGrossMargin(code);
        case 'net_margin':
            return calculateNetMargin(code);
        case 'current_ratio':
            return ExtendedFactors.calculateCurrentRatio(code);
        case 'debt_ratio':
            return ExtendedFactors.calculateDebtRatio(code);

        // 波动率因子
        case 'volatility':
            return ExtendedFactors.calculateVolatility(code);
        case 'downside_volatility':
            return ExtendedFactors.calculateDownsideVolatility(code);
        case 'max_drawdown':
            return ExtendedFactors.calculateMaxDrawdown(code);

        // 流动性因子
        case 'avg_turnover':
            return ExtendedFactors.calculateAvgTurnover(code);
        case 'avg_amount':
            return ExtendedFactors.calculateAvgAmount(code);

        default:
            return {
                success: false,
                error: `不支持的因子类型: ${factorName}，支持的因子: ${SUPPORTED_FACTORS.join(', ')}`
            };
    }
}

/**
 * 批量计算因子
 */
export async function batchCalculateFactors(
    codes: string[],
    factorName: string
): Promise<BatchFactorResult> {
    const factors: FactorValue[] = [];
    const errors: Array<{ code: string; error: string }> = [];

    for (const code of codes) {
        const result = await calculateFactor(code, factorName);
        if (result.success && result.data) {
            factors.push(result.data);
        } else {
            errors.push({ code, error: result.error || '未知错误' });
        }
    }

    return {
        success: true,
        factors,
        errors,
    };
}

/**
 * 计算多个因子
 */
export async function calculateMultipleFactors(
    code: string,
    factorNames: string[]
): Promise<{ code: string; factors: Record<string, number | null>; errors: string[] }> {
    const factors: Record<string, number | null> = {};
    const errors: string[] = [];

    for (const factorName of factorNames) {
        const result = await calculateFactor(code, factorName);
        if (result.success && result.data) {
            factors[factorName] = result.data.value;
        } else {
            factors[factorName] = null;
            errors.push(result.error || `计算 ${factorName} 失败`);
        }
    }

    return { code, factors, errors };
}
