/**
 * 主交易页面 - 专业炒股软件风格
 * 三栏布局：左侧自选股 + 中间K线图 + 右侧盘口
 */
import React, { useState, useEffect, useCallback } from 'react'
import { message } from 'antd'
import { WatchlistPanel } from '@/components/Layout/WatchlistPanel'
import { KLineChart } from '@/components/KLineChart'
import { RightPanel } from '@/components/Stock'
import { TopBar } from '@/components/Layout/TopBar'
import { api } from '@/services/api'
import type { StockHeaderData, OrderBookData, TradeRecord } from '@/components/Stock'

// 颜色常量
const COLORS = {
  bg: '#0d1117',
  panelBg: '#161b22',
  contentBg: '#1c2128',
  border: '#21262d',
  text: '#e6edf3',
  textSecondary: '#8b949e',
}

// 布局样式
const containerStyle: React.CSSProperties = {
  height: '100vh',
  display: 'flex',
  flexDirection: 'column',
  background: COLORS.bg,
  overflow: 'hidden',
}

const mainContentStyle: React.CSSProperties = {
  flex: 1,
  display: 'flex',
  overflow: 'hidden',
}

const leftPanelStyle: React.CSSProperties = {
  width: 240,
  flexShrink: 0,
  borderRight: `1px solid ${COLORS.border}`,
  background: COLORS.panelBg,
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

const centerPanelStyle: React.CSSProperties = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
  background: COLORS.contentBg,
}

const rightPanelStyle: React.CSSProperties = {
  width: 320,
  flexShrink: 0,
  borderLeft: `1px solid ${COLORS.border}`,
  background: COLORS.panelBg,
  overflow: 'hidden',
}

const chartContainerStyle: React.CSSProperties = {
  flex: 1,
  padding: 16,
  overflow: 'hidden',
}

export default function Trading() {
  // 当前选中的股票
  const [selectedStock, setSelectedStock] = useState<{ code: string; name: string } | null>(null)
  
  // 股票数据状态
  const [stockData, setStockData] = useState<StockHeaderData | undefined>()
  const [orderBookData, setOrderBookData] = useState<OrderBookData | undefined>()
  const [tradeData, setTradeData] = useState<TradeRecord[] | undefined>()
  const [loading, setLoading] = useState(false)

  // 选择股票
  const handleStockSelect = useCallback((code: string, name: string) => {
    setSelectedStock({ code, name })
  }, [])

  // 加载股票数据
  const loadStockData = useCallback(async (code: string, name: string) => {
    setLoading(true)
    try {
      // 获取股票行情
      const quoteRes = await api.getStockQuote(code) as any
      if (quoteRes.success && quoteRes.data) {
        const q = quoteRes.data
        setStockData({
          stockCode: code,
          stockName: q.stock_name || name,
          currentPrice: q.current_price || q.close || 0,
          preClose: q.prev_close || q.pre_close || 0,
          open: q.open_price || q.open || 0,
          high: q.high_price || q.high || 0,
          low: q.low_price || q.low || 0,
          volume: q.volume || 0,
          amount: q.amount || 0,
          changePercent: q.change_percent || 0,
          change: q.change_amount || q.change || 0,
          turnoverRate: q.turnover_rate,
          pe: q.pe_ratio || q.pe,
          pb: q.pb_ratio || q.pb,
          marketCap: q.market_cap,
        })

        const basePrice = q.current_price || q.close || 100
        const preClose = q.prev_close || q.pre_close || basePrice

        // 尝试获取真实盘口数据
        try {
          const orderBookRes = await api.getOrderBook(code) as any
          if (orderBookRes.success && orderBookRes.data) {
            setOrderBookData({
              stockCode: code,
              stockName: name,
              currentPrice: basePrice,
              preClose,
              asks: orderBookRes.data.asks || [],
              bids: orderBookRes.data.bids || [],
            })
          } else {
            // 数据获取失败，显示空状态
            setOrderBookData(undefined)
          }
        } catch {
          setOrderBookData(undefined)
        }

        // 尝试获取真实成交明细
        try {
          const tradeRes = await api.getTradeDetail(code) as any
          if (tradeRes.success && tradeRes.data) {
            setTradeData(tradeRes.data)
          } else {
            setTradeData(undefined)
          }
        } catch {
          setTradeData(undefined)
        }
      }
    } catch (error) {
      console.error('加载股票数据失败:', error)
      message.error('加载数据失败')
    } finally {
      setLoading(false)
    }
  }, [])

  // 监听股票选择变化
  useEffect(() => {
    if (selectedStock) {
      loadStockData(selectedStock.code, selectedStock.name)
    }
  }, [selectedStock, loadStockData])

  // 定时刷新数据 - 降低频率以减少服务器压力
  useEffect(() => {
    if (!selectedStock) return

    const interval = setInterval(() => {
      loadStockData(selectedStock.code, selectedStock.name)
    }, 15000) // 15秒刷新一次（盘口数据更新不需要太频繁）

    return () => clearInterval(interval)
  }, [selectedStock, loadStockData])

  return (
    <div style={containerStyle}>
      {/* 顶部工具栏 */}
      <TopBar onStockSelect={handleStockSelect} />

      {/* 主内容区 */}
      <div style={mainContentStyle}>
        {/* 左侧：自选股面板 */}
        <div style={leftPanelStyle}>
          <WatchlistPanel
            onStockSelect={handleStockSelect}
            selectedStock={selectedStock?.code}
          />
        </div>

        {/* 中间：K线图 */}
        <div style={centerPanelStyle}>
          {selectedStock ? (
            <div style={chartContainerStyle}>
              <KLineChart
                stockCode={selectedStock.code}
                period="day"
                config={{
                  height: 500,
                  backgroundColor: COLORS.contentBg,
                  textColor: COLORS.text,
                  gridColor: COLORS.border,
                }}
              />
            </div>
          ) : (
            <div style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: COLORS.textSecondary,
            }}>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 48, marginBottom: 16 }}>📈</div>
                <div style={{ fontSize: 16 }}>请从左侧选择股票或使用搜索</div>
              </div>
            </div>
          )}
        </div>

        {/* 右侧：盘口和成交明细 */}
        <div style={rightPanelStyle}>
          <RightPanel
            stockData={stockData}
            orderBookData={orderBookData}
            tradeData={tradeData}
            loading={loading}
          />
        </div>
      </div>
    </div>
  )
}
