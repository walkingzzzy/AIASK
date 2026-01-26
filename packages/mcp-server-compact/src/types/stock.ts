/**
 * 股票相关类型定义
 */

import type { TECHNICAL_INDICATORS, KLINE_PERIODS, CANDLESTICK_PATTERNS } from '../config/constants.js';

// 股票代码
export type StockCode = string;

// 技术指标类型
export type TechnicalIndicator = typeof TECHNICAL_INDICATORS[number];

// K线周期
export type KlinePeriod = typeof KLINE_PERIODS[number] | '101' | '102' | '103';

// K线形态
export type CandlestickPattern = typeof CANDLESTICK_PATTERNS[number];

/**
 * 实时行情数据
 */
export interface RealtimeQuote {
    code: StockCode;
    name: string;
    price: number;
    change: number;
    changePercent: number;
    open: number;
    high: number;
    low: number;
    preClose: number;
    volume: number;
    amount: number;
    turnoverRate: number;
    timestamp: number;
    // 估值数据（可选）
    pe?: number;
    pb?: number;
    marketCap?: number;
    floatMarketCap?: number;
}

/**
 * K线数据
 */
export interface KlineData {
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    amount?: number;
}

/**
 * 五档盘口
 */
export interface OrderBook {
    code: StockCode;
    bids: Array<{ price: number; volume: number }>;
    asks: Array<{ price: number; volume: number }>;
    timestamp: number;
}

/**
 * 成交明细
 */
export interface TradeRecord {
    time: string;
    price: number;
    volume: number;
    direction: 'buy' | 'sell' | 'neutral';
}

/**
 * 股票基本信息
 */
export interface StockInfo {
    code: StockCode;
    name: string;
    market: 'SSE' | 'SZSE';
    industry: string;
    sector: string;
    listDate: string;
    totalShares: number;
    floatShares: number;
    marketCap: number;
    floatMarketCap: number;
}

/**
 * 财务数据
 */
export interface FinancialData {
    code: StockCode;
    reportDate: string;
    revenue: number;
    netProfit: number;
    grossProfitMargin: number;
    netProfitMargin: number;
    roe: number;
    roa: number;
    debtRatio: number;
    currentRatio: number;
    eps: number;
    bvps: number;
    // 扩展字段
    assetTurnover?: number;
    leverage?: number;
    revenueGrowth?: number;
    netProfitGrowth?: number;
}

/**
 * 估值指标
 */
export interface ValuationMetrics {
    code: StockCode;
    pe: number;
    peTTM: number;
    pb: number;
    ps: number;
    pcf: number;
    dividendYield: number;
    marketCap: number;
}

/**
 * 估值数据 (别名 ValuationMetrics)
 */
export type ValuationData = ValuationMetrics;

/**
 * 健康度评分
 */
export interface HealthScore {
    code: StockCode;
    totalScore: number;
    dimensions: {
        profitability: number;
        liquidity: number;
        leverage: number;
        efficiency: number;
        growth: number;
    };
    level: 'excellent' | 'good' | 'fair' | 'poor' | 'critical';
}

/**
 * 技术指标结果
 */
export interface IndicatorResult {
    indicator: TechnicalIndicator;
    values: number[];
    signal?: 'buy' | 'sell' | 'hold';
    strength?: number;
}

/**
 * 支撑压力位
 */
export interface SupportResistance {
    code: StockCode;
    supports: number[];
    resistances: number[];
    currentPrice: number;
}

/**
 * 交易信号
 */
export interface TradingSignal {
    code: StockCode;
    signal: 'strong_buy' | 'buy' | 'hold' | 'sell' | 'strong_sell';
    confidence: number;
    reasons: string[];
    indicators: IndicatorResult[];
}

/**
 * 龙虎榜数据
 */
export interface DragonTiger {
    code: StockCode;
    name: string;
    date: string;
    reason: string;
    buyAmount: number;
    sellAmount: number;
    netAmount: number;
    buyers: Array<{
        name: string;
        buyAmount: number;
        sellAmount: number;
    }>;
    sellers: Array<{
        name: string;
        buyAmount: number;
        sellAmount: number;
    }>;
}

/**
 * 北向资金数据
 */
export interface NorthFund {
    date: string;
    shConnect: number;
    szConnect: number;
    total: number;
    cumulative: number;
}

/**
 * 板块数据
 */
export interface SectorData {
    code: string;
    name: string;
    change: number;
    changePercent: number;
    leadingStock: string;
    amount: number;
    netInflow: number;
}

/**
 * 持仓
 */
export interface Position {
    code: StockCode;
    name: string;
    quantity: number;
    costPrice: number;
    currentPrice: number;
    marketValue: number;
    profit: number;
    profitPercent: number;
    createdAt: string;
    updatedAt: string;
}

/**
 * 自选股
 */
export interface WatchlistItem {
    code: StockCode;
    name: string;
    groupId: string;
    tags: string[];
    notes?: string;
    addedAt: string;
}

/**
 * 价格提醒
 */
export interface PriceAlert {
    id: string;
    code: StockCode;
    name: string;
    condition: 'above' | 'below' | 'change_above' | 'change_below';
    targetPrice: number;
    currentPrice?: number;
    triggered: boolean;
    triggeredAt?: string;
    createdAt: string;
}

/**
 * 成交明细 (新增)
 */
export interface TradeDetail {
    time: string;
    price: number;
    volume: number;
    amount: number;
    direction: 'buy' | 'sell' | 'neutral';
}

/**
 * 涨停股票数据
 */
export interface LimitUpStock {
    code: StockCode;
    name: string;
    price: number;
    changePercent: number;
    limitUpPrice: number;
    firstLimitTime: string;
    lastLimitTime: string;
    openTimes: number;
    continuousDays: number;
    turnoverRate: number;
    marketCap: number;
    industry: string;
    concept: string;
}

/**
 * 涨停统计数据
 */
export interface LimitUpStatistics {
    date: string;
    totalLimitUp: number;
    firstBoard: number;
    secondBoard: number;
    thirdBoard: number;
    higherBoard: number;
    failedBoard: number;
    limitDown: number;
    successRate: number;
}

/**
 * 两融数据
 */
export interface MarginData {
    date: string;
    code: string;
    name: string;
    marginBalance: number;
    marginBuy: number;
    marginRepay: number;
    shortBalance: number;
    shortSell: number;
    shortRepay: number;
    totalBalance: number;
}

/**
 * 大宗交易数据
 */
export interface BlockTrade {
    date: string;
    code: string;
    name: string;
    price: number;
    volume: number;
    amount: number;
    premium: number;
    buyer: string;
    seller: string;
}

/**
 * 回测结果
 */
export interface BacktestResult {
    id: string;
    strategy: string;
    params: Record<string, unknown>;
    stocks: string[];
    startDate: string;
    endDate: string;
    initialCapital: number;
    finalCapital: number;
    totalReturn: number;
    maxDrawdown: number;
    sharpeRatio: number;
    tradesCount: number;
    winRate?: number;
    profitFactor?: number;
    trades?: BacktestTrade[];
    equityCurve?: Array<{ date: string; value: number }>;
    createdAt?: string;
}

/**
 * 回测交易记录
 */
export interface BacktestTrade {
    date: string;
    code: string;
    action: 'buy' | 'sell';
    price: number;
    quantity: number;
    amount: number;
    profit?: number;
    profitPercent?: number;
}

/**
 * 个股资金流向
 */
export interface FundFlow {
    code: StockCode;
    // 主力
    mainNetInflow: number;
    mainInflow?: number;
    mainOutflow?: number;
    mainInflowPercent?: number; // 新增: 主力净流入占比
    // 散户
    retailNetInflow?: number;
    retailInflow?: number;
    retailOutflow?: number;
    // 细分资金净流入
    superLargeNetInflow?: number; // 超大单
    largeNetInflow?: number;      // 大单
    middleNetInflow?: number;     // 中单
    smallNetInflow?: number;      // 小单
    // 细分资金流入流出 (可选)
    superLargeInflow?: number;
    superLargeOutflow?: number;
    largeInflow?: number;
    largeOutflow?: number;
    middleInflow?: number;
    middleOutflow?: number;
    smallInflow?: number;
    smallOutflow?: number;
}
