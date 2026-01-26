/**
 * 股票数据存储层 - 统一导出
 * 
 * 此文件作为向后兼容的统一入口，重新导出所有子模块的功能
 * 新代码建议直接从子模块导入
 */

// 数据库连接
export {
    initDatabase,
    closeDatabase,
} from './db-connection.js';

// 股票基础信息
export {
    type StockInfo,
    getStockInfo,
    searchStocks,
    getStocksBySector,
    getSectorList,
    getAllStockCodes,
    upsertStock,
    batchUpsertStocks,
} from './stock-info.js';

// 财务数据
export {
    type FinancialData,
    getLatestFinancialData,
    getFinancialHistory,
    getStocksNeedingFinancialUpdate,
    upsertFinancialData,
    batchUpsertFinancialData,
} from './financial-data.js';

// 估值数据
export {
    type ValuationData,
    getValuationData,
    getBatchValuationData,
    getStocksNeedingUpdate,
    upsertQuote,
    batchUpsertQuotes,
} from './valuation-data.js';

// K线数据
export {
    type DailyBar,
    getDailyBars,
    getDailyBarsByDateRange,
    getStocksNeedingKlineUpdate,
    markKlineSyncAttempted,
    upsertDailyBar,
    batchUpsertDailyBars,
} from './kline-data.js';

// 选股筛选
export {
    type ScreeningCriteria,
    type ScreeningResult,
    screenStocks,
} from './screener-data.js';

// 同步状态
export {
    type SyncStatus,
    type DatabaseStats,
    getSyncStatus,
    getDatabaseStats,
} from './sync-status.js';
