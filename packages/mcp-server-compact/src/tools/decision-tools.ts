/**
 * 决策辅助工具
 * 买卖决策建议
 */

import { z } from 'zod';
import { ToolDefinition, ToolHandler, ToolRegistryItem } from '../types/tools.js';
import { getValuationData } from '../storage/valuation-data.js';
import { getLatestFinancialData } from '../storage/financial-data.js';
import { getDailyBars } from '../storage/kline-data.js';
import { calculateMomentum, calculateEP, calculateROE } from '../services/factor-calculator.js';

// 决策因素
interface DecisionFactor {
    factor: string;
    score: number; // -100 到 100
    weight: number;
    description: string;
}

// ========== should_i_buy ==========

const shouldIBuySchema = z.object({
    code: z.string().describe('股票代码'),
    investmentStyle: z.enum(['value', 'growth', 'momentum', 'balanced']).optional().default('balanced')
        .describe('投资风格'),
});

const shouldIBuyTool: ToolDefinition = {
    name: 'should_i_buy',
    description: '买入决策建议（综合估值、趋势、基本面分析）',
    category: 'decision',
    inputSchema: shouldIBuySchema,
    tags: ['decision', 'buy', 'analysis'],
    dataSource: 'real',
};

const shouldIBuyHandler: ToolHandler<z.infer<typeof shouldIBuySchema>> = async (params) => {
    const valuation = await getValuationData(params.code);
    const financial = await getLatestFinancialData(params.code);
    const momentum = await calculateMomentum(params.code, 3);
    const ep = await calculateEP(params.code);
    const roe = await calculateROE(params.code);

    const factors: DecisionFactor[] = [];
    let totalScore = 0;
    let totalWeight = 0;

    // 1. 估值因素
    if (valuation?.pe) {
        let peScore = 0;
        if (valuation.pe < 15) peScore = 50;
        else if (valuation.pe < 25) peScore = 20;
        else if (valuation.pe < 40) peScore = -10;
        else peScore = -40;

        const weight = params.investmentStyle === 'value' ? 0.35 : 0.20;
        factors.push({
            factor: 'PE估值',
            score: peScore,
            weight,
            description: `PE=${valuation.pe.toFixed(1)}，${peScore > 0 ? '估值偏低' : '估值偏高'}`,
        });
        totalScore += peScore * weight;
        totalWeight += weight;
    }

    // 2. 盈利质量
    if (roe.success && roe.data) {
        let roeScore = 0;
        // 注意: 数据库存储的ROE是百分比格式（如8.28表示8.28%）
        const roeValue = roe.data.value;
        if (roeValue > 20) roeScore = 50;       // ROE > 20%
        else if (roeValue > 15) roeScore = 30;  // ROE > 15%
        else if (roeValue > 10) roeScore = 10;  // ROE > 10%
        else if (roeValue > 5) roeScore = -10;  // ROE > 5%
        else roeScore = -30;

        const weight = 0.20;
        factors.push({
            factor: 'ROE质量',
            score: roeScore,
            weight,
            description: `ROE=${roeValue.toFixed(2)}%`,  // 已经是百分比，直接显示
        });
        totalScore += roeScore * weight;
        totalWeight += weight;
    }

    // 3. 动量因素
    if (momentum.success && momentum.data) {
        let momScore = 0;
        const momValue = momentum.data.value;
        if (momValue > 0.20) momScore = -20; // 涨太多，风险
        else if (momValue > 0.10) momScore = 10;
        else if (momValue > 0) momScore = 30;
        else if (momValue > -0.10) momScore = 20;
        else if (momValue > -0.20) momScore = 10;
        else momScore = -10; // 跌太多，可能有问题

        const weight = params.investmentStyle === 'momentum' ? 0.30 : 0.15;
        factors.push({
            factor: '3月动量',
            score: momScore,
            weight,
            description: `近3月涨跌=${(momValue * 100).toFixed(1)}%`,
        });
        totalScore += momScore * weight;
        totalWeight += weight;
    }

    // 4. 成长因素
    if (financial?.profitGrowth != null) {
        const growth = financial.profitGrowth;
        let growthScore = 0;
        if (growth > 0.30) growthScore = 50;
        else if (growth > 0.15) growthScore = 30;
        else if (growth > 0) growthScore = 10;
        else if (growth > -0.10) growthScore = -10;
        else growthScore = -30;

        const weight = params.investmentStyle === 'growth' ? 0.30 : 0.15;
        factors.push({
            factor: '利润增长',
            score: growthScore,
            weight,
            description: `增长率=${(growth * 100).toFixed(1)}%`,
        });
        totalScore += growthScore * weight;
        totalWeight += weight;
    }

    // 归一化评分
    const finalScore = totalWeight > 0 ? totalScore / totalWeight : 0;

    let recommendation: 'strong_buy' | 'buy' | 'hold' | 'avoid';
    let confidence: number;

    if (finalScore > 30) {
        recommendation = 'strong_buy';
        confidence = Math.min(90, 60 + finalScore);
    } else if (finalScore > 10) {
        recommendation = 'buy';
        confidence = 50 + finalScore;
    } else if (finalScore > -10) {
        recommendation = 'hold';
        confidence = 40 + Math.abs(finalScore);
    } else {
        recommendation = 'avoid';
        confidence = 50 - finalScore;
    }

    return {
        success: true,
        data: {
            stockCode: params.code,
            investmentStyle: params.investmentStyle,
            recommendation,
            score: Math.round(finalScore),
            confidence: `${Math.min(95, Math.round(confidence))}%`,
            factors: factors.sort((a: any, b: any) => Math.abs(b.score * b.weight) - Math.abs(a.score * a.weight)),
            summary: recommendation === 'strong_buy'
                ? `综合评分较高(${Math.round(finalScore)})，建议积极买入`
                : recommendation === 'buy'
                    ? `评分正面(${Math.round(finalScore)})，可考虑买入`
                    : recommendation === 'hold'
                        ? `评分中性(${Math.round(finalScore)})，建议观望`
                        : `评分偏负(${Math.round(finalScore)})，建议回避`,
            disclaimer: '本建议仅供参考，不构成投资建议，请结合自身情况谨慎决策。',
        },
        source: 'calculated',
    };
};

// ========== should_i_sell ==========

const shouldISellSchema = z.object({
    code: z.string().describe('股票代码'),
    buyPrice: z.number().optional().describe('买入成本价'),
    holdingDays: z.number().optional().describe('持有天数'),
});

const shouldISellTool: ToolDefinition = {
    name: 'should_i_sell',
    description: '卖出决策建议（止盈止损、趋势变化分析）',
    category: 'decision',
    inputSchema: shouldISellSchema,
    tags: ['decision', 'sell', 'analysis'],
    dataSource: 'real',
};

const shouldISellHandler: ToolHandler<z.infer<typeof shouldISellSchema>> = async (params) => {
    const valuation = await getValuationData(params.code);
    const bars = await getDailyBars(params.code, 60);
    const momentum1m = await calculateMomentum(params.code, 1);
    const momentum3m = await calculateMomentum(params.code, 3);

    const factors: DecisionFactor[] = [];
    let sellSignals = 0;
    let holdSignals = 0;

    const currentPrice = valuation?.price || (bars.length > 0 ? bars[bars.length - 1].close : null);

    // 1. 盈亏分析
    if (params.buyPrice && currentPrice) {
        const profitPercent = (currentPrice - params.buyPrice) / params.buyPrice;

        if (profitPercent > 0.30) {
            factors.push({
                factor: '止盈信号',
                score: 60,
                weight: 0.30,
                description: `盈利${(profitPercent * 100).toFixed(1)}%，考虑部分止盈`,
            });
            sellSignals++;
        } else if (profitPercent < -0.10) {
            factors.push({
                factor: '止损信号',
                score: 40,
                weight: 0.25,
                description: `亏损${(profitPercent * 100).toFixed(1)}%，考虑止损`,
            });
            sellSignals++;
        } else {
            factors.push({
                factor: '盈亏状态',
                score: 0,
                weight: 0.20,
                description: `当前${profitPercent >= 0 ? '盈利' : '亏损'}${(Math.abs(profitPercent) * 100).toFixed(1)}%`,
            });
        }
    }

    // 2. 动量变化
    if (momentum1m.success && momentum3m.success && momentum1m.data && momentum3m.data) {
        const mom1m = momentum1m.data.value;
        const mom3m = momentum3m.data.value;

        if (mom1m < -0.10 && mom3m > 0) {
            factors.push({
                factor: '趋势转弱',
                score: 50,
                weight: 0.25,
                description: '短期走弱（1月-10%但3月为正），可能见顶',
            });
            sellSignals++;
        } else if (mom1m > 0.15) {
            factors.push({
                factor: '短期过热',
                score: 30,
                weight: 0.20,
                description: `1月涨幅${(mom1m * 100).toFixed(1)}%，短期可能回调`,
            });
            sellSignals++;
        } else if (mom1m > 0 && mom3m > 0) {
            factors.push({
                factor: '趋势向好',
                score: -30,
                weight: 0.25,
                description: '短中期趋势均向上，可继续持有',
            });
            holdSignals++;
        }
    }

    // 3. 估值高位
    if (valuation?.pe && valuation.pe > 50) {
        factors.push({
            factor: '估值过高',
            score: 40,
            weight: 0.20,
            description: `PE=${valuation.pe.toFixed(1)}，估值处于高位`,
        });
        sellSignals++;
    }

    // 决策
    let recommendation: 'sell_all' | 'sell_partial' | 'hold' | 'add';
    let reason: string;

    if (sellSignals >= 2) {
        recommendation = 'sell_partial';
        reason = '多个卖出信号，建议减仓或止盈';
    } else if (sellSignals === 1) {
        recommendation = 'hold';
        reason = '存在一个卖出信号，可观望但注意风险';
    } else if (holdSignals >= 2) {
        recommendation = 'hold';
        reason = '趋势良好，建议继续持有';
    } else {
        recommendation = 'hold';
        reason = '无明显卖出信号';
    }

    return {
        success: true,
        data: {
            stockCode: params.code,
            currentPrice,
            buyPrice: params.buyPrice,
            profitLoss: params.buyPrice && currentPrice
                ? `${((currentPrice - params.buyPrice) / params.buyPrice * 100).toFixed(1)}%`
                : null,
            recommendation,
            sellSignals,
            holdSignals,
            factors,
            reason,
            disclaimer: '本建议仅供参考，不构成投资建议，请结合自身情况谨慎决策。',
        },
        source: 'calculated',
    };
};

// ========== 注册导出 ==========

export const decisionTools: ToolRegistryItem[] = [
    { definition: shouldIBuyTool, handler: shouldIBuyHandler },
    { definition: shouldISellTool, handler: shouldISellHandler },
];
