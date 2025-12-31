import { Card, Tag, Progress, Typography } from 'antd'
import { RocketOutlined, RiseOutlined, SwapOutlined, ThunderboltOutlined, FundOutlined, LineChartOutlined, ClockCircleOutlined } from '@ant-design/icons'
import styles from './InsightCards.module.css'

const { Text } = Typography

export interface Opportunity {
  id: string
  type: string
  stock_code: string
  stock_name: string
  title: string
  reason: string
  confidence: number
  urgency: string
  expected_return?: number
  detected_at: string
  valid_until?: string
}

interface OpportunityCardProps {
  opportunity: Opportunity
  onClick?: (opportunity: Opportunity) => void
}

const typeConfig: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  buy_signal: { icon: <RiseOutlined />, color: '#52c41a', label: '买入信号' },
  similar_stock: { icon: <SwapOutlined />, color: '#1890ff', label: '相似推荐' },
  sector_rotation: { icon: <RocketOutlined />, color: '#722ed1', label: '板块轮动' },
  breakout: { icon: <ThunderboltOutlined />, color: '#fa8c16', label: '突破形态' },
  oversold: { icon: <RiseOutlined />, color: '#13c2c2', label: '超卖反弹' },
  fund_inflow: { icon: <FundOutlined />, color: '#eb2f96', label: '资金流入' },
  technical_breakout: { icon: <LineChartOutlined />, color: '#faad14', label: '技术突破' },
  fundamental_improve: { icon: <RiseOutlined />, color: '#52c41a', label: '基本面改善' },
}

const urgencyColors: Record<string, string> = {
  high: '#ff4d4f',
  medium: '#faad14',
  low: '#52c41a',
}

export default function OpportunityCard({ opportunity, onClick }: OpportunityCardProps) {
  const config = typeConfig[opportunity.type] || typeConfig.buy_signal
  
  return (
    <Card
      className={styles.card}
      size="small"
      hoverable
      onClick={() => onClick?.(opportunity)}
    >
      <div className={styles.header}>
        <div className={styles.stockInfo}>
          <span className={styles.stockName}>{opportunity.stock_name}</span>
          <Text type="secondary" className={styles.stockCode}>{opportunity.stock_code}</Text>
        </div>
        <Tag color={config.color} icon={config.icon}>{config.label}</Tag>
      </div>
      
      <div className={styles.title}>{opportunity.title}</div>
      <div className={styles.reason}>{opportunity.reason}</div>
      
      <div className={styles.footer}>
        <div className={styles.confidence}>
          <Text type="secondary">置信度</Text>
          <Progress
            percent={Math.round(opportunity.confidence * 100)}
            size="small"
            strokeColor={config.color}
            showInfo={false}
            style={{ width: 60 }}
          />
          <span>{Math.round(opportunity.confidence * 100)}%</span>
        </div>
        
        {opportunity.expected_return && (
          <div className={styles.expectedReturn}>
            <Text type="secondary">预期收益</Text>
            <span style={{ color: '#52c41a' }}>+{(opportunity.expected_return * 100).toFixed(1)}%</span>
          </div>
        )}
        
        <Tag
          color={urgencyColors[opportunity.urgency]}
          style={{ marginLeft: 'auto' }}
        >
          {opportunity.urgency === 'high' ? '紧急' : opportunity.urgency === 'medium' ? '中等' : '一般'}
        </Tag>
      </div>
      
      <div className={styles.timeInfo}>
        <ClockCircleOutlined style={{ marginRight: 4 }} />
        <Text type="secondary">
          {new Date(opportunity.detected_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
          {opportunity.valid_until && ` · 有效至 ${new Date(opportunity.valid_until).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })}`}
        </Text>
      </div>
    </Card>
  )
}
