/**
 * 龙虎榜页面
 * 展示龙虎榜数据和分析
 */
import React, { useState, useEffect } from 'react'
import { Table, Card, DatePicker, Select, Spin, Empty, Tag, Statistic, Row, Col } from 'antd'
import { RiseOutlined, FallOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { Dayjs } from 'dayjs'

const { Option } = Select
const { RangePicker } = DatePicker

interface DragonTigerRecord {
  date: string
  code: string
  name: string
  close_price: float
  change_pct: number
  turnover_rate: number
  net_amount: number
  buy_amount: number
  sell_amount: number
  reason: string
  top_institutions: string[]
}

export const DragonTiger: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<DragonTigerRecord[]>([])
  const [selectedDate, setSelectedDate] = useState<Dayjs>(dayjs())
  const [filterType, setFilterType] = useState<string>('all')

  useEffect(() => {
    fetchDragonTigerData()
  }, [selectedDate, filterType])

  const fetchDragonTigerData = async () => {
    setLoading(true)
    try {
      const response = await fetch(
        `/api/dragon-tiger?date=${selectedDate.format('YYYY-MM-DD')}&type=${filterType}`
      )
      const result = await response.json()
      setData(result.data || [])
    } catch (error) {
      console.error('获取龙虎榜数据失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const columns: ColumnsType<DragonTigerRecord> = [
    {
      title: '股票代码',
      dataIndex: 'code',
      key: 'code',
      width: 100,
      fixed: 'left'
    },
    {
      title: '股票名称',
      dataIndex: 'name',
      key: 'name',
      width: 120,
      fixed: 'left'
    },
    {
      title: '收盘价',
      dataIndex: 'close_price',
      key: 'close_price',
      width: 100,
      render: (value: number) => `¥${value.toFixed(2)}`
    },
    {
      title: '涨跌幅',
      dataIndex: 'change_pct',
      key: 'change_pct',
      width: 100,
      render: (value: number) => (
        <span style={{ color: value >= 0 ? '#f5222d' : '#52c41a' }}>
          {value >= 0 ? <RiseOutlined /> : <FallOutlined />}
          {value.toFixed(2)}%
        </span>
      ),
      sorter: (a, b) => a.change_pct - b.change_pct
    },
    {
      title: '换手率',
      dataIndex: 'turnover_rate',
      key: 'turnover_rate',
      width: 100,
      render: (value: number) => `${value.toFixed(2)}%`,
      sorter: (a, b) => a.turnover_rate - b.turnover_rate
    },
    {
      title: '净买入额',
      dataIndex: 'net_amount',
      key: 'net_amount',
      width: 120,
      render: (value: number) => (
        <span style={{ color: value >= 0 ? '#f5222d' : '#52c41a' }}>
          {(value / 10000).toFixed(2)}万
        </span>
      ),
      sorter: (a, b) => a.net_amount - b.net_amount
    },
    {
      title: '买入额',
      dataIndex: 'buy_amount',
      key: 'buy_amount',
      width: 120,
      render: (value: number) => `${(value / 10000).toFixed(2)}万`
    },
    {
      title: '卖出额',
      dataIndex: 'sell_amount',
      key: 'sell_amount',
      width: 120,
      render: (value: number) => `${(value / 10000).toFixed(2)}万`
    },
    {
      title: '上榜原因',
      dataIndex: 'reason',
      key: 'reason',
      width: 200,
      render: (text: string) => <Tag color="blue">{text}</Tag>
    }
  ]

  return (
    <div className="dragon-tiger-page p-6">
      <h1 className="text-2xl font-bold mb-6">龙虎榜</h1>

      {/* 统计卡片 */}
      <Row gutter={16} className="mb-6">
        <Col span={6}>
          <Card>
            <Statistic
              title="上榜股票数"
              value={data.length}
              suffix="只"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="总买入额"
              value={data.reduce((sum, item) => sum + item.buy_amount, 0) / 100000000}
              precision={2}
              suffix="亿"
              valueStyle={{ color: '#f5222d' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="总卖出额"
              value={data.reduce((sum, item) => sum + item.sell_amount, 0) / 100000000}
              precision={2}
              suffix="亿"
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="净买入额"
              value={data.reduce((sum, item) => sum + item.net_amount, 0) / 100000000}
              precision={2}
              suffix="亿"
              valueStyle={{
                color: data.reduce((sum, item) => sum + item.net_amount, 0) >= 0 ? '#f5222d' : '#52c41a'
              }}
            />
          </Card>
        </Col>
      </Row>

      {/* 筛选器 */}
      <Card className="mb-4">
        <div className="flex gap-4">
          <DatePicker
            value={selectedDate}
            onChange={(date) => date && setSelectedDate(date)}
            format="YYYY-MM-DD"
          />

          <Select
            value={filterType}
            onChange={setFilterType}
            style={{ width: 200 }}
          >
            <Option value="all">全部</Option>
            <Option value="rise_limit">涨停</Option>
            <Option value="fall_limit">跌停</Option>
            <Option value="large_amount">大额交易</Option>
            <Option value="high_turnover">高换手率</Option>
          </Select>
        </div>
      </Card>

      {/* 数据表格 */}
      <Card>
        {loading ? (
          <div className="flex justify-center items-center h-64">
            <Spin size="large" tip="加载中..." />
          </div>
        ) : data.length > 0 ? (
          <Table
            columns={columns}
            dataSource={data}
            rowKey="code"
            scroll={{ x: 1200 }}
            pagination={{
              pageSize: 20,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 条记录`
            }}
          />
        ) : (
          <Empty description="暂无数据" />
        )}
      </Card>
    </div>
  )
}

export default DragonTiger
