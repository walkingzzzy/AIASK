import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import * as SentimentServices from '../../services/sentiment.js';

export const sentimentManagerTool: ToolDefinition = {
    name: 'sentiment_manager',
    description: '高级情绪分析管理',
    category: 'market_sentiment',
    inputSchema: managerSchema,
    tags: ['sentiment', 'manager'],
    dataSource: 'real',
};

export const sentimentManagerHandler: ToolHandler = async (params: any) => {
    const { action, code } = params;
    if (!code) return { success: false, error: 'Missing code parameter' };

    if (action === 'analyze_sentiment' || action === 'analyze') {
        const quoteRes = await adapterManager.getRealtimeQuote(code);
        const klineRes = await adapterManager.getKline(code, '101', 60);

        if (!quoteRes.success || !quoteRes.data) return { success: false, error: 'Failed to get quote' };
        const klines = klineRes.success && klineRes.data ? klineRes.data : [];

        const result = SentimentServices.analyzeStockSentiment(quoteRes.data, klines);
        return { success: true, data: result };
    }

    // ===== 市场情绪分析 =====
    if (action === 'analyze_market' || action === 'market_sentiment') {
        const indexCodes = ['000001', '399001', '399006']; // 上证、深证、创业板
        const [quotesRes, limitStatsRes, northRes] = await Promise.all([
            adapterManager.getBatchQuotes(indexCodes),
            adapterManager.getLimitUpStatistics(new Date().toISOString().split('T')[0]),
            adapterManager.getNorthFund(1)
        ]);

        const indices = quotesRes.success && quotesRes.data ? quotesRes.data : [];
        const limitStats = limitStatsRes.success && limitStatsRes.data ? limitStatsRes.data : { totalLimitUp: 0, limitDown: 0 };
        const northMoney = northRes.success && northRes.data && northRes.data.length > 0 ? northRes.data[0].total * 100000000 : null;

        const result = SentimentServices.analyzeMarketSentiment(
            indices,
            limitStats.totalLimitUp,
            limitStats.limitDown,
            northMoney
        );
        return { success: true, data: result };
    }

    // ===== 板块情绪分析 =====
    if (action === 'analyze_sector' || action === 'sector_sentiment') {
        const flowRes = await adapterManager.getSectorFlow(20);
        if (!flowRes.success || !flowRes.data) return { success: false, error: '无法获取板块数据' };

        const sectors = flowRes.data;
        const bullishSectors = sectors.filter((s: any) => s.netInflow > 0).slice(0, 5);
        const bearishSectors = sectors.filter((s: any) => s.netInflow < 0).sort((a: any, b: any) => a.netInflow - b.netInflow).slice(0, 5);

        return {
            success: true,
            data: {
                topBullish: bullishSectors.map((s: any) => ({ name: s.name, flow: s.netInflow, change: s.changePercent })),
                topBearish: bearishSectors.map((s: any) => ({ name: s.name, flow: s.netInflow, change: s.changePercent })),
                marketHotspots: bullishSectors.length,
                analysis: `当前资金净流入前五板块：${bullishSectors.map((s: any) => s.name).join(', ')}`
            }
        };
    }

    // ===== 恐惧贪婪指数 =====
    if (action === 'fear_greed_index' || action === 'fear_greed') {
        // 由于缺乏完整的市场宽度数据，使用简化的估算
        const indexCodes = ['000001', '399001'];
        const [quotesRes, limitStatsRes] = await Promise.all([
            adapterManager.getBatchQuotes(indexCodes),
            adapterManager.getLimitUpStatistics()
        ]);

        const indices = quotesRes.success && quotesRes.data ? quotesRes.data : [];
        const limitStats = limitStatsRes.success && limitStatsRes.data ? limitStatsRes.data : { totalLimitUp: 0, limitDown: 0 };

        // 估算上涨/下跌家数 (基于涨跌停比例放大)
        const totalEstimated = 5000;
        const limitRatio = limitStats.totalLimitUp / (limitStats.totalLimitUp + limitStats.limitDown + 1);
        const advances = Math.floor(limitRatio * totalEstimated); // 这是一个粗略估算
        const declines = totalEstimated - advances;

        // 估算波动率 (基于指数涨跌幅绝对值)
        const avgChange = indices.length > 0 ? indices.reduce((sum, i) => sum + Math.abs(i.changePercent), 0) / indices.length : 1;

        const marketData = {
            advances,
            declines,
            newHighs: limitStats.totalLimitUp, // 用涨停数暂代新高
            newLows: limitStats.limitDown, // 用跌停数暂代新低
            volumeRatio: 1, // 暂无成交量比率
            volatility: avgChange
        };

        const result = SentimentServices.calculateFearGreedIndex(marketData);
        return { success: true, data: result };
    }

    // ===== 情绪趋势 =====
    if (action === 'sentiment_trend') {
        // 暂无历史数据，返回 mocking 提示或单点数据
        // 实际项目应从数据库读取历史记录
        return {
            success: true,
            data: {
                message: '历史情绪趋势数据暂未积累',
                current: await sentimentManagerHandler({ action: 'fear_greed_index' }).then((res: any) => res.data)
            }
        };
    }

    // ===== 情绪报告 =====
    if (action === 'generate_sentiment_report' || action === 'sentiment_report') {
        const [market, fearGreed, sector] = await Promise.all([
            sentimentManagerHandler({ action: 'analyze_market' }).then((res: any) => res.data),
            sentimentManagerHandler({ action: 'fear_greed_index' }).then((res: any) => res.data),
            sentimentManagerHandler({ action: 'analyze_sector' }).then((res: any) => res.data)
        ]);

        // 精简板块数据
        const sectorSimplified = sector ? {
            topBullish: sector.topBullish?.slice(0, 3).map((s: any) => ({ name: s.name, flow: s.flow })),
            topBearish: sector.topBearish?.slice(0, 3).map((s: any) => ({ name: s.name, flow: s.flow })),
            marketHotspots: sector.marketHotspots
        } : null;

        return {
            success: true,
            data: {
                marketSentiment: market?.sentiment || 'Unknown',
                fearGreedIndex: {
                    index: fearGreed?.index || 0,
                    level: fearGreed?.level || 'Unknown'
                },
                sectorSentiment: sectorSimplified,
                summary: `市场情绪: ${market?.sentiment || 'Unknown'}, 恐惧贪婪指数: ${fearGreed?.index || 0} (${fearGreed?.level || 'Unknown'})`
            }
        };
    }

    return { success: false, error: `Unknown action: ${action}` };
};
