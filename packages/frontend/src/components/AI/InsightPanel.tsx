import { useState, useEffect, useMemo } from 'react'
import { Tabs, Spin, Empty, Badge, message, Select, Space } from 'antd'
import {
  RocketOutlined,
  WarningOutlined,
  BulbOutlined,
  ReloadOutlined,
  SortAscendingOutlined
} from '@ant-design/icons'
import OpportunityCard, { Opportunity } from './OpportunityCard'
import RiskAlertCard, { RiskAlert } from './RiskAlertCard'
import InsightCard, { Insight } from './InsightCard'
import { api } from '@/services/api'
import styles from './InsightCards.module.css'

interface InsightPanelProps {
  watchlist?: string[]
  holdings?: string[]
  onStockClick?: (stockCode: string) => void
}

interface InsightSummary {
  opportunities: { items: Opportunity[]; total: number }
  risks: { items: RiskAlert[]; total: number; critical_count: number }
  insights: { items: Insight[]; total: number }
}

type SortOption = 'time' | 'confidence' | 'urgency'
type FilterOption = 'all' | string

export default function InsightPanel({
  watchlist = [],
  holdings = [],
  onStockClick
}: InsightPanelProps) {
  const [loading, setLoading] = useState(false)
  const [summary, setSummary] = useState<InsightSummary | null>(null)
  const [activeTab, setActiveTab] = useState('opportunities')
  const [sortBy, setSortBy] = useState<SortOption>('time')
  const [filterType, setFilterType] = useState<FilterOption>('all')

  const fetchInsights = async () => {
    setLoading(true)
    try {
      const res = await api.getInsightSummary({
        user_id: 'default',
        watchlist,
        holdings,
        investment_style: 'balanced',
        risk_tolerance: 3,
        focus_sectors: []
      }) as any
      
      if (res.success) {
        setSummary(res.data)
      }
    } catch (error) {
      console.error('获取洞察失败:', error)
      message.error('获取洞察数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchInsights()
  }, [watchlist.join(','), holdings.join(',')])

  const handleOpportunityClick = (opp: Opportunity) => {
    onStockClick?.(opp.stock_code)
  }

  const handleRiskClick = (alert: RiskAlert) => {
    onStockClick?.(alert.stock_code)
  }

  // 排序和筛选机会
  const filteredOpportunities = useMemo(() => {
    if (!summary?.opportunities.items) return []
    let items = [...summary.opportunities.items]
    if (filterType !== 'all') {
      items = items.filter(o => o.type === filterType)
    }
    items.sort((a, b) => {
      if (sortBy === 'confidence') return b.confidence - a.confidence
      if (sortBy === 'urgency') {
        const order = { high: 0, medium: 1, low: 2 }
        return (order[a.urgency as keyof typeof order] ?? 2) - (order[b.urgency as keyof typeof order] ?? 2)
      }
      return new Date(b.detected_at).getTime() - new Date(a.detected_at).getTime()
    })
    return items
  }, [summary?.opportunities.items, sortBy, filterType])

  // 排序和筛选风险
  const filteredRisks = useMemo(() => {
    if (!summary?.risks.items) return []
    let items = [...summary.risks.items]
    if (filterType !== 'all') {
      items = items.filter(r => r.severity === filterType || r.type === filterType)
    }
    items.sort((a, b) => {
      if (sortBy === 'urgency') {
        const order = { critical: 0, warning: 1, info: 2 }
        return (order[a.severity as keyof typeof order] ?? 2) - (order[b.severity as keyof typeof order] ?? 2)
      }
      return new Date(b.detected_at).getTime() - new Date(a.detected_at).getTime()
    })
    return items
  }, [summary?.risks.items, sortBy, filterType])

  // 筛选选项
  const opportunityFilterOptions = [
    { value: 'all', label: '全部类型' },
    { value: 'buy_signal', label: '买入信号' },
    { value: 'breakout', label: '突破形态' },
    { value: 'fund_inflow', label: '资金流入' },
    { value: 'sector_rotation', label: '板块轮动' },
  ]

  const riskFilterOptions = [
    { value: 'all', label: '全部级别' },
    { value: 'critical', label: '严重' },
    { value: 'warning', label: '警告' },
    { value: 'info', label: '提示' },
  ]

  const sortOptions = [
    { value: 'time', label: '最新' },
    { value: 'confidence', label: '置信度' },
    { value: 'urgency', label: '紧急度' },
  ]

  const tabItems = [
    {
      key: 'opportunities',
      label: (
        <span>
          <RocketOutlined />
          机会
          {summary && <Badge count={summary.opportunities.total} style={{ marginLeft: 6 }} />}
        </span>
      ),
      children: (
        <div className={styles.tabContent}>
          <div className={styles.filterBar}>
            <Select size="small" value={filterType} onChange={setFilterType} options={opportunityFilterOptions} style={{ width: 100 }} />
            <Select size="small" value={sortBy} onChange={setSortBy} options={sortOptions} style={{ width: 90 }} suffixIcon={<SortAscendingOutlined />} />
          </div>
          {loading ? (
            <div className={styles.loadingState}><Spin /></div>
          ) : filteredOpportunities.length ? (
            filteredOpportunities.map(opp => (
              <OpportunityCard
                key={opp.id}
                opportunity={opp}
                onClick={handleOpportunityClick}
              />
            ))
          ) : (
            <Empty description="暂无投资机会" className={styles.emptyState} />
          )}
        </div>
      )
    },
    {
      key: 'risks',
      label: (
        <span>
          <WarningOutlined />
          风险
          {summary && summary.risks.critical_count > 0 && (
            <Badge count={summary.risks.critical_count} style={{ marginLeft: 6, backgroundColor: '#ff4d4f' }} />
          )}
        </span>
      ),
      children: (
        <div className={styles.tabContent}>
          <div className={styles.filterBar}>
            <Select size="small" value={filterType} onChange={setFilterType} options={riskFilterOptions} style={{ width: 100 }} />
            <Select size="small" value={sortBy} onChange={setSortBy} options={sortOptions.filter(o => o.value !== 'confidence')} style={{ width: 90 }} suffixIcon={<SortAscendingOutlined />} />
          </div>
          {loading ? (
            <div className={styles.loadingState}><Spin /></div>
          ) : filteredRisks.length ? (
            filteredRisks.map(alert => (
              <RiskAlertCard
                key={alert.id}
                alert={alert}
                onClick={handleRiskClick}
              />
            ))
          ) : (
            <Empty description="暂无风险预警" className={styles.emptyState} />
          )}
        </div>
      )
    },
    {
      key: 'insights',
      label: (
        <span>
          <BulbOutlined />
          洞察
          {summary && <Badge count={summary.insights.total} style={{ marginLeft: 6 }} />}
        </span>
      ),
      children: (
        <div className={styles.tabContent}>
          {loading ? (
            <div className={styles.loadingState}><Spin /></div>
          ) : summary?.insights.items.length ? (
            summary.insights.items.map(insight => (
              <InsightCard key={insight.id} insight={insight} />
            ))
          ) : (
            <Empty description="暂无AI洞察" className={styles.emptyState} />
          )}
        </div>
      )
    }
  ]

  return (
    <div className={styles.insightPanel}>
      <div className={styles.panelHeader}>
        <span className={styles.panelTitle}>智能洞察</span>
        <ReloadOutlined 
          spin={loading} 
          onClick={fetchInsights}
          style={{ cursor: 'pointer', color: '#58a6ff' }}
        />
      </div>

      {summary && (
        <div className={styles.summaryStats}>
          <div className={styles.statCard}>
            <div className={styles.statValue} style={{ color: '#52c41a' }}>
              {summary.opportunities.total}
            </div>
            <div className={styles.statLabel}>投资机会</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statValue} style={{ color: '#ff4d4f' }}>
              {summary.risks.critical_count}
            </div>
            <div className={styles.statLabel}>严重风险</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statValue} style={{ color: '#1890ff' }}>
              {summary.insights.total}
            </div>
            <div className={styles.statLabel}>AI洞察</div>
          </div>
        </div>
      )}

      <Tabs 
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        size="small"
      />
    </div>
  )
}
