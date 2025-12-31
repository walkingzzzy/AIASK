/**
 * 自选股状态管理 Store
 * 使用 Zustand 进行状态管理
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { isValidStockCode } from '@/config/constants'

// 股票信息接口
export interface Stock {
  code: string
  name: string
  currentPrice?: number
  changePercent?: number
  aiScore?: number
  addedAt: string
  notes?: string
}

// 分组接口
export interface WatchlistGroup {
  id: string
  name: string
  order: number
  stocks: Stock[]
  createdAt: string
  updatedAt: string
}

interface WatchlistState {
  groups: WatchlistGroup[]
  currentGroupId: string | null

  // 分组操作
  addGroup: (name: string) => void
  removeGroup: (groupId: string) => void
  renameGroup: (groupId: string, newName: string) => void
  setCurrentGroup: (groupId: string) => void
  reorderGroups: (groupIds: string[]) => void

  // 股票操作
  addStock: (groupId: string, stock: Omit<Stock, 'addedAt'>) => void
  removeStock: (groupId: string, stockCode: string) => void
  moveStock: (stockCode: string, fromGroupId: string, toGroupId: string) => void
  updateStockNotes: (groupId: string, stockCode: string, notes: string) => void
  updateStockPrice: (groupId: string, stockCode: string, price: number, changePercent: number) => void

  // 批量操作
  clearGroup: (groupId: string) => void
  importStocks: (groupId: string, stocks: Omit<Stock, 'addedAt'>[]) => void

  // 查询
  getGroup: (groupId: string) => WatchlistGroup | undefined
  getAllStocks: () => Stock[]
  searchStocks: (keyword: string) => Stock[]
}

export const useWatchlistStore = create<WatchlistState>()(
  persist(
    (set, get) => ({
      groups: [
        {
          id: 'default',
          name: '默认分组',
          order: 0,
          stocks: [
            { code: '600519', name: '贵州茅台', currentPrice: 1856.00, changePercent: 2.35, addedAt: new Date().toISOString() },
            { code: '002594', name: '比亚迪', currentPrice: 256.80, changePercent: -1.20, addedAt: new Date().toISOString() },
            { code: '300750', name: '宁德时代', currentPrice: 185.50, changePercent: 0.85, addedAt: new Date().toISOString() },
            { code: '601318', name: '中国平安', currentPrice: 45.20, changePercent: 0.45, addedAt: new Date().toISOString() },
            { code: '000858', name: '五粮液', currentPrice: 142.30, changePercent: 1.80, addedAt: new Date().toISOString() },
          ],
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString()
        }
      ],
      currentGroupId: 'default',

      // 添加分组
      addGroup: (name: string) => {
        const newGroup: WatchlistGroup = {
          id: `group_${Date.now()}`,
          name,
          order: get().groups.length,
          stocks: [],
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString()
        }
        set(state => ({
          groups: [...state.groups, newGroup]
        }))
      },

      // 删除分组
      removeGroup: (groupId: string) => {
        if (groupId === 'default') return // 不允许删除默认分组

        set(state => {
          const newGroups = state.groups.filter(g => g.id !== groupId)
          const newCurrentGroupId = state.currentGroupId === groupId
            ? 'default'
            : state.currentGroupId

          return {
            groups: newGroups,
            currentGroupId: newCurrentGroupId
          }
        })
      },

      // 重命名分组
      renameGroup: (groupId: string, newName: string) => {
        set(state => ({
          groups: state.groups.map(g =>
            g.id === groupId
              ? { ...g, name: newName, updatedAt: new Date().toISOString() }
              : g
          )
        }))
      },

      // 设置当前分组
      setCurrentGroup: (groupId: string) => {
        set({ currentGroupId: groupId })
      },

      // 重新排序分组
      reorderGroups: (groupIds: string[]) => {
        set(state => {
          const groupMap = new Map(state.groups.map(g => [g.id, g]))
          const newGroups = groupIds
            .map(id => groupMap.get(id))
            .filter((g): g is WatchlistGroup => g !== undefined)
            .map((g, index) => ({ ...g, order: index }))

          return { groups: newGroups }
        })
      },

      // 添加股票
      addStock: (groupId: string, stock: Omit<Stock, 'addedAt'>) => {
        // 验证股票代码格式
        if (!isValidStockCode(stock.code)) {
          console.warn(`Invalid stock code: ${stock.code}`)
          return
        }
        
        set(state => ({
          groups: state.groups.map(g =>
            g.id === groupId
              ? {
                  ...g,
                  stocks: [
                    ...g.stocks,
                    { ...stock, addedAt: new Date().toISOString() }
                  ],
                  updatedAt: new Date().toISOString()
                }
              : g
          )
        }))
      },

      // 删除股票
      removeStock: (groupId: string, stockCode: string) => {
        set(state => ({
          groups: state.groups.map(g =>
            g.id === groupId
              ? {
                  ...g,
                  stocks: g.stocks.filter(s => s.code !== stockCode),
                  updatedAt: new Date().toISOString()
                }
              : g
          )
        }))
      },

      // 移动股票
      moveStock: (stockCode: string, fromGroupId: string, toGroupId: string) => {
        set(state => {
          const fromGroup = state.groups.find(g => g.id === fromGroupId)
          const stock = fromGroup?.stocks.find(s => s.code === stockCode)

          if (!stock) return state

          return {
            groups: state.groups.map(g => {
              if (g.id === fromGroupId) {
                return {
                  ...g,
                  stocks: g.stocks.filter(s => s.code !== stockCode),
                  updatedAt: new Date().toISOString()
                }
              }
              if (g.id === toGroupId) {
                return {
                  ...g,
                  stocks: [...g.stocks, stock],
                  updatedAt: new Date().toISOString()
                }
              }
              return g
            })
          }
        })
      },

      // 更新股票备注
      updateStockNotes: (groupId: string, stockCode: string, notes: string) => {
        set(state => ({
          groups: state.groups.map(g =>
            g.id === groupId
              ? {
                  ...g,
                  stocks: g.stocks.map(s =>
                    s.code === stockCode ? { ...s, notes } : s
                  ),
                  updatedAt: new Date().toISOString()
                }
              : g
          )
        }))
      },

      // 更新股票价格
      updateStockPrice: (groupId: string, stockCode: string, price: number, changePercent: number) => {
        set(state => ({
          groups: state.groups.map(g =>
            g.id === groupId
              ? {
                  ...g,
                  stocks: g.stocks.map(s =>
                    s.code === stockCode
                      ? { ...s, currentPrice: price, changePercent }
                      : s
                  )
                }
              : g
          )
        }))
      },

      // 清空分组
      clearGroup: (groupId: string) => {
        set(state => ({
          groups: state.groups.map(g =>
            g.id === groupId
              ? { ...g, stocks: [], updatedAt: new Date().toISOString() }
              : g
          )
        }))
      },

      // 导入股票
      importStocks: (groupId: string, stocks: Omit<Stock, 'addedAt'>[]) => {
        set(state => ({
          groups: state.groups.map(g =>
            g.id === groupId
              ? {
                  ...g,
                  stocks: [
                    ...g.stocks,
                    ...stocks.map(s => ({ ...s, addedAt: new Date().toISOString() }))
                  ],
                  updatedAt: new Date().toISOString()
                }
              : g
          )
        }))
      },

      // 获取分组
      getGroup: (groupId: string) => {
        return get().groups.find(g => g.id === groupId)
      },

      // 获取所有股票
      getAllStocks: () => {
        return get().groups.flatMap(g => g.stocks)
      },

      // 搜索股票
      searchStocks: (keyword: string) => {
        const lowerKeyword = keyword.toLowerCase()
        return get().groups
          .flatMap(g => g.stocks)
          .filter(s =>
            s.code.toLowerCase().includes(lowerKeyword) ||
            s.name.toLowerCase().includes(lowerKeyword)
          )
      }
    }),
    {
      name: 'watchlist-storage',
      version: 1
    }
  )
)
