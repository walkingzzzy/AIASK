/**
 * 情绪分析服务
 * 市场情绪、恐惧贪婪指数等计算
 */

import type { RealtimeQuote, KlineData } from '../types/stock.js';

/**
 * 恐惧贪婪指数计算
 */
export function calculateFearGreedIndex(
    marketData: {
        advances: number;      // 上涨家数
        declines: number;      // 下跌家数
        newHighs: number;      // 新高数
        newLows: number;       // 新低数
        volumeRatio: number;   // 成交量比率
        volatility: number;    // 波动率
    }
): {
    index: number;
    level: 'extreme_fear' | 'fear' | 'neutral' | 'greed' | 'extreme_greed';
    components: Record<string, number>;
} {
    const { advances, declines, newHighs, newLows, volumeRatio, volatility } = marketData;

    // 市场宽度指标 (0-100)
    const breadth = advances / (advances + declines) * 100;

    // 新高新低比 (0-100)
    const highLowRatio = newHighs / (newHighs + newLows + 1) * 100;

    // 成交量指标 (0-100)
    const volumeScore = Math.min(volumeRatio * 50, 100);

    // 波动率反向指标 (波动率高则恐惧)
    const volatilityScore = Math.max(0, 100 - volatility * 5);

    // 综合指数 (各指标等权重)
    const index = (breadth + highLowRatio + volumeScore + volatilityScore) / 4;

    let level: 'extreme_fear' | 'fear' | 'neutral' | 'greed' | 'extreme_greed';
    if (index < 20) level = 'extreme_fear';
    else if (index < 40) level = 'fear';
    else if (index < 60) level = 'neutral';
    else if (index < 80) level = 'greed';
    else level = 'extreme_greed';

    return {
        index: Math.round(index),
        level,
        components: {
            marketBreadth: Math.round(breadth),
            highLowRatio: Math.round(highLowRatio),
            volume: Math.round(volumeScore),
            volatility: Math.round(volatilityScore),
        },
    };
}

/**
 * 个股情绪分析
 */
export function analyzeStockSentiment(
    quote: RealtimeQuote,
    klines: KlineData[],
    newsCount: number = 0,
    positiveNewsRatio: number = 0.5
): {
    sentiment: 'very_bullish' | 'bullish' | 'neutral' | 'bearish' | 'very_bearish';
    score: number;
    factors: Array<{ name: string; score: number; weight: number }>;
} {
    const factors: Array<{ name: string; score: number; weight: number }> = [];

    // 价格动量 (今日涨跌幅)
    const priceScore = Math.min(100, Math.max(0, 50 + quote.changePercent * 5));
    factors.push({ name: '价格动量', score: priceScore, weight: 0.3 });

    // 成交量 (换手率)
    const volumeScore = Math.min(100, quote.turnoverRate * 10);
    factors.push({ name: '成交活跃度', score: volumeScore, weight: 0.2 });

    // 趋势 (5日均线)
    if (klines.length >= 5) {
        const ma5 = klines.slice(-5).reduce((sum, k) => sum + k.close, 0) / 5;
        const trendScore = quote.price > ma5 ? 70 : 30;
        factors.push({ name: '短期趋势', score: trendScore, weight: 0.25 });
    }

    // 新闻情绪
    if (newsCount > 0) {
        const newsScore = positiveNewsRatio * 100;
        factors.push({ name: '新闻情绪', score: newsScore, weight: 0.25 });
    } else {
        factors.push({ name: '新闻情绪', score: 50, weight: 0.25 });
    }

    // 加权平均
    const totalWeight = factors.reduce((sum, f) => sum + f.weight, 0);
    const score = factors.reduce((sum, f) => sum + f.score * f.weight, 0) / totalWeight;

    let sentiment: 'very_bullish' | 'bullish' | 'neutral' | 'bearish' | 'very_bearish';
    if (score >= 75) sentiment = 'very_bullish';
    else if (score >= 60) sentiment = 'bullish';
    else if (score >= 40) sentiment = 'neutral';
    else if (score >= 25) sentiment = 'bearish';
    else sentiment = 'very_bearish';

    return { sentiment, score: Math.round(score), factors };
}

/**
 * 市场整体情绪分析
 */
export function analyzeMarketSentiment(
    indices: RealtimeQuote[],
    limitUpCount: number,
    limitDownCount: number,
    northFundFlow?: number | null
): {
    sentiment: 'very_bullish' | 'bullish' | 'neutral' | 'bearish' | 'very_bearish';
    score: number;
    indicators: Record<string, { value: number; signal: string }>;
} {
    const indicators: Record<string, { value: number; signal: string }> = {};
    let totalScore = 0;
    let count = 0;

    // 指数表现
    if (indices.length > 0) {
        const avgChange = indices.reduce((sum, i) => sum + i.changePercent, 0) / indices.length;
        const indexScore = 50 + avgChange * 10;
        indicators['指数涨跌'] = {
            value: avgChange,
            signal: avgChange > 0 ? 'positive' : avgChange < 0 ? 'negative' : 'neutral',
        };
        totalScore += indexScore;
        count++;
    }

    // 涨跌停比
    if (limitUpCount + limitDownCount > 0) {
        const limitRatio = limitUpCount / (limitUpCount + limitDownCount);
        const limitScore = limitRatio * 100;
        indicators['涨跌停比'] = {
            value: limitRatio,
            signal: limitRatio > 0.7 ? 'very_positive' : limitRatio > 0.5 ? 'positive' : 'negative',
        };
        totalScore += limitScore;
        count++;
    }

    // 北向资金
    if (typeof northFundFlow === 'number') {
        const northScore = 50 + Math.min(50, Math.max(-50, northFundFlow / 100000000 * 10));
        indicators['北向资金'] = {
            value: northFundFlow / 100000000,
            signal: northFundFlow > 0 ? 'positive' : 'negative',
        };
        totalScore += northScore;
        count++;
    }

    const score = count > 0 ? totalScore / count : 50;

    let sentiment: 'very_bullish' | 'bullish' | 'neutral' | 'bearish' | 'very_bearish';
    if (score >= 75) sentiment = 'very_bullish';
    else if (score >= 60) sentiment = 'bullish';
    else if (score >= 40) sentiment = 'neutral';
    else if (score >= 25) sentiment = 'bearish';
    else sentiment = 'very_bearish';

    return { sentiment, score: Math.round(score), indicators };
}
