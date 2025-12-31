/**
 * 指标卡片组件
 * 用于展示统计指标
 */
import React from 'react'
import { Card, Statistic, Tooltip } from 'antd'
import { ArrowUpOutlined, ArrowDownOutlined, InfoCircleOutlined } from '@ant-design/icons'

interface MetricCardProps {
  title: string
  value: number | string
  prefix?: React.ReactNode
  suffix?: string
  precision?: number
  valueStyle?: React.CSSProperties
  trend?: 'up' | 'down' | 'neutral'
  trendValue?: number
  description?: string
  loading?: boolean
  onClick?: () => void
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  prefix,
  suffix,
  precision = 2,
  valueStyle,
  trend,
  trendValue,
  description,
  loading = false,
  onClick
}) => {
  // 根据趋势确定颜色
  const getTrendColor = () => {
    if (trend === 'up') return '#3f8600'
    if (trend === 'down') return '#cf1322'
    return '#000000'
  }

  // 趋势图标
  const getTrendIcon = () => {
    if (trend === 'up') return <ArrowUpOutlined />
    if (trend === 'down') return <ArrowDownOutlined />
    return null
  }

  return (
    <Card
      hoverable={!!onClick}
      onClick={onClick}
      loading={loading}
      className="metric-card"
    >
      <div className="flex justify-between items-start">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-gray-600">{title}</span>
            {description && (
              <Tooltip title={description}>
                <InfoCircleOutlined className="text-gray-400 text-xs" />
              </Tooltip>
            )}
          </div>

          <Statistic
            value={value}
            precision={typeof value === 'number' ? precision : 0}
            prefix={prefix}
            suffix={suffix}
            valueStyle={{
              color: getTrendColor(),
              fontSize: '24px',
              fontWeight: 600,
              ...valueStyle
            }}
          />

          {trend && trendValue !== undefined && (
            <div className="mt-2 flex items-center gap-1">
              {getTrendIcon()}
              <span
                className="text-sm"
                style={{ color: getTrendColor() }}
              >
                {trendValue > 0 ? '+' : ''}{trendValue.toFixed(2)}%
              </span>
              <span className="text-gray-400 text-xs ml-1">vs 昨日</span>
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}

export default MetricCard
