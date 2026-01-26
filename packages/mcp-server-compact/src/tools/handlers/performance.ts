import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';

export const performanceManagerTool: ToolDefinition = {
    name: 'performance_manager',
    description: '业绩归因与分析管理',
    category: 'portfolio_management',
    inputSchema: managerSchema,
    tags: ['performance', 'manager'],
    dataSource: 'real',
};

export const performanceManagerHandler: ToolHandler = async (params: any) => {
    const { action, stocks, weights, benchmarkCode = '000300' } = params;

    if ((action === 'calculate' || action === 'attribution' || action === 'get_summary') && stocks && weights) {
        // 简化的业绩归因
        const stockReturns: number[] = [];
        for (const code of stocks) {
            const klineRes = await adapterManager.getKline(code, '101', 20);
            if (klineRes.success && klineRes.data && klineRes.data.length >= 2) {
                const returns = (klineRes.data[klineRes.data.length - 1].close - klineRes.data[0].close) / klineRes.data[0].close;
                stockReturns.push(returns);
            } else {
                stockReturns.push(0);
            }
        }

        // 计算组合收益
        let portfolioReturn = 0;
        for (let i = 0; i < stocks.length; i++) {
            portfolioReturn += (weights[i] || 0) * stockReturns[i];
        }

        // 获取基准收益
        const benchmarkRes = await adapterManager.getKline(benchmarkCode, '101', 20);
        let benchmarkReturn = 0;
        if (benchmarkRes.success && benchmarkRes.data && benchmarkRes.data.length >= 2) {
            benchmarkReturn = (benchmarkRes.data[benchmarkRes.data.length - 1].close - benchmarkRes.data[0].close) / benchmarkRes.data[0].close;
        }

        return {
            success: true,
            data: {
                portfolioReturn: (portfolioReturn * 100).toFixed(2) + '%',
                benchmarkReturn: (benchmarkReturn * 100).toFixed(2) + '%',
                alpha: ((portfolioReturn - benchmarkReturn) * 100).toFixed(2) + '%',
                stockContributions: stocks.map((code: string, i: number) => ({
                    code,
                    weight: weights[i],
                    return: (stockReturns[i] * 100).toFixed(2) + '%',
                    contribution: ((weights[i] || 0) * stockReturns[i] * 100).toFixed(2) + '%'
                }))
            }
        };
    }

    if (action === 'list' || action === 'help') {
        return { success: true, data: { actions: ['calculate', 'attribution', 'get_summary', 'help'] } };
    }

    if (action === 'calculate' || action === 'attribution' || action === 'get_summary') {
        return { success: false, error: '缺少 stocks 和 weights 参数。Usage: performance_manager(action="calculate", stocks=["000001"], weights=[1.0])' };
    }

    return { success: false, error: `Unknown action: ${action}` };
};
