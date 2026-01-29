/**
 * 市场情绪与资金流向工具
 */

import { z } from 'zod';
import { ToolDefinition, ToolHandler, ToolRegistryItem } from '../types/tools.js';
import { adapterManager } from '../adapters/index.js';
import * as SentimentServices from '../services/sentiment.js';

// ========== get_sentiment_analysis ==========

const getSentimentAnalysisSchema = z.object({
    code: z.string().describe('股票代码'),
});

const getSentimentAnalysisTool: ToolDefinition = {
    name: 'analyze_stock_sentiment',
    description: '分析个股的市场情绪（基于量价、趋势等）',
    category: 'market_sentiment',
    inputSchema: getSentimentAnalysisSchema,
    tags: ['sentiment', 'analysis'],
    dataSource: 'calculated',
};

const getSentimentAnalysisHandler: ToolHandler<z.infer<typeof getSentimentAnalysisSchema>> = async (params) => {
    const code = params.code;
    const quoteRes = await adapterManager.getRealtimeQuote(code);

    if (!quoteRes.success || !quoteRes.data) {
        return { success: false, error: `无法获取 ${code} 的实时行情: ${quoteRes.error}` };
    }
    const quote = quoteRes.data;
    // 获取K线数据用于简单的趋势判断
    const klineRes = await adapterManager.getKline(code, '101', 60);
    const klines = klineRes.success && klineRes.data ? klineRes.data : [];

    if (klines.length === 0) {
        return { success: false, error: `无法获取 ${code} 的K线数据` };
    }

    const analysis = SentimentServices.analyzeStockSentiment(quote, klines);

    return {
        success: true,
        data: analysis,
        source: 'calculated',
    };
};

// ========== calculate_fear_greed_index ==========

const calculateFearGreedSchema = z.object({});

const calculateFearGreedTool: ToolDefinition = {
    name: 'calculate_fear_greed_index',
    description: '计算市场恐惧贪婪指数',
    category: 'market_sentiment',
    inputSchema: calculateFearGreedSchema,
    tags: ['sentiment', 'market'],
    dataSource: 'calculated_estimate',
};

const calculateFearGreedHandler: ToolHandler<z.infer<typeof calculateFearGreedSchema>> = async () => {
    const [limitStatsRes, sectorFlowRes, klineRes] = await Promise.all([
        adapterManager.getLimitUpStatistics(),
        adapterManager.getSectorFlow(50),
        adapterManager.getKline('000001', '101', 60),
    ]);

    const limitStats = limitStatsRes.success && limitStatsRes.data
        ? limitStatsRes.data
        : { totalLimitUp: 0, limitDown: 0 };

    const sectors = sectorFlowRes.success && sectorFlowRes.data ? sectorFlowRes.data : [];
    const advances = sectors.length > 0 ? sectors.filter((s: any) => (s.changePercent || 0) > 0).length : 1;
    const declines = sectors.length > 0 ? sectors.filter((s: any) => (s.changePercent || 0) < 0).length : 1;

    const bars = klineRes.success && klineRes.data ? klineRes.data : [];
    const volumes = bars.map((b: any) => b.volume).filter((v: any) => Number.isFinite(v));
    const volumeRatio = volumes.length >= 20
        ? volumes[volumes.length - 1] / (volumes.slice(-20).reduce((a: any, b: any) => a + b, 0) / 20)
        : 1;

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

    const marketData = {
        advances,
        declines,
        newHighs: limitStats.totalLimitUp || 0,
        newLows: limitStats.limitDown || 0,
        volumeRatio: Number.isFinite(volumeRatio) ? volumeRatio : 1,
        volatility: Number.isFinite(volatility) ? volatility : 1,
    };

    const index = SentimentServices.calculateFearGreedIndex(marketData);

    return {
        success: true,
        data: {
            ...index,
            dataSource: 'calculated_estimate',
            assumptions: [
                '使用板块涨跌家数近似市场宽度',
                '成交量比率基于上证指数近60日量能估算'
            ]
        },
        source: 'calculated',
    };
};

// ========== get_fund_flow ==========

const getFundFlowSchema = z.object({
    code: z.string().describe('股票代码'),
});

const getFundFlowTool: ToolDefinition = {
    name: 'get_fund_flow',
    description: '获取个股的资金流向数据',
    category: 'market_sentiment',
    inputSchema: getFundFlowSchema,
    tags: ['fund_flow', 'stock'],
    dataSource: 'real',
};

const getFundFlowHandler: ToolHandler<z.infer<typeof getFundFlowSchema>> = async (params) => {
    const result = await adapterManager.getFundFlow(params.code);
    if (!result.success || !result.data) {
        return {
            success: false,
            error: result.error || `获取 ${params.code} 的资金流向失败`,
        };
    }
    return {
        success: true,
        data: result.data,
        source: 'eastmoney',
    };
};

// ========== 注册导出 ==========

export const marketSentimentTools: ToolRegistryItem[] = [
    { definition: getSentimentAnalysisTool, handler: getSentimentAnalysisHandler },
    { definition: calculateFearGreedTool, handler: calculateFearGreedHandler },
    { definition: getFundFlowTool, handler: getFundFlowHandler },
];
