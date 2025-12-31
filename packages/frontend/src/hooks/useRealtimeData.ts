/**
 * 实时数据Hook
 * 提供便捷的实时数据订阅和获取
 */
import { useEffect, useCallback, useMemo } from 'react'
import { 
  realtimeService, 
  useRealtimeDataStore,
  RealtimeQuote,
  OrderBookData,
  TradeDetail,
  AIPushMessage
} from '@/services/realtimeService'

interface UseRealtimeDataOptions {
  autoConnect?: boolean
  stockCodes?: string[]
}

/**
 * 实时数据主Hook
 */
export function useRealtimeData(options: UseRealtimeDataOptions = {}) {
  const { autoConnect = true, stockCodes = [] } = options
  
  const isConnected = useRealtimeDataStore(state => state.isConnected)
  const quotes = useRealtimeDataStore(state => state.quotes)
  const aiMessages = useRealtimeDataStore(state => state.aiMessages)
  
  // 自动连接
  useEffect(() => {
    if (autoConnect) {
      realtimeService.connect()
    }
    
    return () => {
      // 组件卸载时不断开连接，保持全局连接
    }
  }, [autoConnect])
  
  // 稳定的股票代码依赖
  const stockCodesKey = useMemo(() => JSON.stringify(stockCodes.slice().sort()), [stockCodes])
  
  // 订阅股票
  useEffect(() => {
    stockCodes.forEach(code => {
      realtimeService.subscribe(code)
    })
    
    return () => {
      stockCodes.forEach(code => {
        realtimeService.unsubscribe(code)
      })
    }
  }, [stockCodesKey, stockCodes])
  
  const subscribe = useCallback((stockCode: string) => {
    realtimeService.subscribe(stockCode)
  }, [])
  
  const unsubscribe = useCallback((stockCode: string) => {
    realtimeService.unsubscribe(stockCode)
  }, [])
  
  const connect = useCallback(() => {
    realtimeService.connect()
  }, [])
  
  const disconnect = useCallback(() => {
    realtimeService.disconnect()
  }, [])
  
  return {
    isConnected,
    quotes: Array.from(quotes.values()),
    aiMessages,
    subscribe,
    unsubscribe,
    connect,
    disconnect
  }
}

/**
 * 单只股票实时行情Hook
 */
export function useStockQuote(stockCode: string): RealtimeQuote | undefined {
  const quote = useRealtimeDataStore(state => state.quotes.get(stockCode))
  
  useEffect(() => {
    if (stockCode) {
      realtimeService.subscribe(stockCode)
    }
    
    return () => {
      if (stockCode) {
        realtimeService.unsubscribe(stockCode)
      }
    }
  }, [stockCode])
  
  return quote
}

/**
 * 盘口数据Hook
 */
export function useOrderBook(stockCode: string): OrderBookData | undefined {
  const orderBook = useRealtimeDataStore(state => state.orderBooks.get(stockCode))
  
  useEffect(() => {
    if (stockCode) {
      realtimeService.subscribe(stockCode)
    }
    
    return () => {
      if (stockCode) {
        realtimeService.unsubscribe(stockCode)
      }
    }
  }, [stockCode])
  
  return orderBook
}

/**
 * 成交明细Hook
 */
export function useTrades(stockCode: string): TradeDetail[] {
  const trades = useRealtimeDataStore(state => state.trades.get(stockCode) || [])
  
  useEffect(() => {
    if (stockCode) {
      realtimeService.subscribe(stockCode)
    }
    
    return () => {
      if (stockCode) {
        realtimeService.unsubscribe(stockCode)
      }
    }
  }, [stockCode])
  
  return trades
}

/**
 * AI推送消息Hook
 */
export function useAIMessages(): {
  messages: AIPushMessage[]
  clearMessages: () => void
} {
  const messages = useRealtimeDataStore(state => state.aiMessages)
  const clearMessages = useRealtimeDataStore(state => state.clearAIMessages)
  
  return { messages, clearMessages }
}

/**
 * 多只股票实时行情Hook
 */
export function useMultiStockQuotes(stockCodes: string[]): Map<string, RealtimeQuote> {
  const quotes = useRealtimeDataStore(state => {
    const result = new Map<string, RealtimeQuote>()
    stockCodes.forEach(code => {
      const quote = state.quotes.get(code)
      if (quote) {
        result.set(code, quote)
      }
    })
    return result
  })
  
  const stockCodesKey = useMemo(() => JSON.stringify(stockCodes.slice().sort()), [stockCodes])
  
  useEffect(() => {
    stockCodes.forEach(code => {
      realtimeService.subscribe(code)
    })
    
    return () => {
      stockCodes.forEach(code => {
        realtimeService.unsubscribe(code)
      })
    }
  }, [stockCodesKey, stockCodes])
  
  return quotes
}

export default useRealtimeData
