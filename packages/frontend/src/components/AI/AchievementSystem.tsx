/**
 * 成就系统组件
 * 展示用户解锁的成就和进度
 */
import { useState, useMemo } from 'react'
import { Card, Typography, Progress, Tooltip, Badge, Modal, Tag } from 'antd'
import { 
  TrophyOutlined,
  FireOutlined,
  StarOutlined,
  RocketOutlined,
  CrownOutlined,
  ThunderboltOutlined,
  HeartOutlined,
  BulbOutlined,
  SafetyOutlined,
  TeamOutlined
} from '@ant-design/icons'
import { useUserProfileStore } from '@/stores/useUserProfileStore'
import styles from './AchievementSystem.module.css'

const { Text, Title } = Typography

// 成就类型
type AchievementCategory = 'streak' | 'learning' | 'trading' | 'social' | 'special'

// 成就定义
interface Achievement {
  id: string
  name: string
  description: string
  icon: React.ReactNode
  category: AchievementCategory
  requirement: {
    type: string
    value: number
  }
  reward?: string
  rarity: 'common' | 'rare' | 'epic' | 'legendary'
}

// 成就进度
interface AchievementProgress {
  achievementId: string
  currentValue: number
  unlocked: boolean
  unlockedAt?: string
}

// 成就库
const achievements: Achievement[] = [
  // 连续使用成就
  {
    id: 'streak_3',
    name: '初露锋芒',
    description: '连续使用3天',
    icon: <FireOutlined />,
    category: 'streak',
    requirement: { type: 'consecutive_days', value: 3 },
    reward: '解锁AI快捷问答',
    rarity: 'common'
  },
  {
    id: 'streak_7',
    name: '坚持不懈',
    description: '连续使用7天',
    icon: <FireOutlined />,
    category: 'streak',
    requirement: { type: 'consecutive_days', value: 7 },
    reward: '解锁高级技术分析',
    rarity: 'common'
  },
  {
    id: 'streak_14',
    name: '习惯养成',
    description: '连续使用14天',
    icon: <FireOutlined />,
    category: 'streak',
    requirement: { type: 'consecutive_days', value: 14 },
    reward: '解锁个性化选股',
    rarity: 'rare'
  },
  {
    id: 'streak_30',
    name: '投资达人',
    description: '连续使用30天',
    icon: <CrownOutlined />,
    category: 'streak',
    requirement: { type: 'consecutive_days', value: 30 },
    reward: '解锁AI投资报告',
    rarity: 'epic'
  },
  {
    id: 'streak_100',
    name: '百日传奇',
    description: '连续使用100天',
    icon: <CrownOutlined />,
    category: 'streak',
    requirement: { type: 'consecutive_days', value: 100 },
    reward: '解锁VIP特权',
    rarity: 'legendary'
  },
  
  // 学习成就
  {
    id: 'learn_10',
    name: '求知若渴',
    description: '学习10个投资概念',
    icon: <BulbOutlined />,
    category: 'learning',
    requirement: { type: 'concepts_learned', value: 10 },
    rarity: 'common'
  },
  {
    id: 'learn_50',
    name: '知识渊博',
    description: '学习50个投资概念',
    icon: <BulbOutlined />,
    category: 'learning',
    requirement: { type: 'concepts_learned', value: 50 },
    rarity: 'rare'
  },
  {
    id: 'query_100',
    name: '好奇宝宝',
    description: '向AI提问100次',
    icon: <StarOutlined />,
    category: 'learning',
    requirement: { type: 'total_queries', value: 100 },
    rarity: 'common'
  },
  {
    id: 'query_500',
    name: '问题专家',
    description: '向AI提问500次',
    icon: <StarOutlined />,
    category: 'learning',
    requirement: { type: 'total_queries', value: 500 },
    rarity: 'rare'
  },
  
  // 交易成就
  {
    id: 'first_decision',
    name: '初次尝试',
    description: '记录第一笔交易决策',
    icon: <RocketOutlined />,
    category: 'trading',
    requirement: { type: 'total_decisions', value: 1 },
    rarity: 'common'
  },
  {
    id: 'win_streak_3',
    name: '三连胜',
    description: '连续3次正确决策',
    icon: <ThunderboltOutlined />,
    category: 'trading',
    requirement: { type: 'win_streak', value: 3 },
    rarity: 'rare'
  },
  {
    id: 'accuracy_70',
    name: '精准判断',
    description: '决策准确率达到70%',
    icon: <SafetyOutlined />,
    category: 'trading',
    requirement: { type: 'accuracy', value: 70 },
    rarity: 'epic'
  },
  
  // 社交成就
  {
    id: 'feedback_10',
    name: '积极反馈',
    description: '给AI反馈10次',
    icon: <HeartOutlined />,
    category: 'social',
    requirement: { type: 'feedback_count', value: 10 },
    rarity: 'common'
  },
  {
    id: 'trust_80',
    name: '信任伙伴',
    description: 'AI信任度达到80',
    icon: <TeamOutlined />,
    category: 'social',
    requirement: { type: 'trust_level', value: 80 },
    rarity: 'rare'
  },
  
  // 特殊成就
  {
    id: 'early_bird',
    name: '早起的鸟儿',
    description: '在开盘前查看早报',
    icon: <TrophyOutlined />,
    category: 'special',
    requirement: { type: 'special', value: 1 },
    rarity: 'common'
  },
  {
    id: 'night_owl',
    name: '夜猫子',
    description: '在22点后进行复盘',
    icon: <TrophyOutlined />,
    category: 'special',
    requirement: { type: 'special', value: 1 },
    rarity: 'common'
  }
]

// 稀有度颜色
const rarityColors: Record<string, string> = {
  common: '#8b949e',
  rare: '#58a6ff',
  epic: '#a371f7',
  legendary: '#ffd700'
}

// 稀有度名称
const rarityNames: Record<string, string> = {
  common: '普通',
  rare: '稀有',
  epic: '史诗',
  legendary: '传说'
}

interface AchievementSystemProps {
  compact?: boolean
  showAll?: boolean
}

export default function AchievementSystem({ compact = false, showAll = false }: AchievementSystemProps) {
  const { usageStats, aiRelationship, learningProgress } = useUserProfileStore()
  const [selectedAchievement, setSelectedAchievement] = useState<Achievement | null>(null)
  
  // 计算成就进度
  const progressMap = useMemo(() => {
    const map: Record<string, AchievementProgress> = {}
    
    achievements.forEach(a => {
      let currentValue = 0
      
      switch (a.requirement.type) {
        case 'consecutive_days':
          currentValue = usageStats.consecutiveDays
          break
        case 'total_queries':
          currentValue = usageStats.totalQueries
          break
        case 'concepts_learned':
          currentValue = learningProgress.learnedConcepts.length
          break
        case 'feedback_count':
          currentValue = aiRelationship.feedbackCount
          break
        case 'trust_level':
          currentValue = aiRelationship.trustLevel
          break
        default:
          currentValue = 0
      }
      
      map[a.id] = {
        achievementId: a.id,
        currentValue,
        unlocked: currentValue >= a.requirement.value
      }
    })
    
    return map
  }, [usageStats, aiRelationship, learningProgress])
  
  // 已解锁成就
  const unlockedAchievements = useMemo(() => 
    achievements.filter(a => progressMap[a.id]?.unlocked),
    [progressMap]
  )
  
  // 进行中成就
  const inProgressAchievements = useMemo(() => 
    achievements.filter(a => !progressMap[a.id]?.unlocked)
      .sort((a, b) => {
        const progressA = progressMap[a.id].currentValue / a.requirement.value
        const progressB = progressMap[b.id].currentValue / b.requirement.value
        return progressB - progressA
      }),
    [progressMap]
  )
  
  // 显示的成就
  const displayAchievements = showAll 
    ? achievements 
    : [...unlockedAchievements.slice(0, 3), ...inProgressAchievements.slice(0, 3)]

  if (compact) {
    return (
      <div className={styles.compactContainer}>
        <div className={styles.compactHeader}>
          <TrophyOutlined style={{ color: '#ffd700' }} />
          <Text strong>{unlockedAchievements.length}</Text>
          <Text type="secondary">/ {achievements.length} 成就</Text>
        </div>
        <div className={styles.compactBadges}>
          {unlockedAchievements.slice(0, 5).map(a => (
            <Tooltip key={a.id} title={a.name}>
              <div 
                className={styles.compactBadge}
                style={{ borderColor: rarityColors[a.rarity] }}
              >
                {a.icon}
              </div>
            </Tooltip>
          ))}
          {unlockedAchievements.length > 5 && (
            <div className={styles.compactMore}>
              +{unlockedAchievements.length - 5}
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className={styles.container}>
      {/* 统计头部 */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <TrophyOutlined style={{ fontSize: 24, color: '#ffd700' }} />
          <div>
            <Title level={4} style={{ margin: 0, color: '#e6edf3' }}>
              成就系统
            </Title>
            <Text type="secondary">
              已解锁 {unlockedAchievements.length} / {achievements.length}
            </Text>
          </div>
        </div>
        <Progress 
          type="circle" 
          percent={Math.round((unlockedAchievements.length / achievements.length) * 100)}
          size={60}
          strokeColor="#ffd700"
        />
      </div>

      {/* 成就列表 */}
      <div className={styles.achievementList}>
        {displayAchievements.map(achievement => {
          const progress = progressMap[achievement.id]
          const percent = Math.min(100, (progress.currentValue / achievement.requirement.value) * 100)
          
          return (
            <Card 
              key={achievement.id}
              className={`${styles.achievementCard} ${progress.unlocked ? styles.unlocked : ''}`}
              size="small"
              onClick={() => setSelectedAchievement(achievement)}
            >
              <div className={styles.achievementContent}>
                <Badge 
                  count={progress.unlocked ? '✓' : null}
                  style={{ backgroundColor: '#52c41a' }}
                >
                  <div 
                    className={styles.achievementIcon}
                    style={{ 
                      borderColor: rarityColors[achievement.rarity],
                      opacity: progress.unlocked ? 1 : 0.5
                    }}
                  >
                    {achievement.icon}
                  </div>
                </Badge>
                <div className={styles.achievementInfo}>
                  <div className={styles.achievementName}>
                    <Text strong style={{ color: progress.unlocked ? '#e6edf3' : '#8b949e' }}>
                      {achievement.name}
                    </Text>
                    <Tag 
                      color={rarityColors[achievement.rarity]}
                      style={{ fontSize: 10, marginLeft: 8 }}
                    >
                      {rarityNames[achievement.rarity]}
                    </Tag>
                  </div>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {achievement.description}
                  </Text>
                  {!progress.unlocked && (
                    <Progress 
                      percent={percent} 
                      size="small"
                      showInfo={false}
                      strokeColor={rarityColors[achievement.rarity]}
                      className={styles.achievementProgress}
                    />
                  )}
                </div>
                <div className={styles.achievementValue}>
                  <Text style={{ color: rarityColors[achievement.rarity] }}>
                    {progress.currentValue}/{achievement.requirement.value}
                  </Text>
                </div>
              </div>
            </Card>
          )
        })}
      </div>

      {/* 成就详情弹窗 */}
      <Modal
        open={!!selectedAchievement}
        onCancel={() => setSelectedAchievement(null)}
        footer={null}
        centered
        className={styles.modal}
      >
        {selectedAchievement && (
          <div className={styles.modalContent}>
            <div 
              className={styles.modalIcon}
              style={{ borderColor: rarityColors[selectedAchievement.rarity] }}
            >
              {selectedAchievement.icon}
            </div>
            <Title level={3} style={{ color: '#e6edf3', marginTop: 16 }}>
              {selectedAchievement.name}
            </Title>
            <Tag color={rarityColors[selectedAchievement.rarity]}>
              {rarityNames[selectedAchievement.rarity]}
            </Tag>
            <Text type="secondary" style={{ display: 'block', marginTop: 16 }}>
              {selectedAchievement.description}
            </Text>
            {selectedAchievement.reward && (
              <div className={styles.modalReward}>
                <Text type="secondary">奖励：</Text>
                <Text style={{ color: '#ffd700' }}>{selectedAchievement.reward}</Text>
              </div>
            )}
            <Progress 
              percent={Math.min(100, (progressMap[selectedAchievement.id].currentValue / selectedAchievement.requirement.value) * 100)}
              strokeColor={rarityColors[selectedAchievement.rarity]}
              style={{ marginTop: 16 }}
            />
            <Text type="secondary">
              进度：{progressMap[selectedAchievement.id].currentValue} / {selectedAchievement.requirement.value}
            </Text>
          </div>
        )}
      </Modal>
    </div>
  )
}
