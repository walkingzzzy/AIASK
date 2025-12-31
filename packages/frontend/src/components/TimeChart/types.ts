/**
 * 分时图组件类型定义
 */

// 分时数据点
export interface TimeData {
  time: string           // 时间 HH:mm 格式
  price: number          // 当前价格
  avgPrice: number       // 均价
  volume: number         // 成交量
  amount?: number        // 成交额
}

// 分时图配置
export interface TimeChartConfig {
  width?: number
  height?: number
  mainHeight?: number    // 主图高度比例 (0-1)
  subHeight?: number     // 副图高度比例 (0-1)
  backgroundColor?: string
  textColor?: string
  gridColor?: string
  upColor?: string       // 上涨颜色（蓝色）
  downColor?: string     // 下跌颜色（绿色）
  avgLineColor?: string  // 均价线颜色
  prevCloseColor?: string // 昨收线颜色
  showLimitLines?: boolean // 是否显示涨跌停线
}

// 分时图组件Props
export interface TimeChartProps {
  stockCode: string
  timeData: TimeData[]
  prevClose: number      // 昨收价
  limitUp?: number       // 涨停价
  limitDown?: number     // 跌停价
  config?: TimeChartConfig
}

// 提示数据
export interface TooltipData {
  time: string
  price: number
  avgPrice: number
  volume: number
  change: number         // 涨跌额
  changePercent: number  // 涨跌幅
}
