import { useState, useRef, useEffect } from 'react'
import { Drawer, message, Segmented } from 'antd'
import { CloseOutlined, MessageOutlined, BulbOutlined, SunOutlined, SettingOutlined, HistoryOutlined, TrophyOutlined } from '@ant-design/icons'
import MessageList from './MessageList'
import InputArea from './InputArea'
import { 
  InsightPanel, 
  MorningBrief, 
  UserPreferences, 
  StreakCard, 
  AIGreeting,
  SmartSuggestions,
  DecisionReview,
  AchievementSystem
} from '@/components/AI'
import type { AISidebarProps, Message } from './types'
import { api } from '@/services/api'
import { useUserProfileStore } from '@/stores/useUserProfileStore'
import { useStreamingResponse } from '@/hooks/useStreamingResponse'
import { useAIContextStore } from '@/hooks/useAIContext'

// LocalStorage键名
const STORAGE_KEY = 'ai_sidebar_state'

type SidebarMode = 'insight' | 'chat' | 'brief' | 'review' | 'achievement' | 'settings'

/**
 * AI覆盖式侧边栏组件
 * 从右侧滑出，用于AI助手对话功能
 * 支持快捷键呼出（Ctrl+K或Cmd+K）
 */
export default function AISidebar({ 
  open, 
  onClose, 
  width = 420,
  watchlist = [],
  holdings = [],
  onStockClick
}: AISidebarProps) {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [useRAG, setUseRAG] = useState(true)
  const [useStreaming, setUseStreaming] = useState(true)
  const [mode, setMode] = useState<SidebarMode>('insight')
  const [lastIntent, setLastIntent] = useState<string>('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  
  // 记录每日活跃
  const recordDailyActive = useUserProfileStore(state => state.recordDailyActive)
  const trackQuery = useUserProfileStore(state => state.trackQuery)
  
  // AI上下文
  const { context, addAction } = useAIContextStore()
  
  // 流式响应Hook
  const { 
    content: streamingContent, 
    isStreaming, 
    sendStreamingMessage,
    reset: resetStreaming 
  } = useStreamingResponse({
    onComplete: (fullContent) => {
      // 流式完成后，更新最后一条消息
      setMessages(prev => {
        const newMessages = [...prev]
        if (newMessages.length > 0 && newMessages[newMessages.length - 1].role === 'assistant') {
          newMessages[newMessages.length - 1].content = fullContent
        }
        return newMessages
      })
      setLoading(false)
    },
    onError: (error) => {
      message.error(error)
      setLoading(false)
    }
  })
  
  useEffect(() => {
    if (open) {
      recordDailyActive()
    }
  }, [open])

  // 从localStorage加载状态
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const state = JSON.parse(saved)
        if (state.messages) {
          //恢复消息，重建Date对象
          const restoredMessages = state.messages.map((msg: Message) => ({
            ...msg,
            timestamp: msg.timestamp ? new Date(msg.timestamp) : undefined,
          }))
          setMessages(restoredMessages)
        }
        if (typeof state.useRAG === 'boolean') {
          setUseRAG(state.useRAG)
        }
      }
    } catch (error) {
      console.error('Failed to load state from localStorage:', error)
    }
  }, [])

  // 保存状态到localStorage
  useEffect(() => {
    try {
      const state = {
        messages,
        useRAG,
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
    } catch (error) {
      console.error('Failed to save state to localStorage:', error)
    }
  }, [messages, useRAG])

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

  // 更新流式内容到消息列表
  useEffect(() => {
    if (isStreaming && streamingContent) {
      setMessages(prev => {
        const newMessages = [...prev]
        if (newMessages.length > 0 && newMessages[newMessages.length - 1].role === 'assistant') {
          newMessages[newMessages.length - 1].content = streamingContent
        }
        return newMessages
      })
    }
  }, [streamingContent, isStreaming])

  // 发送消息
  const handleSend = async () => {
    if (!input.trim() || loading) return

    const userMessage = input.trim()
    setInput('')
    setMessages(prev => [...prev, { 
      role: 'user', 
      content: userMessage,
      timestamp: new Date()
    }])

    setLoading(true)
    
    // 追踪查询
    trackQuery(userMessage, 'chat')
    addAction({ type: 'ask_ai', target: userMessage })
    
    try {
      // 使用AI人格对话或RAG
      if (useStreaming && !useRAG) {
        // 流式AI对话
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: '',
          timestamp: new Date()
        }])
        await sendStreamingMessage(userMessage, {})
      } else {
        // 非流式请求
        const res = useRAG 
          ? await api.ragQuery(userMessage)
          : await api.aiChat(userMessage)

        if (res.success) {
          const responseContent = res.data.response || res.data.answer || JSON.stringify(res.data, null, 2)

          setMessages(prev => [...prev, {
            role: 'assistant',
            content: responseContent,
            useRAG: useRAG,
            timestamp: new Date()
          }])
        } else {
          message.error('查询失败')
        }
        setLoading(false)
      }
    } catch (error) {
      console.error('请求失败:', error)
      message.error('请求失败，请检查API服务')
      
      // 添加错误提示消息
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: '抱歉，当前服务不可用，请稍后再试。',
        timestamp: new Date()
      }])
      setLoading(false)
    }
  }

  // 清空对话
  const handleClearMessages = () => {
    setMessages([])
    resetStreaming()
  }

  return (
    <Drawer
      title={
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'space-between',
        }}>
          <Segmented
            value={mode}
            onChange={(val) => setMode(val as SidebarMode)}
            options={[
              { value: 'insight', label: '洞察', icon: <BulbOutlined /> },
              { value: 'brief', label: '早报', icon: <SunOutlined /> },
              { value: 'chat', label: '对话', icon: <MessageOutlined /> },
              { value: 'review', label: '复盘', icon: <HistoryOutlined /> },
              { value: 'achievement', label: '成就', icon: <TrophyOutlined /> },
              { value: 'settings', label: '设置', icon: <SettingOutlined /> },
            ]}
            size="small"
          />
          {mode === 'chat' && messages.length > 0 && (
            <span 
              onClick={handleClearMessages}
              style={{ 
                fontSize: 12, 
                color: '#58a6ff', 
                cursor: 'pointer',
                marginRight: 8,
              }}
            >
              清空
            </span>
          )}
        </div>
      }
      placement="right"
      onClose={onClose}
      open={open}
      width={width}
      closeIcon={<CloseOutlined />}
      styles={{
        body: { 
          padding: 0,
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          overflow: 'auto',
        },
        header: {
          background: '#0d1117',
          borderBottom: '1px solid #30363d',
        },
      }}
      mask={true}
      maskClosable={true}
    >
      {mode === 'insight' && (
        <InsightPanel 
          watchlist={watchlist}
          holdings={holdings}
          onStockClick={onStockClick}
        />
      )}
      
      {mode === 'brief' && (
        <div style={{ overflow: 'auto', flex: 1 }}>
          <div style={{ padding: 16 }}>
            <StreakCard />
          </div>
          <MorningBrief onStockClick={onStockClick} />
        </div>
      )}
      
      {mode === 'chat' && (
        <>
          {messages.length === 0 && (
            <div style={{ padding: '16px 16px 0' }}>
              <AIGreeting />
            </div>
          )}
          <MessageList
            messages={messages}
            loading={loading && !isStreaming}
            messagesEndRef={messagesEndRef}
            streamingContent={streamingContent}
            isStreaming={isStreaming}
          />
          {messages.length > 0 && !loading && (
            <SmartSuggestions 
              lastIntent={lastIntent}
              onSelect={(suggestion) => {
                setInput(suggestion)
              }}
            />
          )}
          <InputArea
            input={input}
            loading={loading}
            onInputChange={setInput}
            onSend={handleSend}
            onSuggestedQuestionClick={setInput}
            useRAG={useRAG}
            onRAGChange={setUseRAG}
          />
        </>
      )}
      
      {mode === 'review' && (
        <div style={{ overflow: 'auto', flex: 1 }}>
          <DecisionReview />
        </div>
      )}
      
      {mode === 'achievement' && (
        <div style={{ overflow: 'auto', flex: 1 }}>
          <AchievementSystem />
        </div>
      )}
      
      {mode === 'settings' && (
        <div style={{ overflow: 'auto', flex: 1 }}>
          <UserPreferences />
        </div>
      )}
    </Drawer>
  )
}