/**
 * 因子分析服务
 * 
 * 提供高级因子分析功能：
 * - 因子正交化（Gram-Schmidt）
 * - 因子IC分析
 * - 因子衰减分析
 * - 因子相关性分析
 */

import { calculateFactor, SUPPORTED_FACTORS, type SupportedFactor } from './factor-calculator.js';
import { getDailyBarsByDateRange } from '../storage/kline-data.js';

// ========== 类型定义 ==========

export interface FactorMatrix {
    stocks: string[];
    factors: string[];
    values: number[][]; // [stock][factor]
    date: string;
}

export interface OrthogonalizedFactors {
    original: FactorMatrix;
    orthogonalized: FactorMatrix;
    transformMatrix: number[][]; // 正交化变换矩阵
}

export interface ICResult {
    factorName: string;
    ic: number;              // 信息系数（Spearman相关系数）
    icMean: number;          // IC均值
    icStd: number;           // IC标准差
    icIR: number;            // IC信息比率 (IC均值 / IC标准差)
    tStat: number;           // t统计量
    pValue: number;          // p值
    significantDays: number; // 显著天数（|IC| > 0.02）
}

export interface FactorDecayAnalysis {
    factorName: string;
    horizons: number[];      // 持有期（天）
    icByHorizon: number[];   // 各持有期的IC
    decayRate: number;       // 衰减率
    halfLife: number;        // 半衰期（天）
}

export interface FactorCorrelation {
    factors: string[];
    correlationMatrix: number[][];
    highlyCorrelated: Array<{ factor1: string; factor2: string; correlation: number }>;
}

// ========== 辅助函数 ==========

/**
 * 计算向量点积
 */
function dotProduct(a: number[], b: number[]): number {
    return a.reduce((sum, val, i) => sum + val * b[i], 0);
}

/**
 * 计算向量范数
 */
function norm(v: number[]): number {
    return Math.sqrt(dotProduct(v, v));
}

/**
 * 向量标准化
 */
function normalize(v: number[]): number[] {
    const n = norm(v);
    return n > 0 ? v.map((x: any) => x / n) : v;
}

/**
 * 向量减法
 */
function subtract(a: number[], b: number[]): number[] {
    return a.map((val, i) => val - b[i]);
}

/**
 * 向量数乘
 */
function scale(v: number[], scalar: number): number[] {
    return v.map((x: any) => x * scalar);
}

/**
 * 计算Spearman秩相关系数
 */
function spearmanCorrelation(x: number[], y: number[]): number {
    if (x.length !== y.length || x.length === 0) return 0;

    // 计算秩
    const rankX = getRanks(x);
    const rankY = getRanks(y);

    // 计算Pearson相关系数（对秩）
    return pearsonCorrelation(rankX, rankY);
}

/**
 * 获取秩
 */
function getRanks(arr: number[]): number[] {
    const indexed = arr.map((val, idx) => ({ val, idx }));
    indexed.sort((a: any, b: any) => a.val - b.val);

    const ranks = new Array(arr.length);
    for (let i = 0; i < indexed.length; i++) {
        ranks[indexed[i].idx] = i + 1;
    }

    return ranks;
}

/**
 * 计算Pearson相关系数
 */
function pearsonCorrelation(x: number[], y: number[]): number {
    if (x.length !== y.length || x.length === 0) return 0;

    const n = x.length;
    const meanX = x.reduce((a: any, b: any) => a + b, 0) / n;
    const meanY = y.reduce((a: any, b: any) => a + b, 0) / n;

    let numerator = 0;
    let denomX = 0;
    let denomY = 0;

    for (let i = 0; i < n; i++) {
        const dx = x[i] - meanX;
        const dy = y[i] - meanY;
        numerator += dx * dy;
        denomX += dx * dx;
        denomY += dy * dy;
    }

    const denom = Math.sqrt(denomX * denomY);
    return denom > 0 ? numerator / denom : 0;
}

// ========== 因子矩阵构建 ==========

/**
 * 构建因子矩阵
 */
export async function buildFactorMatrix(
    stocks: string[],
    factors: string[],
    date?: string
): Promise<FactorMatrix | { error: string }> {
    if (stocks.length === 0) {
        return { error: '股票列表为空' };
    }

    if (factors.length === 0) {
        return { error: '因子列表为空' };
    }

    const values: number[][] = [];
    const validStocks: string[] = [];

    for (const stock of stocks) {
        const factorValues: number[] = [];
        let allValid = true;

        for (const factor of factors) {
            const result = await calculateFactor(stock, factor);
            if (result.success && result.data) {
                factorValues.push(result.data.value);
            } else {
                allValid = false;
                break;
            }
        }

        if (allValid) {
            values.push(factorValues);
            validStocks.push(stock);
        }
    }

    if (validStocks.length === 0) {
        return { error: '没有有效的因子数据' };
    }

    return {
        stocks: validStocks,
        factors,
        values,
        date: date || new Date().toISOString().slice(0, 10)
    };
}

// ========== Gram-Schmidt 正交化 ==========

/**
 * Gram-Schmidt 正交化
 * 将因子向量组正交化，去除因子间的相关性
 */
export function orthogonalizeFactors(matrix: FactorMatrix): OrthogonalizedFactors {
    const { stocks, factors, values } = matrix;
    const n = stocks.length;
    const m = factors.length;

    // 转置矩阵：从 [stock][factor] 转为 [factor][stock]
    const factorVectors: number[][] = [];
    for (let j = 0; j < m; j++) {
        const vector: number[] = [];
        for (let i = 0; i < n; i++) {
            vector.push(values[i][j]);
        }
        factorVectors.push(vector);
    }

    // Gram-Schmidt 正交化
    const orthogonalVectors: number[][] = [];
    const transformMatrix: number[][] = Array(m).fill(0).map(() => Array(m).fill(0));

    for (let i = 0; i < m; i++) {
        let u = [...factorVectors[i]];

        // 减去在之前所有正交向量上的投影
        for (let j = 0; j < i; j++) {
            const projection = dotProduct(factorVectors[i], orthogonalVectors[j]);
            u = subtract(u, scale(orthogonalVectors[j], projection));
        }

        // 标准化
        const normalized = normalize(u);
        orthogonalVectors.push(normalized);

        // 记录变换矩阵
        for (let j = 0; j <= i; j++) {
            transformMatrix[i][j] = dotProduct(factorVectors[i], orthogonalVectors[j]);
        }
    }

    // 转置回 [stock][factor]
    const orthogonalizedValues: number[][] = [];
    for (let i = 0; i < n; i++) {
        const row: number[] = [];
        for (let j = 0; j < m; j++) {
            row.push(orthogonalVectors[j][i]);
        }
        orthogonalizedValues.push(row);
    }

    return {
        original: matrix,
        orthogonalized: {
            stocks,
            factors: factors.map((f, i) => `${f}_orth`),
            values: orthogonalizedValues,
            date: matrix.date
        },
        transformMatrix
    };
}

// ========== IC 分析 ==========

/**
 * 计算因子IC（Information Coefficient）
 * IC = Spearman相关系数（因子值，未来收益率）
 */
export async function calculateFactorIC(
    stocks: string[],
    factorName: string,
    startDate: string,
    endDate: string,
    horizon: number = 1 // 持有期（天）
): Promise<ICResult | { error: string }> {
    if (stocks.length < 10) {
        return { error: '股票数量不足（至少需要10只）' };
    }

    // 获取日期序列
    const dates = await getDateRange(startDate, endDate);
    if (dates.length < 20) {
        return { error: '日期范围不足（至少需要20个交易日）' };
    }

    const icValues: number[] = [];

    for (let i = 0; i < dates.length - horizon; i++) {
        const currentDate = dates[i];
        const futureDate = dates[i + horizon];

        // 计算当日因子值
        const factorValues: number[] = [];
        const futureReturns: number[] = [];
        const validStocks: string[] = [];

        for (const stock of stocks) {
            // 获取因子值
            const factorResult = await calculateFactor(stock, factorName);
            if (!factorResult.success || !factorResult.data) continue;

            // 获取未来收益率
            const currentBars = await getDailyBarsByDateRange(stock, currentDate, currentDate);
            const futureBars = await getDailyBarsByDateRange(stock, futureDate, futureDate);

            if (currentBars.length > 0 && futureBars.length > 0) {
                const currentPrice = currentBars[0].close;
                const futurePrice = futureBars[0].close;
                const ret = (futurePrice - currentPrice) / currentPrice;

                factorValues.push(factorResult.data.value);
                futureReturns.push(ret);
                validStocks.push(stock);
            }
        }

        // 计算IC
        if (validStocks.length >= 10) {
            const ic = spearmanCorrelation(factorValues, futureReturns);
            icValues.push(ic);
        }
    }

    if (icValues.length === 0) {
        return { error: '无法计算IC，数据不足' };
    }

    // 统计分析
    const icMean = icValues.reduce((a: any, b: any) => a + b, 0) / icValues.length;
    const icVariance = icValues.reduce((a: any, b: any) => a + Math.pow(b - icMean, 2), 0) / icValues.length;
    const icStd = Math.sqrt(icVariance);
    const icIR = icStd > 0 ? icMean / icStd : 0;

    // t检验
    const n = icValues.length;
    const tStat = icStd > 0 ? (icMean * Math.sqrt(n)) / icStd : 0;
    const pValue = calculatePValue(tStat, n - 1);

    // 显著天数
    const significantDays = icValues.filter(ic => Math.abs(ic) > 0.02).length;

    return {
        factorName,
        ic: icValues[icValues.length - 1], // 最新IC
        icMean: Number(icMean.toFixed(4)),
        icStd: Number(icStd.toFixed(4)),
        icIR: Number(icIR.toFixed(4)),
        tStat: Number(tStat.toFixed(4)),
        pValue: Number(pValue.toFixed(4)),
        significantDays
    };
}

/**
 * 计算p值（简化版，使用正态近似）
 */
function calculatePValue(tStat: number, df: number): number {
    // 简化：使用标准正态分布近似
    const z = Math.abs(tStat);
    const p = 2 * (1 - normalCDF(z));
    return Math.max(0, Math.min(1, p));
}

/**
 * 标准正态分布累积分布函数（近似）
 */
function normalCDF(x: number): number {
    const t = 1 / (1 + 0.2316419 * Math.abs(x));
    const d = 0.3989423 * Math.exp(-x * x / 2);
    const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
    return x > 0 ? 1 - p : p;
}

/**
 * 获取日期范围
 */
async function getDateRange(startDate: string, endDate: string): Promise<string[]> {
    // 简化实现：使用任意股票的K线数据获取交易日
    const sampleStock = '000001';
    const bars = await getDailyBarsByDateRange(sampleStock, startDate, endDate);
    return bars.map((b: any) => b.date);
}

// ========== 因子衰减分析 ==========

/**
 * 因子衰减分析
 * 分析因子在不同持有期下的预测能力
 */
export async function analyzeFactorDecay(
    stocks: string[],
    factorName: string,
    startDate: string,
    endDate: string,
    horizons: number[] = [1, 5, 10, 20, 60] // 持有期（天）
): Promise<FactorDecayAnalysis | { error: string }> {
    const icByHorizon: number[] = [];

    for (const horizon of horizons) {
        const icResult = await calculateFactorIC(stocks, factorName, startDate, endDate, horizon);
        if ('error' in icResult) {
            return icResult;
        }
        icByHorizon.push(icResult.icMean);
    }

    // 计算衰减率（线性拟合）
    let sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
    const n = horizons.length;

    for (let i = 0; i < n; i++) {
        sumX += horizons[i];
        sumY += icByHorizon[i];
        sumXY += horizons[i] * icByHorizon[i];
        sumX2 += horizons[i] * horizons[i];
    }

    const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
    const decayRate = -slope; // 负斜率表示衰减

    // 计算半衰期（IC降至初始值的50%所需天数）
    const initialIC = icByHorizon[0];
    const halfLife = initialIC !== 0 && decayRate > 0 ? (initialIC * 0.5) / decayRate : Infinity;

    return {
        factorName,
        horizons,
        icByHorizon: icByHorizon.map(ic => Number(ic.toFixed(4))),
        decayRate: Number(decayRate.toFixed(6)),
        halfLife: Number.isFinite(halfLife) ? Number(halfLife.toFixed(2)) : Infinity
    };
}

// ========== 因子相关性分析 ==========

/**
 * 计算因子相关性矩阵
 */
export async function calculateFactorCorrelation(
    stocks: string[],
    factors: string[],
    threshold: number = 0.7 // 高相关性阈值
): Promise<FactorCorrelation | { error: string }> {
    // 构建因子矩阵
    const matrixResult = await buildFactorMatrix(stocks, factors);
    if ('error' in matrixResult) {
        return matrixResult;
    }

    const { values } = matrixResult;
    const m = factors.length;

    // 计算相关性矩阵
    const correlationMatrix: number[][] = Array(m).fill(0).map(() => Array(m).fill(0));

    for (let i = 0; i < m; i++) {
        for (let j = 0; j < m; j++) {
            if (i === j) {
                correlationMatrix[i][j] = 1.0;
            } else {
                const factorI = values.map(row => row[i]);
                const factorJ = values.map(row => row[j]);
                correlationMatrix[i][j] = pearsonCorrelation(factorI, factorJ);
            }
        }
    }

    // 找出高相关性因子对
    const highlyCorrelated: Array<{ factor1: string; factor2: string; correlation: number }> = [];

    for (let i = 0; i < m; i++) {
        for (let j = i + 1; j < m; j++) {
            const corr = Math.abs(correlationMatrix[i][j]);
            if (corr >= threshold) {
                highlyCorrelated.push({
                    factor1: factors[i],
                    factor2: factors[j],
                    correlation: Number(correlationMatrix[i][j].toFixed(4))
                });
            }
        }
    }

    // 按相关性降序排序
    highlyCorrelated.sort((a: any, b: any) => Math.abs(b.correlation) - Math.abs(a.correlation));

    return {
        factors,
        correlationMatrix: correlationMatrix.map(row => row.map(val => Number(val.toFixed(4)))),
        highlyCorrelated
    };
}

// ========== 批量因子分析 ==========

/**
 * 批量计算所有因子的IC
 */
export async function batchCalculateFactorIC(
    stocks: string[],
    factors: string[],
    startDate: string,
    endDate: string,
    horizon: number = 1
): Promise<{ results: ICResult[]; summary: { avgIC: number; avgIR: number; significantFactors: number } } | { error: string }> {
    const results: ICResult[] = [];

    for (const factor of factors) {
        const icResult = await calculateFactorIC(stocks, factor, startDate, endDate, horizon);
        if ('error' in icResult) {
            console.warn(`Failed to calculate IC for ${factor}: ${icResult.error}`);
            continue;
        }
        results.push(icResult);
    }

    if (results.length === 0) {
        return { error: '无法计算任何因子的IC' };
    }

    // 汇总统计
    const avgIC = results.reduce((sum, r) => sum + Math.abs(r.icMean), 0) / results.length;
    const avgIR = results.reduce((sum, r) => sum + Math.abs(r.icIR), 0) / results.length;
    const significantFactors = results.filter((r: any) => r.pValue < 0.05).length;

    return {
        results,
        summary: {
            avgIC: Number(avgIC.toFixed(4)),
            avgIR: Number(avgIR.toFixed(4)),
            significantFactors
        }
    };
}
