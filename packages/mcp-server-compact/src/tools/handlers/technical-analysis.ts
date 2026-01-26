import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import * as TechnicalServices from '../../services/technical-analysis.js';
import * as PatternServices from '../../services/pattern-recognition.js';

export const technicalAnalysisManagerTool: ToolDefinition = {
    name: 'technical_analysis_manager',
    description: '高级技术分析管理',
    category: 'technical_analysis',
    inputSchema: managerSchema,
    tags: ['technical', 'manager'],
    dataSource: 'real',
};

export const technicalAnalysisManagerHandler: ToolHandler = async (params: any) => {
    const { action, code, period = '101' } = params;

    if (!code) return { success: false, error: 'Missing code parameter' };

    // Common data fetching
    const klineRes = await adapterManager.getKline(code, period, 200);
    const klines = klineRes.success && klineRes.data ? klineRes.data : [];

    if (klines.length === 0) return { success: false, error: `No kline data found for ${code}` };

    const closes = klines.map((k: any) => k.close);
    const highs = klines.map((k: any) => k.high);
    const lows = klines.map((k: any) => k.low);

    if (action === 'calculate_indicators') {
        const ma = TechnicalServices.calculateSMA(closes, 20);
        const macd = TechnicalServices.calculateMACD(closes);
        const kdj = TechnicalServices.calculateKDJ(highs, lows, closes);
        const rsi = TechnicalServices.calculateRSI(closes, 14);
        
        // 只返回最近20个值
        const limit = 20;
        return { 
            success: true, 
            data: { 
                ma: ma.slice(-limit),
                macd: {
                    macd: macd.macd.slice(-limit),
                    signal: macd.signal.slice(-limit),
                    histogram: macd.histogram.slice(-limit)
                },
                kdj: {
                    k: kdj.k.slice(-limit),
                    d: kdj.d.slice(-limit),
                    j: kdj.j.slice(-limit)
                },
                rsi: rsi.slice(-limit),
                note: '仅显示最近20个数据点'
            } 
        };
    }

    if (action === 'check_patterns') {
        const patterns = PatternServices.detectAllPatterns(klines);
        // Filter only detected patterns to keep output clean
        const detected = patterns.filter((p: any) => p.detected);
        return { success: true, data: { patterns: detected } };
    }

    // ===== 支撑阻力位计算 =====
    if (action === 'calculate_support_resistance' || action === 'support_resistance') {
        // 使用近期高低点作为支撑阻力
        const recentHighs = highs.slice(-20);
        const recentLows = lows.slice(-20);
        const maxHigh = Math.max(...recentHighs);
        const minLow = Math.min(...recentLows);
        const currentPrice = closes[closes.length - 1];

        // 简化的支撑阻力
        const pivot = (maxHigh + minLow + currentPrice) / 3;
        const resistance1 = 2 * pivot - minLow;
        const resistance2 = pivot + (maxHigh - minLow);
        const support1 = 2 * pivot - maxHigh;
        const support2 = pivot - (maxHigh - minLow);

        return {
            success: true,
            data: {
                code,
                currentPrice,
                pivot: parseFloat(pivot.toFixed(2)),
                resistance: {
                    r1: parseFloat(resistance1.toFixed(2)),
                    r2: parseFloat(resistance2.toFixed(2)),
                },
                support: {
                    s1: parseFloat(support1.toFixed(2)),
                    s2: parseFloat(support2.toFixed(2)),
                },
                method: 'pivot_points',
            },
        };
    }

    // ===== 背离检测 =====
    if (action === 'detect_divergence' || action === 'divergence') {
        const rsi = TechnicalServices.calculateRSI(closes, 14);
        const macd = TechnicalServices.calculateMACD(closes);
        const divergences: any[] = [];

        // 检测 RSI 背离
        if (rsi.length >= 20 && closes.length >= 20) {
            const priceRecent = closes.slice(-10);
            const rsiRecent = rsi.slice(-10);
            const pricePrev = closes.slice(-20, -10);
            const rsiPrev = rsi.slice(-20, -10);

            const priceHigh1 = Math.max(...priceRecent);
            const priceHigh2 = Math.max(...pricePrev);
            const rsiHigh1 = Math.max(...rsiRecent);
            const rsiHigh2 = Math.max(...rsiPrev);

            if (priceHigh1 > priceHigh2 && rsiHigh1 < rsiHigh2) {
                divergences.push({ type: 'bearish_rsi', description: 'RSI顶背离：价格新高但RSI未创新高', severity: 'warning' });
            }

            const priceLow1 = Math.min(...priceRecent);
            const priceLow2 = Math.min(...pricePrev);
            const rsiLow1 = Math.min(...rsiRecent);
            const rsiLow2 = Math.min(...rsiPrev);

            if (priceLow1 < priceLow2 && rsiLow1 > rsiLow2) {
                divergences.push({ type: 'bullish_rsi', description: 'RSI底背离：价格新低但RSI未创新低', severity: 'opportunity' });
            }
        }

        // 检测 MACD 背离
        if (macd.macd.length >= 20) {
            const macdRecent = macd.macd.slice(-10);
            const macdPrev = macd.macd.slice(-20, -10);
            const priceRecent = closes.slice(-10);
            const pricePrev = closes.slice(-20, -10);

            if (Math.max(...priceRecent) > Math.max(...pricePrev) && Math.max(...macdRecent) < Math.max(...macdPrev)) {
                divergences.push({ type: 'bearish_macd', description: 'MACD顶背离', severity: 'warning' });
            }
            if (Math.min(...priceRecent) < Math.min(...pricePrev) && Math.min(...macdRecent) > Math.min(...macdPrev)) {
                divergences.push({ type: 'bullish_macd', description: 'MACD底背离', severity: 'opportunity' });
            }
        }

        return {
            success: true,
            data: {
                code,
                divergences,
                hasDivergence: divergences.length > 0,
                analyzedPeriod: '近20根K线',
            },
        };
    }

    // ===== 多周期分析 =====
    if (action === 'multi_timeframe_analysis' || action === 'multi_timeframe') {
        const periods = [
            { name: '日线', code: '101' },
            { name: '周线', code: '102' },
        ];

        const analysis: any[] = [];
        for (const p of periods) {
            const kRes = await adapterManager.getKline(code, p.code as any, 60);
            if (kRes.success && kRes.data && kRes.data.length > 20) {
                const cls = kRes.data.map((k: any) => k.close);
                const ma20 = TechnicalServices.calculateSMA(cls, 20);
                const current = cls[cls.length - 1];
                const maValue = ma20[ma20.length - 1];
                const trend = current > maValue ? 'up' : 'down';
                analysis.push({
                    period: p.name,
                    trend,
                    ma20: parseFloat(maValue.toFixed(2)),
                    currentPrice: current,
                    priceVsMa: `${((current / maValue - 1) * 100).toFixed(2)}%`,
                });
            }
        }

        const allUp = analysis.every(a => a.trend === 'up');
        const allDown = analysis.every(a => a.trend === 'down');

        return {
            success: true,
            data: {
                code,
                timeframes: analysis,
                consensus: allUp ? '多周期共振看多' : allDown ? '多周期共振看空' : '多周期分歧',
            },
        };
    }

    // ===== 技术面报告 =====
    if (action === 'generate_technical_report' || action === 'technical_report') {
        const ma = TechnicalServices.calculateSMA(closes, 20);
        const macd = TechnicalServices.calculateMACD(closes);
        const rsi = TechnicalServices.calculateRSI(closes, 14);
        const kdj = TechnicalServices.calculateKDJ(highs, lows, closes);
        const patterns = PatternServices.detectAllPatterns(klines).filter((p: any) => p.detected);

        const currentPrice = closes[closes.length - 1];
        const currentMa = ma[ma.length - 1];
        const currentRsi = rsi[rsi.length - 1];
        const currentK = kdj.k[kdj.k.length - 1];

        const signals: string[] = [];
        if (currentPrice > currentMa) signals.push('价格站上MA20');
        if (currentRsi < 30) signals.push('RSI超卖');
        if (currentRsi > 70) signals.push('RSI超买');
        if (macd.macd[macd.macd.length - 1] > macd.signal[macd.signal.length - 1]) signals.push('MACD金叉');
        if (currentK < 20) signals.push('KDJ超卖');
        if (currentK > 80) signals.push('KDJ超买');

        return {
            success: true,
            data: {
                code,
                summary: {
                    trend: currentPrice > currentMa ? '上涨趋势' : '下跌趋势',
                    momentum: currentRsi > 50 ? '偏强' : '偏弱',
                    signals: signals.slice(0, 5), // 最多5个信号
                },
                indicators: {
                    ma20: parseFloat(currentMa.toFixed(2)),
                    rsi14: parseFloat(currentRsi.toFixed(2)),
                    kdjK: parseFloat(currentK.toFixed(2)),
                    macdHistogram: parseFloat(macd.histogram[macd.histogram.length - 1].toFixed(4)),
                },
                patterns: patterns.slice(0, 3).map((p: any) => ({ name: p.nameCN, confidence: p.confidence })),
            },
        };
    }

    return { success: false, error: `Unknown action: ${action}. Supported: calculate_indicators, check_patterns, calculate_support_resistance, detect_divergence, multi_timeframe_analysis, generate_technical_report` };
};
