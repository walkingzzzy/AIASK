/**
 * 估值分析页面
 * 展示股票估值分析和DCF模型
 */
import React, { useState, useEffect } from 'react'
import { Card, Row, Col, Spin, Empty, Tabs, Descriptions, Progress, Table } from 'antd'
import { StockSearch } from '@/components/StockSearch'
import { MetricCard } from '@/components/MetricCard'
import type { ColumnsType } from 'antd/es/table'

const { TabPane } = Tabs

interface ValuationData {
  code: string
  name: string
  current_price: number
  fair_value: number
  valuation_level: string
  pe_ratio: number
  pb_ratio: number
  ps_ratio: number
  pcf_ratio: number
  roe: number
  dcf_value: number
  industry_avg_pe: number
  industry_avg_pb: number
}

interface DCFData {
  discount_rate: number
  growth_rate: number
  terminal_growth_rate: number
  fcf_projections: number[]
  terminal_value: number
  enterprise_value: number
  equity_value: number
  fair_value_per_share: number
}

export const Valuation: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const [stockCode, setStockCode] = useState<string>('600519')
  const [valuationData, setValuationData] = useState<ValuationData | null>(null)
  const [dcfData, setDCFData] = useState<DCFData | null>(null)

  useEffect(() => {
    if (stockCode) {
      fetchValuationData()
    }
  }, [stockCode])

  const fetchValuationData = async () => {
    setLoading(true)
    try {
      const [valuationRes, dcfRes] = await Promise.all([
        fetch(`/api/valuation/${stockCode}`),
        fetch(`/api/valuation/${stockCode}/dcf`)
      ])

      const valuation = await valuationRes.json()
      const dcf = await dcfRes.json()

      setValuationData(valuation.data)
      setDCFData(dcf.data)
    } catch (error) {
      console.error('获取估值数据失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleStockSelect = (code: string, name: string) => {
    setStockCode(code)
  }

  const getValuationColor = (level: string) => {
    const colorMap: Record<string, string> = {
      '严重低估': '#52c41a',
      '低估': '#73d13d',
      '合理': '#1890ff',
      '高估': '#faad14',
      '严重高估': '#f5222d'
    }
    return colorMap[level] || '#1890ff'
  }

  const getValuationScore = (level: string) => {
    const scoreMap: Record<string, number> = {
      '严重低估': 90,
      '低估': 70,
      '合理': 50,
      '高估': 30,
      '严重高估': 10
    }
    return scoreMap[level] || 50
  }

  const dcfColumns: ColumnsType<any> = [
    {
      title: '年份',
      dataIndex: 'year',
      key: 'year'
    },
    {
      title: '预测自由现金流',
      dataIndex: 'fcf',
      key: 'fcf',
      render: (value: number) => `¥${(value / 100000000).toFixed(2)}亿`
    },
    {
      title: '折现因子',
      dataIndex: 'discount_factor',
      key: 'discount_factor',
      render: (value: number) => value.toFixed(4)
    },
    {
      title: '现值',
      dataIndex: 'present_value',
      key: 'present_value',
      render: (value: number) => `¥${(value / 100000000).toFixed(2)}亿`
    }
  ]

  if (loading) {
    return (
      <div className="flex justify-center items-center h-screen">
        <Spin size="large" tip="加载估值数据..." />
      </div>
    )
  }

  return (
    <div className="valuation-page p-6">
      <h1 className="text-2xl font-bold mb-6">估值分析</h1>

      {/* 股票搜索 */}
      <Card className="mb-4">
        <StockSearch onSelect={handleStockSelect} />
      </Card>

      {valuationData ? (
        <>
          {/* 估值概览 */}
          <Row gutter={16} className="mb-4">
            <Col span={6}>
              <MetricCard
                title="当前价格"
                value={valuationData.current_price}
                prefix="¥"
                precision={2}
              />
            </Col>
            <Col span={6}>
              <MetricCard
                title="合理价值"
                value={valuationData.fair_value}
                prefix="¥"
                precision={2}
                trend={valuationData.fair_value > valuationData.current_price ? 'up' : 'down'}
              />
            </Col>
            <Col span={6}>
              <MetricCard
                title="DCF估值"
                value={dcfData?.fair_value_per_share || 0}
                prefix="¥"
                precision={2}
              />
            </Col>
            <Col span={6}>
              <Card>
                <div className="text-gray-600 mb-2">估值水平</div>
                <div
                  className="text-2xl font-bold mb-2"
                  style={{ color: getValuationColor(valuationData.valuation_level) }}
                >
                  {valuationData.valuation_level}
                </div>
                <Progress
                  percent={getValuationScore(valuationData.valuation_level)}
                  strokeColor={getValuationColor(valuationData.valuation_level)}
                  showInfo={false}
                />
              </Card>
            </Col>
          </Row>

          {/* 详细信息 */}
          <Tabs defaultActiveKey="1">
            <TabPane tab="估值指标" key="1">
              <Card>
                <Row gutter={[16, 16]}>
                  <Col span={12}>
                    <Descriptions title="相对估值" column={2} bordered>
                      <Descriptions.Item label="市盈率 (PE)">
                        {valuationData.pe_ratio.toFixed(2)}
                      </Descriptions.Item>
                      <Descriptions.Item label="行业平均PE">
                        {valuationData.industry_avg_pe.toFixed(2)}
                      </Descriptions.Item>
                      <Descriptions.Item label="市净率 (PB)">
                        {valuationData.pb_ratio.toFixed(2)}
                      </Descriptions.Item>
                      <Descriptions.Item label="行业平均PB">
                        {valuationData.industry_avg_pb.toFixed(2)}
                      </Descriptions.Item>
                      <Descriptions.Item label="市销率 (PS)">
                        {valuationData.ps_ratio.toFixed(2)}
                      </Descriptions.Item>
                      <Descriptions.Item label="市现率 (PCF)">
                        {valuationData.pcf_ratio.toFixed(2)}
                      </Descriptions.Item>
                    </Descriptions>
                  </Col>
                  <Col span={12}>
                    <Descriptions title="盈利能力" column={1} bordered>
                      <Descriptions.Item label="净资产收益率 (ROE)">
                        {valuationData.roe.toFixed(2)}%
                      </Descriptions.Item>
                    </Descriptions>
                  </Col>
                </Row>
              </Card>
            </TabPane>

            <TabPane tab="DCF模型" key="2">
              <Card>
                {dcfData && (
                  <>
                    <Descriptions title="模型参数" column={3} bordered className="mb-4">
                      <Descriptions.Item label="折现率">
                        {(dcfData.discount_rate * 100).toFixed(2)}%
                      </Descriptions.Item>
                      <Descriptions.Item label="增长率">
                        {(dcfData.growth_rate * 100).toFixed(2)}%
                      </Descriptions.Item>
                      <Descriptions.Item label="永续增长率">
                        {(dcfData.terminal_growth_rate * 100).toFixed(2)}%
                      </Descriptions.Item>
                    </Descriptions>

                    <Table
                      columns={dcfColumns}
                      dataSource={dcfData.fcf_projections.map((fcf, index) => ({
                        key: index,
                        year: `第${index + 1}年`,
                        fcf,
                        discount_factor: 1 / Math.pow(1 + dcfData.discount_rate, index + 1),
                        present_value: fcf / Math.pow(1 + dcfData.discount_rate, index + 1)
                      }))}
                      pagination={false}
                      summary={() => (
                        <Table.Summary>
                          <Table.Summary.Row>
                            <Table.Summary.Cell index={0} colSpan={3}>
                              <strong>企业价值</strong>
                            </Table.Summary.Cell>
                            <Table.Summary.Cell index={1}>
                              <strong>¥{(dcfData.enterprise_value / 100000000).toFixed(2)}亿</strong>
                            </Table.Summary.Cell>
                          </Table.Summary.Row>
                          <Table.Summary.Row>
                            <Table.Summary.Cell index={0} colSpan={3}>
                              <strong>股权价值</strong>
                            </Table.Summary.Cell>
                            <Table.Summary.Cell index={1}>
                              <strong>¥{(dcfData.equity_value / 100000000).toFixed(2)}亿</strong>
                            </Table.Summary.Cell>
                          </Table.Summary.Row>
                        </Table.Summary>
                      )}
                    />
                  </>
                )}
              </Card>
            </TabPane>
          </Tabs>
        </>
      ) : (
        <Empty description="请搜索股票查看估值分析" />
      )}
    </div>
  )
}

export default Valuation
