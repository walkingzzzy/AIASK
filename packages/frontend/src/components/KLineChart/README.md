# K线图表组件

## 概述

专业的K线图表组件，基于 `lightweight-charts` 库实现，支持多周期切换、技术指标叠加、交易信号标注等功能。

## 功能特性

- ✅ 多周期支持：1分钟、5分钟、15分钟、30分钟、60分钟、日K、周K、月K
- ✅ 主图指标：MA均线、布林带(BOLL)、SAR
- ✅ 副图指标：成交量(VOL)、MACD、RSI、KDJ
- ✅ 缩放控制：放大、缩小、重置
- ✅ 响应式设计：自动适应容器大小
- ✅ 交易信号标注（预留接口）
- ✅ 图片导出功能（预留接口）

## 使用方法

### 基础用法

```tsx
import KLineChart from '@/components/KLineChart'

function MyComponent() {
  return (
    <KLineChart
      stockCode="600519"
      period="day"
      mainIndicator="MA"
      subIndicator="VOL"
    />
  )
}
```

### 完整配置

```tsx
import KLineChart from '@/components/KLineChart'
import type { TradingSignal } from '@/components/KLineChart/types'

function MyComponent() {
  const signals: TradingSignal[] = [
    { time: '2024-01-01', type: 'buy', price: 100, label: '买入信号' },
    { time: '2024-01-15', type: 'sell', price: 120, label: '卖出信号' }
  ]

  return (
    <KLineChart
      stockCode="600519"
      period="day"
      mainIndicator="MA"
      subIndicator="MACD"
      signals={signals}
      config={{
        width: 1000,
        height: 600,
        upColor: '#ef5350',
        downColor: '#26a69a'
      }}
      onPeriodChange={(period) => console.log('周期变化:', period)}
      onIndicatorChange={(main, sub) => console.log('指标变化:', main, sub)}
    />
  )
}
```

## Props 说明

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| stockCode | string | - | 股票代码（必填） |
| period | PeriodType | 'day' | K线周期 |
| mainIndicator | MainIndicatorType | 'MA' | 主图指标 |
| subIndicator | SubIndicatorType | 'VOL' | 副图指标 |
| signals | TradingSignal[] | [] | 交易信号数组 |
| config | ChartConfig | {} | 图表配置 |
| onPeriodChange | (period) => void | - | 周期变化回调 |
| onIndicatorChange | (main, sub) => void | - | 指标变化回调 |

## 类型定义

### PeriodType
```typescript
type PeriodType = '1min' | '5min' | '15min' | '30min' | '60min' | 'day' | 'week' | 'month'
```

### MainIndicatorType
```typescript
type MainIndicatorType = 'MA' | 'BOLL' | 'SAR' | 'NONE'
```

### SubIndicatorType
```typescript
type SubIndicatorType = 'MACD' | 'RSI' | 'KDJ' | 'VOL' | 'NONE'
```

## 依赖

- `lightweight-charts`: K线图表渲染库
- `antd`: UI组件库
- `react`: React框架

## 注意事项

1. 需要确保后端API提供K线数据接口：`/api/stock/kline/{stockCode}`
2. 数据格式需符合 `KLineData` 接口定义
3. 图表会自动适应容器大小，建议设置固定高度
4. 交易信号标注功能需要后续实现

## 后续优化

- [ ] 实现交易信号标注显示
- [ ] 添加画线工具（趋势线、水平线、斐波那契）
- [ ] 实现图片导出功能
- [ ] 添加更多技术指标
- [ ] 支持自定义指标参数
- [ ] 添加指标计算Web Worker优化
