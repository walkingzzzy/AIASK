/**
 * 自选股管理页面
 */
import React, { useState, useEffect } from 'react'
import { Card, Row, Col, Button, Space, message, Modal } from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { useWatchlistStore } from '@/stores/useWatchlistStore'
import { GroupManager } from './GroupManager'
import { StockTable } from './StockTable'
import { AddStockModal } from './AddStockModal'
import { api } from '@/services/api'

export default function Watchlist() {
  const {
    groups,
    currentGroupId,
    setCurrentGroup,
    addStock,
    removeStock,
    updateStockPrice,
    updateStockNotes
  } = useWatchlistStore()

  const [addModalVisible, setAddModalVisible] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const currentGroup = groups.find(g => g.id === currentGroupId)

  // 刷新行情数据
  const handleRefreshQuotes = async () => {
    if (!currentGroup || currentGroup.stocks.length === 0) {
      message.info('当前分组没有股票')
      return
    }

    setRefreshing(true)
    try {
      // 使用批量API获取行情数据
      const stockCodes = currentGroup.stocks.map(stock => stock.code)
      const result = await api.getBatchStockQuotes(stockCodes) as any

      if (result.success && result.data) {
        currentGroup.stocks.forEach(stock => {
          const quoteData = result.data[stock.code]
          if (quoteData) {
            updateStockPrice(
              currentGroupId!,
              stock.code,
              quoteData.current_price,
              quoteData.change_percent
            )
          }
        })
      }

      message.success('行情数据已更新')
    } catch (error) {
      message.error('刷新行情失败')
    } finally {
      setRefreshing(false)
    }
  }

  // 添加股票
  const handleAddStock = (stockCode: string, stockName: string) => {
    if (!currentGroupId) {
      message.error('请先选择分组')
      return
    }

    // 检查是否已存在
    const exists = currentGroup?.stocks.some(s => s.code === stockCode)
    if (exists) {
      message.warning('该股票已在当前分组中')
      return
    }

    addStock(currentGroupId, {
      code: stockCode,
      name: stockName
    })

    message.success('添加成功')
    setAddModalVisible(false)

    // 获取最新行情
    api.getStockQuote(stockCode).then(result => {
      if (result.success && result.data) {
        updateStockPrice(
          currentGroupId,
          stockCode,
          result.data.current_price,
          result.data.change_percent
        )
      }
    })
  }

  // 删除股票
  const handleRemoveStock = (stockCode: string) => {
    if (!currentGroupId) return

    Modal.confirm({
      title: '确认删除',
      content: '确定要从自选股中删除这只股票吗？',
      onOk: () => {
        removeStock(currentGroupId, stockCode)
        message.success('删除成功')
      }
    })
  }

  // 更新备注
  const handleUpdateNotes = (stockCode: string, notes: string) => {
    if (!currentGroupId) return
    updateStockNotes(currentGroupId, stockCode, notes)
  }

  return (
    <div className="space-y-4">
      {/* 顶部操作栏 */}
      <Card>
        <Row justify="space-between" align="middle">
          <Col>
            <h2 className="text-xl font-semibold m-0">
              自选股管理
              {currentGroup && (
                <span className="text-gray-500 text-sm ml-2">
                  ({currentGroup.stocks.length} 只股票)
                </span>
              )}
            </h2>
          </Col>
          <Col>
            <Space>
              <Button
                icon={<ReloadOutlined />}
                onClick={handleRefreshQuotes}
                loading={refreshing}
              >
                刷新行情
              </Button>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setAddModalVisible(true)}
              >
                添加股票
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* 主内容区 */}
      <Row gutter={16}>
        {/* 左侧：分组管理 */}
        <Col span={6}>
          <GroupManager />
        </Col>

        {/* 右侧：股票列表 */}
        <Col span={18}>
          <StockTable
            stocks={currentGroup?.stocks || []}
            onRemove={handleRemoveStock}
            onUpdateNotes={handleUpdateNotes}
          />
        </Col>
      </Row>

      {/* 添加股票弹窗 */}
      <AddStockModal
        visible={addModalVisible}
        onCancel={() => setAddModalVisible(false)}
        onAdd={handleAddStock}
      />
    </div>
  )
}
