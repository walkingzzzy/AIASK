/**
 * K线图表主组件
 *
 * 使用 lightweight-charts 库实现专业K线图表
 */
import React, { useEffect, useRef, useState, useCallback } from 'react'
import { Spin, Empty } from 'antd'
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  LineData,
  HistogramData,
  CrosshairMode,
  Time
} from 'lightweight-charts'
import { ChartToolbar } from './ChartToolbar'
import { useKLineData, useIndicatorData } from '@/hooks/useKLineData'
import type {
  KLineChartProps,
  PeriodType,
  MainIndicatorType,
  SubIndicatorType,
  ChartConfig,
  KLineData as KLineDataType
} from './types'

// 默认配置
const defaultConfig: ChartConfig = {
  width: 800,
  height: 600,
  mainHeight: 0.7,
  subHeight: 0.3,
  backgroundColor: '#ffffff',
  textColor: '#333333',
  gridColor: '#f0f0f0',
  upColor: '#ef5350',
  downColor: '#26a69a'
}

// MA颜色配置
const MA_COLORS = {
  MA5: '#f5a623',
  MA10: '#4a90d9',
  MA20: '#7b68ee',
  MA60: '#50c878'
}

export const KLineChart: React.FC<KLineChartProps> = ({
  stockCode,
  period = 'day',
  mainIndicator = 'MA',
  subIndicator = 'VOL',
  signals: _signals = [],
  config = {},
  onPeriodChange,
  onIndicatorChange
}) => {
  const mainChartRef = useRef<HTMLDivElement>(null)
  const subChartRef = useRef<HTMLDivElement>(null)
  const mainChartApiRef = useRef<IChartApi | null>(null)
  const subChartApiRef = useRef<IChartApi | null>(null)
  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const maSeriesRefs = useRef<Map<string, ISeriesApi<'Line'>>>(new Map())
  const bollSeriesRefs = useRef<Map<string, ISeriesApi<'Line'>>>(new Map())
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const subIndicatorSeriesRefs = useRef<Map<string, ISeriesApi<'Line' | 'Histogram'>>>(new Map())

  const [currentPeriod, setCurrentPeriod] = useState<PeriodType>(period)
  const [currentMainIndicator, setCurrentMainIndicator] = useState<MainIndicatorType>(mainIndicator)
  const [currentSubIndicator, setCurrentSubIndicator] = useState<SubIndicatorType>(subIndicator)
  const [tooltipData, setTooltipData] = useState<KLineDataType | null>(null)

  // 获取K线数据
  const { data: klineData, loading, error } = useKLineData(stockCode, currentPeriod)
  
  // 获取指标数据
  const { data: mainIndicatorData } = useIndicatorData(stockCode, currentMainIndicator, currentPeriod)
  const { data: subIndicatorData } = useIndicatorData(stockCode, currentSubIndicator, currentPeriod)

  // 合并配置
  const chartConfig = { ...defaultConfig, ...config }
  const mainHeight = Math.floor((chartConfig.height || 600) * (chartConfig.mainHeight || 0.7))
  const subHeight = Math.floor((chartConfig.height || 600) * (chartConfig.subHeight || 0.3))

  // 清理指标系列
  const clearIndicatorSeries = useCallback((chart: IChartApi | null, seriesMap: Map<string, any>) => {
    if (!chart) return
    seriesMap.forEach((series) => {
      try { chart.removeSeries(series) } catch {}
    })
    seriesMap.clear()
  }, [])

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
        timeVisible: true,
        secondsVisible: false,
        borderColor: chartConfig.gridColor
      },
      rightPriceScale: { borderColor: chartConfig.gridColor }
    })

    mainChartApiRef.current = chart

    const candlestickSeries = chart.addCandlestickSeries({
      upColor: chartConfig.upColor,
      downColor: chartConfig.downColor,
      borderUpColor: chartConfig.upColor,
      borderDownColor: chartConfig.downColor,
      wickUpColor: chartConfig.upColor,
      wickDownColor: chartConfig.downColor
    })
    candlestickSeriesRef.current = candlestickSeries

    // 十字光标数据提示
    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.seriesData) {
        setTooltipData(null)
        return
      }
      const candleData = param.seriesData.get(candlestickSeries) as CandlestickData
      if (candleData) {
        setTooltipData({
          time: param.time as string,
          open: candleData.open,
          high: candleData.high,
          low: candleData.low,
          close: candleData.close,
          volume: 0
        })
      }
    })

    return () => {
      chart.remove()
      mainChartApiRef.current = null
      candlestickSeriesRef.current = null
      maSeriesRefs.current.clear()
      bollSeriesRefs.current.clear()
    }
  }, [])

  // 初始化副图
  useEffect(() => {
    if (!subChartRef.current || currentSubIndicator === 'NONE') return

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
        timeVisible: false,
        borderColor: chartConfig.gridColor
      },
      rightPriceScale: { borderColor: chartConfig.gridColor }
    })

    subChartApiRef.current = chart

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
      subIndicatorSeriesRefs.current.clear()
    }
  }, [currentSubIndicator])

  // 更新K线数据
  useEffect(() => {
    if (!candlestickSeriesRef.current || !klineData.length) return

    const chartData: CandlestickData[] = klineData.map(item => ({
      time: item.time as Time,
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close
    }))

    candlestickSeriesRef.current.setData(chartData)
    mainChartApiRef.current?.timeScale().fitContent()
  }, [klineData])

  // 渲染主图指标
  useEffect(() => {
    const chart = mainChartApiRef.current
    if (!chart || !klineData.length) return

    // 清理旧指标
    clearIndicatorSeries(chart, maSeriesRefs.current)
    clearIndicatorSeries(chart, bollSeriesRefs.current)

    if (currentMainIndicator === 'MA' && mainIndicatorData?.length) {
      // MA指标
      const maKeys = ['MA5', 'MA10', 'MA20', 'MA60']
      maKeys.forEach((key) => {
        const color = MA_COLORS[key as keyof typeof MA_COLORS]
        const series = chart.addLineSeries({ color, lineWidth: 1, priceLineVisible: false })
        const data: LineData[] = mainIndicatorData
          .filter((d: any) => d[key] != null)
          .map((d: any) => ({ time: d.time as Time, value: d[key] }))
        if (data.length) series.setData(data)
        maSeriesRefs.current.set(key, series)
      })
    } else if (currentMainIndicator === 'BOLL' && mainIndicatorData?.length) {
      // BOLL指标
      const bollKeys = [
        { key: 'upper', color: '#f5a623' },
        { key: 'middle', color: '#4a90d9' },
        { key: 'lower', color: '#50c878' }
      ]
      bollKeys.forEach(({ key, color }) => {
        const series = chart.addLineSeries({ color, lineWidth: 1, priceLineVisible: false })
        const data: LineData[] = mainIndicatorData
          .filter((d: any) => d[key] != null)
          .map((d: any) => ({ time: d.time as Time, value: d[key] }))
        if (data.length) series.setData(data)
        bollSeriesRefs.current.set(key, series)
      })
    }
  }, [currentMainIndicator, mainIndicatorData, klineData])

  // 渲染副图指标
  useEffect(() => {
    const chart = subChartApiRef.current
    if (!chart) return

    clearIndicatorSeries(chart, subIndicatorSeriesRefs.current)
    volumeSeriesRef.current = null

    if (currentSubIndicator === 'VOL' && klineData.length) {
      // 成交量
      const volSeries = chart.addHistogramSeries({
        priceFormat: { type: 'volume' },
        priceLineVisible: false
      })
      const volData: HistogramData[] = klineData.map(item => ({
        time: item.time as Time,
        value: item.volume,
        color: item.close >= item.open ? chartConfig.upColor : chartConfig.downColor
      }))
      volSeries.setData(volData)
      volumeSeriesRef.current = volSeries
      subIndicatorSeriesRefs.current.set('VOL', volSeries)
    } else if (currentSubIndicator === 'MACD' && subIndicatorData?.length) {
      // MACD
      const difSeries = chart.addLineSeries({ color: '#f5a623', lineWidth: 1, priceLineVisible: false })
      const deaSeries = chart.addLineSeries({ color: '#4a90d9', lineWidth: 1, priceLineVisible: false })
      const macdSeries = chart.addHistogramSeries({ priceLineVisible: false })

      const difData: LineData[] = subIndicatorData.map((d: any) => ({ time: d.time as Time, value: d.DIF || 0 }))
      const deaData: LineData[] = subIndicatorData.map((d: any) => ({ time: d.time as Time, value: d.DEA || 0 }))
      const macdData: HistogramData[] = subIndicatorData.map((d: any) => ({
        time: d.time as Time,
        value: d.MACD || 0,
        color: (d.MACD || 0) >= 0 ? chartConfig.upColor : chartConfig.downColor
      }))

      difSeries.setData(difData)
      deaSeries.setData(deaData)
      macdSeries.setData(macdData)

      subIndicatorSeriesRefs.current.set('DIF', difSeries)
      subIndicatorSeriesRefs.current.set('DEA', deaSeries)
      subIndicatorSeriesRefs.current.set('MACD', macdSeries)
    } else if (currentSubIndicator === 'KDJ' && subIndicatorData?.length) {
      // KDJ
      const kSeries = chart.addLineSeries({ color: '#f5a623', lineWidth: 1, priceLineVisible: false })
      const dSeries = chart.addLineSeries({ color: '#4a90d9', lineWidth: 1, priceLineVisible: false })
      const jSeries = chart.addLineSeries({ color: '#7b68ee', lineWidth: 1, priceLineVisible: false })

      kSeries.setData(subIndicatorData.map((d: any) => ({ time: d.time as Time, value: d.K || 0 })))
      dSeries.setData(subIndicatorData.map((d: any) => ({ time: d.time as Time, value: d.D || 0 })))
      jSeries.setData(subIndicatorData.map((d: any) => ({ time: d.time as Time, value: d.J || 0 })))

      subIndicatorSeriesRefs.current.set('K', kSeries)
      subIndicatorSeriesRefs.current.set('D', dSeries)
      subIndicatorSeriesRefs.current.set('J', jSeries)
    } else if (currentSubIndicator === 'RSI' && subIndicatorData?.length) {
      // RSI
      const rsiSeries = chart.addLineSeries({ color: '#f5a623', lineWidth: 1, priceLineVisible: false })
      rsiSeries.setData(subIndicatorData.map((d: any) => ({ time: d.time as Time, value: d.RSI || 0 })))
      subIndicatorSeriesRefs.current.set('RSI', rsiSeries)
    }

    chart.timeScale().fitContent()
  }, [currentSubIndicator, subIndicatorData, klineData, chartConfig])

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

  // 事件处理
  const handlePeriodChange = (newPeriod: PeriodType) => {
    setCurrentPeriod(newPeriod)
    onPeriodChange?.(newPeriod)
  }

  const handleMainIndicatorChange = (indicator: MainIndicatorType) => {
    setCurrentMainIndicator(indicator)
    onIndicatorChange?.(indicator, currentSubIndicator)
  }

  const handleSubIndicatorChange = (indicator: SubIndicatorType) => {
    setCurrentSubIndicator(indicator)
    onIndicatorChange?.(currentMainIndicator, indicator)
  }

  const handleZoomIn = () => mainChartApiRef.current?.timeScale().scrollToPosition(5, true)
  const handleZoomOut = () => mainChartApiRef.current?.timeScale().scrollToPosition(-5, true)
  const handleReset = () => mainChartApiRef.current?.timeScale().fitContent()
  const handleExport = () => console.log('导出图片功能待实现')

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Spin size="large" tip="加载K线数据..." />
      </div>
    )
  }

  if (error || !klineData.length) {
    return (
      <div className="h-96">
        <Empty description={error || '暂无K线数据'} />
      </div>
    )
  }

  return (
    <div className="kline-chart-container">
      <ChartToolbar
        period={currentPeriod}
        mainIndicator={currentMainIndicator}
        subIndicator={currentSubIndicator}
        onPeriodChange={handlePeriodChange}
        onMainIndicatorChange={handleMainIndicatorChange}
        onSubIndicatorChange={handleSubIndicatorChange}
        onZoomIn={handleZoomIn}
        onZoomOut={handleZoomOut}
        onReset={handleReset}
        onExport={handleExport}
      />
      
      {/* 数据提示 */}
      {tooltipData && (
        <div className="flex gap-4 px-2 py-1 text-xs bg-gray-50 border-b">
          <span>开: <span className="text-red-500">{tooltipData.open.toFixed(2)}</span></span>
          <span>高: <span className="text-red-500">{tooltipData.high.toFixed(2)}</span></span>
          <span>低: <span className="text-green-500">{tooltipData.low.toFixed(2)}</span></span>
          <span>收: <span className={tooltipData.close >= tooltipData.open ? 'text-red-500' : 'text-green-500'}>
            {tooltipData.close.toFixed(2)}
          </span></span>
        </div>
      )}

      {/* 主图 */}
      <div ref={mainChartRef} style={{ width: '100%', height: mainHeight }} />
      
      {/* 副图 */}
      {currentSubIndicator !== 'NONE' && (
        <div ref={subChartRef} style={{ width: '100%', height: subHeight }} />
      )}
    </div>
  )
}

export default KLineChart
