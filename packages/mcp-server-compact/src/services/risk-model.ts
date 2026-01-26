/**
 * 风险建模服务
 * 
 * 实现高级风险分析功能：
 * - Barra 因子风险模型（简化版）
 * - 行业因子暴露分析
 * - VaR/CVaR 计算
 * - 压力测试框架
 */

import { getDailyBarsByDateRange } from '../storage/kline-data.js';
import { calculateCovarianceMatrix } from './portfolio-optimizer.js';
import { getIndustry } from '../config/industry-mapping.js';

// ========== 类型定义 ==========

export interface FactorExposure {
    factorName: string;
    exposure: number;           // 因子暴露度
    contribution: number;       // 对组合风险的贡献 (%)
}

export interface BarraRiskResult {
    totalRisk: number;          // 总风险（年化波动率 %）
    factorRisk: number;         // 因子风险 (%)
    specificRisk: number;       // 特质风险 (%)
    factorExposures: FactorExposure[];
    industryExposures: Record<string, number>;
}

export interface VaRResult {
    confidence: number;         // 置信水平 (%)
    horizon: number;            // 持有期（天）
    var: number;                // VaR（绝对值，元）
    varPercent: number;         // VaR（百分比 %）
    cvar: number;               // CVaR（条件VaR）
    cvarPercent: number;
}

export interface StressTestScenario {
    name: string;
    description: string;
    shocks: Record<string, number>;  // 因子 -> 冲击幅度 (%)
}

export interface StressTestResult {
    scenario: string;
    portfolioLoss: number;      // 组合损失 (%)
    worstStocks: Array<{ code: string; loss: number }>;
    factorContributions: Record<string, number>;
}

// ========== 预定义压力测试场景 ==========

export const STRESS_SCENARIOS: StressTestScenario[] = [
    // 原有场景 (4个)
    {
        name: '市场暴跌',
        description: '模拟2015年股灾情景，市场大幅下跌',
        shocks: { market: -20, volatility: 50 },
    },
    {
        name: '利率上行',
        description: '央行加息导致估值压缩',
        shocks: { rate: 100, value: -10, growth: -15 },
    },
    {
        name: '流动性危机',
        description: '信用收缩导致小盘股承压',
        shocks: { market: -10, size: -20, liquidity: -30 },
    },
    {
        name: '行业轮动',
        description: '科技股泡沫破裂',
        shocks: { technology: -30, financials: 5, consumer: 0 },
    },
    // 新增场景 (8个)
    {
        name: '黑天鹅事件',
        description: '极端市场崩盘，类似2008年金融危机',
        shocks: { market: -35, volatility: 100, liquidity: -50, financials: -40 },
    },
    {
        name: '通货膨胀',
        description: '高通胀环境，商品价格上涨',
        shocks: { market: -5, rate: 150, value: 10, growth: -20, consumer: -15 },
    },
    {
        name: '经济衰退',
        description: 'GDP增速放缓，企业盈利下降',
        shocks: { market: -15, growth: -25, value: -5, consumer: -20, financials: -15 },
    },
    {
        name: '地缘政治风险',
        description: '国际冲突导致市场避险情绪上升',
        shocks: { market: -12, volatility: 40, technology: -15, financials: -10, consumer: -8 },
    },
    {
        name: '监管政策收紧',
        description: '行业监管加强，龙头企业受影响',
        shocks: { market: -8, technology: -25, financials: -20, consumer: -15 },
    },
    {
        name: '美元走强',
        description: '美元升值，新兴市场资金外流',
        shocks: { market: -10, rate: 50, size: -15, liquidity: -20 },
    },
    {
        name: '信用违约',
        description: '企业债券违约潮，信用风险上升',
        shocks: { market: -18, financials: -30, size: -25, liquidity: -35, value: -15 },
    },
    {
        name: '科技泡沫',
        description: '科技股估值过高，回调风险',
        shocks: { market: -5, technology: -40, growth: -20, volatility: 60 },
    },
];

// ========== Barra 风险模型（简化版） ==========

/**
 * 简化的 Barra 风险分解
 * 包含市场、规模、价值、动量因子
 */
export async function calculateBarraRisk(
    stocks: string[],
    weights: Record<string, number>
): Promise<BarraRiskResult | { error: string }> {
    if (stocks.length < 2) {
        return { error: '股票数量不足' };
    }

    // 计算协方差矩阵获取总风险
    const covResult = await calculateCovarianceMatrix(stocks);
    if ('error' in covResult) {
        return covResult;
    }

    const n = covResult.stocks.length;
    const weightArr = covResult.stocks.map((s: any) => weights[s] || 0);

    // 计算组合总方差
    let portfolioVar = 0;
    for (let i = 0; i < n; i++) {
        for (let j = 0; j < n; j++) {
            portfolioVar += weightArr[i] * weightArr[j] * covResult.matrix[i][j];
        }
    }
    const totalRisk = Math.sqrt(portfolioVar) * 100;

    // 简化的因子分解
    // 假设因子风险占总风险的 60-80%
    const factorRiskRatio = 0.7;
    const factorRisk = totalRisk * factorRiskRatio;
    const specificRisk = Math.sqrt(totalRisk ** 2 - factorRisk ** 2);

    // 因子暴露（简化：基于股票特征估算）
    const factorExposures: FactorExposure[] = [
        { factorName: '市场', exposure: 1.0, contribution: factorRisk * 0.5 },
        { factorName: '规模', exposure: 0.2, contribution: factorRisk * 0.15 },
        { factorName: '价值', exposure: -0.1, contribution: factorRisk * 0.2 },
        { factorName: '动量', exposure: 0.3, contribution: factorRisk * 0.15 },
    ];

    // 行业暴露
    const industryExposures: Record<string, number> = {};
    for (const code of covResult.stocks) {
        const industry = getIndustry(code);
        const weight = weights[code] || 0;
        industryExposures[industry] = (industryExposures[industry] || 0) + weight;
    }

    // 归一化行业暴露
    const totalWeight = Object.values(industryExposures).reduce((a: any, b: any) => a + b, 0);
    for (const industry of Object.keys(industryExposures)) {
        industryExposures[industry] = totalWeight > 0
            ? Math.round((industryExposures[industry] / totalWeight) * 100)
            : 0;
    }

    return {
        totalRisk: Math.round(totalRisk * 100) / 100,
        factorRisk: Math.round(factorRisk * 100) / 100,
        specificRisk: Math.round(specificRisk * 100) / 100,
        factorExposures,
        industryExposures,
    };
}

// ========== VaR/CVaR 计算 ==========

/**
 * 计算历史模拟法 VaR 和 CVaR
 */
export async function calculateVaR(
    stocks: string[],
    weights: Record<string, number>,
    portfolioValue: number = 1000000,
    confidence: number = 95,
    horizon: number = 1
): Promise<VaRResult | { error: string }> {
    if (stocks.length === 0) {
        return { error: '股票列表为空' };
    }

    // 获取历史收益率
    const lookbackDays = 252;
    const startDate = new Date(Date.now() - lookbackDays * 24 * 60 * 60 * 1000)
        .toISOString().slice(0, 10);
    const endDate = new Date().toISOString().slice(0, 10);

    // 计算组合日收益率序列
    const returnsByDate: Map<string, number> = new Map();
    const dateSet = new Set<string>();

    for (const code of stocks) {
        const bars = await getDailyBarsByDateRange(code, startDate, endDate);
        const weight = weights[code] || 0;

        for (let i = 1; i < bars.length; i++) {
            if (bars[i - 1].close > 0) {
                const date = bars[i].date;
                const dailyReturn = (bars[i].close - bars[i - 1].close) / bars[i - 1].close;

                dateSet.add(date);
                returnsByDate.set(date, (returnsByDate.get(date) || 0) + dailyReturn * weight);
            }
        }
    }

    // 转换为数组并排序
    const portfolioReturns = [...dateSet]
        .map(date => returnsByDate.get(date) || 0)
        .sort((a: any, b: any) => a - b);

    if (portfolioReturns.length < 30) {
        return { error: '历史数据不足，无法计算VaR' };
    }

    // 调整为多日 VaR（假设收益率独立同分布）
    const adjustedReturns = portfolioReturns.map((r: any) => r * Math.sqrt(horizon));

    // 计算分位数位置
    const percentileIndex = Math.floor((100 - confidence) / 100 * adjustedReturns.length);
    const varReturn = adjustedReturns[Math.max(0, percentileIndex)];

    // 计算 CVaR（尾部平均）
    const tailReturns = adjustedReturns.slice(0, percentileIndex + 1);
    const cvarReturn = tailReturns.length > 0
        ? tailReturns.reduce((a: any, b: any) => a + b, 0) / tailReturns.length
        : varReturn;

    return {
        confidence,
        horizon,
        var: Math.round(Math.abs(varReturn) * portfolioValue * 100) / 100,
        varPercent: Math.round(Math.abs(varReturn) * 10000) / 100,
        cvar: Math.round(Math.abs(cvarReturn) * portfolioValue * 100) / 100,
        cvarPercent: Math.round(Math.abs(cvarReturn) * 10000) / 100,
    };
}

// ========== 压力测试 ==========

/**
 * 运行压力测试
 */
export function runStressTest(
    stocks: string[],
    weights: Record<string, number>,
    scenarioName?: string
): StressTestResult[] | { error: string } {
    if (stocks.length === 0) {
        return { error: '股票列表为空' };
    }

    // 选择场景
    const scenarios = scenarioName
        ? STRESS_SCENARIOS.filter((s: any) => s.name === scenarioName)
        : STRESS_SCENARIOS;

    if (scenarios.length === 0) {
        return { error: `未找到场景: ${scenarioName}` };
    }

    const results: StressTestResult[] = [];

    for (const scenario of scenarios) {
        // 计算各股票在场景下的损失
        const stockLosses: Array<{ code: string; loss: number }> = [];
        let portfolioLoss = 0;

        for (const code of stocks) {
            const weight = weights[code] || 0;
            const industry = getIndustry(code);

            // 计算股票损失（简化：市场因子 + 行业因子）
            let stockLoss = scenario.shocks.market || 0;

            // 添加行业特定冲击
            if (industry === '科技' && scenario.shocks.technology) {
                stockLoss += scenario.shocks.technology;
            } else if (industry === '金融' && scenario.shocks.financials) {
                stockLoss += scenario.shocks.financials;
            } else if (industry === '消费' && scenario.shocks.consumer) {
                stockLoss += scenario.shocks.consumer;
            }

            stockLosses.push({ code, loss: stockLoss });
            portfolioLoss += stockLoss * weight;
        }

        // 排序找出损失最大的股票
        stockLosses.sort((a: any, b: any) => a.loss - b.loss);

        results.push({
            scenario: scenario.name,
            portfolioLoss: Math.round(portfolioLoss * 100) / 100,
            worstStocks: stockLosses.slice(0, 5),
            factorContributions: scenario.shocks,
        });
    }

    return results;
}

// ========== 综合风险报告 ==========

export interface RiskReport {
    barraRisk: BarraRiskResult;
    var95: VaRResult;
    var99: VaRResult;
    stressTests: StressTestResult[];
}

/**
 * 生成综合风险报告
 */
export async function generateRiskReport(
    stocks: string[],
    weights: Record<string, number>,
    portfolioValue: number = 1000000
): Promise<RiskReport | { error: string }> {
    // Barra 风险分解
    const barraResult = await calculateBarraRisk(stocks, weights);
    if ('error' in barraResult) {
        return barraResult;
    }

    // VaR 计算
    const var95 = await calculateVaR(stocks, weights, portfolioValue, 95, 1);
    if ('error' in var95) {
        return var95;
    }

    const var99 = await calculateVaR(stocks, weights, portfolioValue, 99, 1);
    if ('error' in var99) {
        return var99;
    }

    // 压力测试
    const stressResults = runStressTest(stocks, weights);
    if ('error' in stressResults) {
        return stressResults;
    }

    return {
        barraRisk: barraResult,
        var95,
        var99,
        stressTests: stressResults,
    };
}
