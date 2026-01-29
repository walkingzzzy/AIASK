/**
 * 市场数据工具
 * 包含实时行情、K线数据、股票搜索等
 */

import { z } from 'zod';
import { ToolDefinition, ToolHandler, ToolRegistryItem } from '../types/tools.js';
import { adapterManager } from '../adapters/index.js';
import { marketAPI } from '../adapters/eastmoney/market-api.js';
import { getStockInfo, searchStocks } from '../storage/stock-info.js';
import { getDailyBars, getDailyBarsByDateRange } from '../storage/kline-data.js';

// ========== get_batch_quotes ==========

const getRealtimeQuotesSchema = z.object({
    codes: z.array(z.string()).describe('股票代码列表，如 ["000001", "600519"]'),
});

const getRealtimeQuotesTool: ToolDefinition = {
    name: 'get_batch_quotes',
    description: '批量获取指定股票的实时行情数据',
    category: 'market_data',
    inputSchema: getRealtimeQuotesSchema,
    tags: ['core', 'market'],
    priority: 10,
    dataSource: 'real',
};

const getRealtimeQuotesHandler: ToolHandler<z.infer<typeof getRealtimeQuotesSchema>> = async (params) => {
    const results = await Promise.all(
        params.codes.map(async code => {
            const res = await adapterManager.getRealtimeQuote(code);
            return res.success ? res.data : null;
        })
    );

    // 过滤掉错误的
    const quotes = results.filter((r: any) => r !== null);

    return {
        success: true,
        data: quotes,
        source: 'multiple_adapters',
    };
};

// ========== get_kline_data ==========

const getKlineDataSchema = z.object({
    code: z.string().describe('股票代码'),
    period: z.enum(['1m', '5m', '15m', '30m', '60m', '101', '102', '103', 'daily', 'weekly', 'monthly']).default('101').describe('K线周期: 101/daily=日线, 102/weekly=周线, 103/monthly=月线, 1m/5m...=分钟线'),
    startDate: z.string().optional().describe('开始日期 (YYYY-MM-DD)'),
    endDate: z.string().optional().describe('结束日期 (YYYY-MM-DD)'),
    limit: z.number().optional().default(30).describe('返回条数限制，默认30，最大200'),
    adjust: z.enum(['qfq', 'hfq', '']).optional().default('qfq').describe('复权方式: qfq-前复权, hfq-后复权, ""-不复权'),
});

const getKlineDataTool: ToolDefinition = {
    name: 'get_kline_data',
    description: '获取股票的历史K线数据',
    category: 'market_data',
    inputSchema: getKlineDataSchema,
    tags: ['core', 'market'],
    priority: 9,
    dataSource: 'real',
};

const getKlineDataHandler: ToolHandler<z.infer<typeof getKlineDataSchema>> = async (params) => {
    // 转换周期格式
    let period = params.period;
    if (period === 'daily') period = '101';
    if (period === 'weekly') period = '102';
    if (period === 'monthly') period = '103';

    // 如果是日线且请求本地数据 (通常用于回测或大范围分析)
    // 这里简单起见，优先使用 Adapter 获取最新数据
    // 如果需要大范围历史数据，后续可以考虑增加 from_storage 选项

    // API限制
    const limit = Math.min(params.limit || 30, 200);
    const adjust = params.adjust === '' ? undefined : (params.adjust as 'qfq' | 'hfq');

    const apiRes = await adapterManager.getKline(params.code, period, limit);
    const data = apiRes.success ? apiRes.data : [];

    return {
        success: true,
        data,
        source: 'adapter_manager',
    };
};

// ========== get_stock_info ==========

const getStockInfoSchema = z.object({
    code: z.string().describe('股票代码'),
});

const getStockInfoTool: ToolDefinition = {
    name: 'get_stock_info',
    description: '获取股票的基本信息（名称、板块、上市日期等）',
    category: 'market_data',
    inputSchema: getStockInfoSchema,
    tags: ['core', 'info'],
    dataSource: 'real',
};

const getStockInfoHandler: ToolHandler<z.infer<typeof getStockInfoSchema>> = async (params) => {
    const info = getStockInfo(params.code);

    if (!info) {
        // 如果本地没有，尝试通过 adapters 获取 quote 来补充基础信息 (Name)
        const quoteRes = await adapterManager.getRealtimeQuote(params.code);
        if (quoteRes.success && quoteRes.data) {
            const quote = quoteRes.data;
            return {
                success: true,
                data: {
                    code: params.code,
                    name: quote.name,
                    market: params.code.startsWith('6') ? 'SH' : 'SZ', // 简单推断
                },
                source: 'realtime_quote_fallback',
            };
        }

        return {
            success: false,
            error: `未找到股票 ${params.code} 的信息`,
        };
    }

    return {
        success: true,
        data: info,
        source: 'database',
    };
};

// ========== search_stocks ==========

const searchStocksSchema = z.object({
    keyword: z.string().describe('搜索关键词（股票代码或名称）'),
    limit: z.number().optional().default(10).describe('返回结果数量限制'),
});

const searchStocksTool: ToolDefinition = {
    name: 'search_stocks',
    description: '搜索股票代码或名称',
    category: 'market_data',
    inputSchema: searchStocksSchema,
    tags: ['core', 'search'],
    dataSource: 'real',
};

const searchStocksHandler: ToolHandler<z.infer<typeof searchStocksSchema>> = async (params) => {
    const results = searchStocks(params.keyword, params.limit);

    return {
        success: true,
        data: results,
        source: 'database',
    };
};

// ========== get_market_blocks ==========

const getMarketBlocksSchema = z.object({
    type: z.enum(['industry', 'concept', 'region']).default('industry').describe('板块类型：industry(行业), concept(概念), region(地域)'),
});

const getMarketBlocksTool: ToolDefinition = {
    name: 'get_market_blocks',
    description: '获取市场板块列表（行业、概念、地域）',
    category: 'market_data',
    inputSchema: getMarketBlocksSchema,
    tags: ['market', 'blocks'],
    dataSource: 'real',
};

const getMarketBlocksHandler: ToolHandler<z.infer<typeof getMarketBlocksSchema>> = async (params) => {
    try {
        const blocks = await marketAPI.getMarketBlocks(params.type);
        return {
            success: true,
            data: {
                type: params.type,
                blocks,
                total: blocks.length,
            },
            source: 'eastmoney',
        };
    } catch (e) {
        return {
            success: false,
            error: `获取${params.type}板块失败: ${String(e)}`,
        };
    }
};

// ========== get_realtime_quote (单股版本) ==========

const getRealtimeQuoteSchema = z.object({
    stock_code: z.string().describe('股票代码，如 000001'),
});

const getRealtimeQuoteTool: ToolDefinition = {
    name: 'get_realtime_quote',
    description: '获取单只股票的实时行情数据（简化版）',
    category: 'market_data',
    inputSchema: getRealtimeQuoteSchema,
    tags: ['core', 'market'],
    priority: 10,
    dataSource: 'real',
};

const getRealtimeQuoteHandler: ToolHandler<z.infer<typeof getRealtimeQuoteSchema>> = async (params) => {
    const res = await adapterManager.getRealtimeQuote(params.stock_code);
    return {
        success: res.success,
        data: res.data,
        error: res.error,
        source: res.source,
    };
};

// ========== run_simple_backtest ==========

const runSimpleBacktestSchema = z.object({
    stock_codes: z.array(z.string()).describe('回测股票列表'),
    strategy: z.enum(['buy_and_hold', 'ma_cross', 'momentum']).default('buy_and_hold').describe('策略类型'),
    start_date: z.string().describe('开始日期 (YYYY-MM-DD)'),
    end_date: z.string().describe('结束日期 (YYYY-MM-DD)'),
    initial_capital: z.number().optional().default(100000).describe('初始资金（默认10万）'),
});

const runSimpleBacktestTool: ToolDefinition = {
    name: 'run_simple_backtest',
    description: '运行简单回测（买入持有、均线交叉、动量策略）',
    category: 'backtest',
    inputSchema: runSimpleBacktestSchema,
    tags: ['backtest', 'quant'],
    dataSource: 'calculated',
};

const runSimpleBacktestHandler: ToolHandler<z.infer<typeof runSimpleBacktestSchema>> = async (params) => {
    const results: any[] = [];
    const codelist = params.stock_codes;

    // 默认回测最近 1 年 (大约 250 交易日)
    // 如果指定日期，需计算 limit，这里简化为获取足够长的 K 线并在内存过滤
    // 为简单起见，我们请求最近 300 天数据
    const limit = 300;

    for (const code of codelist) {
        const klineRes = await adapterManager.getKline(code, '101', limit);
        if (!klineRes.success || !klineRes.data || klineRes.data.length === 0) {
            results.push({ code, error: '无法获取K线数据' });
            continue;
        }

        let bars = klineRes.data;
        // 简单的日期过滤
        if (params.start_date || params.end_date) {
            bars = bars.filter((b: any) => {
                const date = b.date;
                const afterStart = !params.start_date || date >= params.start_date;
                const beforeEnd = !params.end_date || date <= params.end_date;
                return afterStart && beforeEnd;
            });
        }

        if (bars.length < 2) {
            results.push({ code, error: 'K线数据不足，无法回测' });
            continue;
        }

        const initialCapital = params.initial_capital;
        let finalCapital = initialCapital;
        let quantity = 0;
        const trades: any[] = [];

        if (params.strategy === 'buy_and_hold') {
            // 买入持有: 第一天开盘买入，最后一天收盘卖出
            const first = bars[0];
            const last = bars[bars.length - 1];

            // 全仓买入 (不考虑佣金)
            quantity = Math.floor(initialCapital / first.open);
            const cost = quantity * first.open;
            const remainingCash = initialCapital - cost;

            trades.push({ date: first.date, type: 'buy', price: first.open, quantity });

            // 最后一天市值
            finalCapital = remainingCash + quantity * last.close;
        } else if (params.strategy === 'ma_cross') {
            // 简单均线策略: MA5 > MA20 买入, MA5 < MA20 卖出
            // 需先计算均线
            const closes = bars.map((b: any) => b.close);

            // 简单 MA 计算函数
            const calcMA = (n: number) => {
                const maList = [];
                for (let i = 0; i < closes.length; i++) {
                    if (i < n - 1) {
                        maList.push(NaN); // 数据不足
                        continue;
                    }
                    const sum = closes.slice(i - n + 1, i + 1).reduce((a: any, b: any) => a + b, 0);
                    maList.push(sum / n);
                }
                return maList;
            };

            const ma5 = calcMA(5);
            const ma20 = calcMA(20);

            let cash = initialCapital;

            for (let i = 20; i < bars.length; i++) {
                const prevMA5 = ma5[i - 1];
                const prevMA20 = ma20[i - 1];
                const currMA5 = ma5[i];
                const currMA20 = ma20[i];

                if (isNaN(prevMA5) || isNaN(prevMA20)) continue;

                // 金叉买入
                if (prevMA5 <= prevMA20 && currMA5 > currMA20 && quantity === 0) {
                    quantity = Math.floor(cash / bars[i].close);
                    if (quantity > 0) {
                        cash -= quantity * bars[i].close;
                        trades.push({ date: bars[i].date, type: 'buy', price: bars[i].close, quantity });
                    }
                }
                // 死叉卖出
                else if (prevMA5 >= prevMA20 && currMA5 < currMA20 && quantity > 0) {
                    cash += quantity * bars[i].close;
                    trades.push({ date: bars[i].date, type: 'sell', price: bars[i].close, quantity });
                    quantity = 0;
                }
            }
            finalCapital = cash + (quantity > 0 ? quantity * bars[bars.length - 1].close : 0);
        } else {
            // 其他策略暂未实现，回退到 Buy & Hold
            results.push({ code, error: `策略 ${params.strategy} 暂未实现，仅支持 buy_and_hold, ma_cross` });
            continue;
        }

        const returnRate = ((finalCapital - initialCapital) / initialCapital * 100).toFixed(2) + '%';
        results.push({
            code,
            initialCapital,
            finalCapital: Number(finalCapital.toFixed(2)),
            returnRate,
            tradesCount: trades.length,
            firstTrade: trades[0],
            lastTrade: trades[trades.length - 1]
        });
    }

    return {
        success: true,
        data: {
            strategy: params.strategy,
            period: `${params.start_date || 'auto'} ~ ${params.end_date || 'auto'}`,
            results
        },
        source: 'local_backtest',
    };
};

// ========== 注册导出 ==========

export const marketDataTools: ToolRegistryItem[] = [
    { definition: getRealtimeQuotesTool, handler: getRealtimeQuotesHandler },
    { definition: getRealtimeQuoteTool, handler: getRealtimeQuoteHandler },
    { definition: getKlineDataTool, handler: getKlineDataHandler },
    { definition: getStockInfoTool, handler: getStockInfoHandler },
    { definition: searchStocksTool, handler: searchStocksHandler },
    { definition: getMarketBlocksTool, handler: getMarketBlocksHandler },
    { definition: runSimpleBacktestTool, handler: runSimpleBacktestHandler },
];
