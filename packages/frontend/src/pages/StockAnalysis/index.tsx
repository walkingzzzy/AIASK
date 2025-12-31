import { useState } from 'react'
import { Card, Input, Button, Tabs, Row, Col, Spin, Descriptions, Tag, message, Typography } from 'antd'
import { SearchOutlined, LineChartOutlined, HeartOutlined, BankOutlined, SwapOutlined } from '@ant-design/icons'
import { api } from '@/services/api'
import KLineChart from '@/components/KLineChart'

const { Text } = Typography

// 空状态组件
const EmptyState = ({ icon, title, description }: { icon: React.ReactNode, title: string, description: string }) => (
  <div style={{ 
    display: 'flex', 
    flexDirection: 'column', 
    alignItems: 'center', 
    justifyContent: 'center',
    padding: '60px 24px',
  }}>
    <div style={{
      width: 64,
      height: 64,
      borderRadius: 16,
      background: 'rgba(88, 166, 255, 0.1)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: 16,
      color: '#58a6ff',
      fontSize: 28,
    }}>
      {icon}
    </div>
    <Text style={{ fontSize: 16, fontWeight: 500, color: '#e6edf3', marginBottom: 4 }}>
      {title}
    </Text>
    <Text type="secondary">{description}</Text>
  </div>
)

export default function StockAnalysis() {
  const [stockCode, setStockCode] = useState('')
  const [stockName, setStockName] = useState('')
  const [loading, setLoading] = useState(false)
  const [sentiment, setSentiment] = useState<any>(null)
  const [margin, setMargin] = useState<any>(null)
  const [blockTrade, setBlockTrade] = useState<any>(null)
  const [searchedCode, setSearchedCode] = useState('')  // 用于K线图表的股票代码

  const handleSearch = async () => {
    if (!stockCode.trim()) {
      message.warning('请输入股票代码')
      return
    }

    setLoading(true)
    setSearchedCode(stockCode)  // 保存搜索的股票代码用于K线图表

    try {
      const [sentimentRes, marginRes, blockRes] = await Promise.all([
        api.getStockSentiment(stockCode, stockName),
        api.getStockMargin(stockCode, stockName),
        api.getStockBlockTrade(stockCode, stockName)
      ])

      if (sentimentRes.success) setSentiment(sentimentRes.data)
      if (marginRes.success) setMargin(marginRes.data)
      if (blockRes.success) setBlockTrade(blockRes.data)
    } catch (error) {
      message.error('获取数据失败')
    } finally {
      setLoading(false)
    }
  }

  const getSentimentColor = (level: string) => {
    if (level?.includes('看多') || level?.includes('乐观')) return 'red'
    if (level?.includes('看空') || level?.includes('悲观')) return 'green'
    return 'default'
  }

  const tabItems = [
    {
      key: 'kline',
      label: 'K线图表',
      children: searchedCode ? (
        <div style={{ height: 600 }}>
          <KLineChart
            stockCode={searchedCode}
            period="day"
            mainIndicator="MA"
            subIndicator="VOL"
          />
        </div>
      ) : (
        <EmptyState 
          icon={<LineChartOutlined />}
          title="K线图表"
          description="输入股票代码查看K线走势和技术指标"
        />
      )
    },
    {
      key: 'sentiment',
      label: '情绪分析',
      children: sentiment ? (
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="综合情绪">
            <Tag color={getSentimentColor(sentiment.sentiment_level)}>
              {sentiment.sentiment_level || '未知'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="情绪评分">
            {sentiment.overall_score?.toFixed(2) || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="新闻数量">{sentiment.news_count || 0}</Descriptions.Item>
          <Descriptions.Item label="正面新闻">{sentiment.positive_count || 0}</Descriptions.Item>
          <Descriptions.Item label="负面新闻">{sentiment.negative_count || 0}</Descriptions.Item>
          <Descriptions.Item label="中性新闻">{sentiment.neutral_count || 0}</Descriptions.Item>
        </Descriptions>
      ) : (
        <EmptyState 
          icon={<HeartOutlined />}
          title="情绪分析"
          description="分析市场情绪和新闻舆情"
        />
      )
    },
    {
      key: 'margin',
      label: '两融分析',
      children: margin ? (
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="融资趋势">
            <Tag color={margin.financing_trend === '上升' ? 'red' : margin.financing_trend === '下降' ? 'green' : 'default'}>
              {margin.financing_trend || '未知'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="两融信号">
            <Tag color={margin.signal?.includes('多') ? 'red' : margin.signal?.includes('空') ? 'green' : 'default'}>
              {margin.signal || '中性'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="融资变化">{margin.financing_change?.toFixed(2) || '-'} 亿</Descriptions.Item>
          <Descriptions.Item label="变化比例">{margin.financing_change_pct?.toFixed(2) || '-'}%</Descriptions.Item>
          <Descriptions.Item label="日均净买入">{margin.financing_avg_daily?.toFixed(2) || '-'} 亿</Descriptions.Item>
          <Descriptions.Item label="信号强度">{(margin.signal_strength * 100)?.toFixed(0) || '-'}%</Descriptions.Item>
        </Descriptions>
      ) : (
        <EmptyState 
          icon={<BankOutlined />}
          title="两融分析"
          description="查看融资融券数据和趋势"
        />
      )
    },
    {
      key: 'block',
      label: '大宗交易',
      children: blockTrade ? (
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="交易笔数">{blockTrade.trade_count || 0} 笔</Descriptions.Item>
          <Descriptions.Item label="交易信号">
            <Tag color={blockTrade.signal?.includes('利好') ? 'red' : blockTrade.signal?.includes('利空') ? 'green' : 'default'}>
              {blockTrade.signal || '中性'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="总成交额">{blockTrade.total_amount?.toFixed(2) || '-'} 亿</Descriptions.Item>
          <Descriptions.Item label="平均溢价率">
            <span className={blockTrade.avg_premium_rate > 0 ? 'text-red-500' : 'text-green-500'}>
              {blockTrade.avg_premium_rate?.toFixed(2) || '-'}%
            </span>
          </Descriptions.Item>
          <Descriptions.Item label="溢价成交">{blockTrade.premium_trades || 0} 笔</Descriptions.Item>
          <Descriptions.Item label="折价成交">{blockTrade.discount_trades || 0} 笔</Descriptions.Item>
        </Descriptions>
      ) : (
        <EmptyState 
          icon={<SwapOutlined />}
          title="大宗交易"
          description="查看大宗交易记录和溢价情况"
        />
      )
    }
  ]

  return (
    <div className="space-y-4">
      {/* 搜索框 */}
      <Card>
        <Row gutter={16}>
          <Col span={8}>
            <Input
              placeholder="股票代码，如 600519"
              value={stockCode}
              onChange={(e) => setStockCode(e.target.value)}
              onPressEnter={handleSearch}
            />
          </Col>
          <Col span={8}>
            <Input
              placeholder="股票名称（可选）"
              value={stockName}
              onChange={(e) => setStockName(e.target.value)}
            />
          </Col>
          <Col span={8}>
            <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch} loading={loading}>
              分析股票
            </Button>
          </Col>
        </Row>
      </Card>

      {/* 分析结果 */}
      {loading ? (
        <div className="flex justify-center items-center h-64">
          <Spin size="large" />
        </div>
      ) : (
        <Card>
          <Tabs items={tabItems} />
        </Card>
      )}
    </div>
  )
}
