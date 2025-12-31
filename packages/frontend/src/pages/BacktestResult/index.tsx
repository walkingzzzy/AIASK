/**
 * 回测结果可视化主页面
 */
import { useState, useEffect } from 'react'
import { Card, Tabs, Row, Col, Select, DatePicker, Button, Space, message, Spin } from 'antd'
import { DownloadOutlined, PlayCircleOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { MetricsPanel } from './MetricsPanel'
import { EquityCurve } from './EquityCurve'
import { TradeList } from './TradeList'
import { DrawdownChart } from './DrawdownChart'
import { api, BacktestParams } from '@/services/api'
import type { BacktestResult as LocalBacktestResult, BacktestMetrics, Trade, EquityPoint, DrawdownPeriod } from './types'

const { RangePicker } = DatePicker

export default function BacktestResult() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<LocalBacktestResult | null>(null)
  const [selectedStrategy, setSelectedStrategy] = useState('ai_score')
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs().subtract(1, 'year'),
    dayjs()
  ])
  const [strategies, setStrategies] = useState<any[]>([])

  // 加载可用策略
  useEffect(() => {
    loadStrategies()
  }, [])

  const loadStrategies = async () => {
    try {
      const res: any = await api.getBacktestStrategies()
      if (res.success) {
        setStrategies(res.data)
      }
    } catch (error) {
      console.error('加载策略失败:', error)
    }
  }

  // 转换API响应为本地类型
  const transformResult = (apiData: any): LocalBacktestResult => {
    const metrics: BacktestMetrics = {
      totalReturn: apiData.metrics.total_return,
      annualReturn: apiData.metrics.annual_return,
      sharpeRatio: apiData.metrics.sharpe_ratio,
      maxDrawdown: apiData.metrics.max_drawdown,
      maxDrawdownDuration: apiData.metrics.max_drawdown_duration,
      volatility: apiData.metrics.volatility,
      winRate: apiData.metrics.win_rate,
      profitFactor: apiData.metrics.profit_factor,
      totalTrades: apiData.metrics.total_trades,
      winningTrades: apiData.metrics.winning_trades,
      losingTrades: apiData.metrics.losing_trades,
      avgProfit: apiData.metrics.avg_profit,
      avgLoss: apiData.metrics.avg_loss,
      maxProfit: apiData.metrics.max_profit,
      maxLoss: apiData.metrics.max_loss
    }

    const equityCurve: EquityPoint[] = (apiData.equity_curve || []).map((p: any) => ({
      date: p.date,
      equity: p.equity,
      benchmark: p.benchmark,
      drawdown: p.daily_return
    }))

    const trades: Trade[] = (apiData.trades || []).map((t: any) => ({
      id: String(t.id),
      date: t.date,
      type: t.action === '买入' ? 'buy' : 'sell',
      price: t.price,
      quantity: t.quantity,
      amount: t.amount,
      profit: t.pnl,
      profitPercent: t.pnl_percent,
      commission: 0
    }))

    const drawdownPeriods: DrawdownPeriod[] = (apiData.drawdown_periods || []).map((d: any) => ({
      startDate: d.start_date,
      endDate: d.end_date,
      drawdown: d.drawdown,
      duration: d.duration
    }))

    return {
      strategyName: apiData.strategy_name,
      stockCode: '',
      stockName: '',
      startDate: apiData.start_date,
      endDate: apiData.end_date,
      initialCapital: apiData.initial_capital,
      finalCapital: apiData.final_capital,
      metrics,
      equityCurve,
      trades,
      drawdownPeriods
    }
  }

  const handleRunBacktest = async () => {
    setLoading(true)
    try {
      const params: BacktestParams = {
        strategy: selectedStrategy,
        start_date: dateRange[0].format('YYYY-MM-DD'),
        end_date: dateRange[1].format('YYYY-MM-DD'),
        initial_capital: 1000000,
        holding_days: 20
      }
      
      const res: any = await api.runBacktest(params)
      if (res.success) {
        setResult(transformResult(res.data))
        message.success('回测完成')
      } else {
        message.error('回测失败')
      }
    } catch (error) {
      console.error('回测失败:', error)
      message.error('回测请求失败')
    } finally {
      setLoading(false)
    }
  }

  const handleExport = () => {
    if (!result) {
      message.warning('请先运行回测')
      return
    }
    
    // 导出为JSON
    const dataStr = JSON.stringify(result, null, 2)
    const blob = new Blob([dataStr], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `backtest_${selectedStrategy}_${dateRange[0].format('YYYYMMDD')}.json`
    a.click()
    URL.revokeObjectURL(url)
    message.success('导出成功')
  }

  const tabItems = [
    {
      key: 'overview',
      label: '概览',
      children: result ? (
        <div className="space-y-4">
          <MetricsPanel metrics={result.metrics} />
        </div>
      ) : (
        <div className="text-center text-gray-400 py-8">请先运行回测</div>
      )
    },
    {
      key: 'equity',
      label: '收益曲线',
      children: result ? (
        <EquityCurve data={result.equityCurve} loading={loading} height={500} />
      ) : (
        <div className="text-center text-gray-400 py-8">请先运行回测</div>
      )
    },
    {
      key: 'trades',
      label: '交易记录',
      children: result ? (
        <TradeList trades={result.trades} />
      ) : (
        <div className="text-center text-gray-400 py-8">请先运行回测</div>
      )
    },
    {
      key: 'drawdown',
      label: '回撤分析',
      children: result ? (
        <DrawdownChart drawdownPeriods={result.drawdownPeriods} />
      ) : (
        <div className="text-center text-gray-400 py-8">请先运行回测</div>
      )
    }
  ]

  return (
    <div className="space-y-4">
      {/* 控制栏 */}
      <Card>
        <Row gutter={16} align="middle">
          <Col span={6}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <span className="text-sm text-gray-500">策略选择</span>
              <Select
                style={{ width: '100%' }}
                value={selectedStrategy}
                onChange={setSelectedStrategy}
                options={strategies.map(s => ({ label: s.name, value: s.id }))}
                placeholder="选择回测策略"
              />
            </Space>
          </Col>
          <Col span={8}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <span className="text-sm text-gray-500">时间范围</span>
              <RangePicker 
                style={{ width: '100%' }} 
                value={dateRange}
                onChange={(dates) => dates && setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs])}
              />
            </Space>
          </Col>
          <Col span={10}>
            <Space style={{ float: 'right', marginTop: 20 }}>
              <Button 
                type="primary"
                icon={<PlayCircleOutlined />} 
                onClick={handleRunBacktest} 
                loading={loading}
              >
                运行回测
              </Button>
              <Button icon={<DownloadOutlined />} onClick={handleExport} disabled={!result}>
                导出报告
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* 加载状态 */}
      {loading && (
        <Card>
          <div className="text-center py-12">
            <Spin size="large" />
            <div className="mt-4 text-gray-400">正在运行回测...</div>
          </div>
        </Card>
      )}

      {/* 基本信息 */}
      {result && !loading && (
        <Card size="small">
          <Row gutter={16}>
            <Col span={4}>
              <div className="text-sm text-gray-500">策略名称</div>
              <div className="text-base font-medium">{result.strategyName}</div>
            </Col>
            <Col span={4}>
              <div className="text-sm text-gray-500">回测周期</div>
              <div className="text-base font-medium">
                {result.startDate} ~ {result.endDate}
              </div>
            </Col>
            <Col span={4}>
              <div className="text-sm text-gray-500">初始资金</div>
              <div className="text-base font-medium">
                ¥{result.initialCapital.toLocaleString()}
              </div>
            </Col>
            <Col span={4}>
              <div className="text-sm text-gray-500">最终资金</div>
              <div className="text-base font-medium">
                ¥{result.finalCapital.toLocaleString()}
              </div>
            </Col>
            <Col span={4}>
              <div className="text-sm text-gray-500">总收益率</div>
              <div className="text-base font-medium" style={{
                color: result.metrics.totalReturn >= 0 ? '#3f8600' : '#cf1322'
              }}>
                {result.metrics.totalReturn >= 0 ? '+' : ''}{result.metrics.totalReturn}%
              </div>
            </Col>
            <Col span={4}>
              <div className="text-sm text-gray-500">夏普比率</div>
              <div className="text-base font-medium">
                {result.metrics.sharpeRatio}
              </div>
            </Col>
          </Row>
        </Card>
      )}

      {/* 结果展示 */}
      {!loading && (
        <Card>
          <Tabs items={tabItems} />
        </Card>
      )}
    </div>
  )
}
