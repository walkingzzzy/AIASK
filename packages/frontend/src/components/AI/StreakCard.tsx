import { Card, Progress, Typography, Tooltip } from 'antd'
import { FireOutlined, TrophyOutlined } from '@ant-design/icons'
import { useUserProfileStore } from '@/stores/useUserProfileStore'

const { Text, Title } = Typography

// 连续使用奖励配置
const streakRewards = [
  { days: 3, reward: '解锁AI快捷问答', icon: '💬', unlocked: false },
  { days: 7, reward: '解锁高级技术分析', icon: '📊', unlocked: false },
  { days: 14, reward: '解锁个性化选股', icon: '🎯', unlocked: false },
  { days: 30, reward: '解锁AI投资报告', icon: '📋', unlocked: false },
  { days: 60, reward: '解锁专属投资顾问', icon: '👨‍💼', unlocked: false },
  { days: 100, reward: '解锁VIP特权', icon: '👑', unlocked: false },
]

export default function StreakCard() {
  const { usageStats } = useUserProfileStore()
  const { consecutiveDays, longestStreak } = usageStats

  // 计算下一个里程碑
  const nextMilestone = streakRewards.find(r => r.days > consecutiveDays)
  const daysToNext = nextMilestone ? nextMilestone.days - consecutiveDays : 0
  const progress = nextMilestone 
    ? ((consecutiveDays / nextMilestone.days) * 100) 
    : 100

  // 标记已解锁的奖励
  const rewardsWithStatus = streakRewards.map(r => ({
    ...r,
    unlocked: consecutiveDays >= r.days
  }))

  return (
    <Card 
      size="small"
      style={{ 
        background: 'linear-gradient(135deg, #1a1f2e 0%, #2d3748 100%)',
        border: '1px solid #30363d'
      }}
    >
      {/* 当前连续天数 */}
      <div style={{ textAlign: 'center', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          <FireOutlined style={{ fontSize: 28, color: '#ff6b35' }} />
          <Title level={2} style={{ margin: 0, color: '#e6edf3' }}>
            {consecutiveDays}
          </Title>
          <Text type="secondary">天</Text>
        </div>
        <Text type="secondary">连续使用</Text>
      </div>

      {/* 进度条 */}
      {nextMilestone && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              距离下一个里程碑
            </Text>
            <Text style={{ fontSize: 12, color: '#58a6ff' }}>
              还差 {daysToNext} 天
            </Text>
          </div>
          <Progress 
            percent={progress} 
            showInfo={false}
            strokeColor={{
              '0%': '#ff6b35',
              '100%': '#ffd700',
            }}
            trailColor="#30363d"
          />
          <div style={{ textAlign: 'center', marginTop: 8 }}>
            <Text style={{ color: '#ffd700' }}>
              {nextMilestone.icon} {nextMilestone.reward}
            </Text>
          </div>
        </div>
      )}

      {/* 最长记录 */}
      <div style={{ 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center',
        gap: 8,
        padding: '8px 0',
        borderTop: '1px solid #30363d',
        marginTop: 8
      }}>
        <TrophyOutlined style={{ color: '#ffd700' }} />
        <Text type="secondary">最长记录: </Text>
        <Text strong style={{ color: '#ffd700' }}>{longestStreak} 天</Text>
      </div>

      {/* 奖励列表 */}
      <div style={{ marginTop: 16 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>里程碑奖励</Text>
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(3, 1fr)', 
          gap: 8,
          marginTop: 8 
        }}>
          {rewardsWithStatus.map((reward, index) => (
            <Tooltip key={index} title={reward.reward}>
              <div style={{
                textAlign: 'center',
                padding: '8px 4px',
                borderRadius: 8,
                background: reward.unlocked ? 'rgba(82, 196, 26, 0.1)' : '#21262d',
                border: `1px solid ${reward.unlocked ? '#52c41a' : '#30363d'}`,
                opacity: reward.unlocked ? 1 : 0.6
              }}>
                <div style={{ fontSize: 20 }}>{reward.icon}</div>
                <Text style={{ 
                  fontSize: 11, 
                  color: reward.unlocked ? '#52c41a' : '#8b949e' 
                }}>
                  {reward.days}天
                </Text>
              </div>
            </Tooltip>
          ))}
        </div>
      </div>
    </Card>
  )
}
