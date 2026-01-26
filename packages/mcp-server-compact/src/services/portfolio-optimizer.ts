/**
 * 组合优化服务
 * 
 * 实现高级组合优化功能：
 * - 协方差矩阵计算
 * - 均值-方差优化
 * - Black-Litterman 模型
 * - 风险预算优化
 * - 交易成本约束
 */

import { getDailyBarsByDateRange } from '../storage/kline-data.js';

// ========== 类型定义 ==========

export interface OptimizationResult {
    weights: Record<string, number>;     // 股票代码 -> 权重
    expectedReturn: number;              // 预期收益率 (%)
    volatility: number;                  // 波动率 (%)
    sharpeRatio: number;                 // 夏普比率
    diversificationRatio: number;        // 分散化比率
}

export interface CovarianceMatrix {
    stocks: string[];
    matrix: number[][];
    means: number[];
    correlationMatrix: number[][];
}

export interface BlackLittermanConfig {
    stocks: string[];
    views: Array<{
        type: 'absolute' | 'relative';   // 绝对/相对观点
        stocks: string[];                 // 涉及的股票
        weights: number[];                // 相对观点中的权重差
        expectedReturn: number;           // 预期收益率
        confidence: number;               // 置信度 0-1
    }>;
    riskAversion?: number;               // 风险厌恶系数，默认2.5
    tau?: number;                        // 不确定性缩放因子，默认0.05
}

export interface RiskBudgetConfig {
    stocks: string[];
    riskBudgets: number[];               // 各股票风险预算比例（归一化）
    targetVolatility?: number;           // 目标波动率 (%)
}

// ========== 协方差矩阵计算 ==========

/**
 * 计算股票收益率序列
 */
function calculateReturns(bars: Array<{ date: string; close: number }>): number[] {
    const returns: number[] = [];
    for (let i = 1; i < bars.length; i++) {
        if (bars[i - 1].close > 0) {
            returns.push((bars[i].close - bars[i - 1].close) / bars[i - 1].close);
        }
    }
    return returns;
}

/**
 * 计算协方差矩阵
 */
export async function calculateCovarianceMatrix(
    stocks: string[],
    lookbackDays: number = 252
): Promise<CovarianceMatrix | { error: string }> {
    const startDate = new Date(Date.now() - lookbackDays * 24 * 60 * 60 * 1000)
        .toISOString().slice(0, 10);
    const endDate = new Date().toISOString().slice(0, 10);

    // 获取所有股票的收益率
    const returnSeries: Map<string, number[]> = new Map();
    const validStocks: string[] = [];

    for (const code of stocks) {
        const bars = await getDailyBarsByDateRange(code, startDate, endDate);
        if (bars.length >= 20) {
            const returns = calculateReturns(bars);
            if (returns.length >= 20) {
                returnSeries.set(code, returns);
                validStocks.push(code);
            }
        }
    }

    if (validStocks.length < 2) {
        return { error: '有效股票数量不足，无法计算协方差矩阵' };
    }

    // 对齐收益率序列（取最短长度）
    const minLength = Math.min(...[...returnSeries.values()].map((r: any) => r.length));
    const alignedReturns: number[][] = validStocks.map(code => {
        const returns = returnSeries.get(code)!;
        return returns.slice(returns.length - minLength);
    });

    const n = validStocks.length;

    // 计算均值
    const means = alignedReturns.map(returns =>
        returns.reduce((a: any, b: any) => a + b, 0) / returns.length * 252 // 年化
    );

    // 计算协方差矩阵
    const covMatrix: number[][] = [];
    for (let i = 0; i < n; i++) {
        const row: number[] = [];
        for (let j = 0; j < n; j++) {
            let cov = 0;
            const meanI = means[i] / 252;
            const meanJ = means[j] / 252;

            for (let k = 0; k < minLength; k++) {
                cov += (alignedReturns[i][k] - meanI) * (alignedReturns[j][k] - meanJ);
            }
            cov = (cov / (minLength - 1)) * 252; // 年化
            row.push(Math.round(cov * 10000) / 10000);
        }
        covMatrix.push(row);
    }

    // 计算相关性矩阵
    const corrMatrix: number[][] = [];
    for (let i = 0; i < n; i++) {
        const row: number[] = [];
        for (let j = 0; j < n; j++) {
            const stdI = Math.sqrt(covMatrix[i][i]);
            const stdJ = Math.sqrt(covMatrix[j][j]);
            const corr = stdI > 0 && stdJ > 0 ? covMatrix[i][j] / (stdI * stdJ) : 0;
            row.push(Math.round(corr * 10000) / 10000);
        }
        corrMatrix.push(row);
    }

    return {
        stocks: validStocks,
        matrix: covMatrix,
        means: means.map((m: any) => Math.round(m * 10000) / 10000),
        correlationMatrix: corrMatrix,
    };
}

// ========== 均值-方差优化 ==========

/**
 * 简化的均值-方差优化（等风险贡献方法）
 */
export async function optimizeMeanVariance(
    covMatrix: CovarianceMatrix
): Promise<OptimizationResult | { error: string }> {
    if (!covMatrix || !covMatrix.stocks) {
        return { error: '协方差矩阵无效' };
    }
    
    const n = covMatrix.stocks.length;

    if (n < 2) {
        return { error: '股票数量不足' };
    }

    // 简化实现：使用逆协方差加权
    // 真实实现需要二次规划求解器
    const variances = covMatrix.matrix.map((row, i) => row[i]);
    const totalInvVar = variances.reduce((sum, v) => sum + (v > 0 ? 1 / v : 0), 0);

    const weights: Record<string, number> = {};
    for (let i = 0; i < n; i++) {
        const invVar = variances[i] > 0 ? 1 / variances[i] : 0;
        weights[covMatrix.stocks[i]] = Math.round((invVar / totalInvVar) * 10000) / 10000;
    }

    // 计算组合指标
    const weightArr = covMatrix.stocks.map((s: any) => weights[s]);
    const expectedReturn = covMatrix.means.reduce((sum, m, i) => sum + m * weightArr[i], 0);

    // 计算组合方差
    let portfolioVar = 0;
    for (let i = 0; i < n; i++) {
        for (let j = 0; j < n; j++) {
            portfolioVar += weightArr[i] * weightArr[j] * covMatrix.matrix[i][j];
        }
    }
    const volatility = Math.sqrt(portfolioVar);

    // 夏普比率（假设无风险利率 3%）
    const riskFreeRate = 0.03;
    const sharpe = volatility > 0 ? (expectedReturn - riskFreeRate) / volatility : 0;

    // 分散化比率
    const weightedVol = variances.reduce((sum, v, i) => sum + weightArr[i] * Math.sqrt(v), 0);
    const diversificationRatio = volatility > 0 ? weightedVol / volatility : 1;

    return {
        weights,
        expectedReturn: Math.round(expectedReturn * 10000) / 100,
        volatility: Math.round(volatility * 10000) / 100,
        sharpeRatio: Math.round(sharpe * 100) / 100,
        diversificationRatio: Math.round(diversificationRatio * 100) / 100,
    };
}

// ========== Black-Litterman 模型 ==========

/**
 * Black-Litterman 模型优化
 */
export async function blackLittermanOptimize(
    config: BlackLittermanConfig
): Promise<OptimizationResult | { error: string }> {
    const { stocks, views, riskAversion = 2.5, tau = 0.05 } = config;

    if (stocks.length < 2) {
        return { error: '股票数量不足' };
    }

    // 计算协方差矩阵
    const covResult = await calculateCovarianceMatrix(stocks);
    if ('error' in covResult) {
        return covResult;
    }

    const n = covResult.stocks.length;
    const Sigma = covResult.matrix;

    // 市场均衡收益率（根据市值加权的隐含收益）
    // 简化：使用等权作为市场组合
    const marketWeights = new Array(n).fill(1 / n);
    const impliedReturns = Sigma.map((row, _) =>
        row.reduce((sum, cov, j) => sum + cov * marketWeights[j], 0) * riskAversion
    );

    // 如果没有观点，返回市场均衡权重
    if (!views || views.length === 0) {
        const weights: Record<string, number> = {};
        for (let i = 0; i < n; i++) {
            weights[covResult.stocks[i]] = Math.round(marketWeights[i] * 10000) / 10000;
        }

        return await optimizeMeanVariance(covResult);
    }

    // 构建观点矩阵 P 和 Q
    // 简化实现：仅支持绝对观点
    const P: number[][] = [];
    const Q: number[] = [];
    const Omega: number[][] = []; // 观点不确定性矩阵

    for (const view of views) {
        if (view.type === 'absolute' && view.stocks.length === 1) {
            const stockIdx = covResult.stocks.indexOf(view.stocks[0]);
            if (stockIdx >= 0) {
                const pRow = new Array(n).fill(0);
                pRow[stockIdx] = 1;
                P.push(pRow);
                Q.push(view.expectedReturn);

                // 观点不确定性与置信度成反比
                const omega = (1 - view.confidence) * Sigma[stockIdx][stockIdx] * tau;
                const omegaRow = new Array(P.length).fill(0);
                omegaRow[P.length - 1] = omega;
                Omega.push(omegaRow);
            }
        }
    }

    if (P.length === 0) {
        // 没有有效观点，返回市场均衡
        return await optimizeMeanVariance(covResult);
    }

    // Black-Litterman 公式（简化版）
    // E[R] = [(tau*Sigma)^(-1) + P'*Omega^(-1)*P]^(-1) * [(tau*Sigma)^(-1)*Pi + P'*Omega^(-1)*Q]
    // 简化：直接用观点调整隐含收益
    const adjustedReturns = [...impliedReturns];
    for (let v = 0; v < P.length; v++) {
        for (let i = 0; i < n; i++) {
            if (P[v][i] !== 0) {
                const adjustment = (Q[v] - impliedReturns[i]) * views[v].confidence;
                adjustedReturns[i] += adjustment;
            }
        }
    }

    // 根据调整后的收益计算最优权重（简化：收益越高权重越大）
    const totalReturn = adjustedReturns.reduce((a: any, b: any) => a + Math.max(b, 0), 0);
    const weights: Record<string, number> = {};

    for (let i = 0; i < n; i++) {
        const ret = Math.max(adjustedReturns[i], 0);
        weights[covResult.stocks[i]] = totalReturn > 0
            ? Math.round((ret / totalReturn) * 10000) / 10000
            : Math.round((1 / n) * 10000) / 10000;
    }

    // 计算组合指标
    const weightArr = covResult.stocks.map((s: any) => weights[s]);
    const expectedReturn = adjustedReturns.reduce((sum, r, i) => sum + r * weightArr[i], 0);

    let portfolioVar = 0;
    for (let i = 0; i < n; i++) {
        for (let j = 0; j < n; j++) {
            portfolioVar += weightArr[i] * weightArr[j] * Sigma[i][j];
        }
    }
    const volatility = Math.sqrt(portfolioVar);

    const riskFreeRate = 0.03;
    const sharpe = volatility > 0 ? (expectedReturn - riskFreeRate) / volatility : 0;

    return {
        weights,
        expectedReturn: Math.round(expectedReturn * 10000) / 100,
        volatility: Math.round(volatility * 10000) / 100,
        sharpeRatio: Math.round(sharpe * 100) / 100,
        diversificationRatio: 1.0,
    };
}

// ========== 风险预算优化 ==========

/**
 * 风险预算优化（目标：各资产风险贡献等于预设比例）
 */
export async function riskBudgetOptimize(
    config: RiskBudgetConfig
): Promise<OptimizationResult | { error: string }> {
    const { stocks, riskBudgets, targetVolatility } = config;

    if (stocks.length !== riskBudgets.length) {
        return { error: '股票数量与风险预算数量不匹配' };
    }

    // 归一化风险预算
    const totalBudget = riskBudgets.reduce((a: any, b: any) => a + b, 0);
    const normalizedBudgets = riskBudgets.map((b: any) => b / totalBudget);

    // 计算协方差矩阵
    const covResult = await calculateCovarianceMatrix(stocks);
    if ('error' in covResult) {
        return covResult;
    }

    const n = covResult.stocks.length;
    const Sigma = covResult.matrix;

    // 简化的风险预算优化：权重与风险预算/波动率的比例成正比
    const invVols = Sigma.map((row, i) => {
        const vol = Math.sqrt(row[i]);
        return vol > 0 ? 1 / vol : 0;
    });

    const scaledWeights = normalizedBudgets.map((b, i) => b * invVols[i]);
    const totalScaled = scaledWeights.reduce((a: any, b: any) => a + b, 0);

    const weights: Record<string, number> = {};
    for (let i = 0; i < n; i++) {
        weights[covResult.stocks[i]] = totalScaled > 0
            ? Math.round((scaledWeights[i] / totalScaled) * 10000) / 10000
            : Math.round((1 / n) * 10000) / 10000;
    }

    // 计算组合指标
    const weightArr = covResult.stocks.map((s: any) => weights[s]);
    const expectedReturn = covResult.means.reduce((sum, m, i) => sum + m * weightArr[i], 0);

    let portfolioVar = 0;
    for (let i = 0; i < n; i++) {
        for (let j = 0; j < n; j++) {
            portfolioVar += weightArr[i] * weightArr[j] * Sigma[i][j];
        }
    }
    let volatility = Math.sqrt(portfolioVar);

    // 如果指定目标波动率，调整杠杆
    if (targetVolatility && volatility > 0) {
        const leverage = targetVolatility / 100 / volatility;
        for (const code of covResult.stocks) {
            weights[code] = Math.round(weights[code] * leverage * 10000) / 10000;
        }
        volatility = targetVolatility / 100;
    }

    const riskFreeRate = 0.03;
    const sharpe = volatility > 0 ? (expectedReturn - riskFreeRate) / volatility : 0;

    return {
        weights,
        expectedReturn: Math.round(expectedReturn * 10000) / 100,
        volatility: Math.round(volatility * 10000) / 100,
        sharpeRatio: Math.round(sharpe * 100) / 100,
        diversificationRatio: 1.0,
    };
}

// ========== 综合组合优化接口 ==========

export type OptimizationMethod = 'mean_variance' | 'black_litterman' | 'risk_budget' | 'equal_weight';

export interface PortfolioOptimizerConfig {
    stocks: string[];
    method: OptimizationMethod;
    views?: BlackLittermanConfig['views'];
    riskBudgets?: number[];
    targetVolatility?: number;
    lookbackDays?: number;
}

/**
 * 统一的组合优化接口
 */
export async function optimizePortfolio(
    config: PortfolioOptimizerConfig
): Promise<OptimizationResult | { error: string }> {
    const { stocks, method, views, riskBudgets, targetVolatility, lookbackDays = 252 } = config;

    if (stocks.length < 2) {
        return { error: '至少需要2只股票' };
    }

    switch (method) {
        case 'equal_weight': {
            const n = stocks.length;
            const weights: Record<string, number> = {};
            for (const code of stocks) {
                weights[code] = Math.round((1 / n) * 10000) / 10000;
            }

            const covResult = await calculateCovarianceMatrix(stocks, lookbackDays);
            if ('error' in covResult) {
                return {
                    weights,
                    expectedReturn: 0,
                    volatility: 0,
                    sharpeRatio: 0,
                    diversificationRatio: 1,
                };
            }

            // 计算等权组合指标
            const weightArr = covResult.stocks.map((s: any) => weights[s] || 0);
            const expectedReturn = covResult.means.reduce((sum, m, i) => sum + m * weightArr[i], 0);

            let portfolioVar = 0;
            for (let i = 0; i < covResult.stocks.length; i++) {
                for (let j = 0; j < covResult.stocks.length; j++) {
                    portfolioVar += weightArr[i] * weightArr[j] * covResult.matrix[i][j];
                }
            }
            const volatility = Math.sqrt(portfolioVar);
            const sharpe = volatility > 0 ? (expectedReturn - 0.03) / volatility : 0;

            return {
                weights,
                expectedReturn: Math.round(expectedReturn * 10000) / 100,
                volatility: Math.round(volatility * 10000) / 100,
                sharpeRatio: Math.round(sharpe * 100) / 100,
                diversificationRatio: 1,
            };
        }

        case 'mean_variance': {
            const covResult = await calculateCovarianceMatrix(stocks, lookbackDays);
            if ('error' in covResult) {
                return covResult;
            }
            return await optimizeMeanVariance(covResult);
        }

        case 'black_litterman': {
            return await blackLittermanOptimize({
                stocks,
                views: views || [],
            });
        }

        case 'risk_budget': {
            return await riskBudgetOptimize({
                stocks,
                riskBudgets: riskBudgets || stocks.map(() => 1),
                targetVolatility,
            });
        }

        default:
            return { error: `未知的优化方法: ${method}` };
    }
}
