/**
 * 左侧自选股面板组件
 * 实时显示自选股行情，支持分组管理
 */
import React, { useState, useEffect, useCallback } from 'react'
import { Dropdown, Menu, Modal, Input, message, Tooltip } from 'antd'
import { 
  PlusOutlined, 
  MoreOutlined, 
  StarFilled,
  DeleteOutlined,
  EditOutlined,
  FolderOutlined,
  CaretUpOutlined,
  CaretDownOutlined,
  LoadingOutlined,
} from '@ant-design/icons'
import { useWatchlistStore, Stock, WatchlistGroup } from '@/stores/useWatchlistStore'
import { api } from '@/services/api'
import styles from './WatchlistPanel.module.css'

interface WatchlistPanelProps {
  onStockSelect: (code: string, name: string) => void
  selectedStock?: string
  collapsed?: boolean
  onCollapse?: (collapsed: boolean) => void
}

export const WatchlistPanel: React.FC<WatchlistPanelProps> = ({
  onStockSelect,
  selectedStock,
  collapsed = false,
  onCollapse,
}) => {
  const { 
    groups, 
    currentGroupId, 
    setCurrentGroup,
    addGroup,
    removeGroup,
    renameGroup,
    removeStock,
    updateStockPrice,
  } = useWatchlistStore()

  const [editingGroup, setEditingGroup] = useState<string | null>(null)
  const [newGroupName, setNewGroupName] = useState('')
  const [showAddGroup, setShowAddGroup] = useState(false)
  const [loading, setLoading] = useState(false)
  
  // 使用 ref 存储当前分组ID和股票列表，避免依赖项频繁变化
  const currentGroupIdRef = React.useRef(currentGroupId)
  const stocksRef = React.useRef<Stock[]>([])

  const currentGroup = groups.find(g => g.id === currentGroupId) || groups[0]
  
  // 更新 ref
  React.useEffect(() => {
    currentGroupIdRef.current = currentGroupId
    stocksRef.current = currentGroup?.stocks || []
  }, [currentGroupId, currentGroup?.stocks])

  // 从API获取真实行情数据 - 使用批量API
  const fetchRealTimeQuotes = useCallback(async () => {
    const stocks = stocksRef.current
    const groupId = currentGroupIdRef.current
    
    if (!stocks.length || !groupId) return
    
    setLoading(true)
    try {
      // 使用批量API获取所有自选股的行情
      const stockCodes = stocks.map(s => s.code)
      const res = await api.getBatchStockQuotes(stockCodes) as any
      
      if (res.success && res.data) {
        // 批量更新价格
        for (const stock of stocks) {
          const quoteData = res.data[stock.code]
          if (quoteData) {
            const price = quoteData.current_price || quoteData.close || 0
            const changePercent = quoteData.change_percent || 0
            if (price > 0) {
              updateStockPrice(groupId, stock.code, price, changePercent)
            }
          }
        }
      }
    } catch (err) {
      console.warn('获取行情失败:', err)
    } finally {
      setLoading(false)
    }
  }, [updateStockPrice])  // 只依赖 updateStockPrice

  // 初始加载和定时刷新真实行情
  useEffect(() => {
    // 立即获取一次
    fetchRealTimeQuotes()
    
    // 每30秒刷新一次（降低频率，减少服务器压力）
    const interval = setInterval(() => {
      fetchRealTimeQuotes()
    }, 30000)
    
    return () => clearInterval(interval)
  }, [fetchRealTimeQuotes])
  
  // 当分组变化时，立即获取新分组的行情
  useEffect(() => {
    if (currentGroupId) {
      // 延迟一点执行，确保 ref 已更新
      const timer = setTimeout(fetchRealTimeQuotes, 100)
      return () => clearTimeout(timer)
    }
  }, [currentGroupId, fetchRealTimeQuotes])

  // 处理股票点击
  const handleStockClick = (stock: Stock) => {
    onStockSelect(stock.code, stock.name)
  }

  // 处理股票右键菜单
  const getStockContextMenu = (stock: Stock) => ({
    items: [
      {
        key: 'delete',
        icon: <DeleteOutlined />,
        label: '删除',
        danger: true,
        onClick: () => {
          removeStock(currentGroupId!, stock.code)
          message.success('已从自选股移除')
        }
      },
    ]
  })

  // 处理分组切换
  const handleGroupChange = (groupId: string) => {
    setCurrentGroup(groupId)
  }

  // 添加新分组
  const handleAddGroup = () => {
    if (!newGroupName.trim()) {
      message.warning('请输入分组名称')
      return
    }
    addGroup(newGroupName.trim())
    setNewGroupName('')
    setShowAddGroup(false)
    message.success('分组创建成功')
  }

  // 删除分组
  const handleDeleteGroup = (groupId: string) => {
    if (groupId === 'default') {
      message.warning('默认分组不能删除')
      return
    }
    Modal.confirm({
      title: '确认删除',
      content: '删除分组后，其中的股票将被移除，确定要删除吗？',
      onOk: () => {
        removeGroup(groupId)
        message.success('分组已删除')
      }
    })
  }

  // 渲染价格变化
  const renderPriceChange = (stock: Stock) => {
    const change = stock.changePercent || 0
    const isUp = change > 0
    const isDown = change < 0
    
    return (
      <div className={styles.stockChange}>
        <span className={`${styles.price} ${isUp ? styles.up : isDown ? styles.down : ''}`}>
          {stock.currentPrice?.toFixed(2) || '--'}
        </span>
        <span className={`${styles.percent} ${isUp ? styles.up : isDown ? styles.down : ''}`}>
          {isUp && '+'}{change.toFixed(2)}%
          {isUp ? <CaretUpOutlined /> : isDown ? <CaretDownOutlined /> : null}
        </span>
      </div>
    )
  }

  if (collapsed) {
    return (
      <div className={styles.collapsedPanel} onClick={() => onCollapse?.(false)}>
        <StarFilled style={{ color: '#d29922' }} />
      </div>
    )
  }

  return (
    <div className={styles.panel}>
      {/* 面板头部 */}
      <div className={styles.header}>
        <div className={styles.title}>
          <StarFilled style={{ color: '#d29922', marginRight: 6 }} />
          自选股
          {loading && <LoadingOutlined style={{ marginLeft: 8, fontSize: 12 }} />}
        </div>
        <Tooltip title="收起">
          <span className={styles.collapseBtn} onClick={() => onCollapse?.(true)}>
            ‹
          </span>
        </Tooltip>
      </div>

      {/* 分组选择 */}
      <div className={styles.groupTabs}>
        {groups.map(group => (
          <Dropdown
            key={group.id}
            menu={{
              items: [
                {
                  key: 'rename',
                  icon: <EditOutlined />,
                  label: '重命名',
                  onClick: () => setEditingGroup(group.id)
                },
                {
                  key: 'delete',
                  icon: <DeleteOutlined />,
                  label: '删除',
                  danger: true,
                  disabled: group.id === 'default',
                  onClick: () => handleDeleteGroup(group.id)
                }
              ]
            }}
            trigger={['contextMenu']}
          >
            <div
              className={`${styles.groupTab} ${currentGroupId === group.id ? styles.active : ''}`}
              onClick={() => handleGroupChange(group.id)}
            >
              {group.name}
              <span className={styles.stockCount}>{group.stocks.length}</span>
            </div>
          </Dropdown>
        ))}
        <div className={styles.addGroupBtn} onClick={() => setShowAddGroup(true)}>
          <PlusOutlined />
        </div>
      </div>

      {/* 股票列表 */}
      <div className={styles.stockList}>
        {currentGroup?.stocks.length === 0 ? (
          <div className={styles.emptyState}>
            <FolderOutlined style={{ fontSize: 32, opacity: 0.3 }} />
            <p>暂无自选股</p>
            <span>使用搜索添加股票</span>
          </div>
        ) : (
          currentGroup?.stocks.map(stock => (
            <Dropdown
              key={stock.code}
              menu={getStockContextMenu(stock)}
              trigger={['contextMenu']}
            >
              <div
                className={`${styles.stockItem} ${selectedStock === stock.code ? styles.selected : ''}`}
                onClick={() => handleStockClick(stock)}
              >
                <div className={styles.stockInfo}>
                  <span className={styles.stockName}>{stock.name}</span>
                  <span className={styles.stockCode}>{stock.code}</span>
                </div>
                {renderPriceChange(stock)}
              </div>
            </Dropdown>
          ))
        )}
      </div>

      {/* 添加分组弹窗 */}
      <Modal
        title="新建分组"
        open={showAddGroup}
        onOk={handleAddGroup}
        onCancel={() => {
          setShowAddGroup(false)
          setNewGroupName('')
        }}
        width={320}
      >
        <Input
          placeholder="请输入分组名称"
          value={newGroupName}
          onChange={e => setNewGroupName(e.target.value)}
          onPressEnter={handleAddGroup}
          maxLength={10}
        />
      </Modal>

      {/* 重命名分组弹窗 */}
      <Modal
        title="重命名分组"
        open={!!editingGroup}
        onOk={() => {
          if (editingGroup && newGroupName.trim()) {
            renameGroup(editingGroup, newGroupName.trim())
            setEditingGroup(null)
            setNewGroupName('')
            message.success('重命名成功')
          }
        }}
        onCancel={() => {
          setEditingGroup(null)
          setNewGroupName('')
        }}
        width={320}
      >
        <Input
          placeholder="请输入新名称"
          value={newGroupName}
          onChange={e => setNewGroupName(e.target.value)}
          maxLength={10}
        />
      </Modal>
    </div>
  )
}

export default WatchlistPanel
