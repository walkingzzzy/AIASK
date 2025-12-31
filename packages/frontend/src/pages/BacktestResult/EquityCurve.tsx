/**
 * 收益曲线组件
 */
import React, { useEffect, useRef } from 'react'
import { Empty, Spin } from 'antd'
import * as echarts from 'echarts'
import type { EquityPoint } from './types'

interface EquityCurveProps {
  data: EquityPoint[]
  loading?: boolean
  height?: number
}

export const EquityCurve: React.FC<EquityCurveProps> = ({
  data,
  loading = false,
  height = 400
}) => {
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstanceRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    if (!chartRef.current || !data.length) return

    // 初始化图表
    if (!chartInstanceRef.current) {
      chartInstanceRef.current = echarts.init(chartRef.current)
    }

    const chart = chartInstanceRef.current

    // 准备数据
    const dates = data.map(item => item.date)
    const equityData = data.map(item => item.equity)
    const benchmarkData = data.map(item => item.benchmark || null)
    const drawdownData = data.map(item => (item.drawdown || 0) * 100)

    // 配置图表
    const option: echarts.EChartsOption = {
      title: {
        text: '资金曲线',
        left: 'center'
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross'
        },
        formatter: (params: any) => {
          let result = `${params[0].axisValue}<br/>`
          params.forEach((item: any) => {
            if (item.seriesName === '回撤') {
              result += `${item.marker}${item.seriesName}: ${item.value.toFixed(2)}%<br/>`
            } else {
              result += `${item.marker}${item.seriesName}: ¥${item.value.toLocaleString()}<br/>`
            }
          })
          return result
        }
      },
      legend: {
        data: ['账户权益', '基准收益', '回撤'],
        top: 30
      },
      grid: [
        {
          left: '10%',
          right: '10%',
          top: '15%',
          height: '55%'
        },
        {
          left: '10%',
          right: '10%',
          top: '75%',
          height: '15%'
        }
      ],
      xAxis: [
        {
          type: 'category',
          data: dates,
          gridIndex: 0,
          axisLabel: {
            formatter: (value: string) => value.slice(5)
          }
        },
        {
          type: 'category',
          data: dates,
          gridIndex: 1,
          axisLabel: {
            show: true,
            formatter: (value: string) => value.slice(5)
          }
        }
      ],
      yAxis: [
        {
          type: 'value',
          gridIndex: 0,
          name: '权益',
          axisLabel: {
            formatter: (value: number) => `¥${(value / 10000).toFixed(1)}万`
          }
        },
        {
          type: 'value',
          gridIndex: 1,
          name: '回撤%',
          inverse: true,
          axisLabel: {
            formatter: (value: number) => `${value.toFixed(1)}%`
          }
        }
      ],
      series: [
        {
          name: '账户权益',
          type: 'line',
          data: equityData,
          xAxisIndex: 0,
          yAxisIndex: 0,
          smooth: true,
          symbol: 'none',
          lineStyle: {
            color: '#1890ff',
            width: 2
          },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(24, 144, 255, 0.3)' },
              { offset: 1, color: 'rgba(24, 144, 255, 0.05)' }
            ])
          }
        },
        {
          name: '基准收益',
          type: 'line',
          data: benchmarkData,
          xAxisIndex: 0,
          yAxisIndex: 0,
          smooth: true,
          symbol: 'none',
          lineStyle: {
            color: '#52c41a',
            width: 1,
            type: 'dashed'
          }
        },
        {
          name: '回撤',
          type: 'line',
          data: drawdownData,
          xAxisIndex: 1,
          yAxisIndex: 1,
          smooth: true,
          symbol: 'none',
          lineStyle: {
            color: '#ff4d4f',
            width: 1
          },
          areaStyle: {
            color: 'rgba(255, 77, 79, 0.2)'
          }
        }
      ],
      dataZoom: [
        {
          type: 'inside',
          xAxisIndex: [0, 1],
          start: 0,
          end: 100
        },
        {
          type: 'slider',
          xAxisIndex: [0, 1],
          start: 0,
          end: 100,
          bottom: 10
        }
      ]
    }

    chart.setOption(option)

    // 响应式调整
    const resizeHandler = () => {
      chart.resize()
    }
    window.addEventListener('resize', resizeHandler)

    return () => {
      window.removeEventListener('resize', resizeHandler)
    }
  }, [data])

  // 清理图表
  useEffect(() => {
    return () => {
      if (chartInstanceRef.current) {
        chartInstanceRef.current.dispose()
        chartInstanceRef.current = null
      }
    }
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center" style={{ height }}>
        <Spin size="large" tip="加载数据..." />
      </div>
    )
  }

  if (!data.length) {
    return (
      <div style={{ height }}>
        <Empty description="暂无数据" />
      </div>
    )
  }

  return <div ref={chartRef} style={{ width: '100%', height }} />
}
