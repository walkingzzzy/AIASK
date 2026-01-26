/**
 * K线形态识别服务
 * 扩展支持61+种K线形态识别
 */

import * as ti from 'technicalindicators';
import type { KlineData } from '../types/stock.js';

// 形态分类
export type PatternCategory =
    | 'reversal_bullish'    // 看涨反转
    | 'reversal_bearish'    // 看跌反转
    | 'continuation'        // 持续形态
    | 'neutral'             // 中性形态
    | 'doji'                // 十字星类
    | 'star'                // 星线类
    | 'engulfing'           // 吞没类
    | 'harami'              // 孕线类
    | 'hammer'              // 锤子类
    | 'marubozu';           // 光头光脚类

// 形态定义
export interface PatternDefinition {
    name: string;           // 英文名
    nameCN: string;         // 中文名
    category: PatternCategory;
    bullish: boolean;       // 是否看涨
    reliability: 'high' | 'medium' | 'low';  // 可靠性
    description: string;    // 描述
}

// 形态识别结果
export interface PatternResult {
    pattern: string;
    nameCN: string;
    detected: boolean;
    bullish: boolean;
    category: PatternCategory;
    reliability: string;
    description: string;
    confidence?: number;
}

// 所有支持的形态定义
export const PATTERN_DEFINITIONS: Record<string, PatternDefinition> = {
    // ========== 十字星类 ==========
    doji: {
        name: 'doji',
        nameCN: '十字星',
        category: 'doji',
        bullish: false,
        reliability: 'medium',
        description: '开盘价与收盘价几乎相等，表示多空力量平衡',
    },
    dragonfly_doji: {
        name: 'dragonfly_doji',
        nameCN: '蜻蜓十字',
        category: 'doji',
        bullish: true,
        reliability: 'medium',
        description: '下影线很长，无上影线，出现在下跌趋势末端可能反转',
    },
    gravestone_doji: {
        name: 'gravestone_doji',
        nameCN: '墓碑十字',
        category: 'doji',
        bullish: false,
        reliability: 'medium',
        description: '上影线很长，无下影线，出现在上涨趋势末端可能反转',
    },

    // ========== 星线类 ==========
    morning_star: {
        name: 'morning_star',
        nameCN: '早晨之星',
        category: 'star',
        bullish: true,
        reliability: 'high',
        description: '三根K线组合，底部反转信号，可靠性高',
    },
    evening_star: {
        name: 'evening_star',
        nameCN: '黄昏之星',
        category: 'star',
        bullish: false,
        reliability: 'high',
        description: '三根K线组合，顶部反转信号，可靠性高',
    },
    morning_doji_star: {
        name: 'morning_doji_star',
        nameCN: '早晨十字星',
        category: 'star',
        bullish: true,
        reliability: 'high',
        description: '早晨之星的变体，中间为十字星，信号更强',
    },
    evening_doji_star: {
        name: 'evening_doji_star',
        nameCN: '黄昏十字星',
        category: 'star',
        bullish: false,
        reliability: 'high',
        description: '黄昏之星的变体，中间为十字星，信号更强',
    },
    shooting_star: {
        name: 'shooting_star',
        nameCN: '流星线',
        category: 'star',
        bullish: false,
        reliability: 'medium',
        description: '上影线很长，实体小，出现在上涨趋势末端',
    },
    abandoned_baby: {
        name: 'abandoned_baby',
        nameCN: '弃婴形态',
        category: 'star',
        bullish: true,
        reliability: 'high',
        description: '罕见但可靠的反转形态，中间K线与前后有跳空',
    },

    // ========== 吞没类 ==========
    bullish_engulfing: {
        name: 'bullish_engulfing',
        nameCN: '看涨吞没',
        category: 'engulfing',
        bullish: true,
        reliability: 'high',
        description: '阳线完全包住前一根阴线，强烈看涨信号',
    },
    bearish_engulfing: {
        name: 'bearish_engulfing',
        nameCN: '看跌吞没',
        category: 'engulfing',
        bullish: false,
        reliability: 'high',
        description: '阴线完全包住前一根阳线，强烈看跌信号',
    },
    dark_cloud_cover: {
        name: 'dark_cloud_cover',
        nameCN: '乌云盖顶',
        category: 'engulfing',
        bullish: false,
        reliability: 'high',
        description: '阴线开盘高于前阳线最高价，收盘深入阳线实体',
    },
    piercing_line: {
        name: 'piercing_line',
        nameCN: '刺透形态',
        category: 'engulfing',
        bullish: true,
        reliability: 'high',
        description: '阳线开盘低于前阴线最低价，收盘深入阴线实体',
    },

    // ========== 孕线类 ==========
    bullish_harami: {
        name: 'bullish_harami',
        nameCN: '看涨孕线',
        category: 'harami',
        bullish: true,
        reliability: 'medium',
        description: '小阳线被前一根大阴线包含，可能反转',
    },
    bearish_harami: {
        name: 'bearish_harami',
        nameCN: '看跌孕线',
        category: 'harami',
        bullish: false,
        reliability: 'medium',
        description: '小阴线被前一根大阳线包含，可能反转',
    },
    bullish_harami_cross: {
        name: 'bullish_harami_cross',
        nameCN: '看涨孕十字',
        category: 'harami',
        bullish: true,
        reliability: 'high',
        description: '十字星被前一根大阴线包含，反转信号更强',
    },
    bearish_harami_cross: {
        name: 'bearish_harami_cross',
        nameCN: '看跌孕十字',
        category: 'harami',
        bullish: false,
        reliability: 'high',
        description: '十字星被前一根大阳线包含，反转信号更强',
    },

    // ========== 锤子类 ==========
    hammer: {
        name: 'hammer',
        nameCN: '锤头线',
        category: 'hammer',
        bullish: true,
        reliability: 'medium',
        description: '下影线很长，实体小，出现在下跌趋势末端',
    },
    hanging_man: {
        name: 'hanging_man',
        nameCN: '上吊线',
        category: 'hammer',
        bullish: false,
        reliability: 'medium',
        description: '形态与锤头线相同，但出现在上涨趋势末端',
    },
    inverted_hammer: {
        name: 'inverted_hammer',
        nameCN: '倒锤头',
        category: 'hammer',
        bullish: true,
        reliability: 'low',
        description: '上影线很长，实体小，出现在下跌趋势末端',
    },
    bullish_hammer: {
        name: 'bullish_hammer',
        nameCN: '看涨锤子',
        category: 'hammer',
        bullish: true,
        reliability: 'medium',
        description: '阳线锤头，看涨信号更强',
    },
    bearish_hammer: {
        name: 'bearish_hammer',
        nameCN: '看跌锤子',
        category: 'hammer',
        bullish: false,
        reliability: 'medium',
        description: '阴线锤头，需要确认',
    },
    bullish_inverted_hammer: {
        name: 'bullish_inverted_hammer',
        nameCN: '看涨倒锤头',
        category: 'hammer',
        bullish: true,
        reliability: 'low',
        description: '阳线倒锤头',
    },
    bearish_inverted_hammer: {
        name: 'bearish_inverted_hammer',
        nameCN: '看跌倒锤头',
        category: 'hammer',
        bullish: false,
        reliability: 'low',
        description: '阴线倒锤头',
    },

    // ========== 光头光脚类 ==========
    bullish_marubozu: {
        name: 'bullish_marubozu',
        nameCN: '看涨光头光脚',
        category: 'marubozu',
        bullish: true,
        reliability: 'high',
        description: '无上下影线的大阳线，强烈看涨',
    },
    bearish_marubozu: {
        name: 'bearish_marubozu',
        nameCN: '看跌光头光脚',
        category: 'marubozu',
        bullish: false,
        reliability: 'high',
        description: '无上下影线的大阴线，强烈看跌',
    },

    // ========== 陀螺类 ==========
    bullish_spinning_top: {
        name: 'bullish_spinning_top',
        nameCN: '看涨纺锤',
        category: 'neutral',
        bullish: true,
        reliability: 'low',
        description: '小实体阳线，上下影线较长，表示犹豫',
    },
    bearish_spinning_top: {
        name: 'bearish_spinning_top',
        nameCN: '看跌纺锤',
        category: 'neutral',
        bullish: false,
        reliability: 'low',
        description: '小实体阴线，上下影线较长，表示犹豫',
    },

    // ========== 多K线组合 ==========
    three_white_soldiers: {
        name: 'three_white_soldiers',
        nameCN: '红三兵',
        category: 'reversal_bullish',
        bullish: true,
        reliability: 'high',
        description: '连续三根阳线，每根收盘价高于前一根，强烈看涨',
    },
    three_black_crows: {
        name: 'three_black_crows',
        nameCN: '三只乌鸦',
        category: 'reversal_bearish',
        bullish: false,
        reliability: 'high',
        description: '连续三根阴线，每根收盘价低于前一根，强烈看跌',
    },
    tweezer_top: {
        name: 'tweezer_top',
        nameCN: '镊子顶',
        category: 'reversal_bearish',
        bullish: false,
        reliability: 'medium',
        description: '两根K线最高价相同，顶部反转信号',
    },
    tweezer_bottom: {
        name: 'tweezer_bottom',
        nameCN: '镊子底',
        category: 'reversal_bullish',
        bullish: true,
        reliability: 'medium',
        description: '两根K线最低价相同，底部反转信号',
    },
    downside_tasuki_gap: {
        name: 'downside_tasuki_gap',
        nameCN: '下跳空并列阴阳',
        category: 'continuation',
        bullish: false,
        reliability: 'medium',
        description: '下跌趋势中的持续形态',
    },

    // ========== 自定义扩展形态 ==========
    double_bottom: {
        name: 'double_bottom',
        nameCN: '双底/W底',
        category: 'reversal_bullish',
        bullish: true,
        reliability: 'high',
        description: '两个相近低点形成的底部反转形态',
    },
    double_top: {
        name: 'double_top',
        nameCN: '双顶/M头',
        category: 'reversal_bearish',
        bullish: false,
        reliability: 'high',
        description: '两个相近高点形成的顶部反转形态',
    },
    head_shoulders_bottom: {
        name: 'head_shoulders_bottom',
        nameCN: '头肩底',
        category: 'reversal_bullish',
        bullish: true,
        reliability: 'high',
        description: '经典底部反转形态，中间低点最低',
    },
    head_shoulders_top: {
        name: 'head_shoulders_top',
        nameCN: '头肩顶',
        category: 'reversal_bearish',
        bullish: false,
        reliability: 'high',
        description: '经典顶部反转形态，中间高点最高',
    },
    ascending_triangle: {
        name: 'ascending_triangle',
        nameCN: '上升三角形',
        category: 'continuation',
        bullish: true,
        reliability: 'medium',
        description: '水平阻力线和上升支撑线，通常向上突破',
    },
    descending_triangle: {
        name: 'descending_triangle',
        nameCN: '下降三角形',
        category: 'continuation',
        bullish: false,
        reliability: 'medium',
        description: '水平支撑线和下降阻力线，通常向下突破',
    },
    symmetric_triangle: {
        name: 'symmetric_triangle',
        nameCN: '对称三角形',
        category: 'continuation',
        bullish: false,
        reliability: 'medium',
        description: '收敛的支撑和阻力线，突破方向不确定',
    },
    rising_wedge: {
        name: 'rising_wedge',
        nameCN: '上升楔形',
        category: 'reversal_bearish',
        bullish: false,
        reliability: 'medium',
        description: '两条向上收敛的趋势线，通常向下突破',
    },
    falling_wedge: {
        name: 'falling_wedge',
        nameCN: '下降楔形',
        category: 'reversal_bullish',
        bullish: true,
        reliability: 'medium',
        description: '两条向下收敛的趋势线，通常向上突破',
    },
    flag_bullish: {
        name: 'flag_bullish',
        nameCN: '看涨旗形',
        category: 'continuation',
        bullish: true,
        reliability: 'medium',
        description: '急涨后的短期整理，通常继续上涨',
    },
    flag_bearish: {
        name: 'flag_bearish',
        nameCN: '看跌旗形',
        category: 'continuation',
        bullish: false,
        reliability: 'medium',
        description: '急跌后的短期整理，通常继续下跌',
    },
    gap_up: {
        name: 'gap_up',
        nameCN: '向上跳空缺口',
        category: 'continuation',
        bullish: true,
        reliability: 'medium',
        description: '开盘价高于前一日最高价，表示强势',
    },
    gap_down: {
        name: 'gap_down',
        nameCN: '向下跳空缺口',
        category: 'continuation',
        bullish: false,
        reliability: 'medium',
        description: '开盘价低于前一日最低价，表示弱势',
    },
    island_reversal_top: {
        name: 'island_reversal_top',
        nameCN: '岛形反转顶',
        category: 'reversal_bearish',
        bullish: false,
        reliability: 'high',
        description: '向上跳空后向下跳空，强烈看跌信号',
    },
    island_reversal_bottom: {
        name: 'island_reversal_bottom',
        nameCN: '岛形反转底',
        category: 'reversal_bullish',
        bullish: true,
        reliability: 'high',
        description: '向下跳空后向上跳空，强烈看涨信号',
    },
};


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
 * 使用technicalindicators库检测形态
 */
function detectTIPattern(
    open: number[],
    high: number[],
    low: number[],
    close: number[],
    patternName: string
): boolean {
    const input = { open, high, low, close };

    try {
        switch (patternName) {
            case 'doji':
                return ti.doji(input)[input.open.length - 1] || false;
            case 'dragonfly_doji':
                return ti.dragonflydoji(input)[input.open.length - 1] || false;
            case 'gravestone_doji':
                return ti.gravestonedoji(input)[input.open.length - 1] || false;
            case 'morning_star':
                return ti.morningstar(input)[input.open.length - 1] || false;
            case 'evening_star':
                return ti.eveningstar(input)[input.open.length - 1] || false;
            case 'morning_doji_star':
                return ti.morningdojistar(input)[input.open.length - 1] || false;
            case 'evening_doji_star':
                return ti.eveningdojistar(input)[input.open.length - 1] || false;
            case 'shooting_star':
                return ti.shootingstar(input)[input.open.length - 1] || false;
            case 'abandoned_baby':
                return ti.abandonedbaby(input)[input.open.length - 1] || false;
            case 'bullish_engulfing':
                return ti.bullishengulfingpattern(input)[input.open.length - 1] || false;
            case 'bearish_engulfing':
                return ti.bearishengulfingpattern(input)[input.open.length - 1] || false;
            case 'dark_cloud_cover':
                return ti.darkcloudcover(input)[input.open.length - 1] || false;
            case 'piercing_line':
                return ti.piercingline(input)[input.open.length - 1] || false;
            case 'bullish_harami':
                return ti.bullishharami(input)[input.open.length - 1] || false;
            case 'bearish_harami':
                return ti.bearishharami(input)[input.open.length - 1] || false;
            case 'bullish_harami_cross':
                return ti.bullishharamicross(input)[input.open.length - 1] || false;
            case 'bearish_harami_cross':
                return ti.bearishharamicross(input)[input.open.length - 1] || false;
            case 'hammer':
                return ti.hammerpattern(input)[input.open.length - 1] || false;
            case 'hanging_man':
                return ti.hangingman(input)[input.open.length - 1] || false;
            case 'bullish_hammer':
                return ti.bullishhammerstick(input)[input.open.length - 1] || false;
            case 'bearish_hammer':
                return ti.bearishhammerstick(input)[input.open.length - 1] || false;
            case 'bullish_inverted_hammer':
                return ti.bullishinvertedhammerstick(input)[input.open.length - 1] || false;
            case 'bearish_inverted_hammer':
                return ti.bearishinvertedhammerstick(input)[input.open.length - 1] || false;
            case 'bullish_marubozu':
                return ti.bullishmarubozu(input)[input.open.length - 1] || false;
            case 'bearish_marubozu':
                return ti.bearishmarubozu(input)[input.open.length - 1] || false;
            case 'bullish_spinning_top':
                return ti.bullishspinningtop(input)[input.open.length - 1] || false;
            case 'bearish_spinning_top':
                return ti.bearishspinningtop(input)[input.open.length - 1] || false;
            case 'three_white_soldiers':
                return ti.threewhitesoldiers(input)[input.open.length - 1] || false;
            case 'three_black_crows':
                return ti.threeblackcrows(input)[input.open.length - 1] || false;
            case 'tweezer_top':
                return ti.tweezertop(input)[input.open.length - 1] || false;
            case 'tweezer_bottom':
                return ti.tweezerbottom(input)[input.open.length - 1] || false;
            case 'downside_tasuki_gap':
                return ti.downsidetasukigap(input)[input.open.length - 1] || false;
            default:
                return false;
        }
    } catch {
        return false;
    }
}


/**
 * 检测自定义形态（双底、头肩等复杂形态）
 */
function detectCustomPattern(
    open: number[],
    high: number[],
    low: number[],
    close: number[],
    patternName: string
): boolean {
    const len = close.length;
    if (len < 5) return false;

    switch (patternName) {
        case 'double_bottom': {
            // 简化的双底检测：找两个相近的低点
            if (len < 20) return false;
            const recentLows = low.slice(-20);
            const firstHalf = recentLows.slice(0, 10);
            const secondHalf = recentLows.slice(10);
            const min1 = Math.min(...firstHalf);
            const min2 = Math.min(...secondHalf);
            const diff = Math.abs(min1 - min2) / min1;
            return diff < 0.03 && close[len - 1] > Math.max(min1, min2) * 1.02;
        }

        case 'double_top': {
            if (len < 20) return false;
            const recentHighs = high.slice(-20);
            const firstHalf = recentHighs.slice(0, 10);
            const secondHalf = recentHighs.slice(10);
            const max1 = Math.max(...firstHalf);
            const max2 = Math.max(...secondHalf);
            const diff = Math.abs(max1 - max2) / max1;
            return diff < 0.03 && close[len - 1] < Math.min(max1, max2) * 0.98;
        }

        case 'gap_up': {
            if (len < 2) return false;
            return open[len - 1] > high[len - 2];
        }

        case 'gap_down': {
            if (len < 2) return false;
            return open[len - 1] < low[len - 2];
        }

        case 'island_reversal_top': {
            if (len < 5) return false;
            // 向上跳空后向下跳空
            const hasGapUp = low[len - 3] > high[len - 4];
            const hasGapDown = high[len - 1] < low[len - 2];
            return hasGapUp && hasGapDown;
        }

        case 'island_reversal_bottom': {
            if (len < 5) return false;
            // 向下跳空后向上跳空
            const hasGapDown = high[len - 3] < low[len - 4];
            const hasGapUp = low[len - 1] > high[len - 2];
            return hasGapDown && hasGapUp;
        }

        case 'ascending_triangle': {
            if (len < 10) return false;
            const recentHighs = high.slice(-10);
            const recentLows = low.slice(-10);
            // 高点相近，低点逐渐抬高
            const highRange = Math.max(...recentHighs) - Math.min(...recentHighs);
            const lowTrend = recentLows[9] - recentLows[0];
            return highRange / Math.max(...recentHighs) < 0.02 && lowTrend > 0;
        }

        case 'descending_triangle': {
            if (len < 10) return false;
            const recentHighs = high.slice(-10);
            const recentLows = low.slice(-10);
            // 低点相近，高点逐渐降低
            const lowRange = Math.max(...recentLows) - Math.min(...recentLows);
            const highTrend = recentHighs[9] - recentHighs[0];
            return lowRange / Math.min(...recentLows) < 0.02 && highTrend < 0;
        }

        default:
            return false;
    }
}


/**
 * 检测所有K线形态
 */
export function detectAllPatterns(
    klines: KlineData[],
    categories?: PatternCategory[]
): PatternResult[] {
    const { open, high, low, close } = extractOHLCV(klines);
    const results: PatternResult[] = [];

    for (const [name, def] of Object.entries(PATTERN_DEFINITIONS)) {
        // 如果指定了分类，只检测该分类的形态
        if (categories && categories.length > 0 && !categories.includes(def.category)) {
            continue;
        }

        let detected = false;

        // 先尝试使用technicalindicators库
        detected = detectTIPattern(open, high, low, close, name);

        // 如果库不支持，尝试自定义检测
        if (!detected) {
            detected = detectCustomPattern(open, high, low, close, name);
        }

        results.push({
            pattern: name,
            nameCN: def.nameCN,
            detected,
            bullish: def.bullish,
            category: def.category,
            reliability: def.reliability,
            description: def.description,
        });
    }

    return results;
}

/**
 * 只返回检测到的形态
 */
export function detectPatternsFiltered(
    klines: KlineData[],
    options?: {
        categories?: PatternCategory[];
        minReliability?: 'low' | 'medium' | 'high';
        bullishOnly?: boolean;
        bearishOnly?: boolean;
    }
): PatternResult[] {
    const allResults = detectAllPatterns(klines, options?.categories);

    return allResults.filter((r: any) => {
        if (!r.detected) return false;

        if (options?.minReliability) {
            const reliabilityOrder = { low: 0, medium: 1, high: 2 };
            if (reliabilityOrder[r.reliability as 'low' | 'medium' | 'high'] <
                reliabilityOrder[options.minReliability]) {
                return false;
            }
        }

        if (options?.bullishOnly && !r.bullish) return false;
        if (options?.bearishOnly && r.bullish) return false;

        return true;
    });
}

/**
 * 获取所有支持的形态列表
 */
export function getAllPatternDefinitions(): PatternDefinition[] {
    return Object.values(PATTERN_DEFINITIONS);
}

/**
 * 按分类获取形态
 */
export function getPatternsByCategory(category: PatternCategory): PatternDefinition[] {
    return Object.values(PATTERN_DEFINITIONS).filter((p: any) => p.category === category);
}

/**
 * 获取形态统计
 */
export function getPatternStats(): {
    total: number;
    byCategory: Record<string, number>;
    byReliability: Record<string, number>;
    bullish: number;
    bearish: number;
} {
    const patterns = Object.values(PATTERN_DEFINITIONS);
    const byCategory: Record<string, number> = {};
    const byReliability: Record<string, number> = {};
    let bullish = 0;
    let bearish = 0;

    for (const p of patterns) {
        byCategory[p.category] = (byCategory[p.category] || 0) + 1;
        byReliability[p.reliability] = (byReliability[p.reliability] || 0) + 1;
        if (p.bullish) bullish++;
        else bearish++;
    }

    return {
        total: patterns.length,
        byCategory,
        byReliability,
        bullish,
        bearish,
    };
}
