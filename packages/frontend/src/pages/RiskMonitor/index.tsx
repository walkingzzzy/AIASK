/**
 * 风险监控页面
 */
import { useState, useEffect } from 'react'
import { Card, Row, Col, Table, Tag, Alert, Button, Modal, Form, InputNumber, message, Progress, Statistic } from 'antd'
import { WarningOutlined, CheckCircleOutlined, ReloadOutlined, SettingOutlined } from '@ant-design/icons'
import { api } from '@/services/api'

interface RiskAlert {
  alert_type: string
  severity: string
  message: string
  stock_code?: string
  stock_name?: string
  timestamp: string
}

interface RiskMetrics {
  portfolio_volatility: number
  max_drawdown: number
  concentration_risk: number
  beta: number
  var_95: number
  sharpe_ratio: number
}

interface RiskThresholds {
  max_position_pct: number
  max_sector_pct: number
  max_drawdown_pct: number
  min_liquidity: number
  max_volatility: number
}

export default function RiskMonitor() {
  const [loading, setLoading] = useState(true)
  const [alerts, setAlerts] = useState<RiskAlert[]>([])
  const [metrics, setMetrics] = useState<RiskMetrics | null>(null)
  const [thresholds, setThresholds] = useState<RiskThresholds | null>(null)
  const [settingsVisible, setSettingsVisible] = useState(false)
  const [form] = Form.useForm()

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [alertsRes, metricsRes, thresholdsRes] = await Promise.all([
        api.checkRisk(),
        api.getRiskMetrics(),
        api.getRiskThresholds()
      ])

      if (alertsRes.success) setAlerts(alertsRes.data.alerts || [])
      if (metricsRes.success) setMetrics(metricsRes.data)
      if (thresholdsRes.success) {
        setThresholds(thresholdsRes.data)
        form.setFieldsValue(thresholdsRes.data)
      }
    } catch (error) {
      console.error('加载失败:', error)
      message.error('加载风险数据失败')
    } finally {
      setLoading(false)
    }
  }

  const handleUpdateThresholds = async () => {
    try {
      const values = await form.validateFields()

      // 更新每个阈值
      for (const [key, value] of Object.entries(values)) {
        await api.updateRiskThreshold(key, value as number)
      }

      message.success('阈值更新成功')
      setSettingsVisible(false)
      loadData()
    } catch (error) {
      console.error('更新失败:', error)
      message.error('更新阈值失败')
    }
  }

  const getSeverityColor = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'high':
      case '高':
        return 'red'
      case 'medium':
      case '中':
        return 'orange'
      case 'low':
      case '低':
        return 'yellow'
      default:
        return 'default'
    }
  }

  const getSeverityIcon = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'high':
      case '高':
        return <WarningOutlined style={{ color: '#ef4444' }} />
      case 'medium':
      case '中':
        return <WarningOutlined style={{ color: '#f97316' }} />
      default:
        return <CheckCircleOutlined style={{ color: '#22c55e' }} />
    }
  }

  const alertColumns = [
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      render: (severity: string) => (
        <Tag color={getSeverityColor(severity)} icon={getSeverityIcon(severity)}>
          {severity}
        </Tag>
      )
    },
    {
      title: '类型',
      dataIndex: 'alert_type',
      key: 'alert_type',
      width: 120
    },
    {
      title: '股票',
      key: 'stock',
      width: 150,
      render: (_: any, record: RiskAlert) => {
        if (record.stock_code && record.stock_name) {
          return (
            <span>
              {record.stock_name}
              <span className="text-gray-400 text-xs ml-1">({record.stock_code})</span>
            </span>
          )
        }
        return '-'
      }
    },
    {
      title: '预警信息',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true
    },
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 180,
      render: (time: string) => new Date(time).toLocaleString('zh-CN')
    }
  ]

  const getRiskLevel = (value: number, thresholdKey: string) => {
    if (!thresholds) return 'default'

    const threshold = thresholds[thresholdKey as keyof RiskThresholds]
    if (!threshold) return 'default'

    if (thresholdKey === 'max_drawdown_pct' || thresholdKey === 'max_volatility') {
      // 越大越危险
      if (value >= threshold * 0.9) return 'red'
      if (value >= threshold * 0.7) return 'orange'
      return 'green'
    } else {
      // 越小越危险
      if (value <= threshold * 1.1) return 'red'
      if (value <= threshold * 1.3) return 'orange'
      return 'green'
    }
  }

  return (
    <div className="space-y-4">
      {/* 风险概览 */}
      <Card
        title="风险概览"
        extra={
          <div className="space-x-2">
            <Button icon={<ReloadOutlined />} onClick={loadData} loading={loading}>
              刷新
            </Button>
            <Button icon={<SettingOutlined />} onClick={() => setSettingsVisible(true)}>
              阈值设置
            </Button>
          </div>
        }
      >
        {alerts.length > 0 ? (
          <Alert
            message={`发现 ${alerts.length} 个风险预警`}
            description="请及时关注并采取相应措施"
            type="warning"
            showIcon
            icon={<WarningOutlined />}
          />
        ) : (
          <Alert
            message="当前无风险预警"
            description="组合风险在可控范围内"
            type="success"
            showIcon
            icon={<CheckCircleOutlined />}
          />
        )}
      </Card>

      {/* 风险指标 */}
      {metrics && (
        <Card title="风险指标">
          <Row gutter={[16, 16]}>
            <Col span={8}>
              <Card>
                <Statistic
                  title="组合波动率"
                  value={metrics.portfolio_volatility * 100}
                  precision={2}
                  suffix="%"
                  valueStyle={{ color: getRiskLevel(metrics.portfolio_volatility, 'max_volatility') }}
                />
                <Progress
                  percent={metrics.portfolio_volatility * 100}
                  showInfo={false}
                  strokeColor={getRiskLevel(metrics.portfolio_volatility, 'max_volatility')}
                />
              </Card>
            </Col>
            <Col span={8}>
              <Card>
                <Statistic
                  title="最大回撤"
                  value={Math.abs(metrics.max_drawdown) * 100}
                  precision={2}
                  suffix="%"
                  valueStyle={{ color: getRiskLevel(Math.abs(metrics.max_drawdown), 'max_drawdown_pct') }}
                />
                <Progress
                  percent={Math.abs(metrics.max_drawdown) * 100}
                  showInfo={false}
                  strokeColor={getRiskLevel(Math.abs(metrics.max_drawdown), 'max_drawdown_pct')}
                />
              </Card>
            </Col>
            <Col span={8}>
              <Card>
                <Statistic
                  title="集中度风险"
                  value={metrics.concentration_risk * 100}
                  precision={2}
                  suffix="%"
                />
                <Progress
                  percent={metrics.concentration_risk * 100}
                  showInfo={false}
                  strokeColor={getRiskLevel(metrics.concentration_risk, 'max_position_pct')}
                />
              </Card>
            </Col>
            <Col span={8}>
              <Card>
                <Statistic
                  title="Beta系数"
                  value={metrics.beta}
                  precision={2}
                  valueStyle={{ color: metrics.beta > 1 ? '#ef4444' : '#22c55e' }}
                />
              </Card>
            </Col>
            <Col span={8}>
              <Card>
                <Statistic
                  title="VaR (95%)"
                  value={Math.abs(metrics.var_95) * 100}
                  precision={2}
                  suffix="%"
                />
              </Card>
            </Col>
            <Col span={8}>
              <Card>
                <Statistic
                  title="夏普比率"
                  value={metrics.sharpe_ratio}
                  precision={2}
                  valueStyle={{ color: metrics.sharpe_ratio > 1 ? '#22c55e' : '#ef4444' }}
                />
              </Card>
            </Col>
          </Row>
        </Card>
      )}

      {/* 风险预警列表 */}
      <Card title={`风险预警 (${alerts.length})`}>
        <Table
          columns={alertColumns}
          dataSource={alerts}
          rowKey={(record, index) => `${record.alert_type}-${index}`}
          loading={loading}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      {/* 阈值设置弹窗 */}
      <Modal
        title="风险阈值设置"
        open={settingsVisible}
        onOk={handleUpdateThresholds}
        onCancel={() => setSettingsVisible(false)}
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="max_position_pct"
            label="单只股票最大仓位 (%)"
            rules={[{ required: true, message: '请输入最大仓位' }]}
          >
            <InputNumber min={1} max={100} precision={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="max_sector_pct"
            label="单个行业最大仓位 (%)"
            rules={[{ required: true, message: '请输入最大行业仓位' }]}
          >
            <InputNumber min={1} max={100} precision={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="max_drawdown_pct"
            label="最大回撤阈值 (%)"
            rules={[{ required: true, message: '请输入最大回撤' }]}
          >
            <InputNumber min={1} max={100} precision={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="min_liquidity"
            label="最小流动性要求 (万元)"
            rules={[{ required: true, message: '请输入最小流动性' }]}
          >
            <InputNumber min={0} precision={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="max_volatility"
            label="最大波动率阈值 (%)"
            rules={[{ required: true, message: '请输入最大波动率' }]}
          >
            <InputNumber min={1} max={100} precision={1} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
