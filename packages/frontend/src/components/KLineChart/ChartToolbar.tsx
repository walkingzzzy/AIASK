/**
 * K线图表工具栏组件
 */
import React from 'react'
import { Button, Space, Select, Tooltip } from 'antd'
import {
  ZoomInOutlined,
  ZoomOutOutlined,
  ReloadOutlined,
  DownloadOutlined,
  SettingOutlined
} from '@ant-design/icons'
import type { ChartToolbarProps, PeriodType, MainIndicatorType, SubIndicatorType } from './types'

const { Option } = Select

export const ChartToolbar: React.FC<ChartToolbarProps> = ({
  period,
  mainIndicator,
  subIndicator,
  onPeriodChange,
  onMainIndicatorChange,
  onSubIndicatorChange,
  onZoomIn,
  onZoomOut,
  onReset,
  onExport
}) => {
  // 周期选项
  const periodOptions: { label: string; value: PeriodType }[] = [
    { label: '1分钟', value: '1min' },
    { label: '5分钟', value: '5min' },
    { label: '15分钟', value: '15min' },
    { label: '30分钟', value: '30min' },
    { label: '60分钟', value: '60min' },
    { label: '日K', value: 'day' },
    { label: '周K', value: 'week' },
    { label: '月K', value: 'month' }
  ]

  // 主图指标选项
  const mainIndicatorOptions: { label: string; value: MainIndicatorType }[] = [
    { label: '无', value: 'NONE' },
    { label: 'MA均线', value: 'MA' },
    { label: '布林带', value: 'BOLL' },
    { label: 'SAR', value: 'SAR' }
  ]

  // 副图指标选项
  const subIndicatorOptions: { label: string; value: SubIndicatorType }[] = [
    { label: '成交量', value: 'VOL' },
    { label: 'MACD', value: 'MACD' },
    { label: 'RSI', value: 'RSI' },
    { label: 'KDJ', value: 'KDJ' },
    { label: '无', value: 'NONE' }
  ]

  return (
    <div className="flex items-center justify-between p-2 bg-white border-b">
      <Space size="small">
        {/* 周期选择 */}
        <Select
          value={period}
          onChange={onPeriodChange}
          style={{ width: 100 }}
          size="small"
        >
          {periodOptions.map(opt => (
            <Option key={opt.value} value={opt.value}>{opt.label}</Option>
          ))}
        </Select>

        {/* 主图指标 */}
        <Select
          value={mainIndicator}
          onChange={onMainIndicatorChange}
          style={{ width: 100 }}
          size="small"
        >
          {mainIndicatorOptions.map(opt => (
            <Option key={opt.value} value={opt.value}>{opt.label}</Option>
          ))}
        </Select>

        {/* 副图指标 */}
        <Select
          value={subIndicator}
          onChange={onSubIndicatorChange}
          style={{ width: 100 }}
          size="small"
        >
          {subIndicatorOptions.map(opt => (
            <Option key={opt.value} value={opt.value}>{opt.label}</Option>
          ))}
        </Select>
      </Space>

      <Space size="small">
        {/* 缩放控制 */}
        {onZoomIn && (
          <Tooltip title="放大">
            <Button size="small" icon={<ZoomInOutlined />} onClick={onZoomIn} />
          </Tooltip>
        )}
        {onZoomOut && (
          <Tooltip title="缩小">
            <Button size="small" icon={<ZoomOutOutlined />} onClick={onZoomOut} />
          </Tooltip>
        )}
        {onReset && (
          <Tooltip title="重置">
            <Button size="small" icon={<ReloadOutlined />} onClick={onReset} />
          </Tooltip>
        )}
        {onExport && (
          <Tooltip title="导出图片">
            <Button size="small" icon={<DownloadOutlined />} onClick={onExport} />
          </Tooltip>
        )}
      </Space>
    </div>
  )
}
