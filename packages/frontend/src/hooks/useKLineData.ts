/**
 * K线数据Hook
 */
import { useState, useEffect, useCallback } from 'react'
import { message } from 'antd'
import type { KLineData, PeriodType } from '@/components/KLineChart/types'
import { api } from '@/services/api'

interface UseKLineDataResult {
  data: KLineData[]
  loading: boolean
  error: string | null
  refresh: () => void
}

export const useKLineData = (
  stockCode: string,
  period: PeriodType = 'day'
): UseKLineDataResult => {
  const [data, setData] = useState<KLineData[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    if (!stockCode) {
      setData([])
      return
    }

    setLoading(true)
    setError(null)

    try {
      // 调用API获取K线数据
      const response: any = await api.getKLineData(stockCode, period)

      if (response.success && response.data) {
        setData(response.data)
      } else {
        throw new Error(response.message || '获取K线数据失败')
      }
    } catch (err: any) {
      const errorMsg = err.message || '获取K线数据失败'
      setError(errorMsg)
      message.error(errorMsg)
      setData([])
    } finally {
      setLoading(false)
    }
  }, [stockCode, period])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  return {
    data,
    loading,
    error,
    refresh: fetchData
  }
}

// 技术指标数据Hook
export const useIndicatorData = (
  stockCode: string,
  indicatorType: string,
  period: PeriodType = 'day'
) => {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!stockCode || indicatorType === 'NONE') {
      setData([])
      return
    }

    const fetchIndicator = async () => {
      setLoading(true)
      try {
        const response: any = await api.getIndicatorData(stockCode, indicatorType, period)
        if (response.success && response.data) {
          setData(response.data)
        }
      } catch (err) {
        console.error('获取指标数据失败:', err)
        setData([])
      } finally {
        setLoading(false)
      }
    }

    fetchIndicator()
  }, [stockCode, indicatorType, period])

  return { data, loading }
}
