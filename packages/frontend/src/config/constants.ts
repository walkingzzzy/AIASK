/**
 * 应用常量配置
 */

// API 配置
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'
export const WS_URL = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000/ws/realtime'

// 时间间隔 (毫秒)
export const INTERVALS = {
  HEARTBEAT: 30000,
  MARKET_STATUS_UPDATE: 60000,
  USER_PROFILE_SYNC: 5 * 60 * 1000,
  NOTIFICATION_CHECK: 5 * 60 * 1000,
  QUOTE_REFRESH: 3000,
} as const

// 重连配置
export const RECONNECT = {
  MAX_ATTEMPTS: 10,
  BASE_INTERVAL: 3000,
  MAX_INTERVAL: 30000,
} as const

// 缓存限制
export const CACHE_LIMITS = {
  RECENT_STOCKS: 10,
  RECENT_ACTIONS: 20,
  AI_MESSAGES: 50,
  TRADE_DETAILS: 100,
  NOTIFICATIONS: 50,
} as const

// 股票代码正则
export const STOCK_CODE_REGEX = /^[036]\d{5}$/

// 验证股票代码格式
export function isValidStockCode(code: string): boolean {
  return STOCK_CODE_REGEX.test(code)
}
