import { useState } from 'react'
import { Card, Input, Button, Row, Col, Progress, Tag, Spin, message, Typography } from 'antd'
import { SearchOutlined, RobotOutlined, LineChartOutlined, FundOutlined, HeartOutlined, SafetyOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { api } from '@/services/api'

const { Text } = Typography

interface AIScoreData {
  stock_code: string
  ai_score: number
  signal: string
  confidence: number
  subscores: {
    technical: number
    fundamental: number
    fund_flow: number
    sentiment: number
    risk: number
  }
}

export default function AIScore() {
  const [stockCode, setStockCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [scoreData, setScoreData] = useState<AIScoreData | null>(null)

  const handleSearch = async () => {
    if (!stockCode.trim()) {
      message.warning('请输入股票代码')
      return
    }
    
    setLoading(true)
    try {
      const res = await api.getAIScore(stockCode)
      if (res.success) {
        setScoreData(res.data)
      } else {
        message.error('获取评分失败')
      }
    } catch (error) {
      message.error('请求失败，请检查API服务是否启动')
    } finally {
      setLoading(false)
    }
  }

  const getSignalColor = (signal: string) => {
    switch (signal) {
      case 'Strong Buy': return 'red'
      case 'Buy': return 'orange'
      case 'Hold': return 'blue'
      case 'Sell': return 'green'
      case 'Strong Sell': return 'cyan'
      default: return 'default'
    }
  }

  const getScoreColor = (score: number) => {
    if (score >= 8) return '#ef4444'
    if (score >= 6) return '#f97316'
    if (score >= 4) return '#eab308'
    return '#22c55e'
  }

  return (
    <div className="space-y-4">
      {/* 搜索框 */}
      <Card>
        <div className="flex gap-4">
          <Input
            placeholder="输入股票代码，如 600519"
            value={stockCode}
            onChange={(e) => setStockCode(e.target.value)}
            onPressEnter={handleSearch}
            style={{ width: 300 }}
          />
          <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch} loading={loading}>
            获取AI评分
          </Button>
        </div>
      </Card>

      {/* 评分结果 */}
      {loading ? (
        <div className="flex justify-center items-center h-64">
          <Spin size="large" />
        </div>
      ) : scoreData ? (
        <Row gutter={16}>
          <Col span={8}>
            <Card title="综合评分">
              <div className="text-center">
                <Progress
                  type="circle"
                  percent={scoreData.ai_score * 10}
                  format={() => scoreData.ai_score.toFixed(1)}
                  strokeColor={getScoreColor(scoreData.ai_score)}
                  size={150}
                />
                <div className="mt-4">
                  <Tag color={getSignalColor(scoreData.signal)} className="text-lg px-4 py-1">
                    {scoreData.signal}
                  </Tag>
                </div>
                <div className="mt-2 text-gray-400">
                  置信度: {(scoreData.confidence * 100).toFixed(0)}%
                </div>
              </div>
            </Card>
          </Col>
          <Col span={16}>
            <Card title="分项评分">
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between mb-1">
                    <span>技术面</span>
                    <span>{scoreData.subscores.technical.toFixed(1)}</span>
                  </div>
                  <Progress percent={scoreData.subscores.technical * 10} showInfo={false} />
                </div>
                <div>
                  <div className="flex justify-between mb-1">
                    <span>基本面</span>
                    <span>{scoreData.subscores.fundamental.toFixed(1)}</span>
                  </div>
                  <Progress percent={scoreData.subscores.fundamental * 10} showInfo={false} />
                </div>
                <div>
                  <div className="flex justify-between mb-1">
                    <span>资金面</span>
                    <span>{scoreData.subscores.fund_flow.toFixed(1)}</span>
                  </div>
                  <Progress percent={scoreData.subscores.fund_flow * 10} showInfo={false} />
                </div>
                <div>
                  <div className="flex justify-between mb-1">
                    <span>情绪面</span>
                    <span>{scoreData.subscores.sentiment.toFixed(1)}</span>
                  </div>
                  <Progress percent={scoreData.subscores.sentiment * 10} showInfo={false} />
                </div>
                <div>
                  <div className="flex justify-between mb-1">
                    <span>风险面</span>
                    <span>{scoreData.subscores.risk.toFixed(1)}</span>
                  </div>
                  <Progress percent={scoreData.subscores.risk * 10} showInfo={false} />
                </div>
              </div>
            </Card>
          </Col>
        </Row>
      ) : (
        <Card styles={{ body: { padding: '60px 24px' } }}>
          <div style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            alignItems: 'center', 
            justifyContent: 'center',
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
            }}>
              <RobotOutlined style={{ fontSize: 40, color: 'white' }} />
            </div>
            <Text style={{ fontSize: 18, fontWeight: 600, color: '#e6edf3', marginBottom: 8 }}>
              AI智能评分系统
            </Text>
            <Text type="secondary" style={{ marginBottom: 24 }}>
              输入股票代码，获取多维度AI评分分析
            </Text>
            <div style={{ 
              display: 'flex', 
              gap: 24, 
              flexWrap: 'wrap', 
              justifyContent: 'center',
              maxWidth: 600,
            }}>
              {[
                { icon: <LineChartOutlined />, label: '技术面分析', color: '#58a6ff' },
                { icon: <FundOutlined />, label: '基本面分析', color: '#3fb950' },
                { icon: <ThunderboltOutlined />, label: '资金面分析', color: '#d29922' },
                { icon: <HeartOutlined />, label: '情绪面分析', color: '#f85149' },
                { icon: <SafetyOutlined />, label: '风险评估', color: '#8b5cf6' },
              ].map((item, index) => (
                <div 
                  key={index}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '8px 16px',
                    background: `${item.color}15`,
                    borderRadius: 8,
                    color: item.color,
                    fontSize: 13,
                  }}
                >
                  {item.icon}
                  <span>{item.label}</span>
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}
