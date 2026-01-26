/**
 * 估值模型工具
 * DCF、DDM、相对估值等
 */

import { z } from 'zod';
import { ToolDefinition, ToolHandler, ToolRegistryItem } from '../types/tools.js';
import { calculateDCF, compareValuations } from '../services/valuation.js';
import { getLatestFinancialData } from '../storage/financial-data.js';
import { getValuationData } from '../storage/valuation-data.js';
import { adapterManager } from '../adapters/index.js';

// ========== dcf_valuation ==========

const dcfValuationSchema = z.object({
    code: z.string().describe('股票代码'),
    freeCashFlow: z.number().optional().describe('自由现金流（元），不填则从财务数据估算'),
    growthRate: z.number().optional().default(0.08).describe('预期增长率，默认8%'),
    discountRate: z.number().optional().default(0.10).describe('折现率，默认10%'),
    terminalGrowthRate: z.number().optional().default(0.02).describe('永续增长率，默认2%'),
    years: z.number().optional().default(5).describe('预测年数，默认5年'),
});

const dcfValuationTool: ToolDefinition = {
    name: 'dcf_valuation',
    description: 'DCF 现金流折现估值模型',
    category: 'valuation',
    inputSchema: dcfValuationSchema,
    tags: ['valuation', 'dcf', 'intrinsic'],
    dataSource: 'real',
};

const dcfValuationHandler: ToolHandler<z.infer<typeof dcfValuationSchema>> = async (params) => {
    // 获取财务数据
    const financial = await getLatestFinancialData(params.code);
    const valuation = await getValuationData(params.code);

    const resolveNetProfit = async () => {
        if (financial?.netProfit && financial.netProfit > 0) {
            return { value: financial.netProfit, source: 'financials' };
        }
        if (valuation?.pe && valuation?.marketCap && valuation.pe > 0) {
            return { value: valuation.marketCap / valuation.pe, source: 'valuation_pe' };
        }
        if (financial?.eps && valuation?.price && valuation?.marketCap) {
            const shares = valuation.marketCap / valuation.price;
            return { value: financial.eps * shares, source: 'eps' };
        }

        const adapterFinancial = await adapterManager.getFinancials(params.code);
        if (adapterFinancial.success && adapterFinancial.data?.netProfit && adapterFinancial.data.netProfit > 0) {
            return { value: adapterFinancial.data.netProfit, source: 'adapter_financials' };
        }

        const adapterValuation = await adapterManager.getValuationMetrics(params.code);
        if (adapterValuation.success && adapterValuation.data?.pe && adapterValuation.data?.marketCap && adapterValuation.data.pe > 0) {
            return { value: adapterValuation.data.marketCap / adapterValuation.data.pe, source: 'adapter_valuation' };
        }

        return null;
    };

    // 估算自由现金流（使用净利润 * 0.7 作为近似）
    let fcf = params.freeCashFlow;
    let fcfSource = params.freeCashFlow ? 'manual' : 'unknown';
    if (!fcf) {
        const netProfitResult = await resolveNetProfit();
        if (netProfitResult && netProfitResult.value > 0) {
            fcf = netProfitResult.value * 0.7;
            fcfSource = netProfitResult.source;
        }
    }

    if (!fcf || fcf <= 0) {
        return {
            success: false,
            error: `无法获取股票 ${params.code} 的自由现金流数据，请手动提供 freeCashFlow 参数`,
        };
    }

    const result = await calculateDCF(
        fcf,
        params.growthRate,
        params.discountRate,
        params.terminalGrowthRate,
        params.years
    );

    // 计算每股价值（如果有股本数据）
    const sharesOutstanding = valuation?.marketCap && valuation?.price
        ? valuation.marketCap / valuation.price
        : null;

    const intrinsicValuePerShare = sharesOutstanding
        ? result.intrinsicValue / sharesOutstanding
        : null;

    const marginOfSafety = intrinsicValuePerShare && valuation?.price
        ? (intrinsicValuePerShare - valuation.price) / intrinsicValuePerShare
        : null;

    return {
        success: true,
        data: {
            stockCode: params.code,
            assumptions: {
                freeCashFlow: fcf,
                freeCashFlowSource: fcfSource,
                growthRate: `${(params.growthRate * 100).toFixed(1)}%`,
                discountRate: `${(params.discountRate * 100).toFixed(1)}%`,
                terminalGrowthRate: `${(params.terminalGrowthRate * 100).toFixed(1)}%`,
                forecastYears: params.years,
            },
            valuation: {
                enterpriseValue: Math.round(result.intrinsicValue),
                terminalValuePortion: Math.round(result.terminalValue),
                presentValueOfCashFlows: result.presentValues.map((v: any) => Math.round(v)),
            },
            perShare: intrinsicValuePerShare ? {
                intrinsicValue: Math.round(intrinsicValuePerShare * 100) / 100,
                currentPrice: valuation?.price,
                marginOfSafety: marginOfSafety ? `${(marginOfSafety * 100).toFixed(1)}%` : null,
                recommendation: marginOfSafety && marginOfSafety > 0.3 ? 'undervalued'
                    : marginOfSafety && marginOfSafety < -0.2 ? 'overvalued' : 'fairly_valued',
            } : null,
        },
        source: 'calculated',
    };
};

// ========== ddm_valuation ==========

const ddmValuationSchema = z.object({
    code: z.string().describe('股票代码'),
    dividend: z.number().optional().describe('每股股息（元），不填则从数据估算'),
    growthRate: z.number().optional().default(0.05).describe('股息增长率，默认5%'),
    requiredReturn: z.number().optional().default(0.10).describe('要求回报率，默认10%'),
});

const ddmValuationTool: ToolDefinition = {
    name: 'ddm_valuation',
    description: 'DDM 股息折现模型估值（适用于稳定派息股票）',
    category: 'valuation',
    inputSchema: ddmValuationSchema,
    tags: ['valuation', 'ddm', 'dividend'],
    dataSource: 'real',
};

const ddmValuationHandler: ToolHandler<z.infer<typeof ddmValuationSchema>> = async (params) => {
    const valuation = await getValuationData(params.code);
    const payoutRatio = 0.3;

    // 估算股息 - 当前ValuationData不含 dividendYield，需用户手动输入
    let dividend = params.dividend;
    let dividendSource = params.dividend ? 'manual' : 'unknown';
    let price = valuation?.price;
    let marketCap = valuation?.marketCap ?? null;
    if (!price) {
        const quoteRes = await adapterManager.getRealtimeQuote(params.code);
        if (quoteRes.success && quoteRes.data?.price) {
            price = quoteRes.data.price;
        }
        if (!marketCap && quoteRes.success && quoteRes.data?.marketCap) {
            marketCap = quoteRes.data.marketCap;
        }
    }

    if (!dividend || dividend <= 0) {
        const valRes = await adapterManager.getValuationMetrics(params.code);
        const yieldValue = valRes.success ? valRes.data?.dividendYield : null;
        if (yieldValue && price) {
            const ratio = yieldValue > 1 ? yieldValue / 100 : yieldValue;
            dividend = price * ratio;
            dividendSource = 'dividend_yield';
        }
    }

    if ((!dividend || dividend <= 0) && price) {
        const netProfitResult = await (async () => {
            const financial = await getLatestFinancialData(params.code);
            if (financial?.netProfit && financial.netProfit > 0) {
                return { value: financial.netProfit, source: 'financials' };
            }
            if (valuation?.pe && valuation?.marketCap && valuation.pe > 0) {
                return { value: valuation.marketCap / valuation.pe, source: 'valuation_pe' };
            }
            const adapterFinancial = await adapterManager.getFinancials(params.code);
            if (adapterFinancial.success && adapterFinancial.data?.netProfit && adapterFinancial.data.netProfit > 0) {
                return { value: adapterFinancial.data.netProfit, source: 'adapter_financials' };
            }
            const adapterValuation = await adapterManager.getValuationMetrics(params.code);
            if (adapterValuation.success && adapterValuation.data?.pe && adapterValuation.data?.marketCap && adapterValuation.data.pe > 0) {
                return { value: adapterValuation.data.marketCap / adapterValuation.data.pe, source: 'adapter_valuation' };
            }
            return null;
        })();
        if (netProfitResult && marketCap && price) {
            const shares = marketCap / price;
            if (shares > 0) {
                dividend = (netProfitResult.value * payoutRatio) / shares;
                dividendSource = `estimated_payout_${netProfitResult.source}`;
            }
        }
    }

    if (!dividend || dividend <= 0) {
        return {
            success: false,
            error: `股票 ${params.code} 无股息数据或未派息，DDM模型不适用。DDM模型仅适用于有稳定分红的公司。`,
            data: {
                suggestion: '请使用 dcf_valuation (适用于稳定现金流公司) 或 relative_valuation (适用于一般公司) 进行估值',
                reason: 'No dividend data found or dividend is zero.'
            },
        };
    }

    if (params.growthRate >= params.requiredReturn) {
        return {
            success: false,
            error: '增长率必须小于要求回报率',
        };
    }

    // Gordon Growth Model: P = D1 / (r - g)
    const nextDividend = dividend * (1 + params.growthRate);
    const intrinsicValue = nextDividend / (params.requiredReturn - params.growthRate);

    const marginOfSafety = valuation?.price
        ? (intrinsicValue - valuation.price) / intrinsicValue
        : null;

    return {
        success: true,
        data: {
            stockCode: params.code,
            model: 'Gordon Growth Model (DDM)',
            assumptions: {
                currentDividend: dividend,
                nextYearDividend: Math.round(nextDividend * 100) / 100,
                dividendGrowthRate: `${(params.growthRate * 100).toFixed(1)}%`,
                requiredReturn: `${(params.requiredReturn * 100).toFixed(1)}%`,
                dividendSource,
                payoutRatio: dividendSource.startsWith('estimated_payout') ? `${(payoutRatio * 100).toFixed(0)}%` : null,
            },
            valuation: {
                intrinsicValue: Math.round(intrinsicValue * 100) / 100,
                currentPrice: valuation?.price,
                marginOfSafety: marginOfSafety ? `${(marginOfSafety * 100).toFixed(1)}%` : null,
                recommendation: marginOfSafety && marginOfSafety > 0.2 ? 'undervalued'
                    : marginOfSafety && marginOfSafety < -0.1 ? 'overvalued' : 'fairly_valued',
            },
        },
        source: 'calculated',
    };
};

// ========== relative_valuation ==========

const relativeValuationSchema = z.object({
    code: z.string().describe('目标股票代码'),
    peers: z.array(z.string()).optional().describe('同行股票代码列表'),
    metrics: z.array(z.enum(['pe', 'pb', 'ps', 'peg'])).optional().default(['pe', 'pb'])
        .describe('对比指标'),
});

const relativeValuationTool: ToolDefinition = {
    name: 'relative_valuation',
    description: '相对估值法（PE/PB/PS同行对比）',
    category: 'valuation',
    inputSchema: relativeValuationSchema,
    tags: ['valuation', 'relative', 'comparison'],
    dataSource: 'real',
};

const relativeValuationHandler: ToolHandler<z.infer<typeof relativeValuationSchema>> = async (params) => {
    const targetValuation = await getValuationData(params.code);
    const targetFinancial = await getLatestFinancialData(params.code);

    if (!targetValuation) {
        return {
            success: false,
            error: `无法获取股票 ${params.code} 的估值数据`,
        };
    }

    // 获取同行数据
    const peersData: Array<{
        code: string;
        pe: number;
        pb: number;
        roe: number;
        growth: number;
    }> = [];

    // 添加目标股票
    peersData.push({
        code: params.code,
        pe: targetValuation.pe || 0,
        pb: targetValuation.pb || 0,
        roe: targetFinancial?.roe || 0,
        growth: targetFinancial?.profitGrowth || 0,
    });

    // 添加同行股票
    for (const peer of params.peers || []) {
        const peerVal = await getValuationData(peer);
        const peerFin = await getLatestFinancialData(peer);
        if (peerVal) {
            peersData.push({
                code: peer,
                pe: peerVal.pe || 0,
                pb: peerVal.pb || 0,
                roe: peerFin?.roe || 0,
                growth: peerFin?.profitGrowth || 0,
            });
        }
    }

    if (peersData.length < 2) {
        // 返回单股估值摘要
        return {
            success: true,
            data: {
                stockCode: params.code,
                valuation: {
                    pe: targetValuation.pe,
                    pb: targetValuation.pb,
                    // ps 和 dividendYield 当前不在 ValuationData 中
                },
                quality: {
                    roe: targetFinancial?.roe,
                    profitGrowth: targetFinancial?.profitGrowth,
                },
                note: '未提供同行对比，仅返回单股估值指标',
            },
            source: 'database',
        };
    }

    // 计算对比
    const comparison = compareValuations(peersData);
    const targetResult = comparison.find(c => c.code === params.code);

    // 计算行业均值
    const avgPe = peersData.reduce((a: any, b: any) => a + b.pe, 0) / peersData.length;
    const avgPb = peersData.reduce((a: any, b: any) => a + b.pb, 0) / peersData.length;

    return {
        success: true,
        data: {
            targetStock: {
                code: params.code,
                pe: targetValuation.pe,
                pb: targetValuation.pb,
                peg: targetResult?.peg,
                assessment: targetResult?.assessment,
                rank: `${targetResult?.rank}/${peersData.length}`,
            },
            industryAverage: {
                pe: Math.round(avgPe * 100) / 100,
                pb: Math.round(avgPb * 100) / 100,
            },
            premiumDiscount: {
                pePremium: targetValuation.pe && avgPe
                    ? `${(((targetValuation.pe / avgPe) - 1) * 100).toFixed(1)}%`
                    : null,
                pbPremium: targetValuation.pb && avgPb
                    ? `${(((targetValuation.pb / avgPb) - 1) * 100).toFixed(1)}%`
                    : null,
            },
            peerComparison: comparison,
        },
        source: 'calculated',
    };
};

// ========== 注册导出 ==========

export const valuationTools: ToolRegistryItem[] = [
    { definition: dcfValuationTool, handler: dcfValuationHandler },
    { definition: ddmValuationTool, handler: ddmValuationHandler },
    { definition: relativeValuationTool, handler: relativeValuationHandler },
];
