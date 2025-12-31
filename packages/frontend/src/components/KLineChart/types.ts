/**
 * K线图表组件类型定义
 */

// K线数据点
export interface KLineData {
  time: string | number  // 时间戳或日期字符串
  open: number           // 开盘价
  high: number           // 最高价
  low: number            // 最低价
  close: number          // 收盘价
  volume: number         // 成交量
}

// 技术指标数据
export interface IndicatorData {
  time: string | number
  value: number | number[]  // 单值或多值（如MACD有DIF、DEA、MACD三个值）
}

// 周期类型
export type PeriodType = '1min' | '5min' | '15min' | '30min' | '60min' | 'day' | 'week' | 'month'

// 主图指标类型
export type MainIndicatorType = 'MA' | 'BOLL' | 'SAR' | 'NONE'

// 副图指标类型
export type SubIndicatorType = 'MACD' | 'RSI' | 'KDJ' | 'VOL' | 'NONE'

// 交易信号类型
export interface TradingSignal {
  time: string | number
  type: 'buy' | 'sell'
  price: number
  label?: string
}

// 图表配置
export interface ChartConfig {
  width?: number
  height?: number
  mainHeight?: number      // 主图高度比例
  subHeight?: number       // 副图高度比例
  backgroundColor?: string
  textColor?: string
  gridColor?: string
  upColor?: string         // 上涨颜色
  downColor?: string       // 下跌颜色
}

// K线图表组件Props
export interface KLineChartProps {
  stockCode: string
  period?: PeriodType
  mainIndicator?: MainIndicatorType
  subIndicator?: SubIndicatorType
  signals?: TradingSignal[]
  config?: ChartConfig
  onPeriodChange?: (period: PeriodType) => void
  onIndicatorChange?: (main: MainIndicatorType, sub: SubIndicatorType) => void
}

// 工具栏Props
export interface ChartToolbarProps {
  period: PeriodType
  mainIndicator: MainIndicatorType
  subIndicator: SubIndicatorType
  onPeriodChange: (period: PeriodType) => void
  onMainIndicatorChange: (indicator: MainIndicatorType) => void
  onSubIndicatorChange: (indicator: SubIndicatorType) => void
  onZoomIn?: () => void
  onZoomOut?: () => void
  onReset?: () => void
  onExport?: () => void
}

// 指标面板Props
export interface IndicatorPanelProps {
  visible: boolean
  onClose: () => void
  onApply: (main: MainIndicatorType, sub: SubIndicatorType) => void
}
