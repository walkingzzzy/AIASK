import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import * as TechnicalServices from '../../services/technical-analysis.js';
import * as SentimentServices from '../../services/sentiment.js';

export const comprehensiveManagerTool: ToolDefinition = { name: 'comprehensive_manager', description: '综合分析管理', category: 'comprehensive', inputSchema: managerSchema, dataSource: 'real' };

export const comprehensiveManagerHandler: ToolHandler = async (params: any) => {
    const { action, code } = params;

    if ((action === 'analyze' || action === 'full_analysis' || action === 'stock_report' || action === 'market_report' || !action) && code) {
        // 聚合多个服务结果
        const [quote, kline, fundFlow, financials] = await Promise.all([
            adapterManager.getRealtimeQuote(code),
            adapterManager.getKline(code, '101', 60),
            adapterManager.getFundFlow(code),
            adapterManager.getFinancials(code)
        ]);

        if (!quote.success || !quote.data) {
            return { success: false, error: `无法获取 ${code} 的行情数据` };
        }

        const result: any = {
            code,
            name: quote.data.name,
            quote: {
                price: quote.data.price,
                changePercent: quote.data.changePercent,
                volume: quote.data.volume,
                amount: quote.data.amount,
                marketCap: quote.data.marketCap,
            }
        };

        // 技术分析
        if (kline.success && kline.data && kline.data.length > 20) {
            const closes = kline.data.map((k: any) => k.close);
            const ma20 = TechnicalServices.calculateSMA(closes, 20);
            const macd = TechnicalServices.calculateMACD(closes);
            const rsi = TechnicalServices.calculateRSI(closes, 14);
            result.technical = {
                ma20: ma20[ma20.length - 1],
                macd: { macd: macd.macd[macd.macd.length - 1], signal: macd.signal[macd.signal.length - 1] },
                rsi: rsi[rsi.length - 1],
                trend: closes[closes.length - 1] > ma20[ma20.length - 1] ? '上涨趋势' : '下跌趋势'
            };
        }

        // 资金流向
        if (fundFlow.success && fundFlow.data) {
            result.fundFlow = fundFlow.data;
        }

        // 基本面
        if (financials.success && financials.data) {
            result.fundamentals = {
                roe: financials.data.roe,
                roa: financials.data.roa,
                eps: financials.data.eps,
                netProfit: financials.data.netProfit,
                revenue: financials.data.revenue,
                netProfitMargin: financials.data.netProfitMargin,
                grossProfitMargin: financials.data.grossProfitMargin,
            };
        }

        // 情绪分析
        if (quote.data && kline.success && kline.data) {
            const sentiment = SentimentServices.analyzeStockSentiment(quote.data, kline.data);
            result.sentiment = sentiment;
        }

        return { success: true, data: result };
    }

    // Market-wide report (no code required)
    if (action === 'market_report') {
        return {
            success: true,
            data: {
                type: 'market_report',
                description: '市场综合报告',
                sections: {
                    indices: '使用 get_realtime_quote 查询 sh000001(上证) / sz399001(深证) 等指数',
                    sectors: '使用 sector_manager.flow 查看板块资金流向',
                    northFund: '使用 trading_data_manager.north_fund 查看北向资金',
                    limitUp: '使用 limit_up_manager.pool 查看涨停股池'
                },
                tip: '如需个股综合分析，请指定 code 参数'
            }
        };
    }

    if (action === 'list' || action === 'help') {
        return { success: true, data: { actions: ['analyze', 'stock_report', 'market_report', 'help'] } };
    }

    return { success: false, error: '缺少股票代码或未知操作。支持: analyze, stock_report, market_report, help' };
};
