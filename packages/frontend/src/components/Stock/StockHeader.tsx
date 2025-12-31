import React from 'react'
import { Spin } from 'antd'

export interface StockHeaderData {
  stockCode: string
  stockName: string
  currentPrice: number
  preClose: number
  open: number
  high: number
  low: number
  volume: number
  amount: number
  changePercent: number
  change: number
  turnoverRate?: number
  pe?: number
  pb?: number
  marketCap?: number
}

export interface StockHeaderProps {
  data?: StockHeaderData
  loading?: boolean
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
  padding: 16,
}

const priceRowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'baseline',
  marginBottom: 12,
}

const gridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(4, 1fr)',
  gap: '8px 16px',
  fontSize: 12,
}

const labelStyle: React.CSSProperties = {
  color: COLORS.textSecondary,
  marginRight: 4,
}

const formatNumber = (num: number, decimals = 2): string => {
  if (num >= 100000000) return (num / 100000000).toFixed(2) + '亿'
  if (num >= 10000) return (num / 10000).toFixed(2) + '万'
  return num.toFixed(decimals)
}

const StockHeader: React.FC<StockHeaderProps> = ({ data, loading }) => {
  if (loading) {
    return <div style={{ ...containerStyle, textAlign: 'center', padding: 40 }}><Spin size="small" /></div>
  }
  if (!data) {
    return <div style={{ ...containerStyle, textAlign: 'center', color: COLORS.textSecondary }}>请选择股票</div>
  }

  const priceColor = data.changePercent >= 0 ? COLORS.red : COLORS.green
  const sign = data.changePercent >= 0 ? '+' : ''

  return (
    <div style={containerStyle}>
      <div style={{ marginBottom: 8 }}>
        <span style={{ fontSize: 16, fontWeight: 600, color: COLORS.text }}>{data.stockName}</span>
        <span style={{ marginLeft: 8, color: COLORS.textSecondary, fontSize: 12 }}>{data.stockCode}</span>
      </div>
      <div style={priceRowStyle}>
        <span style={{ fontSize: 28, fontWeight: 600, color: priceColor, fontFamily: 'monospace' }}>
          {data.currentPrice.toFixed(2)}
        </span>
        <span style={{ marginLeft: 12, fontSize: 14, color: priceColor }}>
          {sign}{data.change.toFixed(2)} ({sign}{data.changePercent.toFixed(2)}%)
        </span>
      </div>
      <div style={gridStyle}>
        <div><span style={labelStyle}>今开</span><span style={{ color: data.open >= data.preClose ? COLORS.red : COLORS.green }}>{data.open.toFixed(2)}</span></div>
        <div><span style={labelStyle}>最高</span><span style={{ color: COLORS.red }}>{data.high.toFixed(2)}</span></div>
        <div><span style={labelStyle}>最低</span><span style={{ color: COLORS.green }}>{data.low.toFixed(2)}</span></div>
        <div><span style={labelStyle}>昨收</span><span style={{ color: COLORS.text }}>{data.preClose.toFixed(2)}</span></div>
        <div><span style={labelStyle}>成交量</span><span style={{ color: COLORS.text }}>{formatNumber(data.volume, 0)}</span></div>
        <div><span style={labelStyle}>成交额</span><span style={{ color: COLORS.text }}>{formatNumber(data.amount)}</span></div>
        {data.turnoverRate !== undefined && <div><span style={labelStyle}>换手率</span><span style={{ color: COLORS.text }}>{data.turnoverRate.toFixed(2)}%</span></div>}
        {data.marketCap !== undefined && <div><span style={labelStyle}>总市值</span><span style={{ color: COLORS.text }}>{formatNumber(data.marketCap)}</span></div>}
      </div>
    </div>
  )
}

export default StockHeader
