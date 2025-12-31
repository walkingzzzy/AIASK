/**
 * 选股雷达页面
 */
import { useState, useEffect } from 'react'
import { Card, Row, Col, Table, Button, Form, InputNumber, message, Tag, Tabs, Space, Typography } from 'antd'
import { 
  SearchOutlined, 
  ThunderboltOutlined, 
  StarOutlined,
  TrophyOutlined,
  RiseOutlined,
  DollarOutlined,
} from '@ant-design/icons'
import { api } from '@/services/api'

const { Text, Title } = Typography

interface ScreenedStock {
  stock_code: string
  stock_name: string
  ai_score?: number
  pe_ratio?: number
  pb_ratio?: number
  roe?: number
  revenue_growth?: number
  profit_growth?: number
  dividend_yield?: number
  market_cap?: number
}

interface Strategy {
  name: string
  description: string
  conditions: any[]
}

// 策略卡片图标映射
const strategyIcons: Record<string, React.ReactNode> = {
  'value_investing': <DollarOutlined style={{ fontSize: 24, color: '#3fb950' }} />,
  'growth_stocks': <RiseOutlined style={{ fontSize: 24, color: '#f85149' }} />,
  'high_ai_score': <TrophyOutlined style={{ fontSize: 24, color: '#d29922' }} />,
}

// 策略卡片颜色映射
const strategyColors: Record<string, string> = {
  'value_investing': '#3fb950',
  'growth_stocks': '#f85149',
  'high_ai_score': '#d29922',
}

export default function StockScreener() {
  const [loading, setLoading] = useState(false)
  const [strategies, setStrategies] = useState<Record<string, Strategy>>({})
  const [results, setResults] = useState<ScreenedStock[]>([])
  const [form] = Form.useForm()

  useEffect(() => {
    loadStrategies()
  }, [])

  const loadStrategies = async () => {
    try {
      const res = await api.getScreeningStrategies()
      if (res.success) {
        setStrategies(res.data)
      }
    } catch (error) {
      console.error('加载策略失败:', error)
    }
  }

  const handleStrategyScreen = async (strategyName: string) => {
    setLoading(true)
    try {
      const res = await api.screenStocks({ strategy_name: strategyName, limit: 50 })
      if (res.success) {
        setResults(res.data)
        message.success(`筛选完成，找到 ${res.data.length} 只股票`)
      }
    } catch (error) {
      console.error('筛选失败:', error)
      message.error('筛选股票失败')
    } finally {
      setLoading(false)
    }
  }

  const handleCustomScreen = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)

      const conditions: any[] = []

      if (values.ai_score_min) {
        conditions.push({ field: 'ai_score', operator: '>=', value: values.ai_score_min })
      }
      if (values.pe_max) {
        conditions.push({ field: 'pe_ratio', operator: '<=', value: values.pe_max })
      }
      if (values.pb_max) {
        conditions.push({ field: 'pb_ratio', operator: '<=', value: values.pb_max })
      }
      if (values.roe_min) {
        conditions.push({ field: 'roe', operator: '>=', value: values.roe_min })
      }
      if (values.revenue_growth_min) {
        conditions.push({ field: 'revenue_growth', operator: '>=', value: values.revenue_growth_min })
      }
      if (values.dividend_yield_min) {
        conditions.push({ field: 'dividend_yield', operator: '>=', value: values.dividend_yield_min })
      }

      const res = await api.screenStocks({ custom_conditions: conditions, limit: 50 })
      if (res.success) {
        setResults(res.data)
        message.success(`筛选完成，找到 ${res.data.length} 只股票`)
      }
    } catch (error) {
      console.error('筛选失败:', error)
      message.error('筛选股票失败')
    } finally {
      setLoading(false)
    }
  }

  const columns = [
    {
      title: '股票',
      key: 'stock',
      fixed: 'left' as const,
      width: 150,
      render: (_: any, record: ScreenedStock) => (
        <div>
          <Text strong style={{ color: '#e6edf3' }}>{record.stock_name}</Text>
          <Text type="secondary" style={{ fontSize: 12, marginLeft: 6 }}>
            {record.stock_code}
          </Text>
        </div>
      )
    },
    {
      title: 'AI评分',
      dataIndex: 'ai_score',
      key: 'ai_score',
      width: 100,
      sorter: (a: ScreenedStock, b: ScreenedStock) => (a.ai_score || 0) - (b.ai_score || 0),
      render: (score: number) => {
        if (!score) return <Text type="secondary">-</Text>
        const color = score >= 8 ? '#f85149' : score >= 6 ? '#d29922' : '#58a6ff'
        return (
          <Tag 
            style={{ 
              background: `${color}20`, 
              color, 
              border: 'none',
              fontWeight: 600,
            }}
          >
            {score.toFixed(1)}
          </Tag>
        )
      }
    },
    {
      title: '市盈率',
      dataIndex: 'pe_ratio',
      key: 'pe_ratio',
      width: 100,
      sorter: (a: ScreenedStock, b: ScreenedStock) => (a.pe_ratio || 0) - (b.pe_ratio || 0),
      render: (val: number) => val ? <span className="font-mono-num">{val.toFixed(2)}</span> : '-'
    },
    {
      title: '市净率',
      dataIndex: 'pb_ratio',
      key: 'pb_ratio',
      width: 100,
      sorter: (a: ScreenedStock, b: ScreenedStock) => (a.pb_ratio || 0) - (b.pb_ratio || 0),
      render: (val: number) => val ? <span className="font-mono-num">{val.toFixed(2)}</span> : '-'
    },
    {
      title: 'ROE',
      dataIndex: 'roe',
      key: 'roe',
      width: 100,
      sorter: (a: ScreenedStock, b: ScreenedStock) => (a.roe || 0) - (b.roe || 0),
      render: (val: number) => val ? <span className="font-mono-num">{(val * 100).toFixed(2)}%</span> : '-'
    },
    {
      title: '营收增长',
      dataIndex: 'revenue_growth',
      key: 'revenue_growth',
      width: 100,
      sorter: (a: ScreenedStock, b: ScreenedStock) => (a.revenue_growth || 0) - (b.revenue_growth || 0),
      render: (val: number) => {
        if (!val) return '-'
        const color = val > 0 ? '#f85149' : '#3fb950'
        return <span className="font-mono-num" style={{ color }}>{(val * 100).toFixed(2)}%</span>
      }
    },
    {
      title: '利润增长',
      dataIndex: 'profit_growth',
      key: 'profit_growth',
      width: 100,
      sorter: (a: ScreenedStock, b: ScreenedStock) => (a.profit_growth || 0) - (b.profit_growth || 0),
      render: (val: number) => {
        if (!val) return '-'
        const color = val > 0 ? '#f85149' : '#3fb950'
        return <span className="font-mono-num" style={{ color }}>{(val * 100).toFixed(2)}%</span>
      }
    },
    {
      title: '股息率',
      dataIndex: 'dividend_yield',
      key: 'dividend_yield',
      width: 100,
      sorter: (a: ScreenedStock, b: ScreenedStock) => (a.dividend_yield || 0) - (b.dividend_yield || 0),
      render: (val: number) => val ? <span className="font-mono-num">{(val * 100).toFixed(2)}%</span> : '-'
    },
    {
      title: '市值(亿)',
      dataIndex: 'market_cap',
      key: 'market_cap',
      width: 120,
      sorter: (a: ScreenedStock, b: ScreenedStock) => (a.market_cap || 0) - (b.market_cap || 0),
      render: (val: number) => val ? <span className="font-mono-num">{(val / 100000000).toFixed(2)}</span> : '-'
    }
  ]

  // Tab items配置
  const tabItems = [
    {
      key: '1',
      label: '预设策略',
      children: (
        <Row gutter={16}>
          {Object.entries(strategies).map(([key, strategy]) => (
            <Col xs={24} sm={12} lg={8} key={key}>
              <Card
                hoverable
                onClick={() => handleStrategyScreen(key)}
                className="strategy-card"
                style={{ marginBottom: 16 }}
                styles={{ body: { padding: 20 } }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
                  <div style={{
                    width: 48,
                    height: 48,
                    borderRadius: 12,
                    background: `${strategyColors[key] || '#58a6ff'}15`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}>
                    {strategyIcons[key] || <ThunderboltOutlined style={{ fontSize: 24, color: '#58a6ff' }} />}
                  </div>
                  <div>
                    <Title level={5} style={{ margin: 0, marginBottom: 4 }}>{strategy.name}</Title>
                    <Text type="secondary" style={{ fontSize: 13 }}>{strategy.description}</Text>
                  </div>
                </div>
              </Card>
            </Col>
          ))}
          {Object.keys(strategies).length === 0 && (
            <Col span={24}>
              <div style={{ textAlign: 'center', padding: 40 }}>
                <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.3 }}>📊</div>
                <Text type="secondary">暂无预设策略</Text>
              </div>
            </Col>
          )}
        </Row>
      ),
    },
    {
      key: '2',
      label: '自定义筛选',
      children: (
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col xs={24} sm={12} lg={8}>
              <Form.Item name="ai_score_min" label="AI评分 (最低)">
                <InputNumber min={0} max={10} step={0.1} style={{ width: '100%' }} placeholder="如: 7.0" size="large" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} lg={8}>
              <Form.Item name="pe_max" label="市盈率 (最高)">
                <InputNumber min={0} step={1} style={{ width: '100%' }} placeholder="如: 30" size="large" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} lg={8}>
              <Form.Item name="pb_max" label="市净率 (最高)">
                <InputNumber min={0} step={0.1} style={{ width: '100%' }} placeholder="如: 5" size="large" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col xs={24} sm={12} lg={8}>
              <Form.Item name="roe_min" label="ROE (最低 %)">
                <InputNumber min={0} max={100} step={1} style={{ width: '100%' }} placeholder="如: 15" size="large" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} lg={8}>
              <Form.Item name="revenue_growth_min" label="营收增长 (最低 %)">
                <InputNumber min={-100} max={1000} step={1} style={{ width: '100%' }} placeholder="如: 20" size="large" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} lg={8}>
              <Form.Item name="dividend_yield_min" label="股息率 (最低 %)">
                <InputNumber min={0} max={100} step={0.1} style={{ width: '100%' }} placeholder="如: 3" size="large" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item>
            <Button
              type="primary"
              icon={<SearchOutlined />}
              onClick={handleCustomScreen}
              loading={loading}
              size="large"
            >
              开始筛选
            </Button>
          </Form.Item>
        </Form>
      ),
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 统计概览 */}
      <Row gutter={16}>
        <Col xs={24} sm={12} lg={6}>
          <Card styles={{ body: { padding: '20px 24px' } }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ color: '#8b949e', fontSize: 13, marginBottom: 8 }}>预设策略</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                  <span className="font-mono-num" style={{ fontSize: 28, fontWeight: 600, color: '#58a6ff' }}>
                    {Object.keys(strategies).length}
                  </span>
                  <span style={{ fontSize: 14, color: '#8b949e' }}>个</span>
                </div>
              </div>
              <ThunderboltOutlined style={{ fontSize: 24, color: '#58a6ff', opacity: 0.8 }} />
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card styles={{ body: { padding: '20px 24px' } }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ color: '#8b949e', fontSize: 13, marginBottom: 8 }}>筛选结果</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                  <span className="font-mono-num" style={{ fontSize: 28, fontWeight: 600, color: '#d29922' }}>
                    {results.length}
                  </span>
                  <span style={{ fontSize: 14, color: '#8b949e' }}>只</span>
                </div>
              </div>
              <StarOutlined style={{ fontSize: 24, color: '#d29922', opacity: 0.8 }} />
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card styles={{ body: { padding: '16px 24px' } }}>
            <div style={{ color: '#8b949e', fontSize: 13, marginBottom: 12 }}>快速筛选</div>
            <Space wrap>
              {Object.entries(strategies).map(([key, strategy]) => (
                <Button
                  key={key}
                  onClick={() => handleStrategyScreen(key)}
                  loading={loading}
                  style={{
                    borderColor: strategyColors[key] || '#30363d',
                    color: strategyColors[key] || '#e6edf3',
                  }}
                >
                  {strategy.name}
                </Button>
              ))}
              {Object.keys(strategies).length === 0 && (
                <Text type="secondary">暂无可用策略</Text>
              )}
            </Space>
          </Card>
        </Col>
      </Row>

      {/* 筛选条件 */}
      <Card>
        <Tabs defaultActiveKey="1" items={tabItems} />
      </Card>

      {/* 筛选结果 */}
      {results.length > 0 && (
        <Card 
          title={
            <Space>
              <StarOutlined style={{ color: '#d29922' }} />
              <span>筛选结果</span>
              <Tag color="blue">{results.length} 只</Tag>
            </Space>
          }
          styles={{ body: { padding: 0 } }}
        >
          <Table
            columns={columns}
            dataSource={results}
            rowKey="stock_code"
            loading={loading}
            pagination={{ pageSize: 20 }}
            scroll={{ x: 1200 }}
            size="middle"
          />
        </Card>
      )}
    </div>
  )
}
