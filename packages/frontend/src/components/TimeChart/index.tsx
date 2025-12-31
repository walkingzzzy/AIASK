/**
 * 分时图组件
 * 使用 lightweight-charts 实现A股分时图
 */
import React, { useEffect, useRef, useState, useMemo } from 'react'
import { Empty } from 'antd'
import {
  createChart,
  IChartApi,
  ISeriesApi,
  LineData,
  HistogramData,
  CrosshairMode,
  Time,
  LineStyle,
  LineSeries,
  HistogramSeries
} from 'lightweight-charts'
import type { TimeChartProps, TimeChartConfig, TooltipData } from './types'

// 默认配置
const defaultConfig: TimeChartConfig = {
  width: 800,
  height: 400,
  mainHeight: 0.75,
  subHeight: 0.25,
  backgroundColor: '#ffffff',
  textColor: '#333333',
  gridColor: '#f0f0f0',
  upColor: '#1677ff',      // 上涨蓝色
  downColor: '#52c41a',    // 下跌绿色
  avgLineColor: '#faad14', // 均价线黄色
  prevCloseColor: '#999999',
  showLimitLines: false
}

export const TimeChart: React.FC<TimeChartProps> = ({
  stockCode,
  timeData,
  prevClose,
  limitUp,
  limitDown,
  config = {}
}) => {
  const mainChartRef = useRef<HTMLDivElement>(null)
  const subChartRef = useRef<HTMLDivElement>(null)
  const mainChartApiRef = useRef<IChartApi | null>(null)
  const subChartApiRef = useRef<IChartApi | null>(null)
  const priceSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const avgSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  const [tooltipData, setTooltipData] = useState<TooltipData | null>(null)

  const chartConfig = { ...defaultConfig, ...config }
  const mainHeight = Math.floor((chartConfig.height || 400) * (chartConfig.mainHeight || 0.75))
  const subHeight = Math.floor((chartConfig.height || 400) * (chartConfig.subHeight || 0.25))

  // 转换数据为图表格式
  const { priceData, avgData, volumeData } = useMemo(() => {
    if (!timeData.length) return { priceData: [], avgData: [], volumeData: [] }

    const priceData: LineData[] = []
    const avgData: LineData[] = []
    const volumeData: HistogramData[] = []

    timeData.forEach((item, idx) => {
      const time = idx as Time
      priceData.push({ time, value: item.price })
      avgData.push({ time, value: item.avgPrice })
      
      const isUp = item.price >= prevClose
      volumeData.push({
        time,
        value: item.volume,
        color: isUp ? chartConfig.upColor : chartConfig.downColor
      })
    })

    return { priceData, avgData, volumeData }
  }, [timeData, prevClose, chartConfig.upColor, chartConfig.downColor])

  // 初始化主图
  useEffect(() => {
    if (!mainChartRef.current) return

    const chart = createChart(mainChartRef.current, {
      width: chartConfig.width,
      height: mainHeight,
      layout: {
        background: { color: chartConfig.backgroundColor },
        textColor: chartConfig.textColor
      },
      grid: {
        vertLines: { color: chartConfig.gridColor },
        horzLines: { color: chartConfig.gridColor }
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { labelVisible: true },
        horzLine: { labelVisible: true }
      },
      timeScale: {
        visible: true,
        borderColor: chartConfig.gridColor,
        tickMarkFormatter: (time: number) => {
          if (time >= 0 && time < timeData.length) {
            return timeData[time]?.time || ''
          }
          return ''
        }
      },
      rightPriceScale: {
        borderColor: chartConfig.gridColor,
        scaleMargins: { top: 0.1, bottom: 0.1 }
      }
    })

    mainChartApiRef.current = chart

    // 价格线 - 根据涨跌设置颜色
    const lastPrice = timeData[timeData.length - 1]?.price || prevClose
    const priceColor = lastPrice >= prevClose ? chartConfig.upColor : chartConfig.downColor

    const priceSeries = chart.addSeries(LineSeries, {
      color: priceColor,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true
    })
    priceSeriesRef.current = priceSeries

    // 均价线
    const avgSeries = chart.addSeries(LineSeries, {
      color: chartConfig.avgLineColor,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false
    })
    avgSeriesRef.current = avgSeries

    // 昨收价参考线
    const prevCloseLine = chart.addSeries(LineSeries, {
      color: chartConfig.prevCloseColor,
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false
    })
    if (timeData.length > 0) {
      prevCloseLine.setData([
        { time: 0 as Time, value: prevClose },
        { time: (timeData.length - 1) as Time, value: prevClose }
      ])
    }

    // 涨跌停参考线
    if (chartConfig.showLimitLines && limitUp && limitDown) {
      const limitUpLine = chart.addSeries(LineSeries, {
        color: chartConfig.upColor,
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        priceLineVisible: false,
        lastValueVisible: false
      })
      const limitDownLine = chart.addSeries(LineSeries, {
        color: chartConfig.downColor,
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        priceLineVisible: false,
        lastValueVisible: false
      })
      if (timeData.length > 0) {
        limitUpLine.setData([
          { time: 0 as Time, value: limitUp },
          { time: (timeData.length - 1) as Time, value: limitUp }
        ])
        limitDownLine.setData([
          { time: 0 as Time, value: limitDown },
          { time: (timeData.length - 1) as Time, value: limitDown }
        ])
      }
    }

    // 十字光标数据提示
    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.seriesData) {
        setTooltipData(null)
        return
      }
      const idx = param.time as number
      if (idx >= 0 && idx < timeData.length) {
        const item = timeData[idx]
        const change = item.price - prevClose
        const changePercent = (change / prevClose) * 100
        setTooltipData({
          time: item.time,
          price: item.price,
          avgPrice: item.avgPrice,
          volume: item.volume,
          change,
          changePercent
        })
      }
    })

    return () => {
      chart.remove()
      mainChartApiRef.current = null
    }
  }, [chartConfig, mainHeight, prevClose, limitUp, limitDown, timeData])

  // 初始化副图（成交量）
  useEffect(() => {
    if (!subChartRef.current) return

    const chart = createChart(subChartRef.current, {
      width: chartConfig.width,
      height: subHeight,
      layout: {
        background: { color: chartConfig.backgroundColor },
        textColor: chartConfig.textColor
      },
      grid: {
        vertLines: { color: chartConfig.gridColor },
        horzLines: { color: chartConfig.gridColor }
      },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: {
        visible: false,
        borderColor: chartConfig.gridColor
      },
      rightPriceScale: {
        borderColor: chartConfig.gridColor,
        scaleMargins: { top: 0.1, bottom: 0 }
      }
    })

    subChartApiRef.current = chart

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceLineVisible: false
    })
    volumeSeriesRef.current = volumeSeries

    // 同步主副图时间轴
    if (mainChartApiRef.current) {
      mainChartApiRef.current.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (range) chart.timeScale().setVisibleLogicalRange(range)
      })
      chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (range) mainChartApiRef.current?.timeScale().setVisibleLogicalRange(range)
      })
    }

    return () => {
      chart.remove()
      subChartApiRef.current = null
    }
  }, [chartConfig, subHeight])

  // 更新数据
  useEffect(() => {
    if (priceSeriesRef.current && priceData.length) {
      priceSeriesRef.current.setData(priceData)
    }
    if (avgSeriesRef.current && avgData.length) {
      avgSeriesRef.current.setData(avgData)
    }
    if (volumeSeriesRef.current && volumeData.length) {
      volumeSeriesRef.current.setData(volumeData)
    }
    mainChartApiRef.current?.timeScale().fitContent()
    subChartApiRef.current?.timeScale().fitContent()
  }, [priceData, avgData, volumeData])

  // 响应式调整
  useEffect(() => {
    if (!mainChartRef.current) return

    const resizeObserver = new ResizeObserver(entries => {
      const { width } = entries[0].contentRect
      mainChartApiRef.current?.applyOptions({ width })
      subChartApiRef.current?.applyOptions({ width })
    })

    resizeObserver.observe(mainChartRef.current)
    return () => resizeObserver.disconnect()
  }, [])

  if (!timeData.length) {
    return <Empty description="暂无分时数据" />
  }

  const formatVolume = (vol: number) => {
    if (vol >= 100000000) return (vol / 100000000).toFixed(2) + '亿'
    if (vol >= 10000) return (vol / 10000).toFixed(2) + '万'
    return vol.toString()
  }

  return (
    <div className="time-chart-container">
      {/* 数据提示 */}
      {tooltipData && (
        <div className="flex gap-4 px-2 py-1 text-xs bg-gray-50 border-b">
          <span>时间: {tooltipData.time}</span>
          <span>价格: <span className={tooltipData.change >= 0 ? 'text-blue-500' : 'text-green-500'}>
            {tooltipData.price.toFixed(2)}
          </span></span>
          <span>均价: <span className="text-yellow-500">{tooltipData.avgPrice.toFixed(2)}</span></span>
          <span>涨跌: <span className={tooltipData.change >= 0 ? 'text-blue-500' : 'text-green-500'}>
            {tooltipData.change >= 0 ? '+' : ''}{tooltipData.change.toFixed(2)} ({tooltipData.changePercent >= 0 ? '+' : ''}{tooltipData.changePercent.toFixed(2)}%)
          </span></span>
          <span>成交量: {formatVolume(tooltipData.volume)}</span>
        </div>
      )}

      {/* 主图 - 价格线 */}
      <div ref={mainChartRef} style={{ width: '100%', height: mainHeight }} />
      
      {/* 副图 - 成交量 */}
      <div ref={subChartRef} style={{ width: '100%', height: subHeight }} />
    </div>
  )
}

export default TimeChart
