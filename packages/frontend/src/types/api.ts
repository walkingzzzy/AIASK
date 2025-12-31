/**
 * API 响应类型定义
 */

// 通用 API 响应
export interface ApiResponse<T = unknown> {
  success: boolean
  data?: T
  message?: string
  error?: string
}

// 股票行情
export interface StockQuote {
  stock_code: string
  stock_name: string
  current_price: number
  change: number
  change_percent: number
  volume: number
  amount: number
  high: number
  low: number
  open: number
  pre_close: number
  timestamp: number
}

// K线数据
export interface KLineDataItem {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount?: number
}

// AI评分
export interface AIScoreData {
  stock_code: string
  stock_name: string
  score: number
  rating: string
  factors: AIScoreFactor[]
  updated_at: string
}

export interface AIScoreFactor {
  name: string
  score: number
  weight: number
  description: string
}

// 洞察数据
export interface InsightData {
  type: 'opportunity' | 'risk' | 'insight'
  title: string
  content: string
  stock_code?: string
  stock_name?: string
  priority: 'high' | 'medium' | 'low'
  timestamp: number
}

// 早报数据
export interface MorningBriefData {
  greeting: string
  market_summary: string
  watchlist_highlights: string[]
  opportunities: InsightData[]
  risks: InsightData[]
}

// AI聊天响应
export interface AIChatResponse {
  response: string
  ai_name: string
  context?: Record<string, unknown>
}

// 用户画像
export interface UserProfileResponse {
  user_id: string
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
  usage_stats?: {
    total_queries: number
    total_sessions: number
    consecutive_days: number
    longest_streak: number
    first_active_date?: string
    last_active_date?: string
    active_hours: number[]
  }
  ai_relationship?: {
    trust_level: number
    suggestion_follow_rate: number
    total_suggestions: number
    followed_suggestions: number
    feedback_count: number
    positive_feedback: number
  }
}
