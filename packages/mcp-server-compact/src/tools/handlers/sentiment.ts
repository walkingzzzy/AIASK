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
    dataSource: 'calculated_estimate',
};

async function buildMarketBreadthMetrics() {
    const assumptions: string[] = [];
    const [limitStatsRes, sectorFlowRes, klineRes] = await Promise.all([
        adapterManager.getLimitUpStatistics(),
        adapterManager.getSectorFlow(50),
        adapterManager.getKline('000001', '101', 60),
    ]);

    const limitStats = limitStatsRes.success && limitStatsRes.data
        ? limitStatsRes.data
        : { totalLimitUp: 0, limitDown: 0 };
    if (!limitStatsRes.success) {
        assumptions.push('涨跌停统计获取失败，使用0作为新高/新低占位');
    }

    const sectors = sectorFlowRes.success && sectorFlowRes.data ? sectorFlowRes.data : [];
    let advances = 1;
    let declines = 1;
    if (sectors.length > 0) {
        advances = sectors.filter((s: any) => (s.changePercent || 0) > 0).length;
        declines = sectors.filter((s: any) => (s.changePercent || 0) < 0).length;
        assumptions.push('使用板块涨跌家数近似市场宽度');
    } else {
        assumptions.push('板块数据为空，使用最小宽度占位');
    }

    const bars = klineRes.success && klineRes.data ? klineRes.data : [];
    const volumes = bars.map((b: any) => b.volume).filter((v: any) => Number.isFinite(v));
    const volumeRatio = volumes.length >= 20
        ? volumes[volumes.length - 1] / (volumes.slice(-20).reduce((a: any, b: any) => a + b, 0) / 20)
        : 1;
    if (volumes.length < 20) {
        assumptions.push('指数成交量样本不足，成交量比率使用默认值1');
    }

    const returns = bars.length >= 2
        ? bars.slice(1).map((b, i) => {
            const prev = bars[i].close;
            return prev > 0 ? (b.close - prev) / prev : 0;
        })
        : [];
    const avgReturn = returns.length > 0 ? returns.reduce((a: any, b: any) => a + b, 0) / returns.length : 0;
    const variance = returns.length > 1
        ? returns.reduce((a: any, b: any) => a + (b - avgReturn) ** 2, 0) / (returns.length - 1)
        : 0;
    const volatility = Math.sqrt(variance) * 100;
    if (returns.length < 2) {
        assumptions.push('指数波动率样本不足，波动率使用默认值1');
    }

    return {
        advances,
        declines,
        newHighs: limitStats.totalLimitUp || 0,
        newLows: limitStats.limitDown || 0,
        volumeRatio: Number.isFinite(volumeRatio) ? volumeRatio : 1,
        volatility: Number.isFinite(volatility) ? volatility : 1,
        assumptions,
    };
}

export const sentimentManagerHandler: ToolHandler = async (params: any) => {
    const { action, code } = params;

    if (action === 'analyze_sentiment' || action === 'analyze') {
        if (!code) return { success: false, error: 'Missing code parameter' };
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
        const marketMetrics = await buildMarketBreadthMetrics();
        const marketData = {
            advances: marketMetrics.advances,
            declines: marketMetrics.declines,
            newHighs: marketMetrics.newHighs,
            newLows: marketMetrics.newLows,
            volumeRatio: marketMetrics.volumeRatio,
            volatility: marketMetrics.volatility,
        };

        const result = SentimentServices.calculateFearGreedIndex(marketData);
        return {
            success: true,
            data: {
                ...result,
                dataSource: 'calculated_estimate',
                assumptions: marketMetrics.assumptions
            }
        };
    }

    // ===== 情绪趋势 =====
    if (action === 'sentiment_trend') {
        // 暂无历史数据，返回 mocking 提示或单点数据
        // 实际项目应从数据库读取历史记录
        return {
            success: true,
            data: {
                message: '历史情绪趋势数据暂未积累',
                current: await sentimentManagerHandler({ action: 'fear_greed_index' }).then((res: any) => res.data),
                isSimulated: true,
                dataSource: 'simulated',
                assumptions: [
                    '暂无历史情绪时间序列，返回当前指标作为占位',
                    '趋势判断不代表真实市场情绪演变'
                ]
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
