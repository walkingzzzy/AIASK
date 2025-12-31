import { useState, useEffect } from 'react'
import { Card, Row, Col, Statistic, Table, Tag, Spin, Space, Typography } from 'antd'
import { 
  ArrowUpOutlined, 
  ArrowDownOutlined, 
  FireOutlined, 
  ThunderboltOutlined,
  TrophyOutlined,
  WalletOutlined,
  BankOutlined,
  SmileOutlined,
} from '@ant-design/icons'
import { api } from '@/services/api'
import { useWebSocket } from '@/hooks/useWebSocket'

const { Text } = Typography

interface MarketStats {
  total: number
  first_limit: number
  continuous: number
  max_continuous: number
}

interface LimitUpStock {
  stock_code: string
  stock_name: string
  continuous_days: number
  limit_up_reason?: string
}

// 连接状态组件
const ConnectionStatus = ({ isConnected }: { isConnected: boolean }) => (
  <span 
    className={`connection-status ${isConnected ? 'online' : 'offline'}`}
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      padding: '2px 8px',
      borderRadius: 10,
      fontSize: 11,
      fontWeight: 500,
      background: isConnected ? 'rgba(63, 185, 80, 0.15)' : 'rgba(248, 81, 73, 0.15)',
      color: isConnected ? '#3fb950' : '#f85149',
    }}
  >
    <span style={{
      width: 6,
      height: 6,
      borderRadius: '50%',
      background: isConnected ? '#3fb950' : '#f85149',
    }} />
    {isConnected ? '实时' : '离线'}
  </span>
)

// 统计卡片组件
const StatCard = ({ 
  title, 
  value, 
  suffix, 
  icon, 
  color,
  trend,
  extra,
}: {
  title: React.ReactNode
  value: number | string
  suffix?: string
  icon: React.ReactNode
  color?: string
  trend?: 'up' | 'down'
  extra?: React.ReactNode
}) => (
  <Card 
    className="stat-card"
    styles={{ body: { padding: '20px 24px' } }}
  >
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
      <div>
        <div style={{ 
          color: '#8b949e', 
          fontSize: 13, 
          marginBottom: 12,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}>
          {title}
          {extra}
        </div>
        <div style={{ 
          display: 'flex', 
          alignItems: 'baseline', 
          gap: 4,
        }}>
          {trend && (
            <span style={{ color: trend === 'up' ? '#f85149' : '#3fb950', marginRight: 4 }}>
              {trend === 'up' ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
            </span>
          )}
          <span 
            className="font-mono-num"
            style={{ 
              fontSize: 32, 
              fontWeight: 600, 
              color: color || '#e6edf3',
              lineHeight: 1,
            }}
          >
            {value}
          </span>
          {suffix && (
            <span style={{ fontSize: 14, color: '#8b949e', marginLeft: 4 }}>
              {suffix}
            </span>
          )}
        </div>
      </div>
      <div style={{ 
        fontSize: 24, 
        color: color || '#58a6ff',
        opacity: 0.8,
      }}>
        {icon}
      </div>
    </div>
  </Card>
)

export default function Dashboard() {
  const [loading, setLoading] = useState(true)
  const [limitUpStats, setLimitUpStats] = useState<MarketStats | null>(null)
  const [limitUpStocks, setLimitUpStocks] = useState<LimitUpStock[]>([])
  const [marginData, setMarginData] = useState<any>(null)

  // WebSocket实时连接
  const { isConnected } = useWebSocket({
    onMessage: (message) => {
      console.log('Received real-time update:', message)
      if (message.type === 'market_update') {
        if (message.data) {
          setMarginData((prev: any) => ({ ...prev, ...message.data }))
        }
      }
    }
  })

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [statsRes, stocksRes, marginRes] = await Promise.all([
        api.getLimitUpStatistics(),
        api.getDailyLimitUp(),
        api.getMarketMargin()
      ])
      
      if (statsRes.success) setLimitUpStats(statsRes.data)
      if (stocksRes.success) setLimitUpStocks(stocksRes.data.slice(0, 10))
      if (marginRes.success) setMarginData(marginRes.data)
    } catch (error) {
      console.error('加载数据失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const columns = [
    {
      title: '股票',
      dataIndex: 'stock_name',
      key: 'stock_name',
      render: (text: string, record: LimitUpStock) => (
        <div>
          <Text strong style={{ color: '#e6edf3' }}>{text}</Text>
          <Text type="secondary" style={{ fontSize: 12, marginLeft: 6 }}>
            {record.stock_code}
          </Text>
        </div>
      )
    },
    {
      title: '连板',
      dataIndex: 'continuous_days',
      key: 'continuous_days',
      width: 80,
      render: (days: number) => (
        <Tag 
          color={days >= 3 ? '#f85149' : days >= 2 ? '#d29922' : 'default'}
          style={{ 
            borderRadius: 4, 
            fontWeight: 600,
            border: 'none',
          }}
        >
          {days}板
        </Tag>
      )
    },
    {
      title: '涨停原因',
      dataIndex: 'limit_up_reason',
      key: 'limit_up_reason',
      ellipsis: true,
      render: (text: string) => (
        <Text type="secondary" ellipsis style={{ maxWidth: 200 }}>
          {text || '-'}
        </Text>
      )
    }
  ]

  if (loading) {
    return (
      <div style={{ 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center', 
        height: 400,
        flexDirection: 'column',
        gap: 16,
      }}>
        <Spin size="large" />
        <Text type="secondary">加载市场数据中...</Text>
      </div>
    )
  }

  // 获取市场情绪颜色
  const getSentimentColor = (sentiment: string) => {
    if (sentiment?.includes('乐观') || sentiment?.includes('贪婪')) return '#3fb950'
    if (sentiment?.includes('悲观') || sentiment?.includes('恐惧')) return '#f85149'
    return '#d29922'
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 涨停统计 */}
      <Row gutter={16}>
        <Col xs={24} sm={12} lg={6}>
          <StatCard
            title={
              <Space>
                今日涨停
                <ConnectionStatus isConnected={isConnected} />
              </Space>
            }
            value={limitUpStats?.total || 0}
            suffix="只"
            icon={<FireOutlined />}
            color="#f85149"
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard
            title="首板"
            value={limitUpStats?.first_limit || 0}
            suffix="只"
            icon={<ThunderboltOutlined />}
            color="#58a6ff"
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard
            title="连板"
            value={limitUpStats?.continuous || 0}
            suffix="只"
            icon={<FireOutlined />}
            color="#d29922"
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard
            title="最高连板"
            value={limitUpStats?.max_continuous || 0}
            suffix="板"
            icon={<TrophyOutlined />}
            color="#f85149"
          />
        </Col>
      </Row>

      {/* 融资融券 */}
      <Row gutter={16}>
        <Col xs={24} sm={12} lg={8}>
          <StatCard
            title="融资余额"
            value={marginData?.financing_balance?.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'}
            suffix="亿"
            icon={<WalletOutlined />}
            color={marginData?.financing_5d_change > 0 ? '#f85149' : '#3fb950'}
            trend={marginData?.financing_5d_change > 0 ? 'up' : 'down'}
          />
        </Col>
        <Col xs={24} sm={12} lg={8}>
          <StatCard
            title="融券余额"
            value={marginData?.securities_balance?.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'}
            suffix="亿"
            icon={<BankOutlined />}
            color="#58a6ff"
          />
        </Col>
        <Col xs={24} lg={8}>
          <Card styles={{ body: { padding: '20px 24px' } }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ color: '#8b949e', fontSize: 13, marginBottom: 12 }}>
                  市场情绪
                </div>
                <div style={{ 
                  fontSize: 24, 
                  fontWeight: 600, 
                  color: getSentimentColor(marginData?.market_sentiment),
                }}>
                  {marginData?.market_sentiment || '未知'}
                </div>
              </div>
              <div style={{ fontSize: 24, color: getSentimentColor(marginData?.market_sentiment), opacity: 0.8 }}>
                <SmileOutlined />
              </div>
            </div>
          </Card>
        </Col>
      </Row>

      {/* 涨停列表 */}
      <Card 
        title={
          <Space>
            <FireOutlined style={{ color: '#f85149' }} />
            <span>今日涨停 Top10</span>
          </Space>
        }
        extra={
          <a href="#" style={{ color: '#58a6ff', fontSize: 13 }}>
            查看全部 →
          </a>
        }
        styles={{ body: { padding: 0 } }}
      >
        <Table
          columns={columns}
          dataSource={limitUpStocks}
          rowKey="stock_code"
          pagination={false}
          size="middle"
          locale={{
            emptyText: (
              <div style={{ padding: 40, textAlign: 'center' }}>
                <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.3 }}>📊</div>
                <Text type="secondary">暂无涨停数据</Text>
              </div>
            )
          }}
        />
      </Card>
    </div>
  )
}
