import { useState, useEffect } from 'react'
import { Card, Table, Tag, Row, Col, Statistic, Spin, Input, Button } from 'antd'
import { FireOutlined, SearchOutlined } from '@ant-design/icons'
import { api } from '@/services/api'

interface LimitUpStock {
  stock_code: string
  stock_name: string
  continuous_days: number
  limit_up_reason?: string
  seal_amount?: number
  turnover_rate?: number
}

interface LimitUpStats {
  total: number
  first_limit: number
  continuous: number
  max_continuous: number
}

export default function LimitUp() {
  const [loading, setLoading] = useState(true)
  const [stocks, setStocks] = useState<LimitUpStock[]>([])
  const [stats, setStats] = useState<LimitUpStats | null>(null)
  const [searchCode, setSearchCode] = useState('')
  const [predicting, setPredicting] = useState(false)
  const [prediction, setPrediction] = useState<any>(null)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [stocksRes, statsRes] = await Promise.all([
        api.getDailyLimitUp(),
        api.getLimitUpStatistics()
      ])
      if (stocksRes.success) setStocks(stocksRes.data)
      if (statsRes.success) setStats(statsRes.data)
    } catch (error) {
      console.error('加载失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const handlePredict = async () => {
    if (!searchCode.trim()) return
    setPredicting(true)
    try {
      const res = await api.predictContinuation(searchCode)
      if (res.success) {
        setPrediction(res.data)
      }
    } catch (error) {
      console.error('预测失败:', error)
    } finally {
      setPredicting(false)
    }
  }

  const columns = [
    {
      title: '股票',
      dataIndex: 'stock_name',
      key: 'stock_name',
      render: (text: string, record: LimitUpStock) => (
        <span>
          <span className="font-medium">{text}</span>
          <span className="text-gray-400 text-xs ml-1">({record.stock_code})</span>
        </span>
      )
    },
    {
      title: '连板',
      dataIndex: 'continuous_days',
      key: 'continuous_days',
      sorter: (a: LimitUpStock, b: LimitUpStock) => a.continuous_days - b.continuous_days,
      render: (days: number) => (
        <Tag color={days >= 5 ? 'red' : days >= 3 ? 'orange' : days >= 2 ? 'gold' : 'default'}>
          {days === 1 ? '首板' : `${days}连板`}
        </Tag>
      )
    },
    {
      title: '涨停原因',
      dataIndex: 'limit_up_reason',
      key: 'limit_up_reason',
      ellipsis: true,
      render: (text: string) => text || '-'
    },
    {
      title: '封单额(亿)',
      dataIndex: 'seal_amount',
      key: 'seal_amount',
      render: (val: number) => val ? val.toFixed(2) : '-'
    },
    {
      title: '换手率',
      dataIndex: 'turnover_rate',
      key: 'turnover_rate',
      render: (val: number) => val ? `${val.toFixed(2)}%` : '-'
    }
  ]

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* 统计卡片 */}
      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic
              title="今日涨停"
              value={stats?.total || 0}
              suffix="只"
              valueStyle={{ color: '#ef4444' }}
              prefix={<FireOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="首板" value={stats?.first_limit || 0} suffix="只" />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic 
              title="连板" 
              value={stats?.continuous || 0} 
              suffix="只"
              valueStyle={{ color: '#f97316' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic 
              title="最高连板" 
              value={stats?.max_continuous || 0} 
              suffix="板"
              valueStyle={{ color: '#dc2626' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 连板预测 */}
      <Card title="连板预测">
        <div className="flex gap-4 mb-4">
          <Input
            placeholder="输入股票代码"
            value={searchCode}
            onChange={(e) => setSearchCode(e.target.value)}
            style={{ width: 200 }}
          />
          <Button 
            type="primary" 
            icon={<SearchOutlined />} 
            onClick={handlePredict}
            loading={predicting}
          >
            预测连板
          </Button>
        </div>
        {prediction && (
          <div className="bg-gray-800 p-4 rounded">
            <Row gutter={16}>
              <Col span={8}>
                <Statistic 
                  title="连板概率" 
                  value={(prediction.continuation_prob * 100).toFixed(1)} 
                  suffix="%" 
                  valueStyle={{ color: prediction.continuation_prob > 0.5 ? '#ef4444' : '#6b7280' }}
                />
              </Col>
              <Col span={8}>
                <Statistic title="风险等级" value={prediction.risk_level || '中'} />
              </Col>
              <Col span={8}>
                <Statistic title="建议" value={prediction.suggestion || '观望'} />
              </Col>
            </Row>
          </div>
        )}
      </Card>

      {/* 涨停列表 */}
      <Card title="今日涨停列表">
        <Table
          columns={columns}
          dataSource={stocks}
          rowKey="stock_code"
          pagination={{ pageSize: 15 }}
          size="small"
        />
      </Card>
    </div>
  )
}
