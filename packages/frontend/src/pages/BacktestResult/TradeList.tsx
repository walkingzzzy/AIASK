/**
 * 交易列表组件
 */
import React from 'react'
import { Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { Trade } from './types'

interface TradeListProps {
  trades: Trade[]
}

export const TradeList: React.FC<TradeListProps> = ({ trades }) => {
  const columns: ColumnsType<Trade> = [
    {
      title: '日期',
      dataIndex: 'date',
      key: 'date',
      width: 120,
      sorter: (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 80,
      render: (type: string) => (
        <Tag color={type === 'buy' ? 'red' : 'green'}>
          {type === 'buy' ? '买入' : '卖出'}
        </Tag>
      ),
      filters: [
        { text: '买入', value: 'buy' },
        { text: '卖出', value: 'sell' }
      ],
      onFilter: (value, record) => record.type === value
    },
    {
      title: '价格',
      dataIndex: 'price',
      key: 'price',
      width: 100,
      align: 'right',
      render: (price: number) => `¥${price.toFixed(2)}`
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 100,
      align: 'right',
      render: (quantity: number) => quantity.toLocaleString()
    },
    {
      title: '金额',
      dataIndex: 'amount',
      key: 'amount',
      width: 120,
      align: 'right',
      render: (amount: number) => `¥${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    },
    {
      title: '手续费',
      dataIndex: 'commission',
      key: 'commission',
      width: 100,
      align: 'right',
      render: (commission: number) => `¥${commission.toFixed(2)}`
    },
    {
      title: '盈亏',
      dataIndex: 'profit',
      key: 'profit',
      width: 120,
      align: 'right',
      render: (profit?: number) => {
        if (profit === undefined) return '-'
        return (
          <span style={{ color: profit >= 0 ? '#3f8600' : '#cf1322' }}>
            {profit >= 0 ? '+' : ''}¥{profit.toFixed(2)}
          </span>
        )
      },
      sorter: (a, b) => (a.profit || 0) - (b.profit || 0)
    },
    {
      title: '收益率',
      dataIndex: 'profitPercent',
      key: 'profitPercent',
      width: 100,
      align: 'right',
      render: (profitPercent?: number) => {
        if (profitPercent === undefined) return '-'
        return (
          <span style={{ color: profitPercent >= 0 ? '#3f8600' : '#cf1322' }}>
            {profitPercent >= 0 ? '+' : ''}{profitPercent.toFixed(2)}%
          </span>
        )
      },
      sorter: (a, b) => (a.profitPercent || 0) - (b.profitPercent || 0)
    }
  ]

  return (
    <Table
      columns={columns}
      dataSource={trades}
      rowKey="id"
      size="small"
      pagination={{
        pageSize: 20,
        showSizeChanger: true,
        showTotal: (total) => `共 ${total} 笔交易`
      }}
      scroll={{ x: 900 }}
    />
  )
}
