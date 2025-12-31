/**
 * WebSocket Hook for Real-time Data Updates
 * 支持自动重连、心跳检测、指数退避
 */
import { useEffect, useRef, useState, useCallback } from 'react'

interface WebSocketMessage {
  type: string
  stock_code?: string
  data?: any
  message?: string
  limits?: {
    max_subscriptions: number
  }
}

interface UseWebSocketOptions {
  url?: string
  onMessage?: (message: WebSocketMessage) => void
  onError?: (error: Event) => void
  onOpen?: () => void
  onClose?: () => void
  reconnectInterval?: number
  maxReconnectAttempts?: number
  heartbeatInterval?: number
}

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 'failed'

export const useWebSocket = (options: UseWebSocketOptions = {}) => {
  const {
    url = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000/ws/realtime',
    onMessage,
    onError,
    onOpen,
    onClose,
    reconnectInterval = 3000,
    maxReconnectAttempts = 10,
    heartbeatInterval = 30000
  } = options

  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null)
  const [subscriptionLimit, setSubscriptionLimit] = useState<number>(50)
  
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>()
  const heartbeatTimeoutRef = useRef<ReturnType<typeof setTimeout>>()
  const lastPongRef = useRef<number>(Date.now())

  // 计算指数退避延迟
  const getReconnectDelay = useCallback(() => {
    const baseDelay = reconnectInterval
    const attempt = reconnectAttemptsRef.current
    // 指数退避，最大30秒
    return Math.min(baseDelay * Math.pow(1.5, attempt), 30000)
  }, [reconnectInterval])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }

    setStatus('connecting')

    try {
      const ws = new WebSocket(url)

      ws.onopen = () => {
        console.log('WebSocket connected')
        setStatus('connected')
        reconnectAttemptsRef.current = 0
        lastPongRef.current = Date.now()
        onOpen?.()
      }

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data)
          setLastMessage(message)
          
          // 处理特殊消息类型
          if (message.type === 'connected' && message.limits) {
            setSubscriptionLimit(message.limits.max_subscriptions)
          }
          
          if (message.type === 'pong' || message.type === 'heartbeat') {
            lastPongRef.current = Date.now()
          }
          
          onMessage?.(message)
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        onError?.(error)
      }

      ws.onclose = (event) => {
        console.log('WebSocket disconnected:', event.code, event.reason)
        setStatus('disconnected')
        onClose?.()

        // 非正常关闭时自动重连
        if (event.code !== 1000 && reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current++
          const delay = getReconnectDelay()
          console.log(`Reconnecting in ${delay}ms... Attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts}`)
          setStatus('reconnecting')
          
          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, delay)
        } else if (reconnectAttemptsRef.current >= maxReconnectAttempts) {
          console.log('Max reconnect attempts reached')
          setStatus('failed')
        }
      }

      wsRef.current = ws
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error)
      setStatus('failed')
    }
  }, [url, onMessage, onError, onOpen, onClose, maxReconnectAttempts, getReconnectDelay])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }
    if (heartbeatTimeoutRef.current) {
      clearTimeout(heartbeatTimeoutRef.current)
    }
    if (wsRef.current) {
      wsRef.current.close(1000, 'User disconnect')
      wsRef.current = null
    }
    setStatus('disconnected')
    reconnectAttemptsRef.current = 0
  }, [])

  const sendMessage = useCallback((message: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message))
      return true
    } else {
      console.warn('WebSocket is not connected')
      return false
    }
  }, [])

  const subscribe = useCallback((stockCode: string) => {
    return sendMessage({
      action: 'subscribe',
      stock_code: stockCode
    })
  }, [sendMessage])

  const subscribeBatch = useCallback((stockCodes: string[]) => {
    return sendMessage({
      action: 'subscribe_batch',
      stock_codes: stockCodes
    })
  }, [sendMessage])

  const unsubscribe = useCallback((stockCode: string) => {
    return sendMessage({
      action: 'unsubscribe',
      stock_code: stockCode
    })
  }, [sendMessage])

  const unsubscribeAll = useCallback(() => {
    return sendMessage({ action: 'unsubscribe_all' })
  }, [sendMessage])

  const subscribeAI = useCallback(() => {
    return sendMessage({ action: 'subscribe_ai' })
  }, [sendMessage])

  const unsubscribeAI = useCallback(() => {
    return sendMessage({ action: 'unsubscribe_ai' })
  }, [sendMessage])

  // 手动重连
  const reconnect = useCallback(() => {
    disconnect()
    reconnectAttemptsRef.current = 0
    setTimeout(connect, 100)
  }, [connect, disconnect])

  // 使用 ref 存储最新的回调函数，避免闭包陷阱
  const connectRef = useRef(connect)
  const disconnectRef = useRef(disconnect)
  const sendMessageRef = useRef(sendMessage)
  const reconnectRef = useRef(reconnect)
  const statusRef = useRef(status)
  const heartbeatIntervalRef = useRef(heartbeatInterval)

  useEffect(() => {
    connectRef.current = connect
    disconnectRef.current = disconnect
    sendMessageRef.current = sendMessage
    reconnectRef.current = reconnect
    statusRef.current = status
    heartbeatIntervalRef.current = heartbeatInterval
  })

  useEffect(() => {
    connectRef.current()

    // 心跳检测
    const heartbeatCheck = setInterval(() => {
      if (statusRef.current === 'connected') {
        // 发送心跳
        sendMessageRef.current({ action: 'ping' })
        
        // 检查是否收到响应（超过2个心跳周期未收到响应则重连）
        const timeSinceLastPong = Date.now() - lastPongRef.current
        if (timeSinceLastPong > heartbeatIntervalRef.current * 2) {
          console.warn('Heartbeat timeout, reconnecting...')
          reconnectRef.current()
        }
      }
    }, heartbeatIntervalRef.current)

    return () => {
      clearInterval(heartbeatCheck)
      disconnectRef.current()
    }
  }, [])

  return {
    status,
    isConnected: status === 'connected',
    lastMessage,
    subscriptionLimit,
    sendMessage,
    subscribe,
    subscribeBatch,
    unsubscribe,
    unsubscribeAll,
    subscribeAI,
    unsubscribeAI,
    disconnect,
    reconnect
  }
}

export default useWebSocket
