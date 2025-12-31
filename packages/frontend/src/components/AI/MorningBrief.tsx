import { useState, useEffect, useCallback } from 'react'
import { Card, Typography, Tag, Spin, Empty, List, Badge, Button, Collapse } from 'antd'
import {
  SunOutlined,
  RiseOutlined,
  FallOutlined,
  BulbOutlined,
  WarningOutlined,
  RocketOutlined,
  BookOutlined,
  ReloadOutlined,
  CheckCircleOutlined
} from '@ant-design/icons'
import { api } from '@/services/api'
import styles from './InsightCards.module.css'

const { Text, Paragraph, Title } = Typography

interface MorningBriefData {
  greeting: string
  market_overview: string
  watchlist_summary: Array<{
    stock_code: string
    stock_name: string
    change_percent: number
    status: string
  }>
  sector_highlights: Array<{
    sector: string
    change_percent: number
    highlight: string
  }>
  opportunities: Array<{
    type: string
    title: string
    description: string
  }>
  risk_alerts: Array<{
    type: string
    title: string
    description: string
  }>
  todos?: Array<{
    action: string
    stock_code?: string
    stock_name?: string
    reason: string
    priority: 'high' | 'medium' | 'low'
  }>
  learning_tip: string | null
  ai_insight: string | null
  generated_at: string
}

interface MorningBriefProps {
  userId?: string
  onStockClick?: (stockCode: string) => void
}

export default function MorningBrief({ userId = 'default', onStockClick }: MorningBriefProps) {
  const [loading, setLoading] = useState(true)
  const [brief, setBrief] = useState<MorningBriefData | null>(null)
  const [expandedKeys, setExpandedKeys] = useState<string[]>(['market', 'watchlist', 'opportunities', 'risks', 'todos'])

  const fetchBrief = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.getMorningBrief(userId) as any
      if (res.success) {
        setBrief(res.data)
      }
    } catch (error) {
      console.error('获取早报失败:', error)
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    fetchBrief()
  }, [fetchBrief])

  const handleRefresh = () => {
    fetchBrief()
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <Spin tip="正在生成您的个性化早报..." />
      </div>
    )
  }

  if (!brief) {
    return <Empty description="暂无早报数据" />
  }

  const priorityColors = { high: '#ff4d4f', medium: '#faad14', low: '#52c41a' }

  const collapseItems = [
    {
      key: 'market',
      label: <span><RiseOutlined /> 市场概览</span>,
      children: (
        <Paragraph style={{ margin: 0, color: '#c9d1d9' }}>
          {brief.market_overview}
        </Paragraph>
      )
    },
    brief.watchlist_summary.length > 0 && {
      key: 'watchlist',
      label: <span>📊 自选股动态 <Badge count={brief.watchlist_summary.length} style={{ marginLeft: 8 }} /></span>,
      children: (
        <List
          size="small"
          dataSource={brief.watchlist_summary}
          renderItem={item => (
            <List.Item
              style={{ cursor: 'pointer', padding: '8px 0' }}
              onClick={() => onStockClick?.(item.stock_code)}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
                <span>
                  <Text strong>{item.stock_name}</Text>
                  <Text type="secondary" style={{ marginLeft: 8 }}>{item.stock_code}</Text>
                </span>
                <span style={{ color: item.change_percent >= 0 ? '#52c41a' : '#ff4d4f' }}>
                  {item.change_percent >= 0 ? '+' : ''}{item.change_percent.toFixed(2)}%
                </span>
              </div>
            </List.Item>
          )}
        />
      )
    },
    brief.sector_highlights.length > 0 && {
      key: 'sectors',
      label: <span>🔥 关注板块</span>,
      children: brief.sector_highlights.map((sector, index) => (
        <div key={index} style={{ marginBottom: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Tag color="blue">{sector.sector}</Tag>
            <span style={{ color: sector.change_percent >= 0 ? '#52c41a' : '#ff4d4f' }}>
              {sector.change_percent >= 0 ? <RiseOutlined /> : <FallOutlined />}
              {' '}{Math.abs(sector.change_percent).toFixed(2)}%
            </span>
          </div>
          <Text type="secondary" style={{ fontSize: 12 }}>{sector.highlight}</Text>
        </div>
      ))
    },
    brief.opportunities.length > 0 && {
      key: 'opportunities',
      label: <span><RocketOutlined style={{ color: '#52c41a' }} /> 今日机会 <Badge count={brief.opportunities.length} style={{ marginLeft: 8 }} /></span>,
      children: brief.opportunities.map((opp, index) => (
        <div key={index} style={{ marginBottom: 12 }}>
          <Text strong style={{ color: '#52c41a' }}>{opp.title}</Text>
          <Paragraph style={{ margin: '4px 0 0', fontSize: 12, color: '#8b949e' }}>
            {opp.description}
          </Paragraph>
        </div>
      ))
    },
    brief.risk_alerts.length > 0 && {
      key: 'risks',
      label: <span><WarningOutlined style={{ color: '#ff4d4f' }} /> 风险提示 <Badge count={brief.risk_alerts.length} style={{ marginLeft: 8, backgroundColor: '#ff4d4f' }} /></span>,
      children: brief.risk_alerts.map((alert, index) => (
        <div key={index} style={{ marginBottom: 12 }}>
          <Text strong style={{ color: '#ff4d4f' }}>{alert.title}</Text>
          <Paragraph style={{ margin: '4px 0 0', fontSize: 12, color: '#8b949e' }}>
            {alert.description}
          </Paragraph>
        </div>
      ))
    },
    brief.todos && brief.todos.length > 0 && {
      key: 'todos',
      label: <span><CheckCircleOutlined style={{ color: '#1890ff' }} /> 今日待办 <Badge count={brief.todos.length} style={{ marginLeft: 8, backgroundColor: '#1890ff' }} /></span>,
      children: (
        <List
          size="small"
          dataSource={brief.todos}
          renderItem={item => (
            <List.Item
              style={{ cursor: item.stock_code ? 'pointer' : 'default', padding: '8px 0' }}
              onClick={() => item.stock_code && onStockClick?.(item.stock_code)}
            >
              <div style={{ width: '100%' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Tag color={priorityColors[item.priority]}>{item.action}</Tag>
                  {item.stock_name && <Text strong>{item.stock_name}</Text>}
                </div>
                <Text type="secondary" style={{ fontSize: 12 }}>{item.reason}</Text>
              </div>
            </List.Item>
          )}
        />
      )
    },
    brief.ai_insight && {
      key: 'insight',
      label: <span><BulbOutlined style={{ color: '#1890ff' }} /> AI洞察</span>,
      children: (
        <Paragraph style={{ margin: 0, color: '#c9d1d9' }}>
          {brief.ai_insight}
        </Paragraph>
      )
    }
  ].filter(Boolean) as { key: string; label: React.ReactNode; children: React.ReactNode }[]

  return (
    <div className={styles.insightPanel}>
      {/* 问候语和刷新按钮 */}
      <Card size="small" style={{ marginBottom: 16, background: 'linear-gradient(135deg, #1a1f2e 0%, #2d3748 100%)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <SunOutlined style={{ fontSize: 24, color: '#ffd700' }} />
            <div>
              <Title level={5} style={{ margin: 0, color: '#e6edf3' }}>{brief.greeting}</Title>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {new Date(brief.generated_at).toLocaleString('zh-CN')}
              </Text>
            </div>
          </div>
          <Button
            type="text"
            icon={<ReloadOutlined />}
            onClick={handleRefresh}
            loading={loading}
            style={{ color: '#8b949e' }}
          />
        </div>
      </Card>

      {/* 可折叠内容 */}
      <Collapse
        activeKey={expandedKeys}
        onChange={(keys) => setExpandedKeys(keys as string[])}
        items={collapseItems}
        style={{ background: 'transparent', border: 'none' }}
        expandIconPosition="end"
      />

      {/* 学习提示 */}
      {brief.learning_tip && (
        <Card size="small" style={{ marginTop: 16, background: '#21262d' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            <BookOutlined style={{ color: '#58a6ff', marginTop: 4 }} />
            <Text style={{ color: '#8b949e', fontSize: 13 }}>{brief.learning_tip}</Text>
          </div>
        </Card>
      )}
    </div>
  )
}
