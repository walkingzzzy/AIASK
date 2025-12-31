import { Card, Tag, Typography } from 'antd'
import {
  WarningOutlined,
  FallOutlined,
  AlertOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  ClockCircleOutlined,
  StockOutlined,
  FileTextOutlined
} from '@ant-design/icons'
import styles from './InsightCards.module.css'

const { Text } = Typography

export interface RiskAlert {
  id: string
  type: string
  stock_code: string
  stock_name: string
  title: string
  description: string
  severity: string
  suggested_action: string
  current_value?: number
  threshold_value?: number
  detected_at: string
  impact?: string
}

interface RiskAlertCardProps {
  alert: RiskAlert
  onClick?: (alert: RiskAlert) => void
}

const typeConfig: Record<string, { icon: React.ReactNode; label: string }> = {
  price_drop: { icon: <FallOutlined />, label: '价格下跌' },
  volume_anomaly: { icon: <AlertOutlined />, label: '量能异常' },
  news_negative: { icon: <WarningOutlined />, label: '负面舆情' },
  technical_breakdown: { icon: <FallOutlined />, label: '技术破位' },
  fund_outflow: { icon: <FallOutlined />, label: '资金流出' },
  position_risk: { icon: <StockOutlined />, label: '持仓风险' },
  financial_risk: { icon: <FileTextOutlined />, label: '财务风险' },
  market_risk: { icon: <AlertOutlined />, label: '市场风险' },
}

const severityConfig: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  critical: { color: '#ff4d4f', icon: <ExclamationCircleOutlined />, label: '严重' },
  warning: { color: '#faad14', icon: <WarningOutlined />, label: '警告' },
  info: { color: '#1890ff', icon: <InfoCircleOutlined />, label: '提示' },
}

export default function RiskAlertCard({ alert, onClick }: RiskAlertCardProps) {
  const typeInfo = typeConfig[alert.type] || typeConfig.price_drop
  const severityInfo = severityConfig[alert.severity] || severityConfig.warning
  
  return (
    <Card
      className={styles.card}
      size="small"
      hoverable
      onClick={() => onClick?.(alert)}
      style={{ borderLeft: `3px solid ${severityInfo.color}` }}
    >
      <div className={styles.header}>
        <div className={styles.stockInfo}>
          <span className={styles.stockName}>{alert.stock_name}</span>
          <Text type="secondary" className={styles.stockCode}>{alert.stock_code}</Text>
        </div>
        <Tag color={severityInfo.color} icon={severityInfo.icon}>{severityInfo.label}</Tag>
      </div>
      
      <div className={styles.title} style={{ color: severityInfo.color }}>
        {typeInfo.icon} {alert.title}
      </div>
      <div className={styles.reason}>{alert.description}</div>
      
      {(alert.current_value !== undefined && alert.threshold_value !== undefined) && (
        <div className={styles.valueInfo}>
          <Text type="secondary">当前值: </Text>
          <span style={{ color: severityInfo.color }}>{alert.current_value?.toFixed(2)}</span>
          <Text type="secondary" style={{ margin: '0 8px' }}>|</Text>
          <Text type="secondary">阈值: </Text>
          <span>{alert.threshold_value?.toFixed(2)}</span>
        </div>
      )}
      
      {alert.impact && (
        <div className={styles.impactInfo}>
          <Text type="secondary">影响: </Text>
          <span>{alert.impact}</span>
        </div>
      )}
      
      <div className={styles.action}>
        <Tag color="blue">{alert.suggested_action}</Tag>
        <span className={styles.timeInfo}>
          <ClockCircleOutlined style={{ marginRight: 4 }} />
          <Text type="secondary">
            {new Date(alert.detected_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
          </Text>
        </span>
      </div>
    </Card>
  )
}
