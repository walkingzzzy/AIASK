/**
 * 数据中心页面
 */
import { useState, useEffect } from 'react'
import { Card, Row, Col, Table, Button, Select, DatePicker, Form, message, Tag, Statistic, Input } from 'antd'
import { DownloadOutlined, SearchOutlined, DatabaseOutlined } from '@ant-design/icons'
import { api } from '@/services/api'

const { RangePicker } = DatePicker
const { Option } = Select

interface DataCategory {
  name: string
  label: string
  description: string
  record_count: number
}

interface DataStatistic {
  category: string
  total_records: number
  latest_update: string
  data_sources: string[]
}

export default function DataCenter() {
  const [loading, setLoading] = useState(false)
  const [categories, setCategories] = useState<DataCategory[]>([])
  const [statistics, setStatistics] = useState<DataStatistic[]>([])
  const [selectedCategory, setSelectedCategory] = useState<string>('')
  const [fields, setFields] = useState<string[]>([])
  const [queryData, setQueryData] = useState<any[]>([])
  const [form] = Form.useForm()

  useEffect(() => {
    loadCategories()
    loadStatistics()
  }, [])

  const loadCategories = async () => {
    try {
      const res = await api.getDataCategories()
      if (res.success) {
        setCategories(res.data)
      }
    } catch (error) {
      console.error('加载分类失败:', error)
    }
  }

  const loadStatistics = async () => {
    try {
      const res = await api.getDataStatistics()
      if (res.success) {
        setStatistics(res.data)
      }
    } catch (error) {
      console.error('加载统计失败:', error)
    }
  }

  const handleCategoryChange = async (category: string) => {
    setSelectedCategory(category)
    try {
      const res = await api.getCategoryFields(category)
      if (res.success) {
        setFields(res.data)
      }
    } catch (error) {
      console.error('加载字段失败:', error)
    }
  }

  const handleQuery = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)

      const params: any = {
        category: selectedCategory,
        limit: 1000
      }

      if (values.stock_codes) {
        params.stock_codes = values.stock_codes.split(',').map((s: string) => s.trim())
      }

      if (values.date_range) {
        params.start_date = values.date_range[0].format('YYYY-MM-DD')
        params.end_date = values.date_range[1].format('YYYY-MM-DD')
      }

      if (values.fields) {
        params.fields = values.fields
      }

      const res = await api.queryData(params)
      if (res.success) {
        setQueryData(res.data)
        message.success(`查询成功，共 ${res.data.length} 条数据`)
      }
    } catch (error) {
      console.error('查询失败:', error)
      message.error('查询数据失败')
    } finally {
      setLoading(false)
    }
  }

  const handleExport = async (format: string) => {
    try {
      const values = await form.validateFields()

      const params: any = {
        category: selectedCategory,
        format: format
      }

      if (values.stock_codes) {
        params.stock_codes = values.stock_codes.split(',').map((s: string) => s.trim())
      }

      if (values.date_range) {
        params.start_date = values.date_range[0].format('YYYY-MM-DD')
        params.end_date = values.date_range[1].format('YYYY-MM-DD')
      }

      if (values.fields) {
        params.fields = values.fields
      }

      const res = await api.exportData(params)
      if (res.success) {
        message.success('导出任务已创建')
      }
    } catch (error) {
      console.error('导出失败:', error)
      message.error('导出数据失败')
    }
  }

  const statColumns = [
    {
      title: '数据类别',
      dataIndex: 'category',
      key: 'category'
    },
    {
      title: '记录数',
      dataIndex: 'total_records',
      key: 'total_records',
      render: (count: number) => count.toLocaleString()
    },
    {
      title: '最后更新',
      dataIndex: 'latest_update',
      key: 'latest_update',
      render: (date: string) => new Date(date).toLocaleString('zh-CN')
    },
    {
      title: '数据源',
      dataIndex: 'data_sources',
      key: 'data_sources',
      render: (sources: string[]) => (
        <div>
          {sources.map(source => (
            <Tag key={source}>{source}</Tag>
          ))}
        </div>
      )
    }
  ]

  return (
    <div className="space-y-4">
      {/* 数据概览 */}
      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic
              title="数据类别"
              value={categories.length}
              suffix="个"
              prefix={<DatabaseOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="总记录数"
              value={statistics.reduce((sum, s) => sum + s.total_records, 0)}
              suffix="条"
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card>
            <div className="text-gray-400 mb-2">可用数据类别</div>
            <div className="flex flex-wrap gap-2">
              {categories.map(cat => (
                <Tag key={cat.name} color="blue">{cat.label}</Tag>
              ))}
            </div>
          </Card>
        </Col>
      </Row>

      {/* 数据统计 */}
      <Card title="数据统计">
        <Table
          columns={statColumns}
          dataSource={statistics}
          rowKey="category"
          pagination={false}
          size="small"
        />
      </Card>

      {/* 数据查询 */}
      <Card title="数据查询">
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="category"
                label="数据类别"
                rules={[{ required: true, message: '请选择数据类别' }]}
              >
                <Select
                  placeholder="选择数据类别"
                  onChange={handleCategoryChange}
                >
                  {categories.map(cat => (
                    <Option key={cat.name} value={cat.name}>
                      {cat.label}
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="stock_codes" label="股票代码">
                <Input placeholder="多个代码用逗号分隔，如: 600519,000858" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="date_range" label="日期范围">
                <RangePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          {selectedCategory && fields.length > 0 && (
            <Form.Item name="fields" label="选择字段">
              <Select mode="multiple" placeholder="选择要查询的字段（不选则查询全部）">
                {fields.map(field => (
                  <Option key={field} value={field}>{field}</Option>
                ))}
              </Select>
            </Form.Item>
          )}

          <Form.Item>
            <div className="flex gap-2">
              <Button
                type="primary"
                icon={<SearchOutlined />}
                onClick={handleQuery}
                loading={loading}
              >
                查询数据
              </Button>
              <Button
                icon={<DownloadOutlined />}
                onClick={() => handleExport('csv')}
                disabled={!selectedCategory}
              >
                导出CSV
              </Button>
              <Button
                icon={<DownloadOutlined />}
                onClick={() => handleExport('excel')}
                disabled={!selectedCategory}
              >
                导出Excel
              </Button>
            </div>
          </Form.Item>
        </Form>
      </Card>

      {/* 查询结果 */}
      {queryData.length > 0 && (
        <Card title={`查询结果 (${queryData.length} 条)`}>
          <div className="overflow-auto">
            <Table
              dataSource={queryData}
              columns={Object.keys(queryData[0] || {}).map(key => ({
                title: key,
                dataIndex: key,
                key: key,
                ellipsis: true
              }))}
              rowKey={(record, index) => index?.toString() || '0'}
              pagination={{ pageSize: 20 }}
              scroll={{ x: 'max-content' }}
              size="small"
            />
          </div>
        </Card>
      )}
    </div>
  )
}
