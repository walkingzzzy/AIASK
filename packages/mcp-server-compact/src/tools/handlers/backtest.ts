import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import { timescaleDB } from '../../storage/timescaledb.js';
import * as BacktestService from '../../services/backtest.js';
import { getDailyBarsByDateRange } from '../../storage/kline-data.js';

export const backtestManagerTool: ToolDefinition = {
    name: 'backtest_manager',
    description: '回测管理（策略回测、参数优化、蒙特卡洛模拟、结果持久化）',
    category: 'backtest',
    inputSchema: managerSchema,
    tags: ['backtest', 'strategy', 'simulation', 'optimization'],
    dataSource: 'simulated'
};

function rebuildTradeProfits(trades: any[]) {
    const assumptions: string[] = [
        '利润按平均成本法从交易序列重算',
        '手续费/滑点按交易记录字段扣减'
    ];
    let hasMissingPosition = false;
    let hasInvalidTrade = false;

    const indexed = trades.map((t, i) => ({ t, i }));
    indexed.sort((a, b) => {
        const ta = Date.parse(a.t.trade_date || a.t.tradeDate || a.t.date || '') || 0;
        const tb = Date.parse(b.t.trade_date || b.t.tradeDate || b.t.date || '') || 0;
        if (ta === tb) return a.i - b.i;
        return ta - tb;
    });

    const positions = new Map<string, { qty: number; avgCost: number }>();
    const mappedTrades = indexed.map(({ t }) => {
        const action = String(t.action || '').toLowerCase() as 'buy' | 'sell';
        const code = String(t.stock_code || t.stockCode || t.code || '');
        const price = Number(t.price || 0);
        const quantity = Number(t.shares ?? t.quantity ?? 0);
        const fee = Number(t.fee || 0);
        const slippage = Number(t.slippage || 0);
        const amount = Number(t.net_value ?? t.amount ?? price * quantity);
        const date = String(t.trade_date || t.tradeDate || t.date || '');

        if (!code || !price || !quantity || (action !== 'buy' && action !== 'sell')) {
            hasInvalidTrade = true;
            return {
                date,
                code,
                action,
                price,
                quantity,
                amount,
            };
        }

        const position = positions.get(code) || { qty: 0, avgCost: 0 };

        if (action === 'buy') {
            const totalCost = position.avgCost * position.qty;
            const tradeCost = price * quantity + fee + slippage;
            const newQty = position.qty + quantity;
            const newAvgCost = newQty > 0 ? (totalCost + tradeCost) / newQty : 0;
            positions.set(code, { qty: newQty, avgCost: newAvgCost });
            return { date, code, action, price, quantity, amount };
        }

        const availableQty = position.qty;
        let costBasis = 0;
        if (availableQty <= 0) {
            hasMissingPosition = true;
            costBasis = price * quantity;
        } else if (quantity > availableQty) {
            hasMissingPosition = true;
            const extraQty = quantity - availableQty;
            costBasis = position.avgCost * availableQty + price * extraQty;
        } else {
            costBasis = position.avgCost * quantity;
        }

        const proceeds = price * quantity - fee - slippage;
        const profit = proceeds - costBasis;
        const profitPercent = costBasis > 0 ? profit / costBasis : undefined;

        const remainingQty = Math.max(availableQty - quantity, 0);
        positions.set(code, { qty: remainingQty, avgCost: remainingQty > 0 ? position.avgCost : 0 });

        return {
            date,
            code,
            action,
            price,
            quantity,
            amount,
            profit,
            profitPercent,
        };
    });

    if (hasMissingPosition) {
        assumptions.push('卖出数量超过持仓时，超出部分按零利润处理');
    }
    if (hasInvalidTrade) {
        assumptions.push('存在无法解析的交易记录，已跳过利润计算');
    }

    return { mappedTrades, assumptions };
}

export const backtestManagerHandler: ToolHandler = async (params: any) => {
    const {
        action, code, codes, startDate, endDate,
        initialCapital = 100000, strategy = 'buy_and_hold',
        shortPeriod, longPeriod, lookback, threshold,
        maxHoldingDays, sellSignal,
        commission = 0.0003, slippage = 0.001, backtestId, limit = 10,
        paramRanges, runs // For advanced features
    } = params;

    // Support stocks param and handle comma-separated string
    let stockCodes: string[] | null = null;
    const rawCodes = codes || params.stocks || (code ? [code] : null);
    if (typeof rawCodes === 'string') {
        stockCodes = rawCodes.split(',').map((s: string) => s.trim());
    } else if (Array.isArray(rawCodes)) {
        stockCodes = rawCodes;
    }

    // Helper: Get Klines
    async function getKlines(targetCode: string) {
        let klines: Array<{ date: string; open: number; high: number; low: number; close: number; volume: number }> = [];
        if (startDate && endDate) {
            klines = await getDailyBarsByDateRange(targetCode, startDate, endDate);
        }
        if (klines.length < 20) {
            const klineRes = await adapterManager.getKline(targetCode, '101', 500); // 增加获取数量以支持更多策略
            if (klineRes.success && klineRes.data && klineRes.data.length >= 20) {
                klines = klineRes.data;
            }
        }
        return klines;
    }

    // ===== 运行回测 =====
    if (action === 'run' || action === 'backtest') {
        if (!stockCodes || stockCodes.length === 0) return { success: false, error: '缺少股票代码' };

        const klines = await getKlines(stockCodes[0]);
        if (klines.length < 20) return { success: false, error: 'K线数据不足' };

        const runParams = {
            initialCapital, commission, slippage,
            shortPeriod, longPeriod, lookback, threshold,
            maxHoldingDays, sellSignal
        };

        const { result, trades, equityCurve } = BacktestService.runBacktest(stockCodes[0], klines, strategy, runParams);

        // Save result
        const resultId = `bt_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
        result.id = resultId; // Inject ID
        result.createdAt = new Date().toISOString();

        await timescaleDB.saveBacktestResult(result);
        const mappedTrades = trades.map((t: any) => ({
            id: `tr_${Math.random().toString(36).substr(2, 9)}`,
            stockCode: t.code,
            action: t.action,
            price: t.price,
            shares: t.quantity,
            grossValue: t.price * t.quantity,
            fee: 0,
            slippage: 0,
            netValue: t.amount,
            cashBalance: 0,
            equity: 0,
            tradeDate: t.date,
            reason: undefined
        }));

        const mappedEquity = equityCurve.map((e: any) => ({
            date: e.date,
            close: e.close,
            cash: e.cash,
            shares: e.shares,
            equity: e.value,
            dailyReturn: null
        }));

        await timescaleDB.saveBacktestTrades(resultId, mappedTrades as any);
        await timescaleDB.saveBacktestEquity(resultId, mappedEquity);

        // 精简返回：只返回前5笔和后5笔交易，权益曲线采样
        const tradeSample = trades.length <= 10
            ? trades
            : [...trades.slice(0, 5), ...trades.slice(-5)];

        const equitySample = equityCurve.length <= 20
            ? equityCurve
            : equityCurve.filter((_, i) => i % Math.ceil(equityCurve.length / 20) === 0);

        return {
            success: true,
            data: {
                backtestId: resultId,
                strategy,
                performance: {
                    totalReturn: (result.totalReturn * 100).toFixed(2) + '%',
                    maxDrawdown: (result.maxDrawdown * 100).toFixed(2) + '%',
                    sharpeRatio: result.sharpeRatio.toFixed(2),
                    winRate: (result.winRate! * 100).toFixed(1) + '%'
                },
                tradesCount: trades.length,
                tradesSample: tradeSample.map((t: any) => ({
                    date: t.date,
                    action: t.action,
                    price: t.price,
                    quantity: t.quantity
                })),
                equitySample: equitySample.map((e: any) => ({
                    date: e.date,
                    value: Math.round(e.value)
                })),
                note: `完整数据已保存，ID: ${resultId}。使用 action=get 查看详情`,
                dataSource: 'simulated',
                assumptions: [
                    '回测基于历史K线回放，不代表真实撮合与流动性约束',
                    '交易成本使用固定费率/滑点参数进行估算'
                ]
            }
        };
    }

    // ===== 参数优化 =====
    if (action === 'optimize_parameters' || action === 'optimize') {
        if (!stockCodes || stockCodes.length === 0) return { success: false, error: '缺少股票代码' };
        if (!paramRanges) return { success: false, error: '缺少 paramRanges 参数' };

        const klines = await getKlines(stockCodes[0]);
        if (klines.length < 20) return { success: false, error: 'K线数据不足' };

        const baseParams = {
            initialCapital, commission, slippage,
            shortPeriod, longPeriod, lookback, threshold
        };

        // 使用并行优化（如果参数组合较多）
        const { bestParams, bestResult, allResults } = await BacktestService.optimizeParametersParallel(
            stockCodes[0], klines, strategy, baseParams, paramRanges
        );

        return {
            success: true,
            data: {
                bestParams,
                bestPerformance: {
                    return: (bestResult.totalReturn * 100).toFixed(2) + '%',
                    drawdown: (bestResult.maxDrawdown * 100).toFixed(2) + '%',
                    sharpe: bestResult.sharpeRatio.toFixed(2)
                },
                allTrials: allResults.length,
                top5: allResults.sort((a: any, b: any) => b.metric - a.metric).slice(0, 5).map((r: any) => ({
                    params: r.params,
                    metric: parseFloat(r.metric.toFixed(4))
                })),
                note: '仅显示前5个最佳结果',
                dataSource: 'simulated',
                assumptions: [
                    '参数优化基于历史样本回测结果',
                    '未进行稳健性或交易成本敏感性校验'
                ]
            }
        };
    }

    // ===== 蒙特卡洛模拟 =====
    if (action === 'monte_carlo_simulation' || action === 'monte_carlo') {
        if (!backtestId) return { success: false, error: '缺少 backtestId' };

        const trades = await timescaleDB.getBacktestTrades(backtestId);
        if (!trades || trades.length === 0) return { success: false, error: '未找到回测交易记录' };

        // Need initial capital from result to do ratio calc correctly, or pass it in
        const result = await timescaleDB.getBacktestResultById(backtestId);
        const capital = result ? result.initialCapital : initialCapital;

        const { mappedTrades, assumptions } = rebuildTradeProfits(trades);
        const simResult = BacktestService.monteCarloSimulation(mappedTrades, capital, runs || 1000);

        return {
            success: true,
            data: {
                ...simResult,
                isSimulated: true,
                dataSource: 'simulated',
                assumptions: [
                    '蒙特卡洛基于历史交易利润的随机重排',
                ].concat(assumptions)
            }
        };
    }

    // ===== 滚动前进分析 =====
    if (action === 'walk_forward_analysis') {
        if (!stockCodes || stockCodes.length === 0) return { success: false, error: '缺少股票代码' };
        if (!paramRanges) return { success: false, error: '缺少 paramRanges 参数' };

        const klines = await getKlines(stockCodes[0]);
        if (klines.length < 100) return { success: false, error: 'K线数据不足以进行滚动分析' };

        const baseParams = {
            initialCapital, commission, slippage,
            shortPeriod, longPeriod, lookback, threshold
        };

        try {
            const { results, overallReturn } = BacktestService.walkForwardAnalysis(
                stockCodes[0], klines, strategy, baseParams, paramRanges,
                params.trainWindow || 200, params.testWindow || 60
            );

            return {
                success: true,
                data: {
                    segments: results.length,
                    overallReturn: (overallReturn * 100).toFixed(2) + '%',
                    details: results.map((r: any) => ({
                        period: r.period,
                        params: r.params,
                        return: (r.return * 100).toFixed(2) + '%'
                    })),
                    isSimulated: true,
                    dataSource: 'simulated',
                    assumptions: [
                        '训练/测试窗口为历史滑动分段，不代表真实实盘执行',
                        '参数选择存在样本期偏差与过拟合风险'
                    ]
                }
            };
        } catch (e) {
            return { success: false, error: String(e) };
        }
    }

    // ===== 回测报告生成 =====
    if (action === 'generate_backtest_report' || action === 'report') {
        if (!backtestId) return { success: false, error: '缺少 backtestId' };

        const result = await timescaleDB.getBacktestResultById(backtestId);
        if (!result) return { success: false, error: '回测结果不存在' };

        const trades = await timescaleDB.getBacktestTrades(backtestId);
        const equity = await timescaleDB.getBacktestEquity(backtestId);

        // 权益曲线采样：最多返回30个点
        const equitySample = equity.length <= 30
            ? equity
            : equity.filter((_, i) => i % Math.ceil(equity.length / 30) === 0);

        const report = {
            title: `Backtest Report: ${result.strategy} on ${result.stocks.join(',')}`,
            metrics: {
                return: (result.totalReturn * 100).toFixed(2) + '%',
                annualized: ((result.annualReturn || 0) * 100).toFixed(2) + '%',
                maxDD: (result.maxDrawdown * 100).toFixed(2) + '%',
                sharpe: result.sharpeRatio.toFixed(2),
                trades: result.tradesCount,
                winRate: ((result.winRate || 0) * 100).toFixed(2) + '%'
            },
            equityChart: equitySample.map((e: any) => ({ d: e.date, v: Math.round(e.equity) })),
            tradeDistribution: {
                wins: Math.round(result.tradesCount * (result.winRate || 0)),
                losses: Math.round(result.tradesCount * (1 - (result.winRate || 0)))
            },
            note: `权益曲线已采样至${equitySample.length}个点`,
            dataSource: 'simulated',
            assumptions: [
                '报告基于历史回测结果汇总',
                '指标未包含实盘交易冲击与资金约束'
            ]
        };

        return { success: true, data: report };
    }

    // ===== 查询历史回测 =====
    if (action === 'list' || action === 'history') {
        const results = await timescaleDB.getBacktestResults(limit, strategy !== 'buy_and_hold' ? strategy : undefined);
        return { success: true, data: { results, total: results.length } };
    }

    // ===== 获取回测详情 =====
    if (action === 'get' || action === 'detail') {
        if (!backtestId) return { success: false, error: '缺少 backtestId' };
        const result = await timescaleDB.getBacktestResultById(backtestId);
        if (!result) return { success: false, error: '回测结果不存在' };
        const trades = await timescaleDB.getBacktestTrades(backtestId);
        const equity = await timescaleDB.getBacktestEquity(backtestId);

        // 限制返回数据量
        const tradesLimit = params.tradesLimit || 20;
        const equityLimit = params.equityLimit || 50;

        const tradesSample = trades.length <= tradesLimit
            ? trades
            : [...trades.slice(0, tradesLimit / 2), ...trades.slice(-tradesLimit / 2)];

        const equitySample = equity.length <= equityLimit
            ? equity
            : equity.filter((_, i) => i % Math.ceil(equity.length / equityLimit) === 0);

        return {
            success: true,
            data: {
                result,
                trades: tradesSample,
                tradesTotal: trades.length,
                equityCurve: equitySample,
                equityTotal: equity.length,
                note: '数据已采样，如需完整数据请使用数据库查询'
            }
        };
    }

    // ===== 列出策略 =====
    if (action === 'list_strategies' || action === 'strategies') {
        // Should ideally scan service capabilities
        return {
            success: true,
            data: {
                strategies: [
                    { name: 'buy_and_hold', description: '买入持有策略', params: [] },
                    { name: 'ma_cross', description: '均线交叉策略', params: ['shortPeriod', 'longPeriod'] },
                    { name: 'momentum', description: '动量策略', params: ['lookback', 'threshold'] },
                    { name: 'rsi', description: 'RSI超买超卖策略', params: [] },
                ]
            }
        };
    }

    return { success: false, error: `未知操作: ${action}。支持的操作: run, optimize, monte_carlo, walk_forward, report, list, get` };
};
