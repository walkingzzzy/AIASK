import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { api, AIServiceStatus, LLMStatus, EmbeddingStatus } from '../services/api'

interface AppSettings {
  apiUrl: string
  darkMode: boolean
  autoRefresh: boolean
  refreshInterval: number
}

// AI状态
interface AIStatus {
  isLoading: boolean
  isConfigured: boolean
  overallStatus: string
  llm: LLMStatus | null
  embedding: EmbeddingStatus | null
  recommendations: string[]
  lastChecked: string | null
  error: string | null
}

interface AppState {
  // 设置
  settings: AppSettings
  updateSettings: (settings: Partial<AppSettings>) => void
  
  // 最近搜索
  recentStocks: string[]
  addRecentStock: (code: string) => void
  clearRecentStocks: () => void
  
  // 收藏股票
  favoriteStocks: string[]
  addFavorite: (code: string) => void
  removeFavorite: (code: string) => void
  isFavorite: (code: string) => boolean
  
  // AI状态
  aiStatus: AIStatus
  fetchAIStatus: () => Promise<void>
  clearAIStatusError: () => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      // 默认设置
      settings: {
        apiUrl: 'http://127.0.0.1:8000',
        darkMode: true,
        autoRefresh: true,
        refreshInterval: 30000,
      },
      
      updateSettings: (newSettings) =>
        set((state) => ({
          settings: { ...state.settings, ...newSettings },
        })),
      
      // 最近搜索
      recentStocks: [],
      addRecentStock: (code) =>
        set((state) => ({
          recentStocks: [code, ...state.recentStocks.filter((c) => c !== code)].slice(0, 10),
        })),
      clearRecentStocks: () => set({ recentStocks: [] }),
      
      // 收藏股票
      favoriteStocks: [],
      addFavorite: (code) =>
        set((state) => ({
          favoriteStocks: [...state.favoriteStocks, code],
        })),
      removeFavorite: (code) =>
        set((state) => ({
          favoriteStocks: state.favoriteStocks.filter((c) => c !== code),
        })),
      isFavorite: (code) => get().favoriteStocks.includes(code),
      
      // AI状态
      aiStatus: {
        isLoading: false,
        isConfigured: false,
        overallStatus: '未知',
        llm: null,
        embedding: null,
        recommendations: [],
        lastChecked: null,
        error: null,
      },
      
      fetchAIStatus: async () => {
        set((state) => ({
          aiStatus: { ...state.aiStatus, isLoading: true, error: null }
        }))
        
        try {
          const response = await api.getAIStatus() as any
          if (response.success && response.data) {
            const data = response.data as AIServiceStatus
            set({
              aiStatus: {
                isLoading: false,
                isConfigured: data.llm?.is_configured && data.embedding?.is_configured,
                overallStatus: data.overall_status,
                llm: data.llm,
                embedding: data.embedding,
                recommendations: data.recommendations || [],
                lastChecked: new Date().toISOString(),
                error: null,
              }
            })
          } else {
            throw new Error('获取AI状态失败')
          }
        } catch (error: any) {
          set((state) => ({
            aiStatus: {
              ...state.aiStatus,
              isLoading: false,
              error: error.message || '获取AI状态失败',
              lastChecked: new Date().toISOString(),
            }
          }))
        }
      },
      
      clearAIStatusError: () =>
        set((state) => ({
          aiStatus: { ...state.aiStatus, error: null }
        })),
    }),
    {
      name: 'a-stock-app-storage',
      // 只持久化部分状态，AI状态不需要持久化
      partialize: (state) => ({
        settings: state.settings,
        recentStocks: state.recentStocks,
        favoriteStocks: state.favoriteStocks,
      }),
    }
  )
)

export default useAppStore
