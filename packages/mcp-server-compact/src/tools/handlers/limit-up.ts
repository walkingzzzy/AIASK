import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import { callAkshareMcpTool } from '../../adapters/akshare-mcp-client.js';
import { buildManagerHelp } from './manager-help.js';

export const limitUpManagerTool: ToolDefinition = {
    name: 'limit_up_manager',
    description: '涨停板分析管理（涨停池、统计、原因分析、连板分析）',
    category: 'market_sentiment',
    inputSchema: managerSchema,
    tags: ['limit_up', 'manager', 'analysis'],
    dataSource: 'real',
};

export const limitUpManagerHandler: ToolHandler = async (params: any) => {
    const { action, date, code, topN = 20 } = params;
    const help = buildManagerHelp(action, {
        actions: [
            'get_limit_up_pool',
            'pool',
            'get_limit_up_statistics',
            'statistics',
            'stats',
            'analyze_limit_up_reason',
            'reason',
            'predict_continuation',
            'continuation',
            'continuous',
            'analyze_auction',
            'auction',
        ],
        description: '涨停板分析入口，action 为空时返回可用动作。',
    });
    if (help) return help;

    // ===== 涨停池 =====
    if (action === 'get_limit_up_pool' || action === 'pool' || !action) {
        const res = await adapterManager.getLimitUpStocks(date);
        if (!res.success || !res.data) {
            return { success: false, error: res.error || '获取涨停数据失败' };
        }
        return {
            success: true,
            data: {
                date: date || new Date().toISOString().slice(0, 10),
                limitUpStocks: res.data,
                count: res.data.length,
                source: res.source,
            },
        };
    }

    // ===== 涨停统计 =====
    if (action === 'get_limit_up_statistics' || action === 'statistics' || action === 'stats') {
        const res = await adapterManager.getLimitUpStocks(date);
        if (!res.success || !res.data) {
            return { success: false, error: '获取涨停数据失败' };
        }

        const stocks = res.data;

        // 统计分析
        const firstBoard = stocks.filter((s: any) => !s.continuousDays || s.continuousDays === 1);
        const secondBoard = stocks.filter((s: any) => s.continuousDays === 2);
        const thirdBoardPlus = stocks.filter((s: any) => s.continuousDays && s.continuousDays >= 3);

        // 涨停时间分布
        const timeDistribution: Record<string, number> = {
            '开盘涨停': 0,
            '早盘涨停': 0,
            '午后涨停': 0,
            '尾盘涨停': 0,
        };

        stocks.forEach((s: any) => {
            const limitTime = s.firstLimitTime || '';
            if (limitTime.startsWith('09:25') || limitTime.startsWith('09:30')) {
                timeDistribution['开盘涨停']++;
            } else if (limitTime < '11:30') {
                timeDistribution['早盘涨停']++;
            } else if (limitTime < '14:30') {
                timeDistribution['午后涨停']++;
            } else {
                timeDistribution['尾盘涨停']++;
            }
        });

        // 板块分布
        const sectorDistribution: Record<string, number> = {};
        stocks.forEach((s: any) => {
            const sector = s.industry || s.concept || '未分类';
            sectorDistribution[sector] = (sectorDistribution[sector] || 0) + 1;
        });

        const topSectors = Object.entries(sectorDistribution)
            .sort((a: any, b: any) => b[1] - a[1])
            .slice(0, 5)
            .map(([name, count]) => ({ name, count }));

        return {
            success: true,
            data: {
                date: date || new Date().toISOString().slice(0, 10),
                summary: {
                    total: stocks.length,
                    firstBoard: firstBoard.length,
                    secondBoard: secondBoard.length,
                    thirdBoardPlus: thirdBoardPlus.length,
                },
                timeDistribution,
                topSectors,
                marketSentiment: stocks.length > 50 ? '强势' : stocks.length > 30 ? '活跃' : stocks.length > 15 ? '一般' : '冷淡',
            },
        };
    }

    // ===== 涨停原因分析 =====
    if (action === 'analyze_limit_up_reason' || action === 'reason') {
        if (!code) return { success: false, error: '需要股票代码' };

        // 获取涨停数据
        const limitRes = await adapterManager.getLimitUpStocks(date);
        const limitStock = limitRes.data?.find(s => s.code === code);
        const end = date ? new Date(date) : new Date();
        const start = new Date(end);
        start.setDate(end.getDate() - 7);
        const noticesRes = await callAkshareMcpTool<{
            events: Array<{ title: string; type: string; date: string; url?: string }>;
        }>('get_stock_notices', {
            start_date: start.toISOString().slice(0, 10),
            end_date: end.toISOString().slice(0, 10),
            stock_code: code,
        });

        if (!noticesRes.success || !noticesRes.data?.events?.length) {
            return {
                success: false,
                error: noticesRes.error || '未找到可解释涨停的公告事件',
            };
        }

        const reasons = noticesRes.data.events
            .slice(0, 5)
            .map((e: any) => e.title || e.type)
            .filter(Boolean);

        if (!reasons.length) {
            return { success: false, error: '公告事件数据不足，无法形成原因分析' };
        }

        return {
            success: true,
            data: {
                code,
                name: limitStock?.name || code,
                industry: limitStock?.industry,
                concept: limitStock?.concept,
                limitUpInfo: limitStock || null,
                reasons,
                source: 'akshare_notice',
            },
        };
    }

    // ===== 连板股分析 =====
    if (action === 'predict_continuation' || action === 'continuation' || action === 'continuous') {
        const res = await adapterManager.getLimitUpStocks(date);
        if (!res.success || !res.data) {
            return { success: false, error: '获取涨停数据失败' };
        }

        // 筛选连板股
        const continuousStocks = res.data
            .filter((s: any) => s.continuousDays && s.continuousDays >= 2)
            .sort((a: any, b: any) => (b.continuousDays || 0) - (a.continuousDays || 0));

        // 分析连板强度
        const analysis = continuousStocks.slice(0, topN).map((s: any) => {
            const boards = s.continuousDays || 0;
            let continuationProbability = '中';
            if (boards >= 5) continuationProbability = '低（高位风险大）';
            else if (boards >= 3) continuationProbability = '中等';
            else if (boards === 2) continuationProbability = '较高（需看封单）';

            return {
                code: s.code,
                name: s.name,
                continuousBoards: boards,
                firstLimitTime: s.firstLimitTime,
                continuationProbability,
            };
        });

        return {
            success: true,
            data: {
                date: date || new Date().toISOString().slice(0, 10),
                continuousStocks: analysis,
                totalContinuous: continuousStocks.length,
                highestBoards: continuousStocks[0]?.continuousDays || 0,
                marketHeight: continuousStocks[0] ? `${continuousStocks[0].name}(${continuousStocks[0].continuousDays}板)` : '无',
            },
        };
    }

    // ===== 竞价分析 =====
    if (action === 'analyze_auction' || action === 'auction') {
        return { success: false, error: '竞价实时数据未接入，无法进行竞价分析' };
    }

    return { success: false, error: `未知操作: ${action}。支持: pool, statistics, reason, continuation, auction` };
};
