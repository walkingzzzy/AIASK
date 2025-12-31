/**
 * 添加股票弹窗组件
 */
import React, { useState } from 'react'
import { Modal, Input, Form, message, Spin } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { api } from '@/services/api'

interface AddStockModalProps {
  visible: boolean
  onCancel: () => void
  onAdd: (stockCode: string, stockName: string) => void
}

export const AddStockModal: React.FC<AddStockModalProps> = ({
  visible,
  onCancel,
  onAdd
}) => {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [stockName, setStockName] = useState('')

  // 搜索股票信息
  const handleSearch = async () => {
    const stockCode = form.getFieldValue('stockCode')
    if (!stockCode || !stockCode.trim()) {
      message.warning('请输入股票代码')
      return
    }

    setLoading(true)
    try {
      const result = await api.getStockQuote(stockCode.trim())
      if (result.success && result.data) {
        setStockName(result.data.name || '')
        form.setFieldsValue({ stockName: result.data.name || '' })
        message.success('股票信息获取成功')
      } else {
        message.error('未找到该股票')
        setStockName('')
      }
    } catch (error) {
      message.error('获取股票信息失败')
      setStockName('')
    } finally {
      setLoading(false)
    }
  }

  // 提交添加
  const handleOk = async () => {
    try {
      const values = await form.validateFields()
      const stockCode = values.stockCode.trim()
      const stockName = values.stockName?.trim() || stockCode

      onAdd(stockCode, stockName)
      form.resetFields()
      setStockName('')
    } catch (error) {
      // 表单验证失败
    }
  }

  // 取消
  const handleCancel = () => {
    form.resetFields()
    setStockName('')
    onCancel()
  }

  return (
    <Modal
      title="添加股票到自选"
      open={visible}
      onOk={handleOk}
      onCancel={handleCancel}
      okText="添加"
      cancelText="取消"
      width={500}
    >
      <Spin spinning={loading}>
        <Form
          form={form}
          layout="vertical"
          autoComplete="off"
        >
          <Form.Item
            label="股票代码"
            name="stockCode"
            rules={[
              { required: true, message: '请输入股票代码' },
              { pattern: /^\d{6}$/, message: '请输入6位数字股票代码' }
            ]}
          >
            <Input
              placeholder="输入6位股票代码，如 600519"
              maxLength={6}
              suffix={
                <SearchOutlined
                  className="cursor-pointer text-blue-500"
                  onClick={handleSearch}
                />
              }
              onPressEnter={handleSearch}
            />
          </Form.Item>

          <Form.Item
            label="股票名称"
            name="stockName"
            rules={[{ required: true, message: '请先搜索股票信息' }]}
          >
            <Input
              placeholder="点击搜索图标获取股票名称"
              disabled
              value={stockName}
            />
          </Form.Item>

          <div className="text-gray-500 text-sm">
            提示：输入股票代码后，点击搜索图标或按回车键获取股票信息
          </div>
        </Form>
      </Spin>
    </Modal>
  )
}
