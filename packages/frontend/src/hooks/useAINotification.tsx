/**
 * AI主动推送Hook
 * 管理AI推送通知的获取和显示
 */
import { useState, useEffect, useCallback } from 'react'
import { notification } from 'antd'
import { 
  BulbOutlined, 
  WarningOutlined, 
  RiseOutlined,
  SunOutlined,
  BellOutlined
} from '@ant-design/icons'
import { api } from '@/services/api'
import { useUserProfileStore } from '@/stores/useUserProfileStore'

// 推送类型
export type NotificationType = 
  | 'morning_brief'      // 早盘简报
  | 'opportunity'        // 投资机会
  | 'risk_alert'         // 风险预警
  | 'market_event'       // 市场事件
  | 'stock_alert'        // 个股异动
  | 'daily_review'       // 收盘复盘

// 推送优先级
export type NotificationPriority = 'critical' | 'high' | 'medium' | 'low'

// 推送消息
export interface AINotification {
  id: string
  type: NotificationType
  priority: NotificationPriority
  title: string
  content: string
  stockCode?: string
  stockName?: string
  timestamp: Date
  read: boolean
  actionUrl?: string
  data?: Record<string, any>
}

// 推送配置
interface NotificationConfig {
  enabled: boolean
  morningBrief: boolean
  opportunities: boolean
  riskAlerts: boolean
  stockAlerts: boolean
  dailyReview: boolean
  quietHoursStart: number  // 静默开始时间 (0-23)
  quietHoursEnd: number    // 静默结束时间 (0-23)
}

const defaultConfig: NotificationConfig = {
  enabled: true,
  morningBrief: true,
  opportunities: true,
  riskAlerts: true,
  stockAlerts: true,
  dailyReview: true,
  quietHoursStart: 22,
  quietHoursEnd: 8
}

// 图标映射
const iconMap: Record<NotificationType, React.ReactNode> = {
  morning_brief: <SunOutlined style={{ color: '#ffd700' }} />,
  opportunity: <RiseOutlined style={{ color: '#52c41a' }} />,
  risk_alert: <WarningOutlined style={{ color: '#ff4d4f' }} />,
  market_event: <BellOutlined style={{ color: '#1890ff' }} />,
  stock_alert: <BulbOutlined style={{ color: '#fa8c16' }} />,
  daily_review: <BulbOutlined style={{ color: '#722ed1' }} />
}

export function useAINotification() {
  const [notifications, setNotifications] = useState<AINotification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [config, setConfig] = useState<NotificationConfig>(defaultConfig)
  const [lastCheckTime, setLastCheckTime] = useState<Date | null>(null)
  
  const { notificationEnabled } = useUserProfileStore()
  
  // 检查是否在静默时间
  const isQuietHours = useCallback(() => {
    const hour = new Date().getHours()
    if (config.quietHoursStart > config.quietHoursEnd) {
      // 跨午夜
      return hour >= config.quietHoursStart || hour < config.quietHoursEnd
    }
    return hour >= config.quietHoursStart && hour < config.quietHoursEnd
  }, [config])
  
  // 标记已读
  const markAsRead = useCallback((id: string) => {
    setNotifications(prev =>
      prev.map(n => n.id === id ? { ...n, read: true } : n)
    )
    setUnreadCount(prev => Math.max(0, prev - 1))
  }, [])
  
  // 显示通知
  const showNotification = useCallback((notif: AINotification) => {
    if (!config.enabled || !notificationEnabled) return
    if (isQuietHours() && notif.priority !== 'critical') return
    
    // 检查类型是否启用
    const typeEnabled = {
      morning_brief: config.morningBrief,
      opportunity: config.opportunities,
      risk_alert: config.riskAlerts,
      stock_alert: config.stockAlerts,
      market_event: true,
      daily_review: config.dailyReview
    }
    
    if (!typeEnabled[notif.type]) return
    
    // 显示系统通知
    notification.open({
      message: notif.title,
      description: notif.content,
      icon: iconMap[notif.type],
      placement: 'topRight',
      duration: notif.priority === 'critical' ? 0 : 5,
      onClick: () => {
        markAsRead(notif.id)
      }
    })
  }, [config, notificationEnabled, isQuietHours, markAsRead])
  
  // 添加通知
  const addNotification = useCallback((notif: Omit<AINotification, 'id' | 'timestamp' | 'read'>) => {
    const newNotif: AINotification = {
      ...notif,
      id: `notif_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      timestamp: new Date(),
      read: false
    }
    
    setNotifications(prev => [newNotif, ...prev].slice(0, 50)) // 保留最近50条
    setUnreadCount(prev => prev + 1)
    showNotification(newNotif)
    
    return newNotif
  }, [showNotification])
  
  // 标记全部已读
  const markAllAsRead = useCallback(() => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })))
    setUnreadCount(0)
  }, [])
  
  // 清除通知
  const clearNotifications = useCallback(() => {
    setNotifications([])
    setUnreadCount(0)
  }, [])
  
  // 获取推送（从服务器）
  const fetchNotifications = useCallback(async () => {
    try {
      // 获取机会推送
      const opportunitiesRes: any = await api.getOpportunities({
        watchlist: [],
        holdings: []
      })
      
      if (opportunitiesRes.success && opportunitiesRes.data?.length > 0) {
        const topOpportunity = opportunitiesRes.data[0]
        addNotification({
          type: 'opportunity',
          priority: topOpportunity.urgency === 'high' ? 'high' : 'medium',
          title: '发现投资机会',
          content: `${topOpportunity.stock_name}: ${topOpportunity.reason}`,
          stockCode: topOpportunity.stock_code,
          stockName: topOpportunity.stock_name,
          data: topOpportunity
        })
      }
      
      // 获取风险预警
      const risksRes: any = await api.getRisks({
        watchlist: [],
        holdings: []
      })
      
      if (risksRes.success && risksRes.data?.length > 0) {
        const criticalRisks = risksRes.data.filter((r: any) => r.severity === 'critical')
        for (const risk of criticalRisks.slice(0, 2)) {
          addNotification({
            type: 'risk_alert',
            priority: 'critical',
            title: risk.title,
            content: risk.description,
            stockCode: risk.stock_code,
            stockName: risk.stock_name,
            data: risk
          })
        }
      }
      
      setLastCheckTime(new Date())
    } catch (error) {
      console.error('获取推送失败:', error)
    }
  }, [addNotification])
  
  // 检查早盘简报时间
  const checkMorningBrief = useCallback(async () => {
    const now = new Date()
    const hour = now.getHours()
    const minute = now.getMinutes()
    
    // 8:30-9:00 推送早盘简报
    if (hour === 8 && minute >= 30 && config.morningBrief) {
      try {
        const res: any = await api.getMorningBrief()
        if (res.success && res.data) {
          addNotification({
            type: 'morning_brief',
            priority: 'medium',
            title: '📰 今日早盘简报',
            content: res.data.greeting || '新的一天开始了，让我们看看今天的市场情况。',
            data: res.data
          })
        }
      } catch (error) {
        console.error('获取早盘简报失败:', error)
      }
    }
  }, [config.morningBrief, addNotification])
  
  // 定时检查推送
  useEffect(() => {
    if (!config.enabled || !notificationEnabled) return
    
    // 初始检查
    checkMorningBrief()
    
    // 每5分钟检查一次
    const interval = setInterval(() => {
      const marketStatus = getMarketStatus()
      
      // 交易时段检查机会和风险
      if (marketStatus === 'trading') {
        fetchNotifications()
      }
      
      // 检查早盘简报
      checkMorningBrief()
    }, 5 * 60 * 1000)
    
    return () => clearInterval(interval)
  }, [config.enabled, notificationEnabled, fetchNotifications, checkMorningBrief])
  
  // 更新配置
  const updateConfig = useCallback((updates: Partial<NotificationConfig>) => {
    setConfig(prev => ({ ...prev, ...updates }))
  }, [])
  
  return {
    notifications,
    unreadCount,
    config,
    addNotification,
    markAsRead,
    markAllAsRead,
    clearNotifications,
    fetchNotifications,
    updateConfig,
    lastCheckTime
  }
}

// 辅助函数：获取市场状态
function getMarketStatus(): 'pre_open' | 'trading' | 'lunch_break' | 'closed' {
  const now = new Date()
  const hour = now.getHours()
  const minute = now.getMinutes()
  const day = now.getDay()
  
  if (day === 0 || day === 6) return 'closed'
  
  const time = hour * 100 + minute
  
  if (time < 930) return 'pre_open'
  if (time >= 930 && time < 1130) return 'trading'
  if (time >= 1130 && time < 1300) return 'lunch_break'
  if (time >= 1300 && time < 1500) return 'trading'
  return 'closed'
}

export default useAINotification
