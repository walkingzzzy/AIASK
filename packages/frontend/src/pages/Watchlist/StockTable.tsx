/**
 * 股票列表组件
 */
import React, { useState } from 'react'
import { Card, Table, Tag, Button, Space, Input, Modal, Tooltip } from 'antd'
import {
  DeleteOutlined,
  EditOutlined,
  LineChartOutlined,
  RiseOutlined,
  FallOutlined
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import type { Stock } from '@/stores/useWatchlistStore'

const { TextArea } = Input

interface StockTableProps {
  stocks: Stock[]
  onRemove: (stockCode: string) => void
  onUpdateNotes: (stockCode: string, notes: string) => void
}

export const StockTable: React.FC<StockTableProps> = ({
  stocks,
  onRemove,
  onUpdateNotes
}) => {
  const [notesModalVisible, setNotesModalVisible] = useState(false)
  const [editingStock, setEditingStock] = useState<Stock | null>(null)
  const [notesValue, setNotesValue] = useState('')

  // 打开备注编辑弹窗
  const openNotesModal = (stock: Stock) => {
    setEditingStock(stock)
    setNotesValue(stock.notes || '')
    setNotesModalVisible(true)
  }

  // 保存备注
  const handleSaveNotes = () => {
    if (editingStock) {
      onUpdateNotes(editingStock.code, notesValue)
      setNotesModalVisible(false)
      setEditingStock(null)
      setNotesValue('')
    }
  }

  // 表格列定义
  const columns: ColumnsType<Stock> = [
    {
      title: '股票代码',
      dataIndex: 'code',
      key: 'code',
      width: 120,
      fixed: 'left',
      render: (code: string) => (
        <span className="font-mono font-semibold">{code}</span>
      )
    },
    {
      title: '股票名称',
      dataIndex: 'name',
      key: 'name',
      width: 150,
      fixed: 'left'
    },
    {
      title: '当前价格',
      dataIndex: 'currentPrice',
      key: 'currentPrice',
      width: 120,
      align: 'right',
      render: (price?: number) => (
        price !== undefined ? (
          <span className="font-mono">¥{price.toFixed(2)}</span>
        ) : (
          <span className="text-gray-400">-</span>
        )
      ),
      sorter: (a, b) => (a.currentPrice || 0) - (b.currentPrice || 0)
    },
    {
      title: '涨跌幅',
      dataIndex: 'changePercent',
      key: 'changePercent',
      width: 120,
      align: 'right',
      render: (percent?: number) => {
        if (percent === undefined) {
          return <span className="text-gray-400">-</span>
        }

        const isPositive = percent >= 0
        const color = isPositive ? 'text-red-500' : 'text-green-500'
        const Icon = isPositive ? RiseOutlined : FallOutlined

        return (
          <span className={`font-mono ${color} flex items-center justify-end`}>
            <Icon className="mr-1" />
            {isPositive ? '+' : ''}{percent.toFixed(2)}%
          </span>
        )
      },
      sorter: (a, b) => (a.changePercent || 0) - (b.changePercent || 0),
      defaultSortOrder: 'descend'
    },
    {
      title: 'AI评分',
      dataIndex: 'aiScore',
      key: 'aiScore',
      width: 100,
      align: 'center',
      render: (score?: number) => {
        if (score === undefined) {
          return <span className="text-gray-400">-</span>
        }

        let color = 'default'
        if (score >= 80) color = 'red'
        else if (score >= 60) color = 'orange'
        else if (score >= 40) color = 'blue'
        else color = 'gray'

        return <Tag color={color}>{score}</Tag>
      },
      sorter: (a, b) => (a.aiScore || 0) - (b.aiScore || 0)
    },
    {
      title: '备注',
      dataIndex: 'notes',
      key: 'notes',
      width: 200,
      ellipsis: true,
      render: (notes?: string) => (
        <Tooltip title={notes}>
          <span className="text-gray-600">{notes || '-'}</span>
        </Tooltip>
      )
    },
    {
      title: '添加时间',
      dataIndex: 'addedAt',
      key: 'addedAt',
      width: 180,
      render: (date: string) => new Date(date).toLocaleString('zh-CN'),
      sorter: (a, b) => new Date(a.addedAt).getTime() - new Date(b.addedAt).getTime()
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      fixed: 'right',
      render: (_: any, record: Stock) => (
        <Space size="small">
          <Tooltip title="查看K线">
            <Button
              type="text"
              size="small"
              icon={<LineChartOutlined />}
              onClick={() => {
                // 跳转到股票分析页面
                window.location.href = `/stock-analysis?code=${record.code}`
              }}
            />
          </Tooltip>
          <Tooltip title="编辑备注">
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => openNotesModal(record)}
            />
          </Tooltip>
          <Tooltip title="删除">
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => onRemove(record.code)}
            />
          </Tooltip>
        </Space>
      )
    }
  ]

  return (
    <>
      <Card>
        <Table
          columns={columns}
          dataSource={stocks}
          rowKey="code"
          pagination={{
            pageSize: 20,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 只股票`
          }}
          scroll={{ x: 1200 }}
          size="small"
        />
      </Card>

      {/* 备注编辑弹窗 */}
      <Modal
        title={`编辑备注 - ${editingStock?.name} (${editingStock?.code})`}
        open={notesModalVisible}
        onOk={handleSaveNotes}
        onCancel={() => {
          setNotesModalVisible(false)
          setEditingStock(null)
          setNotesValue('')
        }}
        okText="保存"
        cancelText="取消"
        width={600}
      >
        <TextArea
          value={notesValue}
          onChange={(e) => setNotesValue(e.target.value)}
          placeholder="输入备注信息..."
          rows={4}
          maxLength={200}
          showCount
        />
      </Modal>
    </>
  )
}
