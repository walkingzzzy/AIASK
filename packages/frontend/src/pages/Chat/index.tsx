import { useState, useRef, useEffect, useMemo } from 'react'
import { Card, Input, Button, Spin, message, Switch, Space, Typography, Avatar } from 'antd'
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  InfoCircleOutlined,
  BulbOutlined,
} from '@ant-design/icons'
import DOMPurify from 'dompurify'
import { api } from '@/services/api'

const { Text, Paragraph } = Typography

interface Message {
  role: 'user' | 'assistant'
  content: string
  useRAG?: boolean
  timestamp?: Date
}

export default function Chat() {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [useRAG, setUseRAG] = useState(true)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 自动滚动到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSend = async () => {
    if (!input.trim()) return

    const userMessage = input.trim()
    setInput('')
    setMessages(prev => [...prev, { 
      role: 'user', 
      content: userMessage,
      timestamp: new Date()
    }])

    setLoading(true)
    try {
      let res

      if (useRAG) {
        res = await api.ragQuery(userMessage)
      } else {
        res = await api.query(userMessage)
      }

      if (res.success) {
        const responseContent = res.data.response || res.data.answer ||
                               JSON.stringify(res.data, null, 2)

        setMessages(prev => [...prev, {
          role: 'assistant',
          content: responseContent,
          useRAG: useRAG,
          timestamp: new Date()
        }])
      } else {
        message.error('查询失败')
      }
    } catch (error) {
      console.error('请求失败:', error)
      message.error('请求失败，请检查API服务是否启动')
    } finally {
      setLoading(false)
    }
  }

  const suggestedQuestions = [
    { icon: '📈', text: '帮我分析一下贵州茅台的投资价值' },
    { icon: '🔥', text: '今天有哪些涨停股票？' },
    { icon: '💡', text: '最近市场热点板块有哪些？' },
    { icon: '📊', text: '如何判断一只股票的买入时机？' },
  ]

  return (
    <div style={{ 
      display: 'flex', 
      flexDirection: 'column', 
      height: 'calc(100vh - 180px)',
      minHeight: 500,
    }}>
      {/* 顶部控制栏 */}
      <Card 
        styles={{ 
          body: { 
            padding: '12px 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 12,
          } 
        }}
        style={{ marginBottom: 16, flexShrink: 0 }}
      >
        <Space size="middle">
          <div style={{
            width: 36,
            height: 36,
            borderRadius: 8,
            background: 'linear-gradient(135deg, #58a6ff 0%, #8b5cf6 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <RobotOutlined style={{ fontSize: 18, color: 'white' }} />
          </div>
          <div>
            <Text strong style={{ fontSize: 14 }}>RAG增强检索</Text>
            <Switch
              checked={useRAG}
              onChange={setUseRAG}
              size="small"
              style={{ marginLeft: 12 }}
            />
          </div>
        </Space>
        <Text type="secondary" style={{ fontSize: 12 }}>
          <InfoCircleOutlined style={{ marginRight: 4 }} />
          {useRAG ? '使用向量数据库增强回答准确性' : '使用基础NLP查询'}
        </Text>
      </Card>

      {/* 消息区域 */}
      <Card 
        style={{ 
          flex: 1, 
          marginBottom: 16,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
        styles={{ 
          body: { 
            flex: 1,
            overflow: 'auto',
            padding: 20,
            display: 'flex',
            flexDirection: 'column',
          } 
        }}
      >
        {messages.length === 0 ? (
          // 空状态 - 欢迎界面
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
              width: 80,
              height: 80,
              borderRadius: 20,
              background: 'linear-gradient(135deg, #58a6ff 0%, #8b5cf6 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: 24,
              boxShadow: '0 8px 32px rgba(88, 166, 255, 0.3)',
            }}>
              <RobotOutlined style={{ fontSize: 36, color: 'white' }} />
            </div>
            
            <Paragraph strong style={{ fontSize: 20, marginBottom: 8, color: '#e6edf3' }}>
              你好！我是A股智能分析助手
            </Paragraph>
            <Paragraph type="secondary" style={{ marginBottom: 32, maxWidth: 400 }}>
              我可以帮你分析股票、解读市场行情、提供投资建议。试试下面的问题开始对话吧！
            </Paragraph>

            {/* 推荐问题 */}
            <div style={{ width: '100%', maxWidth: 600 }}>
              <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: 8, 
                marginBottom: 16,
                justifyContent: 'center',
              }}>
                <BulbOutlined style={{ color: '#d29922' }} />
                <Text type="secondary">试试这些问题</Text>
              </div>
              <div style={{ 
                display: 'grid', 
                gridTemplateColumns: 'repeat(2, 1fr)', 
                gap: 12,
              }}>
                {suggestedQuestions.map((q, i) => (
                  <Button
                    key={i}
                    type="default"
                    onClick={() => setInput(q.text)}
                    style={{
                      height: 'auto',
                      padding: '12px 16px',
                      textAlign: 'left',
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 10,
                      whiteSpace: 'normal',
                      lineHeight: 1.4,
                    }}
                  >
                    <span style={{ fontSize: 18 }}>{q.icon}</span>
                    <span style={{ flex: 1 }}>{q.text}</span>
                  </Button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          // 消息列表
          <div style={{ flex: 1 }}>
            {messages.map((msg, index) => (
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
                  maxWidth: '80%',
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
                    <pre
                      style={{
                        whiteSpace: 'pre-wrap',
                        fontFamily: 'inherit',
                        margin: 0,
                        lineHeight: 1.6,
                      }}
                      dangerouslySetInnerHTML={{
                        __html: DOMPurify.sanitize(msg.content)
                      }}
                    />
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
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}

        {/* 加载状态 */}
        {loading && (
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
        )}
      </Card>

      {/* 输入区域 */}
      <div style={{ 
        display: 'flex', 
        gap: 12,
        flexShrink: 0,
      }}>
        <Input
          placeholder="输入您的问题..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={handleSend}
          disabled={loading}
          size="large"
          autoComplete="off"
          allowClear
          style={{ flex: 1 }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSend}
          loading={loading}
          size="large"
          style={{ width: 100 }}
        >
          发送
        </Button>
      </div>
    </div>
  )
}
