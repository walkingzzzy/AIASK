/**
 * 回测服务
 * 提供策略回测、参数优化、蒙特卡洛模拟等功能
 */

import { BacktestResult, BacktestTrade, KlineData } from '../types/stock.js';
import * as TechnicalServices from './technical-analysis.js';

export interface BacktestParams {
    initialCapital: number;
    commission: number;
    slippage: number;
    shortPeriod?: number;
    longPeriod?: number;
    lookback?: number;
    threshold?: number;
}

export interface SimulationResult {
    runs: number;
    bestCase: number;
    worstCase: number;
    average: number;
    median: number;
    confidence95: number;
    drawdowns: number[];
}

/**
 * 运行回测
 */
export function runBacktest(
    code: string,
    klines: KlineData[],
    strategy: string,
    params: BacktestParams
): { result: BacktestResult; trades: BacktestTrade[]; equityCurve: Array<{ date: string; value: number; cash: number; shares: number; close: number }> } {
    const { initialCapital, commission, slippage } = params;
    const closes = klines.map((k: any) => k.close);
    const signals: Array<{ date: string; signal: 'buy' | 'sell' | 'hold'; price: number }> = [];

    // 1. 生成信号
    if (strategy === 'buy_and_hold') {
        if (klines.length > 0) {
            signals.push({ date: klines[0].date, signal: 'buy', price: klines[0].close });
        }
    } else if (strategy === 'ma_cross') {
        const shortPeriod = params.shortPeriod || 5;
        const longPeriod = params.longPeriod || 20;
        const maShort = TechnicalServices.calculateSMA(closes, shortPeriod);
        const maLong = TechnicalServices.calculateSMA(closes, longPeriod);
        const offset = longPeriod - 1;
        let position = false;

        for (let i = 1; i < maShort.length && i < maLong.length; i++) {
            const prevShort = maShort[i - 1];
            const prevLong = maLong[i - 1];
            const currShort = maShort[i];
            const currLong = maLong[i];
            const kIdx = i + offset;

            if (kIdx >= klines.length) break;

            if (!position && prevShort <= prevLong && currShort > currLong) {
                signals.push({ date: klines[kIdx].date, signal: 'buy', price: klines[kIdx].close });
                position = true;
            } else if (position && prevShort >= prevLong && currShort < currLong) {
                signals.push({ date: klines[kIdx].date, signal: 'sell', price: klines[kIdx].close });
                position = false;
            }
        }
    } else if (strategy === 'momentum') {
        const lookback = params.lookback || 20;
        const threshold = params.threshold || 0.02;
        let position = false;

        for (let i = lookback; i < klines.length; i++) {
            const pastPrice = klines[i - lookback].close;
            const currPrice = klines[i].close;
            const momentum = (currPrice - pastPrice) / pastPrice;

            if (!position && momentum > threshold) {
                signals.push({ date: klines[i].date, signal: 'buy', price: currPrice });
                position = true;
            } else if (position && momentum < -threshold) {
                signals.push({ date: klines[i].date, signal: 'sell', price: currPrice });
                position = false;
            }
        }
    } else if (strategy === 'rsi') {
        const rsi = TechnicalServices.calculateRSI(closes, 14);
        let position = false;
        const offset = 14;

        for (let i = 1; i < rsi.length; i++) {
            const kIdx = i + offset;
            if (kIdx >= klines.length) break;

            if (!position && rsi[i] < 30) {
                signals.push({ date: klines[kIdx].date, signal: 'buy', price: klines[kIdx].close });
                position = true;
            } else if (position && rsi[i] > 70) {
                signals.push({ date: klines[kIdx].date, signal: 'sell', price: klines[kIdx].close });
                position = false;
            }
        }
    }

    // 2. 执行交易
    let cash = initialCapital;
    let shares = 0;
    const trades: BacktestTrade[] = [];
    const equityCurve: Array<{ date: string; value: number; cash: number; shares: number; close: number }> = [];

    // 按天遍历，处理当日信号并记录权益
    for (let i = 0; i < klines.length; i++) {
        const k = klines[i];
        const signal = signals.find(s => s.date === k.date);

        if (signal) {
            if (signal.signal === 'buy' && cash > 0) {
                const buyPrice = signal.price * (1 + slippage);
                const maxShares = Math.floor(cash / (buyPrice * (1 + commission)));
                if (maxShares > 0) {
                    const cost = maxShares * buyPrice * (1 + commission);
                    shares += maxShares;
                    cash -= cost;
                    trades.push({
                        date: k.date,
                        code,
                        action: 'buy',
                        price: buyPrice,
                        quantity: maxShares,
                        amount: cost
                    });
                }
            } else if (signal.signal === 'sell' && shares > 0) {
                const sellPrice = signal.price * (1 - slippage);
                const revenue = shares * sellPrice * (1 - commission);

                // 计算本次交易盈亏 (简化：假设全部卖出对应最近的买入)
                // 实际应根据 FIFO 或加权平均计算，这里简化处理
                const lastBuy = trades.filter((t: any) => t.action === 'buy').pop();
                const buyPrice = lastBuy ? lastBuy.price : sellPrice;
                const profit = revenue - (shares * buyPrice * (1 + commission));

                trades.push({
                    date: k.date,
                    code,
                    action: 'sell',
                    price: sellPrice,
                    quantity: shares,
                    amount: revenue,
                    profit,
                    profitPercent: profit / (shares * buyPrice * (1 + commission))
                });

                cash += revenue;
                shares = 0;
            }
        }

        const equity = cash + shares * k.close;
        equityCurve.push({
            date: k.date,
            value: equity,
            cash,
            shares,
            close: k.close
        });
    }

    // 3. 计算指标
    const finalCapital = equityCurve[equityCurve.length - 1]?.value || initialCapital;
    const totalReturn = (finalCapital - initialCapital) / initialCapital;

    // 计算最大回撤
    let maxDrawdown = 0;
    let peak = -Infinity;
    for (const p of equityCurve) {
        if (p.value > peak) peak = p.value;
        const dd = (peak - p.value) / peak;
        if (dd > maxDrawdown) maxDrawdown = dd;
    }

    // 计算夏普比率
    const returns = [];
    for (let i = 1; i < equityCurve.length; i++) {
        returns.push((equityCurve[i].value - equityCurve[i - 1].value) / equityCurve[i - 1].value);
    }
    const avgReturn = returns.reduce((a: any, b: any) => a + b, 0) / (returns.length || 1);
    const stdDev = Math.sqrt(returns.reduce((a: any, b: any) => a + Math.pow(b - avgReturn, 2), 0) / (returns.length || 1));
    const sharpeRatio = stdDev > 0 ? (avgReturn * 252 - 0.03) / (stdDev * Math.sqrt(252)) : 0;

    // 统计胜率
    const sellTrades = trades.filter((t: any) => t.action === 'sell');
    const winningTrades = sellTrades.filter((t: any) => (t.profit || 0) > 0);
    const winRate = sellTrades.length > 0 ? winningTrades.length / sellTrades.length : 0;

    const grossProfit = winningTrades.reduce((sum, t) => sum + (t.profit || 0), 0);
    const grossLoss = sellTrades.filter((t: any) => (t.profit || 0) <= 0).reduce((sum, t) => sum + Math.abs(t.profit || 0), 0);
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : (grossProfit > 0 ? 999 : 0);

    const result: BacktestResult = {
        id: '', // 由调用方生成
        strategy,
        params: params as any,
        stocks: [code],
        startDate: klines[0]?.date || '',
        endDate: klines[klines.length - 1]?.date || '',
        initialCapital,
        finalCapital,
        totalReturn,
        maxDrawdown,
        sharpeRatio,
        tradesCount: trades.length,
        winRate,
        profitFactor
    };

    return { result, trades, equityCurve };
}

/**
 * 参数优化
 * Grid Search（单线程版本，保留用于小规模优化）
 */
export function optimizeParameters(
    code: string,
    klines: KlineData[],
    strategy: string,
    baseParams: BacktestParams,
    paramRanges: Record<string, number[]> // key: paramName, value: [start, end, step]
): { bestParams: BacktestParams; bestResult: BacktestResult; allResults: Array<{ params: any; metric: number }> } {
    const keys = Object.keys(paramRanges);
    if (keys.length === 0) {
        const { result } = runBacktest(code, klines, strategy, baseParams);
        return { bestParams: baseParams, bestResult: result, allResults: [] };
    }

    // 生成参数组合
    const combinations: any[] = [];

    function generateCombinations(index: number, currentParams: any) {
        if (index === keys.length) {
            combinations.push({ ...baseParams, ...currentParams });
            return;
        }

        const key = keys[index];
        const [start, end, step] = paramRanges[key];
        for (let val = start; val <= end; val += step) {
            generateCombinations(index + 1, { ...currentParams, [key]: Number(val.toFixed(4)) });
        }
    }

    generateCombinations(0, {});

    // 运行回测
    let bestMetric = -Infinity;
    let bestResult: BacktestResult | null = null;
    let bestParams: BacktestParams = baseParams;
    const allResults: Array<{ params: any; metric: number }> = [];

    for (const params of combinations) {
        const { result } = runBacktest(code, klines, strategy, params);
        // 优化目标：夏普比率 * (1 - 最大回撤) -> 兼顾收益与风险
        // 或者简单使用 totalReturn
        const metric = result.sharpeRatio * (1 - result.maxDrawdown); // 简单的综合评分

        allResults.push({ params, metric });

        if (metric > bestMetric) {
            bestMetric = metric;
            bestResult = result;
            bestParams = params;
        }
    }

    if (!bestResult) {
        // Fallback
        const { result } = runBacktest(code, klines, strategy, baseParams);
        bestResult = result;
    }

    return { bestParams, bestResult, allResults };
}

/**
 * 参数优化（并行版本）
 * 使用 Worker Threads 进行多核并行计算
 */
export async function optimizeParametersParallel(
    code: string,
    klines: KlineData[],
    strategy: string,
    baseParams: BacktestParams,
    paramRanges: Record<string, number[]>
): Promise<{ bestParams: BacktestParams; bestResult: BacktestResult; allResults: Array<{ params: any; metric: number }> }> {
    const keys = Object.keys(paramRanges);
    if (keys.length === 0) {
        const { result } = runBacktest(code, klines, strategy, baseParams);
        return { bestParams: baseParams, bestResult: result, allResults: [] };
    }

    // 动态导入 Worker 相关模块
    const { Worker } = await import('worker_threads');
    const os = await import('os');
    const path = await import('path');
    const { fileURLToPath } = await import('url');

    // 生成参数组合
    const combinations: BacktestParams[] = [];

    function generateCombinations(index: number, currentParams: any) {
        if (index === keys.length) {
            combinations.push({ ...baseParams, ...currentParams });
            return;
        }

        const key = keys[index];
        const [start, end, step] = paramRanges[key];
        for (let val = start; val <= end; val += step) {
            generateCombinations(index + 1, { ...currentParams, [key]: Number(val.toFixed(4)) });
        }
    }

    generateCombinations(0, {});

    // 如果组合数量较少，使用单线程
    if (combinations.length < 10) {
        return optimizeParameters(code, klines, strategy, baseParams, paramRanges);
    }

    // 获取 CPU 核心数
    const cpuCount = os.cpus().length;
    const workerCount = Math.min(cpuCount, Math.ceil(combinations.length / 5)); // 每个 Worker 至少处理 5 个组合
    const chunkSize = Math.ceil(combinations.length / workerCount);

    // 获取 Worker 文件路径
    const __filename = fileURLToPath(import.meta.url);
    const __dirname = path.dirname(__filename);
    const workerPath = path.join(__dirname, 'backtest-worker.js');

    // 创建 Workers
    const workers: Array<Promise<any>> = [];

    for (let i = 0; i < workerCount; i++) {
        const start = i * chunkSize;
        const end = Math.min(start + chunkSize, combinations.length);
        const chunk = combinations.slice(start, end);

        if (chunk.length === 0) continue;

        const workerPromise = new Promise((resolve, reject) => {
            const worker = new Worker(workerPath, {
                workerData: {
                    code,
                    klines,
                    strategy,
                    paramCombinations: chunk,
                },
            });

            worker.on('message', (message) => {
                if (message.success) {
                    resolve(message.data);
                } else {
                    reject(new Error(message.error));
                }
                worker.terminate();
            });

            worker.on('error', reject);
            worker.on('exit', (exitCode) => {
                if (exitCode !== 0) {
                    reject(new Error(`Worker stopped with exit code ${exitCode}`));
                }
            });
        });

        workers.push(workerPromise);
    }

    // 等待所有 Workers 完成
    const workerResults = await Promise.all(workers);

    // 合并结果
    let bestMetric = -Infinity;
    let bestParams: BacktestParams = baseParams;
    const allResults: Array<{ params: any; metric: number }> = [];

    for (const workerResult of workerResults) {
        allResults.push(...workerResult.results);
        if (workerResult.bestMetric > bestMetric) {
            bestMetric = workerResult.bestMetric;
            bestParams = workerResult.bestParams;
        }
    }

    // 使用最优参数运行一次完整回测获取详细结果
    const { result: bestResult } = runBacktest(code, klines, strategy, bestParams);

    return { bestParams, bestResult, allResults };
}

/**
 * 蒙特卡洛模拟
 * 随机重排交易序列，评估策略稳健性
 */
export function monteCarloSimulation(
    trades: BacktestTrade[],
    initialCapital: number,
    runs: number = 1000
): SimulationResult {
    const closedTrades = trades.filter((t: any) => t.action === 'sell');
    const profits = closedTrades.map((t: any) => t.profit || 0);

    if (profits.length === 0) {
        return { runs, bestCase: 0, worstCase: 0, average: 0, median: 0, confidence95: 0, drawdowns: [] };
    }

    const finalEquities: number[] = [];
    const maxDrawdowns: number[] = [];

    for (let i = 0; i < runs; i++) {
        // Shuffle profits
        const shuffled = [...profits].sort(() => Math.random() - 0.5);

        let capital = initialCapital;
        let peak = capital;
        let maxDD = 0;

        for (const p of shuffled) {
            capital += p;
            if (capital > peak) peak = capital;
            const dd = peak > 0 ? (peak - capital) / peak : 0;
            if (dd > maxDD) maxDD = dd;
        }
        finalEquities.push(capital);
        maxDrawdowns.push(maxDD);
    }

    finalEquities.sort((a: any, b: any) => a - b);
    maxDrawdowns.sort((a: any, b: any) => a - b);

    const sum = finalEquities.reduce((a: any, b: any) => a + b, 0);
    const avg = sum / runs;
    const median = finalEquities[Math.floor(runs / 2)];
    const best = finalEquities[runs - 1];
    const worst = finalEquities[0];
    const conf95Idx = Math.floor(runs * 0.05); // 5% quantile
    const conf95 = finalEquities[conf95Idx];

    return {
        runs,
        bestCase: (best - initialCapital) / initialCapital,
        worstCase: (worst - initialCapital) / initialCapital,
        average: (avg - initialCapital) / initialCapital,
        median: (median - initialCapital) / initialCapital,
        confidence95: (conf95 - initialCapital) / initialCapital,
        drawdowns: maxDrawdowns
    };
}

/**
 * 滚动前进分析 (Walk Forward Analysis)
 * 模拟实盘：在历史数据上通过"优化窗口"寻找最优参数，然后在随后的"测试窗口"上应用该参数
 */
export function walkForwardAnalysis(
    code: string,
    klines: KlineData[],
    strategy: string,
    baseParams: BacktestParams,
    paramRanges: Record<string, number[]>,
    trainWindow: number = 250, // 训练窗口长度 (e.g., 250 days)
    testWindow: number = 60    // 测试窗口长度 (e.g., 60 days)
): { results: Array<{ period: string; params: any; return: number }>; overallReturn: number } {
    if (klines.length < trainWindow + testWindow) {
        throw new Error('Data length insufficient for Walk Forward Analysis');
    }

    const segments: Array<{ period: string; params: any; return: number }> = [];
    let capital = baseParams.initialCapital;

    // 滚动窗口
    for (let i = 0; i < klines.length - trainWindow - testWindow; i += testWindow) {
        // 1. 训练集 (In-Sample)
        const trainKlines = klines.slice(i, i + trainWindow);
        const { bestParams } = optimizeParameters(code, trainKlines, strategy, baseParams, paramRanges);

        // 2. 测试集 (Out-of-Sample)
        const testStartIdx = i + trainWindow;
        const testEndIdx = Math.min(testStartIdx + testWindow, klines.length);
        const testKlines = klines.slice(testStartIdx, testEndIdx);

        if (testKlines.length === 0) break;

        // 在测试集上运行通过训练集得到的参数
        const { result } = runBacktest(code, testKlines, strategy, { ...bestParams, initialCapital: capital });

        capital = result.finalCapital;
        segments.push({
            period: `${testKlines[0].date} - ${testKlines[testKlines.length - 1].date}`,
            params: bestParams,
            return: result.totalReturn
        });
    }

    const overallReturn = (capital - baseParams.initialCapital) / baseParams.initialCapital;

    return { results: segments, overallReturn };
}


// ========== 动态止损止盈 ==========

export interface DynamicStopLossConfig {
    method: 'atr' | 'volatility' | 'percentage';
    atrMultiplier?: number;      // ATR倍数（默认2.0）
    atrPeriod?: number;          // ATR周期（默认14）
    volatilityMultiplier?: number; // 波动率倍数（默认1.5）
    volatilityPeriod?: number;   // 波动率周期（默认20）
    fixedPercentage?: number;    // 固定百分比（默认5%）
    trailingStop?: boolean;      // 是否使用移动止损（默认true）
}

export interface DynamicTakeProfitConfig {
    method: 'atr' | 'risk_reward' | 'percentage';
    atrMultiplier?: number;      // ATR倍数（默认3.0）
    riskRewardRatio?: number;    // 风险收益比（默认2:1）
    fixedPercentage?: number;    // 固定百分比（默认10%）
}

/**
 * 计算ATR（Average True Range）
 */
function calculateATR(klines: KlineData[], period: number = 14): number[] {
    const atr: number[] = [];
    const trueRanges: number[] = [];

    for (let i = 0; i < klines.length; i++) {
        if (i === 0) {
            trueRanges.push(klines[i].high - klines[i].low);
        } else {
            const tr = Math.max(
                klines[i].high - klines[i].low,
                Math.abs(klines[i].high - klines[i - 1].close),
                Math.abs(klines[i].low - klines[i - 1].close)
            );
            trueRanges.push(tr);
        }

        if (i >= period - 1) {
            const avgTR = trueRanges.slice(i - period + 1, i + 1).reduce((a: any, b: any) => a + b, 0) / period;
            atr.push(avgTR);
        }
    }

    return atr;
}

/**
 * 计算历史波动率
 */
function calculateVolatility(klines: KlineData[], period: number = 20): number[] {
    const volatility: number[] = [];
    const returns: number[] = [];

    for (let i = 1; i < klines.length; i++) {
        const ret = (klines[i].close - klines[i - 1].close) / klines[i - 1].close;
        returns.push(ret);

        if (i >= period) {
            const recentReturns = returns.slice(i - period, i);
            const mean = recentReturns.reduce((a: any, b: any) => a + b, 0) / period;
            const variance = recentReturns.reduce((a: any, b: any) => a + Math.pow(b - mean, 2), 0) / period;
            const std = Math.sqrt(variance);
            volatility.push(std);
        }
    }

    return volatility;
}

/**
 * 计算动态止损价格
 */
export function calculateDynamicStopLoss(
    entryPrice: number,
    currentPrice: number,
    klines: KlineData[],
    currentIndex: number,
    config: DynamicStopLossConfig
): number {
    const { method, trailingStop = true } = config;

    let stopLoss = 0;

    if (method === 'atr') {
        const atrPeriod = config.atrPeriod || 14;
        const atrMultiplier = config.atrMultiplier || 2.0;

        if (currentIndex >= atrPeriod - 1) {
            const atrValues = calculateATR(klines.slice(0, currentIndex + 1), atrPeriod);
            const currentATR = atrValues[atrValues.length - 1];

            if (trailingStop) {
                // 移动止损：基于当前价格
                stopLoss = currentPrice - (currentATR * atrMultiplier);
            } else {
                // 固定止损：基于入场价格
                stopLoss = entryPrice - (currentATR * atrMultiplier);
            }
        } else {
            // 数据不足，使用固定百分比
            stopLoss = entryPrice * 0.95;
        }
    } else if (method === 'volatility') {
        const volPeriod = config.volatilityPeriod || 20;
        const volMultiplier = config.volatilityMultiplier || 1.5;

        if (currentIndex >= volPeriod) {
            const volValues = calculateVolatility(klines.slice(0, currentIndex + 1), volPeriod);
            const currentVol = volValues[volValues.length - 1];

            if (trailingStop) {
                stopLoss = currentPrice * (1 - currentVol * volMultiplier);
            } else {
                stopLoss = entryPrice * (1 - currentVol * volMultiplier);
            }
        } else {
            stopLoss = entryPrice * 0.95;
        }
    } else if (method === 'percentage') {
        const percentage = config.fixedPercentage || 5;

        if (trailingStop) {
            stopLoss = currentPrice * (1 - percentage / 100);
        } else {
            stopLoss = entryPrice * (1 - percentage / 100);
        }
    }

    // 确保止损价格不高于入场价格（做多情况）
    return Math.min(stopLoss, entryPrice * 0.99);
}

/**
 * 计算动态止盈价格
 */
export function calculateDynamicTakeProfit(
    entryPrice: number,
    stopLossPrice: number,
    klines: KlineData[],
    currentIndex: number,
    config: DynamicTakeProfitConfig
): number {
    const { method } = config;

    let takeProfit = 0;

    if (method === 'atr') {
        const atrPeriod = 14;
        const atrMultiplier = config.atrMultiplier || 3.0;

        if (currentIndex >= atrPeriod - 1) {
            const atrValues = calculateATR(klines.slice(0, currentIndex + 1), atrPeriod);
            const currentATR = atrValues[atrValues.length - 1];
            takeProfit = entryPrice + (currentATR * atrMultiplier);
        } else {
            takeProfit = entryPrice * 1.10;
        }
    } else if (method === 'risk_reward') {
        const ratio = config.riskRewardRatio || 2.0;
        const risk = entryPrice - stopLossPrice;
        takeProfit = entryPrice + (risk * ratio);
    } else if (method === 'percentage') {
        const percentage = config.fixedPercentage || 10;
        takeProfit = entryPrice * (1 + percentage / 100);
    }

    return takeProfit;
}

/**
 * 带动态止损止盈的回测
 */
export function runBacktestWithDynamicStops(
    code: string,
    klines: KlineData[],
    strategy: string,
    params: BacktestParams,
    stopLossConfig: DynamicStopLossConfig,
    takeProfitConfig: DynamicTakeProfitConfig
): { result: BacktestResult; trades: BacktestTrade[]; equityCurve: Array<{ date: string; value: number; cash: number; shares: number; close: number; stopLoss?: number; takeProfit?: number }> } {
    const { initialCapital, commission, slippage } = params;

    // 先运行基础策略获取信号
    const baseBacktest = runBacktest(code, klines, strategy, params);
    const buySignals = baseBacktest.trades.filter((t: any) => t.action === 'buy');

    // 重新执行，加入动态止损止盈
    let cash = initialCapital;
    let shares = 0;
    let entryPrice = 0;
    let entryIndex = 0;
    let currentStopLoss = 0;
    let currentTakeProfit = 0;
    let highestPrice = 0;

    const trades: BacktestTrade[] = [];
    const equityCurve: Array<{ date: string; value: number; cash: number; shares: number; close: number; stopLoss?: number; takeProfit?: number }> = [];

    let buySignalIndex = 0;

    for (let i = 0; i < klines.length; i++) {
        const k = klines[i];
        let triggered = false;

        // 检查是否有买入信号
        if (buySignalIndex < buySignals.length && buySignals[buySignalIndex].date === k.date && shares === 0) {
            const buyPrice = k.close * (1 + slippage);
            const maxShares = Math.floor(cash / (buyPrice * (1 + commission)));

            if (maxShares > 0) {
                const cost = maxShares * buyPrice * (1 + commission);
                shares = maxShares;
                cash -= cost;
                entryPrice = buyPrice;
                entryIndex = i;
                highestPrice = buyPrice;

                // 计算初始止损止盈
                currentStopLoss = calculateDynamicStopLoss(entryPrice, k.close, klines, i, stopLossConfig);
                currentTakeProfit = calculateDynamicTakeProfit(entryPrice, currentStopLoss, klines, i, takeProfitConfig);

                trades.push({
                    date: k.date,
                    code,
                    action: 'buy',
                    price: buyPrice,
                    quantity: maxShares,
                    amount: cost
                });
            }
            buySignalIndex++;
        }

        // 持仓期间，检查止损止盈
        if (shares > 0) {
            // 更新最高价（用于移动止损）
            if (k.close > highestPrice) {
                highestPrice = k.close;
            }

            // 更新动态止损（如果是移动止损）
            if (stopLossConfig.trailingStop) {
                const newStopLoss = calculateDynamicStopLoss(entryPrice, highestPrice, klines, i, stopLossConfig);
                currentStopLoss = Math.max(currentStopLoss, newStopLoss); // 止损只能上移，不能下移
            }

            // 检查是否触发止损
            if (k.close <= currentStopLoss) {
                const sellPrice = currentStopLoss * (1 - slippage);
                const revenue = shares * sellPrice * (1 - commission);
                const profit = revenue - (shares * entryPrice * (1 + commission));

                trades.push({
                    date: k.date,
                    code,
                    action: 'sell',
                    price: sellPrice,
                    quantity: shares,
                    amount: revenue,
                    profit,
                    profitPercent: profit / (shares * entryPrice * (1 + commission))
                });

                cash += revenue;
                shares = 0;
                triggered = true;
            }
            // 检查是否触发止盈
            else if (k.close >= currentTakeProfit) {
                const sellPrice = currentTakeProfit * (1 - slippage);
                const revenue = shares * sellPrice * (1 - commission);
                const profit = revenue - (shares * entryPrice * (1 + commission));

                trades.push({
                    date: k.date,
                    code,
                    action: 'sell',
                    price: sellPrice,
                    quantity: shares,
                    amount: revenue,
                    profit,
                    profitPercent: profit / (shares * entryPrice * (1 + commission))
                });

                cash += revenue;
                shares = 0;
                triggered = true;
            }
        }

        const equity = cash + shares * k.close;
        equityCurve.push({
            date: k.date,
            value: equity,
            cash,
            shares,
            close: k.close,
            stopLoss: shares > 0 ? currentStopLoss : undefined,
            takeProfit: shares > 0 ? currentTakeProfit : undefined
        });
    }

    // 计算指标
    const finalCapital = equityCurve[equityCurve.length - 1]?.value || initialCapital;
    const totalReturn = (finalCapital - initialCapital) / initialCapital;

    let maxDrawdown = 0;
    let peak = -Infinity;
    for (const p of equityCurve) {
        if (p.value > peak) peak = p.value;
        const dd = (peak - p.value) / peak;
        if (dd > maxDrawdown) maxDrawdown = dd;
    }

    const returns = [];
    for (let i = 1; i < equityCurve.length; i++) {
        returns.push((equityCurve[i].value - equityCurve[i - 1].value) / equityCurve[i - 1].value);
    }
    const avgReturn = returns.reduce((a: any, b: any) => a + b, 0) / (returns.length || 1);
    const stdDev = Math.sqrt(returns.reduce((a: any, b: any) => a + Math.pow(b - avgReturn, 2), 0) / (returns.length || 1));
    const sharpeRatio = stdDev > 0 ? (avgReturn * 252 - 0.03) / (stdDev * Math.sqrt(252)) : 0;

    const sellTrades = trades.filter((t: any) => t.action === 'sell');
    const winningTrades = sellTrades.filter((t: any) => (t.profit || 0) > 0);
    const winRate = sellTrades.length > 0 ? winningTrades.length / sellTrades.length : 0;

    const grossProfit = winningTrades.reduce((sum, t) => sum + (t.profit || 0), 0);
    const grossLoss = sellTrades.filter((t: any) => (t.profit || 0) <= 0).reduce((sum, t) => sum + Math.abs(t.profit || 0), 0);
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : (grossProfit > 0 ? 999 : 0);

    const result: BacktestResult = {
        id: '',
        strategy: `${strategy}_dynamic_stops`,
        params: { ...params, stopLossConfig, takeProfitConfig } as any,
        stocks: [code],
        startDate: klines[0]?.date || '',
        endDate: klines[klines.length - 1]?.date || '',
        initialCapital,
        finalCapital,
        totalReturn,
        maxDrawdown,
        sharpeRatio,
        tradesCount: trades.length,
        winRate,
        profitFactor
    };

    return { result, trades, equityCurve };
}
