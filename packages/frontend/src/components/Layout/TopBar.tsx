/**
 * 顶部导航栏组件
 * 包含：全局搜索、大盘指数、实时时间
 */
import React, { useState, useEffect, useRef } from 'react'
import { Input, Spin, message } from 'antd'
import { SearchOutlined, CaretUpOutlined, CaretDownOutlined, PlusOutlined } from '@ant-design/icons'
import { useWatchlistStore } from '@/stores/useWatchlistStore'
import styles from './TopBar.module.css'

interface IndexData {
  name: string
  code: string
  price: number
  change: number
  changePercent: number
}

interface SearchResult {
  code: string
  name: string
}

interface TopBarProps {
  onStockSelect: (code: string, name: string) => void
}

export const TopBar: React.FC<TopBarProps> = ({ onStockSelect }) => {
  const [currentTime, setCurrentTime] = useState(new Date())
  const [searchValue, setSearchValue] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [showDropdown, setShowDropdown] = useState(false)
  const searchRef = useRef<HTMLDivElement>(null)
  
  const { addStock, groups, currentGroupId } = useWatchlistStore()
  
  // 模拟大盘指数数据（实际应从API获取）
  const [indices] = useState<IndexData[]>([
    { name: '上证', code: '000001.SH', price: 3150.25, change: 37.5, changePercent: 1.2 },
    { name: '深证', code: '399001.SZ', price: 10500.80, change: -52.5, changePercent: -0.5 },
    { name: '创业板', code: '399006.SZ', price: 2100.15, change: 16.8, changePercent: 0.8 },
  ])

  // 更新时间
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  // 点击外部关闭搜索下拉
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // 搜索股票
  const handleSearch = async (value: string) => {
    setSearchValue(value)
    if (!value.trim()) {
      setSearchResults([])
      setShowDropdown(false)
      return
    }
    
    setSearching(true)
    setShowDropdown(true)
    
    try {
      // 调用API搜索股票
      const res = await fetch(`/api/stock/search?keyword=${encodeURIComponent(value)}&limit=8`)
      const data = await res.json()
      if (data.success && data.data) {
        setSearchResults(data.data.map((s: any) => ({ code: s.code, name: s.name })))
      } else {
        setSearchResults([])
      }
    } catch (error) {
      console.error('搜索失败:', error)
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }

  // 选择股票
  const handleSelectStock = (stock: SearchResult) => {
    onStockSelect(stock.code, stock.name)
    setSearchValue('')
    setShowDropdown(false)
  }

  // 添加到自选股
  const handleAddToWatchlist = (stock: SearchResult, e: React.MouseEvent) => {
    e.stopPropagation()
    const groupId = currentGroupId || 'default'
    const currentGroup = groups.find(g => g.id === groupId)
    
    // 检查是否已存在
    if (currentGroup?.stocks.some(s => s.code === stock.code)) {
      message.warning('该股票已在自选股中')
      return
    }
    
    addStock(groupId, { code: stock.code, name: stock.name })
    message.success(`已添加 ${stock.name} 到自选股`)
  }

  // 快捷键支持
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault()
        const input = document.querySelector('.topbar-search input') as HTMLInputElement
        input?.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('zh-CN', { hour12: false })
  }

  const isTradeTime = () => {
    const hours = currentTime.getHours()
    const minutes = currentTime.getMinutes()
    const time = hours * 60 + minutes
    return (time >= 9 * 60 + 30 && time <= 11 * 60 + 30) || 
           (time >= 13 * 60 && time <= 15 * 60)
  }

  return (
    <div className={styles.topBar}>
      {/* 全局搜索 */}
      <div className={styles.searchWrapper} ref={searchRef}>
        <Input
          className="topbar-search"
          prefix={<SearchOutlined style={{ color: '#6e7681' }} />}
          placeholder="搜索股票代码/名称 (Ctrl+F)"
          value={searchValue}
          onChange={e => handleSearch(e.target.value)}
          onFocus={() => searchValue && setShowDropdown(true)}
          style={{
            width: 240,
            background: '#161b22',
            border: '1px solid #30363d',
            borderRadius: 6,
          }}
        />
        {showDropdown && (
          <div className={styles.searchDropdown}>
            {searching ? (
              <div className={styles.searchLoading}><Spin size="small" /></div>
            ) : searchResults.length > 0 ? (
              searchResults.map(stock => (
                <div
                  key={stock.code}
                  className={styles.searchItem}
                  onClick={() => handleSelectStock(stock)}
                >
                  <span className={styles.stockCode}>{stock.code}</span>
                  <span className={styles.stockName}>{stock.name}</span>
                  <span 
                    className={styles.addBtn}
                    onClick={(e) => handleAddToWatchlist(stock, e)}
                    title="添加到自选股"
                  >
                    <PlusOutlined />
                  </span>
                </div>
              ))
            ) : (
              <div className={styles.noResult}>未找到相关股票</div>
            )}
          </div>
        )}
      </div>

      {/* 大盘指数 */}
      <div className={styles.indexBar}>
        {indices.map(index => (
          <div key={index.code} className={styles.indexItem}>
            <span className={styles.indexName}>{index.name}</span>
            <span className={`${styles.indexPrice} ${index.change >= 0 ? styles.up : styles.down}`}>
              {index.price.toFixed(2)}
            </span>
            <span className={`${styles.indexChange} ${index.change >= 0 ? styles.up : styles.down}`}>
              {index.change >= 0 ? <CaretUpOutlined /> : <CaretDownOutlined />}
              {Math.abs(index.changePercent).toFixed(2)}%
            </span>
          </div>
        ))}
      </div>

      {/* 实时时间 */}
      <div className={styles.timeWrapper}>
        <span className={`${styles.tradeStatus} ${isTradeTime() ? styles.trading : ''}`}>
          {isTradeTime() ? '交易中' : '休市'}
        </span>
        <span className={styles.time}>{formatTime(currentTime)}</span>
      </div>
    </div>
  )
}

export default TopBar
