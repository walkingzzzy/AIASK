/**
 * AI问候组件
 * 显示个性化问候语和AI人格信息
 */
import { useEffect, useState } from 'react'
import { Avatar, Skeleton, Typography } from 'antd'
import { RobotOutlined } from '@ant-design/icons'
import { api } from '@/services/api'
import styles from './AIGreeting.module.css'

const { Text } = Typography

interface AIGreetingProps {
  userId?: string
  showAvatar?: boolean
  compact?: boolean
}

interface GreetingData {
  greeting: string
  ai_name: string
  consecutive_days: number
}

export default function AIGreeting({ 
  userId = 'default',
  showAvatar = true,
  compact = false
}: AIGreetingProps) {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<GreetingData | null>(null)

  useEffect(() => {
    const fetchGreeting = async () => {
      try {
        const res = await api.getAIGreeting(userId)
        if (res.success) {
          setData(res.data)
        }
      } catch (error) {
        console.error('获取问候语失败:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchGreeting()
  }, [userId])

  if (loading) {
    return (
      <div className={styles.container}>
        <Skeleton.Avatar active size={compact ? 32 : 48} />
        <Skeleton.Input active style={{ width: 200, marginLeft: 12 }} />
      </div>
    )
  }

  if (!data) {
    return null
  }

  return (
    <div className={`${styles.container} ${compact ? styles.compact : ''}`}>
      {showAvatar && (
        <Avatar 
          size={compact ? 32 : 48}
          icon={<RobotOutlined />}
          className={styles.avatar}
        />
      )}
      <div className={styles.content}>
        <Text className={styles.greeting}>{data.greeting}</Text>
        {data.consecutive_days > 1 && !compact && (
          <Text type="secondary" className={styles.streak}>
            已连续使用 {data.consecutive_days} 天
          </Text>
        )}
      </div>
    </div>
  )
}
