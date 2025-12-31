/**
 * 回测指标面板组件
 */
import React from 'react'
import { Card, Row, Col, Statistic, Divider } from 'antd'
import {
  RiseOutlined,
  FallOutlined,
  TrophyOutlined,
  ThunderboltOutlined,
  LineChartOutlined,
  PercentageOutlined
} from '@ant-design/icons'
import type { BacktestMetrics } from './types'

interface MetricsPanelProps {
  metrics: BacktestMetrics
}

export const MetricsPanel: React.FC<MetricsPanelProps> = ({ metrics }) => {
  return (
    <div className="space-y-4">
      {/* 收益指标 */}
      <Card title="收益指标" size="small">
        <Row gutter={16}>
          <Col span={6}>
            <Statistic
              title="总收益率"
              value={metrics.totalReturn * 100}
              precision={2}
              suffix="%"
              valueStyle={{ color: metrics.totalReturn >= 0 ? '#cf1322' : '#3f8600' }}
              prefix={metrics.totalReturn >= 0 ? <RiseOutlined /> : <FallOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="年化收益率"
              value={metrics.annualReturn * 100}
              precision={2}
              suffix="%"
              valueStyle={{ color: metrics.annualReturn >= 0 ? '#cf1322' : '#3f8600' }}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="夏普比率"
              value={metrics.sharpeRatio}
              precision={2}
              prefix={<TrophyOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="盈亏比"
              value={metrics.profitFactor}
              precision={2}
              prefix={<ThunderboltOutlined />}
            />
          </Col>
        </Row>
      </Card>

      {/* 风险指标 */}
      <Card title="风险指标" size="small">
        <Row gutter={16}>
          <Col span={6}>
            <Statistic
              title="最大回撤"
              value={Math.abs(metrics.maxDrawdown) * 100}
              precision={2}
              suffix="%"
              valueStyle={{ color: '#cf1322' }}
              prefix={<FallOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="回撤持续天数"
              value={metrics.maxDrawdownDuration}
              suffix="天"
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="波动率"
              value={metrics.volatility * 100}
              precision={2}
              suffix="%"
              prefix={<LineChartOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="胜率"
              value={metrics.winRate * 100}
              precision={2}
              suffix="%"
              prefix={<PercentageOutlined />}
            />
          </Col>
        </Row>
      </Card>

      {/* 交易统计 */}
      <Card title="交易统计" size="small">
        <Row gutter={16}>
          <Col span={6}>
            <Statistic
              title="总交易次数"
              value={metrics.totalTrades}
              suffix="笔"
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="盈利交易"
              value={metrics.winningTrades}
              suffix="笔"
              valueStyle={{ color: '#3f8600' }}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="亏损交易"
              value={metrics.losingTrades}
              suffix="笔"
              valueStyle={{ color: '#cf1322' }}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="平均盈利"
              value={metrics.avgProfit}
              precision={2}
              prefix="¥"
              valueStyle={{ color: '#3f8600' }}
            />
          </Col>
        </Row>
        <Divider style={{ margin: '12px 0' }} />
        <Row gutter={16}>
          <Col span={6}>
            <Statistic
              title="平均亏损"
              value={Math.abs(metrics.avgLoss)}
              precision={2}
              prefix="¥"
              valueStyle={{ color: '#cf1322' }}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="最大单笔盈利"
              value={metrics.maxProfit}
              precision={2}
              prefix="¥"
              valueStyle={{ color: '#3f8600' }}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="最大单笔亏损"
              value={Math.abs(metrics.maxLoss)}
              precision={2}
              prefix="¥"
              valueStyle={{ color: '#cf1322' }}
            />
          </Col>
        </Row>
      </Card>
    </div>
  )
}
