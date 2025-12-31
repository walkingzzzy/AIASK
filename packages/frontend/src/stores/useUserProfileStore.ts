/**
 * 用户画像状态管理 Store
 * 管理用户偏好、使用统计、AI关系等
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { api } from '@/services/api'

// 投资风格
export type InvestmentStyle = 'value' | 'growth' | 'momentum' | 'swing' | 'quant'

// 知识水平
export type KnowledgeLevel = 'beginner' | 'intermediate' | 'advanced'

// AI人格风格
export type AIPersonality = 'professional' | 'friendly' | 'concise'

// 使用统计
export interface UsageStats {
  totalQueries: number
  totalSessions: number
  consecutiveDays: number
  longestStreak: number
  firstActiveDate: string | null
  lastActiveDate: string | null
  activeHours: number[]
}

// AI关系
export interface AIRelationship {
  trustLevel: number
  suggestionFollowRate: number
  totalSuggestions: number
  followedSuggestions: number
  feedbackCount: number
  positiveFeedback: number
}

// 学习进度
export interface LearningProgress {
  learnedConcepts: string[]
  conceptsToLearn: string[]
  quizScores: Record<string, number>
  totalLearningTime: number
}

// 用户画像状态
interface UserProfileState {
  userId: string
  
  // 基本偏好
  investmentStyle: InvestmentStyle
  riskTolerance: number
  focusSectors: string[]
  avoidedSectors: string[]
  preferredMarketCap: string
  
  // 知识维度
  knowledgeLevel: KnowledgeLevel
  learningProgress: LearningProgress
  
  // 决策维度
  decisionSpeed: 'fast' | 'deliberate'
  analysisDepth: 'quick' | 'detailed'
  preferredDataTypes: string[]
  
  // 个性化设置
  nickname: string | null
  aiPersonality: AIPersonality
  notificationEnabled: boolean
  morningBriefEnabled: boolean
  
  // 使用统计
  usageStats: UsageStats
  
  // AI关系
  aiRelationship: AIRelationship
  
  // 加载状态
  isLoading: boolean
  lastSyncTime: string | null
  
  // 操作方法
  loadProfile: () => Promise<void>
  updateProfile: (updates: Partial<UserProfileState>) => Promise<void>
  updatePreferences: (preferences: Partial<{
    investmentStyle: InvestmentStyle
    riskTolerance: number
    focusSectors: string[]
    avoidedSectors: string[]
    knowledgeLevel: KnowledgeLevel
    aiPersonality: AIPersonality
    notificationEnabled: boolean
    morningBriefEnabled: boolean
  }>) => Promise<void>
  
  // 行为追踪
  trackStockView: (stockCode: string, stockName: string) => void
  trackQuery: (query: string, intent: string, stockCodes?: string[]) => void
  trackFeedback: (isPositive: boolean, context?: any) => void
  
  // 统计更新
  incrementQueryCount: () => void
  recordDailyActive: () => void
  
  // 重置
  resetProfile: () => void
}

const defaultUsageStats: UsageStats = {
  totalQueries: 0,
  totalSessions: 0,
  consecutiveDays: 0,
  longestStreak: 0,
  firstActiveDate: null,
  lastActiveDate: null,
  activeHours: []
}

const defaultAIRelationship: AIRelationship = {
  trustLevel: 50,
  suggestionFollowRate: 0,
  totalSuggestions: 0,
  followedSuggestions: 0,
  feedbackCount: 0,
  positiveFeedback: 0
}

const defaultLearningProgress: LearningProgress = {
  learnedConcepts: [],
  conceptsToLearn: [],
  quizScores: {},
  totalLearningTime: 0
}

export const useUserProfileStore = create<UserProfileState>()(
  persist(
    (set, get) => ({
      userId: 'default',
      
      // 默认偏好
      investmentStyle: 'growth',
      riskTolerance: 3,
      focusSectors: ['科技', '消费', '医药'],
      avoidedSectors: [],
      preferredMarketCap: 'all',
      
      knowledgeLevel: 'intermediate',
      learningProgress: defaultLearningProgress,
      
      decisionSpeed: 'deliberate',
      analysisDepth: 'detailed',
      preferredDataTypes: ['technical', 'fundamental'],
      
      nickname: null,
      aiPersonality: 'professional',
      notificationEnabled: true,
      morningBriefEnabled: true,
      
      usageStats: defaultUsageStats,
      aiRelationship: defaultAIRelationship,
      
      isLoading: false,
      lastSyncTime: null,
      
      // 从服务器加载画像
      loadProfile: async () => {
        set({ isLoading: true })
        try {
          const res = await api.getUserProfile() as any
          if (res.success && res.data) {
            const data = res.data
            set({
              investmentStyle: data.investment_style || 'growth',
              riskTolerance: data.risk_tolerance || 3,
              focusSectors: data.focus_sectors || [],
              avoidedSectors: data.avoided_sectors || [],
              preferredMarketCap: data.preferred_market_cap || 'all',
              knowledgeLevel: data.knowledge_level || 'intermediate',
              decisionSpeed: data.decision_speed || 'deliberate',
              analysisDepth: data.analysis_depth || 'detailed',
              preferredDataTypes: data.preferred_data_types || [],
              nickname: data.nickname,
              aiPersonality: data.ai_personality || 'professional',
              notificationEnabled: data.notification_enabled ?? true,
              morningBriefEnabled: data.morning_brief_enabled ?? true,
              usageStats: {
                totalQueries: data.usage_stats?.total_queries || 0,
                totalSessions: data.usage_stats?.total_sessions || 0,
                consecutiveDays: data.usage_stats?.consecutive_days || 0,
                longestStreak: data.usage_stats?.longest_streak || 0,
                firstActiveDate: data.usage_stats?.first_active_date,
                lastActiveDate: data.usage_stats?.last_active_date,
                activeHours: data.usage_stats?.active_hours || []
              },
              aiRelationship: {
                trustLevel: data.ai_relationship?.trust_level || 50,
                suggestionFollowRate: data.ai_relationship?.suggestion_follow_rate || 0,
                totalSuggestions: data.ai_relationship?.total_suggestions || 0,
                followedSuggestions: data.ai_relationship?.followed_suggestions || 0,
                feedbackCount: data.ai_relationship?.feedback_count || 0,
                positiveFeedback: data.ai_relationship?.positive_feedback || 0
              },
              lastSyncTime: new Date().toISOString()
            })
          }
        } catch (error) {
          console.error('加载用户画像失败:', error)
        } finally {
          set({ isLoading: false })
        }
      },
      
      // 更新画像
      updateProfile: async (updates) => {
        set(updates)
        
        // 同步到服务器
        try {
          const apiUpdates: any = {}
          if (updates.investmentStyle) apiUpdates.investment_style = updates.investmentStyle
          if (updates.riskTolerance) apiUpdates.risk_tolerance = updates.riskTolerance
          if (updates.focusSectors) apiUpdates.focus_sectors = updates.focusSectors
          if (updates.avoidedSectors) apiUpdates.avoided_sectors = updates.avoidedSectors
          if (updates.knowledgeLevel) apiUpdates.knowledge_level = updates.knowledgeLevel
          if (updates.aiPersonality) apiUpdates.ai_personality = updates.aiPersonality
          if (updates.nickname !== undefined) apiUpdates.nickname = updates.nickname
          if (updates.notificationEnabled !== undefined) apiUpdates.notification_enabled = updates.notificationEnabled
          if (updates.morningBriefEnabled !== undefined) apiUpdates.morning_brief_enabled = updates.morningBriefEnabled
          
          if (Object.keys(apiUpdates).length > 0) {
            await api.updateUserProfile(apiUpdates)
          }
        } catch (error) {
          console.error('同步用户画像失败:', error)
        }
      },
      
      // 更新偏好设置
      updatePreferences: async (preferences) => {
        const updates: any = {}
        
        if (preferences.investmentStyle) updates.investmentStyle = preferences.investmentStyle
        if (preferences.riskTolerance) updates.riskTolerance = preferences.riskTolerance
        if (preferences.focusSectors) updates.focusSectors = preferences.focusSectors
        if (preferences.avoidedSectors) updates.avoidedSectors = preferences.avoidedSectors
        if (preferences.knowledgeLevel) updates.knowledgeLevel = preferences.knowledgeLevel
        if (preferences.aiPersonality) updates.aiPersonality = preferences.aiPersonality
        if (preferences.notificationEnabled !== undefined) updates.notificationEnabled = preferences.notificationEnabled
        if (preferences.morningBriefEnabled !== undefined) updates.morningBriefEnabled = preferences.morningBriefEnabled
        
        await get().updateProfile(updates)
      },
      
      // 追踪股票浏览
      trackStockView: (stockCode, stockName) => {
        api.trackBehavior({
          event_type: 'stock_view',
          stock_code: stockCode,
          stock_name: stockName
        }).catch(console.error)
      },
      
      // 追踪查询
      trackQuery: (query, intent, stockCodes) => {
        api.trackQuery({ query, intent, stock_codes: stockCodes }).catch(console.error)
        get().incrementQueryCount()
      },
      
      // 追踪反馈
      trackFeedback: (isPositive, context) => {
        api.trackFeedback({
          feedback_type: 'ai_response',
          is_positive: isPositive,
          context
        }).catch(console.error)
        
        // 更新本地AI关系数据
        set(state => ({
          aiRelationship: {
            ...state.aiRelationship,
            feedbackCount: state.aiRelationship.feedbackCount + 1,
            positiveFeedback: isPositive 
              ? state.aiRelationship.positiveFeedback + 1 
              : state.aiRelationship.positiveFeedback,
            trustLevel: isPositive
              ? Math.min(100, state.aiRelationship.trustLevel + 2)
              : Math.max(0, state.aiRelationship.trustLevel - 1)
          }
        }))
      },
      
      // 增加查询计数
      incrementQueryCount: () => {
        set(state => ({
          usageStats: {
            ...state.usageStats,
            totalQueries: state.usageStats.totalQueries + 1
          }
        }))
      },
      
      // 记录每日活跃
      recordDailyActive: () => {
        const today = new Date().toISOString().split('T')[0]
        const state = get()
        
        if (state.usageStats.lastActiveDate !== today) {
          const lastDate = state.usageStats.lastActiveDate
          let consecutiveDays = 1
          
          if (lastDate) {
            const last = new Date(lastDate)
            const now = new Date(today)
            const diffDays = Math.floor((now.getTime() - last.getTime()) / (1000 * 60 * 60 * 24))
            
            if (diffDays === 1) {
              consecutiveDays = state.usageStats.consecutiveDays + 1
            }
          }
          
          set(state => ({
            usageStats: {
              ...state.usageStats,
              lastActiveDate: today,
              firstActiveDate: state.usageStats.firstActiveDate || today,
              consecutiveDays,
              longestStreak: Math.max(state.usageStats.longestStreak, consecutiveDays)
            }
          }))
        }
      },
      
      // 重置画像
      resetProfile: () => {
        set({
          investmentStyle: 'growth',
          riskTolerance: 3,
          focusSectors: ['科技', '消费', '医药'],
          avoidedSectors: [],
          preferredMarketCap: 'all',
          knowledgeLevel: 'intermediate',
          learningProgress: defaultLearningProgress,
          decisionSpeed: 'deliberate',
          analysisDepth: 'detailed',
          preferredDataTypes: ['technical', 'fundamental'],
          nickname: null,
          aiPersonality: 'professional',
          notificationEnabled: true,
          morningBriefEnabled: true,
          usageStats: defaultUsageStats,
          aiRelationship: defaultAIRelationship,
          lastSyncTime: null
        })
      }
    }),
    {
      name: 'user-profile-storage',
      version: 1,
      partialize: (state) => ({
        userId: state.userId,
        investmentStyle: state.investmentStyle,
        riskTolerance: state.riskTolerance,
        focusSectors: state.focusSectors,
        avoidedSectors: state.avoidedSectors,
        knowledgeLevel: state.knowledgeLevel,
        nickname: state.nickname,
        aiPersonality: state.aiPersonality,
        notificationEnabled: state.notificationEnabled,
        morningBriefEnabled: state.morningBriefEnabled,
        usageStats: state.usageStats,
        aiRelationship: state.aiRelationship
      })
    }
  )
)
