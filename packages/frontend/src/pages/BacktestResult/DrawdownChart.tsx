/**
 * 回撤图表组件
 */
import React from 'react'
import { Card, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { DrawdownPeriod } from './types'

interface DrawdownChartProps {
  drawdownPeriods: DrawdownPeriod[]
}

export const DrawdownChart: React.FC<DrawdownChartProps> = ({ drawdownPeriods }) => {
  const columns: ColumnsType<DrawdownPeriod> = [
    {
      title: '开始日期',
      dataIndex: 'startDate',
      key: 'startDate',
      width: 120
    },
    {
      title: '结束日期',
      dataIndex: 'endDate',
      key: 'endDate',
      width: 120
    },
    {
      title: '回撤幅度',
      dataIndex: 'drawdown',
      key: 'drawdown',
      width: 120,
      align: 'right',
      render: (drawdown: number) => (
        <Tag color="red">
          {(Math.abs(drawdown) * 100).toFixed(2)}%
        </Tag>
      ),
      sorter: (a, b) => Math.abs(b.drawdown) - Math.abs(a.drawdown)
    },
    {
      title: '持续天数',
      dataIndex: 'duration',
      key: 'duration',
      width: 100,
      align: 'right',
      render: (duration: number) => `${duration} 天`,
      sorter: (a, b) => b.duration - a.duration
    }
  ]

  // 按回撤幅度排序，显示最大的几次回撤
  const sortedPeriods = [...drawdownPeriods]
    .sort((a, b) => Math.abs(b.drawdown) - Math.abs(a.drawdown))
    .slice(0, 10)

  return (
    <Card title="主要回撤区间" size="small">
      <Table
        columns={columns}
        dataSource={sortedPeriods}
        rowKey={(record) => `${record.startDate}-${record.endDate}`}
        size="small"
        pagination={false}
      />
    </Card>
  )
}
