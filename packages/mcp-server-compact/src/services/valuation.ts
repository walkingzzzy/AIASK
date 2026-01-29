/**
 * 估值计算服务
 * DCF、健康度评分等
 */

import type { FinancialData, HealthScore, ValuationMetrics } from '../types/stock.js';
import { HEALTH_SCORE_WEIGHTS } from '../config/constants.js';

/**
 * 计算健康度评分
 */
export function calculateHealthScore(
    financials: FinancialData,
    valuation: ValuationMetrics,
    customWeights?: Partial<typeof HEALTH_SCORE_WEIGHTS>
): HealthScore {
    const weights = { ...HEALTH_SCORE_WEIGHTS, ...customWeights };

    // 盈利能力评分 (0-100)
    const profitabilityScore = calculateProfitabilityScore(financials);

    // 流动性评分 (0-100)
    const liquidityScore = calculateLiquidityScore(financials);

    // 杠杆率评分 (0-100)
    const leverageScore = calculateLeverageScore(financials);

    // 运营效率评分 (0-100)
    const efficiencyScore = calculateEfficiencyScore(financials);

    // 成长性评分 (0-100)
    const growthScore = calculateGrowthScore(financials, valuation);

    const totalScore =
        profitabilityScore * weights.profitability +
        liquidityScore * weights.liquidity +
        leverageScore * weights.leverage +
        efficiencyScore * weights.efficiency +
        growthScore * weights.growth;

    let level: HealthScore['level'];
    if (totalScore >= 80) level = 'excellent';
    else if (totalScore >= 65) level = 'good';
    else if (totalScore >= 50) level = 'fair';
    else if (totalScore >= 35) level = 'poor';
    else level = 'critical';

    return {
        code: financials.code,
        totalScore: Math.round(totalScore),
        dimensions: {
            profitability: Math.round(profitabilityScore),
            liquidity: Math.round(liquidityScore),
            leverage: Math.round(leverageScore),
            efficiency: Math.round(efficiencyScore),
            growth: Math.round(growthScore),
        },
        level,
    };
}

/**
 * 盈利能力评分
 */
function calculateProfitabilityScore(financials: FinancialData): number {
    let score = 50; // 基础分
    const roe = financials.roe ?? 0;
    const netProfitMargin = financials.netProfitMargin ?? 0;
    const roa = financials.roa ?? 0;

    // ROE 评分 (15% 以上优秀)
    if (roe > 20) score += 25;
    else if (roe > 15) score += 20;
    else if (roe > 10) score += 10;
    else if (roe < 5) score -= 10;

    // 净利率评分
    if (netProfitMargin > 20) score += 15;
    else if (netProfitMargin > 10) score += 10;
    else if (netProfitMargin > 5) score += 5;
    else if (netProfitMargin < 0) score -= 20;

    // ROA 评分
    if (roa > 10) score += 10;
    else if (roa > 5) score += 5;

    return Math.max(0, Math.min(100, score));
}

/**
 * 流动性评分
 */
function calculateLiquidityScore(financials: FinancialData): number {
    let score = 50;
    const currentRatio = financials.currentRatio ?? 0;

    // 流动比率评分 (2左右最佳)
    if (currentRatio >= 2 && currentRatio <= 3) score += 30;
    else if (currentRatio >= 1.5) score += 20;
    else if (currentRatio >= 1) score += 10;
    else score -= 20;

    return Math.max(0, Math.min(100, score));
}

/**
 * 杠杆率评分 (低负债得高分)
 */
function calculateLeverageScore(financials: FinancialData): number {
    let score = 50;
    const debtRatio = financials.debtRatio ?? 0;

    // 资产负债率评分 (低于50%较好)
    if (debtRatio < 30) score += 30;
    else if (debtRatio < 50) score += 20;
    else if (debtRatio < 70) score += 0;
    else score -= 20;

    return Math.max(0, Math.min(100, score));
}

/**
 * 运营效率评分
 */
function calculateEfficiencyScore(financials: FinancialData): number {
    let score = 50;
    const grossProfitMargin = financials.grossProfitMargin ?? 0;

    // 毛利率评分
    if (grossProfitMargin > 40) score += 25;
    else if (grossProfitMargin > 30) score += 15;
    else if (grossProfitMargin > 20) score += 5;
    else if (grossProfitMargin < 10) score -= 10;

    return Math.max(0, Math.min(100, score));
}

/**
 * 成长性评分
 */
function calculateGrowthScore(_financials: FinancialData, valuation: ValuationMetrics): number {
    let score = 50;

    // PE估值合理性
    if (valuation.pe > 0 && valuation.pe < 15) score += 15;
    else if (valuation.pe >= 15 && valuation.pe < 30) score += 10;
    else if (valuation.pe >= 50) score -= 15;

    // PB估值
    if (valuation.pb > 0 && valuation.pb < 2) score += 10;
    else if (valuation.pb >= 5) score -= 10;

    return Math.max(0, Math.min(100, score));
}

/**
 * 简化的 DCF 估值
 */
export function calculateDCF(
    freeCashFlow: number,
    growthRate: number,
    discountRate: number,
    terminalGrowthRate: number = 0.02,
    years: number = 5
): {
    intrinsicValue: number;
    presentValues: number[];
    terminalValue: number;
} {
    const presentValues: number[] = [];
    let totalPV = 0;

    // 计算预测期现值
    for (let i = 1; i <= years; i++) {
        const fcf = freeCashFlow * Math.pow(1 + growthRate, i);
        const pv = fcf / Math.pow(1 + discountRate, i);
        presentValues.push(pv);
        totalPV += pv;
    }

    // 计算终值
    const terminalFCF = freeCashFlow * Math.pow(1 + growthRate, years) * (1 + terminalGrowthRate);
    const terminalValue = terminalFCF / (discountRate - terminalGrowthRate);
    const terminalPV = terminalValue / Math.pow(1 + discountRate, years);

    return {
        intrinsicValue: totalPV + terminalPV,
        presentValues,
        terminalValue: terminalPV,
    };
}

/**
 * PE 估值对比
 */
export function compareValuations(
    stocks: Array<{ code: string; pe: number; pb: number; roe: number; growth: number }>
): Array<{
    code: string;
    peg: number;
    pbRoe: number;
    rank: number;
    assessment: 'undervalued' | 'fair' | 'overvalued';
}> {
    const results = stocks.map(stock => {
        // PEG = PE / 增长率
        const peg = stock.growth > 0 ? stock.pe / stock.growth : 999;

        // PB/ROE 比值
        const pbRoe = stock.roe > 0 ? stock.pb / stock.roe * 100 : 999;

        let assessment: 'undervalued' | 'fair' | 'overvalued';
        if (peg < 1 && pbRoe < 0.1) assessment = 'undervalued';
        else if (peg > 2 || pbRoe > 0.3) assessment = 'overvalued';
        else assessment = 'fair';

        return { code: stock.code, peg, pbRoe, rank: 0, assessment };
    });

    // 按 PEG 排序
    results.sort((a: any, b: any) => a.peg - b.peg);
    results.forEach((r, i) => { r.rank = i + 1; });

    return results;
}
