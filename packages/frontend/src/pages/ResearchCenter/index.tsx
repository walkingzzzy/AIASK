/**
 * 研报中心页面
 * 支持研报检索、AI分析、评级统计等功能
 */
import { useState, useEffect } from 'react'
import { Card, Row, Col, Table, Tag, Input, Button, Select, Statistic, Tabs, message, Modal, Spin, Descriptions, List, Progress } from 'antd'
import { SearchOutlined, FileTextOutlined, TrophyOutlined, RobotOutlined, BulbOutlined, WarningOutlined, AimOutlined } from '@ant-design/icons'
import { api } from '@/services/api'

const { Search } = Input
const { Option } = Select

interface Report {
  report_id: string
  title: string
  stock_code: string
  stock_name: string
  institution: string
  analyst: string
  rating: string
  target_price?: number
  current_price?: number
  publish_date: string
  summary?: string
  key_points?: string[]
}

interface ReportSummary {
  total_count: number
  by_type: Record<string, number>
  by_rating: Record<string, number>
  recent_reports: Report[]
  hot_stocks: Array<{ stock_code: string; stock_name: string; report_count: number }>
}

interface AnalysisResult {
  report_id: string
  analysis_type: string
  result: any
  generated_at: string
}

export default function ResearchCenter() {
  const [loading, setLoading] = useState(true)
  const [summary, setSummary] = useState<ReportSummary | null>(null)
  const [reports, setReports] = useState<Report[]>([])
  const [searchType, setSearchType] = useState<'keyword' | 'stock' | 'institution'>('keyword')
  const [searchValue, setSearchValue] = useState('')
  
  // AI分析相关
  const [analysisModalVisible, setAnalysisModalVisible] = useState(false)
  const [selectedReport, setSelectedReport] = useState<Report | null>(null)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null)
  const [analysisType, setAnalysisType] = useState('summary')

  useEffect(() => {
    loadSummary()
    loadRecentReports()
  }, [])

  const loadSummary = async () => {
    try {
      const res: any = await api.getResearchSummary()
      if (res.success) {
        setSummary(res.data)
      }
    } catch (error) {
      console.error('加载摘要失败:', error)
    }
  }

  const loadRecentReports = async () => {
    setLoading(true)
    try {
      const res: any = await api.getRecentResearch(7, 20)
      if (res.success) {
        setReports(res.data)
      }
    } catch (error) {
      console.error('加载研报失败:', error)
      message.error('加载研报失败')
    } finally {
      setLoading(false)
    }
  }

  const handleSearch = async () => {
    if (!searchValue.trim()) {
      message.warning('请输入搜索内容')
      return
    }

    setLoading(true)
    try {
      const params: any = { limit: 20 }

      if (searchType === 'keyword') {
        params.keyword = searchValue
      } else if (searchType === 'stock') {
        params.stock_code = searchValue
      } else if (searchType === 'institution') {
        params.institution = searchValue
      }

      const res: any = await api.searchResearch(params)
      if (res.success) {
        setReports(res.data)
      }
    } catch (error) {
      console.error('搜索失败:', error)
      message.error('搜索研报失败')
    } finally {
      setLoading(false)
    }
  }

  const handleAnalyze = async (report: Report) => {
    setSelectedReport(report)
    setAnalysisModalVisible(true)
    setAnalysisResult(null)
    await runAnalysis(report.report_id, 'summary')
  }

  const runAnalysis = async (reportId: string, type: string) => {
    setAnalysisLoading(true)
    setAnalysisType(type)
    try {
      const res: any = await api.analyzeReport(reportId, type)
      if (res.success) {
        setAnalysisResult(res.data)
      } else {
        message.error('分析失败')
      }
    } catch (error) {
      console.error('AI分析失败:', error)
      message.error('AI分析请求失败')
    } finally {
      setAnalysisLoading(false)
    }
  }

  const getRatingColor = (rating: string) => {
    const r = rating.toLowerCase()
    if (r.includes('买入') || r.includes('buy') || r.includes('增持')) return 'red'
    if (r.includes('持有') || r.includes('hold') || r.includes('中性')) return 'blue'
    if (r.includes('卖出') || r.includes('sell') || r.includes('减持')) return 'green'
    return 'default'
  }

  const reportColumns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      width: 280
    },
    {
      title: '股票',
      key: 'stock',
      width: 140,
      render: (_: any, record: Report) => (
        <span>
          {record.stock_name}
          <span className="text-gray-400 text-xs ml-1">({record.stock_code})</span>
        </span>
      )
    },
    {
      title: '机构',
      dataIndex: 'institution',
      key: 'institution',
      width: 100
    },
    {
      title: '评级',
      dataIndex: 'rating',
      key: 'rating',
      width: 80,
      render: (rating: string) => (
        <Tag color={getRatingColor(rating)}>{rating}</Tag>
      )
    },
    {
      title: '目标价',
      dataIndex: 'target_price',
      key: 'target_price',
      width: 90,
      render: (price: number) => price ? `¥${price.toFixed(2)}` : '-'
    },
    {
      title: '发布日期',
      dataIndex: 'publish_date',
      key: 'publish_date',
      width: 100,
      render: (date: string) => new Date(date).toLocaleDateString('zh-CN')
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: any, record: Report) => (
        <Button 
          type="link" 
          icon={<RobotOutlined />}
          onClick={() => handleAnalyze(record)}
        >
          AI分析
        </Button>
      )
    }
  ]

  const hotStockColumns = [
    {
      title: '排名',
      key: 'rank',
      width: 60,
      render: (_: any, __: any, index: number) => {
        const rank = index + 1
        if (rank <= 3) {
          return <TrophyOutlined style={{ color: rank === 1 ? '#ffd700' : rank === 2 ? '#c0c0c0' : '#cd7f32' }} />
        }
        return rank
      }
    },
    {
      title: '股票',
      key: 'stock',
      render: (_: any, record: any) => (
        <span>
          {record.stock_name}
          <span className="text-gray-400 text-xs ml-1">({record.stock_code})</span>
        </span>
      )
    },
    {
      title: '研报数量',
      dataIndex: 'report_count',
      key: 'report_count',
      render: (count: number) => <Tag color="blue">{count} 篇</Tag>
    }
  ]

  // 渲染AI分析结果
  const renderAnalysisResult = () => {
    if (!analysisResult) return null
    
    const { result } = analysisResult
    
    if (analysisType === 'summary') {
      return (
        <div className="space-y-4">
          <Card size="small" title={<><BulbOutlined /> 核心摘要</>}>
            <p>{result.executive_summary}</p>
          </Card>
          
          <Card size="small" title="核心论点">
            <List
              size="small"
              dataSource={result.key_thesis || []}
              renderItem={(item: string) => (
                <List.Item>• {item}</List.Item>
              )}
            />
          </Card>
          
          <Card size="small" title="估值观点">
            <p>{result.valuation_view}</p>
            <div className="mt-2">
              <span className="text-gray-500">置信度：</span>
              <Progress 
                percent={Math.round((result.confidence_score || 0) * 100)} 
                size="small" 
                style={{ width: 150, display: 'inline-block', marginLeft: 8 }}
              />
            </div>
          </Card>
        </div>
      )
    }
    
    if (analysisType === 'key_points') {
      return (
        <div className="space-y-4">
          <Card size="small" title="财务亮点">
            <List
              size="small"
              dataSource={result.financial_highlights || []}
              renderItem={(item: string) => <List.Item>📊 {item}</List.Item>}
            />
          </Card>
          
          <Card size="small" title="业务动态">
            <List
              size="small"
              dataSource={result.business_updates || []}
              renderItem={(item: string) => <List.Item>📈 {item}</List.Item>}
            />
          </Card>
          
          <Card size="small" title="管理层指引">
            <List
              size="small"
              dataSource={result.management_guidance || []}
              renderItem={(item: string) => <List.Item>💼 {item}</List.Item>}
            />
          </Card>
        </div>
      )
    }
    
    if (analysisType === 'risk') {
      return (
        <div className="space-y-4">
          <Card size="small" title={<><WarningOutlined /> 风险识别</>}>
            {(result.identified_risks || []).map((risk: any, index: number) => (
              <Card key={index} size="small" className="mb-2" style={{ background: '#1a1a2e' }}>
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="风险类型">
                    <Tag color="orange">{risk.risk_type}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="描述">{risk.description}</Descriptions.Item>
                  <Descriptions.Item label="严重程度">
                    <Tag color={risk.severity === '高' ? 'red' : risk.severity === '中等' ? 'orange' : 'green'}>
                      {risk.severity}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="缓解措施">{risk.mitigation}</Descriptions.Item>
                </Descriptions>
              </Card>
            ))}
          </Card>
          
          <Row gutter={16}>
            <Col span={12}>
              <Card size="small">
                <Statistic title="整体风险等级" value={result.overall_risk_level} />
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small">
                <Statistic title="风险收益比" value={result.risk_reward_ratio} />
              </Card>
            </Col>
          </Row>
        </div>
      )
    }
    
    if (analysisType === 'target') {
      return (
        <div className="space-y-4">
          <Card size="small" title={<><AimOutlined /> 目标价分析</>}>
            <Row gutter={16}>
              <Col span={8}>
                <Statistic 
                  title="乐观情景" 
                  value={result.target_prices?.bull_case} 
                  prefix="¥"
                  valueStyle={{ color: '#3f8600' }}
                />
              </Col>
              <Col span={8}>
                <Statistic 
                  title="基准情景" 
                  value={result.target_prices?.base_case} 
                  prefix="¥"
                />
              </Col>
              <Col span={8}>
                <Statistic 
                  title="悲观情景" 
                  value={result.target_prices?.bear_case} 
                  prefix="¥"
                  valueStyle={{ color: '#cf1322' }}
                />
              </Col>
            </Row>
          </Card>
          
          <Card size="small" title="估值方法">
            <Table
              size="small"
              pagination={false}
              dataSource={result.valuation_methods || []}
              columns={[
                { title: '方法', dataIndex: 'method', key: 'method' },
                { title: '目标价', dataIndex: 'target', key: 'target', render: (v: number) => `¥${v}` },
                { title: '权重', dataIndex: 'weight', key: 'weight', render: (v: number) => `${v * 100}%` }
              ]}
              rowKey="method"
            />
          </Card>
          
          <Row gutter={16}>
            <Col span={12}>
              <Card size="small">
                <Statistic title="上涨空间" value={result.upside_potential} valueStyle={{ color: '#3f8600' }} />
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small">
                <Statistic title="时间周期" value={result.time_horizon} />
              </Card>
            </Col>
          </Row>
        </div>
      )
    }
    
    return null
  }

  const tabItems = [
    {
      key: '1',
      label: '最新研报',
      children: (
        <Table
          columns={reportColumns}
          dataSource={reports}
          rowKey="report_id"
          loading={loading}
          pagination={{ pageSize: 15 }}
          size="small"
        />
      )
    },
    {
      key: '2',
      label: '热门股票',
      children: (
        <Table
          columns={hotStockColumns}
          dataSource={summary?.hot_stocks || []}
          rowKey="stock_code"
          pagination={false}
          size="small"
        />
      )
    },
    {
      key: '3',
      label: '评级分布',
      children: (
        <Row gutter={16}>
          {summary && Object.entries(summary.by_rating).map(([rating, count]) => (
            <Col span={6} key={rating}>
              <Card>
                <Statistic
                  title={rating}
                  value={count}
                  suffix="篇"
                  valueStyle={{ color: getRatingColor(rating) === 'red' ? '#ef4444' : getRatingColor(rating) === 'blue' ? '#3b82f6' : '#22c55e' }}
                />
              </Card>
            </Col>
          ))}
        </Row>
      )
    }
  ]

  return (
    <div className="space-y-4">
      {/* 研报概览 */}
      {summary && (
        <Row gutter={16}>
          <Col span={6}>
            <Card>
              <Statistic
                title="研报总数"
                value={summary.total_count}
                suffix="篇"
                prefix={<FileTextOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="买入评级"
                value={summary.by_rating['买入'] || 0}
                suffix="篇"
                valueStyle={{ color: '#ef4444' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="持有评级"
                value={summary.by_rating['持有'] || 0}
                suffix="篇"
                valueStyle={{ color: '#3b82f6' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="热门股票"
                value={summary.hot_stocks?.length || 0}
                suffix="只"
              />
            </Card>
          </Col>
        </Row>
      )}

      {/* 搜索栏 */}
      <Card>
        <div className="flex gap-4">
          <Select
            value={searchType}
            onChange={setSearchType}
            style={{ width: 120 }}
          >
            <Option value="keyword">关键词</Option>
            <Option value="stock">股票代码</Option>
            <Option value="institution">机构名称</Option>
          </Select>
          <Search
            placeholder={
              searchType === 'keyword' ? '输入关键词搜索' :
              searchType === 'stock' ? '输入股票代码' :
              '输入机构名称'
            }
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
            onSearch={handleSearch}
            enterButton={<Button type="primary" icon={<SearchOutlined />}>搜索</Button>}
            loading={loading}
          />
        </div>
      </Card>

      {/* 主内容区 */}
      <Card>
        <Tabs items={tabItems} />
      </Card>

      {/* AI分析弹窗 */}
      <Modal
        title={
          <span>
            <RobotOutlined /> AI研报分析 - {selectedReport?.title?.slice(0, 30)}...
          </span>
        }
        open={analysisModalVisible}
        onCancel={() => setAnalysisModalVisible(false)}
        footer={null}
        width={800}
      >
        {selectedReport && (
          <div className="space-y-4">
            {/* 研报基本信息 */}
            <Card size="small">
              <Descriptions column={3} size="small">
                <Descriptions.Item label="股票">{selectedReport.stock_name}</Descriptions.Item>
                <Descriptions.Item label="机构">{selectedReport.institution}</Descriptions.Item>
                <Descriptions.Item label="评级">
                  <Tag color={getRatingColor(selectedReport.rating)}>{selectedReport.rating}</Tag>
                </Descriptions.Item>
              </Descriptions>
            </Card>

            {/* 分析类型选择 */}
            <div className="flex gap-2">
              <Button 
                type={analysisType === 'summary' ? 'primary' : 'default'}
                onClick={() => runAnalysis(selectedReport.report_id, 'summary')}
                loading={analysisLoading && analysisType === 'summary'}
              >
                核心摘要
              </Button>
              <Button 
                type={analysisType === 'key_points' ? 'primary' : 'default'}
                onClick={() => runAnalysis(selectedReport.report_id, 'key_points')}
                loading={analysisLoading && analysisType === 'key_points'}
              >
                关键要点
              </Button>
              <Button 
                type={analysisType === 'risk' ? 'primary' : 'default'}
                onClick={() => runAnalysis(selectedReport.report_id, 'risk')}
                loading={analysisLoading && analysisType === 'risk'}
              >
                风险分析
              </Button>
              <Button 
                type={analysisType === 'target' ? 'primary' : 'default'}
                onClick={() => runAnalysis(selectedReport.report_id, 'target')}
                loading={analysisLoading && analysisType === 'target'}
              >
                目标价
              </Button>
            </div>

            {/* 分析结果 */}
            {analysisLoading ? (
              <div className="text-center py-8">
                <Spin size="large" />
                <div className="mt-4 text-gray-400">AI正在分析研报...</div>
              </div>
            ) : (
              renderAnalysisResult()
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
