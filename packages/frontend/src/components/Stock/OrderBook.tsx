import React from 'react'
import { Spin } from 'antd'

export interface OrderBookLevel {
  price: number
  volume: number
}

export interface OrderBookData {
  stockCode: string
  stockName: string
  currentPrice: number
  preClose: number
  asks: OrderBookLevel[]
  bids: OrderBookLevel[]
  timestamp?: string
}

export interface OrderBookProps {
  data?: OrderBookData
  loading?: boolean
  showHeader?: boolean
  levels?: number
}

const COLORS = {
  bg: '#161b22',
  border: '#30363d',
  text: '#e6edf3',
  textSecondary: '#8b949e',
  red: '#f85149',
  green: '#3fb950',
}

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

const OrderBook: React.FC<OrderBookProps> = ({ data, loading, showHeader = true, levels = 5 }) => {
  if (loading) {
    return <div style={{ ...containerStyle, textAlign: 'center', padding: 40 }}><Spin size="small" /></div>
  }
  if (!data) {
    return <div style={{ ...containerStyle, textAlign: 'center', color: COLORS.textSecondary }}>暂无盘口数据</div>
  }

  const { asks, bids, preClose } = data
  const maxVolume = Math.max(...[...asks, ...bids].map(l => l.volume), 1)
  const displayAsks = asks.slice(0, levels).reverse()
  const displayBids = bids.slice(0, levels)

  return (
    <div style={containerStyle}>
      {showHeader && <div style={headerStyle}><span>档位</span><span>价格</span><span>涨跌幅</span><span>数量</span></div>}
      {displayAsks.map((level, i) => {
        const idx = levels - i
        const color = getPriceColor(level.price, preClose)
        return (
          <div key={`ask-${idx}`} style={rowStyle}>
            <div style={{ ...barStyle, width: `${(level.volume / maxVolume) * 100}%`, background: COLORS.red }} />
            <span style={labelStyle}>卖{idx}</span>
            <span style={{ ...priceStyle, color }}>{formatPrice(level.price)}</span>
            <span style={{ ...changeStyle, color }}>{formatChange(level.price, preClose)}</span>
            <span style={volumeStyle}>{formatVolume(level.volume)}</span>
          </div>
        )
      })}
      <div style={{ height: 1, background: COLORS.border, margin: '6px 0' }} />
      {displayBids.map((level, i) => {
        const color = getPriceColor(level.price, preClose)
        return (
          <div key={`bid-${i + 1}`} style={rowStyle}>
            <div style={{ ...barStyle, width: `${(level.volume / maxVolume) * 100}%`, background: COLORS.green }} />
            <span style={labelStyle}>买{i + 1}</span>
            <span style={{ ...priceStyle, color }}>{formatPrice(level.price)}</span>
            <span style={{ ...changeStyle, color }}>{formatChange(level.price, preClose)}</span>
            <span style={volumeStyle}>{formatVolume(level.volume)}</span>
          </div>
        )
      })}
    </div>
  )
}

export default OrderBook
