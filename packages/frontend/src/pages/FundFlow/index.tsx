import { useState, useEffect } from 'react'
import { Card, Tabs, Table, Row, Col, Statistic, Spin, Tag } from 'antd'
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons'
import { api } from '@/services/api'

export default function FundFlow() {
  const [loading, setLoading] = useState(true)
  const [marginData, setMarginData] = useState<any>(null)
  const [blockTradeData, setBlockTradeData] = useState<any>(null)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [marginRes, blockRes] = await Promise.all([
        api.getMarketMargin(),
        api.getDailyBlockTrade()
      ])
      if (marginRes.success) setMarginData(marginRes.data)
      if (blockRes.success) setBlockTradeData(blockRes.data)
    } catch (error) {
      console.error('加载失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const blockTradeColumns = [
    {
      title: '股票',
      dataIndex: 'stock_name',
      key: 'stock_name',
      render: (text: string, record: any) => (
        <span>{text} <span className="text-gray-400 text-xs">({record.stock_code})</span></span>
      )
    },
    {
      title: '成交额(亿)',
      dataIndex: 'amount',
      key: 'amount',
      render: (val: number) => (val / 10000).toFixed(2)
    },
    {
      title: '溢价率',
      dataIndex: 'premium_rate',
      key: 'premium_rate',
      render: (val: number) => (
        <span className={val > 0 ? 'text-red-500' : val < 0 ? 'text-green-500' : ''}>
          {val > 0 ? '+' : ''}{val?.toFixed(2)}%
        </span>
      )
    },
    {
      title: '信号',
      key: 'signal',
      render: (_: any, record: any) => (
        <Tag color={record.premium_rate > 0 ? 'red' : record.premium_rate < -5 ? 'green' : 'default'}>
          {record.premium_rate > 0 ? '利好' : record.premium_rate < -5 ? '利空' : '中性'}
        </Tag>
      )
    }
  ]

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Spin size="large" />
      </div>
    )
  }

  const tabItems = [
    {
      key: 'margin',
      label: '融资融券',
      children: (
        <div className="space-y-4">
          <Row gutter={16}>
            <Col span={6}>
              <Card>
                <Statistic
                  title="融资余额"
                  value={marginData?.financing_balance || 0}
                  precision={2}
                  suffix="亿"
                  valueStyle={{ color: marginData?.financing_5d_change > 0 ? '#ef4444' : '#22c55e' }}
                  prefix={marginData?.financing_5d_change > 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="融券余额"
                  value={marginData?.securities_balance || 0}
                  precision={2}
                  suffix="亿"
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="5日变化"
                  value={marginData?.financing_5d_change || 0}
                  precision={2}
                  suffix="亿"
                  valueStyle={{ color: marginData?.financing_5d_change > 0 ? '#ef4444' : '#22c55e' }}
                  prefix={marginData?.financing_5d_change > 0 ? '+' : ''}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="市场情绪"
                  value={marginData?.market_sentiment || '未知'}
                />
              </Card>
            </Col>
          </Row>
          <Card title="两融分析">
            <p className="text-gray-400">
              当前融资余额 {marginData?.financing_balance?.toFixed(2)} 亿元，
              {marginData?.financing_5d_change > 0 ? '近5日增加' : '近5日减少'} 
              {Math.abs(marginData?.financing_5d_change || 0).toFixed(2)} 亿元。
              市场情绪：{marginData?.market_sentiment || '未知'}
            </p>
          </Card>
        </div>
      )
    },
    {
      key: 'block',
      label: '大宗交易',
      children: (
        <div className="space-y-4">
          <Row gutter={16}>
            <Col span={6}>
              <Card>
                <Statistic title="成交笔数" value={blockTradeData?.total_count || 0} suffix="笔" />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic title="成交总额" value={blockTradeData?.total_amount || 0} precision={2} suffix="亿" />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic title="溢价成交" value={blockTradeData?.premium_count || 0} suffix="笔" valueStyle={{ color: '#ef4444' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic 
                  title="平均溢价率" 
                  value={blockTradeData?.avg_premium_rate || 0} 
                  precision={2} 
                  suffix="%" 
                  valueStyle={{ color: (blockTradeData?.avg_premium_rate || 0) > 0 ? '#ef4444' : '#22c55e' }}
                />
              </Card>
            </Col>
          </Row>
          <Card title="成交额Top5">
            <Table
              columns={blockTradeColumns}
              dataSource={blockTradeData?.top_trades || []}
              rowKey="stock_code"
              pagination={false}
              size="small"
            />
          </Card>
        </div>
      )
    }
  ]

  return (
    <Card>
      <Tabs items={tabItems} />
    </Card>
  )
}
