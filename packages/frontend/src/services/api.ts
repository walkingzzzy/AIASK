import axios from 'axios'

// 从环境变量获取API地址，默认为本地开发地址
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'

const instance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ==================== 请求节流工具 ====================

/**
 * 节流函数 - 限制函数执行频率
 */
function throttle<T extends (...args: any[]) => any>(
  func: T,
  limit: number
): (...args: Parameters<T>) => ReturnType<T> | undefined {
  let inThrottle = false
  let lastResult: ReturnType<T> | undefined
  
  return function(this: any, ...args: Parameters<T>): ReturnType<T> | undefined {
    if (!inThrottle) {
      lastResult = func.apply(this, args)
      inThrottle = true
      setTimeout(() => (inThrottle = false), limit)
      return lastResult
    }
    return lastResult
  }
}

/**
 * 请求队列 - 用于批量请求的排队处理
 */
class RequestQueue {
  private queue: Map<string, {
    resolve: (value: any) => void
    reject: (reason: any) => void
  }[]> = new Map()
  private timer: ReturnType<typeof setTimeout> | null = null
  private batchDelay = 200 // 批量请求延迟 (ms) - 增加到200ms以便更好地批量合并
  private batchHandler: ((codes: string[]) => Promise<any>) | null = null
  
  setBatchHandler(handler: (codes: string[]) => Promise<any>) {
    this.batchHandler = handler
  }
  
  add(code: string): Promise<any> {
    return new Promise((resolve, reject) => {
      if (!this.queue.has(code)) {
        this.queue.set(code, [])
      }
      this.queue.get(code)!.push({ resolve, reject })
      
      // 启动批量处理定时器
      if (!this.timer) {
        this.timer = setTimeout(() => this.flush(), this.batchDelay)
      }
    })
  }
  
  private async flush() {
    this.timer = null
    const codes = Array.from(this.queue.keys())
    const handlers = new Map(this.queue)
    this.queue.clear()
    
    if (codes.length === 0 || !this.batchHandler) return
    
    try {
      const result = await this.batchHandler(codes)
      
      // 分发结果给等待的请求
      for (const [code, callbacks] of handlers) {
        const data = result.data?.[code]
        if (data) {
          callbacks.forEach(cb => cb.resolve({ success: true, data }))
        } else {
          const error = result.errors?.find((e: any) => e.code === code)
          callbacks.forEach(cb => cb.resolve({
            success: false,
            error: error?.error || '无法获取行情数据'
          }))
        }
      }
    } catch (error) {
      // 批量请求失败，所有等待的请求都失败
      for (const [, callbacks] of handlers) {
        callbacks.forEach(cb => cb.reject(error))
      }
    }
  }
}

// 行情请求队列实例
const quoteQueue = new RequestQueue()

// 响应拦截器
instance.interceptors.response.use(
  (response) => response.data,
  (error) => {
    // 处理 429 错误
    if (error.response?.status === 429) {
      const retryAfter = error.response.headers['retry-after'] || 60
      console.warn(`请求被限流，${retryAfter}秒后重试`)
      // 可以在这里实现自动重试逻辑
    }
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

// 内部批量查询函数（供请求队列使用）
const _batchGetQuotes = (stockCodes: string[]) =>
  instance.post('/stock/quotes/batch', stockCodes)

// 初始化请求队列的批量处理器
quoteQueue.setBatchHandler(_batchGetQuotes)

export const api = {
  // 健康检查
  healthCheck: () => instance.get('/health'),

  // 股票数据
  // 单个行情查询（会自动合并为批量请求）
  getStockQuote: (stockCode: string) => quoteQueue.add(stockCode),
  
  // 直接单个查询（绕过请求合并，用于需要立即响应的场景）
  getStockQuoteDirect: (stockCode: string) => instance.get(`/stock/quote/${stockCode}`),
  
  // 批量行情查询（推荐用于多只股票）
  getBatchStockQuotes: (stockCodes: string[]) => instance.post('/stock/quotes/batch', stockCodes),
  
  getStockKline: (stockCode: string, period = 'daily', limit = 100) =>
    instance.get(`/stock/kline/${stockCode}`, { params: { period, limit } }),

  // K线数据（用于图表）
  getKLineData: (stockCode: string, period: string) =>
    instance.get(`/stock/kline/${stockCode}`, { params: { period, limit: 500 } }),

  // 技术指标数据
  getIndicatorData: (stockCode: string, indicatorType: string, period: string) =>
    instance.get(`/stock/indicator/${stockCode}`, { params: { indicator: indicatorType, period } }),


  // AI评分
  getAIScore: (stockCode: string, stockName = '') =>
    instance.post('/ai-score', { stock_code: stockCode, stock_name: stockName }),
  getBatchAIScore: (stockCodes: string[]) =>
    instance.post('/ai-score/batch', { stock_codes: stockCodes }),

  // NLP查询
  query: (queryText: string) => instance.post('/query', { query: queryText }),

  // 情绪分析
  getStockSentiment: (stockCode: string, stockName = '') =>
    instance.post('/sentiment/stock', { stock_code: stockCode, stock_name: stockName }),
  getMarketSentiment: () => instance.get('/sentiment/market'),

  // 涨停分析
  getDailyLimitUp: () => instance.get('/limit-up/daily'),
  getLimitUpStatistics: () => instance.get('/limit-up/statistics'),
  predictContinuation: (stockCode: string, stockName = '') =>
    instance.post('/limit-up/predict', { stock_code: stockCode, stock_name: stockName }),

  // 融资融券
  getMarketMargin: () => instance.get('/margin/market'),
  getStockMargin: (stockCode: string, stockName = '') =>
    instance.post('/margin/stock', { stock_code: stockCode, stock_name: stockName }),

  // 大宗交易
  getDailyBlockTrade: () => instance.get('/block-trade/daily'),
  getStockBlockTrade: (stockCode: string, stockName = '') =>
    instance.post('/block-trade/stock', { stock_code: stockCode, stock_name: stockName }),

  // 估值分析
  getValuation: (stockCode: string) => instance.get(`/valuation/${stockCode}`),
  getDCFValuation: (stockCode: string) => instance.get(`/valuation/${stockCode}/dcf`),
  getCompareValuation: (stockCode: string) => instance.get(`/valuation/${stockCode}/compare`),
  getIndustryAvgValuation: (industry: string) => instance.get(`/valuation/industry/${industry}/average`),

  // 龙虎榜
  getDragonTiger: (date?: string, type: string = 'all') =>
    instance.get('/dragon-tiger', { params: { date, type } }),

  // 集合竞价
  getCallAuctionRanking: (topN: number = 50) =>
    instance.get('/call-auction/ranking', { params: { top_n: topN } }),
  getCallAuctionStock: (stockCode: string) =>
    instance.get(`/call-auction/stock/${stockCode}`),

  // 组合管理
  getPortfolioPositions: () => instance.get('/portfolio/positions'),
  getPortfolioSummary: () => instance.get('/portfolio/summary'),
  getPortfolioRisk: () => instance.get('/portfolio/risk'),
  addPosition: (data: { stock_code: string; stock_name: string; quantity: number; cost_price: number }) =>
    instance.post('/portfolio/add', data),
  removePosition: (stockCode: string) => instance.delete(`/portfolio/remove/${stockCode}`),

  // 风险监控
  checkRisk: () => instance.get('/risk-monitor/check'),
  getRiskMetrics: () => instance.get('/risk-monitor/metrics'),
  getRiskThresholds: () => instance.get('/risk-monitor/thresholds'),
  updateRiskThreshold: (thresholdName: string, newValue: number) =>
    instance.post('/risk-monitor/thresholds', { threshold_name: thresholdName, new_value: newValue }),

  // 研报中心
  getResearchSummary: () => instance.get('/research/summary'),
  getStockResearch: (stockCode: string, limit: number = 10) =>
    instance.get(`/research/stock/${stockCode}`, { params: { limit } }),
  searchResearch: (params: { keyword?: string; stock_code?: string; institution?: string; limit?: number }) =>
    instance.post('/research/search', params),
  getRecentResearch: (days: number = 7, limit: number = 20) =>
    instance.get('/research/recent', { params: { days, limit } }),

  // 数据中心
  getDataCategories: () => instance.get('/data-center/categories'),
  getDataStatistics: () => instance.get('/data-center/statistics'),
  getCategoryFields: (category: string) => instance.get(`/data-center/fields/${category}`),
  queryData: (params: any) => instance.post('/data-center/query', params),
  exportData: (params: any) => instance.post('/data-center/export', params),

  // 选股雷达
  screenStocks: (params: { strategy_name?: string; custom_conditions?: any[]; limit?: number }) =>
    instance.post('/screener/screen', params),
  getScreeningStrategies: () => instance.get('/screener/strategies'),

  // RAG检索
  ragQuery: (query: string) => instance.post('/rag/query', { query }),

  // 盘口数据（五档买卖盘）
  getOrderBook: (stockCode: string) => instance.get(`/stock/orderbook/${stockCode}`),
  
  // 成交明细
  getTradeDetail: (stockCode: string, limit = 50) => 
    instance.get(`/stock/trades/${stockCode}`, { params: { limit } }),

  // ==================== 回测系统 ====================
  
  // 运行回测
  runBacktest: (params: BacktestParams) =>
    instance.post('/backtest/run', params),
  
  // 分层回测
  runStratifiedBacktest: (holdingDays = 20) =>
    instance.post('/backtest/stratified', null, { params: { holding_days: holdingDays } }),
  
  // 优化阈值
  optimizeThresholds: (params: { strategy?: string; holding_days?: number }) =>
    instance.post('/backtest/optimize', params),
  
  // 滚动验证
  runRollingValidation: (trainWindow = 252, testWindow = 63, step = 21) =>
    instance.post('/backtest/rolling', null, { params: { train_window: trainWindow, test_window: testWindow, step } }),
  
  // 获取可用策略
  getBacktestStrategies: () =>
    instance.get('/backtest/strategies'),
  
  // 获取回测历史
  getBacktestHistory: (limit = 10) =>
    instance.get('/backtest/history', { params: { limit } }),

  // ==================== 研报分析增强 ====================
  
  // AI分析研报
  analyzeReport: (reportId: string, analysisType = 'summary') =>
    instance.post('/research/analyze', { report_id: reportId, analysis_type: analysisType }),
  
  // 获取机构列表
  getResearchInstitutions: () =>
    instance.get('/research/institutions'),
  
  // 获取评级趋势
  getRatingTrend: (stockCode: string, months = 6) =>
    instance.get('/research/ratings/trend', { params: { stock_code: stockCode, months } }),

  // ==================== 洞察引擎 ====================
  
  // 获取投资机会
  getOpportunities: (profile: UserProfile) =>
    instance.post('/insight/opportunities', profile),
  
  // 获取单只股票的投资机会
  getStockOpportunities: (stockCode: string, stockName = '') =>
    instance.get(`/insight/opportunities/${stockCode}`, { params: { stock_name: stockName } }),
  
  // 获取风险预警
  getRisks: (profile: UserProfile) =>
    instance.post('/insight/risks', profile),
  
  // 获取单只股票的风险预警
  getStockRisks: (stockCode: string, stockName = '', isHolding = false) =>
    instance.get(`/insight/risks/${stockCode}`, { params: { stock_name: stockName, is_holding: isHolding } }),
  
  // 获取每日AI洞察
  getDailyInsights: (profile: UserProfile) =>
    instance.post('/insight/daily', profile),
  
  // 获取单只股票的AI洞察
  getStockInsights: (stockCode: string, stockName = '') =>
    instance.get(`/insight/stock/${stockCode}`, { params: { stock_name: stockName } }),
  
  // 获取洞察摘要（综合接口）
  getInsightSummary: (profile: UserProfile) =>
    instance.post('/insight/summary', profile),

  // ==================== 用户画像 ====================
  
  // 获取用户画像
  getUserProfile: (userId = 'default') =>
    instance.get('/user/profile', { params: { user_id: userId } }),
  
  // 更新用户画像
  updateUserProfile: (updates: Partial<UserProfileData>, userId = 'default') =>
    instance.put('/user/profile', updates, { params: { user_id: userId } }),
  
  // 获取用户偏好
  getUserPreferences: (userId = 'default') =>
    instance.get('/user/profile/preferences', { params: { user_id: userId } }),
  
  // 追踪行为
  trackBehavior: (event: BehaviorEventData, userId = 'default') =>
    instance.post('/user/behavior', event, { params: { user_id: userId } }),
  
  // 追踪查询
  trackQuery: (data: { query: string; intent: string; stock_codes?: string[]; success?: boolean }, userId = 'default') =>
    instance.post('/user/behavior/query', data, { params: { user_id: userId } }),
  
  // 追踪决策
  trackDecision: (data: { stock_code: string; stock_name: string; action: string; reason: string; price: number; ai_suggested?: boolean }, userId = 'default') =>
    instance.post('/user/behavior/decision', data, { params: { user_id: userId } }),
  
  // 追踪反馈
  trackFeedback: (data: { feedback_type: string; is_positive: boolean; context?: any }, userId = 'default') =>
    instance.post('/user/behavior/feedback', data, { params: { user_id: userId } }),
  
  // 获取行为摘要
  getBehaviorSummary: (userId = 'default', days = 7) =>
    instance.get('/user/behavior/summary', { params: { user_id: userId, days } }),
  
  // 触发偏好学习
  triggerLearning: (userId = 'default') =>
    instance.post('/user/learn', null, { params: { user_id: userId } }),
  
  // 获取学习洞察
  getLearningInsights: (userId = 'default') =>
    instance.get('/user/learning-insights', { params: { user_id: userId } }),
  
  // 获取个性化推荐
  getRecommendations: (userId = 'default', limit = 10) =>
    instance.get('/user/recommendations', { params: { user_id: userId, limit } }),
  
  // 获取个性化早报
  getMorningBrief: (userId = 'default') =>
    instance.get('/user/morning-brief', { params: { user_id: userId } }),
  
  // 更新自选股（同步到用户画像）
  syncWatchlist: (watchlist: string[], userId = 'default') =>
    instance.put('/user/watchlist', { watchlist }, { params: { user_id: userId } }),
  
  // 更新持仓（同步到用户画像）
  syncHoldings: (holdings: string[], userId = 'default') =>
    instance.put('/user/holdings', { holdings }, { params: { user_id: userId } }),
  
  // 获取使用统计
  getUsageStats: (userId = 'default') =>
    instance.get('/user/stats', { params: { user_id: userId } }),
  
  // 获取连续使用数据
  getStreak: (userId = 'default') =>
    instance.get('/user/streak', { params: { user_id: userId } }),

  // ==================== AI人格与对话 ====================
  
  // 获取个性化问候语
  getAIGreeting: (userId = 'default') =>
    instance.get('/ai/greeting', { params: { user_id: userId } }),
  
  // 获取AI人格配置
  getAICharacter: () =>
    instance.get('/ai/character'),
  
  // 增强AI响应
  enhanceResponse: (response: string, context: Record<string, any> = {}, userId = 'default') =>
    instance.post('/ai/enhance', { response, context }, { params: { user_id: userId } }),
  
  // 获取情绪响应
  getEmotionResponse: (context: EmotionContextData, userId = 'default') =>
    instance.post('/ai/emotion', context, { params: { user_id: userId } }),
  
  // 获取安慰消息
  getComfortMessage: (lossPercent: number, stockName?: string) =>
    instance.get('/ai/comfort', { params: { loss_percent: lossPercent, stock_name: stockName } }),
  
  // 获取鼓励消息
  getEncouragementMessage: (achievement: string, days?: number, count?: number, improvement?: number) =>
    instance.get('/ai/encouragement', { params: { achievement, days, count, improvement } }),
  
  // 获取警示消息
  getWarningMessage: (warningType: string) =>
    instance.get('/ai/warning', { params: { warning_type: warningType } }),
  
  // 获取记忆叙述
  getMemoryNarrative: (narrativeType = 'summary', userId = 'default') =>
    instance.get('/ai/memory', { params: { user_id: userId, narrative_type: narrativeType } }),
  
  // 普通对话
  aiChat: (message: string, context: Record<string, any> = {}, userId = 'default') =>
    instance.post('/ai/chat', { message, context, stream: false }, { params: { user_id: userId } }),
  
  // 流式对话（返回URL，需要使用EventSource）
  getAIChatStreamUrl: (userId = 'default') =>
    `${API_BASE_URL}/ai/chat/stream?user_id=${userId}`,
  
  // 获取AI服务状态
  getAIStatus: () => instance.get('/ai/status'),

  // ==================== 决策追踪 ====================
  
  // 记录决策
  recordDecision: (data: DecisionCreateData, userId = 'default') =>
    instance.post('/decision/record', data, { params: { user_id: userId } }),
  
  // 获取决策列表
  getDecisions: (days = 30, limit = 50, userId = 'default') =>
    instance.get('/decision/list', { params: { user_id: userId, days, limit } }),
  
  // 获取决策统计
  getDecisionStats: (days = 30, userId = 'default') =>
    instance.get('/decision/stats', { params: { user_id: userId, days } }),
  
  // 更新决策价格
  updateDecisionPrice: (decisionId: string, currentPrice: number, userId = 'default') =>
    instance.put(`/decision/${decisionId}/update`, null, { params: { user_id: userId, current_price: currentPrice } }),
  
  // 删除决策
  deleteDecision: (decisionId: string, userId = 'default') =>
    instance.delete(`/decision/${decisionId}`, { params: { user_id: userId } }),
  
  // 获取AI建议历史
  getAISuggestions: (days = 30, userId = 'default') =>
    instance.get('/decision/ai-suggestions', { params: { user_id: userId, days } }),
}

// 用户画像类型
export interface UserProfile {
  user_id?: string
  watchlist?: string[]
  holdings?: string[]
  investment_style?: 'conservative' | 'balanced' | 'aggressive'
  risk_tolerance?: number
  focus_sectors?: string[]
}

// 完整用户画像数据类型
export interface UserProfileData {
  investment_style?: string
  risk_tolerance?: number
  focus_sectors?: string[]
  avoided_sectors?: string[]
  preferred_market_cap?: string
  knowledge_level?: string
  decision_speed?: string
  analysis_depth?: string
  preferred_data_types?: string[]
  nickname?: string
  ai_personality?: string
  notification_enabled?: boolean
  morning_brief_enabled?: boolean
}

// 行为事件数据类型
export interface BehaviorEventData {
  event_type: string
  data?: Record<string, any>
  stock_code?: string
  stock_name?: string
  page?: string
  session_id?: string
}

// 情绪上下文数据类型
export interface EmotionContextData {
  market_change?: number
  user_profit?: number
  consecutive_days?: number
  win_streak?: number
  loss_streak?: number
  concepts_learned?: number
  days_since_last_visit?: number
  stock_name?: string
  stock_code?: string
}

// AI人格配置类型
export interface AICharacter {
  name: string
  avatar: string
  traits: string[]
}

// AI对话响应类型
export interface AIChatResponse {
  response: string
  ai_name: string
}

// AI服务状态类型
export interface AIServiceStatus {
  overall_status: string
  llm: LLMStatus
  embedding: EmbeddingStatus
  recommendations: string[]
}

export interface LLMStatus {
  is_configured: boolean
  model: string | null
  base_url: string | null
  status: string
  message: string
}

export interface EmbeddingStatus {
  is_configured: boolean
  using_mock?: boolean
  status: string
  message: string
}

// 决策创建数据类型
export interface DecisionCreateData {
  stock_code: string
  stock_name: string
  action: 'buy' | 'sell' | 'hold'
  reason: string
  price: number
  ai_suggested?: boolean
  ai_confidence?: number
}

// 决策记录类型
export interface DecisionRecord {
  id: string
  user_id: string
  stock_code: string
  stock_name: string
  action: 'buy' | 'sell' | 'hold'
  reason: string
  price_at_decision: number
  current_price?: number
  profit_percent?: number
  is_correct?: boolean
  ai_suggested: boolean
  ai_confidence?: number
  timestamp: string
}

// 回测参数类型
export interface BacktestParams {
  strategy?: string
  stock_codes?: string[]
  start_date?: string
  end_date?: string
  initial_capital?: number
  holding_days?: number
  buy_threshold?: number
  sell_threshold?: number
}

// 回测结果类型
export interface BacktestResult {
  strategy_name: string
  start_date: string
  end_date: string
  initial_capital: number
  final_capital: number
  metrics: BacktestMetrics
  equity_curve: EquityPoint[]
  trades: TradeRecord[]
  drawdown_periods: DrawdownPeriod[]
}

export interface BacktestMetrics {
  total_return: number
  annual_return: number
  sharpe_ratio: number
  max_drawdown: number
  max_drawdown_duration: number
  volatility: number
  win_rate: number
  profit_factor: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  avg_profit: number
  avg_loss: number
  max_profit: number
  max_loss: number
}

export interface EquityPoint {
  date: string
  equity: number
  benchmark: number
  daily_return: number
}

export interface TradeRecord {
  id: number
  date: string
  stock_code: string
  stock_name: string
  action: string
  price: number
  quantity: number
  amount: number
  pnl?: number
  pnl_percent?: number
}

export interface DrawdownPeriod {
  start_date: string
  end_date: string
  drawdown: number
  duration: number
  recovery_days: number
}

export default api
