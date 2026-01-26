/**
 * 技术分析服务
 * 计算各种技术指标
 */

import * as ti from 'technicalindicators';
import type { KlineData, IndicatorResult, TechnicalIndicator } from '../types/stock.js';

/**
 * 从K线数据提取OHLCV
 */
function extractOHLCV(klines: KlineData[]) {
    return {
        open: klines.map((k: any) => k.open),
        high: klines.map((k: any) => k.high),
        low: klines.map((k: any) => k.low),
        close: klines.map((k: any) => k.close),
        volume: klines.map((k: any) => k.volume),
    };
}

/**
 * 计算 SMA (简单移动平均)
 */
export function calculateSMA(closes: number[], period: number): number[] {
    return ti.SMA.calculate({ period, values: closes });
}

/**
 * 计算 EMA (指数移动平均)
 */
export function calculateEMA(closes: number[], period: number): number[] {
    return ti.EMA.calculate({ period, values: closes });
}

/**
 * 计算 RSI (相对强弱指标)
 */
export function calculateRSI(closes: number[], period: number = 14): number[] {
    return ti.RSI.calculate({ period, values: closes });
}

/**
 * 计算 MACD
 */
export function calculateMACD(closes: number[], fastPeriod: number = 12, slowPeriod: number = 26, signalPeriod: number = 9): {
    macd: number[];
    signal: number[];
    histogram: number[];
} {
    const result = ti.MACD.calculate({
        values: closes,
        fastPeriod,
        slowPeriod,
        signalPeriod,
        SimpleMAOscillator: false,
        SimpleMASignal: false,
    });

    return {
        macd: result.map((r: any) => r.MACD || 0),
        signal: result.map((r: any) => r.signal || 0),
        histogram: result.map((r: any) => r.histogram || 0),
    };
}

/**
 * 计算 KDJ
 */
export function calculateKDJ(highs: number[], lows: number[], closes: number[], period: number = 9, signalPeriod: number = 3): {
    k: number[];
    d: number[];
    j: number[];
} {
    const stoch = ti.Stochastic.calculate({
        high: highs,
        low: lows,
        close: closes,
        period,
        signalPeriod,
    });

    const k = stoch.map((s: any) => s.k);
    const d = stoch.map((s: any) => s.d);
    const j = stoch.map((s) => 3 * s.k - 2 * s.d);

    return { k, d, j };
}

/**
 * 计算布林带
 */
export function calculateBollingerBands(closes: number[], period: number = 20, stdDev: number = 2): {
    upper: number[];
    middle: number[];
    lower: number[];
} {
    const result = ti.BollingerBands.calculate({
        period,
        values: closes,
        stdDev,
    });

    return {
        upper: result.map((r: any) => r.upper),
        middle: result.map((r: any) => r.middle),
        lower: result.map((r: any) => r.lower),
    };
}

/**
 * 计算 ATR (平均真实波幅)
 */
export function calculateATR(highs: number[], lows: number[], closes: number[], period: number = 14): number[] {
    return ti.ATR.calculate({
        high: highs,
        low: lows,
        close: closes,
        period,
    });
}

/**
 * 计算 OBV (能量潮)
 */
export function calculateOBV(closes: number[], volumes: number[]): number[] {
    return ti.OBV.calculate({
        close: closes,
        volume: volumes,
    });
}

/**
 * 计算 CCI (顺势指标)
 */
export function calculateCCI(highs: number[], lows: number[], closes: number[], period: number = 20): number[] {
    return ti.CCI.calculate({
        high: highs,
        low: lows,
        close: closes,
        period,
    });
}

/**
 * 计算 Williams %R
 */
export function calculateWilliamsR(highs: number[], lows: number[], closes: number[], period: number = 14): number[] {
    return ti.WilliamsR.calculate({
        high: highs,
        low: lows,
        close: closes,
        period,
    });
}

/**
 * 计算 ROC (变动率)
 */
export function calculateROC(closes: number[], period: number = 12): number[] {
    return ti.ROC.calculate({
        period,
        values: closes,
    });
}

/**
 * 计算多个技术指标
 */
export function calculateIndicators(klines: KlineData[], indicators: TechnicalIndicator[], timeperiod: number = 14): IndicatorResult[] {
    const { high, low, close, volume } = extractOHLCV(klines);
    const results: IndicatorResult[] = [];

    for (const indicator of indicators) {
        let values: number[] = [];
        let signal: 'buy' | 'sell' | 'hold' | undefined;

        switch (indicator) {
            case 'sma':
                values = calculateSMA(close, timeperiod);
                break;
            case 'ema':
                values = calculateEMA(close, timeperiod);
                break;
            case 'rsi': {
                values = calculateRSI(close, timeperiod);
                const lastRsi = values[values.length - 1];
                if (lastRsi !== undefined) {
                    if (lastRsi < 30) signal = 'buy';
                    else if (lastRsi > 70) signal = 'sell';
                    else signal = 'hold';
                }
                break;
            }
            case 'macd': {
                const macdResult = calculateMACD(close);
                values = macdResult.histogram;
                const lastHist = macdResult.histogram[macdResult.histogram.length - 1];
                const prevHist = macdResult.histogram[macdResult.histogram.length - 2];
                if (lastHist !== undefined && prevHist !== undefined) {
                    if (lastHist > 0 && prevHist < 0) signal = 'buy';
                    else if (lastHist < 0 && prevHist > 0) signal = 'sell';
                    else signal = 'hold';
                }
                break;
            }
            case 'kdj': {
                const kdjResult = calculateKDJ(high, low, close);
                values = kdjResult.j;
                const lastJ = kdjResult.j[kdjResult.j.length - 1];
                if (lastJ !== undefined) {
                    if (lastJ < 20) signal = 'buy';
                    else if (lastJ > 80) signal = 'sell';
                    else signal = 'hold';
                }
                break;
            }
            case 'boll': {
                const bollResult = calculateBollingerBands(close, timeperiod);
                values = bollResult.middle;
                break;
            }
            case 'atr':
                values = calculateATR(high, low, close, timeperiod);
                break;
            case 'obv':
                values = calculateOBV(close, volume);
                break;
            case 'cci': {
                values = calculateCCI(high, low, close, timeperiod);
                const lastCci = values[values.length - 1];
                if (lastCci !== undefined) {
                    if (lastCci < -100) signal = 'buy';
                    else if (lastCci > 100) signal = 'sell';
                    else signal = 'hold';
                }
                break;
            }
            case 'williamsr': {
                values = calculateWilliamsR(high, low, close, timeperiod);
                const lastWr = values[values.length - 1];
                if (lastWr !== undefined) {
                    if (lastWr < -80) signal = 'buy';
                    else if (lastWr > -20) signal = 'sell';
                    else signal = 'hold';
                }
                break;
            }
            case 'roc':
                values = calculateROC(close, timeperiod);
                break;
            default:
                continue;
        }

        results.push({
            indicator,
            values,
            signal,
        });
    }

    return results;
}

/**
 * 检测K线形态
 */
export function detectPatterns(klines: KlineData[]): Array<{ pattern: string; detected: boolean; bullish: boolean }> {
    const { open, high, low, close } = extractOHLCV(klines);
    const patterns: Array<{ pattern: string; detected: boolean; bullish: boolean }> = [];

    // 十字星
    const doji = ti.doji({ open, high, low, close });
    patterns.push({
        pattern: 'doji',
        detected: doji[doji.length - 1] || false,
        bullish: false, // 中性形态
    });

    // 锤头线
    const hammer = ti.hammerpattern({ open, high, low, close });
    patterns.push({
        pattern: 'hammer',
        detected: hammer[hammer.length - 1] || false,
        bullish: true,
    });

    // 吞没形态
    const bullishEngulfing = ti.bullishengulfingpattern({ open, high, low, close });
    patterns.push({
        pattern: 'bullish_engulfing',
        detected: bullishEngulfing[bullishEngulfing.length - 1] || false,
        bullish: true,
    });

    const bearishEngulfing = ti.bearishengulfingpattern({ open, high, low, close });
    patterns.push({
        pattern: 'bearish_engulfing',
        detected: bearishEngulfing[bearishEngulfing.length - 1] || false,
        bullish: false,
    });

    // 早晨之星
    const morningStar = ti.morningstar({ open, high, low, close });
    patterns.push({
        pattern: 'morning_star',
        detected: morningStar[morningStar.length - 1] || false,
        bullish: true,
    });

    // 黄昏之星
    const eveningStar = ti.eveningstar({ open, high, low, close });
    patterns.push({
        pattern: 'evening_star',
        detected: eveningStar[eveningStar.length - 1] || false,
        bullish: false,
    });

    // 三白兵
    const threeWhiteSoldiers = ti.threewhitesoldiers({ open, high, low, close });
    patterns.push({
        pattern: 'three_white_soldiers',
        detected: threeWhiteSoldiers[threeWhiteSoldiers.length - 1] || false,
        bullish: true,
    });

    // 三乌鸦
    const threeBlackCrows = ti.threeblackcrows({ open, high, low, close });
    patterns.push({
        pattern: 'three_black_crows',
        detected: threeBlackCrows[threeBlackCrows.length - 1] || false,
        bullish: false,
    });

    return patterns;
}

/**
 * 计算支撑压力位
 */
export function calculateSupportResistance(klines: KlineData[]): { supports: number[]; resistances: number[] } {
    const { high, low, close } = extractOHLCV(klines);

    // 使用简单的高低点方法
    const lookback = Math.min(20, klines.length);
    const recentHighs = high.slice(-lookback);
    const recentLows = low.slice(-lookback);
    const currentPrice = close[close.length - 1];

    // 找出局部高点作为压力位
    const resistances: number[] = [];
    for (let i = 1; i < recentHighs.length - 1; i++) {
        if (recentHighs[i] > recentHighs[i - 1] && recentHighs[i] > recentHighs[i + 1]) {
            if (recentHighs[i] > currentPrice) {
                resistances.push(recentHighs[i]);
            }
        }
    }

    // 找出局部低点作为支撑位
    const supports: number[] = [];
    for (let i = 1; i < recentLows.length - 1; i++) {
        if (recentLows[i] < recentLows[i - 1] && recentLows[i] < recentLows[i + 1]) {
            if (recentLows[i] < currentPrice) {
                supports.push(recentLows[i]);
            }
        }
    }

    // 排序并返回最近的几个
    return {
        supports: supports.sort((a: any, b: any) => b - a).slice(0, 3),
        resistances: resistances.sort((a: any, b: any) => a - b).slice(0, 3),
    };
}

/**
 * 生成综合交易信号
 */
export function generateTradingSignal(indicators: IndicatorResult[]): {
    signal: 'strong_buy' | 'buy' | 'hold' | 'sell' | 'strong_sell';
    confidence: number;
    reasons: string[];
} {
    let buySignals = 0;
    let sellSignals = 0;
    const reasons: string[] = [];

    for (const ind of indicators) {
        if (ind.signal === 'buy') {
            buySignals++;
            reasons.push(`${ind.indicator.toUpperCase()} 发出买入信号`);
        } else if (ind.signal === 'sell') {
            sellSignals++;
            reasons.push(`${ind.indicator.toUpperCase()} 发出卖出信号`);
        }
    }

    const total = indicators.length;
    const buyRatio = buySignals / total;
    const sellRatio = sellSignals / total;

    let signal: 'strong_buy' | 'buy' | 'hold' | 'sell' | 'strong_sell';
    let confidence: number;

    if (buyRatio >= 0.7) {
        signal = 'strong_buy';
        confidence = buyRatio;
    } else if (buyRatio >= 0.5) {
        signal = 'buy';
        confidence = buyRatio;
    } else if (sellRatio >= 0.7) {
        signal = 'strong_sell';
        confidence = sellRatio;
    } else if (sellRatio >= 0.5) {
        signal = 'sell';
        confidence = sellRatio;
    } else {
        signal = 'hold';
        confidence = 1 - Math.max(buyRatio, sellRatio);
    }

    return { signal, confidence, reasons };
}
