import { Avatar, Spin, Typography } from 'antd'
import { 
  RobotOutlined, 
  UserOutlined,
  BulbOutlined,
} from '@ant-design/icons'
import type { MessageListProps, Message } from './types'

const { Text, Paragraph } = Typography

/**
 * 消息列表组件
 * 显示用户和AI助手的对话消息
 */
export default function MessageList({
  messages,
  loading,
  messagesEndRef,
  streamingContent,
  isStreaming,
}: MessageListProps) {
  // 推荐问题列表
  const suggestedQuestions = [
    { icon: '📈', text: '帮我分析一下贵州茅台的投资价值' },
    { icon: '🔥', text: '今天有哪些涨停股票？' },
    { icon: '💡', text: '最近市场热点板块有哪些？' },
    { icon: '📊', text: '如何判断一只股票的买入时机？' },
  ]

  // 渲染单条消息
  const renderMessage = (msg: Message, index: number) => (
    <div
      key={index}
      style={{
        display: 'flex',
        justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
        marginBottom: 16,
      }}
      className="fade-in"
    >
      <div style={{
        display: 'flex',
        gap: 12,
        maxWidth: '85%',
        flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
      }}>
        <Avatar 
          icon={msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
          style={{ 
            backgroundColor: msg.role === 'user' ? '#3fb950' : '#58a6ff',
            flexShrink: 0,
          }}
        />
        <div style={{
          padding: '12px 16px',
          borderRadius: 12,
          background: msg.role === 'user' ? '#58a6ff' : '#262c36',
          color: msg.role === 'user' ? 'white' : '#e6edf3',
        }}>
          {msg.role === 'assistant' && msg.useRAG && (
            <div style={{ 
              fontSize: 11, 
              opacity: 0.7, 
              marginBottom: 6,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}>
              <RobotOutlined /> RAG增强回答
            </div>
          )}
          <pre style={{ 
            whiteSpace: 'pre-wrap', 
            fontFamily: 'inherit', 
            margin: 0,
            lineHeight: 1.6,
          }}>
            {msg.content}
          </pre>
          {msg.timestamp && (
            <div style={{ 
              fontSize: 11, 
              opacity: 0.5, 
              marginTop: 8, 
              textAlign: 'right',
            }}>
              {msg.timestamp.toLocaleTimeString('zh-CN', { 
                hour: '2-digit', 
                minute: '2-digit' 
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )

  // 空状态 - 欢迎界面
  const renderEmptyState = () => (
    <div style={{ 
      flex: 1, 
      display: 'flex', 
      flexDirection: 'column', 
      alignItems: 'center', 
      justifyContent: 'center',
      textAlign: 'center',
      padding: 20,
    }}>
      <div style={{
        width: 70,
        height: 70,
        borderRadius: 16,
        background: 'linear-gradient(135deg, #58a6ff 0%, #8b5cf6 100%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: 20,
        boxShadow: '0 8px 32px rgba(88, 166, 255, 0.3)',
      }}>
        <RobotOutlined style={{ fontSize: 32, color: 'white' }} />
      </div>
      <Paragraph strong style={{ fontSize: 18, marginBottom: 8, color: '#e6edf3' }}>
        你好！我是A股智能分析助手
      </Paragraph>
      <Paragraph type="secondary" style={{ marginBottom: 24, fontSize: 13}}>
        我可以帮你分析股票、解读市场行情、提供投资建议
      </Paragraph>

      {/* 推荐问题 */}
      <div style={{ width: '100%' }}>
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: 6, 
          marginBottom: 12,justifyContent: 'center',
        }}>
          <BulbOutlined style={{ color: '#d29922', fontSize: 14 }} />
          <Text type="secondary" style={{ fontSize: 12 }}>试试这些问题</Text>
        </div>
        <div style={{ 
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
        }}>
          {suggestedQuestions.map((q, i) => (
            <div
              key={i}
              onClick={() => {
                // 这个功能需要通过props传递
                console.log('Suggested question clicked:', q.text)
              }}
              style={{
                padding: '10px 12px',
                textAlign: 'left',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                whiteSpace: 'normal',
                lineHeight: 1.4,
                cursor: 'pointer',borderRadius: 8,
                border: '1px solid #30363d',
                transition: 'all 0.2s',fontSize: 12,
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = '#262c36'
                e.currentTarget.style.borderColor = '#58a6ff'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent'
                e.currentTarget.style.borderColor = '#30363d'
              }}
            >
              <span style={{ fontSize: 16}}>{q.icon}</span>
              <span style={{ flex: 1, color: '#e6edf3' }}>{q.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  // 加载状态
  const renderLoadingState = () => (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '12px 0',
    }}>
      <Avatar
        icon={<RobotOutlined />}
        style={{ backgroundColor: '#58a6ff' }}
      />
      <div style={{
        padding: '12px 16px',
        borderRadius: 12,
        background: '#262c36',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}>
        <Spin size="small" />
        <Text type="secondary">正在思考中...</Text>
      </div>
    </div>
  )

  // 渲染流式消息
  const renderStreamingMessage = () => (
    <div style={{
      display: 'flex',
      justifyContent: 'flex-start',
      marginBottom: 16,
    }}>
      <div style={{ display: 'flex', gap: 12, maxWidth: '85%' }}>
        <Avatar
          icon={<RobotOutlined />}
          style={{ backgroundColor: '#58a6ff', flexShrink: 0 }}
        />
        <div style={{
          padding: '12px 16px',
          borderRadius: 12,
          background: '#262c36',
          color: '#e6edf3',
        }}>
          <pre style={{
            whiteSpace: 'pre-wrap',
            fontFamily: 'inherit',
            margin: 0,
            lineHeight: 1.6,
          }}>
            {streamingContent}<span className="typing-cursor">|</span>
          </pre>
        </div>
      </div>
    </div>
  )

  return (
    <div style={{
      flex: 1,
      overflow: 'auto',
      padding: 20,
      display: 'flex',
      flexDirection: 'column',
    }}>
      <style>{`
        @keyframes blink { 0%,50%{opacity:1} 51%,100%{opacity:0} }
        .typing-cursor { animation: blink 1s infinite; color: #58a6ff; font-weight: bold; }
      `}</style>
      {messages.length === 0 && !isStreaming ? (
        renderEmptyState()
      ) : (
        <div style={{ flex: 1 }}>
          {messages.map(renderMessage)}
          {isStreaming && streamingContent && renderStreamingMessage()}
          <div ref={messagesEndRef} />
        </div>
      )}

      {loading && !isStreaming && renderLoadingState()}
    </div>
  )
}