/**
 * AI上下文感知Hook
 * 自动收集用户当前操作上下文，供AI使用
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import { create } from 'zustand'

// 当前股票信息
export interface CurrentStock {
  code: string
  name: string
  price?: number
  changePercent?: number
  sector?: string
}

// 用户操作记录
export interface UserAction {
  type: 'view_stock' | 'search' | 'add_watchlist' | 'remove_watchlist' | 'click_insight' | 'ask_ai'
  target?: string
  timestamp: Date
  data?: Record<string, any>
}

// AI上下文
export interface AIContext {
  // 当前关注的股票
  currentStock: CurrentStock | null
  // 最近浏览的股票
  recentStocks: CurrentStock[]
  // 当前页面
  currentPage: string
  // 最近操作
  recentActions: UserAction[]
  // 市场状态
  marketStatus: 'pre_open' | 'trading' | 'lunch_break' | 'closed'
  // 当前时间段
  timeOfDay: 'morning' | 'afternoon' | 'evening' | 'night'
  // 会话开始时间
  sessionStartTime: Date
}

// 上下文Store
interface AIContextStore {
  context: AIContext
  setCurrentStock: (stock: CurrentStock | null) => void
  addRecentStock: (stock: CurrentStock) => void
  setCurrentPage: (page: string) => void
  addAction: (action: Omit<UserAction, 'timestamp'>) => void
  updateMarketStatus: () => void
  getContextSummary: () => string
  reset: () => void
}

// 获取市场状态
function getMarketStatus(): 'pre_open' | 'trading' | 'lunch_break' | 'closed' {
  const now = new Date()
  const hour = now.getHours()
  const minute = now.getMinutes()
  const day = now.getDay()
  
  // 周末休市
  if (day === 0 || day === 6) return 'closed'
  
  const time = hour * 100 + minute
  
  if (time < 930) return 'pre_open'
  if (time >= 930 && time < 1130) return 'trading'
  if (time >= 1130 && time < 1300) return 'lunch_break'
  if (time >= 1300 && time < 1500) return 'trading'
  return 'closed'
}

// 获取时间段
function getTimeOfDay(): 'morning' | 'afternoon' | 'evening' | 'night' {
  const hour = new Date().getHours()
  if (hour >= 5 && hour < 12) return 'morning'
  if (hour >= 12 && hour < 18) return 'afternoon'
  if (hour >= 18 && hour < 22) return 'evening'
  return 'night'
}

const defaultContext: AIContext = {
  currentStock: null,
  recentStocks: [],
  currentPage: 'dashboard',
  recentActions: [],
  marketStatus: getMarketStatus(),
  timeOfDay: getTimeOfDay(),
  sessionStartTime: new Date()
}

export const useAIContextStore = create<AIContextStore>((set, get) => ({
  context: defaultContext,
  
  setCurrentStock: (stock) => {
    set(state => ({
      context: {
        ...state.context,
        currentStock: stock
      }
    }))
    
    // 同时添加到最近浏览
    if (stock) {
      get().addRecentStock(stock)
    }
  },
  
  addRecentStock: (stock) => {
    set(state => {
      const existing = state.context.recentStocks.filter(s => s.code !== stock.code)
      return {
        context: {
          ...state.context,
          recentStocks: [stock, ...existing].slice(0, 10) // 保留最近10只
        }
      }
    })
  },
  
  setCurrentPage: (page) => {
    set(state => ({
      context: {
        ...state.context,
        currentPage: page
      }
    }))
    
    // 记录页面浏览操作
    get().addAction({ type: 'view_stock', target: page })
  },
  
  addAction: (action) => {
    set(state => ({
      context: {
        ...state.context,
        recentActions: [
          { ...action, timestamp: new Date() },
          ...state.context.recentActions
        ].slice(0, 20) // 保留最近20个操作
      }
    }))
  },
  
  updateMarketStatus: () => {
    set(state => ({
      context: {
        ...state.context,
        marketStatus: getMarketStatus(),
        timeOfDay: getTimeOfDay()
      }
    }))
  },
  
  getContextSummary: () => {
    const { context } = get()
    const parts: string[] = []
    
    // 当前股票
    if (context.currentStock) {
      parts.push(`当前查看: ${context.currentStock.name}(${context.currentStock.code})`)
      if (context.currentStock.changePercent !== undefined) {
        const sign = context.currentStock.changePercent >= 0 ? '+' : ''
        parts.push(`涨跌幅: ${sign}${context.currentStock.changePercent.toFixed(2)}%`)
      }
    }
    
    // 最近浏览
    if (context.recentStocks.length > 1) {
      const recent = context.recentStocks.slice(1, 4).map(s => s.name).join('、')
      parts.push(`最近浏览: ${recent}`)
    }
    
    // 市场状态
    const statusMap = {
      'pre_open': '盘前',
      'trading': '交易中',
      'lunch_break': '午间休市',
      'closed': '已收盘'
    }
    parts.push(`市场状态: ${statusMap[context.marketStatus]}`)
    
    return parts.join('\n')
  },
  
  reset: () => {
    set({
      context: {
        ...defaultContext,
        sessionStartTime: new Date()
      }
    })
  }
}))

/**
 * AI上下文Hook
 */
export function useAIContext() {
  const store = useAIContextStore()
  
  // 定期更新市场状态
  useEffect(() => {
    const interval = setInterval(() => {
      store.updateMarketStatus()
    }, 60000) // 每分钟更新
    
    return () => clearInterval(interval)
  }, [store])
  
  // 构建AI请求上下文
  const buildRequestContext = useCallback(() => {
    const { context } = store
    return {
      current_stock: context.currentStock ? {
        code: context.currentStock.code,
        name: context.currentStock.name,
        price: context.currentStock.price,
        change_percent: context.currentStock.changePercent
      } : null,
      recent_stocks: context.recentStocks.map(s => s.code),
      current_page: context.currentPage,
      market_status: context.marketStatus,
      time_of_day: context.timeOfDay,
      session_duration_minutes: Math.floor(
        (Date.now() - context.sessionStartTime.getTime()) / 60000
      )
    }
  }, [store])
  
  return {
    ...store,
    buildRequestContext
  }
}

export default useAIContext
