/**
 * 情绪消息组件
 * 根据市场和用户状态显示情绪化消息
 */
import { useEffect, useState } from 'react'
import { Card, Typography, Space, Tag } from 'antd'
import { 
  HeartOutlined, 
  SmileOutlined, 
  MehOutlined,
  FrownOutlined,
  TrophyOutlined,
  FireOutlined,
  WarningOutlined
} from '@ant-design/icons'
import { api, EmotionContextData } from '@/services/api'
import styles from './EmotionMessage.module.css'

const { Paragraph } = Typography

interface EmotionMessageProps {
  context: EmotionContextData
  userId?: string
  showTriggers?: boolean
}

interface EmotionResponse {
  triggers: string[]
  responses: {
    comfort?: string
    encouragement?: string
    warning?: string
    celebration?: string
  }
}

const triggerIcons: Record<string, React.ReactNode> = {
  'market_crash': <FrownOutlined style={{ color: '#f85149' }} />,
  'big_loss': <FrownOutlined style={{ color: '#f85149' }} />,
  'loss_streak': <MehOutlined style={{ color: '#d29922' }} />,
  'market_surge': <SmileOutlined style={{ color: '#3fb950' }} />,
  'big_profit': <TrophyOutlined style={{ color: '#3fb950' }} />,
  'win_streak': <FireOutlined style={{ color: '#f0883e' }} />,
  'consecutive_login': <HeartOutlined style={{ color: '#f778ba' }} />,
  'learning_milestone': <TrophyOutlined style={{ color: '#a371f7' }} />,
  'comeback': <SmileOutlined style={{ color: '#58a6ff' }} />,
  'overtrading': <WarningOutlined style={{ color: '#d29922' }} />,
  'chasing_high': <WarningOutlined style={{ color: '#f85149' }} />,
}

const triggerLabels: Record<string, string> = {
  'market_crash': '市场大跌',
  'big_loss': '较大亏损',
  'loss_streak': '连续亏损',
  'market_surge': '市场大涨',
  'big_profit': '盈利丰厚',
  'win_streak': '连续盈利',
  'consecutive_login': '连续登录',
  'learning_milestone': '学习里程碑',
  'comeback': '久别重逢',
  'overtrading': '频繁交易',
  'chasing_high': '追高风险',
}

export default function EmotionMessage({ 
  context, 
  userId = 'default',
  showTriggers = false
}: EmotionMessageProps) {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<EmotionResponse | null>(null)

  useEffect(() => {
    const fetchEmotion = async () => {
      try {
        const res: any = await api.getEmotionResponse(context, userId)
        if (res.success) {
          setData(res.data)
        }
      } catch (error) {
        console.error('获取情绪响应失败:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchEmotion()
  }, [context, userId])

  if (loading || !data || data.triggers.length === 0) {
    return null
  }

  const { triggers, responses } = data
  const messages = Object.values(responses).filter(Boolean)

  if (messages.length === 0) {
    return null
  }

  return (
    <Card className={styles.card} size="small">
      {showTriggers && triggers.length > 0 && (
        <Space wrap className={styles.triggers}>
          {triggers.map(trigger => (
            <Tag 
              key={trigger} 
              icon={triggerIcons[trigger]}
              className={styles.tag}
            >
              {triggerLabels[trigger] || trigger}
            </Tag>
          ))}
        </Space>
      )}
      
      <div className={styles.messages}>
        {responses.comfort && (
          <Paragraph className={styles.comfort}>
            <HeartOutlined className={styles.icon} />
            {responses.comfort}
          </Paragraph>
        )}
        
        {responses.encouragement && (
          <Paragraph className={styles.encouragement}>
            <SmileOutlined className={styles.icon} />
            {responses.encouragement}
          </Paragraph>
        )}
        
        {responses.celebration && (
          <Paragraph className={styles.celebration}>
            <TrophyOutlined className={styles.icon} />
            {responses.celebration}
          </Paragraph>
        )}
        
        {responses.warning && (
          <Paragraph className={styles.warning}>
            <WarningOutlined className={styles.icon} />
            {responses.warning}
          </Paragraph>
        )}
      </div>
    </Card>
  )
}
