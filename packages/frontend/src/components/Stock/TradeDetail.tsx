import React, { useEffect, useRef, useState } from 'react'
import { Spin } from 'antd'

export interface TradeRecord {
  time: string
  price: number
  volume: number
  direction: 'buy' | 'sell' | 'neutral'
  amount?: number
}

export interface TradeDetailProps {
  data?: TradeRecord[]
  loading?: boolean
  preClose?: number
  maxRows?: number
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
  marginBottom: 8,
  paddingBottom: 8,
  borderBottom: `1px solid ${COLORS.border}`,
  color: COLORS.textSecondary,
  fontSize: 11,
}

const rowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  height: 22,
}

const cellStyle: React.CSSProperties = {
  fontFamily: 'monospace',
}

const formatVolume = (volume: number): string => {
  if (volume >= 10000) return (volume / 10000).toFixed(1) + '万'
  return volume.toString()
}

const getDirectionColor = (direction: string): string => {
  if (direction === 'buy') return COLORS.red
  if (direction === 'sell') return COLORS.green
  return COLORS.text
}

const getDirectionText = (direction: string): string => {
  if (direction === 'buy') return 'B'
  if (direction === 'sell') return 'S'
  return '-'
}

const highlightKeyframes = `
@keyframes tradeHighlight {
  0% { background-color: rgba(251, 191, 36, 0.4); }
  100% { background-color: transparent; }
}
`

const TradeDetail: React.FC<TradeDetailProps> = ({ data, loading, preClose = 0, maxRows = 20 }) => {
  const [newIndices, setNewIndices] = useState<Set<number>>(new Set())
  const prevLenRef = useRef(0)

  useEffect(() => {
    if (!data) return
    if (prevLenRef.current > 0 && data.length > prevLenRef.current) {
      const newCount = data.length - prevLenRef.current
      const indices = new Set<number>()
      for (let i = 0; i < Math.min(newCount, maxRows); i++) indices.add(i)
      setNewIndices(indices)
      setTimeout(() => setNewIndices(new Set()), 800)
    }
    prevLenRef.current = data.length
  }, [data, maxRows])

  if (loading) {
    return <div style={{ ...containerStyle, textAlign: 'center', padding: 40 }}><Spin size="small" /></div>
  }
  if (!data || data.length === 0) {
    return <div style={{ ...containerStyle, textAlign: 'center', color: COLORS.textSecondary }}>暂无成交数据</div>
  }

  const displayData = data.slice(0, maxRows)

  return (
    <div style={containerStyle}>
      <style>{highlightKeyframes}</style>
      <div style={headerStyle}>
        <span style={{ width: 50 }}>时间</span>
        <span style={{ flex: 1, textAlign: 'right' }}>价格</span>
        <span style={{ width: 60, textAlign: 'right' }}>数量</span>
        <span style={{ width: 24, textAlign: 'center' }}>方向</span>
      </div>
      <div style={{ maxHeight: 400, overflow: 'auto' }}>
        {displayData.map((trade, index) => {
          const priceColor = preClose > 0
            ? (trade.price > preClose ? COLORS.red : trade.price < preClose ? COLORS.green : COLORS.text)
            : getDirectionColor(trade.direction)
          const isNew = newIndices.has(index)
          return (
            <div key={`${trade.time}-${index}`} style={{ ...rowStyle, animation: isNew ? 'tradeHighlight 0.8s ease-out' : undefined }}>
              <span style={{ ...cellStyle, width: 50, color: COLORS.textSecondary }}>{trade.time}</span>
              <span style={{ ...cellStyle, flex: 1, textAlign: 'right', color: priceColor }}>
                {trade.price.toFixed(2)}
              </span>
              <span style={{ ...cellStyle, width: 60, textAlign: 'right', color: COLORS.textSecondary }}>
                {formatVolume(trade.volume)}
              </span>
              <span style={{
                ...cellStyle,
                width: 24,
                textAlign: 'center',
                color: getDirectionColor(trade.direction),
                fontWeight: 500,
              }}>
                {getDirectionText(trade.direction)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default TradeDetail
