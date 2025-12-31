/**
 * 回测结果相关类型定义
 */

// 交易记录
export interface Trade {
  id: string
  date: string
  type: 'buy' | 'sell'
  price: number
  quantity: number
  amount: number
  profit?: number
  profitPercent?: number
  commission: number
}

// 回测指标
export interface BacktestMetrics {
  totalReturn: number          // 总收益率
  annualReturn: number         // 年化收益率
  sharpeRatio: number          // 夏普比率
  maxDrawdown: number          // 最大回撤
  maxDrawdownDuration: number  // 最大回撤持续天数
  volatility: number           // 波动率
  winRate: number              // 胜率
  profitFactor: number         // 盈亏比
  totalTrades: number          // 总交易次数
  winningTrades: number        // 盈利交易次数
  losingTrades: number         // 亏损交易次数
  avgProfit: number            // 平均盈利
  avgLoss: number              // 平均亏损
  maxProfit: number            // 最大单笔盈利
  maxLoss: number              // 最大单笔亏损
}

// 资金曲线数据点
export interface EquityPoint {
  date: string
  equity: number        // 账户权益
  benchmark?: number    // 基准收益
  drawdown?: number     // 回撤
}

// 回测结果
export interface BacktestResult {
  strategyName: string
  stockCode: string
  stockName: string
  startDate: string
  endDate: string
  initialCapital: number
  finalCapital: number
  metrics: BacktestMetrics
  equityCurve: EquityPoint[]
  trades: Trade[]
  drawdownPeriods: DrawdownPeriod[]
}

// 回撤区间
export interface DrawdownPeriod {
  startDate: string
  endDate: string
  drawdown: number
  duration: number
}

// 策略对比数据
export interface StrategyComparison {
  strategies: {
    name: string
    metrics: BacktestMetrics
    equityCurve: EquityPoint[]
  }[]
}
