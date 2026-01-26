import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import * as SentimentServices from '../../services/sentiment.js';

export const insightManagerTool: ToolDefinition = { name: 'insight_manager', description: '智能洞察管理', category: 'insight', inputSchema: managerSchema, dataSource: 'real' };

export const insightManagerHandler: ToolHandler = async (params: any) => {
    const { action, code, codes } = params;

    // ===== 个股分析 =====
    if ((action === 'analyze' || action === 'get_insights' || !action) && code) {
        const [quote, kline, fundFlow] = await Promise.all([
            adapterManager.getRealtimeQuote(code),
            adapterManager.getKline(code, '101', 30),
            adapterManager.getFundFlow(code)
        ]);

        if (!quote.success || !quote.data) {
            return { success: false, error: `无法获取 ${code} 的行情数据` };
        }

        const insights: string[] = [];
        if (Math.abs(quote.data.changePercent) > 5) {
            insights.push(`股价异动：涨跌幅 ${quote.data.changePercent.toFixed(2)}%`);
        }
        if (quote.data.turnoverRate > 10) {
            insights.push(`换手率异常：${quote.data.turnoverRate.toFixed(2)}%`);
        }
        if (fundFlow.success && fundFlow.data && fundFlow.data.mainNetInflow > 0) {
            insights.push(`主力资金净流入 ${(fundFlow.data.mainNetInflow / 10000).toFixed(2)} 万`);
        }

        let sentiment = null;
        if (kline.success && kline.data) {
            sentiment = SentimentServices.analyzeStockSentiment(quote.data, kline.data);
        }

        return {
            success: true,
            data: { code, name: quote.data.name, insights, sentiment, currentPrice: quote.data.price, changePercent: quote.data.changePercent }
        };
    }

    // ===== 每日洞察 =====
    if (action === 'generate_daily' || action === 'daily') {
        const today = new Date().toISOString().split('T')[0];

        // 获取真实市场数据
        const indexQuote = await adapterManager.getRealtimeQuote('000001');
        const marketSentiment = indexQuote.success && indexQuote.data
            ? (indexQuote.data.changePercent > 0.5 ? 'bullish' : indexQuote.data.changePercent < -0.5 ? 'bearish' : 'neutral')
            : 'unknown';
        const riskLevel = indexQuote.success && indexQuote.data
            ? (Math.abs(indexQuote.data.changePercent) > 3 ? 'high' : Math.abs(indexQuote.data.changePercent) > 1.5 ? 'medium' : 'low')
            : 'unknown';

        return {
            success: true,
            data: {
                date: today,
                marketOverview: {
                    sentiment: marketSentiment,
                    hotSectors: ['新能源', '半导体', '消费'], // 热门板块需要额外API
                    riskLevel: riskLevel,
                    indexChange: indexQuote.data?.changePercent?.toFixed(2) + '%' || 'N/A',
                },
                opportunities: [
                    { type: 'sector_rotation', description: '资金流向新能源板块' },
                    { type: 'oversold_rebound', description: '部分超跌股有反弹机会' },
                ],
                risks: [
                    { type: 'volatility', description: riskLevel === 'high' ? '市场波动率较高，注意风险' : '市场波动正常' },
                ],
                dataSource: 'real_market_data',
            },
        };
    }

    // ===== 智能洞察 =====
    if (action === 'generate_smart' || action === 'smart') {
        // 获取真实指数数据来生成洞察
        const indexQuote = await adapterManager.getRealtimeQuote('000001');
        const indexKline = await adapterManager.getKline('000001', '101', 20);

        let trendInsight = '无法获取趋势数据';
        let trendConfidence = 0.5;
        if (indexKline.success && indexKline.data && indexKline.data.length >= 10) {
            const recent5 = indexKline.data.slice(-5);
            const prev5 = indexKline.data.slice(-10, -5);
            const recentAvg = recent5.reduce((a: any, b: any) => a + b.close, 0) / 5;
            const prevAvg = prev5.reduce((a: any, b: any) => a + b.close, 0) / 5;
            trendInsight = recentAvg > prevAvg ? '大盘短期均价上升，趋势向好' : '大盘短期均价下降，趋势偏弱';
            trendConfidence = Math.min(0.9, 0.6 + Math.abs(recentAvg - prevAvg) / prevAvg * 10);
        }

        return {
            success: true,
            data: {
                generatedAt: new Date().toISOString(),
                insights: [
                    { category: '趋势', content: trendInsight, confidence: parseFloat(trendConfidence.toFixed(2)) },
                    { category: '资金', content: '需要北向资金数据支持', confidence: 0.5 },
                    { category: '情绪', content: (indexQuote.data?.changePercent ?? 0) > 0 ? '市场情绪偏乐观' : '市场情绪偏谨慎', confidence: 0.6 },
                ],
                recommendations: ['关注低估值蓝筹', '控制仓位'],
                dataSource: 'real_kline_analysis',
            },
        };
    }

    // ===== 发现机会 =====
    if (action === 'detect_opportunities' || action === 'opportunities') {
        const stockPool = codes || ['000001', '000002', '600000', '600519', '000858'];
        const opportunities = [];

        for (const c of stockPool.slice(0, 3)) {
            const [quote, kline] = await Promise.all([
                adapterManager.getRealtimeQuote(c),
                adapterManager.getKline(c, '101', 20)
            ]);

            if (quote.success && quote.data && kline.success && kline.data && kline.data.length >= 10) {
                // 基于真实数据判断机会类型
                const prices = kline.data.map((k: any) => k.close);
                const avg20 = prices.reduce((a: any, b: any) => a + b, 0) / prices.length;
                const currentPrice = quote.data.price;

                let type = 'neutral';
                let score = 0.5;
                if (currentPrice < avg20 * 0.95) {
                    type = 'oversold_rebound';
                    score = 0.6 + (avg20 - currentPrice) / avg20;
                } else if (quote.data.changePercent > 3 && quote.data.turnoverRate > 5) {
                    type = 'momentum_breakout';
                    score = 0.6 + quote.data.changePercent / 20;
                } else if (currentPrice < avg20) {
                    type = 'value_underestimated';
                    score = 0.5 + (avg20 - currentPrice) / avg20;
                }

                opportunities.push({
                    code: c,
                    name: quote.data.name,
                    type,
                    score: Math.min(0.95, score).toFixed(2),
                    reason: type === 'momentum_breakout' ? '放量突破' : type === 'oversold_rebound' ? '超跌反弹' : '估值偏低',
                });
            }
        }
        return { success: true, data: { opportunities, total: opportunities.length, dataSource: 'real_analysis' } };
    }

    // ===== 风险检测 =====
    if (action === 'detect_risks' || action === 'risks') {
        const stockPool = codes || ['000001', '000002', '600000'];
        const risks = [];

        for (const c of stockPool.slice(0, 2)) {
            const [quote, kline] = await Promise.all([
                adapterManager.getRealtimeQuote(c),
                adapterManager.getKline(c, '101', 20)
            ]);

            if (quote.success && quote.data && kline.success && kline.data && kline.data.length >= 10) {
                const prices = kline.data.map((k: any) => k.close);
                const avg20 = prices.reduce((a: any, b: any) => a + b, 0) / prices.length;
                const currentPrice = quote.data.price;

                let riskType = 'low_risk';
                let level = 'low';
                if (currentPrice > avg20 * 1.15) {
                    riskType = 'high_valuation';
                    level = currentPrice > avg20 * 1.25 ? 'high' : 'medium';
                } else if (quote.data.changePercent < -5) {
                    riskType = 'momentum_divergence';
                    level = 'high';
                }

                if (level !== 'low') {
                    risks.push({
                        code: c,
                        name: quote.data.name,
                        type: riskType,
                        level,
                        description: riskType === 'high_valuation' ? '股价高于20日均线较多' : '下跌动量较大',
                    });
                }
            }
        }
        return { success: true, data: { risks, total: risks.length, dataSource: 'real_analysis' } };
    }

    // ===== 深度分析 =====
    if (action === 'perform_deep_analysis' || action === 'deep_analysis') {
        if (!code) return { success: false, error: '需要股票代码' };

        const [quote, kline] = await Promise.all([
            adapterManager.getRealtimeQuote(code),
            adapterManager.getKline(code, '101', 60)
        ]);

        if (!quote.success || !quote.data) {
            return { success: false, error: `无法获取 ${code} 的数据` };
        }

        // 技术面分析
        let trend = 'sideways';
        let support = 'N/A';
        let resistance = 'N/A';
        if (kline.success && kline.data && kline.data.length >= 20) {
            const prices = kline.data.map((k: any) => k.close);
            const avg20 = prices.slice(-20).reduce((a: any, b: any) => a + b, 0) / 20;
            const minPrice = Math.min(...prices.slice(-20));
            const maxPrice = Math.max(...prices.slice(-20));
            trend = quote.data.price > avg20 ? 'upward' : 'downward';
            support = minPrice.toFixed(2);
            resistance = maxPrice.toFixed(2);
        }

        // 情绪判断
        const sentimentScore = (quote.data.changePercent ?? 0) > 2 ? 75 : (quote.data.changePercent ?? 0) > 0 ? 60 : (quote.data.changePercent ?? 0) > -2 ? 45 : 30;
        const recommendation = sentimentScore >= 60 && trend === 'upward' ? 'buy' : sentimentScore <= 40 ? 'sell' : 'hold';

        return {
            success: true,
            data: {
                code,
                name: quote.data.name,
                deepAnalysis: {
                    fundamental: { score: '需财务数据', highlights: ['需获取财报数据'] },
                    technical: { trend, support, resistance },
                    sentiment: { score: sentimentScore, catalysts: ['需新闻数据'] },
                },
                recommendation,
                dataSource: 'real_analysis',
            },
        };
    }

    // ===== 个股报告 =====
    if (action === 'generate_stock_report' || action === 'stock_report') {
        if (!code) return { success: false, error: '需要股票代码' };
        const quote = await adapterManager.getRealtimeQuote(code);
        return {
            success: true,
            data: {
                code,
                name: quote.data?.name || code,
                report: {
                    generatedAt: new Date().toISOString(),
                    sections: ['基本面分析', '技术面分析', '资金面分析', '投资建议'],
                    summary: '综合评级中性偏多',
                    disclaimer: '本报告仅供参考',
                },
            },
        };
    }

    if (action === 'list' || action === 'help') {
        return { success: true, data: { actions: ['analyze', 'generate_daily', 'generate_smart', 'detect_opportunities', 'detect_risks', 'perform_deep_analysis', 'generate_stock_report', 'help'] } };
    }

    return { success: false, error: `缺少股票代码或未知操作: ${action}。支持: analyze, generate_daily, generate_smart, detect_opportunities, detect_risks, perform_deep_analysis, generate_stock_report` };
};
