/**
 * AIASK MCP Server Constants
 */

// 股票代码正则表达式
export const STOCK_CODE_REGEX = {
    A_SHARE: /^[036]\d{5}$/,
    MULTI_MARKET: /^(SSE:|SZSE:|NASDAQ:|NYSE:|CRYPTO:)?[A-Z0-9.]+$/,
};

// 支持的技术指标
export const TECHNICAL_INDICATORS = [
    'sma', 'ema', 'wma', 'dema', 'tema', 'kama', 't3',
    'rsi', 'macd', 'kdj', 'cci', 'williamsr', 'roc',
    'boll', 'atr', 'keltner',
    'obv', 'vwap', 'volumeprofile',
] as const;

// K线周期
export const KLINE_PERIODS = ['1m', '5m', '15m', '30m', '60m', 'daily', 'weekly', 'monthly'] as const;

// K线形态
export const CANDLESTICK_PATTERNS = [
    'doji', 'hammer', 'engulfing', 'morningstar', 'eveningstar',
    'threewhitesoldiers', 'threeblackcrows', 'harami', 'piercing',
] as const;

// 工具分类
export const TOOL_CATEGORIES = {
    DISCOVERY: 'discovery',
    SKILLS: 'skills', // Added Skills category
    MARKET_DATA: 'market-data',
    TECHNICAL_ANALYSIS: 'technical-analysis',
    FUNDAMENTAL_ANALYSIS: 'fundamental-analysis',
    MARKET_INSIGHT: 'market-insight',
    SENTIMENT: 'sentiment',
    TRADING_DATA: 'trading-data',
    SECTOR_ROTATION: 'sector-rotation',
    LIMIT_UP: 'limit-up',
    PORTFOLIO: 'portfolio',
    BACKTEST: 'backtest',
    SCREENER: 'screener',
    RESEARCH: 'research',
    WATCHLIST: 'watchlist',
    ALERTS: 'alerts',
    RISK_MONITOR: 'risk-monitor',
    INSIGHT: 'insight',
    DECISION: 'decision',
    VECTOR_SEARCH: 'vector-search',
    COMPREHENSIVE: 'comprehensive',
} as const;

// 缓存 TTL (秒)
export const CACHE_TTL = {
    REALTIME_QUOTE: 5,      // 实时行情：5秒
    KLINE: 1800,            // K线数据：30分钟
    KLINE_INTRADAY: 60,     // 分钟K线：1分钟
    FINANCIAL: 86400,       // 财务数据：24小时
    NEWS: 300,              // 新闻：5分钟
    NORTH_FUND: 1200,       // 北向资金：20分钟
    NORTH_FUND_STALE: 7200, // 北向资金降级缓存：2小时
    SECTOR_FLOW: 600,       // 板块资金：10分钟
    SECTOR_FLOW_STALE: 1800, // 板块资金降级缓存：30分钟
    DRAGON_TIGER: 3600,     // 龙虎榜：1小时
    LIMIT_UP: 60,           // 涨停数据：1分钟
    DEFAULT: 300,
} as const;

// 数据源优先级（业务层仅通过 akshare-mcp 统一访问数据）
export const DATA_SOURCE_PRIORITY = {
    REALTIME: ['akshare'],
    KLINE: ['akshare'],
    FINANCIAL: ['akshare'],
    DRAGON_TIGER: ['akshare'],
    NORTH_FUND: ['akshare'],
    SECTOR_FLOW: ['akshare'],
} as const;

// Tushare API 配置
export const TUSHARE_CONFIG = {
    BASE_URL: process.env.TUSHARE_BASE_URL || 'https://api.tushare.pro',
    TOKEN: process.env.TUSHARE_TOKEN || 'e01ec90ddc36b88b6911be4e702d507540ee7adaaa53a9fd455f056d',
} as const;

// AKShare 服务配置
export const AKSHARE_CONFIG = {
    BASE_URL: process.env.AKSHARE_BASE_URL || 'http://localhost:8080',
    ENABLED: process.env.AKSHARE_ENABLED === 'true',
} as const;

// Baostock 配置
export const BAOSTOCK_CONFIG = {
    ENABLED: process.env.BAOSTOCK_ENABLED === 'true',
    BASE_URL: process.env.BAOSTOCK_BASE_URL || '',
} as const;

// Wind 配置
export const WIND_CONFIG = {
    ENABLED: process.env.WIND_ENABLED === 'true',
    BASE_URL: process.env.WIND_BASE_URL || '',
} as const;

// 数据校验规则
export const DATA_VALIDATION = {
    PRICE_RANGE: { min: 0.01, max: 99999 },
    CHANGE_RANGE: { min: -20, max: 20 },
    ST_CHANGE_RANGE: { min: -5, max: 5 },
    VOLUME_MIN: 0,
    TIMESTAMP_MAX_DELAY: 300000, // 5分钟
    CROSS_SOURCE_PRICE_DIFF: 0.005, // 0.5%
} as const;

// 健康度评分默认权重
export const HEALTH_SCORE_WEIGHTS = {
    profitability: 0.30,
    liquidity: 0.20,
    leverage: 0.20,
    efficiency: 0.15,
    growth: 0.15,
} as const;

// HTTP 状态码
export const HTTP_STATUS = {
    OK: 200,
    BAD_REQUEST: 400,
    NOT_FOUND: 404,
    INTERNAL_ERROR: 500,
} as const;
