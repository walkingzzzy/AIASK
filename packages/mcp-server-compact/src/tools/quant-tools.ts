/**
 * 量化因子工具
 * 基于 factor-calculator 服务提供因子分析功能
 */

import { z } from 'zod';
import { ToolDefinition, ToolHandler, ToolRegistryItem } from '../types/tools.js';
import {
    SUPPORTED_FACTORS,
    calculateFactor,
    batchCalculateFactors,
    calculateMultipleFactors,
} from '../services/factor-calculator.js';

// ========== get_factor_library ==========

const getFactorLibrarySchema = z.object({
    category: z.preprocess((value) => {
        if (typeof value !== 'string') return value;
        const normalized = value.trim().toLowerCase();
        if (normalized === 'value') return 'valuation';
        return normalized;
    }, z.enum(['all', 'valuation', 'growth', 'momentum', 'quality']))
        .optional()
        .default('all')
        .describe('因子类别筛选'),
});

const getFactorLibraryTool: ToolDefinition = {
    name: 'get_factor_library',
    description: '获取可用因子库列表及说明',
    category: 'quant',
    inputSchema: getFactorLibrarySchema,
    tags: ['quant', 'factor', 'library'],
    dataSource: 'real',
};

const factorDescriptions: Record<string, { name: string; category: string; description: string }> = {
    ep: { name: 'EP (盈利收益率)', category: 'valuation', description: '1/PE，越高表示估值越低' },
    bp: { name: 'BP (净资产收益率)', category: 'valuation', description: '1/PB，越高表示估值越低' },
    revenue_growth: { name: '营收增长率', category: 'growth', description: '同比营收增长率' },
    profit_growth: { name: '利润增长率', category: 'growth', description: '同比净利润增长率' },
    momentum_1m: { name: '1月动量', category: 'momentum', description: '过去1个月涨跌幅' },
    momentum_3m: { name: '3月动量', category: 'momentum', description: '过去3个月涨跌幅' },
    momentum_6m: { name: '6月动量', category: 'momentum', description: '过去6个月涨跌幅' },
    momentum_12m: { name: '12月动量', category: 'momentum', description: '过去12个月涨跌幅' },
    roe: { name: 'ROE', category: 'quality', description: '净资产收益率' },
    gross_margin: { name: '毛利率', category: 'quality', description: '毛利润/营收' },
    net_margin: { name: '净利率', category: 'quality', description: '净利润/营收' },
};

const getFactorLibraryHandler: ToolHandler<z.infer<typeof getFactorLibrarySchema>> = async (params) => {
    const allFactors = SUPPORTED_FACTORS.map((f: any) => ({
        factorId: f,
        ...factorDescriptions[f] || { name: f, category: 'other', description: '' },
    }));

    let filtered = allFactors;
    if (params.category !== 'all') {
        filtered = allFactors.filter((f: any) => f.category === params.category);
    }

    const byCategory = filtered.reduce((acc, f) => {
        if (!acc[f.category]) acc[f.category] = [];
        acc[f.category].push(f);
        return acc;
    }, {} as Record<string, typeof filtered>);

    return {
        success: true,
        data: {
            totalFactors: SUPPORTED_FACTORS.length,
            filteredCount: filtered.length,
            categories: Object.keys(byCategory),
            factors: filtered,
            byCategory,
        },
        source: 'factor_library',
    };
};

// ========== calculate_factor ==========

const calculateFactorSchema = z.object({
    code: z.string().describe('股票代码'),
    factor: z.string().describe('因子名称 (ep/bp/roe/momentum_6m 等)'),
});

const calculateFactorTool: ToolDefinition = {
    name: 'calculate_factor',
    description: '计算单只股票的指定因子值',
    category: 'quant',
    inputSchema: calculateFactorSchema,
    tags: ['quant', 'factor', 'calculate'],
    dataSource: 'real',
};

const calculateFactorHandler: ToolHandler<z.infer<typeof calculateFactorSchema>> = async (params) => {
    const result = await calculateFactor(params.code, params.factor);

    if (!result.success) {
        return {
            success: false,
            error: result.error,
            data: {
                supportedFactors: SUPPORTED_FACTORS,
            },
        };
    }

    return {
        success: true,
        data: result.data,
        source: 'calculated',
    };
};

// ========== calculate_factor_ic ==========

const calculateFactorIcSchema = z.object({
    factor: z.string().describe('因子名称'),
    codes: z.array(z.string()).min(5).describe('股票代码列表（至少5只）'),
    period: z.number().optional().default(20).describe('收益率计算周期（天）'),
});

const calculateFactorIcTool: ToolDefinition = {
    name: 'calculate_factor_ic',
    description: '计算因子 IC (Information Coefficient) 和 IR (Information Ratio)',
    category: 'quant',
    inputSchema: calculateFactorIcSchema,
    tags: ['quant', 'factor', 'ic', 'ir'],
    dataSource: 'real',
};

const calculateFactorIcHandler: ToolHandler<z.infer<typeof calculateFactorIcSchema>> = async (params) => {
    // 批量计算因子值
    const factorResult = await batchCalculateFactors(params.codes, params.factor);

    if (factorResult.factors.length < 5) {
        return {
            success: false,
            error: `有效因子值不足，需要至少5只股票，当前仅 ${factorResult.factors.length} 只`,
            data: { errors: factorResult.errors.slice(0, 10) },
        };
    }

    // 使用真实的因子值统计
    const values = factorResult.factors.map((f: any) => f.value);
    const mean = values.reduce((a: any, b: any) => a + b, 0) / values.length;
    const std = Math.sqrt(values.reduce((a: any, b: any) => a + (b - mean) ** 2, 0) / values.length);

    // 计算真实的 IC：使用因子值排名与收益率排名的 Spearman 相关性
    // 获取每只股票的实际收益率（基于K线数据）
    const { getDailyBars } = await import('../storage/kline-data.js');

    const stockReturns: Array<{ code: string; factorValue: number; periodReturn: number }> = [];

    for (const factor of factorResult.factors) {
        const bars = await getDailyBars(factor.code, params.period + 5);
        if (bars.length >= params.period) {
            const startIdx = Math.max(0, bars.length - params.period - 1);
            const endIdx = bars.length - 1;
            const startPrice = bars[startIdx].close;
            const endPrice = bars[endIdx].close;
            if (startPrice > 0) {
                const periodReturn = (endPrice - startPrice) / startPrice;
                stockReturns.push({
                    code: factor.code,
                    factorValue: factor.value,
                    periodReturn,
                });
            }
        }
    }

    let ic = 0;
    let ir = 0;

    if (stockReturns.length >= 5) {
        // 计算 Spearman 秩相关系数
        const n = stockReturns.length;

        // 对因子值排名
        const sortedByFactor = [...stockReturns].sort((a: any, b: any) => a.factorValue - b.factorValue);
        const factorRanks = new Map<string, number>();
        sortedByFactor.forEach((s, i) => factorRanks.set(s.code, i + 1));

        // 对收益率排名
        const sortedByReturn = [...stockReturns].sort((a: any, b: any) => a.periodReturn - b.periodReturn);
        const returnRanks = new Map<string, number>();
        sortedByReturn.forEach((s, i) => returnRanks.set(s.code, i + 1));

        // 计算秩差平方和
        let d2Sum = 0;
        for (const s of stockReturns) {
            const d = (factorRanks.get(s.code) || 0) - (returnRanks.get(s.code) || 0);
            d2Sum += d * d;
        }

        // Spearman rho = 1 - 6 * sum(d^2) / (n * (n^2 - 1))
        ic = 1 - (6 * d2Sum) / (n * (n * n - 1));

        // IR = IC / IC标准差（简化：使用IC的绝对值除以一个经验常数）
        ir = Math.abs(ic) > 0.01 ? ic / 0.15 : 0;
    }

    return {
        success: true,
        data: {
            factor: params.factor,
            sampleSize: factorResult.factors.length,
            validReturns: stockReturns.length,
            period: params.period,
            statistics: {
                mean: Number(mean.toFixed(6)),
                std: Number(std.toFixed(6)),
                min: Math.min(...values),
                max: Math.max(...values),
            },
            ic: {
                value: Number(ic.toFixed(4)),
                ir: Number(ir.toFixed(4)),
                interpretation: ic > 0.05 ? '正向有效' : ic < -0.05 ? '反向有效' : '无显著效果',
                dataSource: stockReturns.length >= 5 ? 'real_calculation' : 'insufficient_data',
            },
            topStocks: factorResult.factors
                .sort((a: any, b: any) => b.value - a.value)
                .slice(0, 5)
                .map((f: any) => ({ code: f.code, value: f.value })),
            bottomStocks: factorResult.factors
                .sort((a: any, b: any) => a.value - b.value)
                .slice(0, 5)
                .map((f: any) => ({ code: f.code, value: f.value })),
        },
        source: 'calculated',
    };
};

// ========== backtest_factor ==========

const backtestFactorSchema = z.object({
    factor: z.string().describe('因子名称'),
    codes: z.array(z.string()).min(10).describe('股票池（至少10只）'),
    groups: z.number().optional().default(5).describe('分组数量，默认5'),
    holdingDays: z.number().optional().default(20).describe('持仓周期（天）'),
});

const backtestFactorTool: ToolDefinition = {
    name: 'backtest_factor',
    description: '单因子回测（分组测试因子有效性）',
    category: 'quant',
    inputSchema: backtestFactorSchema,
    tags: ['quant', 'factor', 'backtest'],
    dataSource: 'real',
};

const backtestFactorHandler: ToolHandler<z.infer<typeof backtestFactorSchema>> = async (params) => {
    // 批量计算因子值
    const factorResult = await batchCalculateFactors(params.codes, params.factor);

    // Adaptive Grouping Logic
    let numGroups = params.groups;
    const minStocksPerGroup = 2; // At least 2 stocks per group for averaging

    // First check overall validity
    if (factorResult.factors.length < minStocksPerGroup * 2) {
        return {
            success: false,
            error: `有效股票数量严重不足 (${factorResult.factors.length} 只)，无法进行多空回测 (至少需要 ${minStocksPerGroup * 2} 只)`,
        };
    }

    // Adjust groups if needed
    if (factorResult.factors.length < numGroups * minStocksPerGroup) {
        const suggestedGroups = Math.floor(factorResult.factors.length / minStocksPerGroup);
        if (suggestedGroups >= 2) {
            numGroups = suggestedGroups;
            // We can log a warning or include it in the result note
        } else {
            return {
                success: false,
                error: `有效股票数量不足 (${factorResult.factors.length} 只)，无法满足 ${numGroups} 分组 (建议减少分组或扩大股票池)`,
            };
        }
    }


    // 获取K线数据计算真实收益率
    const { getDailyBars } = await import('../storage/kline-data.js');

    // 为每只股票计算真实收益率
    const stocksWithReturns: Array<{ code: string; factorValue: number; periodReturn: number }> = [];
    for (const factor of factorResult.factors) {
        const bars = await getDailyBars(factor.code, params.holdingDays + 10);
        if (bars.length >= params.holdingDays) {
            const startIdx = Math.max(0, bars.length - params.holdingDays - 1);
            const endIdx = bars.length - 1;
            const startPrice = bars[startIdx].close;
            const endPrice = bars[endIdx].close;
            if (startPrice > 0) {
                const periodReturn = (endPrice - startPrice) / startPrice;
                stocksWithReturns.push({
                    code: factor.code,
                    factorValue: factor.value,
                    periodReturn,
                });
            }
        }
    }

    if (stocksWithReturns.length < params.groups * 2) {
        return {
            success: false,
            error: `有效收益率数据不足，需要至少 ${params.groups * 2} 只，当前仅 ${stocksWithReturns.length} 只有K线数据`,
        };
    }

    // 按因子值排序分组
    const sorted = [...stocksWithReturns].sort((a: any, b: any) => b.factorValue - a.factorValue);
    const groupSize = Math.floor(sorted.length / params.groups);

    const groupResults: Array<{
        group: number;
        label: string;
        stockCount: number;
        avgFactorValue: number;
        periodReturn: string;
        returnValue: number;
        topStocks: string[];
    }> = [];

    for (let i = 0; i < numGroups; i++) {
        const start = i * groupSize;
        const end = i === numGroups - 1 ? sorted.length : (i + 1) * groupSize;
        const groupStocks = sorted.slice(start, end);

        if (groupStocks.length === 0) continue;

        const avgFactorValue = groupStocks.reduce((a: any, b: any) => a + b.factorValue, 0) / groupStocks.length;

        // 使用真实的收益率平均值
        const avgReturn = groupStocks.reduce((a: any, b: any) => a + b.periodReturn, 0) / groupStocks.length;

        groupResults.push({
            group: i + 1,
            label: i === 0 ? '高因子组' : i === numGroups - 1 ? '低因子组' : `第${i + 1}组`,
            stockCount: groupStocks.length,
            avgFactorValue: Number(avgFactorValue.toFixed(6)),
            periodReturn: `${(avgReturn * 100).toFixed(2)}%`,
            returnValue: Number(avgReturn.toFixed(4)),
            topStocks: groupStocks.slice(0, 3).map((s: any) => s.code),
        });
    }

    // 计算多空收益
    if (groupResults.length < 2) {
        return {
            success: false,
            error: `分组计算失败，有效分组不足`,
        };
    }
    const longShortReturn = groupResults[0].returnValue - groupResults[groupResults.length - 1].returnValue;

    return {
        success: true,
        data: {
            factor: params.factor,
            stockPool: params.codes.length,
            validStocks: stocksWithReturns.length,
            groups: numGroups,
            originalGroups: params.groups,
            holdingDays: params.holdingDays,
            groupResults,
            summary: {
                longShortReturn: `${(longShortReturn * 100).toFixed(2)}%`,
                isEffective: longShortReturn > 0,
                monotonicity: groupResults.every((g, i) =>
                    i === 0 || g.returnValue <= groupResults[i - 1].returnValue
                ),
                dataSource: 'real_kline_data',
                note: numGroups !== params.groups ? `因有效股票不足，分组数已从 ${params.groups} 自动调整为 ${numGroups}` : undefined
            },
        },
        source: 'backtest',
    };
};

// ========== 注册导出 ==========

export const quantTools: ToolRegistryItem[] = [
    { definition: getFactorLibraryTool, handler: getFactorLibraryHandler },
    { definition: calculateFactorTool, handler: calculateFactorHandler },
    { definition: calculateFactorIcTool, handler: calculateFactorIcHandler },
    { definition: backtestFactorTool, handler: backtestFactorHandler },
];
