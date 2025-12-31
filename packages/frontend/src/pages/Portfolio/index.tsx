/**
 * 组合管理页面
 */
import { useState, useEffect } from 'react'
import { Card, Row, Col, Statistic, Table, Button, Modal, Form, Input, InputNumber, message, Tag, Space } from 'antd'
import { PlusOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons'
import { api } from '@/services/api'

interface Position {
  stock_code: string
  stock_name: string
  quantity: number
  cost_price: number
  current_price?: number
  market_value?: number
  profit_loss?: number
  profit_loss_pct?: number
}

interface PortfolioSummary {
  total_market_value: number
  total_cost: number
  total_profit_loss: number
  total_profit_loss_pct: number
  position_count: number
}

interface RiskAnalysis {
  risk_level: string
  suggestions: string[]
  concentration_risk?: number
  volatility_risk?: number
}

export default function Portfolio() {
  const [loading, setLoading] = useState(true)
  const [positions, setPositions] = useState<Position[]>([])
  const [summary, setSummary] = useState<PortfolioSummary | null>(null)
  const [riskAnalysis, setRiskAnalysis] = useState<RiskAnalysis | null>(null)
  const [addModalVisible, setAddModalVisible] = useState(false)
  const [form] = Form.useForm()

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [positionsRes, summaryRes, riskRes] = await Promise.all([
        api.getPortfolioPositions(),
        api.getPortfolioSummary(),
        api.getPortfolioRisk()
      ])

      if (positionsRes.success) setPositions(positionsRes.data)
      if (summaryRes.success) setSummary(summaryRes.data)
      if (riskRes.success) setRiskAnalysis(riskRes.data)
    } catch (error) {
      console.error('加载失败:', error)
      message.error('加载组合数据失败')
    } finally {
      setLoading(false)
    }
  }

  const handleAddPosition = async () => {
    try {
      const values = await form.validateFields()
      const res = await api.addPosition(values)

      if (res.success) {
        message.success('添加持仓成功')
        setAddModalVisible(false)
        form.resetFields()
        loadData()
      } else {
        message.error('添加失败')
      }
    } catch (error) {
      console.error('添加失败:', error)
      message.error('添加持仓失败')
    }
  }

  const handleRemovePosition = (stockCode: string) => {
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除这个持仓吗？',
      onOk: async () => {
        try {
          const res = await api.removePosition(stockCode)
          if (res.success) {
            message.success('删除成功')
            loadData()
          }
        } catch (error) {
          message.error('删除失败')
        }
      }
    })
  }

  const columns = [
    {
      title: '股票',
      dataIndex: 'stock_name',
      key: 'stock_name',
      render: (text: string, record: Position) => (
        <span>
          <span className="font-medium">{text}</span>
          <span className="text-gray-400 text-xs ml-1">({record.stock_code})</span>
        </span>
      )
    },
    {
      title: '持仓数量',
      dataIndex: 'quantity',
      key: 'quantity',
      render: (val: number) => val.toLocaleString()
    },
    {
      title: '成本价',
      dataIndex: 'cost_price',
      key: 'cost_price',
      render: (val: number) => `¥${val.toFixed(2)}`
    },
    {
      title: '现价',
      dataIndex: 'current_price',
      key: 'current_price',
      render: (val: number) => val ? `¥${val.toFixed(2)}` : '-'
    },
    {
      title: '市值',
      dataIndex: 'market_value',
      key: 'market_value',
      render: (val: number) => val ? `¥${val.toLocaleString()}` : '-'
    },
    {
      title: '盈亏',
      dataIndex: 'profit_loss',
      key: 'profit_loss',
      render: (val: number, record: Position) => {
        if (!val) return '-'
        const color = val >= 0 ? 'text-red-500' : 'text-green-500'
        return (
          <span className={color}>
            {val >= 0 ? '+' : ''}{val.toFixed(2)}
            {record.profit_loss_pct && (
              <span className="ml-1">
                ({record.profit_loss_pct >= 0 ? '+' : ''}{record.profit_loss_pct.toFixed(2)}%)
              </span>
            )}
          </span>
        )
      }
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: Position) => (
        <Button
          type="link"
          danger
          icon={<DeleteOutlined />}
          onClick={() => handleRemovePosition(record.stock_code)}
        >
          删除
        </Button>
      )
    }
  ]

  const getRiskLevelColor = (level: string) => {
    switch (level) {
      case '低': return 'green'
      case '中': return 'orange'
      case '高': return 'red'
      default: return 'default'
    }
  }

  return (
    <div className="space-y-4">
      {/* 组合概览 */}
      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic
              title="总市值"
              value={summary?.total_market_value || 0}
              precision={2}
              prefix="¥"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="总成本"
              value={summary?.total_cost || 0}
              precision={2}
              prefix="¥"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="总盈亏"
              value={summary?.total_profit_loss || 0}
              precision={2}
              prefix={summary?.total_profit_loss && summary.total_profit_loss >= 0 ? '+¥' : '-¥'}
              valueStyle={{
                color: summary?.total_profit_loss && summary.total_profit_loss >= 0 ? '#ef4444' : '#22c55e'
              }}
              suffix={
                summary?.total_profit_loss_pct && (
                  <span className="text-sm">
                    ({summary.total_profit_loss_pct >= 0 ? '+' : ''}{summary.total_profit_loss_pct.toFixed(2)}%)
                  </span>
                )
              }
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="持仓数量"
              value={summary?.position_count || 0}
              suffix="只"
            />
          </Card>
        </Col>
      </Row>

      {/* 风险分析 */}
      {riskAnalysis && (
        <Card title="风险分析">
          <Row gutter={16}>
            <Col span={8}>
              <div className="text-center">
                <div className="text-gray-400 mb-2">风险等级</div>
                <Tag color={getRiskLevelColor(riskAnalysis.risk_level)} className="text-lg px-4 py-1">
                  {riskAnalysis.risk_level}
                </Tag>
              </div>
            </Col>
            <Col span={16}>
              <div>
                <div className="text-gray-400 mb-2">风险提示</div>
                <ul className="list-disc list-inside space-y-1">
                  {riskAnalysis.suggestions.map((suggestion, index) => (
                    <li key={index} className="text-sm">{suggestion}</li>
                  ))}
                </ul>
              </div>
            </Col>
          </Row>
        </Card>
      )}

      {/* 持仓列表 */}
      <Card
        title="持仓明细"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadData} loading={loading}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddModalVisible(true)}>
              添加持仓
            </Button>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={positions}
          rowKey="stock_code"
          loading={loading}
          pagination={false}
        />
      </Card>

      {/* 添加持仓弹窗 */}
      <Modal
        title="添加持仓"
        open={addModalVisible}
        onOk={handleAddPosition}
        onCancel={() => {
          setAddModalVisible(false)
          form.resetFields()
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="stock_code"
            label="股票代码"
            rules={[{ required: true, message: '请输入股票代码' }]}
          >
            <Input placeholder="如: 600519" />
          </Form.Item>
          <Form.Item
            name="stock_name"
            label="股票名称"
            rules={[{ required: true, message: '请输入股票名称' }]}
          >
            <Input placeholder="如: 贵州茅台" />
          </Form.Item>
          <Form.Item
            name="quantity"
            label="持仓数量"
            rules={[{ required: true, message: '请输入持仓数量' }]}
          >
            <InputNumber min={100} step={100} style={{ width: '100%' }} placeholder="100的整数倍" />
          </Form.Item>
          <Form.Item
            name="cost_price"
            label="成本价"
            rules={[{ required: true, message: '请输入成本价' }]}
          >
            <InputNumber min={0} precision={2} style={{ width: '100%' }} placeholder="如: 1800.50" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
