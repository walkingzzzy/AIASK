/**
 * 向量化回测引擎
 * 使用数组操作替代循环，提升性能
 */

import { BacktestResult, BacktestTrade, KlineData } from '../types/stock.js';
import { BacktestParams } from './backtest.js';

/**
 * 向量化计算收益率
 */
function calculateReturns(prices: number[]): number[] {
    const returns = new Array(prices.length - 1);
    for (let i = 1; i < prices.length; i++) {
        returns[i - 1] = (prices[i] - prices[i - 1]) / prices[i - 1];
    }
    return returns;
}

/**
 * 向量化计算移动平均
 */
function calculateMA(prices: number[], period: number): number[] {
    const ma = new Array(prices.length);
    let sum = 0;
    
    // 初始化前period个元素的和
    for (let i = 0; i < Math.min(period, prices.length); i++) {
        sum += prices[i];
        ma[i] = sum / (i + 1);
    }
    
    // 滑动窗口计算
    for (let i = period; i < prices.length; i++) {
        sum = sum - prices[i - period] + prices[i];
        ma[i] = sum / period;
    }
    
    return ma;
}

/**
 * 向量化生成交叉信号
 */
function generateCrossSignals(
    shortMA: number[],
    longMA: number[],
    offset: number = 0
): Array<{ index: number; signal: 'buy' | 'sell' }> {
    const signals: Array<{ index: number; signal: 'buy' | 'sell' }> = [];
    
    for (let i = 1; i < Math.min(shortMA.length, longMA.length); i++) {
        const prevShort = shortMA[i - 1];
        const prevLong = longMA[i - 1];
        const currShort = shortMA[i];
        const currLong = longMA[i];
        
        // 金叉：短期均线上穿长期均线
        if (prevShort <= prevLong && currShort > currLong) {
            signals.push({ index: i + offset, signal: 'buy' });
        }
        // 死叉：短期均线下穿长期均线
        else if (prevShort >= prevLong && currShort < currLong) {
            signals.push({ index: i + offset, signal: 'sell' });
        }
    }
    
    return signals;
}

/**
 * 向量化计算权益曲线
 */
function calculateEquityCurve(
    prices: number[],
    signals: Array<{ index: number; signal: 'buy' | 'sell' }>,
    initialCapital: number,
    commission: number,
    slippage: number
): {
    equity: number[];
    cash: number[];
    shares: number[];
    trades: Array<{ index: number; action: 'buy' | 'sell'; price: number; quantity: number; amount: number }>;
} {
    const equity = new Array(prices.length);
    const cash = new Array(prices.length);
    const shares = new Array(prices.length);
    const trades: Array<{ index: number; action: 'buy' | 'sell'; price: number; quantity: number; amount: number }> = [];
    
    let currentCash = initialCapital;
    let currentShares = 0;
    let signalIndex = 0;
    
    for (let i = 0; i < prices.length; i++) {
        // 检查是否有信号
        if (signalIndex < signals.length && signals[signalIndex].index === i) {
            const signal = signals[signalIndex];
            
            if (signal.signal === 'buy' && currentCash > 0) {
                const buyPrice = prices[i] * (1 + slippage);
                const maxShares = Math.floor(currentCash / (buyPrice * (1 + commission)));
                
                if (maxShares > 0) {
                    const cost = maxShares * buyPrice * (1 + commission);
                    currentShares += maxShares;
                    currentCash -= cost;
                    
                    trades.push({
                        index: i,
                        action: 'buy',
                        price: buyPrice,
                        quantity: maxShares,
                        amount: cost
                    });
                }
            } else if (signal.signal === 'sell' && currentShares > 0) {
                const sellPrice = prices[i] * (1 - slippage);
                const revenue = currentShares * sellPrice * (1 - commission);
                
                trades.push({
                    index: i,
                    action: 'sell',
                    price: sellPrice,
                    quantity: currentShares,
                    amount: revenue
                });
                
                currentCash += revenue;
                currentShares = 0;
            }
            
            signalIndex++;
        }
        
        cash[i] = currentCash;
        shares[i] = currentShares;
        equity[i] = currentCash + currentShares * prices[i];
    }
    
    return { equity, cash, shares, trades };
}

/**
 * 向量化计算最大回撤
 */
function calculateMaxDrawdown(equity: number[]): number {
    let maxDD = 0;
    let peak = -Infinity;
    
    for (let i = 0; i < equity.length; i++) {
        if (equity[i] > peak) {
            peak = equity[i];
        }
        const dd = peak > 0 ? (peak - equity[i]) / peak : 0;
        if (dd > maxDD) {
            maxDD = dd;
        }
    }
    
    return maxDD;
}

/**
 * 向量化计算夏普比率
 */
function calculateSharpeRatio(equity: number[], riskFreeRate: number = 0.03): number {
    const returns = calculateReturns(equity);
    
    if (returns.length === 0) return 0;
    
    const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
    const variance = returns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / returns.length;
    const stdDev = Math.sqrt(variance);
    
    if (stdDev === 0) return 0;
    
    // 年化
    const annualizedReturn = avgReturn * 252;
    const annualizedStd = stdDev * Math.sqrt(252);
    
    return (annualizedReturn - riskFreeRate) / annualizedStd;
}

/**
 * 向量化回测 - MA交叉策略
 */
export function runVectorizedBacktest(
    code: string,
    klines: KlineData[],
    strategy: string,
    params: BacktestParams
): { result: BacktestResult; trades: BacktestTrade[]; equityCurve: Array<{ date: string; value: number; cash: number; shares: number; close: number }> } {
    const { initialCapital, commission, slippage } = params;
    const closes = klines.map(k => k.close);
    
    let signals: Array<{ index: number; signal: 'buy' | 'sell' }> = [];
    
    // 生成信号（向量化）
    if (strategy === 'ma_cross') {
        const shortPeriod = params.shortPeriod || 5;
        const longPeriod = params.longPeriod || 20;
        
        const maShort = calculateMA(closes, shortPeriod);
        const maLong = calculateMA(closes, longPeriod);
        
        // 从长期均线有效的位置开始
        const offset = longPeriod - 1;
        const validShort = maShort.slice(offset);
        const validLong = maLong.slice(offset);
        
        signals = generateCrossSignals(validShort, validLong, offset);
    } else if (strategy === 'buy_and_hold') {
        signals = [{ index: 0, signal: 'buy' }];
    }
    
    // 计算权益曲线（向量化）
    const { equity, cash, shares, trades: rawTrades } = calculateEquityCurve(
        closes,
        signals,
        initialCapital,
        commission,
        slippage
    );
    
    // 转换为标准格式
    const trades: BacktestTrade[] = rawTrades.map(t => {
        const base = {
            date: klines[t.index].date,
            code,
            action: t.action,
            price: t.price,
            quantity: t.quantity,
            amount: t.amount,
        };
        
        if (t.action === 'sell') {
            return {
                ...base,
                profit: calculateTradeProfit(rawTrades, t as any, commission),
                profitPercent: calculateTradeProfitPercent(rawTrades, t as any, commission)
            };
        }
        
        return base;
    });
    
    const equityCurve = klines.map((k, i) => ({
        date: k.date,
        value: equity[i],
        cash: cash[i],
        shares: shares[i],
        close: k.close
    }));
    
    // 计算指标（向量化）
    const finalCapital = equity[equity.length - 1];
    const totalReturn = (finalCapital - initialCapital) / initialCapital;
    const maxDrawdown = calculateMaxDrawdown(equity);
    const sharpeRatio = calculateSharpeRatio(equity);
    
    // 统计胜率
    const sellTrades = trades.filter(t => t.action === 'sell');
    const winningTrades = sellTrades.filter(t => (t.profit || 0) > 0);
    const winRate = sellTrades.length > 0 ? winningTrades.length / sellTrades.length : 0;
    
    const grossProfit = winningTrades.reduce((sum, t) => sum + (t.profit || 0), 0);
    const grossLoss = sellTrades
        .filter(t => (t.profit || 0) <= 0)
        .reduce((sum, t) => sum + Math.abs(t.profit || 0), 0);
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : (grossProfit > 0 ? 999 : 0);
    
    const result: BacktestResult = {
        id: '',
        strategy: `${strategy}_vectorized`,
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
 * 计算单笔交易盈亏
 */
function calculateTradeProfit(
    trades: Array<{ index: number; action: 'buy' | 'sell'; price: number; quantity: number; amount: number }>,
    sellTrade: { index: number; action: 'sell'; price: number; quantity: number; amount: number },
    commission: number
): number {
    // 找到最近的买入交易
    const buyTrades = trades.filter(t => t.action === 'buy' && t.index < sellTrade.index);
    if (buyTrades.length === 0) return 0;
    
    const lastBuy = buyTrades[buyTrades.length - 1];
    const cost = sellTrade.quantity * lastBuy.price * (1 + commission);
    const revenue = sellTrade.amount;
    
    return revenue - cost;
}

/**
 * 计算单笔交易盈亏百分比
 */
function calculateTradeProfitPercent(
    trades: Array<{ index: number; action: 'buy' | 'sell'; price: number; quantity: number; amount: number }>,
    sellTrade: { index: number; action: 'sell'; price: number; quantity: number; amount: number },
    commission: number
): number {
    const profit = calculateTradeProfit(trades, sellTrade, commission);
    const buyTrades = trades.filter(t => t.action === 'buy' && t.index < sellTrade.index);
    if (buyTrades.length === 0) return 0;
    
    const lastBuy = buyTrades[buyTrades.length - 1];
    const cost = sellTrade.quantity * lastBuy.price * (1 + commission);
    
    return cost > 0 ? profit / cost : 0;
}

/**
 * 批量向量化回测
 * 同时回测多个股票，共享计算资源
 */
export function runBatchVectorizedBacktest(
    stocks: Array<{ code: string; klines: KlineData[] }>,
    strategy: string,
    params: BacktestParams
): Array<{ code: string; result: BacktestResult }> {
    const results: Array<{ code: string; result: BacktestResult }> = [];
    
    for (const stock of stocks) {
        try {
            const { result } = runVectorizedBacktest(stock.code, stock.klines, strategy, params);
            results.push({ code: stock.code, result });
        } catch (error) {
            // Skip failed backtests
            continue;
        }
    }
    
    return results;
}
