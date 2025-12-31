/**
 * 流式响应Hook
 * 用于处理AI对话的流式输出
 */
import { useState, useCallback, useRef } from 'react'
import { api } from '@/services/api'
import { API_BASE_URL } from '@/config/constants'

interface StreamingState {
  content: string
  isStreaming: boolean
  error: string | null
  isDone: boolean
}

interface UseStreamingResponseOptions {
  userId?: string
  onChunk?: (chunk: string) => void
  onComplete?: (fullContent: string) => void
  onError?: (error: string) => void
}

export function useStreamingResponse(options: UseStreamingResponseOptions = {}) {
  const { userId = 'default', onChunk, onComplete, onError } = options
  
  const [state, setState] = useState<StreamingState>({
    content: '',
    isStreaming: false,
    error: null,
    isDone: false,
  })
  
  const abortControllerRef = useRef<AbortController | null>(null)
  const contentRef = useRef('')

  /**
   * 发送流式请求
   */
  const sendStreamingMessage = useCallback(async (
    message: string,
    context: Record<string, any> = {}
  ) => {
    // 取消之前的请求
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    
    abortControllerRef.current = new AbortController()
    contentRef.current = ''
    
    setState({
      content: '',
      isStreaming: true,
      error: null,
      isDone: false,
    })

    try {
      const response = await fetch(
        `${API_BASE_URL}/ai/chat/stream?user_id=${userId}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ message, context, stream: true }),
          signal: abortControllerRef.current.signal,
        }
      )

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('No reader available')
      }

      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              
              if (data.done) {
                setState(prev => ({
                  ...prev,
                  isStreaming: false,
                  isDone: true,
                }))
                onComplete?.(contentRef.current)
              } else if (data.content) {
                contentRef.current += data.content
                setState(prev => ({
                  ...prev,
                  content: contentRef.current,
                }))
                onChunk?.(data.content)
              }
            } catch {
              // 忽略解析错误
            }
          }
        }
      }
    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        return // 请求被取消，不处理
      }
      
      const errorMessage = (error as Error).message || '流式请求失败'
      setState(prev => ({
        ...prev,
        isStreaming: false,
        error: errorMessage,
      }))
      onError?.(errorMessage)
    }
  }, [userId, onChunk, onComplete, onError])

  /**
   * 发送普通请求（非流式）
   */
  const sendMessage = useCallback(async (
    message: string,
    context: Record<string, any> = {}
  ) => {
    setState({
      content: '',
      isStreaming: true,
      error: null,
      isDone: false,
    })

    try {
      const res: any = await api.aiChat(message, context, userId)
      
      if (res.success) {
        const content = res.data.response
        setState({
          content,
          isStreaming: false,
          error: null,
          isDone: true,
        })
        onComplete?.(content)
        return content
      } else {
        throw new Error('请求失败')
      }
    } catch (error) {
      const errorMessage = (error as Error).message || '请求失败'
      setState(prev => ({
        ...prev,
        isStreaming: false,
        error: errorMessage,
      }))
      onError?.(errorMessage)
      return null
    }
  }, [userId, onComplete, onError])

  /**
   * 取消当前请求
   */
  const cancel = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      setState(prev => ({
        ...prev,
        isStreaming: false,
      }))
    }
  }, [])

  /**
   * 重置状态
   */
  const reset = useCallback(() => {
    cancel()
    contentRef.current = ''
    setState({
      content: '',
      isStreaming: false,
      error: null,
      isDone: false,
    })
  }, [cancel])

  return {
    ...state,
    sendStreamingMessage,
    sendMessage,
    cancel,
    reset,
  }
}

export default useStreamingResponse
