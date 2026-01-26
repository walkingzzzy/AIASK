/**
 * 优化的回测引擎
 * 使用 TypedArray 和对象池模式提升性能
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

interface EquityCurvePoint {
    date: string;
    value: number;
    cash: number;
    shares: number;
    close: number;
}

/**
 * 对象池：复用对象减少 GC 压力
 */
class ObjectPool<T> {
    private pool: T[] = [];
    private factory: () => T;
    private reset: (obj: T) => void;

    constructor(factory: () => T, reset: (obj: T) => void, initialSize: number = 0) {
        this.factory = factory;
        this.reset = reset;
        for (let i = 0; i < initialSize; i++) {
            this.pool.push(factory());
        }
    }

    acquire(): T {
        if (this.pool.length > 0) {
            return this.pool.pop()!;
        }
        return this.factory();
    }

    release(obj: T): void {
        this.reset(obj);
        this.pool.push(obj);
    }

    clear(): void {
        this.pool = [];
    }
}

// 权益曲线点对象池
const equityPointPool = new ObjectPool<EquityCurvePoint>(
    () => ({ date: '', value: 0, cash: 0, shares: 0, close: 0 }),
    (obj) => {
        obj.date = '';
        obj.value = 0;
        obj.cash = 0;
        obj.shares = 0;
        obj.close = 0;
    },
    1000
);

// 交易对象池
const tradePool = new ObjectPool<BacktestTrade>(
    () => ({
        date: '',
        code: '',
        action: 'buy',
        price: 0,
        quantity: 0,
        amount: 0,
    }),
    (obj) => {
        obj.date = '';
        obj.code = '';
        obj.action = 'buy';
        obj.price = 0;
        obj.quantity = 0;
        obj.amount = 0;
        obj.profit = undefined;
        obj.profitPercent = undefined;
    },
    100
);

/**
 * 优化的回测引擎
 * 使用 TypedArray 和对象池
 */
export function runOptimizedBacktest(
    code: string,
    klines: KlineData[],
    strategy: string,
    params: BacktestParams
): { result: BacktestResult; trades: BacktestTrade[]; equityCurve: EquityCurvePoint[] } {
    const { initialCapital, commission, slippage } = params;
    const n = klines.length;

    // 使用 TypedArray 存储价格数据（性能优化）
    const closes = new Float64Array(n);
    const opens = new Float64Array(n);
    const highs = new Float64Array(n);
    const lows = new Float64Array(n);
    const volumes = new Float64Array(n);

    for (let i = 0; i < n; i++) {
        closes[i] = klines[i].close;
        opens[i] = klines[i].open;
        highs[i] = klines[i].high;
        lows[i] = klines[i].low;
        volumes[i] = klines[i].volume;
    }

    // 生成信号
    const signals: Array<{ index: number; signal: 'buy' | 'sell'; price: number }> = [];

    if (strategy === 'buy_and_hold') {
        if (n > 0) {
            signals.push({ index: 0, signal: 'buy', price: closes[0] });
        }
    } else if (strategy === 'ma_cross') {
        const shortPeriod = params.shortPeriod || 5;
        const longPeriod = params.longPeriod || 20;

        // 转换为普通数组用于 MA 计算
        const closesArray = Array.from(closes);
        const shortMA = TechnicalServices.calculateSMA(closesArray, shortPeriod);
        const longMA = TechnicalServices.calculateSMA(closesArray, longPeriod);

        let position = false;
        const offset = longPeriod - 1;

        for (let i = 1; i < shortMA.length; i++) {
            const kIdx = i + offset;
            if (kIdx >= n) break;

            if (!position && shortMA[i] > longMA[i] && shortMA[i - 1] <= longMA[i - 1]) {
                signals.push({ index: kIdx, signal: 'buy', price: closes[kIdx] });
                position = true;
            } else if (position && shortMA[i] < longMA[i] && shortMA[i - 1] >= longMA[i - 1]) {
                signals.push({ index: kIdx, signal: 'sell', price: closes[kIdx] });
                position = false;
            }
        }
    } else if (strategy === 'rsi') {
        const closesArray = Array.from(closes);
        const rsi = TechnicalServices.calculateRSI(closesArray, 14);
        let position = false;
        const offset = 14;

        for (let i = 1; i < rsi.length; i++) {
            const kIdx = i + offset;
            if (kIdx >= n) break;

            if (!position && rsi[i] < 30) {
                signals.push({ index: kIdx, signal: 'buy', price: closes[kIdx] });
                position = true;
            } else if (position && rsi[i] > 70) {
                signals.push({ index: kIdx, signal: 'sell', price: closes[kIdx] });
                position = false;
            }
        }
    }

    // 执行交易（使用对象池）
    let cash = initialCapital;
    let shares = 0;
    const trades: BacktestTrade[] = [];
    const equityCurve: EquityCurvePoint[] = [];

    let signalIdx = 0;

    for (let i = 0; i < n; i++) {
        // 检查是否有信号
        if (signalIdx < signals.length && signals[signalIdx].index === i) {
            const signal = signals[signalIdx];
            signalIdx++;

            if (signal.signal === 'buy' && cash > 0) {
                const buyPrice = signal.price * (1 + slippage);
                const maxShares = Math.floor(cash / (buyPrice * (1 + commission)));
                
                if (maxShares > 0) {
                    const cost = maxShares * buyPrice * (1 + commission);
                    shares += maxShares;
                    cash -= cost;

                    const trade = tradePool.acquire();
                    trade.date = klines[i].date;
                    trade.code = code;
                    trade.action = 'buy';
                    trade.price = buyPrice;
                    trade.quantity = maxShares;
                    trade.amount = cost;
                    trades.push(trade);
                }
            } else if (signal.signal === 'sell' && shares > 0) {
                const sellPrice = signal.price * (1 - slippage);
                const revenue = shares * sellPrice * (1 - commission);

                const lastBuy = trades.filter(t => t.action === 'buy').pop();
                const buyPrice = lastBuy ? lastBuy.price : sellPrice;
                const profit = revenue - (shares * buyPrice * (1 + commission));

                const trade = tradePool.acquire();
                trade.date = klines[i].date;
                trade.code = code;
                trade.action = 'sell';
                trade.price = sellPrice;
                trade.quantity = shares;
                trade.amount = revenue;
                trade.profit = profit;
                trade.profitPercent = profit / (shares * buyPrice * (1 + commission));
                trades.push(trade);

                cash += revenue;
                shares = 0;
            }
        }

        // 记录权益曲线
        const equity = cash + shares * closes[i];
        const point = equityPointPool.acquire();
        point.date = klines[i].date;
        point.value = equity;
        point.cash = cash;
        point.shares = shares;
        point.close = closes[i];
        equityCurve.push(point);
    }

    // 计算回测结果
    const finalCapital = cash + shares * closes[n - 1];
    const totalReturn = (finalCapital - initialCapital) / initialCapital;

    // 计算最大回撤
    let peak = initialCapital;
    let maxDrawdown = 0;
    for (const point of equityCurve) {
        if (point.value > peak) peak = point.value;
        const dd = peak > 0 ? (peak - point.value) / peak : 0;
        if (dd > maxDrawdown) maxDrawdown = dd;
    }

    // 计算夏普比率
    const returns: number[] = [];
    for (let i = 1; i < equityCurve.length; i++) {
        const ret = (equityCurve[i].value - equityCurve[i - 1].value) / equityCurve[i - 1].value;
        returns.push(ret);
    }
    const avgReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
    const variance = returns.reduce((a, b) => a + Math.pow(b - avgReturn, 2), 0) / returns.length;
    const stdDev = Math.sqrt(variance);
    const sharpeRatio = stdDev > 0 ? (avgReturn / stdDev) * Math.sqrt(252) : 0;

    // 胜率
    const winningTrades = trades.filter(t => t.action === 'sell' && (t.profit || 0) > 0).length;
    const totalTrades = trades.filter(t => t.action === 'sell').length;
    const winRate = totalTrades > 0 ? winningTrades / totalTrades : 0;

    const result: BacktestResult = {
        id: '',
        strategy: strategy,
        params: { ...params } as Record<string, unknown>,
        stocks: [code],
        startDate: klines[0].date,
        endDate: klines[n - 1].date,
        initialCapital,
        finalCapital,
        totalReturn,
        maxDrawdown,
        sharpeRatio,
        tradesCount: totalTrades,
        winRate,
        profitFactor: 0, // 简化
    };

    return { result, trades, equityCurve };
}

/**
 * 清理对象池（在不需要时释放内存）
 */
export function clearObjectPools(): void {
    equityPointPool.clear();
    tradePool.clear();
}
