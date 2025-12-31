/**
 * 决策复盘组件
 * 展示AI历史建议的准确率和用户决策记录
 */
import { useState, useEffect } from 'react'
import { Card, Typography, Progress, Table, Tag, Empty, Spin, Statistic, Row, Col } from 'antd'
import { 
  CheckCircleOutlined, 
  CloseCircleOutlined,
  RiseOutlined,
  FallOutlined,
  TrophyOutlined
} from '@ant-design/icons'
import { api } from '@/services/api'
import styles from './DecisionReview.module.css'

const { Text, Title } = Typography

// 决策记录
interface DecisionRecord {
  id: string
  stockCode: string
  stockName: string
  action: 'buy' | 'sell' | 'hold'
  reason: string
  priceAtDecision: number
  currentPrice: number
  profitPercent: number
  isCorrect: boolean
  aiSuggested: boolean
  timestamp: string
}

// 复盘统计
interface ReviewStats {
  totalDecisions: number
  correctDecisions: number
  accuracy: number
  totalProfit: number
  avgProfit: number
  bestDecision: DecisionRecord | null
  worstDecision: DecisionRecord | null
  aiAccuracy: number
  userAccuracy: number
}

interface DecisionReviewProps {
  userId?: string
  days?: number
}

export default function DecisionReview({ userId = 'default', days = 30 }: DecisionReviewProps) {
  const [loading, setLoading] = useState(true)
  const [decisions, setDecisions] = useState<DecisionRecord[]>([])
  const [stats, setStats] = useState<ReviewStats | null>(null)

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        // 调用API获取决策记录
        const res = await api.getDecisions(days, 50, userId) as any
        
        if (res.success && res.data && res.data.length > 0) {
          const records: DecisionRecord[] = res.data.map((d: any) => ({
            id: d.id,
            stockCode: d.stock_code,
            stockName: d.stock_name,
            action: d.action,
            reason: d.reason,
            priceAtDecision: d.price_at_decision,
            currentPrice: d.current_price,
            profitPercent: d.profit_percent,
            isCorrect: d.is_correct,
            aiSuggested: d.ai_suggested,
            timestamp: d.timestamp
          }))
          
          setDecisions(records)
          
          // 计算统计
          const correct = records.filter(d => d.isCorrect).length
          const aiDecisions = records.filter(d => d.aiSuggested)
          const aiCorrect = aiDecisions.filter(d => d.isCorrect).length
          const userDecisions = records.filter(d => !d.aiSuggested)
          const userCorrect = userDecisions.filter(d => d.isCorrect).length
          
          const totalProfit = records.reduce((sum, d) => sum + d.profitPercent, 0)
          
          setStats({
            totalDecisions: records.length,
            correctDecisions: correct,
            accuracy: records.length > 0 ? (correct / records.length) * 100 : 0,
            totalProfit,
            avgProfit: records.length > 0 ? totalProfit / records.length : 0,
            bestDecision: records.reduce((best, d) =>
              !best || d.profitPercent > best.profitPercent ? d : best, null as DecisionRecord | null),
            worstDecision: records.reduce((worst, d) =>
              !worst || d.profitPercent < worst.profitPercent ? d : worst, null as DecisionRecord | null),
            aiAccuracy: aiDecisions.length > 0 ? (aiCorrect / aiDecisions.length) * 100 : 0,
            userAccuracy: userDecisions.length > 0 ? (userCorrect / userDecisions.length) * 100 : 0
          })
        } else {
          // 无数据时显示空状态
          setDecisions([])
          setStats(null)
        }
      } catch (error) {
        console.error('获取决策记录失败:', error)
        setDecisions([])
        setStats(null)
      } finally {
        setLoading(false)
      }
    }
    
    fetchData()
  }, [userId, days])

  const columns = [
    {
      title: '股票',
      dataIndex: 'stockName',
      key: 'stockName',
      render: (name: string, record: DecisionRecord) => (
        <div>
          <Text strong>{name}</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 11 }}>{record.stockCode}</Text>
        </div>
      )
    },
    {
      title: '操作',
      dataIndex: 'action',
      key: 'action',
      render: (action: string) => {
        const config = {
          buy: { color: 'green', text: '买入' },
          sell: { color: 'red', text: '卖出' },
          hold: { color: 'blue', text: '持有' }
        }
        const c = config[action as keyof typeof config]
        return <Tag color={c.color}>{c.text}</Tag>
      }
    },
    {
      title: '收益',
      dataIndex: 'profitPercent',
      key: 'profitPercent',
      render: (profit: number) => (
        <span style={{ color: profit >= 0 ? '#52c41a' : '#ff4d4f' }}>
          {profit >= 0 ? <RiseOutlined /> : <FallOutlined />}
          {' '}{profit >= 0 ? '+' : ''}{profit.toFixed(2)}%
        </span>
      )
    },
    {
      title: '来源',
      dataIndex: 'aiSuggested',
      key: 'aiSuggested',
      render: (ai: boolean) => (
        <Tag color={ai ? 'purple' : 'default'}>
          {ai ? 'AI建议' : '个人判断'}
        </Tag>
      )
    },
    {
      title: '结果',
      dataIndex: 'isCorrect',
      key: 'isCorrect',
      render: (correct: boolean) => (
        correct 
          ? <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 18 }} />
          : <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 18 }} />
      )
    }
  ]

  if (loading) {
    return (
      <div className={styles.loading}>
        <Spin tip="加载中..." />
      </div>
    )
  }

  if (!stats || decisions.length === 0) {
    return (
      <Empty 
        description="暂无决策记录"
        className={styles.empty}
      />
    )
  }

  return (
    <div className={styles.container}>
      {/* 统计卡片 */}
      <Card className={styles.statsCard} size="small">
        <Row gutter={16}>
          <Col span={8}>
            <Statistic
              title="总体准确率"
              value={stats.accuracy}
              precision={1}
              suffix="%"
              valueStyle={{ color: stats.accuracy >= 60 ? '#52c41a' : '#ff4d4f' }}
            />
          </Col>
          <Col span={8}>
            <Statistic
              title="AI建议准确率"
              value={stats.aiAccuracy}
              precision={1}
              suffix="%"
              prefix={<TrophyOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Col>
          <Col span={8}>
            <Statistic
              title="平均收益"
              value={stats.avgProfit}
              precision={2}
              suffix="%"
              prefix={stats.avgProfit >= 0 ? '+' : ''}
              valueStyle={{ color: stats.avgProfit >= 0 ? '#52c41a' : '#ff4d4f' }}
            />
          </Col>
        </Row>
      </Card>

      {/* 准确率对比 */}
      <Card className={styles.compareCard} size="small" title="准确率对比">
        <div className={styles.compareItem}>
          <Text>AI建议</Text>
          <Progress 
            percent={stats.aiAccuracy} 
            strokeColor="#722ed1"
            format={p => `${p?.toFixed(1)}%`}
          />
        </div>
        <div className={styles.compareItem}>
          <Text>个人判断</Text>
          <Progress 
            percent={stats.userAccuracy} 
            strokeColor="#1890ff"
            format={p => `${p?.toFixed(1)}%`}
          />
        </div>
      </Card>

      {/* 决策记录表格 */}
      <Card className={styles.tableCard} size="small" title={`最近${days}天决策记录`}>
        <Table
          dataSource={decisions}
          columns={columns}
          rowKey="id"
          size="small"
          pagination={false}
          className={styles.table}
        />
      </Card>

      {/* 最佳/最差决策 */}
      {(stats.bestDecision || stats.worstDecision) && (
        <Row gutter={12}>
          {stats.bestDecision && (
            <Col span={12}>
              <Card className={styles.highlightCard} size="small">
                <div className={styles.highlightTitle}>
                  <RiseOutlined style={{ color: '#52c41a' }} /> 最佳决策
                </div>
                <Text strong>{stats.bestDecision.stockName}</Text>
                <div className={styles.highlightProfit} style={{ color: '#52c41a' }}>
                  +{stats.bestDecision.profitPercent.toFixed(2)}%
                </div>
              </Card>
            </Col>
          )}
          {stats.worstDecision && (
            <Col span={12}>
              <Card className={styles.highlightCard} size="small">
                <div className={styles.highlightTitle}>
                  <FallOutlined style={{ color: '#ff4d4f' }} /> 需改进
                </div>
                <Text strong>{stats.worstDecision.stockName}</Text>
                <div className={styles.highlightProfit} style={{ color: '#ff4d4f' }}>
                  {stats.worstDecision.profitPercent.toFixed(2)}%
                </div>
              </Card>
            </Col>
          )}
        </Row>
      )}
    </div>
  )
}
