import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';

export const tradingDataManagerTool: ToolDefinition = {
    name: 'trading_data_manager',
    description: '交易数据管理（北向资金、资金流、融资融券、大宗交易）',
    category: 'market_data',
    inputSchema: managerSchema,
    tags: ['trading', 'data', 'fund_flow'],
    dataSource: 'real',
};

export const tradingDataManagerHandler: ToolHandler = async (params: any) => {
    const { action, code, codes, days = 10, topN = 20, sortBy = 'amount' } = params;

    // ===== 北向资金流向 =====
    if (action === 'get_north_fund' || action === 'north_fund') {
        const res = await adapterManager.getNorthFund(days);
        if (!res.success || !res.data) {
            return { success: false, error: res.error || '获取北向资金失败' };
        }

        // 计算统计数据
        const data = res.data;
        const totalInflow = data.reduce((sum, d) => sum + (d.total || 0), 0);
        const avgInflow = totalInflow / data.length;

        return {
            success: true,
            data: {
                days,
                history: data,
                statistics: {
                    totalNetInflow: Math.round(totalInflow / 1e8) + '亿',
                    avgDailyInflow: Math.round(avgInflow / 1e8) + '亿',
                    inflowDays: data.filter((d: any) => (d.total || 0) > 0).length,
                    outflowDays: data.filter((d: any) => (d.total || 0) < 0).length,
                },
                trend: totalInflow > 0 ? '净流入' : '净流出',
                source: res.source,
            },
        };
    }

    // ===== 北向资金持股 =====
    if (action === 'get_north_fund_holding' || action === 'north_holding') {
        const targetCodes = codes ? (Array.isArray(codes) ? codes : codes.split(',')) : null;

        if (!targetCodes || targetCodes.length === 0) {
            return { success: false, error: '需要指定股票代码列表 codes' };
        }

        const results = await Promise.all(
            targetCodes.map(async (c: string) => {
                const res = await adapterManager.getNorthFundHolding(c);
                return {
                    code: c,
                    success: res.success,
                    data: res.data,
                };
            })
        );

        const holdings = results
            .filter((r: any) => r.success && r.data)
            .map((r: any) => ({
                code: r.code,
                shares: r.data?.shares,
                ratio: r.data?.ratio,
                change: r.data?.change,
            }));

        return {
            success: true,
            data: {
                holdings,
                count: holdings.length,
            },
        };
    }

    // ===== 北向资金排行 =====
    if (action === 'get_north_fund_top' || action === 'north_top') {
        const res = await adapterManager.getNorthFundTop(topN);
        if (!res.success || !res.data) {
            return { success: false, error: res.error || '获取北向资金排行失败' };
        }

        return {
            success: true,
            data: {
                ranking: res.data,
                count: res.data.length,
                source: res.source,
            },
        };
    }

    // ===== 个股资金流向 =====
    if (action === 'get_fund_flow' || action === 'fund_flow') {
        if (!code) return { success: false, error: '需要股票代码' };

        const res = await adapterManager.getFundFlow(code);
        if (!res.success || !res.data) {
            return { success: false, error: res.error || '获取资金流向失败' };
        }

        const flow = res.data;
        const totalInflow = (flow.superLargeInflow || 0) + (flow.largeInflow || 0) +
            (flow.middleInflow || 0);

        return {
            success: true,
            data: {
                code,
                mainNetInflow: flow.mainNetInflow,
                retailNetInflow: flow.retailNetInflow,
                superLargeInflow: flow.superLargeInflow,
                largeInflow: flow.largeInflow,
                totalInflow,
                mainForce: (flow.mainNetInflow || 0) > 0 ? '主力流入' : '主力流出',
                source: res.source,
            },
        };
    }

    // ===== 批量资金流向 =====
    if (action === 'get_batch_fund_flow' || action === 'batch_flow') {
        const targetCodes = codes ? (Array.isArray(codes) ? codes : codes.split(',')) : null;
        if (!targetCodes || targetCodes.length === 0) {
            return { success: false, error: '需要股票代码列表 codes' };
        }

        const results = await Promise.all(
            targetCodes.slice(0, 20).map(async (c: string) => {
                const res = await adapterManager.getFundFlow(c);
                return {
                    code: c,
                    mainNetInflow: res.data?.mainNetInflow || 0,
                    success: res.success,
                };
            })
        );

        // 按主力净流入排序
        const sorted = results.filter((r: any) => r.success).sort((a: any, b: any) => b.mainNetInflow - a.mainNetInflow);

        return {
            success: true,
            data: {
                flows: sorted,
                topInflow: sorted.slice(0, 5),
                topOutflow: sorted.slice(-5).reverse(),
            },
        };
    }

    // ===== 融资融券数据 =====
    if (action === 'get_margin_data' || action === 'margin') {
        const res = await adapterManager.getMarginRanking(topN, sortBy === 'buy' ? 'buy' : 'balance');
        if (!res.success) {
            return { success: false, error: res.error || '获取融资融券数据失败' };
        }

        return {
            success: true,
            data: {
                sortBy,
                ranking: res.data,
                source: res.source,
            },
        };
    }

    // ===== 大宗交易数据 =====
    if (action === 'get_block_trades' || action === 'block') {
        const date = params.date;
        const res = await adapterManager.getBlockTrades(date);
        if (!res.success) {
            return { success: false, error: res.error || '获取大宗交易数据失败' };
        }

        // 统计分析
        const trades = res.data || [];
        const totalAmount = trades.reduce((sum: number, t: any) => sum + (t.amount || 0), 0);
        const premiumTrades = trades.filter((t: any) => t.premium && t.premium > 0);
        const discountTrades = trades.filter((t: any) => t.premium && t.premium < 0);

        return {
            success: true,
            data: {
                date: date || new Date().toISOString().slice(0, 10),
                trades: trades.slice(0, topN),
                statistics: {
                    totalTrades: trades.length,
                    totalAmount: Math.round(totalAmount / 1e8) + '亿',
                    premiumCount: premiumTrades.length,
                    discountCount: discountTrades.length,
                },
                source: res.source,
            },
        };
    }

    return { success: false, error: `未知操作: ${action}。支持: north_fund, north_holding, north_top, fund_flow, batch_flow, margin, block` };
};
