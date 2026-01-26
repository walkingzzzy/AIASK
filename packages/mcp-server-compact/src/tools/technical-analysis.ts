/**
 * 技术分析工具
 * 包含技术指标计算、形态识别等
 */

import { z } from 'zod';
import { ToolDefinition, ToolHandler, ToolRegistryItem } from '../types/tools.js';
import { adapterManager } from '../adapters/index.js';
import * as TechnicalServices from '../services/technical-analysis.js';
import * as PatternServices from '../services/pattern-recognition.js';

// ========== calculate_indicators ==========

const calculateIndicatorsSchema = z.object({
    code: z.string().describe('股票代码'),
    indicators: z.array(z.enum([
        'MA', 'EMA', 'RSI', 'MACD', 'KDJ', 'BOLL', 'ATR', 'OBV', 'CCI', 'WR', 'ROC'
    ])).describe('需要计算的指标列表'),
    period: z.enum(['daily', 'weekly', 'monthly', '1m', '5m', '15m', '30m', '60m']).default('daily').describe('K线周期'),
    limit: z.number().optional().default(100).describe('用于计算的K线数量（会影响RSI等指标的准确性）'),
});

const calculateIndicatorsTool: ToolDefinition = {
    name: 'calculate_technical_indicators',
    description: '计算指定股票的技术指标（MACD, RSI, KDJ等）',
    category: 'technical_analysis',
    inputSchema: calculateIndicatorsSchema,
    tags: ['technical', 'indicators'],
    dataSource: 'real',
};

const calculateIndicatorsHandler: ToolHandler<z.infer<typeof calculateIndicatorsSchema>> = async (params) => {
    // 获取K线数据
    let klinePeriod = params.period === 'daily' ? '101' :
        params.period === 'weekly' ? '102' :
            params.period === 'monthly' ? '103' :
                params.period;

    // 获取足够的K线以保证指标计算准确，尤其是EMA/MACD需要较长历史
    const fetchLimit = Math.max(params.limit, 200);
    const klineRes = await adapterManager.getKlineHistory(params.code, klinePeriod as any, fetchLimit);

    if (!klineRes.success || !klineRes.data || klineRes.data.length === 0) {
        return { success: false, error: klineRes.error || `无法获取 ${params.code} 的K线数据` };
    }
    const klines = klineRes.data;

    const results: Record<string, any> = {};

    const highs = klines.map((k: any) => k.high);
    const lows = klines.map((k: any) => k.low);
    const closes = klines.map((k: any) => k.close);
    const volumes = klines.map((k: any) => k.volume);

    for (const indicator of params.indicators) {
        switch (indicator) {
            case 'MA':
                results['MA'] = TechnicalServices.calculateSMA(closes, 5); // 默认5日
                results['MA_20'] = TechnicalServices.calculateSMA(closes, 20);
                results['MA_60'] = TechnicalServices.calculateSMA(closes, 60);
                break;
            case 'EMA':
                results['EMA_12'] = TechnicalServices.calculateEMA(closes, 12);
                results['EMA_26'] = TechnicalServices.calculateEMA(closes, 26);
                break;
            case 'RSI':
                results['RSI_6'] = TechnicalServices.calculateRSI(closes, 6);
                results['RSI_12'] = TechnicalServices.calculateRSI(closes, 12);
                results['RSI_24'] = TechnicalServices.calculateRSI(closes, 24);
                break;
            case 'MACD':
                results['MACD'] = TechnicalServices.calculateMACD(closes);
                break;
            case 'KDJ':
                results['KDJ'] = TechnicalServices.calculateKDJ(highs, lows, closes);
                break;
            case 'BOLL':
                results['BOLL'] = TechnicalServices.calculateBollingerBands(closes);
                break;
            case 'ATR':
                results['ATR'] = TechnicalServices.calculateATR(highs, lows, closes);
                break;
            case 'OBV':
                results['OBV'] = TechnicalServices.calculateOBV(closes, volumes);
                break;
            case 'CCI':
                results['CCI'] = TechnicalServices.calculateCCI(highs, lows, closes);
                break;
            case 'WR':
                results['WR'] = TechnicalServices.calculateWilliamsR(highs, lows, closes);
                break;
            case 'ROC':
                results['ROC'] = TechnicalServices.calculateROC(closes);
                break;
        }
    }

    return {
        success: true,
        data: {
            code: params.code,
            period: params.period,
            lastDate: klines[klines.length - 1].date,
            indicators: results
        },
        source: 'calculated',
    };
};

// ========== check_candlestick_patterns ==========

const checkPatternsSchema = z.object({
    code: z.string().describe('股票代码'),
    period: z.enum(['daily', 'weekly', '60m']).default('daily').describe('K线周期'),
});

const checkPatternsTool: ToolDefinition = {
    name: 'check_candlestick_patterns',
    description: '检测股票的K线形态（如红三兵、乌云盖顶、早晨之星等）',
    category: 'technical_analysis',
    inputSchema: checkPatternsSchema,
    tags: ['technical', 'patterns'],
    dataSource: 'real',
};

const checkPatternsHandler: ToolHandler<z.infer<typeof checkPatternsSchema>> = async (params) => {
    let klinePeriod = params.period === 'daily' ? '101' :
        params.period === 'weekly' ? '102' :
            params.period;

    const klineRes = await adapterManager.getKlineHistory(params.code, klinePeriod as any, 60);

    if (!klineRes.success || !klineRes.data) {
        return { success: false, error: klineRes.error || `无法获取 ${params.code} 的K线数据` };
    }
    const klines = klineRes.data;

    if (klines.length < 5) {
        return { success: false, error: `K线数据不足` };
    }

    // 检测所有形态
    const patterns = PatternServices.detectAllPatterns(klines);

    // 过滤掉未检测到的
    const detectedPatterns = patterns.filter((p: any) => p.detected);

    return {
        success: true,
        data: {
            code: params.code,
            patterns: detectedPatterns,
        },
        source: 'calculated',
    };
};

// ========== get_available_patterns ==========

const getAvailablePatternsSchema = z.object({});

const getAvailablePatternsTool: ToolDefinition = {
    name: 'get_available_patterns',
    description: '获取支持的K线形态列表及说明',
    category: 'technical_analysis',
    inputSchema: getAvailablePatternsSchema,
    tags: ['technical', 'info'],
    dataSource: 'static', // 静态定义
};

const getAvailablePatternsHandler: ToolHandler<z.infer<typeof getAvailablePatternsSchema>> = async () => {
    return {
        success: true,
        data: PatternServices.getAllPatternDefinitions(),
        source: 'static',
    };
};

// ========== 注册导出 ==========

export const technicalAnalysisTools: ToolRegistryItem[] = [
    { definition: calculateIndicatorsTool, handler: calculateIndicatorsHandler },
    { definition: checkPatternsTool, handler: checkPatternsHandler },
    { definition: getAvailablePatternsTool, handler: getAvailablePatternsHandler },
];
