import { Card, Tag, Typography } from 'antd'
import { 
  BulbOutlined, 
  LineChartOutlined, 
  PieChartOutlined,
  LinkOutlined,
  RiseOutlined
} from '@ant-design/icons'
import styles from './InsightCards.module.css'

const { Text, Paragraph } = Typography

export interface Insight {
  id: string
  type: string
  title: string
  content: string
  confidence: number
  stock_codes: string[]
  generated_at: string
}

interface InsightCardProps {
  insight: Insight
  onClick?: (insight: Insight) => void
}

const typeConfig: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  market_view: { icon: <LineChartOutlined />, color: '#1890ff', label: '市场观点' },
  stock_insight: { icon: <BulbOutlined />, color: '#52c41a', label: '个股洞察' },
  sector_analysis: { icon: <PieChartOutlined />, color: '#722ed1', label: '板块分析' },
  correlation: { icon: <LinkOutlined />, color: '#fa8c16', label: '关联分析' },
  trend: { icon: <RiseOutlined />, color: '#13c2c2', label: '趋势分析' },
}

export default function InsightCard({ insight, onClick }: InsightCardProps) {
  const config = typeConfig[insight.type] || typeConfig.market_view
  
  return (
    <Card
      className={styles.card}
      size="small"
      hoverable
      onClick={() => onClick?.(insight)}
    >
      <div className={styles.header}>
        <Tag color={config.color} icon={config.icon}>{config.label}</Tag>
        <Text type="secondary" className={styles.time}>
          {new Date(insight.generated_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
        </Text>
      </div>
      
      <div className={styles.insightTitle}>{insight.title}</div>
      
      <Paragraph 
        className={styles.content}
        ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}
      >
        {insight.content}
      </Paragraph>
      
      {insight.stock_codes.length > 0 && (
        <div className={styles.relatedStocks}>
          <Text type="secondary">相关股票: </Text>
          {insight.stock_codes.slice(0, 5).map(code => (
            <Tag key={code} style={{ marginRight: 4 }}>{code}</Tag>
          ))}
          {insight.stock_codes.length > 5 && (
            <Text type="secondary">+{insight.stock_codes.length - 5}</Text>
          )}
        </div>
      )}
      
      <div className={styles.confidenceBar}>
        <Text type="secondary">置信度 {Math.round(insight.confidence * 100)}%</Text>
        <div className={styles.progressBar}>
          <div 
            className={styles.progressFill} 
            style={{ 
              width: `${insight.confidence * 100}%`,
              backgroundColor: config.color 
            }} 
          />
        </div>
      </div>
    </Card>
  )
}
