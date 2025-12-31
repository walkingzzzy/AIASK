/**
 * 实时盘口组件
 * 使用WebSocket实时更新盘口数据
 */
import React, { useEffect, useState } from 'react'
import { Spin, Badge } from 'antd'
import { SyncOutlined } from '@ant-design/icons'
import { useOrderBook } from '@/hooks/useRealtimeData'
import { useRealtimeDataStore } from '@/services/realtimeService'
import { api } from '@/services/api'

export interface OrderBookLevel {
  price: number
  volume: number
}

export interface RealtimeOrderBookProps {
  stockCode: string
  stockName?: string
  preClose?: number
  showHeader?: boolean
  levels?: number
  showConnectionStatus?: boolean
}

const COLORS = {
  bg: '#161b22',
  border: '#30363d',
  text: '#e6edf3',
  textSecondary: '#8b949e',
  red: '#f85149',
  green: '#3fb950',
  connected: '#3fb950',
  disconnected: '#f85149',
}

const formatVolume = (volume: number): string => {
  if (volume >= 10000) return (volume / 10000).toFixed(1) + '万'
  return volume.toString()
}

const formatPrice = (price: number): string => price.toFixed(2)

const formatChange = (price: number, preClose: number): string => {
  if (!preClose) return '--'
  const pct = ((price - preClose) / preClose) * 100
  return (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%'
}

const getPriceColor = (price: number, preClose: number): string => {
  if (price > preClose) return COLORS.red
  if (price < preClose) return COLORS.green
  return COLORS.text
}

const RealtimeOrderBook: React.FC<RealtimeOrderBookProps> = ({ 
  stockCode, 
  stockName,
  preClose = 0,
  showHeader = true, 
  levels = 5,
  showConnectionStatus = true
}) => {
  const [loading, setLoading] = useState(true)
  const [localData, setLocalData] = useState<{
    asks: OrderBookLevel[]
    bids: OrderBookLevel[]
  } | null>(null)
  
  // 实时数据
  const realtimeOrderBook = useOrderBook(stockCode)
  const isConnected = useRealtimeDataStore(state => state.isConnected)
  
  // 初始加载
  useEffect(() => {
    const fetchInitialData = async () => {
      if (!stockCode) return
      
      setLoading(true)
      try {
        const res: any = await api.getOrderBook(stockCode)
        if (res.success && res.data) {
          setLocalData({
            asks: res.data.asks || [],
            bids: res.data.bids || []
          })
        }
      } catch (error) {
        console.error('Failed to fetch order book:', error)
        // 数据获取失败，显示空状态
        setLocalData(null)
      } finally {
        setLoading(false)
      }
    }
    
    fetchInitialData()
  }, [stockCode, preClose])
  
  // 合并实时数据
  const data = realtimeOrderBook ? {
    asks: realtimeOrderBook.asks,
    bids: realtimeOrderBook.bids
  } : localData
  
  if (loading) {
    return (
      <div style={{ ...containerStyle, textAlign: 'center', padding: 40 }}>
        <Spin size="small" />
      </div>
    )
  }
  
  if (!data) {
    return (
      <div style={{ ...containerStyle, textAlign: 'center', color: COLORS.textSecondary }}>
        暂无盘口数据
      </div>
    )
  }

  const { asks, bids } = data
  const maxVolume = Math.max(
    ...asks.map(l => l.volume), 
    ...bids.map(l => l.volume), 
    1
  )
  const displayAsks = asks.slice(0, levels).reverse()
  const displayBids = bids.slice(0, levels)

  return (
    <div style={containerStyle}>
      {showHeader && (
        <div style={headerStyle}>
          <span>档位</span>
          <span>价格</span>
          <span>涨跌幅</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            数量
            {showConnectionStatus && (
              <Badge
                status={isConnected ? 'success' : 'error'}
                title={isConnected ? '实时连接' : '离线'}
              />
            )}
          </span>
        </div>
      )}
      
      {/* 卖盘 */}
      {displayAsks.map((level, i) => {
        const idx = levels - i
        const color = getPriceColor(level.price, preClose)
        return (
          <div key={`ask-${idx}`} style={rowStyle}>
            <div
              style={{
                ...barStyle,
                width: `${(level.volume / maxVolume) * 100}%`,
                background: COLORS.red
              }}
            />
            <span style={labelStyle}>卖{idx}</span>
            <span style={{ ...priceStyle, color }}>{formatPrice(level.price)}</span>
            <span style={{ ...changeStyle, color }}>{formatChange(level.price, preClose)}</span>
            <span style={volumeStyle}>{formatVolume(level.volume)}</span>
          </div>
        )
      })}
      
      {/* 分隔线 */}
      <div style={{ height: 1, background: COLORS.border, margin: '6px 0' }} />
      
      {/* 买盘 */}
      {displayBids.map((level, i) => {
        const color = getPriceColor(level.price, preClose)
        return (
          <div key={`bid-${i + 1}`} style={rowStyle}>
            <div
              style={{
                ...barStyle,
                width: `${(level.volume / maxVolume) * 100}%`,
                background: COLORS.green
              }}
            />
            <span style={labelStyle}>买{i + 1}</span>
            <span style={{ ...priceStyle, color }}>{formatPrice(level.price)}</span>
            <span style={{ ...changeStyle, color }}>{formatChange(level.price, preClose)}</span>
            <span style={volumeStyle}>{formatVolume(level.volume)}</span>
          </div>
        )
      })}
      
      {/* 实时更新指示器 */}
      {isConnected && realtimeOrderBook && (
        <div style={updateIndicatorStyle}>
          <SyncOutlined spin style={{ fontSize: 10, marginRight: 4 }} />
          实时更新中
        </div>
      )}
    </div>
  )
}

// 样式
const containerStyle: React.CSSProperties = {
  background: COLORS.bg,
  borderRadius: 8,
  padding: 12,
  fontSize: 12,
}

const headerStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  marginBottom: 8,
  paddingBottom: 8,
  borderBottom: `1px solid ${COLORS.border}`,
  color: COLORS.textSecondary,
  fontSize: 11,
}

const rowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  height: 24,
  position: 'relative',
}

const labelStyle: React.CSSProperties = {
  width: 32,
  color: COLORS.textSecondary,
  flexShrink: 0,
}

const priceStyle: React.CSSProperties = {
  width: 55,
  textAlign: 'right',
  fontFamily: 'monospace',
}

const changeStyle: React.CSSProperties = {
  width: 50,
  textAlign: 'right',
  fontFamily: 'monospace',
  fontSize: 10,
  paddingRight: 8,
}

const volumeStyle: React.CSSProperties = {
  width: 60,
  textAlign: 'right',
  fontFamily: 'monospace',
  color: COLORS.textSecondary,
}

const barStyle: React.CSSProperties = {
  position: 'absolute',
  right: 0,
  top: 2,
  bottom: 2,
  opacity: 0.3,
  borderRadius: 2,
}

const updateIndicatorStyle: React.CSSProperties = {
  marginTop: 8,
  paddingTop: 8,
  borderTop: `1px solid ${COLORS.border}`,
  fontSize: 10,
  color: COLORS.textSecondary,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
}

export default RealtimeOrderBook
