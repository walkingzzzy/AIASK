/**
 * 交易配置
 * 统一管理交易相关的配置参数
 */

export interface TradingConfig {
    // 交易成本
    commission: number;          // 佣金费率
    slippage: number;           // 滑点
    stampDuty: number;          // 印花税（卖出时）
    minCommission: number;      // 最低佣金
    
    // 风险控制
    maxSinglePosition: number;  // 单只股票最大仓位
    maxSectorWeight: number;    // 单个行业最大权重
    maxDrawdown: number;        // 最大回撤限制
    stopLoss: number;           // 止损比例
    takeProfit: number;         // 止盈比例
    
    // 交易限制
    minTradeAmount: number;     // 最小交易金额
    maxTradeAmount: number;     // 最大交易金额
    minHoldingPeriod: number;   // 最小持仓天数
    
    // 市场规则
    tradingHours: {
        morning: { start: string; end: string };
        afternoon: { start: string; end: string };
    };
    priceLimit: number;         // 涨跌停限制（10%）
    stPriceLimit: number;       // ST股票涨跌停限制（5%）
}

/**
 * 默认交易配置
 */
export const DEFAULT_TRADING_CONFIG: TradingConfig = {
    // 交易成本（A股标准）
    commission: 0.0003,         // 万三佣金
    slippage: 0.001,           // 0.1%滑点
    stampDuty: 0.001,          // 0.1%印花税
    minCommission: 5,          // 5元最低佣金
    
    // 风险控制
    maxSinglePosition: 0.20,   // 单只最大20%
    maxSectorWeight: 0.40,     // 单行业最大40%
    maxDrawdown: 0.20,         // 最大回撤20%
    stopLoss: 0.10,            // 止损10%
    takeProfit: 0.20,          // 止盈20%
    
    // 交易限制
    minTradeAmount: 1000,      // 最小1000元
    maxTradeAmount: 10000000,  // 最大1000万
    minHoldingPeriod: 1,       // 最少持有1天（T+1）
    
    // 市场规则
    tradingHours: {
        morning: { start: '09:30', end: '11:30' },
        afternoon: { start: '13:00', end: '15:00' }
    },
    priceLimit: 0.10,          // 10%涨跌停
    stPriceLimit: 0.05,        // 5% ST涨跌停
};

/**
 * 保守型配置
 */
export const CONSERVATIVE_CONFIG: TradingConfig = {
    ...DEFAULT_TRADING_CONFIG,
    maxSinglePosition: 0.10,   // 单只最大10%
    maxSectorWeight: 0.30,     // 单行业最大30%
    maxDrawdown: 0.10,         // 最大回撤10%
    stopLoss: 0.05,            // 止损5%
    takeProfit: 0.15,          // 止盈15%
};

/**
 * 激进型配置
 */
export const AGGRESSIVE_CONFIG: TradingConfig = {
    ...DEFAULT_TRADING_CONFIG,
    maxSinglePosition: 0.30,   // 单只最大30%
    maxSectorWeight: 0.50,     // 单行业最大50%
    maxDrawdown: 0.30,         // 最大回撤30%
    stopLoss: 0.15,            // 止损15%
    takeProfit: 0.30,          // 止盈30%
};

/**
 * 当前使用的配置
 */
let currentConfig: TradingConfig = DEFAULT_TRADING_CONFIG;

/**
 * 获取当前配置
 */
export function getTradingConfig(): TradingConfig {
    return { ...currentConfig };
}

/**
 * 设置配置
 */
export function setTradingConfig(config: Partial<TradingConfig>): void {
    currentConfig = { ...currentConfig, ...config };
}

/**
 * 重置为默认配置
 */
export function resetTradingConfig(): void {
    currentConfig = { ...DEFAULT_TRADING_CONFIG };
}

/**
 * 使用预设配置
 */
export function useTradingPreset(preset: 'default' | 'conservative' | 'aggressive'): void {
    switch (preset) {
        case 'conservative':
            currentConfig = { ...CONSERVATIVE_CONFIG };
            break;
        case 'aggressive':
            currentConfig = { ...AGGRESSIVE_CONFIG };
            break;
        default:
            currentConfig = { ...DEFAULT_TRADING_CONFIG };
    }
}

/**
 * 计算实际交易成本
 */
export function calculateTradingCost(
    amount: number,
    action: 'buy' | 'sell',
    config: TradingConfig = currentConfig
): {
    commission: number;
    stampDuty: number;
    total: number;
} {
    // 佣金
    let commission = amount * config.commission;
    if (commission < config.minCommission) {
        commission = config.minCommission;
    }
    
    // 印花税（仅卖出时收取）
    const stampDuty = action === 'sell' ? amount * config.stampDuty : 0;
    
    return {
        commission,
        stampDuty,
        total: commission + stampDuty
    };
}

/**
 * 检查是否在交易时间内
 */
export function isInTradingHours(time: Date = new Date(), config: TradingConfig = currentConfig): boolean {
    const hours = time.getHours();
    const minutes = time.getMinutes();
    const timeStr = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
    
    const { morning, afternoon } = config.tradingHours;
    
    return (
        (timeStr >= morning.start && timeStr <= morning.end) ||
        (timeStr >= afternoon.start && timeStr <= afternoon.end)
    );
}

/**
 * 检查价格是否触及涨跌停
 */
export function isPriceLimited(
    currentPrice: number,
    previousClose: number,
    isST: boolean = false,
    config: TradingConfig = currentConfig
): {
    isLimitUp: boolean;
    isLimitDown: boolean;
    limitUpPrice: number;
    limitDownPrice: number;
} {
    const limit = isST ? config.stPriceLimit : config.priceLimit;
    const limitUpPrice = previousClose * (1 + limit);
    const limitDownPrice = previousClose * (1 - limit);
    
    return {
        isLimitUp: currentPrice >= limitUpPrice * 0.999, // 允许0.1%误差
        isLimitDown: currentPrice <= limitDownPrice * 1.001,
        limitUpPrice,
        limitDownPrice
    };
}
