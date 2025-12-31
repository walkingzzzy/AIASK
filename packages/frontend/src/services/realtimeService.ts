/**
 * 实时数据服务
 * 统一管理WebSocket连接和实时数据推送
 */
import { create } from 'zustand'

// 实时行情数据
export interface RealtimeQuote {
  stockCode: string
  stockName: string
  price: number
  change: number
  changePercent: number
  volume: number
  amount: number
  high: number
  low: number
  open: number
  preClose: number
  timestamp: number
}

// 盘口数据
export interface OrderBookData {
  stockCode: string
  asks: Array<{ price: number; volume: number }>  // 卖盘
  bids: Array<{ price: number; volume: number }>  // 买盘
  timestamp: number
}

// 成交明细
export interface TradeDetail {
  stockCode: string
  price: number
  volume: number
  amount: number
  direction: 'buy' | 'sell' | 'neutral'
  time: string
}

// AI推送消息
export interface AIPushMessage {
  type: 'opportunity' | 'risk' | 'insight' | 'alert'
  title: string
  content: string
  stockCode?: string
  stockName?: string
  priority: 'high' | 'medium' | 'low'
  timestamp: number
}

// WebSocket消息类型
type WSMessageType = 
  | 'quote'
  | 'orderbook'
  | 'trade'
  | 'ai_push'
  | 'subscribed'
  | 'unsubscribed'
  | 'pong'
  | 'error'

interface WSMessage {
  type: WSMessageType
  stock_code?: string
  data?: any
}

// 实时数据Store
interface RealtimeDataStore {
  // 连接状态
  isConnected: boolean
  reconnectAttempts: number
  
  // 数据缓存
  quotes: Map<string, RealtimeQuote>
  orderBooks: Map<string, OrderBookData>
  trades: Map<string, TradeDetail[]>
  aiMessages: AIPushMessage[]
  
  // 订阅列表
  subscriptions: Set<string>
  
  // 操作方法
  setConnected: (connected: boolean) => void
  updateQuote: (quote: RealtimeQuote) => void
  updateOrderBook: (orderBook: OrderBookData) => void
  addTrade: (trade: TradeDetail) => void
  addAIMessage: (message: AIPushMessage) => void
  clearAIMessages: () => void
  addSubscription: (stockCode: string) => void
  removeSubscription: (stockCode: string) => void
  getQuote: (stockCode: string) => RealtimeQuote | undefined
  getOrderBook: (stockCode: string) => OrderBookData | undefined
  getTrades: (stockCode: string) => TradeDetail[]
}

export const useRealtimeDataStore = create<RealtimeDataStore>((set, get) => ({
  isConnected: false,
  reconnectAttempts: 0,
  quotes: new Map(),
  orderBooks: new Map(),
  trades: new Map(),
  aiMessages: [],
  subscriptions: new Set(),
  
  setConnected: (connected) => set({ isConnected: connected }),
  
  updateQuote: (quote) => set(state => {
    const newQuotes = new Map(state.quotes)
    newQuotes.set(quote.stockCode, quote)
    return { quotes: newQuotes }
  }),
  
  updateOrderBook: (orderBook) => set(state => {
    const newOrderBooks = new Map(state.orderBooks)
    newOrderBooks.set(orderBook.stockCode, orderBook)
    return { orderBooks: newOrderBooks }
  }),
  
  addTrade: (trade) => set(state => {
    const newTrades = new Map(state.trades)
    const existing = newTrades.get(trade.stockCode) || []
    newTrades.set(trade.stockCode, [trade, ...existing].slice(0, 100)) // 保留最近100条
    return { trades: newTrades }
  }),
  
  addAIMessage: (message) => set(state => ({
    aiMessages: [message, ...state.aiMessages].slice(0, 50) // 保留最近50条
  })),
  
  clearAIMessages: () => set({ aiMessages: [] }),
  
  addSubscription: (stockCode) => set(state => {
    const newSubs = new Set(state.subscriptions)
    newSubs.add(stockCode)
    return { subscriptions: newSubs }
  }),
  
  removeSubscription: (stockCode) => set(state => {
    const newSubs = new Set(state.subscriptions)
    newSubs.delete(stockCode)
    return { subscriptions: newSubs }
  }),
  
  getQuote: (stockCode) => get().quotes.get(stockCode),
  getOrderBook: (stockCode) => get().orderBooks.get(stockCode),
  getTrades: (stockCode) => get().trades.get(stockCode) || []
}))

/**
 * 实时数据服务类
 */
class RealtimeService {
  private ws: WebSocket | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null
  private maxReconnectAttempts = 5
  private reconnectAttempts = 0
  private baseReconnectInterval = 3000
  private heartbeatInterval = 30000
  private url = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000/ws/realtime'
  
  private messageHandlers: Map<WSMessageType, ((data: any) => void)[]> = new Map()
  
  /**
   * 计算指数退避延迟
   */
  private getReconnectDelay(): number {
    return Math.min(this.baseReconnectInterval * Math.pow(1.5, this.reconnectAttempts), 30000)
  }
  
  /**
   * 连接WebSocket
   */
  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      console.log('WebSocket already connected')
      return
    }
    
    try {
      this.ws = new WebSocket(this.url)
      
      this.ws.onopen = () => {
        console.log('WebSocket connected')
        this.reconnectAttempts = 0
        useRealtimeDataStore.getState().setConnected(true)
        useRealtimeDataStore.setState({ reconnectAttempts: 0 })
        this.startHeartbeat()
        
        // 重新订阅之前的股票（批量）
        const subscriptions = useRealtimeDataStore.getState().subscriptions
        if (subscriptions.size > 0) {
          this.subscribeBatch(Array.from(subscriptions))
        }
      }
      
      this.ws.onmessage = (event) => {
        try {
          const message: WSMessage = JSON.parse(event.data)
          this.handleMessage(message)
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
        }
      }
      
      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }
      
      this.ws.onclose = (event) => {
        console.log('WebSocket disconnected:', event.code, event.reason)
        useRealtimeDataStore.getState().setConnected(false)
        this.stopHeartbeat()
        
        // 非正常关闭时自动重连
        if (event.code !== 1000) {
          this.scheduleReconnect()
        }
      }
    } catch (error) {
      console.error('Failed to create WebSocket:', error)
      this.scheduleReconnect()
    }
  }
  
  /**
   * 断开连接
   */
  disconnect(): void {
    this.stopHeartbeat()
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    useRealtimeDataStore.getState().setConnected(false)
  }
  
  /**
   * 订阅股票
   */
  subscribe(stockCode: string): void {
    useRealtimeDataStore.getState().addSubscription(stockCode)
    this.send({ action: 'subscribe', stock_code: stockCode })
  }
  
  /**
   * 批量订阅股票
   */
  subscribeBatch(stockCodes: string[]): void {
    stockCodes.forEach(code => {
      useRealtimeDataStore.getState().addSubscription(code)
    })
    this.send({ action: 'subscribe_batch', stock_codes: stockCodes })
  }
  
  /**
   * 取消订阅
   */
  unsubscribe(stockCode: string): void {
    useRealtimeDataStore.getState().removeSubscription(stockCode)
    this.send({ action: 'unsubscribe', stock_code: stockCode })
  }
  
  /**
   * 取消所有订阅
   */
  unsubscribeAll(): void {
    useRealtimeDataStore.setState({ subscriptions: new Set() })
    this.send({ action: 'unsubscribe_all' })
  }
  
  /**
   * 发送消息
   */
  send(message: any): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    } else {
      console.warn('WebSocket is not connected')
    }
  }
  
  /**
   * 注册消息处理器
   */
  on(type: WSMessageType, handler: (data: any) => void): () => void {
    const handlers = this.messageHandlers.get(type) || []
    handlers.push(handler)
    this.messageHandlers.set(type, handlers)
    
    // 返回取消注册函数
    return () => {
      const handlers = this.messageHandlers.get(type) || []
      const index = handlers.indexOf(handler)
      if (index > -1) {
        handlers.splice(index, 1)
      }
    }
  }
  
  /**
   * 处理消息
   */
  private handleMessage(message: WSMessage): void {
    const store = useRealtimeDataStore.getState()
    
    switch (message.type) {
      case 'quote':
        if (message.data) {
          store.updateQuote(this.parseQuote(message.data))
        }
        break
        
      case 'orderbook':
        if (message.data) {
          store.updateOrderBook(this.parseOrderBook(message.data))
        }
        break
        
      case 'trade':
        if (message.data) {
          store.addTrade(this.parseTrade(message.data))
        }
        break
        
      case 'ai_push':
        if (message.data) {
          store.addAIMessage(this.parseAIMessage(message.data))
        }
        break
        
      case 'subscribed':
        console.log(`Subscribed to ${message.stock_code}`)
        break
        
      case 'unsubscribed':
        console.log(`Unsubscribed from ${message.stock_code}`)
        break
        
      case 'pong':
        // 心跳响应
        break
        
      case 'error':
        console.error('WebSocket error:', message.data)
        break
    }
    
    // 调用注册的处理器
    const handlers = this.messageHandlers.get(message.type) || []
    handlers.forEach(handler => handler(message.data))
  }
  
  /**
   * 解析行情数据
   */
  private parseQuote(data: any): RealtimeQuote {
    return {
      stockCode: data.stock_code || data.stockCode,
      stockName: data.stock_name || data.stockName || '',
      price: data.price || data.current || 0,
      change: data.change || 0,
      changePercent: data.change_percent || data.changePercent || 0,
      volume: data.volume || 0,
      amount: data.amount || 0,
      high: data.high || 0,
      low: data.low || 0,
      open: data.open || 0,
      preClose: data.pre_close || data.preClose || 0,
      timestamp: data.timestamp || Date.now()
    }
  }
  
  /**
   * 解析盘口数据
   */
  private parseOrderBook(data: any): OrderBookData {
    return {
      stockCode: data.stock_code || data.stockCode,
      asks: (data.asks || []).map((a: any) => ({
        price: a.price || a[0],
        volume: a.volume || a[1]
      })),
      bids: (data.bids || []).map((b: any) => ({
        price: b.price || b[0],
        volume: b.volume || b[1]
      })),
      timestamp: data.timestamp || Date.now()
    }
  }
  
  /**
   * 解析成交明细
   */
  private parseTrade(data: any): TradeDetail {
    return {
      stockCode: data.stock_code || data.stockCode,
      price: data.price || 0,
      volume: data.volume || 0,
      amount: data.amount || 0,
      direction: data.direction || 'neutral',
      time: data.time || new Date().toLocaleTimeString()
    }
  }
  
  /**
   * 解析AI推送消息
   */
  private parseAIMessage(data: any): AIPushMessage {
    return {
      type: data.type || 'alert',
      title: data.title || '',
      content: data.content || '',
      stockCode: data.stock_code || data.stockCode,
      stockName: data.stock_name || data.stockName,
      priority: data.priority || 'medium',
      timestamp: data.timestamp || Date.now()
    }
  }
  
  /**
   * 开始心跳
   */
  private startHeartbeat(): void {
    this.stopHeartbeat()
    this.heartbeatTimer = setInterval(() => {
      this.send({ action: 'ping' })
    }, this.heartbeatInterval)
  }
  
  /**
   * 停止心跳
   */
  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }
  
  /**
   * 计划重连
   */
  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('Max reconnect attempts reached')
      return
    }
    
    const delay = this.getReconnectDelay()
    this.reconnectAttempts++
    
    this.reconnectTimer = setTimeout(() => {
      console.log(`Reconnecting... Attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts}`)
      useRealtimeDataStore.setState({ reconnectAttempts: this.reconnectAttempts })
      this.connect()
    }, delay)
  }
}

// 导出单例
export const realtimeService = new RealtimeService()

export default realtimeService
