import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import * as RiskServices from '../../services/risk-model.js';

export const riskManagerTool: ToolDefinition = {
    name: 'risk_manager',
    description: '风险管理',
    category: 'portfolio_management',
    inputSchema: managerSchema,
    dataSource: 'calculated_estimate'
};

async function buildMarketContext() {
    const assumptions: string[] = [];
    const [sectorFlowRes, klineRes] = await Promise.all([
        adapterManager.getSectorFlow(50),
        adapterManager.getKline('000001', '101', 60),
    ]);

    const sectors = sectorFlowRes.success && sectorFlowRes.data ? sectorFlowRes.data : [];
    let advances = 1;
    let declines = 1;
    if (sectors.length > 0) {
        advances = sectors.filter((s: any) => (s.changePercent || 0) > 0).length;
        declines = sectors.filter((s: any) => (s.changePercent || 0) < 0).length;
        assumptions.push('市场宽度使用板块涨跌家数近似');
    } else {
        assumptions.push('板块数据不可用，市场宽度使用最小占位值');
    }

    const bars = klineRes.success && klineRes.data ? klineRes.data : [];
    const volumes = bars.map((b: any) => b.volume).filter((v: any) => Number.isFinite(v));
    const volumeRatio = volumes.length >= 20
        ? volumes[volumes.length - 1] / (volumes.slice(-20).reduce((a: any, b: any) => a + b, 0) / 20)
        : 1;
    if (volumes.length < 20) {
        assumptions.push('成交量样本不足，成交量比率使用默认值1');
    }

    return {
        marketBreadth: { advances, declines },
        volumeRatio: Number.isFinite(volumeRatio) ? volumeRatio : 1,
        assumptions,
    };
}

export const riskManagerHandler: ToolHandler = async (params: any) => {
    const { action, stocks, weights, code, confidence } = params;

    // ===== 风险计算 =====
    if (action === 'calculate_risk' && stocks && weights) {
        const report = await RiskServices.generateRiskReport(stocks, weights);
        if ('error' in report) return { success: false, error: report.error };
        const stressTests = Array.isArray(report.stressTests)
            ? report.stressTests.map((s: any) => ({ ...s, isSimulated: true }))
            : report.stressTests;
        return {
            success: true,
            data: {
                ...report,
                stressTests,
                dataSource: 'calculated_estimate',
                assumptions: [
                    'Barra因子暴露为简化估算（固定因子占比）',
                    '压力测试使用预设情景冲击，不含流动性与相关性二阶效应',
                    '行业暴露基于静态行业映射'
                ]
            }
        };
    }

    // ===== VaR 分析 =====
    if (action === 'var_analysis' || action === 'calculate_var') {
        const conf = confidence || 0.95;
        const holdingPeriod = params.period || 1;
        const targetStocks = stocks || ['000001', '600000'];

        // 使用真实的历史收益率计算VaR
        const { getDailyBars } = await import('../../storage/kline-data.js');

        const allReturns: number[] = [];
        for (const stock of targetStocks) {
            const bars = await getDailyBars(stock, 60);
            for (let i = 1; i < bars.length; i++) {
                if (bars[i - 1].close > 0) {
                    allReturns.push((bars[i].close - bars[i - 1].close) / bars[i - 1].close);
                }
            }
        }

        if (allReturns.length < 20) {
            return { success: false, error: '历史数据不足，无法计算VaR' };
        }

        // 排序计算历史VaR
        const sortedReturns = [...allReturns].sort((a: any, b: any) => a - b);
        const varIndex = Math.floor(sortedReturns.length * (1 - conf));
        const historicalVaR = Math.abs(sortedReturns[varIndex] || 0);

        // 参数VaR（正态分布假设）
        const mean = allReturns.reduce((a: any, b: any) => a + b, 0) / allReturns.length;
        const variance = allReturns.reduce((a: any, b: any) => a + (b - mean) ** 2, 0) / allReturns.length;
        const std = Math.sqrt(variance);
        const zScore = conf === 0.99 ? 2.33 : conf === 0.95 ? 1.65 : 1.28;
        const parametricVaR = Math.abs(mean - zScore * std);

        // 条件VaR（超过VaR的平均损失）
        const tailReturns = sortedReturns.slice(0, varIndex + 1);
        const cvar = tailReturns.length > 0
            ? Math.abs(tailReturns.reduce((a: any, b: any) => a + b, 0) / tailReturns.length)
            : parametricVaR * 1.3;

        return {
            success: true,
            data: {
                confidence: `${conf * 100}%`,
                holdingPeriod: `${holdingPeriod}天`,
                historicalVaR: `${(historicalVaR * 100).toFixed(2)}%`,
                parametricVaR: `${(parametricVaR * 100).toFixed(2)}%`,
                conditionalVaR: `${(cvar * 100).toFixed(2)}%`,
                sampleSize: allReturns.length,
                dataSource: 'real_kline_data',
            },
        };
    }

    // ===== 压力测试 =====
    if (action === 'stress_test' || action === 'stress') {
        const targetStocks = stocks || ['000001', '600000'];
        const { getDailyBars } = await import('../../storage/kline-data.js');

        // 计算股票的历史波动率来估算压力影响
        let totalVolatility = 0;
        let validCount = 0;
        for (const stock of targetStocks) {
            const bars = await getDailyBars(stock, 60);
            if (bars.length >= 20) {
                const returns = [];
                for (let i = 1; i < bars.length; i++) {
                    if (bars[i - 1].close > 0) {
                        returns.push((bars[i].close - bars[i - 1].close) / bars[i - 1].close);
                    }
                }
                if (returns.length > 0) {
                    const mean = returns.reduce((a: number, b: number) => a + b, 0) / returns.length;
                    const variance = returns.reduce((a: number, b: number) => a + (b - mean) ** 2, 0) / returns.length;
                    totalVolatility += Math.sqrt(variance);
                    validCount++;
                }
            }
        }

        const avgVolatility = validCount > 0 ? totalVolatility / validCount : 0.02;
        const beta = 1.0; // 简化假设

        const scenarios = [
            { name: '市场暴跌', marketChange: -0.15, portfolioImpact: `${(-15 * beta).toFixed(1)}%` },
            { name: '利率上升', rateChange: 0.01, portfolioImpact: `${(-3 * beta).toFixed(1)}%` },
            { name: '流动性危机', volumeDrop: -0.5, portfolioImpact: `${(-10 * avgVolatility * 100).toFixed(1)}%` },
            { name: '行业冲击', sectorDrop: -0.2, portfolioImpact: `${(-7 * beta).toFixed(1)}%` },
        ];
        const marketContext = await buildMarketContext();
        return {
            success: true,
            data: {
                scenarios,
                avgVolatility: `${(avgVolatility * 100).toFixed(2)}%`,
                analyzedAt: new Date().toISOString(),
                marketContext,
                isSimulated: true,
                dataSource: 'simulated',
                assumptions: [
                    '压力情景为固定冲击，收益影响采用线性近似',
                    '组合Beta简化为1.0，未建模个股差异'
                ].concat(marketContext.assumptions)
            }
        };
    }

    // ===== 相关性分析 =====
    if (action === 'correlation_analysis' || action === 'correlation') {
        const stockList = stocks || ['000001', '600000', '000002'];
        const { getDailyBars } = await import('../../storage/kline-data.js');

        // 计算每只股票的收益率序列
        const returnSeries: Record<string, number[]> = {};
        for (const stock of stockList) {
            const bars = await getDailyBars(stock, 60);
            const returns: number[] = [];
            for (let i = 1; i < bars.length; i++) {
                if (bars[i - 1].close > 0) {
                    returns.push((bars[i].close - bars[i - 1].close) / bars[i - 1].close);
                }
            }
            returnSeries[stock] = returns;
        }

        // 计算Pearson相关系数
        const calcCorrelation = (arr1: number[], arr2: number[]): number => {
            const n = Math.min(arr1.length, arr2.length);
            if (n < 10) return 0;
            const mean1 = arr1.slice(0, n).reduce((a: any, b: any) => a + b, 0) / n;
            const mean2 = arr2.slice(0, n).reduce((a: any, b: any) => a + b, 0) / n;
            let cov = 0, var1 = 0, var2 = 0;
            for (let i = 0; i < n; i++) {
                cov += (arr1[i] - mean1) * (arr2[i] - mean2);
                var1 += (arr1[i] - mean1) ** 2;
                var2 += (arr2[i] - mean2) ** 2;
            }
            return var1 > 0 && var2 > 0 ? cov / Math.sqrt(var1 * var2) : 0;
        };

        let totalCorr = 0;
        let corrCount = 0;
        const correlations = stockList.map((s1: string) => ({
            stock: s1,
            correlations: stockList.map((s2: string) => {
                if (s1 === s2) return { with: s2, value: '1.00' };
                const corr = calcCorrelation(returnSeries[s1] || [], returnSeries[s2] || []);
                totalCorr += corr;
                corrCount++;
                return { with: s2, value: corr.toFixed(2) };
            }),
        }));

        return {
            success: true,
            data: {
                correlations,
                avgCorrelation: corrCount > 0 ? (totalCorr / corrCount).toFixed(2) : '0.00',
                dataSource: 'real_calculation'
            }
        };
    }

    // ===== 风险敞口报告 =====
    if (action === 'exposure_report' || action === 'exposure') {
        const targetStocks = stocks || ['000001', '600000'];
        const { getDailyBars } = await import('../../storage/kline-data.js');

        // 计算组合与市场的Beta（简化：使用上证指数作为基准）
        let avgBeta = 1.0;
        // 这里简化处理，实际需要市场指数数据

        return {
            success: true,
            data: {
                exposures: {
                    market: { beta: avgBeta.toFixed(2), exposure: avgBeta > 1.2 ? 'high' : avgBeta > 0.8 ? 'moderate' : 'low' },
                    sector: { concentration: `前${Math.min(3, targetStocks.length)}股票占比100%`, diversification: targetStocks.length > 5 ? 'moderate' : 'low' },
                    style: { note: '需要因子数据进行风格分析' },
                },
                recommendations: targetStocks.length < 5
                    ? ['增加股票数量提高分散化', '考虑跨行业配置']
                    : ['保持当前分散化水平'],
                dataSource: 'calculated_estimate',
                assumptions: [
                    '组合Beta使用简化假设（未引入市场指数回归）',
                    '行业集中度按持仓数量粗略估计'
                ],
            },
        };
    }

    if (action === 'list' || action === 'help') {
        return { success: true, data: { actions: ['calculate_risk', 'var_analysis', 'stress_test', 'correlation_analysis', 'exposure_report', 'help'] } };
    }

    return { success: false, error: `未知操作: ${action}。支持: calculate_risk, var_analysis, stress_test, correlation_analysis, exposure_report` };
};
