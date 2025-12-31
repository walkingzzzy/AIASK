import React, { useState } from 'react'
import { Tabs, Spin } from 'antd'
import OrderBook, { OrderBookData } from './OrderBook'
import TradeDetail, { TradeRecord } from './TradeDetail'
import StockHeader, { StockHeaderData } from './StockHeader'

export interface RightPanelProps {
  stockData?: StockHeaderData
  orderBookData?: OrderBookData
  tradeData?: TradeRecord[]
  loading?: boolean
  onTabChange?: (key: string) => void
}

const COLORS = {
  bg: '#161b22',
  border: '#30363d',
  text: '#e6edf3',
  textSecondary: '#8b949e',
}

const containerStyle: React.CSSProperties = {
  height: '100%',
  display: 'flex',
  flexDirection: 'column',
  background: COLORS.bg,
}

const RightPanel: React.FC<RightPanelProps> = ({
  stockData,
  orderBookData,
  tradeData,
  loading = false,
  onTabChange,
}) => {
  const [activeTab, setActiveTab] = useState('orderbook')

  const handleTabChange = (key: string) => {
    setActiveTab(key)
    onTabChange?.(key)
  }

  if (loading) {
    return (
      <div style={{ ...containerStyle, justifyContent: 'center', alignItems: 'center' }}>
        <Spin />
      </div>
    )
  }

  const tabItems = [
    {
      key: 'orderbook',
      label: '盘口',
      children: <OrderBook data={orderBookData} />,
    },
    {
      key: 'trades',
      label: '明细',
      children: <TradeDetail data={tradeData} preClose={stockData?.preClose} />,
    },
  ]

  return (
    <div style={containerStyle}>
      <StockHeader data={stockData} />
      <div style={{ flex: 1, overflow: 'hidden', marginTop: 8 }}>
        <Tabs
          activeKey={activeTab}
          onChange={handleTabChange}
          items={tabItems}
          size="small"
          style={{ height: '100%' }}
          tabBarStyle={{
            margin: '0 12px',
            borderBottom: `1px solid ${COLORS.border}`,
          }}
        />
      </div>
    </div>
  )
}

export default RightPanel
export { OrderBook, TradeDetail, StockHeader }
export type { OrderBookData, TradeRecord, StockHeaderData }
