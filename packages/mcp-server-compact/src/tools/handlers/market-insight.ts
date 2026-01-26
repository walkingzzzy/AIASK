import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import { callAkshareMcpTool } from '../../adapters/akshare-mcp-client.js';
import { buildManagerHelp } from './manager-help.js';

export const marketInsightManagerTool: ToolDefinition = {
    name: 'market_insight_manager',
    description: '市场洞察管理（龙虎榜、涨停、大宗交易、热点概念、交易机会）',
    category: 'market_sentiment',
    inputSchema: managerSchema,
    tags: ['insight', 'manager', 'market'],
    dataSource: 'real',
};

interface BlockData {
    code: string;
    name: string;
    changePercent?: number;
    change?: number;
    stockCount?: number;
}

export const marketInsightManagerHandler: ToolHandler = async (params: any) => {
    const { action, date, topN = 10, type = 'industry' } = params;
    const help = buildManagerHelp(action, {
        actions: [
            'get_dragon_tiger',
            'dragon_tiger',
            'get_limit_up',
            'limit_up',
            'get_block_trades',
            'block_trades',
            'get_margin_ranking',
            'margin',
            'get_market_news',
            'news',
            'get_hot_concepts',
            'hot_concepts',
            'concepts',
            'get_industry_trends',
            'industry_trends',
            'trends',
            'get_trading_opportunities',
            'opportunities',
            'smart_monitor',
            'monitor',
            'detect_anomalies',
            'anomalies',
            'overview',
        ],
        description: '市场洞察入口，action 为空时返回可用动作。',
    });
    if (help) return help;

    // ===== 龙虎榜 =====
    if (action === 'get_dragon_tiger' || action === 'dragon_tiger') {
        const res = await adapterManager.getDragonTiger(date);
        return res.success
            ? { success: true, data: { dragonTiger: res.data, source: res.source } }
            : { success: false, error: res.error };
    }

    // ===== 涨停股 =====
    if (action === 'get_limit_up' || action === 'limit_up') {
        const res = await adapterManager.getLimitUpStocks(date);
        return res.success
            ? { success: true, data: { limitUpStocks: res.data, source: res.source } }
            : { success: false, error: res.error };
    }

    // ===== 大宗交易 =====
    if (action === 'get_block_trades' || action === 'block_trades') {
        const res = await adapterManager.getBlockTrades(date);
        return res.success
            ? { success: true, data: { blockTrades: res.data, source: res.source } }
            : { success: false, error: res.error };
    }

    // ===== 融资融券排名 =====
    if (action === 'get_margin_ranking' || action === 'margin') {
        const res = await adapterManager.getMarginRanking(topN, 'balance');
        return res.success
            ? { success: true, data: { marginRanking: res.data, source: res.source } }
            : { success: false, error: res.error };
    }

    // ===== 市场新闻 =====
    if (action === 'get_market_news' || action === 'news') {
        const res = await adapterManager.getMarketNews(topN);
        return res.success
            ? { success: true, data: { news: res.data, source: res.source } }
            : { success: false, error: res.error };
    }

    // ===== 热门概念 =====
    if (action === 'get_hot_concepts' || action === 'hot_concepts' || action === 'concepts') {
        const blocksRes = await callAkshareMcpTool<BlockData[]>('get_concept_fund_flow', { top_n: 50 });
        if (!blocksRes.success || !blocksRes.data) {
            return { success: false, error: '获取概念板块失败' };
        }

        // 按涨幅排序
        const sorted = blocksRes.data.sort((a: BlockData, b: BlockData) => (b.changePercent || 0) - (a.changePercent || 0));
        const hotConcepts = sorted.slice(0, topN).map((c: BlockData, idx: number) => ({
            rank: idx + 1,
            name: c.name,
            code: c.code,
            change: c.changePercent,
            stockCount: c.stockCount,
            isHot: (c.changePercent || 0) > 2,
        }));

        return {
            success: true,
            data: {
                hotConcepts,
                coldConcepts: sorted.slice(-5).reverse().map((c: BlockData) => ({
                    name: c.name,
                    change: c.changePercent,
                })),
                totalConcepts: sorted.length,
                hotCount: sorted.filter((c: BlockData) => (c.changePercent || 0) > 2).length,
            },
        };
    }

    // ===== 行业趋势 =====
    if (action === 'get_industry_trends' || action === 'industry_trends' || action === 'trends') {
        const blocksRes = await callAkshareMcpTool<BlockData[]>('get_sector_fund_flow', { top_n: 50 });
        if (!blocksRes.success || !blocksRes.data) {
            return { success: false, error: '获取行业数据失败' };
        }

        const industries = blocksRes.data;
        const gainers = industries.filter((i: BlockData) => (i.changePercent || 0) > 0).length;
        const losers = industries.length - gainers;

        // 分组
        const strongIndustries = industries.filter((i: BlockData) => (i.changePercent || 0) > 2).slice(0, 5);
        const weakIndustries = industries.filter((i: BlockData) => (i.changePercent || 0) < -2).slice(0, 5);

        return {
            success: true,
            data: {
                summary: {
                    total: industries.length,
                    gainers,
                    losers,
                    ratio: `${gainers}:${losers}`,
                },
                strongIndustries: strongIndustries.map((i: BlockData) => ({ name: i.name, change: i.changePercent })),
                weakIndustries: weakIndustries.map((i: BlockData) => ({ name: i.name, change: i.changePercent })),
                marketTrend: gainers > losers * 1.5 ? '普涨' : losers > gainers * 1.5 ? '普跌' : '分化',
            },
        };
    }

    // ===== 交易机会 =====
    if (action === 'get_trading_opportunities' || action === 'opportunities') {
        // 聚合多数据源识别机会
        const [limitUpRes, dragonRes, marginRes] = await Promise.all([
            adapterManager.getLimitUpStocks(date),
            adapterManager.getDragonTiger(date),
            adapterManager.getMarginRanking(10, 'buy'),
        ]);

        const opportunities: Array<{
            type: string;
            code: string;
            name: string;
            reason: string;
            risk: string;
        }> = [];

        // 龙虎榜机构买入
        if (dragonRes.success && dragonRes.data) {
            const institutionBuys = dragonRes.data
                .filter((d: any) => d.buyAmount && d.institutionBuy)
                .slice(0, 3);
            institutionBuys.forEach((d: any) => {
                opportunities.push({
                    type: '龙虎榜机构买入',
                    code: d.code,
                    name: d.name,
                    reason: `机构买入 ${d.institutionBuy}`,
                    risk: '中',
                });
            });
        }

        // 首板涨停
        if (limitUpRes.success && limitUpRes.data) {
            const firstBoards = limitUpRes.data
                .filter((s: any) => !s.continuousLimitUp || s.continuousLimitUp === 1)
                .slice(0, 3);
            firstBoards.forEach((s: any) => {
                opportunities.push({
                    type: '首板涨停',
                    code: s.code,
                    name: s.name,
                    reason: '首次涨停，关注次日走势',
                    risk: '高',
                });
            });
        }

        // 融资增仓
        if (marginRes.success && marginRes.data) {
            const marginBuys = marginRes.data.slice(0, 3);
            marginBuys.forEach((m: any) => {
                opportunities.push({
                    type: '融资增仓',
                    code: m.code,
                    name: m.name,
                    reason: '融资资金流入',
                    risk: '中',
                });
            });
        }

        return {
            success: true,
            data: {
                date: date || new Date().toISOString().slice(0, 10),
                opportunities: opportunities.slice(0, topN),
                totalOpportunities: opportunities.length,
                disclaimer: '以上机会仅供参考，不构成投资建议',
            },
        };
    }

    // ===== 智能监控 =====
    if (action === 'smart_monitor' || action === 'monitor') {
        // 综合监控市场异动
        const [limitUpRes, blocksRes] = await Promise.all([
            adapterManager.getLimitUpStocks(date),
            callAkshareMcpTool<BlockData[]>('get_concept_fund_flow', { top_n: 30 }),
        ]);

        const alerts: string[] = [];

        // 涨停数量监控
        if (limitUpRes.success && limitUpRes.data) {
            const count = limitUpRes.data.length;
            if (count > 100) alerts.push(`涨停数量达 ${count} 只，市场情绪极度亢奋`);
            else if (count > 50) alerts.push(`涨停数量 ${count} 只，市场活跃`);
            else if (count < 10) alerts.push(`涨停数量仅 ${count} 只，市场低迷`);
        }

        // 板块异动监控
        if (blocksRes.success && blocksRes.data) {
            const hotBlocks = blocksRes.data.filter((b: BlockData) => (b.changePercent || 0) > 5);
            if (hotBlocks.length > 3) {
                alerts.push(`${hotBlocks.length} 个概念板块涨幅超5%：${hotBlocks.slice(0, 3).map((b: BlockData) => b.name).join('、')}`);
            }
        }

        return {
            success: true,
            data: {
                timestamp: new Date().toISOString(),
                alerts,
                alertCount: alerts.length,
                marketStatus: alerts.length > 2 ? '异动频繁' : alerts.length > 0 ? '正常' : '平静',
            },
        };
    }

    // ===== 异常检测 =====
    if (action === 'detect_anomalies' || action === 'anomalies') {
        // 检测市场异常
        const [limitUpRes, dragonRes] = await Promise.all([
            adapterManager.getLimitUpStocks(date),
            adapterManager.getDragonTiger(date),
        ]);

        const anomalies: Array<{ type: string; description: string; severity: string }> = [];

        // 涨停异常
        if (limitUpRes.success && limitUpRes.data) {
            const highBoards = limitUpRes.data.filter((s: any) => s.continuousLimitUp && s.continuousLimitUp >= 5);
            if (highBoards.length > 0) {
                anomalies.push({
                    type: '连板妖股',
                    description: `${highBoards.length} 只股票连板5日以上`,
                    severity: 'warning',
                });
            }
        }

        // 龙虎榜异常
        if (dragonRes.success && dragonRes.data) {
            const bigSells = dragonRes.data.filter((d: any) => d.sellAmount && d.sellAmount > 5e8);
            if (bigSells.length > 0) {
                anomalies.push({
                    type: '大额卖出',
                    description: `${bigSells.length} 只股票龙虎榜卖出超5亿`,
                    severity: 'alert',
                });
            }
        }

        return {
            success: true,
            data: {
                date: date || new Date().toISOString().slice(0, 10),
                anomalies,
                hasWarning: anomalies.some(a => a.severity === 'warning'),
                hasAlert: anomalies.some(a => a.severity === 'alert'),
            },
        };
    }

    // ===== 市场概览 =====
    if (action === 'overview' || !action) {
        const [dragon, limitUp, margin, concepts] = await Promise.all([
            adapterManager.getDragonTiger(date),
            adapterManager.getLimitUpStocks(date),
            adapterManager.getMarginRanking(5, 'balance'),
            callAkshareMcpTool<BlockData[]>('get_concept_fund_flow', { top_n: 20 }),
        ]);

        const hotConcepts = concepts.success && concepts.data
            ? concepts.data.sort((a: BlockData, b: BlockData) => (b.changePercent || 0) - (a.changePercent || 0)).slice(0, 5)
            : [];

        return {
            success: true,
            data: {
                dragonTiger: dragon.success ? dragon.data?.slice(0, 5) : null,
                limitUp: limitUp.success ? { count: limitUp.data?.length, top5: limitUp.data?.slice(0, 5) } : null,
                marginTop5: margin.success ? margin.data : null,
                hotConcepts: hotConcepts.map((c: BlockData) => ({ name: c.name, change: c.changePercent })),
            },
        };
    }

    return { success: false, error: `未知操作: ${action}。支持: dragon_tiger, limit_up, block_trades, margin, news, hot_concepts, industry_trends, opportunities, monitor, anomalies, overview` };
};
