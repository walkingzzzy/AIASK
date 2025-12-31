/**
 * 应用初始化Hook
 * 负责应用启动时的数据初始化
 */
import { useEffect, useState, useCallback, useRef } from 'react'
import { dataSyncService } from '@/services/dataSyncService'
import { useUserProfileStore } from '@/stores/useUserProfileStore'

interface InitializeStatus {
  isInitialized: boolean
  isLoading: boolean
  error: string | null
  healthCheck: boolean
}

export function useAppInitialize() {
  const [status, setStatus] = useState<InitializeStatus>({
    isInitialized: false,
    isLoading: true,
    error: null,
    healthCheck: false
  })
  
  const recordDailyActive = useUserProfileStore(state => state.recordDailyActive)
  
  const initialize = useCallback(async () => {
    setStatus(prev => ({ ...prev, isLoading: true, error: null }))
    
    try {
      // 1. 健康检查
      const isHealthy = await dataSyncService.checkHealth()
      setStatus(prev => ({ ...prev, healthCheck: isHealthy }))
      
      if (!isHealthy) {
        console.warn('Backend service is not healthy, running in offline mode')
      }
      
      // 2. 初始化数据同步服务
      await dataSyncService.initialize()
      
      // 3. 记录每日活跃
      recordDailyActive()
      
      setStatus({
        isInitialized: true,
        isLoading: false,
        error: null,
        healthCheck: isHealthy
      })
      
      console.log('App initialized successfully')
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '初始化失败'
      setStatus({
        isInitialized: false,
        isLoading: false,
        error: errorMessage,
        healthCheck: false
      })
      console.error('App initialization failed:', error)
    }
  }, [recordDailyActive])
  
  const initializedRef = useRef(false)
  
  useEffect(() => {
    if (initializedRef.current) return
    initializedRef.current = true
    initialize()
    
    return () => {
      dataSyncService.stop()
    }
  }, [initialize])
  
  const retry = useCallback(() => {
    initialize()
  }, [initialize])
  
  return {
    ...status,
    retry
  }
}

export default useAppInitialize
