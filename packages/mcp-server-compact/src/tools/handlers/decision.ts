import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import * as TechnicalServices from '../../services/technical-analysis.js';

export const decisionManagerTool: ToolDefinition = {
    name: 'decision_manager',
    description: '决策辅助管理（买卖建议、时机分析、持仓建议）',
    category: 'decision',
    inputSchema: managerSchema,
    tags: ['decision', 'recommendation', 'analysis'],
    dataSource: 'real',
};

export const decisionManagerHandler: ToolHandler = async (params: any) => {
    const { action, code, buyPrice, holdingDays, investmentStyle = 'balanced' } = params;

    // ===== 买卖建议 =====
    if ((action === 'get_recommendation' || action === 'analyze' || !action) && code) {
        const [quote, kline, fundFlow] = await Promise.all([
            adapterManager.getRealtimeQuote(code),
            adapterManager.getKline(code, '101', 60),
            adapterManager.getFundFlow(code),
        ]);

        if (!quote.success || !quote.data) {
            return { success: false, error: `无法获取 ${code} 的行情数据` };
        }

        const factors: { name: string; signal: string; weight: number; score: number }[] = [];

        // 技术面分析
        if (kline.success && kline.data && kline.data.length > 20) {
            const closes = kline.data.map((k: any) => k.close);
            const ma20 = TechnicalServices.calculateSMA(closes, 20);
            const currentVsMa = closes[closes.length - 1] > ma20[ma20.length - 1];
            factors.push({
                name: '均线趋势',
                signal: currentVsMa ? '看多' : '看空',
                weight: 0.3,
                score: currentVsMa ? 60 : 40,
            });

            const rsi = TechnicalServices.calculateRSI(closes, 14);
            const currentRsi = rsi[rsi.length - 1];
            let rsiSignal = '中性';
            let rsiScore = 50;
            if (currentRsi < 30) { rsiSignal = '超卖'; rsiScore = 70; }
            else if (currentRsi > 70) { rsiSignal = '超买'; rsiScore = 30; }
            factors.push({ name: 'RSI', signal: rsiSignal, weight: 0.2, score: rsiScore });

            // MACD 分析
            const macd = TechnicalServices.calculateMACD(closes);
            const lastMacd = macd.histogram[macd.histogram.length - 1];
            const prevMacd = macd.histogram[macd.histogram.length - 2];
            const macdSignal = lastMacd > 0 && lastMacd > prevMacd ? '多头' : '空头';
            factors.push({
                name: 'MACD',
                signal: macdSignal,
                weight: 0.15,
                score: macdSignal === '多头' ? 65 : 35,
            });
        }

        // 资金面分析
        if (fundFlow.success && fundFlow.data) {
            const mainInflow = fundFlow.data.mainNetInflow || 0;
            factors.push({
                name: '主力资金',
                signal: mainInflow > 0 ? '流入' : '流出',
                weight: 0.25,
                score: mainInflow > 0 ? 65 : 35,
            });
        }

        // 量能分析
        factors.push({
            name: '换手率',
            signal: quote.data.turnoverRate > 5 ? '活跃' : '低迷',
            weight: 0.1,
            score: quote.data.turnoverRate > 5 ? 60 : 40,
        });

        // 计算综合得分
        const totalScore = factors.reduce((sum, f) => sum + f.score * f.weight, 0);
        let recommendation: string;
        let confidence: number;

        if (totalScore >= 65) { recommendation = '建议买入'; confidence = 75; }
        else if (totalScore >= 55) { recommendation = '可以关注'; confidence = 60; }
        else if (totalScore >= 45) { recommendation = '中性观望'; confidence = 50; }
        else { recommendation = '建议回避'; confidence = 65; }

        return {
            success: true,
            data: {
                code,
                name: quote.data.name,
                currentPrice: quote.data.price,
                recommendation,
                score: Math.round(totalScore),
                confidence: `${confidence}%`,
                factors,
                disclaimer: '以上建议仅供参考，不构成投资建议',
            },
        };
    }

    // ===== 时机分析 =====
    if (action === 'get_timing_analysis' || action === 'timing') {
        if (!code) return { success: false, error: '需要股票代码' };

        const [quote, kline] = await Promise.all([
            adapterManager.getRealtimeQuote(code),
            adapterManager.getKline(code, '101', 120),
        ]);

        if (!kline.success || !kline.data || kline.data.length < 60) {
            return { success: false, error: '历史数据不足' };
        }

        const closes = kline.data.map((k: any) => k.close);
        const currentPrice = quote.data?.price || closes[closes.length - 1];

        // 支撑压力位计算
        const recent60 = closes.slice(-60);
        const high60 = Math.max(...recent60);
        const low60 = Math.min(...recent60);
        const range = high60 - low60;

        const support1 = low60;
        const support2 = low60 + range * 0.236;
        const resistance1 = high60 - range * 0.236;
        const resistance2 = high60;

        // 判断当前位置
        let positionInRange: string;
        const pricePosition = (currentPrice - low60) / range;
        if (pricePosition < 0.25) positionInRange = '低位区';
        else if (pricePosition < 0.5) positionInRange = '中低位';
        else if (pricePosition < 0.75) positionInRange = '中高位';
        else positionInRange = '高位区';

        // 买入时机建议
        let buyTiming: string;
        if (pricePosition < 0.3) buyTiming = '较好的买入时机';
        else if (pricePosition < 0.5) buyTiming = '可以分批建仓';
        else if (pricePosition < 0.7) buyTiming = '观望为主';
        else buyTiming = '不宜追高';

        return {
            success: true,
            data: {
                code,
                name: quote.data?.name,
                currentPrice,
                priceRange: {
                    high60: Math.round(high60 * 100) / 100,
                    low60: Math.round(low60 * 100) / 100,
                },
                keyLevels: {
                    support1: Math.round(support1 * 100) / 100,
                    support2: Math.round(support2 * 100) / 100,
                    resistance1: Math.round(resistance1 * 100) / 100,
                    resistance2: Math.round(resistance2 * 100) / 100,
                },
                positionInRange,
                pricePositionPercent: `${(pricePosition * 100).toFixed(1)}%`,
                buyTiming,
            },
        };
    }

    // ===== 持仓决策 =====
    if (action === 'get_holding_decision' || action === 'holding') {
        if (!code) return { success: false, error: '需要股票代码' };

        const [quote, kline] = await Promise.all([
            adapterManager.getRealtimeQuote(code),
            adapterManager.getKline(code, '101', 60),
        ]);

        if (!quote.success || !quote.data) {
            return { success: false, error: '获取行情失败' };
        }

        const currentPrice = quote.data.price;
        const signals: Array<{ type: string; signal: string; action: string }> = [];

        // 盈亏分析
        if (buyPrice) {
            const profitPercent = (currentPrice - buyPrice) / buyPrice;
            if (profitPercent > 0.2) {
                signals.push({ type: '止盈', signal: `盈利${(profitPercent * 100).toFixed(1)}%`, action: '考虑部分止盈' });
            } else if (profitPercent < -0.08) {
                signals.push({ type: '止损', signal: `亏损${(Math.abs(profitPercent) * 100).toFixed(1)}%`, action: '考虑止损' });
            }
        }

        // 技术面信号
        if (kline.success && kline.data && kline.data.length > 20) {
            const closes = kline.data.map((k: any) => k.close);
            const ma5 = TechnicalServices.calculateSMA(closes, 5);
            const ma20 = TechnicalServices.calculateSMA(closes, 20);

            // 均线死叉
            if (ma5[ma5.length - 1] < ma20[ma20.length - 1] && ma5[ma5.length - 2] > ma20[ma20.length - 2]) {
                signals.push({ type: '技术', signal: '均线死叉', action: '减仓信号' });
            }

            // 破位
            const recent5Low = Math.min(...closes.slice(-5));
            if (currentPrice < recent5Low * 0.95) {
                signals.push({ type: '技术', signal: '跌破近5日低点', action: '注意风险' });
            }
        }

        // 综合建议
        let holdingAdvice: string;
        const sellSignals = signals.filter((s: any) => s.action.includes('止') || s.action.includes('减'));
        if (sellSignals.length >= 2) holdingAdvice = '建议减仓';
        else if (sellSignals.length === 1) holdingAdvice = '可以观望，设好止损';
        else holdingAdvice = '继续持有';

        return {
            success: true,
            data: {
                code,
                name: quote.data.name,
                currentPrice,
                buyPrice: buyPrice || null,
                profitLoss: buyPrice ? `${((currentPrice - buyPrice) / buyPrice * 100).toFixed(1)}%` : null,
                signals,
                holdingAdvice,
                disclaimer: '以上建议仅供参考，不构成投资建议',
            },
        };
    }

    // ===== 决策历史 =====
    if (action === 'get_history' || action === 'history') {
        // 这里可以从数据库获取用户历史决策
        return {
            success: true,
            data: {
                message: '决策历史功能',
                features: ['记录买卖决策', '回顾决策效果', '优化决策模型'],
                note: '需要用户授权存储决策记录',
            },
            degraded: true,
        };
    }

    // ===== 决策上下文 =====
    if (action === 'get_context' || action === 'context') {
        if (!code) return { success: false, error: '需要股票代码' };

        // 聚合多维度上下文信息
        const [quote, fundFlow] = await Promise.all([
            adapterManager.getRealtimeQuote(code),
            adapterManager.getFundFlow(code),
        ]);

        return {
            success: true,
            data: {
                code,
                realtime: quote.data,
                fundFlow: fundFlow.data,
                contextSummary: {
                    name: quote.data?.name || '未知',
                    marketCap: quote.data?.marketCap ? `${(quote.data.marketCap / 1e8).toFixed(0)}亿` : '未知',
                    mainForce: (fundFlow.data?.mainNetInflow || 0) > 0 ? '主力流入' : '主力流出',
                },
            },
        };
    }

    if (action === 'list' || action === 'help') {
        return { success: true, data: { actions: ['analyze', 'timing', 'holding', 'history', 'context', 'help'] } };
    }

    return { success: false, error: `未知操作: ${action}。支持: analyze, timing, holding, history, context` };
};
