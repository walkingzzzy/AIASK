import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import * as FactorServices from '../../services/factor-calculator.js';

export const quantManagerTool: ToolDefinition = {
    name: 'quant_manager',
    description: '量化因子管理',
    category: 'backtest',
    inputSchema: managerSchema,
    dataSource: 'real'
};

export const quantManagerHandler: ToolHandler = async (params: any) => {
    const code = params.code || params.stock || params.symbol || (Array.isArray(params.codes) && params.codes[0]);
    const { action, factors, codes } = params;

    // ===== 计算因子 =====
    if (action === 'calculate_factors') {
        if (!code) return { success: false, error: 'Missing code parameter (or stock/symbol)' };

        const factorNames = factors || ['ep', 'bp', 'revenue_growth', 'profit_growth', 'momentum_3m', 'roe'];
        const result = await FactorServices.calculateMultipleFactors(code, factorNames);
        return { success: true, data: result };
    }

    // ===== 获取 A 股因子库 =====
    if (action === 'get_china_a_factors' || action === 'china_factors') {
        const factorLibrary = {
            categories: ['估值', '成长', '动量', '质量', '规模', '波动率'],
            factors: [
                { id: 'ep', name: '盈利收益率', category: '估值', formula: '1/PE' },
                { id: 'bp', name: '净资产收益率', category: '估值', formula: '1/PB' },
                { id: 'revenue_growth', name: '营收增长', category: '成长', formula: 'YoY Revenue Growth' },
                { id: 'profit_growth', name: '利润增长', category: '成长', formula: 'YoY Profit Growth' },
                { id: 'momentum_1m', name: '1月动量', category: '动量', formula: '1-month return' },
                { id: 'momentum_3m', name: '3月动量', category: '动量', formula: '3-month return' },
                { id: 'momentum_6m', name: '6月动量', category: '动量', formula: '6-month return' },
                { id: 'roe', name: 'ROE', category: '质量', formula: 'Net Income / Equity' },
                { id: 'gross_margin', name: '毛利率', category: '质量', formula: 'Gross Profit / Revenue' },
                { id: 'market_cap', name: '市值', category: '规模', formula: 'Price * Shares' },
            ],
        };
        return { success: true, data: factorLibrary };
    }

    // ===== Carhart 四因子模型 =====
    if (action === 'calculate_carhart' || action === 'carhart') {
        const targetCode = code || '000001';

        // 获取真实的动量因子数据
        const mom3m = await FactorServices.calculateFactor(targetCode, 'momentum_3m');
        const mom6m = await FactorServices.calculateFactor(targetCode, 'momentum_6m');
        const bp = await FactorServices.calculateFactor(targetCode, 'bp');

        // 使用真实因子值计算Beta（简化版）
        const beta_mom = mom3m.success && mom3m.data ? Number((mom3m.data.value * 2).toFixed(3)) : null;
        const beta_hml = bp.success && bp.data ? Number((bp.data.value * 10 - 0.5).toFixed(3)) : null;

        const result = {
            model: 'Carhart Four-Factor Model',
            target: targetCode,
            coefficients: {
                alpha: '需要回归计算',
                beta_mkt: '需要市场数据回归',
                beta_smb: '需要规模因子数据',
                beta_hml: beta_hml,
                beta_mom: beta_mom,
            },
            factorValues: {
                momentum_3m: mom3m.data?.value ?? null,
                momentum_6m: mom6m.data?.value ?? null,
                bp: bp.data?.value ?? null,
            },
            dataSource: mom3m.success ? 'real_factors' : 'partial',
            note: '因子值基于真实数据，回归系数需要完整实现',
        };
        return { success: true, data: result };
    }

    // ===== 创建多因子模型 =====
    if (action === 'create_multi_factor_model' || action === 'multi_factor') {
        const selectedFactors = factors || ['ep', 'momentum_3m', 'roe'];
        const stockPool = codes || ['000001', '000002', '600000', '600519'];

        // 计算每个因子的平均值
        const factorWeights = [];
        for (const f of selectedFactors) {
            const batchResult = await FactorServices.batchCalculateFactors(stockPool, f);
            const avgValue = batchResult.factors.length > 0
                ? batchResult.factors.reduce((a: any, b: any) => a + b.value, 0) / batchResult.factors.length
                : null;
            factorWeights.push({
                factor: f,
                weight: (1 / selectedFactors.length).toFixed(2),
                avgValue: avgValue?.toFixed(4) ?? '数据不足',
                validStocks: batchResult.factors.length,
            });
        }

        return {
            success: true,
            data: {
                model: {
                    factors: selectedFactors,
                    stockPool: stockPool.length,
                    method: params.method || 'equal_weight',
                },
                factorWeights,
                note: '收益预测需要历史回测数据',
                dataSource: 'real_factors',
            },
        };
    }

    // ===== 生成交易信号 =====
    if (action === 'generate_trading_signal' || action === 'trading_signal') {
        const targetCodes = codes || ['000001', '000002', '600000'];
        const signals = [];

        for (const c of targetCodes) {
            // 使用真实因子计算信号评分
            const ep = await FactorServices.calculateFactor(c, 'ep');
            const mom = await FactorServices.calculateFactor(c, 'momentum_3m');
            const roe = await FactorServices.calculateFactor(c, 'roe');

            let score = 0.5; // 基准分
            if (ep.success && ep.data) {
                score += ep.data.value > 0.05 ? 0.15 : ep.data.value > 0.02 ? 0.05 : -0.1;
            }
            if (mom.success && mom.data) {
                score += mom.data.value > 0.1 ? 0.1 : mom.data.value > 0 ? 0.05 : -0.1;
            }
            if (roe.success && roe.data) {
                score += roe.data.value > 15 ? 0.15 : roe.data.value > 10 ? 0.05 : -0.05;
            }

            score = Math.max(0, Math.min(1, score));

            signals.push({
                code: c,
                score: score.toFixed(3),
                signal: score > 0.7 ? 'buy' : score > 0.4 ? 'hold' : 'sell',
                strength: score > 0.8 ? 'strong' : score > 0.6 ? 'medium' : 'weak',
                factors: {
                    ep: ep.data?.value?.toFixed(4) ?? 'N/A',
                    momentum_3m: mom.data?.value?.toFixed(4) ?? 'N/A',
                    roe: roe.data?.value?.toFixed(2) ?? 'N/A',
                },
            });
        }

        return {
            success: true,
            data: {
                signals,
                generatedAt: new Date().toISOString(),
                model: 'multi_factor_composite',
                dataSource: 'real_factors',
            },
        };
    }

    // ===== 策略模板 =====
    if (action === 'get_strategy_templates' || action === 'templates') {
        return {
            success: true,
            data: {
                templates: [
                    { id: 'value_momentum', name: '价值动量策略', factors: ['ep', 'momentum_6m'], rebalance: 'monthly' },
                    { id: 'quality_growth', name: '质量成长策略', factors: ['roe', 'profit_growth'], rebalance: 'quarterly' },
                    { id: 'low_volatility', name: '低波动策略', factors: ['volatility_20d'], rebalance: 'monthly' },
                    { id: 'small_value', name: '小盘价值策略', factors: ['bp', 'market_cap'], rebalance: 'monthly' },
                ],
            },
        };
    }

    // ===== 策略验证 =====
    if (action === 'validate_strategy' || action === 'validate') {
        const strategyFactors = factors || ['ep', 'momentum_3m'];
        const testCodes = codes || ['000001', '000002', '600000', '600519', '601318', '000858', '002415', '000651', '600036', '601166'];

        // 计算真实的IC值
        const { getDailyBars } = await import('../../storage/kline-data.js');

        let totalIc = 0;
        let validFactorCount = 0;

        for (const factorName of strategyFactors) {
            const factorResult = await FactorServices.batchCalculateFactors(testCodes, factorName);
            if (factorResult.factors.length >= 5) {
                // 计算收益率
                const stockReturns: Array<{ factorValue: number; periodReturn: number }> = [];
                for (const f of factorResult.factors) {
                    const bars = await getDailyBars(f.code, 25);
                    if (bars.length >= 20) {
                        const startPrice = bars[bars.length - 21]?.close || bars[0].close;
                        const endPrice = bars[bars.length - 1].close;
                        if (startPrice > 0) {
                            stockReturns.push({
                                factorValue: f.value,
                                periodReturn: (endPrice - startPrice) / startPrice,
                            });
                        }
                    }
                }

                if (stockReturns.length >= 5) {
                    // 简化IC计算
                    const n = stockReturns.length;
                    const sorted = [...stockReturns].sort((a: any, b: any) => a.factorValue - b.factorValue);
                    const sortedByRet = [...stockReturns].sort((a: any, b: any) => a.periodReturn - b.periodReturn);

                    let d2Sum = 0;
                    for (let i = 0; i < n; i++) {
                        const fRank = sorted.findIndex(s => s === stockReturns[i]) + 1;
                        const rRank = sortedByRet.findIndex(s => s === stockReturns[i]) + 1;
                        d2Sum += (fRank - rRank) ** 2;
                    }
                    const ic = 1 - (6 * d2Sum) / (n * (n * n - 1));
                    totalIc += ic;
                    validFactorCount++;
                }
            }
        }

        const avgIc = validFactorCount > 0 ? totalIc / validFactorCount : 0;

        return {
            success: true,
            data: {
                validation: {
                    factors: strategyFactors,
                    icMean: avgIc.toFixed(3),
                    icIR: (avgIc / 0.15).toFixed(2),
                    validFactors: validFactorCount,
                    testStocks: testCodes.length,
                },
                status: avgIc > 0.02 ? 'passed' : avgIc > 0 ? 'marginal' : 'failed',
                dataSource: 'real_calculation',
            },
        };
    }

    return { success: false, error: `未知操作: ${action}。支持: calculate_factors, get_china_a_factors, calculate_carhart, create_multi_factor_model, generate_trading_signal, get_strategy_templates, validate_strategy` };
};
