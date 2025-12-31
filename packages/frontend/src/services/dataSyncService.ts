/**
 * 数据同步服务
 * 负责初始化和同步各种数据
 */
import { api } from './api'
import { useUserProfileStore } from '@/stores/useUserProfileStore'
import { useAIContextStore } from '@/hooks/useAIContext'
import { realtimeService } from './realtimeService'

// 同步状态
interface SyncStatus {
  userProfile: boolean
  watchlist: boolean
  insights: boolean
  lastSyncTime: Date | null
}

class DataSyncService {
  private syncStatus: SyncStatus = {
    userProfile: false,
    watchlist: false,
    insights: false,
    lastSyncTime: null
  }
  
  private syncInterval: ReturnType<typeof setInterval> | null = null
  private insightInterval: ReturnType<typeof setInterval> | null = null
  
  /**
   * 初始化数据同步
   */
  async initialize(): Promise<void> {
    console.log('Initializing data sync service...')
    
    try {
      // 1. 加载用户画像
      await this.syncUserProfile()
      
      // 2. 连接实时数据
      realtimeService.connect()
      
      // 3. 启动定时同步
      this.startPeriodicSync()
      
      console.log('Data sync service initialized')
    } catch (error) {
      console.error('Failed to initialize data sync service:', error)
    }
  }
  
  /**
   * 同步用户画像
   */
  async syncUserProfile(): Promise<void> {
    try {
      const store = useUserProfileStore.getState()
      await store.loadProfile()
      this.syncStatus.userProfile = true
      console.log('User profile synced')
    } catch (error) {
      console.error('Failed to sync user profile:', error)
    }
  }
  
  /**
   * 同步自选股数据
   */
  async syncWatchlist(watchlist: string[]): Promise<void> {
    try {
      // 订阅实时数据
      watchlist.forEach(code => {
        realtimeService.subscribe(code)
      })
      
      // 同步到用户画像
      await api.syncWatchlist(watchlist)
      
      this.syncStatus.watchlist = true
      console.log('Watchlist synced:', watchlist.length, 'stocks')
    } catch (error) {
      console.error('Failed to sync watchlist:', error)
    }
  }
  
  /**
   * 同步持仓数据
   */
  async syncHoldings(holdings: string[]): Promise<void> {
    try {
      // 订阅实时数据
      holdings.forEach(code => {
        realtimeService.subscribe(code)
      })
      
      // 同步到用户画像
      await api.syncHoldings(holdings)
      
      console.log('Holdings synced:', holdings.length, 'stocks')
    } catch (error) {
      console.error('Failed to sync holdings:', error)
    }
  }
  
  /**
   * 获取洞察数据
   */
  async fetchInsights(watchlist: string[], holdings: string[]): Promise<any> {
    try {
      const res: any = await api.getInsightSummary({
        watchlist,
        holdings
      })
      
      if (res.success) {
        this.syncStatus.insights = true
        return res.data
      }
      return null
    } catch (error) {
      console.error('Failed to fetch insights:', error)
      return null
    }
  }
  
  /**
   * 记录用户行为
   */
  async trackBehavior(
    eventType: string,
    data?: Record<string, any>,
    stockCode?: string,
    stockName?: string
  ): Promise<void> {
    try {
      await api.trackBehavior({
        event_type: eventType,
        data,
        stock_code: stockCode,
        stock_name: stockName,
        page: useAIContextStore.getState().context.currentPage
      })
    } catch (error) {
      // 静默失败，不影响用户体验
      console.debug('Failed to track behavior:', error)
    }
  }
  
  /**
   * 记录股票浏览
   */
  async trackStockView(stockCode: string, stockName: string): Promise<void> {
    // 更新AI上下文
    useAIContextStore.getState().setCurrentStock({
      code: stockCode,
      name: stockName
    })
    
    // 记录行为
    await this.trackBehavior('stock_view', {}, stockCode, stockName)
    
    // 更新用户画像
    useUserProfileStore.getState().trackStockView(stockCode, stockName)
  }
  
  /**
   * 记录查询
   */
  async trackQuery(query: string, intent: string, stockCodes?: string[]): Promise<void> {
    useAIContextStore.getState().addAction({
      type: 'ask_ai',
      target: query
    })
    
    useUserProfileStore.getState().trackQuery(query, intent, stockCodes)
  }
  
  /**
   * 启动定时同步
   */
  private startPeriodicSync(): void {
    // 每5分钟同步一次用户画像
    this.syncInterval = setInterval(() => {
      this.syncUserProfile()
    }, 5 * 60 * 1000)
    
    // 每分钟更新市场状态
    this.insightInterval = setInterval(() => {
      useAIContextStore.getState().updateMarketStatus()
    }, 60 * 1000)
  }
  
  /**
   * 停止同步
   */
  stop(): void {
    if (this.syncInterval) {
      clearInterval(this.syncInterval)
      this.syncInterval = null
    }
    if (this.insightInterval) {
      clearInterval(this.insightInterval)
      this.insightInterval = null
    }
    realtimeService.disconnect()
  }
  
  /**
   * 获取同步状态
   */
  getSyncStatus(): SyncStatus {
    return { ...this.syncStatus }
  }
  
  /**
   * 检查健康状态
   */
  async checkHealth(): Promise<boolean> {
    try {
      const res: any = await api.healthCheck()
      return res.status === 'healthy'
    } catch {
      return false
    }
  }
}

// 导出单例
export const dataSyncService = new DataSyncService()

export default dataSyncService
