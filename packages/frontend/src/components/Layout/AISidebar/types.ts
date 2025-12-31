/**
 * AI侧边栏组件类型定义
 */

export interface Message {
  role: 'user' | 'assistant'
  content: string
  useRAG?: boolean
  timestamp?: Date
  isStreaming?: boolean
}

export interface AISidebarProps {
  open: boolean
  onClose: () => void
  width?: number
  watchlist?: string[]
  holdings?: string[]
  onStockClick?: (stockCode: string) => void
}

export interface MessageListProps {
  messages: Message[]
  loading: boolean
  messagesEndRef: React.RefObject<HTMLDivElement>
  streamingContent?: string
  isStreaming?: boolean
}

export interface InputAreaProps {
  input: string
  loading: boolean
  onInputChange: (value: string) => void
  onSend: () => void
  onSuggestedQuestionClick: (text: string) => void
}